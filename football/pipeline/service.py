import hashlib
import json
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from football.capital.runtime import (
    AUTOMATIC_CONFIGS,
    run_automatic_runtime,
)
from football.capital.runtime import (
    EXECUTION_VERSION as CAPITAL_EXECUTION_VERSION,
)
from football.capital.runtime import (
    RUNTIME_VERSION as CAPITAL_RUNTIME_VERSION,
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
    PredictionExperiment,
)
from football.observability.events import emit_event
from football.observability.pipeline import emit_pipeline_terminal, exception_diagnostic
from football.observability.reconciliation import emit_reconciliation_pending
from football.prediction.constants import ENGINE_VERSION as PREDICTION_ENGINE_VERSION
from football.prediction.evidence import sporting_evidence_basis
from football.prediction.service import latest_selected_config, predict_competition_day
from football.prediction.settlement import settle_prospective_predictions

from .contracts import PhaseResult, PhaseState, PipelineResult
from .hygiene import cleanup_cancelled_matches

PIPELINE_VERSION = "fs006-v1"
REPORT_SCHEMA = "fs006-report-v1"


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


def _experiment_report(experiment, *, created):
    produced = Counter(experiment.predictions.values_list("model_code", flat=True))
    unavailable = Counter()
    failed = Counter()
    failure_reasons = defaultdict(list)
    for key in (experiment.summary or {}).get("unavailable", {}):
        unavailable[key.split(":", 1)[0]] += 1
    for key, detail in (experiment.summary or {}).get("failed", {}).items():
        code = key.split(":", 1)[0]
        failed[code] += 1
        reason = detail.get("reason") if isinstance(detail, dict) else detail
        if reason and str(reason) not in failure_reasons[code]:
            failure_reasons[code].append(str(reason)[:200])
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
            "failed": dict(sorted(failed.items())),
            "failure_reasons": {
                code: reasons[:10] for code, reasons in sorted(failure_reasons.items())
            },
        },
        "dixon_coles": (experiment.summary or {}).get("dixon_coles", {}),
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
    capital_runtime_result,
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
            "capital_runtime": CAPITAL_RUNTIME_VERSION,
            "capital_execution": CAPITAL_EXECUTION_VERSION,
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
            "runtime": capital_runtime_result,
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

    candidates = (
        _prediction_candidates(capture_result, at, dry_run=dry_run)
        if capture_result
        else []
    )
    candidates.extend(_dixon_coles_candidates(at))
    for model_code in ("INDEPENDENT_POISSON", "ELO_MULTINOMIAL_LOGIT"):
        candidates.extend(_sporting_candidates(at, model_code=model_code))
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
                        "target_at": (
                            candidate["target_at"].isoformat()
                            if candidate["target_at"]
                            else None
                        ),
                        "cutoff": candidate["cutoff"].isoformat(),
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
                    candidate["cutoff"],
                    logical_identity=candidate["logical_identity"],
                    intended_window=candidate["intended_window"],
                    target_at=candidate["target_at"],
                    match_ids=candidate["match_ids"],
                    model_codes=candidate["model_codes"],
                    evidence_identity=candidate["evidence_identity"],
                    market_evidence_identity=candidate.get(
                        "market_evidence_identity", ""
                    ),
                    market_evidence_not_before_by_match=candidate.get(
                        "market_evidence_not_before_by_match", {}
                    ),
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
                operational_causes.append(
                    {
                        **exception_diagnostic(error),
                        "component": "prediction",
                        "operation": "predict_competition_day",
                    }
                )
                message = f"{type(error).__name__}:{error}"[:500]
                prediction_errors.append(
                    {
                        "competition_id": candidate["competition_id"],
                        "logical_identity": candidate["logical_identity"],
                        "error": message,
                    }
                )
        created_count = sum(row["created"] for row in experiment_rows)
        created_rows = [row for row in experiment_rows if row["created"]]
        classified_failed = [
            row
            for row in created_rows
            if row.get("dixon_coles", {}).get("status") == "FAILED"
        ]
        classified_unavailable = [
            row
            for row in created_rows
            if row.get("dixon_coles", {}).get("status") == "UNAVAILABLE"
        ]
        produced_count = sum(
            sum(row["models"]["produced"].values()) for row in created_rows
        )
        if prediction_errors:
            state = PhaseState.DEGRADED if experiment_rows else PhaseState.FAILED
        elif classified_failed:
            state = PhaseState.DEGRADED if produced_count else PhaseState.FAILED
        elif classified_unavailable and not produced_count:
            state = PhaseState.UNAVAILABLE
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
                "classified_failed": len(classified_failed),
                "classified_unavailable": len(classified_unavailable),
            },
        )
        errors.extend({"phase": "PREDICTION", **item} for item in prediction_errors)

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
                "automatic_configs": len(AUTOMATIC_CONFIGS),
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
            details={
                "runtime": capital_runtime_result,
                "errors": capital_errors,
            },
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
        f"CAPITAL_DEGRADED:{item}" for item in capital_runtime_result.get("errors", [])
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
        capital_runtime_result=capital_runtime_result,
        capture_data=capture_data,
        cancellation_data=cancellation_data,
        warnings=warnings,
    )
    status = _phase_status(phases)
    if run:
        capture_run_ids = [capture_data["run_id"]] if capture_data.get("run_id") else []
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
