from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from football.capital.contracts import (
    CapitalDecision,
    PolicyConfigError,
    RunUnavailable,
)
from football.capital.metrics import pareto_compare
from football.capital.policies import make_policy
from football.capital.replay import replay


def decision(
    source_id,
    day,
    *,
    action="HOME",
    outcome="HOME",
    price="2.0",
    probability="0.6",
    decision_time=None,
):
    decided = decision_time or datetime(2025, 1, day, 12, tzinfo=timezone.utc)
    return CapitalDecision(
        source_id=source_id,
        decision_time=decided,
        action=action,
        outcome=outcome,
        price=Decimal(price) if price is not None else None,
        probability=Decimal(probability) if probability is not None else None,
        observation_id=source_id if price is not None else None,
        observation_time=decided - timedelta(hours=1) if price is not None else None,
    )


def test_settlement_no_bet_decimal_metrics_and_known_drawdown():
    rows = (
        decision(1, 1, outcome="HOME", price="2.50"),
        decision(2, 2, outcome="AWAY", price="2.00"),
        decision(3, 3, action="NO_BET", outcome="", price=None, probability=None),
    )
    result = replay(rows, make_policy("FLAT_UNIT", {"unit": "1.25"}), Decimal("10"))

    assert [row.profit_loss for row in result.ledger] == [
        Decimal("1.875"),
        Decimal("-1.25"),
        Decimal("0"),
    ]
    assert result.ledger[2].applied_stake == 0
    assert result.metrics["total_staked"] == "2.50"
    assert Decimal(result.metrics["total_pnl"]) == Decimal("0.625")
    assert Decimal(result.metrics["roi"]) == Decimal("0.25")
    assert Decimal(result.metrics["turnover"]) == Decimal("0.25")
    assert Decimal(result.metrics["maximum_drawdown"]) == Decimal("1.25") / Decimal(
        "11.875"
    )
    assert result.metrics["drawdown_duration"] == 2
    assert result.metrics["longest_losing_streak"] == 1
    assert "expected_shortfall" not in result.metrics


def test_exactly_funded_losing_batch_depletes_bankroll_and_marks_ruin():
    result = replay(
        (decision(1, 1, outcome="AWAY"),),
        make_policy("FLAT_UNIT", {"unit": "100"}),
        Decimal("100"),
    )

    row = result.ledger[0]
    assert row.requested_stake == 100
    assert row.applied_stake == 100
    assert row.profit_loss == -100
    assert row.bankroll_after == 0
    assert row.practical_ruin is True
    assert row.termination_reason == "BANKROLL_DEPLETED"
    assert Decimal(result.metrics["terminal_bankroll"]) == 0
    assert result.metrics["practical_ruin"] is True


def test_bankroll_depletion_stops_before_the_next_decision():
    result = replay(
        (
            decision(1, 1, outcome="AWAY"),
            decision(2, 2, outcome="HOME"),
        ),
        make_policy("FLAT_UNIT", {"unit": "100"}),
        Decimal("100"),
    )

    assert [row.source_id for row in result.ledger] == [1]
    assert result.metrics["input_decisions"] == 2
    assert result.metrics["capital_actions"] == 1


def test_same_batch_uses_one_pre_batch_bankroll_and_settles_only_after_sizing():
    batch_time = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
    rows = (
        decision(1, 1, outcome="HOME", decision_time=batch_time),
        decision(2, 1, outcome="AWAY", decision_time=batch_time),
    )
    result = replay(
        rows,
        make_policy("FIXED_FRACTION_BANKROLL", {"fraction": "0.10"}),
        Decimal("100"),
    )

    assert [row.requested_stake for row in result.ledger] == [
        Decimal("10.00"),
        Decimal("10.00"),
    ]
    assert [row.bankroll_before for row in result.ledger] == [100, 100]
    assert [row.bankroll_after for row in result.ledger] == [100, 100]


def test_batch_overcommit_is_explicit_ruin_without_scaling_or_subset():
    batch_time = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
    rows = (
        decision(1, 1, decision_time=batch_time),
        decision(2, 1, decision_time=batch_time),
    )
    result = replay(
        rows,
        make_policy("FIXED_FRACTION_BANKROLL", {"fraction": "0.60"}),
        Decimal("100"),
    )

    assert [row.requested_stake for row in result.ledger] == [60, 60]
    assert [row.applied_stake for row in result.ledger] == [0, 0]
    assert all(row.practical_ruin for row in result.ledger)
    assert all(
        row.termination_reason == "INSUFFICIENT_CAPITAL" for row in result.ledger
    )
    assert result.metrics["practical_ruin"] is True


def test_fixed_target_formula_and_invalid_price_are_explicit():
    policy = make_policy("FIXED_TARGET_PROFIT_NO_RECOVERY", {"target_profit": "3"})
    result = replay((decision(1, 1, price="2.50"),), policy, Decimal("100"))
    assert result.ledger[0].requested_stake == 2

    with pytest.raises(RunUnavailable, match="INVALID_DECIMAL_PRICE"):
        replay((decision(2, 2, price="1.0"),), policy, Decimal("100"))


def test_legacy_exact_ceiling_cumulative_loss_win_reset_and_version():
    rows = (
        decision(1, 1, outcome="AWAY", price="2.50"),
        decision(2, 2, outcome="HOME", price="2.20"),
        decision(3, 3, outcome="HOME", price="3.00"),
    )
    policy = make_policy("LEGACY_RECOVERY", {"initial_stake": "2"})
    result = replay(rows, policy, Decimal("100"))

    assert policy.version == "fs004-legacy-recovery-deviation-1-v1"
    assert [row.requested_stake for row in result.ledger] == [2, 5, 2]
    assert [row.step for row in result.ledger] == [1, 2, 1]
    assert result.ledger[1].policy_state["step"] == 0
    assert result.metrics["sequence_length_distribution"] == {"1": 1, "2": 1}


def test_recovery_never_silently_serializes_concurrent_actions():
    batch_time = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
    rows = (
        decision(1, 1, decision_time=batch_time),
        decision(2, 1, decision_time=batch_time),
    )
    with pytest.raises(RunUnavailable, match="UNAVAILABLE_CONCURRENT_RECOVERY_STEP"):
        replay(
            rows,
            make_policy("LEGACY_RECOVERY", {"initial_stake": "1"}),
            Decimal("100"),
        )


def test_capped_preserves_theoretical_applied_shortfall_and_incomplete_recovery():
    rows = (
        decision(1, 1, outcome="AWAY", price="2.0"),
        decision(2, 2, outcome="HOME", price="2.0"),
    )
    policy = make_policy(
        "LEGACY_CAPPED", {"initial_stake": "2", "max_absolute_stake": "3"}
    )
    result = replay(rows, policy, Decimal("100"))

    second = result.ledger[1]
    assert second.requested_stake == 4
    assert second.applied_stake == 3
    assert second.cap_hit is True
    assert second.shortfall == 1
    assert second.capital_reason == "CAPPED_RECOVERY_SHORTFALL"
    assert result.metrics["total_pnl"] == "1.0"
    assert result.metrics["cap_hits"] == 1
    assert result.metrics["incomplete_terminated_recovery_sequences"] == 1


def test_capped_theoretical_batch_request_over_bankroll_is_still_ruin():
    rows = (
        decision(1, 1, outcome="AWAY", price="2.0"),
        decision(2, 2, outcome="HOME", price="2.0"),
    )
    policy = make_policy(
        "LEGACY_CAPPED", {"initial_stake": "40", "max_absolute_stake": "50"}
    )
    result = replay(rows, policy, Decimal("100"))

    second = result.ledger[1]
    assert second.requested_stake == 80
    assert second.applied_stake == 0
    assert second.practical_ruin is True
    assert second.termination_reason == "INSUFFICIENT_CAPITAL"


def test_capped_max_recovery_steps_terminates_without_claiming_ruin():
    rows = (
        decision(1, 1, outcome="AWAY", price="2.0"),
        decision(2, 2, outcome="HOME", price="2.0"),
    )
    policy = make_policy(
        "LEGACY_CAPPED", {"initial_stake": "2", "max_recovery_steps": 1}
    )
    result = replay(rows, policy, Decimal("100"))

    second = result.ledger[1]
    assert second.requested_stake == 4
    assert second.applied_stake == 0
    assert second.termination_reason == "MAX_RECOVERY_STEPS"
    assert second.practical_ruin is False
    assert result.metrics["incomplete_terminated_recovery_sequences"] == 1


@pytest.mark.parametrize(
    ("alpha", "expected"), (("0", "2"), ("0.5", "3.5"), ("1", "5"))
)
def test_partial_alpha_sensitivity(alpha, expected):
    policy = make_policy("LEGACY_PARTIAL", {"target_profit": "2", "alpha": alpha})
    state = {"target_profit": Decimal("2"), "accumulated_loss": Decimal("3"), "step": 1}
    request = policy.request(decision(1, 1), Decimal("100"), state)
    assert request.requested == Decimal(expected)


def test_partial_win_can_leave_net_sequence_loss():
    rows = (
        decision(1, 1, outcome="AWAY", price="2.0"),
        decision(2, 2, outcome="AWAY", price="2.0"),
        decision(3, 3, outcome="HOME", price="2.0"),
    )
    result = replay(
        rows,
        make_policy("LEGACY_PARTIAL", {"target_profit": "2", "alpha": "0"}),
        Decimal("100"),
    )
    assert Decimal(result.metrics["total_pnl"]) == -2


def test_kelly_positive_edge_lambda_and_non_positive_edge_zero_exposure():
    policy = make_policy("FRACTIONAL_KELLY", {"lambda": "0.5"})
    positive = replay((decision(1, 1),), policy, Decimal("100"))
    assert positive.ledger[0].requested_stake == Decimal("10.00")

    zero = replay(
        (decision(2, 2, probability="0.5", outcome="AWAY"),),
        policy,
        Decimal("100"),
    )
    assert zero.ledger[0].requested_stake == 0
    assert zero.ledger[0].capital_reason == "NO_POSITIVE_KELLY_EDGE"


def test_kelly_missing_probability_or_timestamp_valid_price_is_unavailable():
    policy = make_policy("FRACTIONAL_KELLY", {"lambda": "0.5"})
    with pytest.raises(RunUnavailable, match="MISSING_MODEL_PROBABILITY"):
        replay(
            (decision(1, 1, probability=None),),
            policy,
            Decimal("100"),
        )
    with pytest.raises(RunUnavailable, match="MISSING_TIMESTAMP_VALID_PRICE"):
        replay(
            (decision(2, 2, price=None, probability="0.6"),),
            policy,
            Decimal("100"),
        )


def test_decimal_config_does_not_pass_through_binary_float():
    with pytest.raises(PolicyConfigError, match="BINARY_FLOAT"):
        make_policy("FLAT_UNIT", {"unit": 0.1})


def test_pareto_reports_dominated_without_weighted_score():
    runs = {
        "dominant": {
            "return": 10,
            "maximum_drawdown": 0.1,
            "expected_shortfall": 90,
            "practical_ruin_probability": 0,
            "stake_concentration": 0.1,
        },
        "dominated": {
            "return": 5,
            "maximum_drawdown": 0.2,
            "expected_shortfall": 80,
            "practical_ruin_probability": 0.1,
            "stake_concentration": 0.2,
        },
        "tradeoff": {
            "return": 12,
            "maximum_drawdown": 0.3,
            "expected_shortfall": 75,
            "practical_ruin_probability": 0.2,
            "stake_concentration": 0.3,
        },
    }
    comparison = pareto_compare(runs)
    assert comparison["non_dominated_runs"] == ["dominant", "tradeoff"]
    assert comparison["dominated_runs"] == {"dominated": ["dominant"]}
    assert "score" not in comparison
