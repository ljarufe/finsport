from dataclasses import dataclass
from datetime import date, datetime

from django.db import transaction
from django.utils import timezone

from football.models import Competition, Prediction, PredictionExperiment
from football.observability.events import emit_event

from .constants import (
    CONFIDENCE_GRID,
    ENGINE_VERSION,
    MINIMUM_EV_GRID,
)
from .contracts import FailedPrediction, UnavailablePrediction
from .datasets import eligible_finished_matches, local_day, upcoming_matches_for_day
from .elo import EloMultinomialAdapter
from .evaluation import (
    _persist_prediction,
    dependency_versions,
    persist_standard_policies,
)
from .evidence import dixon_coles_evidence_basis, sporting_evidence_basis
from .goal_models import DixonColesAdapter, IndependentPoissonAdapter
from .market import MarketConsensusAdapter
from .r45 import (
    fit_modernized,
    modernized_config_grid,
    predict_modernized,
    select_modernized_config,
)
from .readiness import active_profile, assess_bet_eligibility
from .readiness_lifecycle import currentness_context

DEFAULT_CONFIG = {
    "dixon_coles": {"xi": 0.001},
    "independent_poisson": {"xi": 0.001},
    "elo_multinomial_logit": {"k": 20, "C": 1.0},
}


def _model_call(adapter, operation, competition, *args):
    try:
        return getattr(adapter, operation)(*args)
    except Exception as error:
        emit_event(
            event_code="SPORTING_MODEL_FAILED",
            severity="ERROR",
            component="prediction",
            operation=operation,
            outcome="FAILED",
            competition_id=competition.pk,
            human_summary="Sporting model execution failed unexpectedly.",
            exception=error,
            context={"model": adapter.model_code},
        )
        return FailedPrediction(
            "SPORTING_MODEL_RUNTIME_FAILED",
            {"error_class": type(error).__name__, "error": str(error)[:500]},
        )


def latest_selected_config(competition):
    experiment = (
        competition.prediction_experiments.filter(
            mode=PredictionExperiment.MODE_BACKTEST, completed_at__isnull=False
        )
        .order_by("-completed_at")
        .first()
    )
    if experiment:
        selected = experiment.config.get("selected_hyperparameters")
        if selected:
            return (
                _profile_configs(competition, selected),
                f"experiment:{experiment.id}",
            )
    return (
        _profile_configs(competition, DEFAULT_CONFIG),
        "fs003-default-no-completed-backtest",
    )


def _profile_configs(competition, selected):
    selected = {**selected}
    for code in (Prediction.INDEPENDENT_POISSON, Prediction.ELO_MULTINOMIAL_LOGIT):
        profile = active_profile(competition, model_code=code)
        if profile and profile.approved:
            selected[code.lower()] = profile.model_config
        elif (
            profile
            and profile.evidence.get("reason") == "NO_FINITE_HYPERPARAMETER_WINNER"
        ):
            selected[code.lower()] = {
                "status": "UNAVAILABLE",
                "reason": f"NO_FINITE_{'ELO' if code == Prediction.ELO_MULTINOMIAL_LOGIT else 'POISSON'}_HYPERPARAMETER_CANDIDATE",
            }
    return selected


def _select_prospective_modernized(history):
    years = sorted({match.season.year for match in history})
    if len(years) < 2:
        return None
    validation_year = years[-1]
    training = [match for match in history if match.season.year < validation_year]
    validation = [match for match in history if match.season.year == validation_year]
    selected = select_modernized_config(
        training,
        validation,
        modernized_config_grid(),
    )
    if selected is None:
        return None
    validation_loss, config = selected
    return {
        **config,
        "validation_log_loss": validation_loss,
        "selection": "strict_prior_history_walk_forward",
        "validation_season": validation_year,
    }


@dataclass(frozen=True)
class ProspectivePredictionResult:
    experiment: PredictionExperiment | None
    created: bool
    reason: str = ""


def _classified_reason(value):
    if isinstance(value, dict):
        return value.get("reason", "")
    return str(value or "")


def _dixon_coles_targets(experiment, targets, unavailable, failed):
    produced_ids = set(
        experiment.predictions.filter(model_code=Prediction.DIXON_COLES).values_list(
            "match_id", flat=True
        )
    )
    rows = {}
    for match in targets:
        key = f"{Prediction.DIXON_COLES}:{match.pk}"
        if key in failed:
            status, reason = "FAILED", _classified_reason(failed[key])
        elif key in unavailable:
            status, reason = "UNAVAILABLE", _classified_reason(unavailable[key])
        elif match.pk in produced_ids:
            status, reason = "PRODUCED", ""
        elif Prediction.DIXON_COLES in failed:
            status, reason = "FAILED", _classified_reason(
                failed[Prediction.DIXON_COLES]
            )
        else:
            status, reason = "UNAVAILABLE", _classified_reason(
                unavailable.get(Prediction.DIXON_COLES, "DIXON_COLES_NOT_PRODUCED")
            )
        rows[str(match.pk)] = {
            "status": status,
            "reasons": [reason] if reason else [],
        }
    return rows


@transaction.atomic
def predict_competition_day(
    competition,
    day,
    cutoff=None,
    *,
    logical_identity="",
    intended_window="",
    target_at=None,
    match_ids=None,
    model_codes=None,
    evidence_identity="",
    market_evidence_identity="",
    market_evidence_not_before_by_match=None,
):
    if isinstance(day, str):
        day = date.fromisoformat(day)
    cutoff = cutoff or timezone.now()
    if timezone.is_naive(cutoff):
        raise ValueError("Prospective cutoff must include a timezone offset.")
    if target_at is not None and timezone.is_naive(target_at):
        raise ValueError("Prospective target_at must include a timezone offset.")
    if not isinstance(competition, Competition):
        competition = Competition.objects.get(pk=competition)
    if logical_identity:
        existing = PredictionExperiment.objects.filter(
            competition=competition,
            mode=PredictionExperiment.MODE_PROSPECTIVE,
            logical_identity=logical_identity,
        ).first()
        if existing:
            return ProspectivePredictionResult(existing, False, "ALREADY_EXISTS")

    target_queryset = upcoming_matches_for_day(competition, day, cutoff)
    if match_ids is not None:
        raw_match_ids = tuple(match_ids)
        if any(isinstance(match_id, bool) for match_id in raw_match_ids):
            raise ValueError("Explicit prospective Match IDs must be integers.")
        try:
            normalized_match_ids = sorted({int(match_id) for match_id in raw_match_ids})
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Explicit prospective Match IDs must be integers."
            ) from error
        target_queryset = target_queryset.filter(pk__in=normalized_match_ids)
    targets = list(target_queryset)
    if not targets:
        return ProspectivePredictionResult(None, False, "NO_ELIGIBLE_TARGETS")
    market_evidence_not_before_by_match = market_evidence_not_before_by_match or {}
    normalized_market_not_before = {}
    for match_id, value in market_evidence_not_before_by_match.items():
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
        if timezone.is_naive(parsed):
            raise ValueError(
                "Market evidence not-before must include a timezone offset."
            )
        normalized_market_not_before[int(match_id)] = parsed
    selected, config_source = latest_selected_config(competition)
    requested_models = set(
        model_codes
        or (
            Prediction.DIXON_COLES,
            Prediction.INDEPENDENT_POISSON,
            Prediction.ELO_MULTINOMIAL_LOGIT,
            Prediction.MARKET_CONSENSUS,
            Prediction.MODERNIZED_R45,
        )
    )
    if model_codes is None and not market_evidence_identity:
        requested_models.discard(Prediction.MARKET_CONSENSUS)
    if Prediction.MARKET_CONSENSUS in requested_models:
        if not market_evidence_identity:
            raise ValueError(
                "MARKET_CONSENSUS v2 requires a capture evidence identity."
            )
        target_ids = {match.pk for match in targets}
        if set(normalized_market_not_before) != target_ids:
            raise ValueError(
                "MARKET_CONSENSUS v2 requires one capture lower bound "
                "per target Match."
            )
    history = list(eligible_finished_matches(competition, before=cutoff))
    history = [match for match in history if local_day(match.kickoff) < day]
    readiness_models = tuple(
        code
        for code in (Prediction.INDEPENDENT_POISSON, Prediction.ELO_MULTINOMIAL_LOGIT)
        if code in requested_models
    )
    readiness_currentness = (
        currentness_context(competition, readiness_models) if readiness_models else {}
    )
    sporting_identities = {}
    for code in readiness_models:
        identity, _, _ = sporting_evidence_basis(
            competition,
            targets,
            cutoff=cutoff,
            config=selected[code.lower()],
            model_code=code,
            history=history,
        )
        if (
            len(requested_models) == 1
            and evidence_identity
            and evidence_identity != identity
        ):
            raise ValueError("Sporting evidence identity does not match its basis.")
        sporting_identities[code] = identity
    dc_basis = None
    if Prediction.DIXON_COLES in requested_models:
        calculated_identity, dc_basis, history = dixon_coles_evidence_basis(
            competition,
            targets,
            cutoff=cutoff,
            config=selected["dixon_coles"],
            history=history,
        )
        if evidence_identity and evidence_identity != calculated_identity:
            raise ValueError("Dixon-Coles evidence identity does not match its basis.")
        evidence_identity = calculated_identity
    if (
        Prediction.MODERNIZED_R45 in requested_models
        and "modernized_r45" not in selected
    ):
        modernized_config = _select_prospective_modernized(history)
        if modernized_config is not None:
            selected = {**selected, "modernized_r45": modernized_config}
            config_source = f"{config_source}+prospective-strict-prior-r45-selection"
    experiment = PredictionExperiment.objects.create(
        competition=competition,
        mode=PredictionExperiment.MODE_PROSPECTIVE,
        period_start=day,
        period_end=day,
        engine_version=ENGINE_VERSION,
        logical_identity=logical_identity,
        intended_window=intended_window,
        target_at=target_at,
        config={
            "dependencies": dependency_versions(),
            "selected_hyperparameters": selected,
            "config_source": config_source,
            "cutoff": cutoff.isoformat(),
            "logical_identity": logical_identity,
            "intended_window": intended_window,
            "target_at": target_at.isoformat() if target_at else None,
            "target_match_ids": sorted(match.pk for match in targets),
            "model_codes": sorted(requested_models),
            "dixon_coles_evidence_identity": evidence_identity if dc_basis else "",
            "dixon_coles_evidence_basis": dc_basis,
            "sporting_evidence_identities": sporting_identities,
            "market_consensus_evidence_identity": market_evidence_identity,
            "market_evidence_not_before_by_match": {
                str(match_id): value.isoformat()
                for match_id, value in sorted(normalized_market_not_before.items())
            },
            "temporal_batch_policy": "FS-005 logical intended_window/target_at; historical-results-strict-prior-local-day",
            "confidence_grid": list(CONFIDENCE_GRID),
            "minimum_ev_grid": list(MINIMUM_EV_GRID),
        },
    )
    adapters = []
    unavailable = {}
    failed = {}
    for code in (Prediction.INDEPENDENT_POISSON, Prediction.ELO_MULTINOMIAL_LOGIT):
        if (
            code in requested_models
            and selected[code.lower()].get("status") == "UNAVAILABLE"
        ):
            unavailable[code] = selected[code.lower()]["reason"]
    if Prediction.DIXON_COLES in requested_models:
        adapters.append(DixonColesAdapter(xi=selected["dixon_coles"]["xi"]))
    if (
        Prediction.INDEPENDENT_POISSON in requested_models
        and Prediction.INDEPENDENT_POISSON not in unavailable
    ):
        adapters.append(
            IndependentPoissonAdapter(xi=selected["independent_poisson"]["xi"])
        )
    if (
        Prediction.ELO_MULTINOMIAL_LOGIT in requested_models
        and Prediction.ELO_MULTINOMIAL_LOGIT not in unavailable
    ):
        adapters.append(
            EloMultinomialAdapter(
                k=selected["elo_multinomial_logit"]["k"],
                c=selected["elo_multinomial_logit"]["C"],
            )
        )
    fitted = []
    for adapter in adapters:
        if adapter.model_code == Prediction.DIXON_COLES and hasattr(
            adapter, "fit_for_targets"
        ):
            outcome = adapter.fit_for_targets(
                history,
                cutoff,
                targets,
                readiness_assessor=lambda diagnostics: assess_bet_eligibility(
                    competition,
                    diagnostics,
                    model_version=adapter.model_version,
                    model_config=adapter.config,
                ),
            )
        else:
            outcome = _model_call(adapter, "fit", competition, history, cutoff)
        if isinstance(outcome, UnavailablePrediction):
            unavailable[adapter.model_code] = outcome.reason
        elif isinstance(outcome, FailedPrediction):
            failed[adapter.model_code] = {
                "reason": outcome.reason,
                "diagnostics": outcome.diagnostics,
            }
        else:
            fitted.append(adapter)
    modernized = None
    modernized_fit_unavailable = {}
    if Prediction.MODERNIZED_R45 in requested_models and "modernized_r45" in selected:
        modernized, modernized_fit_unavailable = fit_modernized(
            history,
            cutoff,
            selected["modernized_r45"],
        )
        if isinstance(modernized, UnavailablePrediction):
            unavailable[Prediction.MODERNIZED_R45] = modernized.reason
            modernized = None
    elif Prediction.MODERNIZED_R45 in requested_models:
        unavailable[Prediction.MODERNIZED_R45] = (
            "INSUFFICIENT_LEAK_SAFE_SELECTION_EVIDENCE"
        )
    market = MarketConsensusAdapter()
    for match in targets:
        for adapter in fitted:
            result = _model_call(adapter, "predict", competition, match, cutoff)
            if isinstance(result, UnavailablePrediction):
                unavailable[f"{adapter.model_code}:{match.id}"] = result.reason
                continue
            if isinstance(result, FailedPrediction):
                failed[f"{adapter.model_code}:{match.id}"] = {
                    "reason": result.reason,
                    "diagnostics": result.diagnostics,
                }
                continue
            prediction = _persist_prediction(
                experiment,
                match,
                adapter,
                result,
                cutoff,
                evidence_identity=(
                    evidence_identity
                    if adapter.model_code == Prediction.DIXON_COLES
                    else sporting_identities.get(adapter.model_code, "")
                ),
                readiness_currentness=readiness_currentness.get(adapter.model_code),
            )
            persist_standard_policies(experiment, match, prediction, result, cutoff)
        if Prediction.MARKET_CONSENSUS in requested_models:
            result = market.predict(
                match,
                cutoff,
                not_before=normalized_market_not_before.get(match.pk),
            )
            if isinstance(result, UnavailablePrediction):
                unavailable[f"MARKET_CONSENSUS:{match.id}"] = {
                    "reason": result.reason,
                    "diagnostics": result.diagnostics,
                }
            else:
                prediction = _persist_prediction(
                    experiment,
                    match,
                    market,
                    result,
                    cutoff,
                    evidence_identity=market_evidence_identity,
                )
                persist_standard_policies(
                    experiment,
                    match,
                    prediction,
                    result,
                    cutoff,
                    price_not_before=normalized_market_not_before[match.pk],
                )
        if modernized is not None:
            result = predict_modernized(modernized, history, match, cutoff)
            if isinstance(result, UnavailablePrediction):
                unavailable[f"MODERNIZED_R45:{match.id}"] = result.reason
            else:
                prediction = _persist_prediction(
                    experiment,
                    match,
                    modernized,
                    result,
                    cutoff,
                    variant=modernized.variant,
                )
                persist_standard_policies(experiment, match, prediction, result, cutoff)
    experiment.summary = {
        "target_count": len(targets),
        "prediction_count": experiment.predictions.count(),
        "decision_count": experiment.decisions.count(),
        "unavailable": unavailable,
        "failed": failed,
        "r45_arms": {
            "MODERNIZED_R45": {
                "status": (
                    "PRODUCED"
                    if experiment.predictions.filter(
                        model_code=Prediction.MODERNIZED_R45
                    ).exists()
                    else "UNAVAILABLE"
                ),
                "unavailable_reasons": {
                    key: reason
                    for key, reason in unavailable.items()
                    if key == Prediction.MODERNIZED_R45
                    or key.startswith("MODERNIZED_R45:")
                },
                "config": selected.get("modernized_r45"),
                "fit_unavailable": modernized_fit_unavailable,
                "classification": "ACTIVE",
            }
        },
    }
    if Prediction.DIXON_COLES in requested_models:
        dc_targets = _dixon_coles_targets(experiment, targets, unavailable, failed)
        dc_statuses = {row["status"] for row in dc_targets.values()}
        experiment.summary["dixon_coles"] = {
            "status": (
                "FAILED"
                if "FAILED" in dc_statuses
                else ("PRODUCED" if "PRODUCED" in dc_statuses else "UNAVAILABLE")
            ),
            "evidence_identity": evidence_identity,
            "reasons": sorted(
                {reason for row in dc_targets.values() for reason in row["reasons"]}
            ),
            "targets": dc_targets,
        }
        dc_summary = experiment.summary["dixon_coles"]
        emit_event(
            event_code=f"DIXON_COLES_{dc_summary['status']}",
            severity="ERROR" if dc_summary["status"] == "FAILED" else "INFO",
            component="prediction",
            operation="dixon_coles",
            outcome=dc_summary["status"],
            failure_kind=(
                "dixon_coles_runtime" if dc_summary["status"] == "FAILED" else ""
            ),
            human_summary="Pure Dixon-Coles prediction reached a classified terminal state.",
            competition_id=competition.pk,
            prediction_experiment_id=experiment.pk,
            context={
                "evidence_identity": evidence_identity,
                "status": dc_summary["status"],
                "reason": "; ".join(
                    str(value)
                    for key, value in {**unavailable, **failed}.items()
                    if key.startswith(Prediction.DIXON_COLES)
                )[:500],
            },
        )
    experiment.completed_at = timezone.now()
    experiment.save(update_fields=["summary", "completed_at", "modified"])
    return ProspectivePredictionResult(experiment, True)


def predict_day(day, cutoff=None):
    if isinstance(day, str):
        day = date.fromisoformat(day)
    cutoff = cutoff or timezone.now()
    experiments = []
    for competition in Competition.objects.filter(
        enabled=True, competition_type="League", country__gt=""
    ):
        result = predict_competition_day(competition, day, cutoff)
        if result.experiment is None:
            continue
        experiments.append(result.experiment)
    return experiments
