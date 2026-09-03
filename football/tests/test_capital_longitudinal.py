import json
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import Client
from django.test.utils import CaptureQueriesContext

from football.capital.longitudinal import (
    PRIMARY_EPOCH,
    REFERENCE_POLICY_ARMS,
    LongitudinalResult,
    build_longitudinal_basis,
    initialize_primary_series,
    recompute_longitudinal_capital,
)
from football.capital.service import run_capital_experiment
from football.capture.contracts import CaptureResult
from football.models import (
    CapitalExperiment,
    CapitalLongitudinalSeries,
    CapitalPolicyRun,
    Decision,
    Match,
    OddsObservation,
    PipelineRun,
    Prediction,
)
from football.pipeline import run_pipeline
from football.pipeline.hygiene import cleanup_cancelled_matches

from .capital_helpers import create_capital_stream

pytestmark = pytest.mark.django_db

AFTER_EPOCH = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)


def _stream(rows, *, suffix="", enabled=True, base=AFTER_EPOCH):
    return create_capital_stream(
        rows,
        decision_policy="MODAL_ALL",
        enabled=enabled,
        suffix=suffix,
        base=base,
    )


def test_series_freezes_enabled_cohort_once_and_keeps_fixed_epoch():
    first_experiment, first_decisions = _stream(
        [
            {"decision_time": PRIMARY_EPOCH - timedelta(microseconds=1)},
            {"decision_time": PRIMARY_EPOCH},
        ],
        suffix="-first",
    )
    disabled_experiment, _ = _stream([{}], suffix="-disabled", enabled=False)

    series, created = initialize_primary_series()
    assert created is True
    assert series.frozen_competition_ids == [first_experiment.competition_id]
    assert series.epoch == PRIMARY_EPOCH

    first_experiment.competition.enabled = False
    first_experiment.competition.save(update_fields=["enabled", "modified"])
    disabled_experiment.competition.enabled = True
    disabled_experiment.competition.save(update_fields=["enabled", "modified"])

    repeated, created = initialize_primary_series()
    basis = build_longitudinal_basis(repeated)
    assert created is False
    assert repeated.frozen_competition_ids == [first_experiment.competition_id]
    assert basis.manifest["decision_ids"] == [first_decisions[1].pk]


def test_empty_enabled_cohort_does_not_freeze_primary_series(monkeypatch):
    disabled_experiment, _ = _stream([{}], suffix="-empty", enabled=False)
    emitter = mock.Mock()
    monkeypatch.setattr("football.capital.longitudinal.emit_event", emitter)

    empty = recompute_longitudinal_capital()

    assert empty.status == "UNAVAILABLE"
    assert empty.reason == "NO_ENABLED_COMPETITIONS"
    assert not CapitalLongitudinalSeries.objects.exists()
    assert not emitter.called

    disabled_experiment.competition.enabled = True
    disabled_experiment.competition.save(update_fields=["enabled", "modified"])
    initialized = recompute_longitudinal_capital()
    series = CapitalLongitudinalSeries.objects.get()

    assert initialized.status == "PRODUCED"
    assert series.frozen_competition_ids == [disabled_experiment.competition_id]

    later_experiment, _ = _stream([{}], suffix="-later-enabled")
    repeated = recompute_longitudinal_capital()
    series.refresh_from_db()

    assert repeated.status == "NO_WORK"
    assert later_experiment.competition_id not in series.frozen_competition_ids
    assert series.frozen_competition_ids == [disabled_experiment.competition_id]


def test_basis_is_chronological_preserves_batches_no_bet_and_stops_at_first_gap():
    first_time = PRIMARY_EPOCH + timedelta(hours=1)
    gap_time = first_time + timedelta(hours=1)
    later_time = gap_time + timedelta(hours=1)
    _, decisions = _stream(
        [
            {"decision_time": first_time, "outcome": "HOME"},
            {
                "decision_time": first_time,
                "action": Decision.ACTION_NO_BET,
                "outcome": "",
                "price": None,
            },
            {"decision_time": gap_time, "outcome": "HOME", "price": None},
            {"decision_time": gap_time, "outcome": "AWAY"},
            {"decision_time": later_time, "outcome": "HOME"},
        ],
        suffix="-gap",
    )
    series, _ = initialize_primary_series()
    basis = build_longitudinal_basis(series)

    assert basis.manifest["decision_ids"] == [decisions[0].pk, decisions[1].pk]
    assert basis.watermark == first_time
    assert basis.input_count == 2
    assert basis.actionable_count == 1
    assert basis.no_bet_count == 1
    assert basis.manifest["complete_batches"] == [
        {
            "decision_time": first_time.isoformat(),
            "decision_ids": [decisions[0].pk, decisions[1].pk],
        }
    ]
    assert basis.first_gap["decision_id"] == decisions[2].pk
    assert basis.first_gap["decision_time"] == gap_time.isoformat()
    assert basis.first_gap["reason"] == "MISSING_SELECTED_ODDS_OBSERVATION"
    assert basis.first_gap["batch_decision_ids"] == [
        decisions[2].pk,
        decisions[3].pk,
    ]
    assert basis.first_gap["match_id"] == decisions[2].match_id
    assert decisions[4].pk not in basis.manifest["decision_ids"]


def test_basis_rejects_selected_late_or_mismatched_price_without_substitution():
    decision_time = AFTER_EPOCH + timedelta(days=1)
    _, decisions = _stream(
        [
            {
                "decision_time": decision_time,
                "observation_time": decision_time + timedelta(minutes=1),
            }
        ],
        suffix="-late",
    )
    selected = decisions[0].selected_odds_observation
    OddsObservation.objects.create(
        match=selected.match,
        source=selected.source,
        bookmaker=selected.bookmaker,
        market=selected.market,
        home=selected.home,
        draw=selected.draw,
        away=selected.away,
        observed_at=decision_time - timedelta(hours=2),
    )
    series, _ = initialize_primary_series()

    basis = build_longitudinal_basis(series)
    assert basis.input_count == 0
    assert basis.first_gap["reason"] == "ODDS_NOT_BEFORE_DECISION"

    Decision.objects.filter(pk=decisions[0].pk).update(selected_price=Decimal("9"))
    OddsObservation.objects.filter(pk=selected.pk).update(
        observed_at=decision_time - timedelta(hours=1)
    )
    basis = build_longitudinal_basis(series)
    assert basis.first_gap["reason"] == "SELECTED_PRICE_MISMATCH"


def test_shared_manifest_provenance_batches_and_all_seven_policy_states():
    same_time = AFTER_EPOCH + timedelta(days=1)
    _, first = _stream(
        [
            {
                "decision_time": same_time,
                "outcome": "AWAY",
                "price": Decimal("2"),
                "probability": 0.4,
                "model_version": "model-v1",
                "model_config": {"xi": 0.0},
            }
        ],
        suffix="-one",
    )
    _, second = _stream(
        [
            {
                "decision_time": same_time,
                "outcome": "HOME",
                "price": Decimal("2"),
                "probability": 0.6,
                "model_version": "model-v2",
                "model_config": {"xi": 0.001},
            }
        ],
        suffix="-two",
    )

    result = recompute_longitudinal_capital()
    snapshot = CapitalExperiment.objects.get(pk=result.capital_experiment_id)
    runs = list(snapshot.policy_runs.order_by("id"))

    assert result.status == "PRODUCED"
    assert [run.policy_code for run in runs] == [
        arm["code"] for arm in REFERENCE_POLICY_ARMS
    ]
    assert snapshot.input_manifest["decision_ids"] == [first[0].pk, second[0].pk]
    assert {
        row["prediction"]["model_version"] for row in snapshot.input_manifest["rows"]
    } == {"model-v1", "model-v2"}
    assert {
        json.dumps(row["prediction"]["model_config"], sort_keys=True)
        for row in snapshot.input_manifest["rows"]
    } == {'{"xi": 0.0}', '{"xi": 0.001}'}

    recovery = {
        "LEGACY_RECOVERY",
        "LEGACY_CAPPED",
        "LEGACY_PARTIAL",
    }
    assert all(
        run.status == CapitalPolicyRun.STATUS_UNAVAILABLE
        and run.reason == "UNAVAILABLE_CONCURRENT_RECOVERY_STEP"
        for run in runs
        if run.policy_code in recovery
    )
    produced = [run for run in runs if run.status == CapitalPolicyRun.STATUS_PRODUCED]
    assert all(
        set(run.ledger_entries.values_list("source_decision_id", flat=True))
        == {first[0].pk, second[0].pk}
        for run in produced
    )
    flat = snapshot.policy_runs.get(policy_code="FLAT_UNIT")
    assert {
        row.bankroll_before
        for row in flat.ledger_entries.order_by("source_decision_id")
    } == {Decimal("100")}
    kelly = snapshot.policy_runs.get(policy_code="FRACTIONAL_KELLY")
    assert kelly.ledger_entries.get(source_decision=first[0]).applied_stake == Decimal(
        "0"
    )


def test_no_bet_has_zero_exposure_and_semantic_change_recomputes_from_epoch(
    monkeypatch,
):
    _, decisions = _stream(
        [
            {"outcome": "HOME", "price": Decimal("2")},
            {"action": Decision.ACTION_NO_BET, "outcome": "", "price": None},
        ],
        suffix="-recompute",
    )
    first = recompute_longitudinal_capital()
    emitter = mock.Mock()
    monkeypatch.setattr("football.capital.longitudinal.emit_event", emitter)
    repeated = recompute_longitudinal_capital()
    assert repeated.status == "NO_WORK"
    assert repeated.capital_experiment_id == first.capital_experiment_id
    assert CapitalExperiment.objects.count() == 1
    assert not emitter.called
    flat = CapitalPolicyRun.objects.get(
        experiment_id=first.capital_experiment_id, policy_code="FLAT_UNIT"
    )
    assert flat.metrics["input_decisions"] == 2
    assert flat.metrics["capital_actions"] == 1
    assert flat.ledger_entries.get(source_decision=decisions[1]).applied_stake == 0

    decisions[0].match.outcome = Match.OUTCOME_AWAY
    decisions[0].match.save(update_fields=["outcome", "modified"])
    changed = recompute_longitudinal_capital()
    series = CapitalLongitudinalSeries.objects.get()
    assert changed.status == "PRODUCED"
    assert changed.input_hash != first.input_hash
    assert changed.capital_experiment_id != first.capital_experiment_id
    assert series.current_snapshot_id == changed.capital_experiment_id
    assert CapitalExperiment.objects.count() == 2
    assert changed.input_count == 2


def test_failed_snapshot_retries_same_basis_then_healthy_snapshot_is_idempotent(
    monkeypatch,
):
    _stream([{}], suffix="-retry")
    from football.capital import service as capital_service

    original_replay = capital_service.replay
    replay_calls = 0

    def transient_replay(*args, **kwargs):
        nonlocal replay_calls
        replay_calls += 1
        if replay_calls == 1:
            raise RuntimeError("transient engine failure")
        return original_replay(*args, **kwargs)

    monkeypatch.setattr(capital_service, "replay", transient_replay)
    monkeypatch.setattr("football.capital.longitudinal.emit_event", mock.Mock())

    failed = recompute_longitudinal_capital()
    failed_snapshot = CapitalExperiment.objects.get(pk=failed.capital_experiment_id)
    series = CapitalLongitudinalSeries.objects.get()

    assert (
        failed_snapshot.policy_runs.filter(
            status=CapitalPolicyRun.STATUS_FAILED
        ).count()
        == 1
    )
    assert series.current_snapshot_id is None

    healthy = recompute_longitudinal_capital()
    healthy_snapshot = CapitalExperiment.objects.get(pk=healthy.capital_experiment_id)
    series.refresh_from_db()

    assert healthy.status == "PRODUCED"
    assert healthy_snapshot.pk != failed_snapshot.pk
    assert healthy_snapshot.semantic_identity == failed_snapshot.semantic_identity
    assert healthy_snapshot.logical_identity != failed_snapshot.logical_identity
    assert not healthy_snapshot.policy_runs.filter(
        status=CapitalPolicyRun.STATUS_FAILED
    ).exists()
    assert series.current_snapshot_id == healthy_snapshot.pk
    assert CapitalExperiment.objects.filter(pk=failed_snapshot.pk).exists()
    assert failed_snapshot.policy_runs.filter(
        status=CapitalPolicyRun.STATUS_FAILED
    ).exists()

    replay_calls_after_retry = replay_calls
    unchanged = recompute_longitudinal_capital()

    assert unchanged.status == "NO_WORK"
    assert unchanged.capital_experiment_id == healthy_snapshot.pk
    assert replay_calls == replay_calls_after_retry
    assert CapitalExperiment.objects.count() == 2


@pytest.mark.django_db(transaction=True)
def test_same_series_recomputes_are_serialized_and_converge(monkeypatch):
    _stream([{}], suffix="-serialized")
    series, _ = initialize_primary_series()
    from football.capital import longitudinal as longitudinal_service

    original_builder = longitudinal_service.build_longitudinal_basis
    first_inside_lock = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    concurrent_builder_entry = threading.Event()
    builder_calls = 0
    builder_calls_lock = threading.Lock()

    def controlled_builder(locked_series):
        nonlocal builder_calls
        with builder_calls_lock:
            builder_calls += 1
            call_number = builder_calls
        if call_number == 1:
            first_inside_lock.set()
            assert release_first.wait(timeout=10)
        else:
            concurrent_builder_entry.set()
        return original_builder(locked_series)

    monkeypatch.setattr(
        longitudinal_service, "build_longitudinal_basis", controlled_builder
    )
    monkeypatch.setattr(longitudinal_service, "emit_event", mock.Mock())
    results = {}
    errors = {}

    def worker(name, started=None):
        close_old_connections()
        if started is not None:
            started.set()
        try:
            results[name] = recompute_longitudinal_capital(series=series.pk)
        except Exception as error:  # pragma: no cover - asserted below
            errors[name] = error
        finally:
            close_old_connections()

    first = threading.Thread(target=worker, args=("first",), daemon=True)
    second = threading.Thread(
        target=worker,
        args=("second", second_started),
        daemon=True,
    )
    first.start()
    assert first_inside_lock.wait(timeout=10)
    second.start()
    assert second_started.wait(timeout=10)
    assert not concurrent_builder_entry.wait(timeout=0.5)

    release_first.set()
    first.join(timeout=10)
    second.join(timeout=10)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == {}
    assert {results["first"].status, results["second"].status} == {
        "PRODUCED",
        "NO_WORK",
    }
    assert (
        results["first"].capital_experiment_id
        == results["second"].capital_experiment_id
    )
    assert CapitalExperiment.objects.count() == 1
    series.refresh_from_db()
    assert series.current_snapshot_id == results["first"].capital_experiment_id


def test_cancellation_deletes_snapshot_and_clears_current_pointer():
    _, decisions = _stream([{}], suffix="-cancel")
    produced = recompute_longitudinal_capital()
    match = decisions[0].match
    match.status_short = "CANC"
    match.status_long = "Cancelled"
    match.outcome = ""
    match.save(update_fields=["status_short", "status_long", "outcome", "modified"])

    result = cleanup_cancelled_matches()
    series = CapitalLongitudinalSeries.objects.get()
    assert result.status == "SUCCESS"
    assert produced.capital_experiment_id in result.capital_experiment_ids
    assert series.current_snapshot_id is None
    assert not CapitalExperiment.objects.filter(
        pk=produced.capital_experiment_id
    ).exists()


def test_first_gap_cancellation_invalidates_current_and_allows_later_advance():
    prefix_time = PRIMARY_EPOCH + timedelta(hours=1)
    gap_time = prefix_time + timedelta(hours=1)
    later_time = gap_time + timedelta(hours=1)
    _, decisions = _stream(
        [
            {"decision_time": prefix_time, "outcome": "HOME"},
            {"decision_time": gap_time, "outcome": "HOME", "price": None},
            {"decision_time": later_time, "outcome": "AWAY"},
        ],
        suffix="-gap-cancel",
    )
    prefix, gap, later = decisions
    produced = recompute_longitudinal_capital()
    snapshot = CapitalExperiment.objects.get(pk=produced.capital_experiment_id)
    assert snapshot.input_manifest["decision_ids"] == [prefix.pk]
    assert snapshot.input_manifest["first_gap"]["decision_id"] == gap.pk
    assert later.pk not in snapshot.input_manifest["decision_ids"]

    gap.match.status_short = "CANC"
    gap.match.status_long = "Cancelled"
    gap.match.outcome = ""
    gap.match.save(update_fields=["status_short", "status_long", "outcome", "modified"])
    cleaned = cleanup_cancelled_matches()
    series = CapitalLongitudinalSeries.objects.get()

    assert produced.capital_experiment_id in cleaned.capital_experiment_ids
    assert not CapitalExperiment.objects.filter(
        pk=produced.capital_experiment_id
    ).exists()
    assert series.current_snapshot_id is None
    assert not Decision.objects.filter(pk=gap.pk).exists()
    assert not Decision.objects.filter(
        match=gap.match, action=Decision.ACTION_NO_BET
    ).exists()

    advanced = recompute_longitudinal_capital()
    advanced_snapshot = CapitalExperiment.objects.get(pk=advanced.capital_experiment_id)
    series.refresh_from_db()
    assert advanced.status == "PRODUCED"
    assert advanced_snapshot.input_manifest["decision_ids"] == [prefix.pk, later.pk]
    assert advanced_snapshot.input_manifest["first_gap"] is None
    assert advanced.watermark == later_time.isoformat()
    assert series.current_snapshot_id == advanced_snapshot.pk


def test_source_owner_constraint_keeps_legacy_rows_valid_and_rejects_bad_shapes():
    source, _ = _stream([{}], suffix="-constraint")
    series, _ = initialize_primary_series()
    legacy = run_capital_experiment(
        prediction_experiment=source,
        source_model_code=Prediction.DIXON_COLES,
        decision_policy_code="MODAL_ALL",
        config={
            "mode": "REPLAY",
            "initial_bankroll": "100",
            "policies": [{"code": "FLAT_UNIT", "config": {"unit": "1"}}],
        },
    )
    assert legacy.source_experiment_id == source.pk
    assert legacy.longitudinal_series_id is None
    assert legacy.semantic_identity == ""

    with pytest.raises(IntegrityError), transaction.atomic():
        CapitalExperiment.objects.create(
            source_experiment=source,
            longitudinal_series=series,
            source_model_code=Prediction.DIXON_COLES,
            decision_policy_code="MODAL_ALL",
            mode="REPLAY",
            initial_bankroll="100",
            input_hash="invalid-both",
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        CapitalExperiment.objects.create(
            source_model_code=Prediction.DIXON_COLES,
            decision_policy_code="MODAL_ALL",
            mode="REPLAY",
            initial_bankroll="100",
            input_hash="invalid-neither",
        )


def test_failed_recompute_invalidates_stale_current_and_emits_one_error(monkeypatch):
    _, decisions = _stream([{}], suffix="-failure")
    first = recompute_longitudinal_capital()
    decisions[0].match.outcome = Match.OUTCOME_AWAY
    decisions[0].match.save(update_fields=["outcome", "modified"])
    failure = RuntimeError("controlled persistence failure")
    monkeypatch.setattr(
        "football.capital.longitudinal.run_prepared_capital_experiment",
        mock.Mock(side_effect=failure),
    )
    emitter = mock.Mock()
    monkeypatch.setattr("football.capital.longitudinal.emit_event", emitter)

    with pytest.raises(RuntimeError, match="controlled"):
        recompute_longitudinal_capital(pipeline_run_id=77)

    CapitalLongitudinalSeries.objects.get().refresh_from_db()
    series = CapitalLongitudinalSeries.objects.get()
    assert series.current_snapshot_id is None
    assert CapitalExperiment.objects.filter(pk=first.capital_experiment_id).exists()
    emitter.assert_called_once()
    assert emitter.call_args.kwargs["severity"] == "ERROR"
    assert emitter.call_args.kwargs["pipeline_run_id"] == 77


def test_initialization_failure_has_one_capital_traceback_owner(monkeypatch):
    failure = RuntimeError("controlled initialization failure")
    monkeypatch.setattr(
        "football.capital.longitudinal.initialize_primary_series",
        mock.Mock(side_effect=failure),
    )
    emitter = mock.Mock()
    monkeypatch.setattr("football.capital.longitudinal.emit_event", emitter)

    with pytest.raises(RuntimeError, match="controlled initialization") as raised:
        recompute_longitudinal_capital(pipeline_run_id=78)

    assert raised.value.longitudinal_event_emitted is True
    emitter.assert_called_once()
    event = emitter.call_args.kwargs
    assert event["event_code"] == "CAPITAL_LONGITUDINAL_RECOMPUTE_FAILED"
    assert event["pipeline_run_id"] == 78
    assert event["exception"] is failure
    assert event["context"]["comparator"] == "DIXON_COLES+MODAL_ALL"


def test_basis_failure_clears_existing_current_but_retains_historical_row(monkeypatch):
    _stream([{}], suffix="-basis-failure")
    produced = recompute_longitudinal_capital()
    series = CapitalLongitudinalSeries.objects.get()
    assert series.current_snapshot_id == produced.capital_experiment_id
    failure = RuntimeError("controlled basis failure")
    monkeypatch.setattr(
        "football.capital.longitudinal.build_longitudinal_basis",
        mock.Mock(side_effect=failure),
    )
    emitter = mock.Mock()
    monkeypatch.setattr("football.capital.longitudinal.emit_event", emitter)

    with pytest.raises(RuntimeError, match="controlled basis"):
        recompute_longitudinal_capital(series=series, pipeline_run_id=79)

    series.refresh_from_db()
    assert series.current_snapshot_id is None
    assert CapitalExperiment.objects.filter(pk=produced.capital_experiment_id).exists()
    emitter.assert_called_once()
    assert emitter.call_args.kwargs["pipeline_run_id"] == 79


def test_unexpected_policy_failure_is_persisted_with_one_traceback_owner(monkeypatch):
    _stream([{}], suffix="-policy-failure")
    monkeypatch.setattr(
        "football.capital.service.replay",
        mock.Mock(side_effect=RuntimeError("controlled engine failure")),
    )
    emitter = mock.Mock()
    monkeypatch.setattr("football.capital.longitudinal.emit_event", emitter)

    result = recompute_longitudinal_capital(pipeline_run_id=88)
    snapshot = CapitalExperiment.objects.get(pk=result.capital_experiment_id)

    assert result.status == "PRODUCED"
    assert snapshot.policy_runs.filter(status="FAILED").count() == 7
    assert snapshot.policy_runs.filter(status="UNAVAILABLE").count() == 0
    emitter.assert_called_once()
    event = emitter.call_args.kwargs
    assert event["event_code"] == "CAPITAL_LONGITUDINAL_POLICY_FAILED"
    assert event["exception"].args == ("controlled engine failure",)
    assert event["pipeline_run_id"] == 88


def test_unavailable_policy_arms_are_reusable_and_do_not_retry(monkeypatch):
    same_time = AFTER_EPOCH + timedelta(days=2)
    _stream([{"decision_time": same_time}], suffix="-unavailable-one")
    _stream([{"decision_time": same_time}], suffix="-unavailable-two")
    from football.capital import longitudinal as longitudinal_service

    runner = mock.Mock(wraps=longitudinal_service.run_prepared_capital_experiment)
    monkeypatch.setattr(longitudinal_service, "run_prepared_capital_experiment", runner)
    monkeypatch.setattr(longitudinal_service, "emit_event", mock.Mock())

    first = recompute_longitudinal_capital()
    snapshot = CapitalExperiment.objects.get(pk=first.capital_experiment_id)
    repeated = recompute_longitudinal_capital()

    assert (
        snapshot.policy_runs.filter(
            status=CapitalPolicyRun.STATUS_UNAVAILABLE,
            reason="UNAVAILABLE_CONCURRENT_RECOVERY_STEP",
        ).count()
        == 3
    )
    assert not snapshot.policy_runs.filter(
        status=CapitalPolicyRun.STATUS_FAILED
    ).exists()
    assert repeated.status == "NO_WORK"
    assert repeated.capital_experiment_id == snapshot.pk
    assert runner.call_count == 1
    assert CapitalExperiment.objects.count() == 1


def test_gap_and_no_work_are_not_incidents_and_command_is_db_only(monkeypatch):
    _stream([{"price": None}], suffix="-quiet")
    emitter = mock.Mock()
    monkeypatch.setattr("football.capital.longitudinal.emit_event", emitter)

    unavailable = recompute_longitudinal_capital()
    assert unavailable.status == "UNAVAILABLE"
    assert unavailable.first_gap["reason"] == "MISSING_SELECTED_ODDS_OBSERVATION"
    assert not emitter.called

    # The manual entry point repeats the same DB-only gap result.
    output = StringIO()
    with mock.patch(
        "requests.sessions.Session.request",
        side_effect=AssertionError("provider call"),
    ):
        call_command("recompute_longitudinal_capital", stdout=output)
    payload = json.loads(output.getvalue())
    assert payload["status"] == "UNAVAILABLE"
    assert payload["comparator"] == {
        "source_model_code": "DIXON_COLES",
        "decision_policy_code": "MODAL_ALL",
    }
    assert not emitter.called


def test_pipeline_invokes_one_db_only_longitudinal_attempt(monkeypatch):
    at = AFTER_EPOCH
    monkeypatch.setattr(
        "football.pipeline.service.run_capture",
        lambda **kwargs: CaptureResult(
            run_id=None,
            status="NO_WORK",
            planning_at=kwargs["at"],
            quota_before={},
            quota_after={},
        ),
    )
    service = mock.Mock(
        return_value=LongitudinalResult(status="NO_WORK", reason="UNCHANGED")
    )
    monkeypatch.setattr(
        "football.pipeline.service.recompute_longitudinal_capital", service
    )
    with mock.patch(
        "requests.sessions.Session.request",
        side_effect=AssertionError("provider call"),
    ):
        result = run_pipeline(at=at)

    service.assert_called_once_with(pipeline_run_id=result.run_id)
    assert result.report["capital"]["longitudinal"]["status"] == "NO_WORK"
    assert result.report["capital"]["baseline"]["policy"] == "FLAT_UNIT"
    assert PipelineRun.objects.get(pk=result.run_id).capital_experiment_ids == []


def test_pipeline_does_not_duplicate_capital_primary_failure_event(monkeypatch):
    at = AFTER_EPOCH
    monkeypatch.setattr(
        "football.pipeline.service.run_capture",
        lambda **kwargs: CaptureResult(
            run_id=None,
            status="NO_WORK",
            planning_at=kwargs["at"],
            quota_before={},
            quota_after={},
        ),
    )
    failure = RuntimeError("capital already emitted this cause")
    failure.longitudinal_event_emitted = True
    monkeypatch.setattr(
        "football.pipeline.service.recompute_longitudinal_capital",
        mock.Mock(side_effect=failure),
    )
    terminal = mock.Mock()
    monkeypatch.setattr("football.pipeline.service.emit_pipeline_terminal", terminal)

    result = run_pipeline(at=at)

    assert result.status == PipelineRun.Status.FAILED
    assert result.phases["CAPITAL"]["state"] == "FAILED"
    terminal.assert_called_once()
    assert terminal.call_args.args[0].pk == result.run_id
    assert terminal.call_args.kwargs["causes"] == []
    assert PipelineRun.objects.get(pk=result.run_id).errors == [
        {
            "phase": "CAPITAL",
            "operation": "LONGITUDINAL_RECOMPUTE",
            "error": "RuntimeError:capital already emitted this cause",
        }
    ]


def test_reporting_separates_current_longitudinal_snapshot_and_queries_are_bounded():
    shared_time = AFTER_EPOCH + timedelta(days=1)
    source, _ = _stream(
        [
            {"decision_time": shared_time},
            {"decision_time": shared_time, "outcome": "AWAY"},
        ],
        suffix="-report",
    )
    longitudinal = recompute_longitudinal_capital()
    longitudinal_snapshot = CapitalExperiment.objects.get(
        pk=longitudinal.capital_experiment_id
    )
    legacy = run_capital_experiment(
        prediction_experiment=source,
        source_model_code=Prediction.DIXON_COLES,
        decision_policy_code="MODAL_ALL",
        config={
            "mode": "REPLAY",
            "initial_bankroll": "100",
            "policies": [{"code": "FLAT_UNIT", "config": {"unit": "1"}}],
        },
    )
    with CaptureQueriesContext(connection) as before:
        response = Client().get("/")
    content = response.content.decode()
    assert response.status_code == 200
    assert "Capital longitudinal / evidencia simulada de investigación" in content
    assert "no selecciona una política ganadora" in content
    assert "DIXON_COLES + MODAL_ALL" in content
    assert f"Snapshot #{longitudinal.capital_experiment_id}" in content
    assert longitudinal_snapshot.input_hash in content
    assert longitudinal_snapshot.engine_version in content
    assert f"IDs {longitudinal_snapshot.input_manifest['decision_ids']}" not in content
    assert "provenance temporal persistido" in content
    assert f"CapitalExperiment #{legacy.pk}" in content
    assert "UNAVAILABLE_CONCURRENT_RECOVERY_STEP" in content

    # Superseded history is not rendered and does not add row-driven queries.
    decision = source.decisions.order_by("id").first()
    decision.match.outcome = Match.OUTCOME_AWAY
    decision.match.save(update_fields=["outcome", "modified"])
    replacement = recompute_longitudinal_capital()
    with CaptureQueriesContext(connection) as after:
        updated = Client().get("/")
    updated_content = updated.content.decode()
    assert f"Snapshot #{replacement.capital_experiment_id}" in updated_content
    assert f"Snapshot #{longitudinal.capital_experiment_id}" not in updated_content
    assert len(after) == len(before)


def test_reporting_failed_longitudinal_run_shows_reason_and_neutral_metrics():
    _stream([{}], suffix="-report-failed")
    longitudinal = recompute_longitudinal_capital()
    failed = CapitalPolicyRun.objects.get(
        experiment_id=longitudinal.capital_experiment_id,
        policy_code="FLAT_UNIT",
    )
    failed.ledger_entries.all().delete()
    failed.status = CapitalPolicyRun.STATUS_FAILED
    failed.reason = "CONTROLLED_DIAGNOSTIC"
    failed.metrics = {}
    failed.save(update_fields=["status", "reason", "metrics", "modified"])

    response = Client().get("/")
    content = response.content.decode()
    failed_row = content.split("FLAT_UNIT", 1)[1].split("</tr>", 1)[0]

    assert response.status_code == 200
    assert "Fallido" in failed_row
    assert "FAILED" in failed_row
    assert "CONTROLLED_DIAGNOSTIC" in failed_row
    assert failed_row.count("—") >= 10
