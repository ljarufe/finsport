import json
import runpy
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from io import StringIO
from types import SimpleNamespace
from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from football.api_football import APIFootballResponseError
from football.capital.baseline import run_research_baseline
from football.capture.contracts import CaptureResult
from football.models import (
    CapitalExperiment,
    Competition,
    Decision,
    Match,
    PipelineRun,
    Prediction,
    PredictionExperiment,
    Season,
    Team,
)
from football.observability.pipeline import exception_diagnostic
from football.pipeline import run_pipeline
from football.pipeline.contracts import PhaseResult, PhaseState
from football.pipeline.service import _phase_status
from football.prediction.contracts import (
    ProbabilityResult,
    UnavailablePrediction,
)
from football.prediction.service import (
    ProspectivePredictionResult,
    predict_competition_day,
)
from football.prediction.settlement import settle_prospective_predictions
from football.tasks import wake_pipeline

from .capital_helpers import create_capital_stream

pytestmark = pytest.mark.django_db


def create_target(name, country, kickoff):
    competition = Competition.objects.create(
        name=name,
        competition_type="League",
        country=country,
        enabled=True,
    )
    season = Season.objects.create(
        competition=competition,
        year=kickoff.year,
        start_date=date(kickoff.year, 1, 1),
        end_date=date(kickoff.year, 12, 31),
        coverage={"odds": True},
    )
    home = Team.objects.create(competition=competition, name=f"{name} Home")
    away = Team.objects.create(competition=competition, name=f"{name} Away")
    match = Match.objects.create(
        season=season,
        home_team=home,
        away_team=away,
        kickoff=kickoff,
        status_short="NS",
        status_long="Not Started",
    )
    return competition, match


def fake_capture(at, targets, *, status="NO_WORK"):
    items = []
    for competition, match in targets:
        target_at = at
        items.append(
            {
                "purpose": "ODDS_CAPTURE",
                "status": "ALREADY_FULFILLED",
                "match_id": match.pk,
                "competition_id": competition.pk,
                "intended_window": "early",
                "target_at": target_at.isoformat(),
                "not_before": (at - timedelta(minutes=5)).isoformat(),
                "not_after": (at + timedelta(minutes=5)).isoformat(),
            }
        )
    return CaptureResult(
        run_id=None,
        status=status,
        planning_at=at,
        quota_before={},
        quota_after={},
        plan={"items": items},
    )


def patch_fast_non_market_models(monkeypatch):
    class Adapter:
        model_code = Prediction.DIXON_COLES
        model_version = "test-v1"
        config = {}

        def __init__(self, **kwargs):
            del kwargs

        def fit(self, history, cutoff):
            del history, cutoff
            return self

        def predict(self, target, cutoff):
            del target, cutoff
            return ProbabilityResult(0.5, 0.3, 0.2)

    class PoissonAdapter(Adapter):
        model_code = Prediction.INDEPENDENT_POISSON

    class EloAdapter(Adapter):
        model_code = Prediction.ELO_MULTINOMIAL_LOGIT

    class MissingMarket:
        def predict(self, target, cutoff):
            del target, cutoff
            return UnavailablePrediction("NO_VALID_MARKET")

    monkeypatch.setattr("football.prediction.service.DixonColesAdapter", Adapter)
    monkeypatch.setattr(
        "football.prediction.service.IndependentPoissonAdapter", PoissonAdapter
    )
    monkeypatch.setattr("football.prediction.service.EloMultinomialAdapter", EloAdapter)
    monkeypatch.setattr(
        "football.prediction.service.MarketConsensusAdapter", MissingMarket
    )


def test_pipeline_dry_run_is_provider_and_write_free(monkeypatch):
    at = datetime(2026, 8, 28, 18, tzinfo=dt_timezone.utc)
    competition, match = create_target("Dry League", "PE", at + timedelta(hours=2))
    calls = []

    def capture_stub(**kwargs):
        calls.append(kwargs)
        return fake_capture(at, [(competition, match)])

    monkeypatch.setattr("football.pipeline.service.run_capture", capture_stub)
    before = {
        "pipeline": PipelineRun.objects.count(),
        "experiments": PredictionExperiment.objects.count(),
        "predictions": Prediction.objects.count(),
        "decisions": Decision.objects.count(),
        "capital": CapitalExperiment.objects.count(),
    }

    result = run_pipeline(at=at, dry_run=True, max_provider_attempts=2)

    assert calls == [
        {
            "at": at,
            "dry_run": True,
            "trigger": "MANUAL",
            "max_provider_attempts": 2,
        }
    ]
    assert result.run_id is None
    assert result.phases["CAPTURE"]["state"] == "SKIPPED"
    assert result.phases["PREDICTION"]["state"] == "SKIPPED"
    assert result.phases["RESULT_SETTLEMENT"]["state"] == "SKIPPED"
    assert result.phases["CAPITAL"]["state"] == "SKIPPED"
    assert result.report["capture"]["provider_attempts"] == 0
    assert result.report["schema_version"] == "fs006-report-v1"
    assert before == {
        "pipeline": PipelineRun.objects.count(),
        "experiments": PredictionExperiment.objects.count(),
        "predictions": Prediction.objects.count(),
        "decisions": Decision.objects.count(),
        "capital": CapitalExperiment.objects.count(),
    }


def test_capture_provider_cause_reaches_single_pipeline_terminal_event(monkeypatch):
    at = datetime(2026, 8, 31, 4, 30, tzinfo=dt_timezone.utc)
    try:
        raise APIFootballResponseError(
            "API-Football reported: fixture: Invalid fixture parameter 1550103",
            failure_kind="provider_application_error",
            diagnostic_context={
                "endpoint_family": "odds",
                "http_status": 200,
                "provider_request_id": "request-pipeline",
                "provider_error_category": "object",
                "provider_error_keys": ["fixture"],
                "provider_error_summary": "fixture: Invalid fixture parameter 1550103",
                "attempts": 1,
            },
        )
    except APIFootballResponseError as error:
        cause = {
            **exception_diagnostic(error),
            "component": "capture",
            "operation": "odds_capture",
        }
    capture = CaptureResult(
        run_id=38,
        status="FAILED",
        planning_at=at,
        quota_before={},
        quota_after={},
        operational_cause=cause,
    )
    monkeypatch.setattr(
        "football.pipeline.service.run_capture", lambda **kwargs: capture
    )

    with mock.patch("football.observability.pipeline.emit_event") as emitter:
        result = run_pipeline(at=at)

    emitter.assert_called_once()
    event = emitter.call_args.kwargs
    assert event["event_code"] == "PIPELINE_FAILED"
    assert event["pipeline_run_id"] == result.run_id
    assert event["capture_run_id"] == 38
    assert event["provider"] == "API-Football"
    assert event["failure_kind"] == "provider_application_error"
    assert event["operation"] == "odds_capture"
    assert event["context"]["provider_error_summary"] == (
        "fixture: Invalid fixture parameter 1550103"
    )
    assert event["traceback_text"].count("Traceback (most recent call last)") == 1


def test_pipeline_command_prints_json_and_rejects_naive_cutoff(monkeypatch):
    at = datetime(2026, 8, 28, 18, tzinfo=dt_timezone.utc)
    result = SimpleNamespace(
        as_dict=lambda: {
            "status": "NO_WORK",
            "report": {"schema_version": "fs006-report-v1"},
        }
    )
    service = mock.Mock(return_value=result)
    monkeypatch.setattr(
        "football.management.commands.run_football_pipeline.run_pipeline", service
    )
    output = StringIO()

    call_command(
        "run_football_pipeline",
        at=at.isoformat(),
        dry_run=True,
        max_provider_attempts=2,
        stdout=output,
    )

    service.assert_called_once_with(
        at=at,
        dry_run=True,
        max_provider_attempts=2,
    )
    assert json.loads(output.getvalue())["report"]["schema_version"] == (
        "fs006-report-v1"
    )
    with pytest.raises(CommandError, match="aware ISO-8601"):
        call_command("run_football_pipeline", at="2026-08-28T18:00:00")


def test_one_cycle_is_multi_competition_and_repeated_cycle_reuses_identity(monkeypatch):
    at = datetime(2026, 8, 28, 18, tzinfo=dt_timezone.utc)
    first = create_target("First League", "PE", at + timedelta(hours=2))
    second = create_target("Second League", "DE", at + timedelta(hours=2))
    capture = fake_capture(at, [first, second])
    monkeypatch.setattr(
        "football.pipeline.service.run_capture", lambda **kwargs: capture
    )

    def predict_stub(competition, day, cutoff, **kwargs):
        del cutoff
        assert kwargs["match_ids"] == sorted(set(kwargs["match_ids"]))
        existing = PredictionExperiment.objects.filter(
            competition_id=competition,
            logical_identity=kwargs["logical_identity"],
        ).first()
        if existing:
            return ProspectivePredictionResult(existing, False, "ALREADY_EXISTS")
        experiment = PredictionExperiment.objects.create(
            competition_id=competition,
            mode=PredictionExperiment.MODE_PROSPECTIVE,
            period_start=day,
            period_end=day,
            logical_identity=kwargs["logical_identity"],
            intended_window=kwargs["intended_window"],
            target_at=kwargs["target_at"],
            config={
                "cutoff": at.isoformat(),
                "target_match_ids": kwargs["match_ids"],
            },
            summary={"target_count": 1},
        )
        return ProspectivePredictionResult(experiment, True)

    monkeypatch.setattr(
        "football.pipeline.service.predict_competition_day", predict_stub
    )

    first_result = run_pipeline(at=at)
    repeated = run_pipeline(at=at)

    assert PredictionExperiment.objects.count() == 2
    assert PipelineRun.objects.count() == 2
    assert first_result.report["prediction"]["created_count"] == 2
    assert repeated.report["prediction"]["created_count"] == 0
    assert repeated.report["prediction"]["reused_count"] == 2
    assert {row["id"] for row in first_result.report["competitions_considered"]} == {
        first[0].pk,
        second[0].pk,
    }
    assert repeated.status == PipelineRun.Status.NO_WORK


def test_pipeline_scopes_each_temporal_experiment_to_its_exact_match_batch(
    monkeypatch,
):
    at = datetime(2026, 8, 28, 18, tzinfo=dt_timezone.utc)
    competition, first_match = create_target(
        "Temporal Scope League", "PE", at + timedelta(hours=4)
    )
    season = first_match.season
    shared_home = Team.objects.create(
        competition=competition, name="Shared Window Home"
    )
    shared_away = Team.objects.create(
        competition=competition, name="Shared Window Away"
    )
    shared_match = Match.objects.create(
        season=season,
        home_team=shared_home,
        away_team=shared_away,
        kickoff=first_match.kickoff,
        status_short="NS",
        status_long="Not Started",
    )
    later_home = Team.objects.create(competition=competition, name="Later Window Home")
    later_away = Team.objects.create(competition=competition, name="Later Window Away")
    later_match = Match.objects.create(
        season=season,
        home_team=later_home,
        away_team=later_away,
        kickoff=at + timedelta(hours=5),
        status_short="NS",
        status_long="Not Started",
    )
    first_target = at
    later_target = at + timedelta(hours=2)

    def item(match, target):
        return {
            "purpose": "ODDS_CAPTURE",
            "status": "ALREADY_FULFILLED",
            "match_id": match.pk,
            "competition_id": competition.pk,
            "intended_window": "early",
            "target_at": target.isoformat(),
            "not_before": (target - timedelta(minutes=5)).isoformat(),
            "not_after": (target + timedelta(minutes=5)).isoformat(),
        }

    plan = {
        "items": [
            item(first_match, first_target),
            item(first_match, first_target),  # duplicated planner representation
            item(shared_match, first_target),
            item(later_match, later_target),
        ]
    }

    def capture_stub(**kwargs):
        return CaptureResult(
            run_id=None,
            status="NO_WORK",
            planning_at=kwargs["at"],
            quota_before={},
            quota_after={},
            plan=plan,
        )

    monkeypatch.setattr("football.pipeline.service.run_capture", capture_stub)
    patch_fast_non_market_models(monkeypatch)

    run_pipeline(at=first_target)
    first_experiment = PredictionExperiment.objects.get(target_at=first_target)

    assert first_experiment.config["target_match_ids"] == sorted(
        [first_match.pk, shared_match.pk]
    )
    assert set(first_experiment.predictions.values_list("match_id", flat=True)) == {
        first_match.pk,
        shared_match.pk,
    }
    assert first_experiment.predictions.count() == 6
    assert first_experiment.decisions.filter(match=later_match).count() == 0

    run_pipeline(at=later_target)
    later_experiment = PredictionExperiment.objects.get(target_at=later_target)

    assert later_experiment.logical_identity != first_experiment.logical_identity
    assert later_experiment.config["target_match_ids"] == [later_match.pk]
    assert set(later_experiment.predictions.values_list("match_id", flat=True)) == {
        later_match.pk
    }
    assert later_experiment.decisions.exclude(match=later_match).count() == 0


def test_prediction_identity_allows_later_window_and_missing_market_keeps_models(
    monkeypatch,
):
    at = datetime(2026, 8, 28, 18, tzinfo=dt_timezone.utc)
    competition, match = create_target(
        "Prediction League", "PE", at + timedelta(hours=4)
    )

    patch_fast_non_market_models(monkeypatch)

    empty = predict_competition_day(
        competition,
        match.kickoff.date(),
        at,
        logical_identity="empty-explicit-target-batch",
        intended_window="early",
        target_at=at,
        match_ids=[999999],
    )

    first = predict_competition_day(
        competition,
        match.kickoff.date(),
        at,
        logical_identity="competition-day-early-target-1",
        intended_window="early",
        target_at=at,
        match_ids=[match.pk, match.pk],
    )
    repeated = predict_competition_day(
        competition,
        match.kickoff.date(),
        at + timedelta(minutes=1),
        logical_identity="competition-day-early-target-1",
        intended_window="early",
        target_at=at,
        match_ids=[match.pk],
    )
    later = predict_competition_day(
        competition,
        match.kickoff.date(),
        at + timedelta(minutes=30),
        logical_identity="competition-day-middle-target-2",
        intended_window="middle",
        target_at=at + timedelta(minutes=30),
        match_ids=[match.pk],
    )

    assert empty.experiment is None
    assert empty.reason == "NO_ELIGIBLE_TARGETS"
    assert first.created is True
    assert repeated.created is False
    assert later.created is True
    assert PredictionExperiment.objects.count() == 2
    assert first.experiment.predictions.count() == 3
    assert first.experiment.config["target_match_ids"] == [match.pk]
    assert not first.experiment.predictions.filter(
        model_code=Prediction.MARKET_CONSENSUS
    ).exists()
    assert first.experiment.summary["unavailable"][f"MARKET_CONSENSUS:{match.pk}"] == (
        "NO_VALID_MARKET"
    )


def test_settlement_requires_canonical_finished_outcome_and_never_rewrites_decision():
    experiment, decisions = create_capital_stream(
        [{"outcome": ""}], decision_policy="MODAL_ALL"
    )
    prediction = experiment.predictions.get()
    decision = decisions[0]
    original = {
        "action": decision.action,
        "reason": decision.reason,
        "selected_price": decision.selected_price,
        "selected_odds_observation_id": decision.selected_odds_observation_id,
    }

    assert settle_prospective_predictions().status == "NO_WORK"
    match = prediction.match
    match.status_short = "FT"
    match.status_long = "Match Finished"
    match.outcome = Match.OUTCOME_HOME
    match.save(update_fields=["status_short", "status_long", "outcome", "modified"])

    settled = settle_prospective_predictions()
    prediction.refresh_from_db()
    decision.refresh_from_db()
    evaluated_at = prediction.evaluated_at
    repeated = settle_prospective_predictions()
    prediction.refresh_from_db()
    experiment.refresh_from_db()

    assert settled.status == "SUCCESS"
    assert prediction.actual_outcome == Match.OUTCOME_HOME
    assert prediction.evaluated_at == evaluated_at
    assert repeated.status == "NO_WORK"
    assert experiment.summary["resolved_prediction_count"] == 1
    assert original == {
        "action": decision.action,
        "reason": decision.reason,
        "selected_price": decision.selected_price,
        "selected_odds_observation_id": decision.selected_odds_observation_id,
    }


def test_capital_baseline_is_exact_idempotent_and_honestly_unavailable():
    experiment, _ = create_capital_stream(
        [{"outcome": "HOME", "price": "2.0000"}],
        decision_policy="MODAL_ALL",
    )

    first = run_research_baseline(experiment)
    repeated = run_research_baseline(experiment)

    assert first.status == "PRODUCED"
    assert first.created is True
    assert repeated.status == "PRODUCED"
    assert repeated.created is False
    assert repeated.capital_experiment_id == first.capital_experiment_id
    capital = CapitalExperiment.objects.get(pk=first.capital_experiment_id)
    assert capital.mode == "REPLAY"
    assert str(capital.initial_bankroll) == "100.00000000"
    run = capital.policy_runs.get()
    assert run.policy_code == "FLAT_UNIT"
    assert run.policy_config == {"unit": "1"}


def test_capital_baseline_unresolved_creates_no_capital_experiment():
    experiment, _ = create_capital_stream(
        [{"outcome": ""}], decision_policy="MODAL_ALL"
    )

    result = run_research_baseline(experiment)

    assert result.status == "UNAVAILABLE"
    assert result.reason == "UNRESOLVED_CANONICAL_OUTCOME"
    assert CapitalExperiment.objects.count() == 0


@override_settings(FOOTBALL_PIPELINE_ENABLED=False)
def test_pipeline_scheduler_disabled_is_provider_free():
    assert wake_pipeline() == {"status": "DISABLED", "provider_attempts": 0}


@override_settings(FOOTBALL_PIPELINE_ENABLED=True)
def test_pipeline_scheduler_enabled_delegates_to_service(monkeypatch):
    result = SimpleNamespace(as_dict=lambda: {"status": "NO_WORK"})
    service = mock.Mock(return_value=result)
    monkeypatch.setattr("football.tasks.run_pipeline", service)

    assert wake_pipeline() == {"status": "NO_WORK"}
    service.assert_called_once_with(trigger=PipelineRun.Trigger.SCHEDULER)


def test_beat_enabled_pipeline_is_the_only_automatic_capture_owner(monkeypatch):
    monkeypatch.setenv("FOOTBALL_PIPELINE_ENABLED", "True")
    monkeypatch.setenv("FOOTBALL_CAPTURE_ENABLED", "True")
    configured = runpy.run_path("finsport/settings.py")

    assert configured["FOOTBALL_PIPELINE_ENABLED"] is True
    assert configured["CELERY_BEAT_SCHEDULE"] == {
        "football-pipeline-wake": {
            "task": "football.pipeline.wake",
            "schedule": configured["FOOTBALL_CAPTURE_WAKE_SECONDS"],
        }
    }


def test_failed_phase_requires_real_success_for_degraded_status():
    phases = {
        "CAPTURE": PhaseResult(PhaseState.FAILED),
        "PREDICTION": PhaseResult(PhaseState.NO_WORK),
        "RESULT_SETTLEMENT": PhaseResult(PhaseState.NO_WORK),
        "CAPITAL": PhaseResult(PhaseState.NO_WORK),
    }

    assert _phase_status(phases) == PipelineRun.Status.FAILED

    phases["RESULT_SETTLEMENT"] = PhaseResult(PhaseState.SUCCESS)

    assert _phase_status(phases) == PipelineRun.Status.DEGRADED
