from collections import Counter
from decimal import Decimal

import numpy as np

from .contracts import ZERO


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else ZERO


def deterministic_metrics(
    decisions,
    ledger,
    initial_bankroll,
    sequence_lengths=(),
    incomplete_sequences=0,
):
    actionable = [decision for decision in decisions if decision.actionable]
    resolved = [decision for decision in actionable if decision.outcome]
    original_wins = sum(decision.outcome == decision.action for decision in resolved)
    exposed = [row for row in ledger if row.applied_stake > 0]
    wins = sum(row.outcome == row.action for row in exposed)
    losses = len(exposed) - wins
    total_staked = sum((row.applied_stake for row in ledger), ZERO)
    total_pnl = sum((row.profit_loss for row in ledger), ZERO)
    terminal = ledger[-1].bankroll_after if ledger else initial_bankroll
    max_stake = max((row.applied_stake for row in ledger), default=ZERO)
    max_stake_ratio = max(
        (
            _ratio(row.applied_stake, row.bankroll_before)
            for row in ledger
            if row.bankroll_before > 0
        ),
        default=ZERO,
    )

    bankroll_by_batch = []
    for row in ledger:
        if not bankroll_by_batch or bankroll_by_batch[-1][0] != row.batch_index:
            bankroll_by_batch.append((row.batch_index, row.bankroll_after))
    peak = initial_bankroll
    maximum_drawdown = ZERO
    maximum_drawdown_amount = ZERO
    current_duration = 0
    maximum_duration = 0
    for _, bankroll in bankroll_by_batch:
        if bankroll >= peak:
            peak = bankroll
            current_duration = 0
        else:
            current_duration += 1
            maximum_duration = max(maximum_duration, current_duration)
            amount = peak - bankroll
            maximum_drawdown_amount = max(maximum_drawdown_amount, amount)
            maximum_drawdown = max(maximum_drawdown, _ratio(amount, peak))

    longest_losing_streak = 0
    current_losing_streak = 0
    for row in exposed:
        if row.outcome == row.action:
            current_losing_streak = 0
        else:
            current_losing_streak += 1
            longest_losing_streak = max(longest_losing_streak, current_losing_streak)

    sequence_distribution = {
        str(length): count
        for length, count in sorted(Counter(sequence_lengths).items())
    }
    practical_ruin = any(row.practical_ruin for row in ledger)
    cap_hits = sum(row.cap_hit for row in ledger)
    return {
        "input_decisions": len(decisions),
        "actionable_capital_decisions": len(actionable),
        "capital_actions": len(exposed),
        "wins": wins,
        "losses": losses,
        "original_decision_wins": original_wins,
        "original_decision_hit_rate": str(
            _ratio(Decimal(original_wins), Decimal(len(resolved)))
        ),
        "total_staked": str(total_staked),
        "total_pnl": str(total_pnl),
        "roi": str(_ratio(total_pnl, total_staked)),
        "terminal_bankroll": str(terminal),
        "maximum_drawdown": str(maximum_drawdown),
        "maximum_drawdown_amount": str(maximum_drawdown_amount),
        "drawdown_duration": maximum_duration,
        "turnover": str(_ratio(total_staked, initial_bankroll)),
        "max_single_stake": str(max_stake),
        "max_stake_pre_bankroll_ratio": str(max_stake_ratio),
        "stake_concentration": str(_ratio(max_stake, total_staked)),
        "practical_ruin": practical_ruin,
        "cap_hits": cap_hits,
        "incomplete_terminated_recovery_sequences": incomplete_sequences,
        "longest_losing_streak": longest_losing_streak,
        "sequence_length_distribution": sequence_distribution,
    }


def stochastic_metrics(
    *,
    terminal_bankroll,
    initial_bankroll,
    maximum_drawdown,
    max_stake,
    max_stake_pre_bankroll_ratio,
    ruined,
    cap_hits,
    terminated,
    seed,
    tail_level,
    mdd_thresholds,
):
    terminal = np.asarray(terminal_bankroll, dtype=np.float64)
    mdd = np.asarray(maximum_drawdown, dtype=np.float64)
    max_stake = np.asarray(max_stake, dtype=np.float64)
    max_stake_ratio = np.asarray(max_stake_pre_bankroll_ratio, dtype=np.float64)
    pnl = terminal - initial_bankroll
    quantile_1 = float(np.quantile(terminal, 0.01))
    quantile_5 = float(np.quantile(terminal, 0.05))
    tail_cutoff = float(np.quantile(terminal, tail_level))
    tail = terminal[terminal <= tail_cutoff]
    expected_shortfall = float(np.mean(tail)) if tail.size else tail_cutoff
    return {
        "seed": seed,
        "path_count": int(terminal.size),
        "mean_terminal_bankroll": float(np.mean(terminal)),
        "median_terminal_bankroll": float(np.median(terminal)),
        "terminal_bankroll_quantile_1": quantile_1,
        "terminal_bankroll_quantile_5": quantile_5,
        "tail_level": tail_level,
        "expected_shortfall": expected_shortfall,
        "practical_ruin_probability": float(np.mean(ruined)),
        "maximum_drawdown_distribution": {
            "mean": float(np.mean(mdd)),
            "median": float(np.median(mdd)),
            "quantile_95": float(np.quantile(mdd, 0.95)),
            "maximum": float(np.max(mdd)),
        },
        "mdd_threshold_probabilities": {
            str(threshold): float(np.mean(mdd > threshold))
            for threshold in mdd_thresholds
        },
        "max_stake_distribution": {
            "mean": float(np.mean(max_stake)),
            "median": float(np.median(max_stake)),
            "quantile_95": float(np.quantile(max_stake, 0.95)),
            "maximum": float(np.max(max_stake)),
        },
        "max_stake_pre_bankroll_ratio_distribution": {
            "mean": float(np.mean(max_stake_ratio)),
            "median": float(np.median(max_stake_ratio)),
            "quantile_95": float(np.quantile(max_stake_ratio, 0.95)),
            "maximum": float(np.max(max_stake_ratio)),
        },
        "cap_distribution": {
            "mean_hits": float(np.mean(cap_hits)),
            "probability_any": float(np.mean(cap_hits > 0)),
        },
        "termination_distribution": {
            "probability": float(np.mean(terminated)),
        },
        "mean_pnl": float(np.mean(pnl)),
        "median_pnl": float(np.median(pnl)),
        "return": float(np.mean(pnl)),
        "stake_concentration": float(np.mean(max_stake_ratio)),
    }


PARETO_DIMENSIONS = {
    "return": True,
    "maximum_drawdown": False,
    "expected_shortfall": True,
    "practical_ruin_probability": False,
    "stake_concentration": False,
}


def pareto_compare(runs):
    """Compare named metric mappings without introducing a weighted score."""

    def value(metrics, dimension):
        if dimension == "return":
            raw = metrics.get("return", metrics.get("total_pnl"))
        elif dimension == "maximum_drawdown":
            raw = metrics.get("maximum_drawdown")
            if isinstance(raw, dict):
                raw = raw.get("mean")
            if raw is None:
                raw = metrics.get("maximum_drawdown_distribution", {}).get("mean")
        elif dimension == "practical_ruin_probability":
            raw = metrics.get("practical_ruin_probability")
            if raw is None and "practical_ruin" in metrics:
                raw = int(metrics["practical_ruin"])
        else:
            raw = metrics.get(dimension)
        if raw is None:
            raise ValueError(f"MISSING_PARETO_DIMENSION:{dimension}")
        return Decimal(str(raw))

    dominated_by = {name: [] for name in runs}
    for candidate_name, candidate in runs.items():
        for challenger_name, challenger in runs.items():
            if candidate_name == challenger_name:
                continue
            weakly_better = True
            strictly_better = False
            for dimension, higher_is_better in PARETO_DIMENSIONS.items():
                left = value(challenger, dimension)
                right = value(candidate, dimension)
                better_or_equal = left >= right if higher_is_better else left <= right
                better = left > right if higher_is_better else left < right
                weakly_better &= better_or_equal
                strictly_better |= better
            if weakly_better and strictly_better:
                dominated_by[candidate_name].append(challenger_name)
    return {
        "metrics_used": list(PARETO_DIMENSIONS),
        "non_dominated_runs": [
            name for name, dominators in dominated_by.items() if not dominators
        ],
        "dominated_runs": {
            name: dominators for name, dominators in dominated_by.items() if dominators
        },
    }
