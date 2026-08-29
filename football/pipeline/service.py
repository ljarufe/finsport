import uuid
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from football.capital.baseline import (
    BASELINE_CONFIG,
    BASELINE_LABEL,
    run_research_baseline,
)
from football.capital.contracts import ENGINE_VERSION as CAPITAL_ENGINE_VERSION
from football.capture import run_capture
from football.models import (
    CaptureRun,
    CaptureWorkItem,
    Competition,
    Match,
    PipelineRun,
    PredictionExperiment,
)
from football.prediction.constants import ENGINE_VERSION as PREDICTION_ENGINE_VERSION
from football.prediction.service import predict_competition_day
from football.prediction.settlement import settle_prospective_predictions

from .contracts import PhaseResult, PhaseState, PipelineResult
from .hygiene import cleanup_cancelled_matches

PIPELINE_VERSION = "fs006-v1"
REPORT_SCHEMA = "fs006-report-v1"


def _parse_instant(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _prediction_candidates(capture_result, at):
    match_ids = {
        item.get("match_id")
        for item in capture_result.plan.get("items", [])
        if item.get("match_id")
    }
    local_timezone = ZoneInfo(settings.TIME_ZONE)
    matches = {
        match.pk: match
        for match in Match.objects.filter(pk__in=match_ids).select_related("season")
    }
    candidates = {}
    for item in capture_result.plan.get("items", []):
        if item.get("purpose") != CaptureWorkItem.Purpose.ODDS_CAPTURE:
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
            },
        )["match_ids"].append(match.pk)
    normalized = []
    for key in sorted(candidates):
        candidate = candidates[key]
        candidate["match_ids"] = sorted(set(candidate["match_ids"]))
        normalized.append(candidate)
    return normalized


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


def _experiment_report(experiment, *, created):
    produced = Counter(experiment.predictions.values_list("model_code", flat=True))
    unavailable = Counter()
    for key in (experiment.summary or {}).get("unavailable", {}):
        unavailable[key.split(":", 1)[0]] += 1
    for code, detail in (experiment.summary or {}).get("r45_arms", {}).items():
        if detail.get("status") == "UNAVAILABLE":
            unavailable[code] += 1
    policies = defaultdict(lambda: {"actionable": 0, "no_bet": 0})
    for code, action in experiment.decisions.values_list("policy_code", "action"):
        key = "no_bet" if action == "NO_BET" else "actionable"
        policies[code][key] += 1
    resolved = experiment.predictions.filter(actual_outcome__isnull=False).count()
    prediction_count = experiment.predictions.count()
    return {
        "id": experiment.pk,
        "created": created,
        "logical_identity": experiment.logical_identity,
        "competition_id": experiment.competition_id,
        "local_day": experiment.period_start.isoformat(),
        "intended_window": experiment.intended_window,
        "target_at": (
            experiment.target_at.isoformat() if experiment.target_at else None
        ),
        "cutoff": experiment.config.get("cutoff"),
        "sample_sizes": {
            "targets": experiment.summary.get("target_count", 0),
            "predictions": prediction_count,
            "decisions": experiment.decisions.count(),
            "resolved_predictions": resolved,
            "unresolved_predictions": prediction_count - resolved,
        },
        "models": {
            "produced": dict(sorted(produced.items())),
            "unavailable": dict(sorted(unavailable.items())),
        },
        "policies": {key: policies[key] for key in sorted(policies)},
    }


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
    experiments,
    cycle_experiments,
    capital_results,
    capture_data,
    cancellation_data,
    warnings,
):
    experiments_by_competition = defaultdict(list)
    for item in experiments:
        experiments_by_competition[item["competition_id"]].append(item)
    competition_rows = []
    for competition in competitions:
        rows = experiments_by_competition[competition.pk]
        competition_rows.append(
            {
                "id": competition.pk,
                "name": competition.name,
                "country": str(competition.country),
                "prediction_state": ("SUCCESS" if rows else "NO_WORK"),
                "prediction_experiments": rows,
            }
        )
    resolved = sum(row["sample_sizes"]["resolved_predictions"] for row in experiments)
    unresolved = sum(
        row["sample_sizes"]["unresolved_predictions"] for row in experiments
    )
    return {
        "schema_version": REPORT_SCHEMA,
        "generated_at": generated_at.isoformat(),
        "cutoff": at.isoformat(),
        "local_day": at.astimezone(ZoneInfo(settings.TIME_ZONE)).date().isoformat(),
        "windows": sorted(
            {row["intended_window"] for row in experiments if row["intended_window"]}
        ),
        "cycle_identity": cycle_identity,
        "versions": {
            "pipeline": PIPELINE_VERSION,
            "prediction_engine": PREDICTION_ENGINE_VERSION,
            "capital_engine": CAPITAL_ENGINE_VERSION,
            "capital_baseline": BASELINE_CONFIG,
            "capital_baseline_label": BASELINE_LABEL,
        },
        "phases": {name: result.as_dict() for name, result in phases.items()},
        "competitions_considered": competition_rows,
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
            "experiment_ids": [row["id"] for row in experiments],
            "experiment_count": len(experiments),
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
            "baseline": {
                "mode": "REPLAY",
                "initial_bankroll": "100",
                "policy": "FLAT_UNIT",
                "config": {"unit": "1"},
                "label": BASELINE_LABEL,
            },
            "results": capital_results,
            "produced_count": sum(
                item["status"] == "PRODUCED" for item in capital_results
            ),
            "unavailable_count": sum(
                item["status"] == "UNAVAILABLE" for item in capital_results
            ),
        },
        "cancelled_match_hygiene": cancellation_data,
        "sample_sizes": {
            "competitions": len(competitions),
            "prediction_experiments": len(experiments),
            "predictions": sum(
                row["sample_sizes"]["predictions"] for row in experiments
            ),
            "decisions": sum(row["sample_sizes"]["decisions"] for row in experiments),
            "resolved_predictions": resolved,
            "unresolved_predictions": unresolved,
        },
        "data_quality_warnings": warnings,
    }


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
                "capital_baseline": BASELINE_CONFIG,
            },
        )
        cycle_identity = str(run.cycle_identity)

    phases = {}
    errors = []
    warnings = []
    capture_data = {"provider_attempts": 0, "plan": {"items": []}}
    capture_result = None
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
        )
        capture_data = capture_result.as_dict()
        phases["CAPTURE"] = PhaseResult(
            _capture_state(capture_result, dry_run=dry_run),
            details=capture_data,
            reason="DRY_RUN" if dry_run else "",
        )
    except Exception as error:
        message = f"{type(error).__name__}:{error}"[:500]
        errors.append({"phase": "CAPTURE", "error": message})
        phases["CAPTURE"] = PhaseResult(PhaseState.FAILED, reason=message)

    candidates = _prediction_candidates(capture_result, at) if capture_result else []
    experiment_rows = []
    prediction_unavailable = []
    prediction_errors = []
    if dry_run:
        phases["PREDICTION"] = PhaseResult(
            PhaseState.SKIPPED,
            reason="DRY_RUN",
            details={
                "planned": [
                    {
                        **candidate,
                        "day": candidate["day"].isoformat(),
                        "target_at": candidate["target_at"].isoformat(),
                    }
                    for candidate in candidates
                ]
            },
        )
    else:
        for candidate in candidates:
            try:
                outcome = predict_competition_day(
                    candidate["competition_id"],
                    candidate["day"],
                    at,
                    logical_identity=candidate["logical_identity"],
                    intended_window=candidate["intended_window"],
                    target_at=candidate["target_at"],
                    match_ids=candidate["match_ids"],
                )
                if outcome.experiment is None:
                    prediction_unavailable.append(
                        {
                            "competition_id": candidate["competition_id"],
                            "logical_identity": candidate["logical_identity"],
                            "reason": outcome.reason,
                        }
                    )
                    continue
                experiment_rows.append(
                    _experiment_report(outcome.experiment, created=outcome.created)
                )
            except Exception as error:
                message = f"{type(error).__name__}:{error}"[:500]
                prediction_errors.append(
                    {
                        "competition_id": candidate["competition_id"],
                        "logical_identity": candidate["logical_identity"],
                        "error": message,
                    }
                )
        created_count = sum(row["created"] for row in experiment_rows)
        if prediction_errors:
            state = PhaseState.DEGRADED if experiment_rows else PhaseState.FAILED
        elif prediction_unavailable and not experiment_rows:
            state = PhaseState.UNAVAILABLE
        elif created_count:
            state = (
                PhaseState.DEGRADED if prediction_unavailable else PhaseState.SUCCESS
            )
        else:
            state = PhaseState.NO_WORK
        phases["PREDICTION"] = PhaseResult(
            state,
            details={
                "experiments": experiment_rows,
                "unavailable": prediction_unavailable,
                "errors": prediction_errors,
            },
        )
        errors.extend({"phase": "PREDICTION", **item} for item in prediction_errors)

    settlement_data = {}
    cancellation_data = {}
    result_errors = []
    try:
        cancellation_data = cleanup_cancelled_matches(dry_run=dry_run).as_dict()
    except Exception as error:
        message = f"{type(error).__name__}:{error}"[:500]
        result_errors.append({"operation": "CANC_HYGIENE", "error": message})
    try:
        settlement_data = settle_prospective_predictions(
            competition_ids=competition_ids,
            dry_run=dry_run,
        ).as_dict()
    except Exception as error:
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

    capital_results = []
    capital_errors = []
    if dry_run:
        phases["CAPITAL"] = PhaseResult(
            PhaseState.SKIPPED,
            reason="DRY_RUN",
            details={
                "baseline": BASELINE_CONFIG,
                "prospective_experiments_considered": PredictionExperiment.objects.filter(
                    mode=PredictionExperiment.MODE_PROSPECTIVE,
                    competition_id__in=competition_ids,
                ).count(),
            },
        )
    else:
        for experiment in PredictionExperiment.objects.filter(
            mode=PredictionExperiment.MODE_PROSPECTIVE,
            competition_id__in=competition_ids,
        ).order_by("id"):
            try:
                capital_results.append(run_research_baseline(experiment).as_dict())
            except Exception as error:
                capital_errors.append(
                    {
                        "prediction_experiment_id": experiment.pk,
                        "error": f"{type(error).__name__}:{error}"[:500],
                    }
                )
        produced = [item for item in capital_results if item["status"] == "PRODUCED"]
        created = [item for item in produced if item["created"]]
        unavailable = [
            item for item in capital_results if item["status"] == "UNAVAILABLE"
        ]
        if capital_errors:
            capital_state = (
                PhaseState.DEGRADED if capital_results else PhaseState.FAILED
            )
        elif created:
            capital_state = PhaseState.DEGRADED if unavailable else PhaseState.SUCCESS
        elif produced:
            capital_state = PhaseState.NO_WORK
        elif unavailable:
            capital_state = PhaseState.UNAVAILABLE
        else:
            capital_state = PhaseState.NO_WORK
        phases["CAPITAL"] = PhaseResult(
            capital_state,
            details={"results": capital_results, "errors": capital_errors},
        )
        errors.extend({"phase": "CAPITAL", **item} for item in capital_errors)

    if len(competitions) < 2:
        warnings.append(
            "REAL_MULTI_LEAGUE_UAT_UNAVAILABLE: fewer than two enabled domestic League competitions"
        )
    warnings.extend(
        f"PREDICTION_UNAVAILABLE:{item['competition_id']}:{item['reason']}"
        for item in prediction_unavailable
    )
    warnings.extend(
        f"CAPITAL_UNAVAILABLE:{item['prediction_experiment_id']}:{item['reason']}"
        for item in capital_results
        if item["status"] == "UNAVAILABLE"
    )
    generated_at = timezone.now()
    phases["REPORT"] = PhaseResult(PhaseState.SUCCESS)
    cycle_created = {row["id"]: row["created"] for row in experiment_rows}
    rolling_experiment_rows = [
        _experiment_report(
            experiment,
            created=cycle_created.get(experiment.pk, False),
        )
        for experiment in PredictionExperiment.objects.filter(
            mode=PredictionExperiment.MODE_PROSPECTIVE,
            competition__enabled=True,
            competition__competition_type="League",
            competition__country__gt="",
        )
        .select_related("competition")
        .order_by("competition_id", "period_start", "target_at", "id")
    ]
    report = _report(
        at=at,
        generated_at=generated_at,
        cycle_identity=cycle_identity,
        phases=phases,
        competitions=competitions,
        experiments=rolling_experiment_rows,
        cycle_experiments=experiment_rows,
        capital_results=capital_results,
        capture_data=capture_data,
        cancellation_data=cancellation_data,
        warnings=warnings,
    )
    status = _phase_status(phases)
    if run:
        capture_run_ids = [capture_data["run_id"]] if capture_data.get("run_id") else []
        prediction_ids = sorted({row["id"] for row in experiment_rows})
        capital_ids = sorted(
            {
                item["capital_experiment_id"]
                for item in capital_results
                if item.get("capital_experiment_id")
            }
        )
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
    return PipelineResult(
        run_id=run.pk if run else None,
        cycle_identity=cycle_identity,
        status=status,
        phases={name: result.as_dict() for name, result in phases.items()},
        report=report,
        dry_run=dry_run,
    )
