from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.utils import timezone

from football.models import Competition, Decision, PredictionExperiment

from .constants import (
    CONFIDENCE_GRID,
    ENGINE_VERSION,
    LEGACY_R45_VERSION,
    LOGISTIC_C_GRID,
    MINIMUM_EV_GRID,
    PRIOR_STRENGTH_GRID,
    R45_VARIANTS,
)
from .contracts import UnavailablePrediction
from .datasets import eligible_finished_matches, local_day, upcoming_matches_for_day
from .elo import EloMultinomialAdapter
from .evaluation import (
    _persist_prediction,
    dependency_versions,
    persist_standard_policies,
)
from .goal_models import DixonColesAdapter, IndependentPoissonAdapter
from .market import MarketConsensusAdapter
from .r45 import LEGACY_REPLAY_REASONS

DEFAULT_CONFIG = {
    "dixon_coles": {"xi": 0.001},
    "independent_poisson": {"xi": 0.001},
    "elo_multinomial_logit": {"k": 20, "C": 1.0},
}


def persist_prospective_r45_accounting(experiment, targets, history, cutoff):
    """Make both R45 arms auditable without inventing unavailable inputs.

    The canonical store currently has no persisted, selected Modernized R45
    configuration.  It is therefore unavailable unless historical temporal
    market evidence exists; the legacy arm is always a nullable-Prediction
    NO_BET because its historical mutable league context cannot be recovered.
    """
    market = MarketConsensusAdapter()
    historical_market_count = sum(
        not isinstance(market.predict(match, match.kickoff), UnavailablePrediction)
        for match in history
    )
    if historical_market_count:
        modernized_reason = "NO_LEAK_SAFE_PROSPECTIVE_MODERNIZED_R45_CONFIGURATION"
    else:
        modernized_reason = "INSUFFICIENT_HISTORICAL_MARKET_OBSERVATIONS"
    for match in targets:
        decision = Decision(
            experiment=experiment,
            match=match,
            prediction=None,
            policy_code="LEGACY_R45",
            policy_variant="",
            policy_version=LEGACY_R45_VERSION,
            policy_config={"unavailable_reasons": list(LEGACY_REPLAY_REASONS)},
            decision_time=cutoff,
            action=Decision.ACTION_NO_BET,
            reason="EXACT_LEGACY_CONTEXT_UNAVAILABLE",
        )
        decision.full_clean()
        decision.save()
    return {
        "MODERNIZED_R45": {
            "status": "UNAVAILABLE",
            "reason": modernized_reason,
            "historical_temporal_market_matches": historical_market_count,
        },
        "LEGACY_R45": {
            "status": "UNAVAILABLE",
            "reason": "EXACT_LEGACY_CONTEXT_UNAVAILABLE",
            "decision_count": len(targets),
            "prediction_count": 0,
        },
    }


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
            return selected, f"experiment:{experiment.id}"
    return DEFAULT_CONFIG, "fs003-default-no-completed-backtest"


@dataclass(frozen=True)
class ProspectivePredictionResult:
    experiment: PredictionExperiment | None
    created: bool
    reason: str = ""


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
    selected, config_source = latest_selected_config(competition)
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
            "temporal_batch_policy": "FS-005 logical intended_window/target_at; historical-results-strict-prior-local-day",
            "confidence_grid": list(CONFIDENCE_GRID),
            "minimum_ev_grid": list(MINIMUM_EV_GRID),
            "modernized_r45_grid": {
                "variants": list(R45_VARIANTS),
                "C": list(LOGISTIC_C_GRID),
                "prior_strength": list(PRIOR_STRENGTH_GRID),
            },
        },
    )
    history = list(eligible_finished_matches(competition, before=cutoff))
    history = [match for match in history if local_day(match.kickoff) < day]
    adapters = (
        DixonColesAdapter(xi=selected["dixon_coles"]["xi"]),
        IndependentPoissonAdapter(xi=selected["independent_poisson"]["xi"]),
        EloMultinomialAdapter(
            k=selected["elo_multinomial_logit"]["k"],
            c=selected["elo_multinomial_logit"]["C"],
        ),
    )
    fitted = []
    unavailable = {}
    for adapter in adapters:
        outcome = adapter.fit(history, cutoff)
        if isinstance(outcome, UnavailablePrediction):
            unavailable[adapter.model_code] = outcome.reason
        else:
            fitted.append(adapter)
    market = MarketConsensusAdapter()
    for match in targets:
        for adapter in fitted:
            result = adapter.predict(match, cutoff)
            if isinstance(result, UnavailablePrediction):
                unavailable[f"{adapter.model_code}:{match.id}"] = result.reason
                continue
            prediction = _persist_prediction(experiment, match, adapter, result, cutoff)
            persist_standard_policies(experiment, match, prediction, result, cutoff)
        result = market.predict(match, cutoff)
        if isinstance(result, UnavailablePrediction):
            unavailable[f"MARKET_CONSENSUS:{match.id}"] = result.reason
        else:
            prediction = _persist_prediction(experiment, match, market, result, cutoff)
            persist_standard_policies(experiment, match, prediction, result, cutoff)
    r45_arms = persist_prospective_r45_accounting(experiment, targets, history, cutoff)
    experiment.summary = {
        "target_count": len(targets),
        "prediction_count": experiment.predictions.count(),
        "decision_count": experiment.decisions.count(),
        "unavailable": unavailable,
        "r45_arms": r45_arms,
    }
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
