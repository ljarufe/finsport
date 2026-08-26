from datetime import timedelta
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command

from football.models import Decision, Prediction, PredictionExperiment
from football.prediction import evaluation, service
from football.prediction.contracts import UnavailablePrediction

from .prediction_helpers import create_synthetic_league, create_synthetic_odds

pytestmark = pytest.mark.django_db


def test_bounded_backtest_persists_predictions_decisions_and_unavailable_arms(
    monkeypatch,
):
    competition, seasons, _ = create_synthetic_league()
    original_eligible = evaluation.eligible_finished_matches

    def bounded_eligible(target_competition, *, season_year=None, before=None):
        rows = list(
            original_eligible(
                target_competition, season_year=season_year, before=before
            )
        )
        if season_year == 2023:
            return rows[:16]
        if season_year == 2024:
            return rows[:4]
        return rows

    selected = {
        "dixon_coles": {
            "xi": 0.001,
            "validation_log_loss": 1.0,
            "grid": [0.0, 0.001, 0.002],
        },
        "independent_poisson": {"xi": 0.001, "selected_by": "dixon_coles"},
        "elo_multinomial_logit": {"k": 20, "C": 1.0, "validation_log_loss": 1.0},
    }
    tuning_inputs = {}

    def fake_select(training, validation):
        tuning_inputs["years"] = {
            match.season.year for match in [*training, *validation]
        }
        return selected

    monkeypatch.setattr(evaluation, "eligible_finished_matches", bounded_eligible)
    monkeypatch.setattr(evaluation, "select_hyperparameters", fake_select)
    outer = bounded_eligible(competition, season_year=2024)
    create_synthetic_odds([outer[0]])

    experiment = evaluation.run_backtest(competition, seasons[2])

    assert experiment.mode == PredictionExperiment.MODE_BACKTEST
    assert experiment.completed_at is not None
    assert experiment.predictions.filter(model_code=Prediction.DIXON_COLES).count() == 2
    assert (
        experiment.predictions.filter(model_code=Prediction.INDEPENDENT_POISSON).count()
        == 2
    )
    assert (
        experiment.predictions.filter(
            model_code=Prediction.ELO_MULTINOMIAL_LOGIT
        ).count()
        == 4
    )
    assert (
        experiment.predictions.filter(model_code=Prediction.MARKET_CONSENSUS).count()
        == 1
    )
    assert (
        experiment.decisions.filter(policy_code="LEGACY_R45", prediction=None).count()
        == 4
    )
    assert experiment.decisions.filter(action=Decision.ACTION_NO_BET).exists()
    assert experiment.decisions.filter(
        policy_code="MODAL_ALL", selected_odds_observation__isnull=False
    ).exists()
    assert experiment.summary["sample_counts"]["outer"] == 4
    assert experiment.summary["predictions"]["MARKET_CONSENSUS:"][
        "book_count_distribution"
    ] == {"4": 1}
    assert tuning_inputs["years"] == {2022, 2023}
    assert experiment.summary["unavailable_arms"]["MODERNIZED_R45"] == (
        "INSUFFICIENT_HISTORICAL_MARKET_OBSERVATIONS"
    )
    training_counts = {
        row.diagnostics["training_matches"]
        for row in experiment.predictions.filter(model_code=Prediction.DIXON_COLES)
    }
    assert training_counts == {72}


def test_management_commands_validate_and_delegate(monkeypatch):
    competition, seasons, _ = create_synthetic_league()
    fake_experiment = mock.Mock(id=99)
    fake_experiment.predictions.count.return_value = 12
    fake_experiment.decisions.count.return_value = 36
    fake_experiment.summary = {"ok": True}
    monkeypatch.setattr(
        "football.management.commands.evaluate_football_predictions.run_backtest",
        lambda *_: fake_experiment,
    )
    output = StringIO()
    call_command(
        "evaluate_football_predictions",
        competition=competition.id,
        season=seasons[2].year,
        stdout=output,
    )
    assert "experiment=99 completed" in output.getvalue()

    captured = {}

    def fake_predict(day, cutoff):
        captured.update(day=day, cutoff=cutoff)
        return []

    monkeypatch.setattr(
        "football.management.commands.predict_football_day.predict_day", fake_predict
    )
    output = StringIO()
    cutoff = seasons[2].matches.first().kickoff - timedelta(days=1)
    call_command(
        "predict_football_day",
        date="2024-08-01",
        cutoff=cutoff.isoformat(),
        stdout=output,
    )
    assert captured["cutoff"] == cutoff
    assert "'experiments': 0" in output.getvalue()


def test_predict_day_history_respects_explicit_cutoff(monkeypatch):
    competition, seasons, _ = create_synthetic_league()
    matches = list(seasons[1].matches.order_by("kickoff", "id"))
    before_cutoff = matches[0]
    after_cutoff = matches[4]
    target = matches[8]
    target.status_short = "NS"
    target.status_long = "Not Started"
    target.save(update_fields=["status_short", "status_long"])
    cutoff = after_cutoff.kickoff - timedelta(days=4)
    fitted_histories = []

    class RecordingAdapter:
        model_code = "RECORDING"

        def __init__(self, **kwargs):
            del kwargs

        def fit(self, history, adapter_cutoff):
            assert adapter_cutoff == cutoff
            fitted_histories.append([match.id for match in history])
            return self

        def predict(self, match, prediction_cutoff):
            del match, prediction_cutoff
            return UnavailablePrediction("TEST_UNAVAILABLE")

    class NoMarket:
        def predict(self, match, prediction_cutoff):
            del match, prediction_cutoff
            return UnavailablePrediction("NO_VALID_MARKET")

    monkeypatch.setattr(service, "DixonColesAdapter", RecordingAdapter)
    monkeypatch.setattr(service, "IndependentPoissonAdapter", RecordingAdapter)
    monkeypatch.setattr(service, "EloMultinomialAdapter", RecordingAdapter)
    monkeypatch.setattr(service, "MarketConsensusAdapter", NoMarket)

    experiments = service.predict_day(target.kickoff.date(), cutoff)

    assert len(experiments) == 1
    assert all(before_cutoff.id in history for history in fitted_histories)
    assert all(after_cutoff.id not in history for history in fitted_histories)
    experiment = experiments[0]
    assert experiment.summary["r45_arms"]["MODERNIZED_R45"] == {
        "status": "UNAVAILABLE",
        "reason": "INSUFFICIENT_HISTORICAL_MARKET_OBSERVATIONS",
        "historical_temporal_market_matches": 0,
    }
    assert experiment.summary["r45_arms"]["LEGACY_R45"] == {
        "status": "UNAVAILABLE",
        "reason": "EXACT_LEGACY_CONTEXT_UNAVAILABLE",
        "decision_count": 1,
        "prediction_count": 0,
    }
    decision = experiment.decisions.get(policy_code="LEGACY_R45")
    assert decision.prediction is None
    assert decision.action == Decision.ACTION_NO_BET
    assert decision.reason == "EXACT_LEGACY_CONTEXT_UNAVAILABLE"
    assert not experiment.predictions.filter(
        model_code=Prediction.MODERNIZED_R45
    ).exists()
