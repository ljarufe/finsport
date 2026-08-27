from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from football.capital.contracts import CapitalDecision, RunUnavailable
from football.capital.policies import make_policy
from football.capital.replay import replay
from football.capital.simulation import simulate


def basis(count=12, *, probability="0.7", price="2.0", outcome="HOME"):
    start = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
    return tuple(
        CapitalDecision(
            source_id=index,
            decision_time=start + timedelta(days=index),
            action="HOME",
            outcome=outcome,
            price=Decimal(price),
            probability=Decimal(probability),
            observation_id=index,
            observation_time=start + timedelta(days=index, hours=-1),
        )
        for index in range(1, count + 1)
    )


def simulation(rows, *, stress=None, seed=41, paths=2_000):
    return simulate(
        rows,
        make_policy("FLAT_UNIT", {"unit": "1"}),
        Decimal("100"),
        seed=seed,
        path_count=paths,
        tail_level=0.05,
        mdd_thresholds=(0.1, 0.2),
        stress=stress,
    )


def test_seeded_monte_carlo_is_reproducible_and_streaming():
    rows = basis()
    first = simulation(rows)
    second = simulation(rows)

    assert first == second
    assert first["path_count"] == 2_000
    assert first["seed"] == 41
    assert (
        first["terminal_bankroll_quantile_1"] <= first["terminal_bankroll_quantile_5"]
    )
    assert first["expected_shortfall"] <= first["terminal_bankroll_quantile_5"]
    assert first["memory_design"].startswith("O(paths)")
    assert "path_rows" not in first


def test_probability_price_and_forced_loss_stress_have_expected_direction():
    rows = basis(count=20, probability="0.75", price="2.20")
    nominal = simulation(rows)
    probability_stress = simulation(rows, stress={"probability_delta": 0.25})
    price_stress = simulation(rows, stress={"price_haircut": 0.30})
    forced_losses = simulation(
        rows, stress={"forced_loss_start": 0, "forced_loss_length": 20}
    )

    assert (
        probability_stress["mean_terminal_bankroll"] < nominal["mean_terminal_bankroll"]
    )
    assert price_stress["mean_terminal_bankroll"] < nominal["mean_terminal_bankroll"]
    assert forced_losses["mean_terminal_bankroll"] < nominal["mean_terminal_bankroll"]
    assert (
        forced_losses["maximum_drawdown_distribution"]["mean"]
        > nominal["maximum_drawdown_distribution"]["mean"]
    )


def test_small_numpy_path_agrees_with_deterministic_reference_at_probability_one():
    rows = basis(count=3, probability="1", price="2.50", outcome="HOME")
    policy = make_policy("FLAT_UNIT", {"unit": "1.25"})
    deterministic = replay(rows, policy, Decimal("10"))
    stochastic = simulate(
        rows,
        policy,
        Decimal("10"),
        seed=7,
        path_count=8,
        tail_level=0.05,
        mdd_thresholds=(0.1,),
    )

    assert stochastic["mean_terminal_bankroll"] == pytest.approx(
        float(deterministic.metrics["terminal_bankroll"])
    )
    assert stochastic["practical_ruin_probability"] == 0


def test_terminal_batch_depletion_is_ruin_and_depleted_paths_stop():
    metrics = simulate(
        basis(count=2, probability="0", outcome="AWAY"),
        make_policy("FLAT_UNIT", {"unit": "100"}),
        Decimal("100"),
        seed=7,
        path_count=32,
        tail_level=0.05,
        mdd_thresholds=(0.5,),
    )

    assert metrics["mean_terminal_bankroll"] == 0
    assert metrics["practical_ruin_probability"] == 1
    assert metrics["termination_distribution"]["probability"] == 1
    assert metrics["max_stake_distribution"]["mean"] == 100


def test_overcommit_is_ruin_and_termination_without_processing_later_decisions():
    metrics = simulate(
        basis(count=2, probability="1"),
        make_policy("FLAT_UNIT", {"unit": "101"}),
        Decimal("100"),
        seed=7,
        path_count=32,
        tail_level=0.05,
        mdd_thresholds=(0.5,),
    )

    assert metrics["practical_ruin_probability"] == 1
    assert metrics["termination_distribution"]["probability"] == 1
    assert metrics["mean_terminal_bankroll"] == 100
    assert metrics["max_stake_distribution"]["maximum"] == 0


def test_stake_concentration_tracks_max_applied_stake_over_pre_batch_bankroll():
    metrics = simulate(
        basis(count=12, probability="0.5"),
        make_policy("FIXED_FRACTION_BANKROLL", {"fraction": "0.20"}),
        Decimal("100"),
        seed=23,
        path_count=256,
        tail_level=0.05,
        mdd_thresholds=(0.5,),
    )

    distribution = metrics["max_stake_pre_bankroll_ratio_distribution"]
    assert distribution["mean"] == pytest.approx(0.20)
    assert distribution["median"] == pytest.approx(0.20)
    assert distribution["maximum"] == pytest.approx(0.20)
    assert metrics["stake_concentration"] == pytest.approx(0.20)


def test_fractional_initial_legacy_stake_is_exact_and_only_recovery_is_ceiled():
    rows = basis(count=2)
    rows = (
        replace(rows[0], probability=Decimal("0"), outcome="AWAY"),
        replace(rows[1], probability=Decimal("1"), outcome="HOME"),
    )
    metrics = simulate(
        rows,
        make_policy("LEGACY_RECOVERY", {"initial_stake": "1.25"}),
        Decimal("100"),
        seed=31,
        path_count=16,
        tail_level=0.05,
        mdd_thresholds=(0.5,),
    )

    assert metrics["mean_terminal_bankroll"] == pytest.approx(101.75)
    assert metrics["max_stake_distribution"]["mean"] == pytest.approx(3.0)


def test_simulation_requires_probability_but_never_mutates_input():
    rows = list(basis(count=1))
    original = rows[0]
    rows[0] = CapitalDecision(
        source_id=original.source_id,
        decision_time=original.decision_time,
        action=original.action,
        outcome=original.outcome,
        price=original.price,
        probability=None,
        observation_id=original.observation_id,
        observation_time=original.observation_time,
    )
    before = tuple(rows)
    with pytest.raises(RunUnavailable, match="MISSING_MODEL_PROBABILITY"):
        simulation(rows)
    assert tuple(rows) == before


def test_simulation_rejects_out_of_bounds_probability():
    rows = list(basis(count=1))
    rows[0] = CapitalDecision(
        source_id=rows[0].source_id,
        decision_time=rows[0].decision_time,
        action=rows[0].action,
        outcome=rows[0].outcome,
        price=rows[0].price,
        probability=Decimal("1.01"),
        observation_id=rows[0].observation_id,
        observation_time=rows[0].observation_time,
    )
    with pytest.raises(RunUnavailable, match="INVALID_MODEL_PROBABILITY"):
        simulation(rows)


def test_simulated_recovery_rejects_concurrent_batch():
    rows = list(basis(count=2))
    rows[1] = CapitalDecision(
        source_id=rows[1].source_id,
        decision_time=rows[0].decision_time,
        action=rows[1].action,
        outcome=rows[1].outcome,
        price=rows[1].price,
        probability=rows[1].probability,
        observation_id=rows[1].observation_id,
        observation_time=rows[0].observation_time,
    )
    with pytest.raises(RunUnavailable, match="UNAVAILABLE_CONCURRENT_RECOVERY_STEP"):
        simulate(
            rows,
            make_policy("LEGACY_RECOVERY", {"initial_stake": "1"}),
            Decimal("100"),
            seed=1,
            path_count=10,
            tail_level=0.05,
            mdd_thresholds=(0.2,),
        )
