from itertools import groupby

import numpy as np

from .contracts import CapitalInputError, RunUnavailable
from .metrics import stochastic_metrics
from .policies import (
    FIXED_FRACTION_BANKROLL,
    FIXED_TARGET_PROFIT_NO_RECOVERY,
    FLAT_UNIT,
    FRACTIONAL_KELLY,
    LEGACY_CAPPED,
    LEGACY_PARTIAL,
    LEGACY_RECOVERY,
)
from .replay import validate_basis
from .stress import (
    deteriorate_price,
    deteriorate_probability,
    is_forced_loss,
    stress_parameters,
)


def _bounded_float(value, name, *, lower, upper):
    value = float(value)
    if not lower < value <= upper:
        raise CapitalInputError(f"{name} must be > {lower} and <= {upper}")
    return value


def simulate(
    decisions,
    policy,
    initial_bankroll,
    *,
    seed,
    path_count,
    tail_level=0.05,
    mdd_thresholds=(0.2, 0.5),
    stress=None,
):
    decisions = tuple(decisions)
    validate_basis(decisions, policy, require_outcome=False)
    if any(row.actionable and row.probability is None for row in decisions):
        raise RunUnavailable("MISSING_MODEL_PROBABILITY")
    if any(
        row.actionable
        and (not row.probability.is_finite() or not 0 <= row.probability <= 1)
        for row in decisions
    ):
        raise RunUnavailable("INVALID_MODEL_PROBABILITY")
    initial_bankroll = float(initial_bankroll)
    if initial_bankroll <= 0:
        raise RunUnavailable("INVALID_INITIAL_BANKROLL")
    if not isinstance(path_count, int) or path_count < 1:
        raise CapitalInputError("path_count must be a positive integer")
    tail_level = _bounded_float(tail_level, "tail_level", lower=0, upper=0.5)
    thresholds = tuple(float(value) for value in mdd_thresholds)
    if any(value < 0 or value > 1 for value in thresholds):
        raise CapitalInputError("MDD thresholds must be between zero and one")
    stress_config = stress_parameters(stress or {})

    rng = np.random.default_rng(seed)
    bankroll = np.full(path_count, initial_bankroll, dtype=np.float64)
    peak = bankroll.copy()
    maximum_drawdown = np.zeros(path_count, dtype=np.float64)
    max_stake = np.zeros(path_count, dtype=np.float64)
    ruined = np.zeros(path_count, dtype=np.bool_)
    terminated = np.zeros(path_count, dtype=np.bool_)
    cap_hits = np.zeros(path_count, dtype=np.int64)
    active = np.ones(path_count, dtype=np.bool_)
    accumulated_loss = np.zeros(path_count, dtype=np.float64)
    target_profit = np.full(path_count, np.nan, dtype=np.float64)
    recovery_step = np.zeros(path_count, dtype=np.int64)
    action_index = 0

    for _, grouped in groupby(decisions, key=lambda row: row.decision_time):
        batch = tuple(grouped)
        pre_batch_bankroll = bankroll.copy()
        batch_requests = []
        batch_applied = []
        batch_wins = []
        batch_termination = np.zeros(path_count, dtype=np.bool_)

        for decision in batch:
            if not decision.actionable:
                continue
            probability = deteriorate_probability(
                float(decision.probability), stress_config["probability_delta"]
            )
            price = deteriorate_price(
                float(decision.price), stress_config["price_haircut"]
            )
            requested, applied, cap_hit, stop = _request_vectors(
                policy,
                price,
                pre_batch_bankroll,
                probability,
                target_profit,
                accumulated_loss,
                recovery_step,
            )
            wins = rng.random(path_count) < probability
            if is_forced_loss(
                action_index,
                start=stress_config["forced_loss_start"],
                length=stress_config["forced_loss_length"],
            ):
                wins.fill(False)
            action_index += 1
            batch_requests.append(requested)
            batch_applied.append(applied)
            batch_wins.append(wins)
            cap_hits += cap_hit & active
            batch_termination |= stop & active

        if not batch_applied:
            continue
        requested_exposure = np.sum(batch_requests, axis=0)
        overcommitted = (
            active & ~batch_termination & (requested_exposure > pre_batch_bankroll)
        )
        ruined |= overcommitted
        terminated |= batch_termination
        funded = active & ~overcommitted & ~batch_termination
        batch_pnl = np.zeros(path_count, dtype=np.float64)

        actionable_rows = [row for row in batch if row.actionable]
        for decision, applied, wins in zip(
            actionable_rows, batch_applied, batch_wins, strict=True
        ):
            price = deteriorate_price(
                float(decision.price), stress_config["price_haircut"]
            )
            effective_stake = np.where(funded, applied, 0.0)
            max_stake = np.maximum(max_stake, effective_stake)
            batch_pnl += np.where(
                funded,
                np.where(wins, effective_stake * (price - 1.0), -effective_stake),
                0.0,
            )
            if policy.is_recovery:
                _settle_recovery_vectors(
                    policy,
                    price,
                    effective_stake,
                    wins,
                    funded,
                    target_profit,
                    accumulated_loss,
                    recovery_step,
                )

        bankroll = pre_batch_bankroll + batch_pnl
        depleted = funded & (bankroll <= 0)
        ruined |= depleted
        terminated |= depleted
        active &= ~overcommitted & ~batch_termination & ~depleted
        peak = np.maximum(peak, bankroll)
        drawdown = np.divide(
            peak - bankroll,
            peak,
            out=np.zeros_like(bankroll),
            where=peak > 0,
        )
        maximum_drawdown = np.maximum(maximum_drawdown, drawdown)

    metrics = stochastic_metrics(
        terminal_bankroll=bankroll,
        initial_bankroll=initial_bankroll,
        maximum_drawdown=maximum_drawdown,
        max_stake=max_stake,
        ruined=ruined,
        cap_hits=cap_hits,
        terminated=terminated,
        seed=seed,
        tail_level=tail_level,
        mdd_thresholds=thresholds,
    )
    metrics.update(
        {
            "numpy_version": np.__version__,
            "memory_design": "O(paths) state vectors; no paths_by_time matrix",
            "stress": stress_config,
        }
    )
    return metrics


def _request_vectors(
    policy,
    price,
    bankroll,
    probability,
    target_profit,
    accumulated_loss,
    recovery_step,
):
    count = bankroll.size
    cap_hit = np.zeros(count, dtype=np.bool_)
    stop = np.zeros(count, dtype=np.bool_)
    if policy.code == FLAT_UNIT:
        requested = np.full(count, float(policy.unit))
    elif policy.code == FIXED_FRACTION_BANKROLL:
        requested = float(policy.fraction) * bankroll
    elif policy.code == FIXED_TARGET_PROFIT_NO_RECOVERY:
        requested = np.full(count, float(policy.target) / (price - 1.0))
    elif policy.code == FRACTIONAL_KELLY:
        full_kelly = max(0.0, (probability * price - 1.0) / (price - 1.0))
        requested = float(policy.lambda_fraction) * full_kelly * bankroll
    elif policy.code in (LEGACY_RECOVERY, LEGACY_CAPPED):
        first = np.isnan(target_profit)
        initial = float(policy.initial_stake)
        theoretical = np.where(
            first,
            initial,
            (target_profit + accumulated_loss) / (price - 1.0),
        )
        requested = (
            np.ceil(theoretical) if policy.code == LEGACY_RECOVERY else theoretical
        )
    elif policy.code == LEGACY_PARTIAL:
        requested = (float(policy.target) + float(policy.alpha) * accumulated_loss) / (
            price - 1.0
        )
    else:  # pragma: no cover - make_policy prevents this
        raise CapitalInputError(f"Unsupported policy: {policy.code}")

    applied = requested.copy()
    if policy.code == LEGACY_CAPPED:
        next_step = recovery_step + 1
        if policy.max_recovery_steps is not None:
            stop = next_step > policy.max_recovery_steps
        if policy.max_stake_fraction is not None:
            applied = np.minimum(applied, float(policy.max_stake_fraction) * bankroll)
        if policy.max_absolute_stake is not None:
            applied = np.minimum(applied, float(policy.max_absolute_stake))
        applied = np.where(stop, 0.0, applied)
        cap_hit = applied < requested
    return requested, applied, cap_hit, stop


def _settle_recovery_vectors(
    policy,
    price,
    applied,
    wins,
    funded,
    target_profit,
    accumulated_loss,
    recovery_step,
):
    first = np.isnan(target_profit)
    if policy.code in (LEGACY_RECOVERY, LEGACY_CAPPED):
        derived_target = float(policy.initial_stake) * (price - 1.0)
    else:
        derived_target = float(policy.target)
    target_profit[funded & first] = derived_target
    recovery_step[funded] += 1
    losing = funded & ~wins
    accumulated_loss[losing] += applied[losing]
    winning = funded & wins
    target_profit[winning] = np.nan
    accumulated_loss[winning] = 0.0
    recovery_step[winning] = 0
