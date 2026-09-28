"""Bounded recovery and persistent classification, without network or writes in plans."""

from django.db.models import Case, IntegerField, Q, Value, When

from football.models import CapitalDeployment, CapitalEvaluation, CaptureWorkItem
from football.observability.events import emit_event, sanitize_text

RECOVERY_LIMIT = 100
IGNORED = ("NOT_DUE", "PLANNED", "ALREADY_FULFILLED", "CONCURRENT_EXECUTOR")


def evaluation_work(deployment, *, capture_run_id=None, at):
    works = CaptureWorkItem.objects.filter(
        purpose="ODDS_CAPTURE",
        intended_window="market-t30m",
        match__isnull=False,
        completed_at__isnull=False,
        run__completed_at__isnull=False,
    ).exclude(status__in=IGNORED)
    current = Q(run_id=capture_run_id) if capture_run_id else Q(pk__in=[])
    if deployment is not None and deployment.activated_at is not None:
        done = CapitalEvaluation.objects.filter(
            deployment=deployment, retryable=False
        ).values("work_id")
        recover = Q(
            source__code="api_football",
            completed_at__gte=deployment.activated_at,
            completed_at__lte=at,
            run__completed_at__lte=at,
        ) & ~Q(pk__in=done)
        works = works.filter(current | recover)
    else:
        works = works.filter(current)
    return list(
        works.select_related("match__season__competition", "run", "source", "market")
        .annotate(
            recovery_priority=Case(
                When(current, then=Value(0)),
                When(match__kickoff__gt=at, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        )
        .order_by("recovery_priority", "target_at", "pk")[:RECOVERY_LIMIT]
    )


def receipt_row(receipt, *, reused=False):
    return {
        "work_id": receipt.work_id,
        "capture_run_id": receipt.work.run_id,
        "match_id": receipt.work.match_id,
        "competition_id": receipt.work.match.competition.pk,
        "status": receipt.status,
        "reason": receipt.reason,
        "experiment_id": receipt.experiment_id,
        "created_experiment": not reused
        and receipt.details.get("created_experiment", False),
        "retryable": receipt.retryable,
        "reused": reused,
        "details": receipt.details,
    }


def save_receipt(
    deployment,
    work,
    *,
    status,
    reason,
    at,
    experiment=None,
    retryable=False,
    details=None,
):
    receipt, created = CapitalEvaluation.objects.get_or_create(
        deployment=deployment,
        work=work,
        defaults=dict(status=status, reason=reason, attempted_at=at),
    )
    if not created:
        receipt.attempts += 1
    receipt.status, receipt.reason, receipt.attempted_at = status, reason[:120], at
    receipt.experiment, receipt.retryable = experiment, retryable
    receipt.details = dict(
        details or {},
        capture_status=work.status,
        capture_source_id=work.source_id,
        capture_market_id=work.market_id,
        capture_work_identity=work.logical_identity,
        original_executed_at=work.executed_at.isoformat() if work.executed_at else None,
        original_completed_at=work.completed_at.isoformat(),
        original_cutoff=work.run.completed_at.isoformat(),
        scientific_selection_config_identity=deployment.selection.get(
            "prediction_config_identity"
        ),
        prospective_config_identity=deployment.selection.get(
            "prospective_prediction_config_identity"
        ),
    )
    receipt.save()
    row = receipt_row(receipt)
    # Emission is best-effort; the receipt remains the transactional audit source.
    emit_event(
        event_code="GLOBAL_PREDICTION_EVALUATED",
        component="prediction",
        operation="evaluate_prospective_t30",
        outcome=status,
        severity=(
            "ERROR"
            if status == "FAILED"
            else (
                "WARNING"
                if status in {"UNAVAILABLE", "MISSED_WINDOW", "BLOCKED"}
                else "INFO"
            )
        ),
        human_summary=f"T-30 work {work.pk}: {status} {reason}",
        capture_run_id=work.run_id,
        match_id=work.match_id,
        competition_id=work.match.competition.pk,
        prediction_experiment_id=receipt.experiment_id,
        provider="API-Football",
        context={"reason": reason, "status": status, "attempts": receipt.attempts},
        occurred_at=at,
    )
    return row


def record_authority_failure(capture_run_id, *, at, error):
    from .deployment import locked_deployment

    deployment = locked_deployment()
    return [
        save_receipt(
            deployment,
            work,
            status="BLOCKED",
            reason="AUTHORITY_ADMISSION_BLOCKED",
            at=at,
            retryable=True,
            details={"error": sanitize_text(error, 500)},
        )
        for work in evaluation_work(deployment, capture_run_id=capture_run_id, at=at)
        if not CapitalEvaluation.objects.filter(
            deployment=deployment, work=work, retryable=False
        ).exists()
    ]


def plan_global_evaluations(*, at, capture_plan=None):
    """Inspect actual recoverable rows and planned capture tasks; never provision."""
    deployment = CapitalDeployment.objects.filter(pk=1).first()
    from .authority import resolve_authority
    from .deployment import admission_reason
    from .prospective import capture_reason, live_selection

    try:
        resolve_authority()
        gate = (
            admission_reason(deployment, deployment.config)
            if deployment and deployment.config_id
            else "REQUIRES_PROVISIONING"
        )
    except (RuntimeError, ValueError):
        gate = "AUTHORITY_ADMISSION_BLOCKED"
    rows = []
    for work in evaluation_work(deployment, at=at):
        classification = "MISSED_EXECUTION_WINDOW" if at >= work.match.kickoff else gate
        if not classification:
            classification = capture_reason(work, deployment)
            if not classification:
                classification = (
                    "VALID_CAPTURE_AWAITING_EVALUATION"
                    if live_selection(work).quotes
                    else "INPUT_QUOTES_MISSING"
                )
        rows.append(
            {
                "work_id": work.pk,
                "capture_run_id": work.run_id,
                "match_id": work.match_id,
                "target_at": work.target_at.isoformat() if work.target_at else None,
                "cutoff": work.run.completed_at.isoformat(),
                "classification": classification,
            }
        )
    proposed = [
        item
        for item in (capture_plan or {}).get("items", [])
        if item.get("purpose") == "ODDS_CAPTURE"
        and item.get("intended_window") == "market-t30m"
    ]
    return {
        "planned": rows,
        "capture_planned": proposed,
        "inspected": True,
        "capture_plan_inspected": capture_plan is not None,
        "recovery_limit": RECOVERY_LIMIT,
        "admission_state": deployment.state if deployment else "NOT_PROVISIONED",
        "admission_reason": gate,
        "eligible_prediction_work_count": sum(
            row["classification"] == "VALID_CAPTURE_AWAITING_EVALUATION" for row in rows
        ),
    }
