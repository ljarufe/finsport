from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.utils import timezone

from football.models import Competition, Prediction, PredictionExperiment

from .constants import (
    CONFIDENCE_GRID,
    ENGINE_VERSION,
    MINIMUM_EV_GRID,
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
from .r45 import (
    fit_modernized,
    modernized_config_grid,
    predict_modernized,
    select_modernized_config,
)

DEFAULT_CONFIG = {
    "dixon_coles": {"xi": 0.001},
    "independent_poisson": {"xi": 0.001},
    "elo_multinomial_logit": {"k": 20, "C": 1.0},
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
    history = list(eligible_finished_matches(competition, before=cutoff))
    history = [match for match in history if local_day(match.kickoff) < day]
    if "modernized_r45" not in selected:
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
            "temporal_batch_policy": "FS-005 logical intended_window/target_at; historical-results-strict-prior-local-day",
            "confidence_grid": list(CONFIDENCE_GRID),
            "minimum_ev_grid": list(MINIMUM_EV_GRID),
        },
    )
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
    modernized = None
    modernized_fit_unavailable = {}
    if "modernized_r45" in selected:
        modernized, modernized_fit_unavailable = fit_modernized(
            history,
            cutoff,
            selected["modernized_r45"],
        )
        if isinstance(modernized, UnavailablePrediction):
            unavailable[Prediction.MODERNIZED_R45] = modernized.reason
            modernized = None
    else:
        unavailable[Prediction.MODERNIZED_R45] = (
            "INSUFFICIENT_LEAK_SAFE_SELECTION_EVIDENCE"
        )
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
