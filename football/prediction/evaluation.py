from collections import defaultdict
from importlib.metadata import version

from django.db import transaction
from django.utils import timezone
from sklearn.metrics import log_loss

from football.models import Decision, Match, Prediction, PredictionExperiment
from football.sync import FINISHED_STATUSES

from .constants import (
    CONFIDENCE_GRID,
    ELO_K_GRID,
    ENGINE_VERSION,
    LOGISTIC_C_GRID,
    MINIMUM_EV_GRID,
    OUTCOMES,
    PRIOR_STRENGTH_GRID,
    R45_VARIANTS,
    XI_GRID,
)
from .contracts import FailedPrediction, UnavailablePrediction
from .datasets import daily_batches, eligible_finished_matches, local_day
from .elo import EloMultinomialAdapter
from .goal_models import DixonColesAdapter, IndependentPoissonAdapter
from .market import MarketConsensusAdapter, best_prices_as_of
from .metrics import policy_metrics, prediction_metrics
from .policies import (
    POLICY_VERSIONS,
    modal_all,
    readiness_no_bet,
    selective_confidence,
    value_policy,
)
from .r45 import (
    fit_modernized,
    modernized_config_grid,
    predict_modernized,
    select_modernized_config,
)
from .readiness import assess_bet_eligibility


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


def _canonical_outcome(match):
    valid = {value for value, _ in Match.OUTCOMES}
    if match.status_short in FINISHED_STATUSES and match.outcome in valid:
        return match.outcome
    return None


def _validation_loss(adapter_factory, config, training, validation):
    actual = []
    probabilities = []
    growing_history = list(training)
    for _, batch in daily_batches(validation):
        cutoff = min(match.kickoff for match in batch)
        adapter = adapter_factory(**config)
        fitted = adapter.fit(growing_history, cutoff)
        if not isinstance(fitted, (UnavailablePrediction, FailedPrediction)):
            for match in batch:
                result = adapter.predict(match, match.kickoff)
                if isinstance(result, (UnavailablePrediction, FailedPrediction)):
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


def _persist_prediction(
    experiment, match, adapter, result, cutoff, *, variant="", evidence_identity=""
):
    assessment = None
    if adapter.model_code == Prediction.DIXON_COLES:
        assessment = assess_bet_eligibility(
            match.competition,
            result.diagnostics,
            model_version=adapter.model_version,
            model_config=adapter.config,
        )
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
        diagnostics={
            **result.diagnostics,
            **(
                {
                    "readiness_profile": (
                        assessment.profile.version if assessment.profile else None
                    ),
                    "bet_eligible": assessment.eligible,
                    "readiness_reason": assessment.reason,
                }
                if assessment
                else {}
            ),
        },
        evidence_identity=evidence_identity,
        bet_eligible=assessment.eligible if assessment else True,
        readiness_profile=assessment.profile if assessment else None,
        readiness_profile_version=(
            assessment.profile.version if assessment and assessment.profile else ""
        ),
        readiness_reason=assessment.reason if assessment else "",
        evaluated_at=timezone.now() if _canonical_outcome(match) else None,
        actual_outcome=_canonical_outcome(match),
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
    if prediction.model_code == Prediction.DIXON_COLES and not prediction.bet_eligible:
        gated = readiness_no_bet(prediction.readiness_reason, result)
        _persist_policy_decision(
            experiment, match, prediction, "MODAL_ALL", "", gated, cutoff
        )
        for threshold in CONFIDENCE_GRID:
            _persist_policy_decision(
                experiment,
                match,
                prediction,
                "SELECTIVE_CONFIDENCE",
                f"{threshold:.2f}",
                gated,
                cutoff,
            )
        for minimum_ev in MINIMUM_EV_GRID:
            _persist_policy_decision(
                experiment,
                match,
                prediction,
                "VALUE",
                f"{minimum_ev:.2f}",
                gated,
                cutoff,
            )
        return
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


def _unavailable_summary(*, market_available, modernized_available):
    unavailable = {}
    if not market_available:
        unavailable["MARKET_CONSENSUS"] = "INSUFFICIENT_HISTORICAL_MARKET_OBSERVATIONS"
    if not modernized_available:
        unavailable["MODERNIZED_R45"] = "INSUFFICIENT_LEAK_SAFE_SELECTION_EVIDENCE"
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
    decisions = experiment.decisions.select_related("match", "prediction").order_by(
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
                    decision.prediction.actual_outcome
                    if decision.prediction_id
                    else _canonical_outcome(decision.match)
                ),
                "selected_price": decision.selected_price,
                "expected_value": decision.expected_value,
            }
        )
    for key, rows in decision_groups.items():
        policy_summary[":".join(key)] = policy_metrics(rows)
    return {"predictions": prediction_summary, "policies": policy_summary}


def refresh_experiment_summary(experiment, *, cancellation_hygiene=None):
    summary = dict(experiment.summary or {})
    summary.update(summarize_experiment(experiment))
    match_ids = set(experiment.predictions.values_list("match_id", flat=True))
    match_ids.update(experiment.decisions.values_list("match_id", flat=True))
    summary.update(
        {
            "target_count": len(match_ids),
            "prediction_count": experiment.predictions.count(),
            "decision_count": experiment.decisions.count(),
            "resolved_prediction_count": experiment.predictions.filter(
                actual_outcome__isnull=False
            ).count(),
            "unresolved_prediction_count": experiment.predictions.filter(
                actual_outcome__isnull=True
            ).count(),
        }
    )
    if cancellation_hygiene is not None:
        history = list(summary.get("cancellation_hygiene", []))
        history.append(cancellation_hygiene)
        summary["cancellation_hygiene"] = history
    experiment.summary = summary
    experiment.save(update_fields=["summary", "modified"])
    return summary


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
    modernized_selection = select_modernized_config(
        inner_training,
        inner_validation,
        modernized_config_grid(),
    )
    if modernized_selection is not None:
        validation_loss, modernized_config = modernized_selection
        selected["modernized_r45"] = {
            **modernized_config,
            "validation_log_loss": validation_loss,
            "selection": "inner_walk_forward",
        }
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
    failed_counts = defaultdict(int)
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
            elif isinstance(fitted, FailedPrediction):
                failed_counts[f"{adapter.model_code}:{fitted.reason}"] += len(batch)
            else:
                fitted_adapters.append(adapter)
        modernized = None
        if "modernized_r45" in selected:
            modernized, fit_unavailable = fit_modernized(
                history,
                batch_cutoff,
                selected["modernized_r45"],
            )
            for reason, count in fit_unavailable.items():
                unavailable_counts[f"MODERNIZED_R45:{reason}"] += count
            if isinstance(modernized, UnavailablePrediction):
                unavailable_counts[f"MODERNIZED_R45:{modernized.reason}"] += len(batch)
                modernized = None
        market = MarketConsensusAdapter()
        for match in batch:
            cutoff = match.kickoff
            for adapter in fitted_adapters:
                result = adapter.predict(match, cutoff)
                if isinstance(result, UnavailablePrediction):
                    unavailable_counts[f"{adapter.model_code}:{result.reason}"] += 1
                    continue
                if isinstance(result, FailedPrediction):
                    failed_counts[f"{adapter.model_code}:{result.reason}"] += 1
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
            if modernized is not None:
                result = predict_modernized(modernized, history, match, cutoff)
                if isinstance(result, UnavailablePrediction):
                    unavailable_counts[f"MODERNIZED_R45:{result.reason}"] += 1
                else:
                    prediction = _persist_prediction(
                        experiment,
                        match,
                        modernized,
                        result,
                        cutoff,
                        variant=modernized.variant,
                    )
                    persist_standard_policies(
                        experiment, match, prediction, result, cutoff
                    )
        # Reveal every result in the batch only after every prediction is frozen.
        history.extend(batch)

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
            ).exists(),
            modernized_available=experiment.predictions.filter(
                model_code=Prediction.MODERNIZED_R45
            ).exists(),
        ),
        "unavailable_counts": dict(unavailable_counts),
        "failed_counts": dict(failed_counts),
    }
    experiment.completed_at = timezone.now()
    experiment.save(update_fields=["summary", "completed_at", "modified"])
    return experiment
