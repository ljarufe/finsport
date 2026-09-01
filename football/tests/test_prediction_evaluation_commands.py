from datetime import timedelta
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

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
    assert not experiment.decisions.filter(prediction=None).exists()
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
        "INSUFFICIENT_LEAK_SAFE_SELECTION_EVIDENCE"
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
    with pytest.raises(CommandError, match="Cutoff must include a timezone offset"):
        call_command(
            "predict_football_day",
            date="2024-08-01",
            cutoff="2024-08-01T10:00:00",
        )


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
    assert experiment.summary["r45_arms"]["MODERNIZED_R45"]["status"] == ("UNAVAILABLE")
    assert experiment.summary["r45_arms"]["MODERNIZED_R45"]["classification"] == (
        "ACTIVE"
    )
    assert not experiment.decisions.filter(prediction=None).exists()
    assert not experiment.predictions.filter(
        model_code=Prediction.MODERNIZED_R45
    ).exists()


def test_modernized_r45_backtest_and_prospective_paths_persist(monkeypatch):
    competition, seasons, _ = create_synthetic_league()
    training = list(seasons[0].matches.order_by("kickoff", "id"))
    validation = list(seasons[1].matches.order_by("kickoff", "id"))
    outer = list(seasons[2].matches.order_by("kickoff", "id"))[:4]
    create_synthetic_odds([*training, *validation, *outer])
    original_eligible = evaluation.eligible_finished_matches

    def bounded_eligible(target_competition, *, season_year=None, before=None):
        rows = list(
            original_eligible(
                target_competition, season_year=season_year, before=before
            )
        )
        return rows[:4] if season_year == seasons[2].year else rows

    selected = {
        "dixon_coles": {"xi": 0.001},
        "independent_poisson": {"xi": 0.001},
        "elo_multinomial_logit": {"k": 20, "C": 1.0},
    }
    modernized = {"variant": "M0", "c": 1.0, "prior_strength": 20}
    monkeypatch.setattr(evaluation, "eligible_finished_matches", bounded_eligible)
    monkeypatch.setattr(evaluation, "select_hyperparameters", lambda *_: selected)
    monkeypatch.setattr(
        evaluation, "select_modernized_config", lambda *_: (0.75, modernized)
    )

    backtest = evaluation.run_backtest(competition, seasons[2])

    r45_predictions = backtest.predictions.filter(model_code=Prediction.MODERNIZED_R45)
    assert r45_predictions.count() == 4
    assert set(r45_predictions.values_list("variant", flat=True)) == {"M0"}
    assert (
        backtest.config["selected_hyperparameters"]["modernized_r45"]["selection"]
        == "inner_walk_forward"
    )
    assert backtest.decisions.filter(prediction__in=r45_predictions).exists()

    target = outer[-1]
    target.status_short = "NS"
    target.status_long = "Not Started"
    target.outcome = ""
    target.home_score = None
    target.away_score = None
    target.save(
        update_fields=[
            "status_short",
            "status_long",
            "outcome",
            "home_score",
            "away_score",
            "modified",
        ]
    )
    cutoff = target.kickoff - timedelta(hours=1)

    prospective = service.predict_competition_day(
        competition,
        target.kickoff.date(),
        cutoff,
        match_ids=[target.pk],
    ).experiment

    prediction = prospective.predictions.get(model_code=Prediction.MODERNIZED_R45)
    assert prediction.variant == "M0"
    assert prediction.cutoff == cutoff
    assert prediction.diagnostics["history_max_kickoff"] < cutoff.isoformat()
    assert prospective.decisions.filter(prediction=prediction).exists()
