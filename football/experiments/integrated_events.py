"""FS-021 versioned replay derived from FS-020 CURRENT lane-first loop.

FS-020 remains unchanged. Its Opportunity/CapitalCandidate, policies, Decimal
contracts, ordering and accounting are reused; only FS-021 applies this gate.
"""

import heapq
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import timedelta
from decimal import Decimal

from football.capital.contracts import ZERO, CapitalDecision, json_decimal

from .capital_analysis import week_start
from .capital_events import INITIAL
from .storage import identity

RULE = "FS021_OPERATIONAL_DEPLETION_5U_AFTER_ALL_OPEN_V2"


@dataclass
class DepletionGate:
    state: str = "ACTIVE"
    ever_nonpositive_equity: bool = False

    def observe_settlement(self, equity):
        self.ever_nonpositive_equity |= equity <= 0

    def evaluate(self, equity, open_count, *, policy_termination=False):
        if self.state == "OPERATIONAL_DEPLETION" or policy_termination:
            return self.state
        if open_count:
            if equity <= Decimal("5"):
                self.state = "AWAITING_FINAL_OPEN_SETTLEMENT"
        else:
            self.state = "OPERATIONAL_DEPLETION" if equity <= Decimal("5") else "ACTIVE"
        return self.state


def opportunity_hash(opportunities):
    return identity(
        [
            {
                k: (
                    v.isoformat()
                    if hasattr(v, "isoformat")
                    else str(v) if isinstance(v, Decimal) else v
                )
                for k, v in asdict(o).items()
            }
            for o in opportunities
        ]
    )


def expand_ledger(result, opportunities, original_stream_sha):
    if (
        opportunity_hash(opportunities) != result["opportunity_sha256"]
        or original_stream_sha != result["original_stream_sha256"]
    ):
        raise ValueError("ORIGINAL_STREAM_INTEGRITY_FAIL")
    ledger = list(result["ledger"])
    suffix = result["suffix"]
    if suffix is not None:
        if (
            suffix["original_stream_sha256"] != original_stream_sha
            or suffix["opportunity_sha256"] != result["opportunity_sha256"]
        ):
            raise ValueError("SUFFIX_BINDING_MISMATCH")
        for index in suffix["indices"]:
            o = opportunities[index]
            ledger.append(
                dict(
                    kind=(
                        "NO_BET"
                        if o.action == "NO_BET"
                        else "NOT_EXECUTED_AFTER_OP_DEPLETION"
                    ),
                    at=o.execution_at.isoformat(),
                    opportunity=o.identity,
                    **suffix["context"],
                )
            )
    return sorted(ledger, key=lambda r: r["at"])


def run_integrated_path(
    opportunities,
    candidate,
    lag=150,
    *,
    trace=False,
    fast=True,
    original_stream_sha=None,
    risk_horizon_start=None,
):
    """Fresh 100u per call. Frozen evidence survives retries; requests do not.

    Decimal context is the CURRENT process context. No quantization or float
    conversion is permitted on the economic path. Trace is optional for heavy
    bootstrap paths; it has no effect on metrics or placement semantics.
    """
    if lag not in (120, 130, 150):
        raise ValueError("INVALID_SETTLEMENT_LAG")
    opportunities = tuple(opportunities)
    if len({o.identity for o in opportunities}) != len(opportunities):
        raise ValueError("DUPLICATE_CAPITAL_OPPORTUNITY")
    # Bootstrap retains scores only; input integrity is checked at execution/shard
    # boundaries. Observed ledgers bind every original row including the suffix.
    stream_sha = opportunity_hash(opportunities) if trace else None
    original_stream_sha = original_stream_sha or stream_sha
    gate = DepletionGate()
    terminal_at = None
    suffix = None
    physical_wakes = 0
    placed_competitions, placed_weeks = set(), set()
    input_indices = {o.identity: i for i, o in enumerate(opportunities)}
    policy = candidate.policy()
    state = policy.initial_state()
    equity, reserved = INITIAL, ZERO
    peak, drawdown, peak_reserved, total_staked = INITIAL, ZERO, ZERO, ZERO
    min_cash = INITIAL
    termination = ""
    ruined = False
    pending, opened, groups = {}, {}, defaultdict(list)
    statuses, counts, ledger = {}, Counter(), []
    stakes = []
    underwater_at = None
    max_drawdown_seconds = 0.0
    last_at = None
    risk_area = ZERO
    risk_cursor = risk_horizon_start
    min_equity = INITIAL
    max_recovery_seconds = 0.0
    for opportunity in opportunities:
        groups[opportunity.execution_at].append(opportunity)
    wakes = list(groups)
    heapq.heapify(wakes)
    scheduled = set(wakes)

    def record(kind, at, opportunity, **details):
        counts[kind] += 1
        if trace:
            ledger.append(
                json_decimal(
                    dict(
                        kind=kind,
                        at=at.isoformat(),
                        opportunity=(
                            opportunity.identity if opportunity is not None else None
                        ),
                        equity=equity,
                        reserved=reserved,
                        available_cash=equity - reserved,
                        policy_state=dict(state),
                        **details,
                    )
                )
            )

    def invariant():
        nonlocal min_cash, peak_reserved
        # Addition/subtraction may carry CURRENT Decimal rounding at context
        # precision; never impose a new quantization on reserved or equity.
        if not equity.is_finite() or not reserved.is_finite():
            raise ValueError("CAPITAL_RESOURCE_INVARIANT")
        if reserved > equity and equity > 0:
            raise ValueError("NEGATIVE_AVAILABLE_CASH")
        min_cash = min(min_cash, equity - reserved)
        peak_reserved = max(peak_reserved, reserved)

    while wakes:
        physical_wakes += 1
        at = heapq.heappop(wakes)
        if risk_cursor is not None:
            if at < risk_cursor:
                raise ValueError("RISK_ACCUMULATOR_TIME_ORDER")
            risk_area += reserved * Decimal(str((at - risk_cursor).total_seconds()))
            risk_cursor = at
        scheduled.remove(at)
        last_at = at
        due = sorted(
            (p for p in opened.values() if p[0] <= at),
            key=lambda p: (p[0], p[1].identity),
        )
        for settlement_at, opportunity, request in due:
            del opened[opportunity.identity]
            reserved -= request.applied
            won = opportunity.actual_outcome == opportunity.selected_outcome
            pnl = request.applied * (opportunity.price - 1) if won else -request.applied
            before = dict(state)
            state, _ = policy.settle(state, request, won)
            equity += pnl
            min_equity = min(min_equity, equity)
            gate.observe_settlement(equity)
            peak = max(peak, equity)
            drawdown = max(drawdown, (peak - equity) / peak)
            if equity < peak and underwater_at is None:
                underwater_at = at
            if underwater_at is not None:
                max_drawdown_seconds = max(
                    max_drawdown_seconds, (at - underwater_at).total_seconds()
                )
                if equity >= peak:
                    max_recovery_seconds = max(
                        max_recovery_seconds, (at - underwater_at).total_seconds()
                    )
                    underwater_at = None
            statuses[opportunity.identity] = "SETTLED"
            record(
                "SETTLEMENT",
                settlement_at,
                opportunity,
                request=asdict(request) if trace else None,
                profit_loss=pnl,
                state_before=before,
                won=won,
            )
            invariant()
            if equity <= ZERO:
                ruined = True
        previous = gate.state
        gate.evaluate(equity, len(opened), policy_termination=bool(termination))
        if gate.state != previous:
            record(gate.state, at, None)
        if gate.state == "OPERATIONAL_DEPLETION" and terminal_at is None:
            terminal_at = at
            for opportunity in sorted(pending.values(), key=lambda o: o.identity):
                statuses[opportunity.identity] = "PATH_STOPPED_OP_DEPLETION"
                record("PATH_STOPPED_OP_DEPLETION", at, opportunity)
            pending.clear()
            if fast:
                remaining = sorted(
                    (o for group in groups.values() for o in group),
                    key=lambda o: (o.execution_at, o.identity),
                )
                suffix = dict(
                    original_stream_sha256=original_stream_sha,
                    opportunity_sha256=stream_sha,
                    indices=[input_indices[o.identity] for o in remaining],
                    context=json_decimal(
                        dict(
                            equity=equity,
                            reserved=reserved,
                            available_cash=equity - reserved,
                            policy_state=dict(state),
                        )
                    ),
                )
                for opportunity in remaining:
                    kind = (
                        "NO_BET"
                        if opportunity.action == "NO_BET"
                        else "NOT_EXECUTED_AFTER_OP_DEPLETION"
                    )
                    statuses[opportunity.identity] = kind
                    counts[kind] += 1
                break
        for opportunity in sorted(tuple(pending.values()), key=lambda o: o.identity):
            if opportunity.kickoff <= at:
                del pending[opportunity.identity]
                statuses[opportunity.identity] = "EXPIRED_CAPACITY"
                record("EXPIRED_CAPACITY", at, opportunity)
        new = groups.pop(at, [])
        if gate.state == "OPERATIONAL_DEPLETION":
            for opportunity in sorted(new, key=lambda o: o.identity):
                kind = (
                    "NO_BET"
                    if opportunity.action == "NO_BET"
                    else "NOT_EXECUTED_AFTER_OP_DEPLETION"
                )
                statuses[opportunity.identity] = kind
                record(kind, at, opportunity)
            continue
        actionable = []
        for opportunity in sorted(new, key=lambda o: o.identity):
            if opportunity.action == "NO_BET":
                statuses[opportunity.identity] = "NO_BET"
                record("NO_BET", at, opportunity)
            else:
                actionable.append(opportunity)
        merged = {o.identity: o for o in [*pending.values(), *actionable]}
        for opportunity in sorted(merged.values(), key=lambda o: o.rank):
            key = opportunity.identity
            if gate.state == "OPERATIONAL_DEPLETION":
                statuses[key] = "NOT_EXECUTED_AFTER_OP_DEPLETION"
                record("NOT_EXECUTED_AFTER_OP_DEPLETION", at, opportunity)
                continue
            if termination:
                pending.pop(key, None)
                statuses[key] = "PATH_TERMINATED"
                record("PATH_TERMINATED", at, opportunity, reason=termination)
                continue
            if opportunity.kickoff <= at:
                pending.pop(key, None)
                statuses[key] = "EXPIRED_CAPACITY"
                record("EXPIRED_CAPACITY", at, opportunity)
                continue
            if gate.state == "AWAITING_FINAL_OPEN_SETTLEMENT":
                if key not in pending:
                    record("PENDING_CAPACITY", at, opportunity, reason=gate.state)
                pending[key] = opportunity
                statuses[key] = "PENDING_CAPACITY"
                continue
            if key in pending:
                record("PENDING_RETRY", at, opportunity)
            if len(opened) >= candidate.max_lanes:
                pending[key] = opportunity
                statuses[key] = "PENDING_CAPACITY"
                record("PENDING_CAPACITY", at, opportunity, reason="NO_AVAILABLE_LANE")
                continue
            decision = CapitalDecision(
                opportunity.source_id,
                opportunity.execution_at,
                opportunity.action,
                "",
                opportunity.price,
                opportunity.probability,
                observation_time=opportunity.execution_at,
            )
            request = policy.request(decision, equity, state)
            record("POLICY_REQUEST", at, opportunity, request=asdict(request))
            if request.termination_reason:
                termination = request.termination_reason
                pending.pop(key, None)
                statuses[key] = "POLICY_TERMINATION"
                record("POLICY_TERMINATION", at, opportunity, reason=termination)
                continue
            if request.requested <= ZERO or request.applied <= ZERO:
                pending.pop(key, None)
                statuses[key] = "ZERO_STAKE"
                record("ZERO_STAKE", at, opportunity, reason=request.reason)
                continue
            if request.requested > equity - reserved:
                pending[key] = opportunity
                statuses[key] = "PENDING_CAPACITY"
                record(
                    "PENDING_CAPACITY",
                    at,
                    opportunity,
                    reason="INSUFFICIENT_AVAILABLE_CASH",
                    request=asdict(request) if trace else None,
                )
                continue
            pending.pop(key, None)
            reserved += request.applied
            total_staked += request.applied
            stakes.append(request.applied)
            placed_competitions.add(opportunity.competition_id)
            placed_weeks.add(week_start(opportunity.execution_at).isoformat())
            counts["CAP_HIT"] += int(request.cap_hit)
            settlement_at = opportunity.kickoff + timedelta(minutes=lag)
            opened[key] = (settlement_at, opportunity, request)
            if settlement_at not in scheduled:
                heapq.heappush(wakes, settlement_at)
                scheduled.add(settlement_at)
            statuses[key] = "OPEN"
            invariant()
            record(
                "PLACEMENT",
                at,
                opportunity,
                request=asdict(request) if trace else None,
                settlement_at=settlement_at.isoformat(),
            )
        if termination:
            for opportunity in sorted(pending.values(), key=lambda o: o.identity):
                statuses[opportunity.identity] = "PATH_TERMINATED"
                record("PATH_TERMINATED", at, opportunity, reason=termination)
            pending.clear()
    for opportunity in sorted(pending.values(), key=lambda o: (o.kickoff, o.identity)):
        statuses[opportunity.identity] = "EXPIRED_CAPACITY"
        record("EXPIRED_CAPACITY", opportunity.kickoff, opportunity)
    # A terminal path must not accrue drawdown time against unvisited Matches.
    # The scalar path may visit them for audit, but neither variant simulates
    # Capital exposure after the final OPEN settlement at terminal_at.
    horizon = (
        terminal_at
        if terminal_at is not None
        else max(
            (o.kickoff + timedelta(minutes=lag) for o in opportunities),
            default=last_at,
        )
    )
    if horizon is not None:
        last_at = horizon
    if underwater_at is not None and last_at is not None:
        max_drawdown_seconds = max(
            max_drawdown_seconds, (last_at - underwater_at).total_seconds()
        )
    if opened or any(s in {"OPEN", "PENDING_CAPACITY"} for s in statuses.values()):
        raise ValueError("CAPITAL_PATH_INCOMPLETE")
    metrics = json_decimal(
        dict(
            bankroll_equity=equity,
            reserved_exposure=reserved,
            available_cash=equity - reserved,
            total_return=(equity - INITIAL) / INITIAL,
            total_staked=total_staked,
            roi=(equity - INITIAL) / total_staked if total_staked else None,
            maximum_drawdown=drawdown,
            drawdown_duration_seconds=max_drawdown_seconds,
            peak_reserved_exposure=peak_reserved,
            minimum_available_cash=min_cash,
            placements=len(stakes),
            stake_min=min(stakes) if stakes else ZERO,
            stake_max=max(stakes) if stakes else ZERO,
            stake_mean=total_staked / len(stakes) if stakes else ZERO,
            counts=dict(sorted(counts.items())),
            outcomes=dict(sorted(Counter(statuses.values()).items())),
            policy_state=state,
            termination_reason=termination
            or ("OPERATIONAL_DEPLETION" if terminal_at else ""),
            policy_termination=termination,
            ever_nonpositive_equity=ruined,
            operational_depletion=terminal_at is not None,
            terminal_at=terminal_at.isoformat() if terminal_at else None,
            placed_competitions=sorted(placed_competitions),
            placed_weeks=sorted(placed_weeks),
            input_count=len(opportunities),
            economic_ruin=ruined or equity <= 0 or termination == "BANKROLL_DEPLETED",
            hard_risk=(
                "FAIL"
                if ruined or equity <= 0 or termination or terminal_at
                else "PASS"
            ),
            structurally_complete=len(statuses) == len(opportunities),
            opportunity_cost="UNAVAILABLE_CURRENCY_NOT_BOUND",
        )
    )
    result = dict(
        metrics=metrics,
        ledger=ledger,
        suffix=suffix,
        physical_wakes=physical_wakes,
        opportunity_sha256=stream_sha,
        original_stream_sha256=original_stream_sha,
    )
    if risk_horizon_start is not None:
        risk_end = risk_horizon_start + timedelta(days=252)
        if risk_cursor > risk_end:
            raise ValueError("RISK_ACCUMULATOR_HORIZON")
        risk_area += reserved * Decimal(str((risk_end - risk_cursor).total_seconds()))
        result["risk_accumulators"] = json_decimal(
            dict(
                maximum_drawdown=drawdown,
                minimum_equity=min_equity,
                minimum_available_cash=min_cash,
                operational_depletion=terminal_at is not None,
                ever_nonpositive_equity=ruined,
                mean_reserved_exposure=risk_area / Decimal(252 * 86400),
                peak_reserved_exposure=peak_reserved,
                drawdown_duration_seconds=max_drawdown_seconds,
                recovery_duration_seconds=max_recovery_seconds,
                underwater_unrecovered=underwater_at is not None,
            )
        )
    result["ledger_hash"] = (
        identity(expand_ledger(result, opportunities, original_stream_sha))
        if trace
        else None
    )
    return result
