import hashlib
import json
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from football.capital.runtime import (
    EXECUTION_VERSION as CAPITAL_EXECUTION_VERSION,
)
from football.capital.runtime import (
    RUNTIME_VERSION as CAPITAL_RUNTIME_VERSION,
)
from football.capital.runtime import (
    run_automatic_runtime,
)
from football.capture import run_capture
from football.capture.contracts import MARKET_CONSENSUS_WINDOW_NAMES
from football.historical import historical_coverage_is_current
from football.models import (
    CaptureRun,
    CaptureWorkItem,
    Competition,
    HistoricalCoverage,
    Match,
    PipelineRun,
)
from football.observability.events import emit_event
from football.observability.pipeline import emit_pipeline_terminal, exception_diagnostic
from football.observability.reconciliation import emit_reconciliation_pending
from football.prediction.constants import ENGINE_VERSION as PREDICTION_ENGINE_VERSION
from football.prediction.evidence import sporting_evidence_basis
from football.prediction.service import latest_selected_config
from football.prediction.settlement import settle_prospective_predictions

from .contracts import PhaseResult, PhaseState, PipelineResult
from .hygiene import cleanup_cancelled_matches

PIPELINE_VERSION = "fs006-v1"
REPORT_SCHEMA = "fs022-operational-report-v1"


def _parse_instant(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _r45_capture_prediction_candidates(capture_result, at):
    """Evaluate R45 from current due acquisition work without another capture."""
    if not settings.FOOTBALL_MODERNIZED_R45_ENABLED:
        return []
    work_items = capture_result.plan.get("items", [])
    match_ids = {item.get("match_id") for item in work_items if item.get("match_id")}
    local_timezone = ZoneInfo(settings.TIME_ZONE)
    matches = {
        match.pk: match
        for match in Match.objects.filter(pk__in=match_ids).select_related("season")
    }
    candidates = {}
    for item in work_items:
        if item.get("purpose") != CaptureWorkItem.Purpose.ODDS_CAPTURE:
            continue
        if item.get("intended_window") not in MARKET_CONSENSUS_WINDOW_NAMES:
            continue
        if not all(
            item.get(key)
            for key in (
                "match_id",
                "competition_id",
                "intended_window",
                "target_at",
                "not_before",
                "not_after",
            )
        ):
            continue
        not_before = _parse_instant(item["not_before"])
        not_after = _parse_instant(item["not_after"])
        if not not_before <= at <= not_after:
            continue
        target_at = _parse_instant(item["target_at"])
        match = matches.get(item["match_id"])
        if match is None:
            continue
        day = match.kickoff.astimezone(local_timezone).date()
        identity = (
            f"{PIPELINE_VERSION}:prediction:{item['competition_id']}:{day}:"
            f"{item['intended_window']}:{target_at.isoformat()}"
        )
        candidates.setdefault(
            identity,
            {
                "competition_id": item["competition_id"],
                "day": day,
                "intended_window": item["intended_window"],
                "target_at": target_at,
                "logical_identity": identity,
                "match_ids": [],
                "model_codes": ["MODERNIZED_R45"],
                "cutoff": at,
                "evidence_identity": "",
            },
        )["match_ids"].append(match.pk)
    normalized = []
    for key in sorted(candidates):
        candidate = candidates[key]
        candidate["match_ids"] = sorted(set(candidate["match_ids"]))
        normalized.append(candidate)
    return normalized


def _market_consensus_prediction_candidates(capture_result, at):
    """Create MC v2 candidates only from a completed durable MC capture batch."""
    work_items = capture_result.completed_work
    accepted_statuses = {
        CaptureWorkItem.Status.SUCCESS,
        CaptureWorkItem.Status.SUCCESS_EMPTY,
        CaptureWorkItem.Status.LATE_CAPTURE,
    }
    batch_cutoff = at
    executed_at_by_identity = {}
    if capture_result.run_id:
        completed_at = (
            CaptureRun.objects.filter(pk=capture_result.run_id)
            .values_list("completed_at", flat=True)
            .first()
        )
        if completed_at is not None:
            batch_cutoff = completed_at
        executed_at_by_identity = dict(
            CaptureWorkItem.objects.filter(
                run_id=capture_result.run_id,
                purpose=CaptureWorkItem.Purpose.ODDS_CAPTURE,
                status__in=(
                    CaptureWorkItem.Status.SUCCESS,
                    CaptureWorkItem.Status.SUCCESS_EMPTY,
                    CaptureWorkItem.Status.LATE_CAPTURE,
                ),
                executed_at__isnull=False,
            ).values_list("logical_identity", "executed_at")
        )
    match_ids = {item.get("match_id") for item in work_items if item.get("match_id")}
    local_timezone = ZoneInfo(settings.TIME_ZONE)
    matches = {
        match.pk: match
        for match in Match.objects.filter(pk__in=match_ids).select_related("season")
    }
    candidates = {}
    for item in work_items:
        if item.get("purpose") != CaptureWorkItem.Purpose.ODDS_CAPTURE:
            continue
        if item.get("intended_window") not in MARKET_CONSENSUS_WINDOW_NAMES:
            continue
        if item.get("status") not in accepted_statuses:
            continue
        if not all(
            item.get(key)
            for key in (
                "match_id",
                "competition_id",
                "intended_window",
                "target_at",
                "not_before",
                "not_after",
            )
        ):
            continue
        target_at = _parse_instant(item["target_at"])
        match = matches.get(item["match_id"])
        if match is None:
            continue
        day = match.kickoff.astimezone(local_timezone).date()
        identity = (
            f"fs013:market-consensus:{item['competition_id']}:{day}:"
            f"{item['intended_window']}:{target_at.isoformat()}"
        )
        candidates.setdefault(
            identity,
            {
                "competition_id": item["competition_id"],
                "day": day,
                "intended_window": item["intended_window"],
                "target_at": target_at,
                "logical_identity": identity,
                "match_ids": [],
                "model_codes": ["MARKET_CONSENSUS"],
                "cutoff": batch_cutoff,
                "evidence_identity": "",
                "market_evidence_identity": "",
                "capture_work_identities": [],
                "market_evidence_not_before_by_match": {},
            },
        )
        candidates[identity]["match_ids"].append(match.pk)
        candidates[identity]["capture_work_identities"].append(item["logical_identity"])
        executed_at = executed_at_by_identity.get(item["logical_identity"])
        if executed_at is not None:
            candidates[identity]["market_evidence_not_before_by_match"][
                str(match.pk)
            ] = executed_at
    normalized = []
    for key in sorted(candidates):
        candidate = candidates[key]
        candidate["match_ids"] = sorted(set(candidate["match_ids"]))
        candidate["capture_work_identities"] = sorted(
            set(candidate["capture_work_identities"])
        )
        evidence_payload = {
            "cutoff": candidate["cutoff"].isoformat(),
            "capture_work_identities": candidate["capture_work_identities"],
        }
        candidate["market_evidence_identity"] = hashlib.sha256(
            json.dumps(evidence_payload, sort_keys=True).encode()
        ).hexdigest()
        normalized.append(candidate)
    return normalized


def _prediction_candidates(capture_result, at, *, dry_run=False):
    candidates = _r45_capture_prediction_candidates(capture_result, at)
    if not dry_run:
        candidates.extend(_market_consensus_prediction_candidates(capture_result, at))
    return candidates


def _dixon_coles_candidates(at):
    return _sporting_candidates(at, model_code="DIXON_COLES")


def _sporting_candidates(at, *, model_code):
    horizon = at + timedelta(hours=settings.FOOTBALL_CAPTURE_HORIZON_HOURS)
    queryset = Match.objects.filter(
        season__competition__enabled=True,
        status_short__in=("TBD", "NS"),
        kickoff__gt=at,
        kickoff__lte=horizon,
    )
    if model_code == "DIXON_COLES":
        queryset = queryset.filter(
            season__competition__historical_coverage__status=HistoricalCoverage.Status.COMPLETE
        )
    matches = list(
        queryset.select_related(
            "season",
            "season__competition",
            "season__competition__historical_coverage",
        ).order_by("season__competition_id", "kickoff", "id")
    )
    local_timezone = ZoneInfo(settings.TIME_ZONE)
    groups = defaultdict(list)
    current_coverage = {}
    for match in matches:
        competition = match.season.competition
        if model_code == "DIXON_COLES":
            if competition.pk not in current_coverage:
                current_coverage[competition.pk] = historical_coverage_is_current(
                    competition, competition.historical_coverage
                )
            if not current_coverage[competition.pk]:
                continue
        groups[
            (
                match.season.competition_id,
                match.kickoff.astimezone(local_timezone).date(),
            )
        ].append(match)
    candidates = []
    for (competition_id, day), targets in sorted(groups.items()):
        competition = targets[0].season.competition
        selected, _ = latest_selected_config(competition)
        cutoff = min(match.kickoff for match in targets) - timedelta(microseconds=1)
        evidence_identity, _, history = sporting_evidence_basis(
            competition,
            targets,
            cutoff=cutoff,
            config=selected[model_code.lower()],
            model_code=model_code,
        )
        if model_code != "DIXON_COLES" and not history:
            continue
        candidates.append(
            {
                "competition_id": competition_id,
                "day": day,
                "intended_window": "football-evidence",
                "target_at": None,
                "logical_identity": (
                    f"fs011:dc:{evidence_identity}"
                    if model_code == "DIXON_COLES"
                    else f"fs012:{model_code}:{evidence_identity}"
                ),
                "match_ids": [match.pk for match in targets],
                "model_codes": [model_code],
                "cutoff": cutoff,
                "evidence_identity": evidence_identity,
            }
        )
    return candidates


def _capture_state(capture_result, *, dry_run):
    if dry_run:
        return PhaseState.SKIPPED
    if capture_result.status in (CaptureRun.Status.SUCCESS,):
        return PhaseState.SUCCESS
    if capture_result.status in (
        CaptureRun.Status.NO_WORK,
        CaptureRun.Status.CONCURRENT_EXECUTOR,
    ):
        return PhaseState.NO_WORK
    if capture_result.status == CaptureRun.Status.PARTIAL:
        return PhaseState.DEGRADED
    return PhaseState.FAILED


def _capital_experiment_allowed(experiment):
    """Exclude R45-only experiments while the R45 Capital path is suspended."""
    if settings.FOOTBALL_MODERNIZED_R45_CAPITAL_ENABLED:
        return True
    model_codes = set((experiment.config or {}).get("model_codes") or [])
    return model_codes != {"MODERNIZED_R45"}


def _phase_status(phase_results):
    domain_states = [
        phase_results[name].state
        for name in ("CAPTURE", "PREDICTION", "RESULT_SETTLEMENT", "CAPITAL")
    ]
    if PhaseState.FAILED in domain_states:
        successful = any(state == PhaseState.SUCCESS for state in domain_states)
        return PipelineRun.Status.DEGRADED if successful else PipelineRun.Status.FAILED
    if PhaseState.DEGRADED in domain_states:
        return PipelineRun.Status.DEGRADED
    if PhaseState.SUCCESS in domain_states:
        return PipelineRun.Status.SUCCESS
    return PipelineRun.Status.NO_WORK


def _report(
    *,
    at,
    generated_at,
    cycle_identity,
    phases,
    competitions,
    cycle_experiments,
    capital_runtime_result,
    capture_data,
    cancellation_data,
    warnings,
):
    """Bounded operational receipt for this wake, never a rolling experiment report."""
    return {
        "schema_version": REPORT_SCHEMA,
        "generated_at": generated_at.isoformat(),
        "cutoff": at.isoformat(),
        "local_day": at.astimezone(ZoneInfo(settings.TIME_ZONE)).date().isoformat(),
        "cycle_identity": cycle_identity,
        "versions": {
            "pipeline": PIPELINE_VERSION,
            "prediction_engine": PREDICTION_ENGINE_VERSION,
            "capital_runtime": CAPITAL_RUNTIME_VERSION,
            "capital_execution": CAPITAL_EXECUTION_VERSION,
        },
        "phases": {name: result.as_dict() for name, result in phases.items()},
        "competitions_considered": [
            {"id": row.pk, "name": row.name, "country": str(row.country)}
            for row in competitions
        ],
        "capture": {
            "state": phases["CAPTURE"].state,
            "run_ids": [capture_data["run_id"]] if capture_data.get("run_id") else [],
            "provider_attempts": capture_data.get("provider_attempts", 0),
            "provider_pages": capture_data.get("provider_pages", 0),
            "provider_retries": capture_data.get("provider_retries", 0),
            "quota_before": capture_data.get("quota_before", {}),
            "quota_after": capture_data.get("quota_after", {}),
        },
        "prediction": {
            "state": phases["PREDICTION"].state,
            "experiment_ids": [row["id"] for row in cycle_experiments],
            "experiment_count": len(cycle_experiments),
            "current_cycle_experiment_ids": [row["id"] for row in cycle_experiments],
            "created_count": sum(row["created"] for row in cycle_experiments),
            "reused_count": sum(not row["created"] for row in cycle_experiments),
        },
        "result_settlement": {
            "state": phases["RESULT_SETTLEMENT"].state,
            **phases["RESULT_SETTLEMENT"].details,
        },
        "capital": {
            "state": phases["CAPITAL"].state,
            "runtime": capital_runtime_result,
        },
        "cancelled_match_hygiene": cancellation_data,
        "data_quality_warnings": warnings,
    }


def _global_prediction_phase(evaluations, experiment_rows, runtime_errors):
    counts = dict(Counter(row["status"] for row in evaluations))
    good = sum(counts.get(key, 0) for key in ("COMPLETED", "NO_BET", "DUPLICATE"))
    bad = sum(
        counts.get(key, 0)
        for key in ("FAILED", "BLOCKED", "UNAVAILABLE", "MISSED_WINDOW")
    )
    authority_errors = [error for error in runtime_errors if "FS022" in error]
    if counts.get("FAILED"):
        state = PhaseState.DEGRADED if good else PhaseState.FAILED
    elif bad or authority_errors:
        state = PhaseState.DEGRADED if good else PhaseState.UNAVAILABLE
    elif good:
        state = PhaseState.SUCCESS
    else:
        state = PhaseState.NO_WORK
    reasons = sorted({row["reason"] for row in evaluations})
    return PhaseResult(
        state,
        reason=(
            ",".join(reasons)[:500]
            if reasons
            else ("AUTHORITY_ADMISSION_BLOCKED" if authority_errors else "")
        ),
        details={
            "experiments": experiment_rows,
            "evaluations": evaluations,
            "status_counts": counts,
            "unavailable": [
                row
                for row in evaluations
                if row["status"] in {"UNAVAILABLE", "MISSED_WINDOW", "BLOCKED"}
            ],
            "errors": [row for row in evaluations if row["status"] == "FAILED"],
            "authority_errors": authority_errors,
        },
    )


def run_pipeline(
    *,
    at=None,
    dry_run=False,
    trigger=PipelineRun.Trigger.MANUAL,
    max_provider_attempts=None,
):
    at = at or timezone.now()
    if timezone.is_naive(at):
        raise ValueError("Pipeline at/cutoff must include an explicit timezone offset.")
    if max_provider_attempts is not None and max_provider_attempts < 1:
        raise ValueError("max_provider_attempts must be positive.")
    local_day = at.astimezone(ZoneInfo(settings.TIME_ZONE)).date()
    started_at = timezone.now()
    competitions = list(
        Competition.objects.filter(
            enabled=True,
            competition_type="League",
            country__gt="",
        ).order_by("id")
    )
    competition_ids = [competition.pk for competition in competitions]
    run = None
    cycle_identity = str(uuid.uuid4())
    if not dry_run:
        run = PipelineRun.objects.create(
            trigger=trigger,
            planning_at=at,
            local_day=local_day,
            started_at=started_at,
            config_snapshot={
                "pipeline_version": PIPELINE_VERSION,
                "report_schema": REPORT_SCHEMA,
                "max_provider_attempts": max_provider_attempts,
                "capital_runtime": CAPITAL_RUNTIME_VERSION,
                "capital_execution": CAPITAL_EXECUTION_VERSION,
            },
        )
        cycle_identity = str(run.cycle_identity)

    phases = {}
    errors = []
    warnings = []
    capture_data = {"provider_attempts": 0, "plan": {"items": []}}
    capture_result = None
    operational_causes = []
    if not dry_run:
        # Establish the prospective era and close old admission before capture.
        # Capture/settlement still run if authority resolution is unavailable.
        from football.strategy.deployment import provision

        try:
            provision(at=started_at)
        except (RuntimeError, ValueError) as error:
            warnings.append(
                f"STRATEGY_ADMISSION_BLOCKED:{type(error).__name__}:{error}"[:500]
            )
    try:
        capture_result = run_capture(
            at=at,
            dry_run=dry_run,
            trigger=(
                CaptureRun.Trigger.SCHEDULER
                if trigger == PipelineRun.Trigger.SCHEDULER
                else CaptureRun.Trigger.MANUAL
            ),
            max_provider_attempts=max_provider_attempts,
            allow_bootstrap=trigger == PipelineRun.Trigger.SCHEDULER,
        )
        capture_data = capture_result.as_dict()
        if capture_result.operational_cause:
            operational_causes.append(capture_result.operational_cause)
        phases["CAPTURE"] = PhaseResult(
            _capture_state(capture_result, dry_run=dry_run),
            details=capture_data,
            reason="DRY_RUN" if dry_run else "",
        )
    except Exception as error:
        operational_causes.append(
            {
                **exception_diagnostic(error),
                "component": "capture",
                "operation": "run_capture",
            }
        )
        message = f"{type(error).__name__}:{error}"[:500]
        errors.append({"phase": "CAPTURE", "error": message})
        phases["CAPTURE"] = PhaseResult(PhaseState.FAILED, reason=message)

    # FS-022 evaluates only #209, from durable T-30 work, inside the serial
    # Capital admission boundary. Manual Lab services retain all alternatives.
    experiment_rows = []
    phases["PREDICTION"] = PhaseResult(
        PhaseState.SKIPPED if dry_run else PhaseState.NO_WORK,
        reason="DRY_RUN" if dry_run else "",
        details=(
            {"planned": []}
            if dry_run
            else {"experiments": [], "unavailable": [], "errors": []}
        ),
    )

    settlement_data = {}
    cancellation_data = {}
    result_errors = []
    try:
        cancellation_data = cleanup_cancelled_matches(dry_run=dry_run).as_dict()
    except Exception as error:
        operational_causes.append(
            {
                **exception_diagnostic(error),
                "component": "settlement",
                "operation": "cleanup_cancelled_matches",
            }
        )
        message = f"{type(error).__name__}:{error}"[:500]
        result_errors.append({"operation": "CANC_HYGIENE", "error": message})
    try:
        settlement_data = settle_prospective_predictions(
            competition_ids=competition_ids,
            dry_run=dry_run,
        ).as_dict()
    except Exception as error:
        operational_causes.append(
            {
                **exception_diagnostic(error),
                "component": "settlement",
                "operation": "settle_prospective_predictions",
            }
        )
        message = f"{type(error).__name__}:{error}"[:500]
        result_errors.append({"operation": "SETTLEMENT", "error": message})
    if dry_run:
        result_state = PhaseState.SKIPPED
    elif result_errors:
        result_state = (
            PhaseState.DEGRADED
            if settlement_data or cancellation_data
            else PhaseState.FAILED
        )
    elif any(
        item.get("status") == "SUCCESS" for item in (settlement_data, cancellation_data)
    ):
        result_state = PhaseState.SUCCESS
    else:
        result_state = PhaseState.NO_WORK
    phases["RESULT_SETTLEMENT"] = PhaseResult(
        result_state,
        reason="DRY_RUN" if dry_run else "",
        details={
            "settlement": settlement_data,
            "cancellation_hygiene": cancellation_data,
            "errors": result_errors,
        },
    )
    errors.extend({"phase": "RESULT_SETTLEMENT", **item} for item in result_errors)

    capital_runtime_result = {}
    capital_errors = []
    if dry_run:
        phases["CAPITAL"] = PhaseResult(
            PhaseState.SKIPPED,
            reason="DRY_RUN",
            details={
                "runtime_version": CAPITAL_RUNTIME_VERSION,
                "execution_version": CAPITAL_EXECUTION_VERSION,
                "automatic_configs": 1,
            },
        )
    else:
        try:
            capital_runtime_result = run_automatic_runtime(
                capture_run_id=capture_data.get("run_id"),
                at=at,
            ).as_dict()
        except Exception as error:
            operational_causes.append(
                {
                    **exception_diagnostic(error),
                    "component": "capital",
                    "operation": "run_automatic_runtime",
                }
            )
            capital_errors.append(
                {
                    "operation": "CAPITAL_V2_RUNTIME",
                    "error": f"{type(error).__name__}:{error}"[:500],
                }
            )
        if capital_errors:
            capital_state = PhaseState.FAILED
        elif capital_runtime_result.get("status") == "DEGRADED":
            capital_state = PhaseState.DEGRADED
        elif capital_runtime_result.get("status") == "PRODUCED":
            capital_state = PhaseState.SUCCESS
        else:
            capital_state = PhaseState.NO_WORK
        phases["CAPITAL"] = PhaseResult(
            capital_state,
            reason=(
                capital_runtime_result.get("result_debt_state")
                or ",".join(capital_runtime_result.get("errors", []))[:500]
                or ",".join(item["error"] for item in capital_errors)[:500]
            ),
            details={
                "runtime": capital_runtime_result,
                "errors": capital_errors,
            },
        )
        errors.extend({"phase": "CAPITAL", **item} for item in capital_errors)

        if capital_runtime_result.get("settled", 0):
            try:
                catch_up = settle_prospective_predictions(
                    competition_ids=competition_ids,
                    dry_run=False,
                ).as_dict()
                result_phase = phases["RESULT_SETTLEMENT"]
                result_phase.details["post_capital_catch_up"] = catch_up
                if catch_up.get("status") == "SUCCESS" and result_phase.state in (
                    PhaseState.NO_WORK,
                    PhaseState.SUCCESS,
                ):
                    phases["RESULT_SETTLEMENT"] = PhaseResult(
                        PhaseState.SUCCESS,
                        details=result_phase.details,
                        reason=result_phase.reason,
                    )
            except Exception as error:
                message = f"{type(error).__name__}:{error}"[:500]
                result_phase = phases["RESULT_SETTLEMENT"]
                result_phase.details.setdefault("errors", []).append(
                    {"operation": "POST_CAPITAL_CATCH_UP", "error": message}
                )
                if result_phase.state != PhaseState.FAILED:
                    phases["RESULT_SETTLEMENT"] = PhaseResult(
                        PhaseState.DEGRADED,
                        details=result_phase.details,
                        reason=result_phase.reason,
                    )
                errors.append(
                    {
                        "phase": "RESULT_SETTLEMENT",
                        "operation": "POST_CAPITAL_CATCH_UP",
                        "error": message,
                    }
                )

    if not dry_run:
        # BSD has its own budget. Run after protected API-F capture and
        # Capital settlement so BSD latency never delays API-F fallback.
        from football.providers.bsd_continuity import run_bsd_continuity

        try:
            capture_data["bsd_continuity"] = run_bsd_continuity(at=at)
            if capture_data["bsd_continuity"]["errors"]:
                warnings.extend(capture_data["bsd_continuity"]["errors"])
        except Exception as error:
            warnings.append(f"BSD_CONTINUITY:{type(error).__name__}:{error}"[:500])

    if dry_run:
        from football.strategy.recovery import plan_global_evaluations

        phases["PREDICTION"] = PhaseResult(
            PhaseState.SKIPPED,
            reason="DRY_RUN",
            details=plan_global_evaluations(
                at=at, capture_plan=capture_data.get("plan") if capture_result else None
            ),
        )
    else:
        evaluations = capital_runtime_result.get("evaluations", [])
        created_ids = {
            row["experiment_id"] for row in evaluations if row.get("created_experiment")
        }
        experiment_ids = {
            row["experiment_id"] for row in evaluations if row.get("experiment_id")
        }
        experiment_rows = [
            {"id": experiment_id, "created": experiment_id in created_ids}
            for experiment_id in sorted(experiment_ids)
        ]
        phases["PREDICTION"] = _global_prediction_phase(
            evaluations, experiment_rows, capital_runtime_result.get("errors", [])
        )
        for row in evaluations:
            if row["status"] in {"FAILED", "BLOCKED", "UNAVAILABLE", "MISSED_WINDOW"}:
                operational_causes.append(
                    dict(
                        component="prediction",
                        operation="evaluate_prospective_t30",
                        failure_kind="prediction_evaluation_" + row["status"].lower(),
                        provider="API-Football",
                        context={"reason": row["reason"], "status": row["status"]},
                    )
                )
        errors.extend(
            {
                "phase": "PREDICTION",
                "work_id": row["work_id"],
                "error": row["details"].get("error", row["reason"]),
            }
            for row in evaluations
            if row["status"] == "FAILED"
        )

    if len(competitions) < 2:
        warnings.append(
            "REAL_MULTI_LEAGUE_UAT_UNAVAILABLE: fewer than two enabled domestic League competitions"
        )
    warnings.extend(
        f"CAPITAL_DEGRADED:{item}" for item in capital_runtime_result.get("errors", [])
    )
    generated_at = timezone.now()
    phases["REPORT"] = PhaseResult(PhaseState.SUCCESS)
    report = _report(
        at=at,
        generated_at=generated_at,
        cycle_identity=cycle_identity,
        phases=phases,
        competitions=competitions,
        cycle_experiments=experiment_rows,
        capital_runtime_result=capital_runtime_result,
        capture_data=capture_data,
        cancellation_data=cancellation_data,
        warnings=warnings,
    )
    status = _phase_status(phases)
    if run:
        capture_run_ids = sorted(
            {
                row["capture_run_id"]
                for row in capital_runtime_result.get("evaluations", [])
            }
            | ({capture_data["run_id"]} if capture_data.get("run_id") else set())
        )
        prediction_ids = sorted({row["id"] for row in experiment_rows})
        capital_ids = []
        run.status = status
        run.completed_at = generated_at
        run.phase_states = {name: result.as_dict() for name, result in phases.items()}
        run.capture_run_ids = capture_run_ids
        run.prediction_experiment_ids = prediction_ids
        run.capital_experiment_ids = capital_ids
        run.warnings = warnings
        run.errors = errors
        run.report = report
        run.save(
            update_fields=[
                "status",
                "completed_at",
                "phase_states",
                "capture_run_ids",
                "prediction_experiment_ids",
                "capital_experiment_ids",
                "warnings",
                "errors",
                "report",
                "modified",
            ]
        )
        emit_pipeline_terminal(run, causes=operational_causes)
        try:
            emit_reconciliation_pending(
                pipeline_run_id=run.pk,
                capture_run_id=(run.capture_run_ids or [None])[0],
            )
        except Exception as error:
            emit_event(
                event_code="RECONCILIATION_CHECK_FAILED",
                severity="ERROR",
                component="reconciliation",
                operation="aggregate_pending_source_refs",
                outcome="FAILED",
                failure_kind="database_dependency",
                human_summary="Pending reconciliation could not be aggregated.",
                pipeline_run_id=run.pk,
                exception=error,
            )
    return PipelineResult(
        run_id=run.pk if run else None,
        cycle_identity=cycle_identity,
        status=status,
        phases={name: result.as_dict() for name, result in phases.items()},
        report=report,
        dry_run=dry_run,
    )
