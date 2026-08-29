import pytest
from django.utils import timezone as django_timezone

from football.capital.service import run_capital_experiment
from football.models import (
    CapitalExperiment,
    CapitalPolicyRun,
    CaptureRun,
    CaptureWorkItem,
    Decision,
    Match,
    MatchSourceRef,
    OddsSnapshot,
    Prediction,
    ReconciliationStatus,
)
from football.pipeline.hygiene import cleanup_cancelled_matches

from .capital_helpers import create_capital_stream

pytestmark = pytest.mark.django_db


def test_canc_cleanup_dry_run_execute_dependencies_and_rerun():
    experiment, decisions = create_capital_stream(
        [
            {"outcome": "HOME", "price": "2.0000"},
            {"outcome": "AWAY", "price": "2.2000"},
        ],
        decision_policy="MODAL_ALL",
    )
    cancelled_decision, preserved_decision = decisions
    cancelled_match = cancelled_decision.match
    observation = cancelled_decision.selected_odds_observation
    OddsSnapshot.objects.create(
        match=cancelled_match,
        source=observation.source,
        bookmaker=observation.bookmaker,
        market=observation.market,
        home=observation.home,
        draw=observation.draw,
        away=observation.away,
        observed_at=observation.observed_at,
    )
    source_ref = MatchSourceRef.objects.create(
        source=observation.source,
        match=cancelled_match,
        external_id="cancelled-fixture",
        external_label="Cancelled fixture",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    capture_run = CaptureRun.objects.create(
        trigger=CaptureRun.Trigger.MANUAL,
        status=CaptureRun.Status.SUCCESS,
        planning_at=django_timezone.now(),
        completed_at=django_timezone.now(),
    )
    work_item = CaptureWorkItem.objects.create(
        run=capture_run,
        purpose=CaptureWorkItem.Purpose.ODDS_CAPTURE,
        status=CaptureWorkItem.Status.SUCCESS,
        source=observation.source,
        match=cancelled_match,
        market=observation.market,
        logical_identity="cancelled-capture-audit",
    )
    deterministic = run_capital_experiment(
        prediction_experiment=experiment,
        source_model_code=Prediction.DIXON_COLES,
        decision_policy_code="MODAL_ALL",
        config={
            "mode": "REPLAY",
            "initial_bankroll": "100",
            "policies": [{"code": "FLAT_UNIT", "config": {"unit": "1"}}],
        },
    )
    stochastic = CapitalExperiment.objects.create(
        source_experiment=experiment,
        source_model_code=Prediction.DIXON_COLES,
        decision_policy_code="MODAL_ALL",
        mode=CapitalExperiment.MODE_MONTE_CARLO,
        initial_bankroll="100",
        config={"mode": "MONTE_CARLO"},
        input_count=1,
        input_hash="a" * 64,
        input_manifest={"decision_ids": [cancelled_decision.pk]},
    )
    CapitalPolicyRun.objects.create(
        experiment=stochastic,
        policy_code="FLAT_UNIT",
        policy_version="test-v1",
        policy_config={"unit": "1"},
        status=CapitalPolicyRun.STATUS_PRODUCED,
    )
    cancelled_match.status_short = "CANC"
    cancelled_match.status_long = "Cancelled"
    cancelled_match.outcome = ""
    cancelled_match.save(
        update_fields=["status_short", "status_long", "outcome", "modified"]
    )
    counts_before = {
        "predictions": Prediction.objects.count(),
        "decisions": Decision.objects.count(),
        "capital": CapitalExperiment.objects.count(),
        "snapshots": OddsSnapshot.objects.count(),
    }

    planned = cleanup_cancelled_matches(dry_run=True)

    assert planned.status == "SKIPPED"
    assert planned.reason == "DRY_RUN"
    assert planned.counts == {
        "matches": 1,
        "odds_snapshots": 1,
        "odds_observations": 1,
        "predictions": 1,
        "decisions": 1,
        "capital_experiments": 2,
    }
    assert set(planned.capital_experiment_ids) == {deterministic.pk, stochastic.pk}
    assert counts_before == {
        "predictions": Prediction.objects.count(),
        "decisions": Decision.objects.count(),
        "capital": CapitalExperiment.objects.count(),
        "snapshots": OddsSnapshot.objects.count(),
    }

    executed = cleanup_cancelled_matches()
    rerun = cleanup_cancelled_matches()
    experiment.refresh_from_db()

    assert executed.status == "SUCCESS"
    assert rerun.status == "NO_WORK"
    assert rerun.reason == "ALREADY_CLEAN"
    assert Match.objects.filter(pk=cancelled_match.pk, status_short="CANC").exists()
    assert MatchSourceRef.objects.filter(pk=source_ref.pk).exists()
    assert CaptureRun.objects.filter(pk=capture_run.pk).exists()
    assert CaptureWorkItem.objects.filter(pk=work_item.pk).exists()
    assert not OddsSnapshot.objects.filter(match=cancelled_match).exists()
    assert not cancelled_match.odds_observations.exists()
    assert not Prediction.objects.filter(match=cancelled_match).exists()
    assert not Decision.objects.filter(match=cancelled_match).exists()
    assert CapitalExperiment.objects.count() == 0
    assert Decision.objects.filter(pk=preserved_decision.pk).exists()
    assert experiment.summary["target_count"] == 1
    assert experiment.summary["prediction_count"] == 1
    assert experiment.summary["decision_count"] == 1
    assert experiment.summary["cancellation_hygiene"][-1]["match_ids"] == [
        cancelled_match.pk
    ]


@pytest.mark.parametrize("status", ["PST", "FT", "SUSP", "UNKNOWN"])
def test_non_canc_statuses_are_never_destructive(status):
    experiment, decisions = create_capital_stream(
        [{"outcome": "HOME"}], decision_policy="MODAL_ALL"
    )
    decision = decisions[0]
    match = decision.match
    match.status_short = status
    match.save(update_fields=["status_short", "modified"])
    prediction_id = experiment.predictions.get().pk
    observation_id = decision.selected_odds_observation_id

    result = cleanup_cancelled_matches(match_ids=[match.pk])

    assert result.status == "NO_WORK"
    assert Match.objects.filter(pk=match.pk).exists()
    assert Prediction.objects.filter(pk=prediction_id).exists()
    assert Decision.objects.filter(pk=decision.pk).exists()
    assert decision.selected_odds_observation.__class__.objects.filter(
        pk=observation_id
    ).exists()
