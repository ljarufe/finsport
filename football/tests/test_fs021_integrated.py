"""Bounded synthetic FS-021 oracles; never run the historical tournament."""

import copy
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from football.capital.contracts import StakeRequest
from football.experiments.capital_analysis import (
    calendar_weeks,
    paired_max_t,
    sampled_path,
)
from football.experiments.capital_runner import CANDIDATES
from football.experiments.integrated_analysis import practical_selection
from football.experiments.integrated_events import (
    DepletionGate,
    expand_ledger,
    run_integrated_path,
)
from football.experiments.integrated_runner import (
    existing_scores,
    init_pool,
    read_artifact,
    replicate_scores,
    save_shard,
    store_artifact,
)
from football.tests.test_fs020_capital import AT, candidate, kinds, opp
from tools import fs021_supervisor as monitor


class ScriptPolicy:
    def __init__(self, stakes, terminate=None):
        self.stakes = stakes
        self.terminate = terminate
        self.request = Mock(side_effect=self._request)

    def initial_state(self):
        return {}

    def _request(self, decision, equity, state):
        stake = Decimal(str(self.stakes.get(decision.source_id, 1)))
        if decision.source_id == self.terminate:
            return StakeRequest(
                stake, Decimal(0), termination_reason="SYNTHETIC_POLICY_END"
            )
        return StakeRequest(stake, stake)

    def settle(self, state, request, won):
        return state, None


def script(stakes, lanes=10, terminate=None):
    policy = ScriptPolicy(stakes, terminate)
    return SimpleNamespace(policy=lambda: policy, max_lanes=lanes), policy


def settlement_path(second_wins=True, *, fast=True):
    capital, policy = script({1: 96, 2: 4})
    rows = [
        opp(1, won=False),
        opp(2, minute=10, won=second_wins),
        opp(3, minute=185),
        opp(4, minute=500),
    ]
    result = run_integrated_path(rows, capital, trace=True, fast=fast)
    return rows, result, policy


def test_d01_exact_floor_stops_before_same_wake_request():
    capital, policy = script({1: 95})
    rows = [opp(1, won=False), opp(2, minute=180), opp(3, minute=400, action="NO_BET")]
    result = run_integrated_path(rows, capital, trace=True)
    assert result["metrics"]["bankroll_equity"] == "5"
    assert policy.request.call_count == 1
    # Later unmatched Matches are retained as evidence, but no drawdown time
    # accrues after the last OPEN settlement that triggers terminal depletion.
    assert result["metrics"]["drawdown_duration_seconds"] == 0
    assert (
        result["metrics"]["terminal_at"]
        == (AT + __import__("datetime").timedelta(minutes=150)).isoformat()
    )
    assert [
        r["kind"] for r in expand_ledger(result, rows, result["original_stream_sha256"])
    ][-2:] == ["NOT_EXECUTED_AFTER_OP_DEPLETION", "NO_BET"]


def test_d02_reversible_pause_last_win_resumes():
    _, result, policy = settlement_path()
    transitions = [r for r in result["ledger"] if r["opportunity"] is None]
    assert [(r["kind"], r["equity"]) for r in transitions] == [
        ("AWAITING_FINAL_OPEN_SETTLEMENT", "4"),
        ("ACTIVE", "8"),
    ]
    assert policy.request.call_count == 4
    assert not result["metrics"]["operational_depletion"]


def test_d03_last_loss_then_terminal():
    _, result, policy = settlement_path(False)
    assert result["metrics"]["bankroll_equity"] == "0"
    assert result["metrics"]["operational_depletion"]
    assert result["metrics"]["ever_nonpositive_equity"]
    assert policy.request.call_count == 2


def test_d04_complete_simultaneous_batch_before_gate():
    capital, _ = script({1: 97, 2: 1})
    rows = [
        opp(1, won=False, probability="1"),
        opp(2, price="5", probability="0.1"),
        opp(3, minute=180),
    ]
    result = run_integrated_path(rows, capital, trace=True)
    assert not result["metrics"]["operational_depletion"]
    assert "AWAITING_FINAL_OPEN_SETTLEMENT" not in [r["kind"] for r in result["ledger"]]
    assert [r["equity"] for r in result["ledger"] if r["kind"] == "SETTLEMENT"][:2] == [
        "3",
        "7",
    ]


def test_d05_three_open_sticky_pause_and_fresh_request():
    capital, policy = script({1: 96, 2: 1, 3: 1, 4: 1})
    rows = [
        opp(1, won=False),
        opp(2, minute=10, won=False),
        opp(3, minute=20, price="4"),
        opp(4, minute=30, price="4"),
        opp(5, minute=200),
    ]
    result = run_integrated_path(rows, capital, trace=True)
    transitions = [r for r in result["ledger"] if r["opportunity"] is None]
    assert [(r["kind"], r["equity"]) for r in transitions] == [
        ("AWAITING_FINAL_OPEN_SETTLEMENT", "4"),
        ("ACTIVE", "9"),
    ]
    fifth = [r for r in result["ledger"] if r["opportunity"] == "5"]
    assert fifth[0]["reason"] == "AWAITING_FINAL_OPEN_SETTLEMENT"
    assert next(r for r in fifth if r["kind"] == "POLICY_REQUEST")["equity"] == "9"
    assert policy.request.call_count == 5


def test_d06_two_open_stop_and_pending_terminal_cause():
    capital, policy = script({1: 96, 2: 1, 3: 1})
    rows = [
        opp(1, won=False),
        opp(2, minute=10, won=False),
        opp(3, minute=20),
        opp(4, minute=190),
    ]
    result = run_integrated_path(rows, capital, trace=True)
    assert result["metrics"]["bankroll_equity"] == "4"
    assert kinds(result, 4) == ["PENDING_CAPACITY", "PATH_STOPPED_OP_DEPLETION"]
    assert policy.request.call_count == 3


def test_d07_cash_not_equity():
    capital, policy = script({1: 94, 2: 6})
    rows = [opp(1, won=False), opp(2, minute=10), opp(3, minute=181)]
    result = run_integrated_path(rows, capital, trace=True)
    pending = next(r for r in result["ledger"] if r["kind"] == "PENDING_CAPACITY")
    assert pending["equity"] == "6" and pending["available_cash"] == "0"
    assert not result["metrics"]["operational_depletion"]
    assert policy.request.call_count == 4


def test_d08_lane_first_kelly_without_edge():
    rows = [opp(i, probability="0.55") for i in range(10)] + [
        opp(10, probability="0.1")
    ]
    result = run_integrated_path(rows, CANDIDATES[6], trace=True)
    assert kinds(result, 10) == ["PENDING_CAPACITY", "EXPIRED_CAPACITY"]
    assert result["metrics"]["counts"]["POLICY_REQUEST"] == 10


def test_d09_above_floor_not_depleted():
    capital, _ = script({1: "94.93", 2: 6})
    result = run_integrated_path(
        [opp(1, won=False), opp(2, minute=200)], capital, trace=True
    )
    assert result["metrics"]["bankroll_equity"] == "5.07"
    assert kinds(result, 2) == [
        "POLICY_REQUEST",
        "PENDING_CAPACITY",
        "EXPIRED_CAPACITY",
    ]
    assert not result["metrics"]["operational_depletion"]


def suffix_fixture(fast):
    capital, _ = script({1: 95})
    rows = [opp(1, won=False)]
    rows += [
        opp(i + 2, minute=300 + i, action="BET" if i < 400 else "NO_BET")
        for i in range(600)
    ]
    return rows, run_integrated_path(
        rows, capital, trace=True, fast=fast, original_stream_sha="a" * 64
    )


def test_d10_zero_future_wakes_and_original_suffix_mutation():
    rows, result = suffix_fixture(True)
    assert result["physical_wakes"] == 2
    assert result["metrics"]["counts"]["NOT_EXECUTED_AFTER_OP_DEPLETION"] == 400
    assert result["metrics"]["counts"]["NO_BET"] == 200
    assert len(result["suffix"]["indices"]) == 600
    mutated = list(rows)
    mutated[-1] = replace(mutated[-1], actual_outcome="AWAY")
    with pytest.raises(ValueError, match="ORIGINAL_STREAM_INTEGRITY"):
        expand_ledger(result, mutated, "a" * 64)
    with pytest.raises(ValueError, match="ORIGINAL_STREAM_INTEGRITY"):
        expand_ledger(result, rows, "b" * 64)


def test_d11_scalar_full_scan_equals_fast_stop():
    rows, fast = suffix_fixture(True)
    _, scalar = suffix_fixture(False)
    assert fast["metrics"] == scalar["metrics"]
    assert fast["ledger_hash"] == scalar["ledger_hash"]
    assert expand_ledger(fast, rows, "a" * 64) == expand_ledger(scalar, rows, "a" * 64)
    assert fast["physical_wakes"] < scalar["physical_wakes"]


def test_d12_parallel_split_restart_duplicate_blocks(tmp_path):
    streams = tuple(tuple([opp(1), opp(2, minute=11000, won=False)]) for _ in range(33))
    init_pool(streams)
    tasks = [(1, [0, 0]), (1, [1, 0])]
    serial = [replicate_scores(task) for task in tasks]
    with ProcessPoolExecutor(
        max_workers=2, initializer=init_pool, initargs=(streams,)
    ) as pool:
        parallel = list(pool.map(replicate_scores, tasks))
    assert np.array_equal(serial, parallel)
    spec = dict(
        runner={},
        input=dict(cohort_sha="cohort", stream_sha="stream", calendar_sha="calendar"),
    )
    whole = tmp_path / "whole"
    split = tmp_path / "split"
    save_shard(whole, spec, 1, 0, 2, serial)
    save_shard(split, spec, 1, 0, 1, [serial[0]])
    save_shard(split, spec, 1, 1, 2, [serial[1]])
    a, ai = existing_scores(whole, spec, 1)
    b, bi = existing_scores(split, spec, 1)
    assert ai == bi == {0, 1} and np.array_equal(a[:2], b[:2])
    before = (split / "shards/150-1-00000-00001.npy").read_bytes()
    save_shard(split, spec, 1, 0, 1, [replicate_scores(tasks[0])])
    assert (split / "shards/150-1-00000-00001.npy").read_bytes() == before
    path = sampled_path(streams[0], calendar_weeks(streams[0]), [0, 0], 1)
    assert len({o.identity for o in path}) == len(path)
    altered = split / "shards/150-1-00000-00001.npy"
    altered.write_bytes(before[:-8])
    with pytest.raises(ValueError, match="CORRUPT_CHECKPOINT"):
        existing_scores(split, spec, 1)


def test_d13_adversarial_nonpositive_open_snapshot_veto_persists():
    # Unreachable from cash-conserving positive-stake 100u inputs, but required
    # adversarial state-machine oracle: a recovery must not erase the veto.
    gate = DepletionGate()
    gate.observe_settlement(Decimal("-1"))
    assert gate.evaluate(Decimal("-1"), 1) == "AWAITING_FINAL_OPEN_SETTLEMENT"
    gate.observe_settlement(Decimal("9"))
    assert gate.evaluate(Decimal("9"), 0) == "ACTIVE"
    assert gate.ever_nonpositive_equity


def test_d14_policy_termination_preserves_open_settlement():
    capital, policy = script({1: 1}, terminate=2)
    result = run_integrated_path(
        [opp(1), opp(2, minute=10), opp(3, minute=20)], capital, trace=True
    )
    assert result["metrics"]["policy_termination"] == "SYNTHETIC_POLICY_END"
    assert result["metrics"]["bankroll_equity"] == "101"
    assert not result["metrics"]["operational_depletion"]
    assert kinds(result, 1)[-1] == "SETTLEMENT"
    assert kinds(result, 3) == ["PATH_TERMINATED"]
    assert policy.request.call_count == 2


def test_atomic_readback_corruption_and_incomplete(tmp_path):
    store_artifact(tmp_path, "payload", b"abc", {"run": 1})
    assert read_artifact(tmp_path, "payload", {"run": 1}) == b"abc"
    (tmp_path / "payload").write_bytes(b"def")
    with pytest.raises(ValueError, match="CORRUPT"):
        store_artifact(tmp_path, "payload", b"abc", {"run": 1})
    (tmp_path / "orphan").write_bytes(b"abc")
    with pytest.raises(ValueError, match="INCOMPLETE"):
        store_artifact(tmp_path, "orphan", b"abc", {})


def selection_fixture():
    metric = dict(
        structurally_complete=True,
        input_count=1877,
        ever_nonpositive_equity=False,
        policy_termination="",
        operational_depletion=False,
        placements=38,
        placed_competitions=[1, 2, 3],
        placed_weeks=[1, 2, 3, 4],
        total_return="-0.1",
        maximum_drawdown="0.2",
        peak_reserved_exposure="10",
    )
    return {
        str(lag): [copy.deepcopy(metric) for _ in range(231)] for lag in (120, 130, 150)
    }, [dict(integrated_index=i) for i in range(231)]


def test_selection_diagnostic_is_separate_and_integrity_never_fallback():
    observed, matrix = selection_fixture()
    practical = practical_selection(observed, matrix)
    assert practical["selected"]["integrated_index"] == 0
    assert practical["mode"] == "PRACTICAL_BASELINE_SIMULATION_ONLY"
    assert practical["historical_loss_making"]
    for p in observed["120"]:
        p["operational_depletion"] = True
    diagnostic = practical_selection(observed, matrix)
    assert diagnostic["mode"] == "DIAGNOSTIC_ONLY__NO_NEW_STAKES"
    assert len(diagnostic["ranking"]) == 231
    observed["120"][0]["input_count"] = 1876
    with pytest.raises(ValueError, match="SELECTION_GATE_A"):
        practical_selection(observed, matrix)


def test_exact_zero_se_and_all_pairs_no_tolerance():
    family = paired_max_t([1, 0, 0], np.array([[1, 1, 1], [0, 0, 0], [0, 1e-15, 0]]))
    assert family["status"] == "ESTIMABLE"
    assert family["pairs"][0]["lower"] == family["pairs"][0]["upper"] == 1
    assert family["pairs"][1]["se"] > 0
    assert paired_max_t([1, 0], [[1, 1], [0, 0]])["status"] == "DEGENERATE_ALL_SE_ZERO"


def test_monitor_alarm_ack_does_not_resume_and_no_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor.shutil, "which", lambda _: None)
    monitor.write(tmp_path / "supervisor.json", {"status": "PAUSE_RESOURCE"})
    first = monitor.alarm(tmp_path, "PAUSE_RESOURCE", ["CPU"])
    assert monitor.alarm(tmp_path, "PAUSE_RESOURCE", ["CPU"]) == first
    monitor.ack(tmp_path)
    assert not monitor.sound_pending(tmp_path, tmp_path / "absent.wav")
    assert monitor.read(tmp_path / "supervisor.json")["status"] == "PAUSE_RESOURCE"
    # A later independent incident with the SAME kind/details must rearm
    # after ACK; otherwise an unattended future pause would be silent.
    second = monitor.alarm(tmp_path, "PAUSE_RESOURCE", ["CPU"])
    assert second["incident"] != first["incident"]
    assert monitor.alarm(tmp_path, "PAUSE_RESOURCE", ["CPU"]) == second
    assert monitor.read(tmp_path / "ack.json")["incident"] == first["incident"]
    data = dict(cpu=None, nvme=71, ram_gib=3, free_gib=79, artifact_gib=51)
    assert (
        len(
            monitor.pause_reasons(
                data, dict(cpu=80, nvme=70, ram_gib=4, free_gib=80, artifact_gib=50)
            )
        )
        == 5
    )
    monitor.tone(tmp_path / "sound.wav")
    import wave

    with wave.open(str(tmp_path / "sound.wav")) as stream:
        assert stream.getnframes() / stream.getframerate() == pytest.approx(0.6)


def test_sensors_accept_only_package_and_composite(tmp_path):
    for i, (driver, label, value) in enumerate(
        [
            ("coretemp", "Package id 0", "50000"),
            ("nvme", "Composite", "42000"),
            ("nvme", "Sensor 2", "99000"),
        ]
    ):
        p = tmp_path / f"hwmon{i}"
        p.mkdir()
        (p / "name").write_text(driver)
        (p / "temp1_label").write_text(label)
        (p / "temp1_input").write_text(value)
    values = monitor.sensors(tmp_path)
    assert values["cpu"] == 50 and values["nvme"] == 42


def test_monitor_unexpected_worker_exit_persists_alarm(tmp_path, monkeypatch):
    healthy = dict(cpu=40, nvme=40, ram_gib=10, free_gib=100, artifact_gib=0)
    monkeypatch.setattr(monitor, "resources", lambda _: healthy)
    monkeypatch.setattr(monitor, "sound_pending", lambda *_: False)
    monkeypatch.setattr(monitor.shutil, "which", lambda _: None)
    monkeypatch.setattr(monitor.signal, "signal", lambda *_: None)
    monkeypatch.setattr(
        monitor.subprocess,
        "Popen",
        lambda *_args, **_kwargs: SimpleNamespace(
            pid=123, poll=lambda: 1, returncode=1
        ),
    )
    assert monitor.main([str(tmp_path), "--", "synthetic-worker"]) == 2
    assert monitor.read(tmp_path / "supervisor.json")["status"] == "STOP_TECHNICAL"
    assert monitor.read(tmp_path / "alarm.json")["kind"] == "STOP_TECHNICAL"


def test_monitor_missing_sensor_pauses_before_worker_start(tmp_path, monkeypatch):
    data = dict(cpu=None, nvme=40, ram_gib=10, free_gib=100, artifact_gib=0)
    monkeypatch.setattr(monitor, "resources", lambda _: data)
    monkeypatch.setattr(monitor, "sound_pending", lambda *_: False)
    monkeypatch.setattr(monitor.shutil, "which", lambda _: None)
    monkeypatch.setattr(monitor.signal, "signal", lambda *_: None)
    spawn = Mock(side_effect=AssertionError("MUST_NOT_START"))
    monkeypatch.setattr(monitor.subprocess, "Popen", spawn)
    assert monitor.main([str(tmp_path), "--", "synthetic-worker"]) == 2
    assert not spawn.called
    assert monitor.read(tmp_path / "supervisor.json")["status"] == "PAUSE_RESOURCE"


def test_fs021_freeze_does_not_require_ticket_inside_git(tmp_path, monkeypatch):
    from football.experiments import integrated_inputs as inputs

    for name in (inputs.RESEARCH, inputs.ADDENDUM):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("approved source\n")
    monkeypatch.setattr(inputs, "integrated_runtime", lambda: {"version": "test"})
    spec = inputs.freeze_spec(tmp_path, {"test": "binding"}, tmp_path / "spec.json")
    assert set(spec["sources"]) == {inputs.RESEARCH, inputs.ADDENDUM}
    assert not any("ticket_approved" in name for name in spec["sources"])


def test_worker_checks_resource_pause_between_capital_paths(tmp_path, monkeypatch):
    from football.experiments import integrated_runner as runner

    monkeypatch.setattr(runner, "_POOL_DIRECTORY", tmp_path)
    monkeypatch.setattr(runner, "_POOL_STREAMS", ((),))
    monkeypatch.setattr(runner, "_POOL_WEEKS", ())
    runner.atomic_json(
        tmp_path / "control.json",
        {"time": __import__("time").time(), "pause": True},
    )
    with pytest.raises(runner.ResourcePause, match="WORKER_CONTROL"):
        runner.replicate_scores((1, [0]))


def test_monitor_signal_stops_prelaunch_pause_without_ack(tmp_path, monkeypatch):
    import signal

    handlers = {}
    monkeypatch.setattr(
        monitor.signal, "signal", lambda s, h: handlers.__setitem__(s, h)
    )
    data = dict(cpu=None, nvme=40, ram_gib=10, free_gib=100, artifact_gib=0)
    monkeypatch.setattr(monitor, "resources", lambda _: data)
    monkeypatch.setattr(monitor, "sound_pending", lambda *_: True)
    monkeypatch.setattr(monitor.shutil, "which", lambda _: None)
    monkeypatch.setattr(
        monitor.time, "sleep", lambda _: handlers[signal.SIGTERM](signal.SIGTERM)
    )
    assert monitor.main([str(tmp_path), "--", "synthetic-worker"]) == 143
    assert monitor.read(tmp_path / "supervisor.json")["status"] == "PAUSE_RESOURCE"


def test_audio_failure_diagnostic_is_once_per_incident(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor.shutil, "which", lambda _: None)

    def no_audio(_path, failures=None):
        failures.append({"player": "paplay", "error": "synthetic-no-audio"})
        return False

    monkeypatch.setattr(monitor, "play", no_audio)
    first = monitor.alarm(tmp_path, "PAUSE_RESOURCE", ["CPU"])
    assert monitor.sound_pending(tmp_path, tmp_path / "sound.wav")
    assert monitor.sound_pending(tmp_path, tmp_path / "sound.wav")
    assert (
        monitor.read(tmp_path / "audio_failure.json")["incident"] == first["incident"]
    )
    entries = (tmp_path / "supervisor.jsonl").read_text().splitlines()
    assert sum('"kind": "AUDIO_UNAVAILABLE"' in entry for entry in entries) == 1
    monitor.ack(tmp_path)
    assert not monitor.sound_pending(tmp_path, tmp_path / "sound.wav")


def test_canonical_26565_pair_family():
    observed = np.arange(231, dtype=float)
    scores = np.repeat(observed[:, None], 4, axis=1)
    scores[-1, -1] += 0.1
    family = paired_max_t(observed, scores)
    assert len(family["pairs"]) == 26565
    assert all(p["i"] < p["j"] for p in family["pairs"])
    assert family["status"] == "ESTIMABLE"


@pytest.mark.parametrize(
    "field,value,lag",
    [
        ("total_return", "0", "150"),
        ("maximum_drawdown", "0.3", "130"),
        ("placements", 39, "120"),
        ("peak_reserved_exposure", "9", "120"),
    ],
)
def test_selection_ties_apply_in_frozen_order(field, value, lag):
    observed, matrix = selection_fixture()
    if field == "maximum_drawdown":
        observed[lag][0][field] = value
        expected = 1
    elif field in {"placements", "peak_reserved_exposure"}:
        for cell in observed.values():
            cell[1][field] = value
        expected = 1
    else:
        observed[lag][1][field] = value
        expected = 1
    assert (
        practical_selection(observed, matrix)["selected"]["integrated_index"]
        == expected
    )


def test_research_can_be_edited_after_spec_without_hash_fail(tmp_path, monkeypatch):
    from football.experiments import integrated_inputs as inputs

    monkeypatch.setattr(inputs, "integrated_runtime", lambda: {"version": "test"})
    first = inputs.freeze_spec(tmp_path, {"synthetic": True}, tmp_path / "first.json")
    for name in (inputs.RESEARCH, inputs.ADDENDUM):
        source = tmp_path / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("maintainer-edited\n")
    second = inputs.freeze_spec(tmp_path, {"synthetic": True}, tmp_path / "second.json")
    assert first == second
    assert first["sources"] == [inputs.RESEARCH, inputs.ADDENDUM]
    assert "code_hash" not in first["runner"]


def test_incomplete_publication_never_computes(tmp_path, monkeypatch):
    from football.experiments import integrated_artifacts as artifacts
    from football.experiments import integrated_events

    replay = Mock(side_effect=AssertionError("PUBLISH_MUST_NOT_REPLAY"))
    monkeypatch.setattr(integrated_events, "run_integrated_path", replay)
    spec = dict(runner={}, input=dict(cohort_sha="c", stream_sha="s", calendar_sha="w"))
    with pytest.raises(FileNotFoundError):
        artifacts.verify_existing(tmp_path, spec, ())
    assert not replay.called


def test_publication_writer_is_deterministic_idempotent_and_conflict_closed(
    tmp_path, monkeypatch
):
    from football.experiments import integrated_artifacts as artifacts
    from football.experiments.storage import atomic_json

    directory = tmp_path / "execution"
    directory.mkdir()
    spec = dict(
        sources={},
        runner=dict(fs021_sources={}),
        input=dict(
            candidates=[dict(integrated_index=i) for i in range(231)],
            profile="SYNTHETIC_TEST_ONLY",
            cohort_sha="c",
            stream_sha="s",
            calendar_sha="w",
        ),
    )
    selected = dict(
        mode="DIAGNOSTIC_ONLY__NO_NEW_STAKES",
        selected=dict(integrated_index=0),
        historical_loss_making=True,
        ranking=[],
    )
    run = dict(
        practical_selection=selected,
        scientific_evidence=dict(
            observed_leader=0, disposition="INSUFFICIENT_EVIDENCE"
        ),
        activation=dict(automatic_operational_routing=False, real_betting=False),
    )
    for name, value in [
        ("spec.json", spec),
        ("run.json", run),
        ("gates.json", {}),
        ("restore.json", {}),
    ]:
        atomic_json(directory / name, value)
    monkeypatch.setattr(artifacts, "verify_existing", lambda *_: (run, {}))
    first = artifacts.publish_existing(directory, spec, (), tmp_path)
    second = artifacts.publish_existing(directory, spec, (), tmp_path)
    assert first == second
    published_root = directory / "original_publication_v1"
    authority = published_root / "FS-021_global_strategy_v1.json"
    index = tmp_path / "docs/experiments/FS-021/execution/original_v1.json"
    assert authority.is_file() and index.is_file()
    assert not (tmp_path / "docs/research/FS-021_global_strategy_v1.json").exists()
    before = authority.read_bytes()
    artifacts.publish_existing(directory, spec, (), tmp_path)
    assert authority.read_bytes() == before
    authority.write_text("conflict")
    with pytest.raises(ValueError, match="ORIGINAL_PUBLICATION_CONFLICT"):
        artifacts.publish_existing(directory, spec, (), tmp_path)


def test_duplicate_blocks_keep_full_fast_logical_hash_and_fresh_state():
    rows = [opp(1, won=False), opp(2, minute=11000, action="NO_BET")]
    replay = sampled_path(rows, calendar_weeks(rows), [0, 0], 1)
    capital = candidate(config={"unit": "95"})
    a = run_integrated_path(replay, capital, trace=True)
    b = run_integrated_path(replay, capital, trace=True, fast=False)
    assert a["metrics"] == b["metrics"]
    assert a["ledger_hash"] == b["ledger_hash"]
    assert a == run_integrated_path(replay, capital, trace=True)
    assert a["metrics"] == run_integrated_path(replay, capital)["metrics"]
