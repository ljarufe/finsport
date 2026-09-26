"""Derive auditable observed economics from authentic FS-021 event ledgers."""

import math
from datetime import timedelta
from decimal import Decimal

from .integrated_inputs import require
from .storage import instant

METRICS_VERSION = "FS021_OBSERVED_ECONOMIC_METRICS_V1"
INITIAL = Decimal("100")


def derive_observed_metrics(result, horizon_start, *, path_horizon, days=252):
    """Use post-event states; hold terminal state constant through empty weeks."""
    require(days > 0, "ECONOMIC_HORIZON")
    ledger, original = result["ledger"], result["metrics"]
    start = instant(horizon_start)
    end = start + timedelta(days=days)
    events = sorted(
        enumerate(ledger), key=lambda item: (instant(item[1]["at"]), item[0])
    )
    equity, reserve, cash = INITIAL, Decimal(0), INITIAL
    peak, maximum_drawdown = INITIAL, Decimal(0)
    min_equity, min_cash, peak_reserved = INITIAL, INITIAL, Decimal(0)
    replayed_equity, positive = INITIAL, []
    underwater_start, max_duration, max_recovery = None, 0.0, 0.0
    area = Decimal(0)
    cursor = start
    daily = []
    next_close = start + timedelta(days=1)
    daily_peak = INITIAL
    daily_drawdowns = []
    last_at = None

    def advance(target):
        nonlocal cursor, area, next_close, daily_peak
        clipped = min(max(target, start), end)
        while next_close <= clipped and next_close <= end:
            area += reserve * Decimal(str((next_close - cursor).total_seconds()))
            cursor = next_close
            daily.append(str(equity))
            daily_peak = max(daily_peak, equity)
            daily_drawdowns.append((daily_peak - equity) / daily_peak)
            next_close += timedelta(days=1)
        area += reserve * Decimal(str((clipped - cursor).total_seconds()))
        cursor = clipped

    for _, event in events:
        at = instant(event["at"])
        last_at = at
        if at < start or at > end:
            # A post-horizon physical event would invalidate the 252-day view.
            require(at >= start and at <= end, "EVENT_OUTSIDE_HORIZON")
        advance(at)
        equity = Decimal(event["equity"])
        reserve = Decimal(event["reserved"])
        cash = Decimal(event["available_cash"])
        require(equity - reserve == cash, "LEDGER_CASH_INVARIANT")
        min_equity, min_cash = min(min_equity, equity), min(min_cash, cash)
        peak_reserved = max(peak_reserved, reserve)
        if event["kind"] == "SETTLEMENT":
            gain = Decimal(event["profit_loss"])
            replayed_equity += gain
            require(replayed_equity == equity, "LEDGER_SETTLEMENT_RECONCILIATION")
            if gain > 0:
                positive.append(gain)
            peak = max(peak, equity)
            maximum_drawdown = max(maximum_drawdown, (peak - equity) / peak)
            if equity < peak and underwater_start is None:
                underwater_start = at
            if underwater_start is not None:
                max_duration = max(
                    max_duration, (at - underwater_start).total_seconds()
                )
                if equity >= peak:
                    max_recovery = max(
                        max_recovery, (at - underwater_start).total_seconds()
                    )
                    underwater_start = None
    if underwater_start is not None and last_at is not None:
        terminal = (
            instant(original["terminal_at"])
            if original["terminal_at"]
            else instant(path_horizon)
        )
        max_duration = max(max_duration, (terminal - underwater_start).total_seconds())
    advance(end)
    require(len(daily) == days and len(daily_drawdowns) == days, "DAILY_EQUITY_COUNT")
    require(
        replayed_equity == Decimal(original["bankroll_equity"]),
        "LEDGER_PNL_RECONCILIATION",
    )
    require(
        (equity - INITIAL) / INITIAL == Decimal(original["total_return"]),
        "LEDGER_RETURN_RECONCILIATION",
    )
    require(
        maximum_drawdown == Decimal(original["maximum_drawdown"]),
        "LEDGER_MDD_RECONCILIATION",
    )
    require(
        max_duration == original["drawdown_duration_seconds"],
        "LEDGER_DURATION_RECONCILIATION",
    )
    require(
        peak_reserved == Decimal(original["peak_reserved_exposure"]),
        "LEDGER_PEAK_RESERVE_RECONCILIATION",
    )
    require(
        min_cash == Decimal(original["minimum_available_cash"]),
        "LEDGER_MIN_CASH_RECONCILIATION",
    )
    concentration = (
        sum(sorted(positive, reverse=True)[:5], Decimal(0)) / sum(positive)
        if positive
        else None
    )
    weekly = [INITIAL] + [Decimal(daily[j]) for j in range(6, days, 7)]
    loss_weeks = sum(b < a for a, b in zip(weekly[:-1], weekly[1:], strict=True))
    worst = sorted(daily_drawdowns, reverse=True)[: math.ceil(days * 0.05)]
    return dict(
        schema=METRICS_VERSION,
        equity_final=str(equity),
        profit_loss=str(equity - INITIAL),
        total_return=original["total_return"],
        maximum_drawdown=str(maximum_drawdown),
        drawdown_duration_seconds=max_duration,
        recovery_duration_seconds=max_recovery,
        underwater_unrecovered=underwater_start is not None,
        weekly_loss_frequency=loss_weeks / (len(weekly) - 1),
        daily_equity=daily,
        cdar95_daily=str(sum(worst) / Decimal(len(worst))),
        mean_reserved_exposure=str(area / Decimal(days * 86400)),
        peak_reserved_exposure=str(peak_reserved),
        minimum_equity=str(min_equity),
        minimum_available_cash=str(min_cash),
        top5_positive_pnl_concentration=(
            str(concentration) if concentration is not None else None
        ),
        settled_count=original["placements"],
        operational_depletion=original["operational_depletion"],
        opportunity_cost=dict(
            status="UNAVAILABLE_UPSTREAM",
            reason="CURRENCY_AND_EXECUTABLE_PRICE_NOT_BOUND",
        ),
        bootstrap_path_risk=dict(
            status="UNAVAILABLE_UPSTREAM",
            reason="ORIGINAL_BOOTSTRAP_STORED_TERMINAL_SCORES_ONLY",
        ),
    )
