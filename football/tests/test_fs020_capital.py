"""Synthetic E2.4 conformance: no real corpus election, DB or providers."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock

import numpy as np
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from football.capital.policies import make_policy
from football.experiments import capital_runner as runner
from football.experiments.capital_analysis import (
    array_hash,
    block_draws,
    bootstrap_scores,
    calendar_weeks,
    finalize_lags,
    interval,
    paired_max_t,
    sampled_path,
    stability_checks,
    within_lag,
)
from football.experiments.capital_events import (
    Opportunity,
    run_event_path,
)
from football.experiments.storage import canonical

AT = datetime(2026, 1, 12, 20, tzinfo=timezone.utc)


def opp(
    i, *, minute=0, probability="0.6", price="2", won=True, action="BET", competition=1
):
    kickoff = AT + timedelta(minutes=minute)
    return Opportunity(
        str(i),
        i,
        competition,
        kickoff,
        kickoff - timedelta(minutes=30),
        action,
        "HOME" if action == "BET" else None,
        "HOME" if won else "AWAY",
        Decimal(price) if action == "BET" else None,
        Decimal(probability) if action == "BET" else None,
    )


def candidate(index=0, *, config=None, lanes=None):
    c = runner.CANDIDATES[index]
    return replace(
        c,
        config_json=canonical(config) if config else c.config_json,
        max_lanes=lanes if lanes is not None else c.max_lanes,
    )


def kinds(result, key):
    return [row["kind"] for row in result["ledger"] if row["opportunity"] == str(key)]


def test_seven_frozen_current_candidates():
    assert len(runner.CANDIDATES) == 7
    assert [c.max_lanes for c in runner.CANDIDATES] == [10, 10, 10, 1, 1, 1, 10]
    for c in runner.CANDIDATES:
        assert c.policy().version == c.version
    assert runner.CANDIDATES[-1].data()["config"] == {"lambda": "0.25"}


@pytest.mark.parametrize("index", range(7))
def test_policy_request_receives_bet_only_for_available_lanes(monkeypatch, index):
    capital = candidate(index)
    policy = capital.policy()
    policy.request = Mock(wraps=policy.request)
    monkeypatch.setattr(
        "football.experiments.capital_events.make_policy", lambda *_: policy
    )
    rows = [opp(0, action="NO_BET")]
    rows += [opp(i) for i in range(1, capital.max_lanes + 1)]
    blocked = capital.max_lanes + 1
    rows.append(opp(blocked, probability="0.51"))

    result = run_event_path(rows, capital, trace=True)

    assert policy.request.call_count == capital.max_lanes
    decisions = [call.args[0] for call in policy.request.call_args_list]
    assert {decision.source_id for decision in decisions} == set(
        range(1, capital.max_lanes + 1)
    )
    assert all(decision.action == "BET" for decision in decisions)
    assert all(decision.outcome == "" for decision in decisions)
    assert kinds(result, 0) == ["NO_BET"]
    assert kinds(result, blocked) == ["PENDING_CAPACITY", "EXPIRED_CAPACITY"]
    settlements = [row for row in result["ledger"] if row["kind"] == "SETTLEMENT"]
    assert len(settlements) == capital.max_lanes
    assert all(row["won"] for row in settlements)


@pytest.mark.parametrize("zero", [False, True])
def test_c01_c02_c04_full_lanes_never_request_and_expire(monkeypatch, zero):
    policy = make_policy("FRACTIONAL_KELLY", {"lambda": "0.25"})
    original = policy.request
    policy.request = Mock(wraps=original)
    monkeypatch.setattr(
        "football.experiments.capital_events.make_policy", lambda *_: policy
    )
    rows = [opp(i, probability="0.55") for i in range(1, 11)]
    rows += [opp(11, probability="0.1" if zero else "0.51")]
    result = run_event_path(rows, candidate(6), trace=True)
    assert policy.request.call_count == 10
    assert kinds(result, 11) == ["PENDING_CAPACITY", "EXPIRED_CAPACITY"]
    assert result["metrics"]["hard_risk"] == "PASS"


def test_c03_retry_kelly_zero_only_after_lane_release():
    rows = [opp(i, probability="0.55") for i in range(1, 11)]
    rows += [opp(11, minute=160, probability="0.1")]
    result = run_event_path(rows, candidate(6), trace=True)
    assert kinds(result, 11) == [
        "PENDING_CAPACITY",
        "PENDING_RETRY",
        "POLICY_REQUEST",
        "ZERO_STAKE",
    ]
    assert result["metrics"]["placements"] == 10
    assert result["metrics"]["hard_risk"] == "PASS"


def test_c05_c06_cash_retry_recomputes_equity():
    c = candidate(1, config={"fraction": "0.6"})
    rows = [opp(1), opp(2, minute=160)]
    result = run_event_path(rows, c, trace=True)
    attempts = [
        r
        for r in result["ledger"]
        if r["kind"] == "POLICY_REQUEST" and r["opportunity"] == "2"
    ]
    assert [Decimal(r["request"]["requested"]) for r in attempts] == [
        Decimal("60"),
        Decimal("96"),
    ]
    assert kinds(result, 2) == [
        "POLICY_REQUEST",
        "PENDING_CAPACITY",
        "PENDING_RETRY",
        "POLICY_REQUEST",
        "PLACEMENT",
        "SETTLEMENT",
    ]
    for row in result["ledger"]:
        assert Decimal(row["available_cash"]) == Decimal(row["equity"]) - Decimal(
            row["reserved"]
        )


def test_c07_settle_state_release_retry_then_fresh_order():
    result = run_event_path(
        [opp(1, won=False), opp(2, minute=160), opp(3, minute=180)],
        candidate(3),
        trace=True,
    )
    same = [
        r
        for r in result["ledger"]
        if r["at"] == (AT + timedelta(minutes=150)).isoformat()
    ]
    assert [r["kind"] for r in same][:4] == [
        "SETTLEMENT",
        "PENDING_RETRY",
        "POLICY_REQUEST",
        "PLACEMENT",
    ]
    request = same[2]
    assert request["policy_state"]["accumulated_loss"] == "1"
    assert request["request"]["requested"] == "2"


@pytest.mark.parametrize("minute", [0, 1])
def test_c08_no_request_at_or_after_kickoff(minute):
    row = replace(opp(1), execution_at=AT + timedelta(minutes=minute))
    result = run_event_path([row], candidate(), trace=True)
    assert kinds(result, 1) == ["EXPIRED_CAPACITY"]


def test_c09_no_bet_and_available_zero_stake():
    result = run_event_path(
        [opp(1, action="NO_BET"), opp(2, probability="0.5")], candidate(6), trace=True
    )
    assert kinds(result, 1) == ["NO_BET"]
    assert kinds(result, 2) == ["POLICY_REQUEST", "ZERO_STAKE"]
    assert result["metrics"]["bankroll_equity"] == "100"


def test_c10_explicit_policy_termination_and_cap_is_not_ruin():
    rows = [opp(1, won=False), opp(2, minute=180), opp(3, minute=181)]
    result = run_event_path(
        rows,
        candidate(4, config={"initial_stake": "1", "max_recovery_steps": 1}),
        trace=True,
    )
    assert result["metrics"]["termination_reason"] == "MAX_RECOVERY_STEPS"
    assert result["metrics"]["hard_risk"] == "FAIL"
    assert kinds(result, 2) == ["POLICY_REQUEST", "POLICY_TERMINATION"]
    assert kinds(result, 3) == ["PATH_TERMINATED"]
    cap = run_event_path(
        [opp(1, won=False), opp(2, minute=180, price="1.1")], candidate(4)
    )
    assert cap["metrics"]["counts"]["CAP_HIT"] == 1
    assert cap["metrics"]["hard_risk"] == "PASS"


def test_c11_ev_kickoff_stable_identity_ranking():
    rows = [opp(9), opp(2), opp(1, probability="0.8")]
    result = run_event_path(rows[::-1], candidate(lanes=1), trace=True)
    assert (
        next(r["opportunity"] for r in result["ledger"] if r["kind"] == "PLACEMENT")
        == "1"
    )
    tie = run_event_path([opp(9), opp(2)], candidate(lanes=1), trace=True)
    assert tie["ledger"][0]["opportunity"] == "2"
    assert result == run_event_path(rows, candidate(lanes=1), trace=True)


@pytest.mark.parametrize("lag", [120, 130, 150])
def test_scalar_hand_calculated_ledger(lag):
    result = run_event_path(
        [opp(1), opp(2, minute=200, won=False)], candidate(3), lag, trace=True
    )
    assert result["metrics"]["bankroll_equity"] == "100"
    assert result["metrics"]["total_staked"] == "2"
    assert result["metrics"]["policy_state"]["accumulated_loss"] == "1"
    assert [r["kind"] for r in result["ledger"]] == [
        "POLICY_REQUEST",
        "PLACEMENT",
        "SETTLEMENT",
    ] * 2
    assert result["ledger"][2]["at"] == (AT + timedelta(minutes=lag)).isoformat()


def test_calendar_keeps_empty_weeks_and_membership_is_execution():
    rows = [opp(1), opp(2, minute=35 * 7 * 24 * 60)]
    weeks = calendar_weeks(rows)
    assert len(weeks) == 36
    for length in (1, 2, 4):
        draws = block_draws(36, length)
        expected = np.random.Generator(
            np.random.PCG64(np.random.SeedSequence([21092026, length]))
        ).integers(
            0, 36 - length + 1, size=(5000, (36 + length - 1) // length), dtype=np.int64
        )
        assert np.array_equal(draws, expected)
        assert np.array_equal(draws, block_draws(36, length))
        assert draws.min() >= 0 and draws.max() <= 36 - length
        manifest = runner.rng_manifest()[str(length)]
        assert manifest["sha256"] == array_hash(draws)
        assert manifest["reference_sha256"] == runner.REFERENCE_RNG_HASHES[str(length)]
        assert (
            manifest["reference_equivalence"] == "PENDING_ORIGINAL_ENCODING_OR_MANIFEST"
        )
    sunday_execution = replace(
        opp(3),
        kickoff=datetime(2026, 1, 19, 5, 10, tzinfo=timezone.utc),
        execution_at=datetime(2026, 1, 19, 4, 40, tzinfo=timezone.utc),
    )
    assert calendar_weeks([sunday_execution])[0].date().isoformat() == "2026-01-12"


def synthetic_weeks():
    return [
        opp(i + 1, minute=i * 7 * 24 * 60, won=i % 2 == 0, competition=1 + i % 2)
        for i in range(4)
    ]


def test_sampled_blocks_carry_state_and_duplicate_identity():
    rows = synthetic_weeks()
    weeks = calendar_weeks(rows)
    replay = sampled_path(rows, weeks, [1, 1, 1, 1], 1)
    assert len({o.identity for o in replay}) == 4
    assert {o.source_id for o in replay} == {2}
    result = run_event_path(replay, candidate(3))
    assert Decimal(result["metrics"]["bankroll_equity"]) == 85
    assert Decimal(result["metrics"]["policy_state"]["accumulated_loss"]) == 15


def test_c12_full_shards_restart_exact():
    rows = synthetic_weeks()
    full = bootstrap_scores(rows, runner.CANDIDATES, 150, 2, 0, 8, replicates=8)
    a = bootstrap_scores(rows, runner.CANDIDATES, 150, 2, 0, 3, replicates=8)
    b = bootstrap_scores(rows, runner.CANDIDATES, 150, 2, 3, 8, replicates=8)
    assert np.array_equal(full, np.concatenate((a, b), axis=1))
    assert np.array_equal(
        b, bootstrap_scores(rows, runner.CANDIDATES, 150, 2, 3, 8, replicates=8)
    )


def test_max_t_matches_manual_calculation_and_reversal():
    observed = [0.1, 0.3, -0.1]
    scores = np.array([[0, 0.2, 0.4, 0.1], [0.1, 0.1, 0.3, 0.4], [0, 0, 0, 0]])
    family = paired_max_t(observed, scores)
    maxima = []
    for b in range(4):
        maxima.append(
            max(
                abs((scores[i, b] - scores[j, b]) - (observed[i] - observed[j]))
                / np.std(scores[i] - scores[j], ddof=1)
                for i, j in [(0, 1), (0, 2), (1, 2)]
            )
        )
    assert family["q95"] == np.quantile(maxima, 0.95, method="linear")
    lower, upper = interval(family, 0, 1)
    assert interval(family, 1, 0) == (-upper, -lower)


def test_zero_se_point_observed_center_and_degenerate_family():
    family = paired_max_t([3, 1, 0], [[2, 2, 2], [2, 2, 2], [0, 1, 2]])
    assert family["status"] == "ESTIMABLE"
    assert interval(family, 0, 1) == (2, 2)
    assert interval(family, 1, 0) == (-2, -2)
    assert family["pairs"][0]["deterministic_se_zero"] is True
    degenerate = paired_max_t(range(7), np.zeros((7, 5)))
    assert len(degenerate["pairs"]) == 21
    assert degenerate["status"] == "DEGENERATE_ALL_SE_ZERO"
    assert degenerate["q95"] == 0


def test_stability_reruns_fresh_halves_and_loo():
    result = stability_checks(synthetic_weeks(), runner.CANDIDATES, 150, 0, 3)
    assert len(result["slices"]) == 4
    assert [s["count"] for s in result["slices"]] == [2, 2, 2, 2]
    assert result["top"] == 0 and result["runner_up"] == 3
    assert [
        [Decimal(score) for score in row["scores"]] for row in result["slices"]
    ] == [
        [Decimal("0"), Decimal("0")],
        [Decimal("0"), Decimal("0")],
        [Decimal("-0.02"), Decimal("-0.03")],
        [Decimal("0.02"), Decimal("0.02")],
    ]


def lag_fixture(*, top=0, stability="PASS", degenerate=False, risk="PASS", strict=True):
    metrics = [
        dict(
            total_return=str(1 if i == top else 0),
            structurally_complete=True,
            hard_risk=risk if i == top else "PASS",
        )
        for i in range(7)
    ]
    family = paired_max_t(
        [float(m["total_return"]) for m in metrics], np.arange(35).reshape(7, 5) * 0.01
    )
    family["status"] = "DEGENERATE_ALL_SE_ZERO" if degenerate else "ESTIMABLE"
    for p in family["pairs"]:
        p["lower"], p["upper"] = (p["delta"], p["delta"]) if strict else (-2, 2)
    return within_lag(
        runner.CANDIDATES,
        metrics,
        {str(length): family for length in (1, 2, 4)},
        {"status": stability},
    )


def test_disposition_precedence_risk_and_fallback():
    assert lag_fixture()["disposition"] == "CLEAR_SUPERIORITY"
    assert lag_fixture(risk="FAIL")["promotion"] == "NO_PROMOTION_RISK_GATE"
    assert lag_fixture(stability="UNSTABLE")["promotion"] == "NO_PROMOTION"
    assert (
        lag_fixture(stability="UNSTABLE", degenerate=True)["disposition"]
        == "INSUFFICIENT_EVIDENCE"
    )
    assert lag_fixture(strict=False, top=1)["promotion"] == "PROMOTE:FLAT_UNIT"
    assert (
        lag_fixture(strict=True, top=1, stability="NON_STRICT")["fallback"]
        == "NO_PROMOTION"
    )
    assert lag_fixture(strict=False, risk="FAIL")["fallback"] == "NO_PROMOTION"


def test_exact_cross_lag_signatures_and_precedence():
    local = lag_fixture()
    final = finalize_lags({str(lag): local for lag in (120, 130, 150)})
    assert final["selected"] == "FLAT_UNIT"
    assert final["signatures"]["150"] == [
        "FLAT_UNIT",
        "CLEAR_SUPERIORITY",
        "PROMOTE:FLAT_UNIT",
        "PASS",
        "PASS",
        "PASS",
        "NOT_APPLICABLE",
    ]
    assert (
        finalize_lags({"120": lag_fixture(top=1), "130": local, "150": local})[
            "disposition"
        ]
        == "UNSTABLE"
    )
    assert (
        finalize_lags(
            {
                "120": lag_fixture(degenerate=True),
                "130": lag_fixture(top=1),
                "150": local,
            }
        )["disposition"]
        == "INSUFFICIENT_EVIDENCE"
    )
    unstable = lag_fixture(stability="UNSTABLE")
    final = finalize_lags({str(lag): unstable for lag in (120, 130, 150)})
    assert final["settlement_time_stability"] == "PASS"
    assert final["disposition"] == "UNSTABLE"


def test_binding_uses_existing_resolver_and_fails_closed(monkeypatch, tmp_path):
    resolver = Mock(side_effect=ValueError("tampered"))
    monkeypatch.setattr(runner, "resolve_global_decision", resolver)
    with pytest.raises(ValueError, match="INPUT_INTEGRITY_FAIL:tampered"):
        runner.source_binding(base=tmp_path)
    resolver.assert_called_once_with(base=tmp_path)


def test_manual_command_guard_and_no_automatic_election(
    settings, monkeypatch, tmp_path
):
    settings.FOOTBALL_PIPELINE_ENABLED = False
    settings.FOOTBALL_CAPTURE_ENABLED = False
    settings.TIME_ZONE = "America/Lima"
    settings.CELERY_TASK_DEFAULT_QUEUE = "finsport.local.safe"
    monkeypatch.setenv("FINSPORT_EXPERIMENT_RUNTIME", "finsport-dev")
    spec_path = str(tmp_path / "FS-020_experiments/s.json")
    for mode in ("freeze", "run"):
        with pytest.raises(CommandError, match="USE_PUBLISH_EXISTING"):
            call_command(
                "run_capital_experiment",
                spec=spec_path,
                workspace_root=str(tmp_path),
                promote=True,
                **{mode: True},
            )
    with pytest.raises(CommandError, match="INVALID_CAPITAL_EXECUTION_ID"):
        call_command(
            "run_capital_experiment",
            spec=spec_path,
            workspace_root=str(tmp_path),
            publish_existing="../../operational",
        )
    monkeypatch.delenv("FINSPORT_EXPERIMENT_RUNTIME")
    with pytest.raises(CommandError, match="RESEARCH_REQUIRES"):
        call_command("run_capital_experiment", spec="none", run=True)


def test_shard_cache_tamper_and_ordered_reduction(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "REPLICATES", 8)
    score = Mock(
        side_effect=lambda rows, candidates, lag, length, start, stop: np.tile(
            np.arange(start, stop), (7, 1)
        )
    )
    monkeypatch.setattr(runner, "bootstrap_scores", score)
    a = runner.execute_shard([], "x", tmp_path, 150, 2, 0, 3)
    b = runner.execute_shard([], "x", tmp_path, 150, 2, 3, 8)
    assert runner.execute_shard([], "x", tmp_path, 150, 2, 0, 3) == a
    assert score.call_count == 2
    recomputed = runner.execute_shard([], "x", tmp_path / "restart", 150, 2, 3, 8)
    assert recomputed == b
    assert np.array_equal(
        runner.reduce_shards([b, a], "x", 150, 2), np.tile(np.arange(8), (7, 1))
    )
    with pytest.raises(ValueError, match="INCOMPLETE"):
        runner.reduce_shards([a], "x", 150, 2)
    b["scores"][0][0] = 99
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        runner.reduce_shards([a, b], "x", 150, 2)


@pytest.mark.parametrize("index", range(7))
def test_current_policy_arithmetic_for_independent_settlements(index):
    c = candidate(index)
    policy = c.policy()
    state = policy.initial_state()
    equity = Decimal("100")
    rows = [
        opp(i + 1, minute=i * 240, price="2.35", probability="0.65", won=i % 3 == 0)
        for i in range(9)
    ]
    from football.capital.contracts import CapitalDecision

    expected_requests = []
    for row in rows:
        request = policy.request(
            CapitalDecision(
                row.source_id,
                row.execution_at,
                row.action,
                "",
                row.price,
                row.probability,
            ),
            equity,
            state,
        )
        if request.requested > equity:
            continue
        expected_requests.append(request)
        won = row.actual_outcome == row.selected_outcome
        equity += request.applied * (row.price - 1) if won else -request.applied
        state, _ = policy.settle(state, request, won)
    result = run_event_path(rows, c, trace=True)
    assert Decimal(result["metrics"]["bankroll_equity"]) == equity
    placements = [r for r in result["ledger"] if r["kind"] == "PLACEMENT"]
    assert [Decimal(r["request"]["applied"]) for r in placements] == [
        r.applied for r in expected_requests
    ]


def test_ruin_veto_is_not_capacity_veto():
    result = run_event_path(
        [opp(1, won=False), opp(2, minute=160)],
        candidate(config={"unit": "100"}),
        trace=True,
    )
    assert result["metrics"]["economic_ruin"] is True
    assert result["metrics"]["termination_reason"] == "BANKROLL_DEPLETED"
    assert result["metrics"]["hard_risk"] == "FAIL"
    assert kinds(result, 2)[-1] == "PATH_TERMINATED"
    blocked = run_event_path([opp(1)], candidate(config={"unit": "101"}))
    assert blocked["metrics"]["hard_risk"] == "PASS"
    assert blocked["metrics"]["outcomes"] == {"EXPIRED_CAPACITY": 1}


def test_strict_bound_zero_fails():
    local = lag_fixture(top=1)
    for family in local["families"].values():
        pair = next(p for p in family["pairs"] if (p["i"], p["j"]) == (0, 1))
        pair["upper"] = 0.0
    metrics = [local["observed"][c.code] for c in runner.CANDIDATES]
    result = within_lag(
        runner.CANDIDATES, metrics, local["families"], {"status": "PASS"}
    )
    assert result["disposition"] == "NO_CLEAR_SUPERIORITY"
    assert result["fallback"] == "FLAT_UNIT"


@pytest.mark.parametrize("field", range(7))
def test_every_signature_field_affects_cross_lag(field):
    import copy

    primary = lag_fixture(top=1)
    other = copy.deepcopy(primary)
    if field == 0:
        other["observed_leader"] = "LEGACY_CAPPED"
    elif field == 1:
        other["disposition"] = "NO_CLEAR_SUPERIORITY"
    elif field == 2:
        other["promotion"] = "NO_PROMOTION"
    elif field in (3, 4):
        other["hard_risk"]["FIXED_FRACTION_BANKROLL"] = "FAIL"
    elif field == 5:
        other["hard_risk"]["FLAT_UNIT"] = "FAIL"
    else:
        other["fallback"] = "NO_PROMOTION"
    result = finalize_lags({"120": other, "130": primary, "150": primary})
    assert result["disposition"] == "UNSTABLE"
    assert result["selected"] is None


@pytest.fixture
def isolated_lab(monkeypatch, settings, tmp_path):
    import hashlib

    settings.BASE_DIR = tmp_path
    settings.FOOTBALL_PIPELINE_ENABLED = False
    settings.FOOTBALL_CAPTURE_ENABLED = False
    settings.TIME_ZONE = "America/Lima"
    settings.CELERY_TASK_DEFAULT_QUEUE = "finsport.local.safe"
    monkeypatch.setenv("FINSPORT_EXPERIMENT_RUNTIME", "finsport-dev")
    research = tmp_path / runner.RESEARCH_REF
    research.parent.mkdir(parents=True)
    research.write_text("Synthetic test authority, not real research.")
    binding = dict(
        authority={},
        authority_hash=runner.identity({}),
        stream_semantic_sha256=runner.SEMANTIC_SHA,
        stream_gzip_sha256=runner.GZIP_SHA,
        row_count=1906,
        cohort_hash="a" * 64,
        calendar={},
    )
    rows = synthetic_weeks()
    monkeypatch.setattr(runner, "source_binding", lambda **kwargs: (rows, binding))
    spec = runner.CapitalSpec(
        canonical(
            dict(
                runner.CONTRACT,
                input=binding,
                candidate_matrix_id=runner.identity(runner.CONTRACT["candidates"]),
                rng_manifest=runner.rng_manifest(),
                research_sha256=hashlib.sha256(research.read_bytes()).hexdigest(),
            )
        )
    )
    return spec, rows, tmp_path


def test_spec_immutable_and_runtime_identity_includes_capital(isolated_lab):
    spec, _, base = isolated_lab
    path = base / "spec.json"
    spec.save(path)
    spec.save(path)
    assert runner.CapitalSpec.load(path) == spec
    bad = spec.data
    bad["candidates"][0]["max_lanes"] = 11
    with pytest.raises(ValueError, match="METHODOLOGY"):
        runner.CapitalSpec(canonical(bad))
    runtime = runner.capital_runtime()
    assert len(runtime["code_hash"]) == 64
    assert runtime["decimal"]["prec"] > 0


def test_synthetic_orchestration_restart_artifacts_publication(
    isolated_lab, monkeypatch
):
    from football.experiments import capital_artifacts

    spec, _, base = isolated_lab
    # Bound the orchestration fixture to eight synthetic replicates. Production
    # command/spec expose no replicate-count override.
    monkeypatch.setattr(runner, "REPLICATES", 8)
    actual_bootstrap = bootstrap_scores
    monkeypatch.setattr(
        runner,
        "bootstrap_scores",
        lambda rows, candidates, lag, length, start, stop: actual_bootstrap(
            rows, candidates, lag, length, start, stop, replicates=8
        ),
    )
    result = runner.run_capital_experiment(spec, base=base, workspace_root=base / "tmp")
    assert (
        runner.run_capital_experiment(spec, base=base, workspace_root=base / "tmp")
        == result
    )
    assert set(result["lags"]) == {"120", "130", "150"}
    assert all("error" not in lag for lag in result["lags"].values())
    assert len(result["artifacts"]) == 12
    record = capital_artifacts.publish_capital(
        result, base=base, workspace_root=base / "tmp"
    )
    assert record["promotion"] == "PROMOTE"
    assert record["selected"] == record["publication_selection"]["selected"]
    assert record["disposition"] == result["summary"]["disposition"]
    assert record["scientific_run_summary"] == result["summary"]
    assert record == capital_artifacts.publish_capital(
        result, base=base, workspace_root=base / "tmp"
    )
    assert (base / capital_artifacts.AUTHORITY_REF).exists()

    # Publication must address the ORIGINAL execution ID after CLI/publisher
    # code changes. A publication never enters the expensive --run path.
    from io import StringIO

    from football.management.commands import run_capital_experiment as cli

    spec_path = runner.capital_root(base / "tmp") / "spec.json"
    spec.save(spec_path)
    original_directory = runner.capital_root(base / "tmp") / result["execution_id"]
    run_before = (original_directory / "run.json").read_bytes()
    shard_files_before = sorted((original_directory / "shards").glob("*.json"))
    authority_before = (base / capital_artifacts.AUTHORITY_REF).read_bytes()
    report_before = (base / capital_artifacts.REPORT_REF).read_bytes()
    with monkeypatch.context() as mp:
        changed_runtime = dict(runner.capital_runtime(), code_hash="f" * 64)
        mp.setattr(runner, "capital_runtime", lambda: changed_runtime)
        forbidden_rerun = Mock(side_effect=AssertionError("UNEXPECTED_ECONOMIC_RERUN"))
        mp.setattr(cli, "run_capital_experiment", forbidden_rerun)
        for _ in range(2):
            output = StringIO()
            call_command(
                "run_capital_experiment",
                spec=str(spec_path),
                workspace_root=str(base / "tmp"),
                publish_existing=result["execution_id"],
                stdout=output,
            )
            assert '"status":"PUBLISHED_EXISTING"' in output.getvalue()
            assert '"selected":"' + record["selected"] + '"' in output.getvalue()
        forbidden_rerun.assert_not_called()
    assert (original_directory / "run.json").read_bytes() == run_before
    assert sorted((original_directory / "shards").glob("*.json")) == shard_files_before
    assert (base / capital_artifacts.AUTHORITY_REF).read_bytes() == authority_before
    assert (base / capital_artifacts.REPORT_REF).read_bytes() == report_before

    (base / capital_artifacts.REPORT_REF).write_text("conflicting report")
    with pytest.raises(ValueError, match="ALREADY_FROZEN"):
        capital_artifacts.publish_capital(
            result, base=base, workspace_root=base / "tmp"
        )
    with pytest.raises(CommandError, match="ALREADY_FROZEN"):
        call_command(
            "run_capital_experiment",
            spec=str(spec_path),
            workspace_root=str(base / "tmp"),
            publish_existing=result["execution_id"],
        )
    _, _, _, directory = runner.execution_context(
        spec, base=base, workspace_root=base / "tmp"
    )
    (directory / "scores-150-2.npy").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="ARTIFACT_MISMATCH"):
        runner.verify_capital_run(result, spec, directory=directory)


def publication_lags():
    observed = {
        candidate.code: {
            "structurally_complete": True,
            "hard_risk": "PASS",
            "total_return": str(index),
            "maximum_drawdown": "0.2",
        }
        for index, candidate in enumerate(runner.CANDIDATES)
    }
    return {
        lag: {"observed": {code: dict(metric) for code, metric in observed.items()}}
        for lag in ("120", "130", "150")
    }


def test_publication_selection_is_deterministic_and_uses_approved_tie_breaks():
    from football.experiments import capital_artifacts

    lags = publication_lags()
    # Equal maximin return: T+150 chooses FRACTIONAL_KELLY over LEGACY_PARTIAL.
    for lag in ("120", "130"):
        lags[lag]["observed"]["LEGACY_PARTIAL"]["total_return"] = "9"
        lags[lag]["observed"]["FRACTIONAL_KELLY"]["total_return"] = "9"
    lags["150"]["observed"]["LEGACY_PARTIAL"]["total_return"] = "8"
    lags["150"]["observed"]["FRACTIONAL_KELLY"]["total_return"] = "9"
    selection = capital_artifacts.publication_selection({"lags": lags})
    assert selection["selected"] == "FRACTIONAL_KELLY"
    assert selection == capital_artifacts.publication_selection({"lags": lags})

    # If T+150 also ties, lower worst drawdown wins; canonical order is final.
    lags["150"]["observed"]["LEGACY_PARTIAL"]["total_return"] = "9"
    lags["120"]["observed"]["FRACTIONAL_KELLY"]["maximum_drawdown"] = "0.3"
    assert (
        capital_artifacts.publication_selection({"lags": lags})["selected"]
        == "LEGACY_PARTIAL"
    )
    lags["120"]["observed"]["FRACTIONAL_KELLY"]["maximum_drawdown"] = "0.2"
    assert (
        capital_artifacts.publication_selection({"lags": lags})["selected"]
        == "LEGACY_PARTIAL"
    )


def test_publication_selection_excludes_incomplete_or_hard_risk_failed_paths():
    from football.experiments import capital_artifacts

    lags = publication_lags()
    lags["130"]["observed"]["FRACTIONAL_KELLY"]["hard_risk"] = "FAIL"
    lags["150"]["observed"]["LEGACY_PARTIAL"]["structurally_complete"] = False
    selection = capital_artifacts.publication_selection({"lags": lags})
    assert selection["selected"] == "LEGACY_CAPPED"
    eligibility = {row["candidate"]: row["eligible"] for row in selection["ranking"]}
    assert eligibility["FRACTIONAL_KELLY"] is False
    assert eligibility["LEGACY_PARTIAL"] is False


def test_invariant_failure_yields_insufficient_never_promotion(
    isolated_lab, monkeypatch
):
    spec, _, base = isolated_lab
    monkeypatch.setattr(
        runner,
        "run_event_path",
        Mock(side_effect=ValueError("CAPITAL_RESOURCE_INVARIANT")),
    )
    result = runner.run_capital_experiment(spec, base=base, workspace_root=base / "tmp")
    assert result["summary"]["disposition"] == "INSUFFICIENT_EVIDENCE"
    assert result["summary"]["promotion"] == "NO_PROMOTION"
    assert all(
        lag["error"] == "CAPITAL_RESOURCE_INVARIANT" for lag in result["lags"].values()
    )


def test_concurrent_recurring_decimal_stakes_do_not_add_a_rounding_veto():
    rows = [opp(i, price="2.35", probability="0.65") for i in range(10)]
    result = run_event_path(rows, candidate(2), trace=True)
    metrics = result["metrics"]
    assert metrics["hard_risk"] == "PASS"
    assert metrics["placements"] == 10
    assert Decimal(metrics["bankroll_equity"]) == Decimal("110")
    # Preserve CURRENT Decimal arithmetic, including its signed final rounding
    # residual. No float epsilon, stake quantization or invented ruin veto.
    for row in result["ledger"]:
        assert Decimal(row["available_cash"]) == Decimal(row["equity"]) - Decimal(
            row["reserved"]
        )


def test_kickoff_tie_break_and_expiry_precede_same_wake_retry():
    early = opp(9)
    later = replace(opp(1, minute=5), execution_at=early.execution_at)
    result = run_event_path([later, early], candidate(lanes=1), trace=True)
    assert result["ledger"][0]["opportunity"] == "9"
    result = run_event_path(
        [opp(1), opp(2, minute=150)], candidate(lanes=1), trace=True
    )
    assert kinds(result, 2) == ["PENDING_CAPACITY", "EXPIRED_CAPACITY"]
    at = (AT + timedelta(minutes=150)).isoformat()
    assert [r["kind"] for r in result["ledger"] if r["at"] == at] == [
        "SETTLEMENT",
        "EXPIRED_CAPACITY",
    ]


def test_stability_odd_calendar_gives_extra_week_to_second_half():
    rows = [opp(i + 1, minute=i * 7 * 24 * 60, competition=i % 2 + 1) for i in range(5)]
    result = stability_checks(rows, runner.CANDIDATES, 150, 0, 1)
    assert [row["count"] for row in result["slices"][:2]] == [2, 3]
    single = stability_checks([opp(1)], runner.CANDIDATES, 150, 0, 1)
    assert single["status"] == "NOT_ESTIMABLE"
