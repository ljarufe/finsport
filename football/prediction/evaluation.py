from collections import defaultdict
from importlib.metadata import version

from django.db import transaction
from django.utils import timezone
from sklearn.metrics import log_loss

from football.models import Decision, Match, Prediction, PredictionExperiment

from .constants import (
    CONFIDENCE_GRID,
    ELO_K_GRID,
    ENGINE_VERSION,
    LEGACY_R45_VERSION,
    LOGISTIC_C_GRID,
    MINIMUM_EV_GRID,
    OUTCOMES,
    PRIOR_STRENGTH_GRID,
    R45_VARIANTS,
    XI_GRID,
)
from .contracts import UnavailablePrediction
from .datasets import daily_batches, eligible_finished_matches, local_day
from .elo import EloMultinomialAdapter
from .goal_models import DixonColesAdapter, IndependentPoissonAdapter
from .market import MarketConsensusAdapter, best_prices_as_of
from .metrics import policy_metrics, prediction_metrics
from .policies import (
    POLICY_VERSIONS,
    modal_all,
    selective_confidence,
    value_policy,
)
from .r45 import LEGACY_REPLAY_REASONS


def dependency_versions():
    return {
        "penaltyblog": version("penaltyblog"),
        "scikit-learn": version("scikit-learn"),
    }


def _outcome(match):
    if match.home_score > match.away_score:
        return Match.OUTCOME_HOME
    if match.home_score < match.away_score:
        return Match.OUTCOME_AWAY
    return Match.OUTCOME_DRAW


def _validation_loss(adapter_factory, config, training, validation):
    actual = []
    probabilities = []
    growing_history = list(training)
    for _, batch in daily_batches(validation):
        cutoff = min(match.kickoff for match in batch)
        adapter = adapter_factory(**config)
        fitted = adapter.fit(growing_history, cutoff)
        if not isinstance(fitted, UnavailablePrediction):
            for match in batch:
                result = adapter.predict(match, match.kickoff)
                if isinstance(result, UnavailablePrediction):
                    continue
                actual.append(_outcome(match))
                probabilities.append(list(result.as_tuple()))
        growing_history.extend(batch)
    if not actual:
        return float("inf")
    return log_loss(
        [OUTCOMES.index(label) for label in actual],
        probabilities,
        labels=[0, 1, 2],
    )


def select_hyperparameters(inner_training, inner_validation):
    dc_candidates = []
    for xi in XI_GRID:
        loss = _validation_loss(
            DixonColesAdapter,
            {"xi": xi},
            inner_training,
            inner_validation,
        )
        dc_candidates.append((loss, xi))
    dc_loss, selected_xi = min(dc_candidates, key=lambda item: (item[0], item[1]))

    elo_candidates = []
    for k in ELO_K_GRID:
        for c in LOGISTIC_C_GRID:
            loss = _validation_loss(
                EloMultinomialAdapter,
                {"k": k, "c": c},
                inner_training,
                inner_validation,
            )
            elo_candidates.append((loss, k, c))
    elo_loss, selected_k, selected_c = min(
        elo_candidates, key=lambda item: (item[0], item[1], item[2])
    )
    return {
        "dixon_coles": {
            "xi": selected_xi,
            "validation_log_loss": dc_loss,
            "grid": list(XI_GRID),
        },
        "independent_poisson": {"xi": selected_xi, "selected_by": "dixon_coles"},
        "elo_multinomial_logit": {
            "k": selected_k,
            "C": selected_c,
            "validation_log_loss": elo_loss,
            "k_grid": list(ELO_K_GRID),
            "C_grid": list(LOGISTIC_C_GRID),
        },
    }


def _persist_prediction(experiment, match, adapter, result, cutoff, *, variant=""):
    prediction = Prediction(
        experiment=experiment,
        match=match,
        model_code=adapter.model_code,
        variant=variant,
        model_version=adapter.model_version,
        model_config={**adapter.config, **dependency_versions()},
        cutoff=cutoff,
        p_home=result.p_home,
        p_draw=result.p_draw,
        p_away=result.p_away,
        predicted_outcome=result.predicted_outcome,
        diagnostics=result.diagnostics,
        evaluated_at=timezone.now() if match.status_short == "FT" else None,
        actual_outcome=_outcome(match) if match.status_short == "FT" else None,
    )
    prediction.full_clean()
    prediction.save()
    return prediction


def _persist_policy_decision(
    experiment, match, prediction, policy_code, policy_variant, result, decision_time
):
    decision = Decision(
        experiment=experiment,
        match=match,
        prediction=prediction,
        policy_code=policy_code,
        policy_variant=policy_variant,
        policy_version=POLICY_VERSIONS[policy_code],
        policy_config=result.config,
        decision_time=decision_time,
        action=result.action,
        reason=result.reason,
        model_probability=result.model_probability,
        selected_odds_observation=result.selected_observation,
        selected_price=result.selected_price,
        expected_value=result.expected_value,
    )
    decision.full_clean()
    decision.save()
    return decision


def persist_standard_policies(experiment, match, prediction, result, cutoff):
    prices = best_prices_as_of(match, cutoff)
    _persist_policy_decision(
        experiment,
        match,
        prediction,
        "MODAL_ALL",
        "",
        modal_all(result, prices),
        cutoff,
    )
    for threshold in CONFIDENCE_GRID:
        _persist_policy_decision(
            experiment,
            match,
            prediction,
            "SELECTIVE_CONFIDENCE",
            f"{threshold:.2f}",
            selective_confidence(result, threshold, prices),
            cutoff,
        )
    if prediction.model_code != Prediction.MARKET_CONSENSUS:
        for minimum_ev in MINIMUM_EV_GRID:
            _persist_policy_decision(
                experiment,
                match,
                prediction,
                "VALUE",
                f"{minimum_ev:.2f}",
                value_policy(result, prices, minimum_ev),
                cutoff,
            )


def _unavailable_summary(*, market_available):
    unavailable = {
        "MODERNIZED_R45": "INSUFFICIENT_HISTORICAL_MARKET_OBSERVATIONS",
        "LEGACY_R45": list(LEGACY_REPLAY_REASONS),
    }
    if not market_available:
        unavailable["MARKET_CONSENSUS"] = "INSUFFICIENT_HISTORICAL_MARKET_OBSERVATIONS"
    return unavailable


def summarize_experiment(experiment):
    prediction_summary = {}
    predictions = experiment.predictions.order_by(
        "model_code", "variant", "match__kickoff", "match_id"
    )
    groups = defaultdict(list)
    for prediction in predictions:
        groups[(prediction.model_code, prediction.variant)].append(prediction)
    for (model_code, variant), rows in groups.items():
        evaluated = [row for row in rows if row.actual_outcome]
        summary = prediction_metrics(
            [row.actual_outcome for row in evaluated],
            [[row.p_home, row.p_draw, row.p_away] for row in evaluated],
        )
        if model_code == Prediction.MARKET_CONSENSUS:
            book_counts = defaultdict(int)
            for row in rows:
                book_count = row.diagnostics.get("book_count")
                if (
                    isinstance(book_count, int)
                    and not isinstance(book_count, bool)
                    and book_count > 0
                ):
                    book_counts[str(book_count)] += 1
            summary["book_count_distribution"] = {
                key: book_counts[key] for key in sorted(book_counts, key=int)
            }
        prediction_summary[f"{model_code}:{variant}"] = summary

    policy_summary = {}
    decisions = experiment.decisions.select_related("match").order_by(
        "policy_code",
        "policy_variant",
        "prediction__model_code",
        "match__kickoff",
        "match_id",
    )
    decision_groups = defaultdict(list)
    for decision in decisions:
        model_code = (
            decision.prediction.model_code if decision.prediction_id else "NONE"
        )
        key = (model_code, decision.policy_code, decision.policy_variant)
        decision_groups[key].append(
            {
                "action": decision.action,
                "reason": decision.reason,
                "actual_outcome": (
                    _outcome(decision.match)
                    if decision.match.status_short == "FT"
                    else None
                ),
                "selected_price": decision.selected_price,
                "expected_value": decision.expected_value,
            }
        )
    for key, rows in decision_groups.items():
        policy_summary[":".join(key)] = policy_metrics(rows)
    return {"predictions": prediction_summary, "policies": policy_summary}


@transaction.atomic
def run_backtest(competition, season):
    season_year = season.year
    inner_training = list(
        eligible_finished_matches(competition, season_year=season_year - 2)
    )
    inner_validation = list(
        eligible_finished_matches(competition, season_year=season_year - 1)
    )
    outer = list(eligible_finished_matches(competition, season_year=season_year))
    if not inner_training or not inner_validation or not outer:
        raise ValueError(
            "Backtest requires non-empty train, validation, and outer seasons."
        )
    selected = select_hyperparameters(inner_training, inner_validation)
    experiment = PredictionExperiment.objects.create(
        competition=competition,
        mode=PredictionExperiment.MODE_BACKTEST,
        period_start=local_day(outer[0].kickoff),
        period_end=local_day(outer[-1].kickoff),
        engine_version=ENGINE_VERSION,
        config={
            "dependencies": dependency_versions(),
            "selected_hyperparameters": selected,
            "evaluation_season": season_year,
            "inner_train_season": season_year - 2,
            "inner_validation_season": season_year - 1,
            "temporal_batch_policy": "America/Lima strict-prior-local-day",
            "de_vig_method": "multiplicative",
            "consensus_method": "mean",
            "confidence_grid": list(CONFIDENCE_GRID),
            "minimum_ev_grid": list(MINIMUM_EV_GRID),
            "modernized_r45_grid": {
                "variants": list(R45_VARIANTS),
                "C": list(LOGISTIC_C_GRID),
                "prior_strength": list(PRIOR_STRENGTH_GRID),
            },
        },
    )
    history = [*inner_training, *inner_validation]
    unavailable_counts = defaultdict(int)
    for _, batch in daily_batches(outer):
        batch_cutoff = min(match.kickoff for match in batch)
        adapters = (
            DixonColesAdapter(xi=selected["dixon_coles"]["xi"]),
            IndependentPoissonAdapter(xi=selected["independent_poisson"]["xi"]),
            EloMultinomialAdapter(
                k=selected["elo_multinomial_logit"]["k"],
                c=selected["elo_multinomial_logit"]["C"],
            ),
        )
        fitted_adapters = []
        for adapter in adapters:
            fitted = adapter.fit(history, batch_cutoff)
            if isinstance(fitted, UnavailablePrediction):
                unavailable_counts[f"{adapter.model_code}:{fitted.reason}"] += len(
                    batch
                )
            else:
                fitted_adapters.append(adapter)
        market = MarketConsensusAdapter()
        for match in batch:
            cutoff = match.kickoff
            for adapter in fitted_adapters:
                result = adapter.predict(match, cutoff)
                if isinstance(result, UnavailablePrediction):
                    unavailable_counts[f"{adapter.model_code}:{result.reason}"] += 1
                    continue
                prediction = _persist_prediction(
                    experiment, match, adapter, result, cutoff
                )
                persist_standard_policies(experiment, match, prediction, result, cutoff)
            result = market.predict(match, cutoff)
            if isinstance(result, UnavailablePrediction):
                unavailable_counts[f"MARKET_CONSENSUS:{result.reason}"] += 1
            else:
                prediction = _persist_prediction(
                    experiment, match, market, result, cutoff
                )
                persist_standard_policies(experiment, match, prediction, result, cutoff)
        # Reveal every result in the batch only after every prediction is frozen.
        history.extend(batch)

    for match in outer:
        decision = Decision(
            experiment=experiment,
            match=match,
            prediction=None,
            policy_code="LEGACY_R45",
            policy_variant="",
            policy_version=LEGACY_R45_VERSION,
            policy_config={"unavailable_reasons": list(LEGACY_REPLAY_REASONS)},
            decision_time=match.kickoff,
            action=Decision.ACTION_NO_BET,
            reason="UNAVAILABLE_FOR_REPLAY",
        )
        decision.full_clean()
        decision.save()

    experiment.summary = {
        **summarize_experiment(experiment),
        "selected_hyperparameters": selected,
        "sample_counts": {
            "inner_train": len(inner_training),
            "inner_validation": len(inner_validation),
            "outer": len(outer),
        },
        "unavailable_arms": _unavailable_summary(
            market_available=experiment.predictions.filter(
                model_code=Prediction.MARKET_CONSENSUS
            ).exists()
        ),
        "unavailable_counts": dict(unavailable_counts),
    }
    experiment.completed_at = timezone.now()
    experiment.save(update_fields=["summary", "completed_at", "modified"])
    return experiment
