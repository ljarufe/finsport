"""Reusable, offline Decimal Event-Time Capital replay (E2.4 lane first).

Only execution and actual settlement instants wake placement. Kickoff is an
expiry deadline, never a placement wake. No database/provider/runtime imports.
"""

import hashlib
import heapq
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from football.capital.contracts import ZERO, CapitalDecision, json_decimal
from football.capital.policies import make_policy

from .storage import canonical

INITIAL = Decimal("100")
RUNNER_VERSION = "FS020_EVENT_TIME_E24_V1"


@dataclass(frozen=True)
class CapitalCandidate:
    code: str
    version: str
    config_json: str
    max_lanes: int

    def policy(self):
        import json

        policy = make_policy(self.code, json.loads(self.config_json))
        if policy.version != self.version or self.max_lanes < 1:
            raise ValueError("CAPITAL_CANDIDATE_CONTRACT_MISMATCH")
        return policy

    def data(self):
        import json

        return dict(
            code=self.code,
            version=self.version,
            config=json.loads(self.config_json),
            max_lanes=self.max_lanes,
        )


@dataclass(frozen=True)
class Opportunity:
    identity: str
    source_id: int
    competition_id: int
    kickoff: datetime
    execution_at: datetime
    action: str
    selected_outcome: str | None
    actual_outcome: str
    price: Decimal | None
    probability: Decimal | None

    def __post_init__(self):
        if (
            not self.identity
            or self.kickoff.tzinfo is None
            or self.execution_at.tzinfo is None
            or self.action not in {"BET", "NO_BET"}
            or self.actual_outcome not in {"HOME", "DRAW", "AWAY"}
        ):
            raise ValueError("INVALID_CAPITAL_OPPORTUNITY")
        if self.action == "BET" and (
            self.selected_outcome not in {"HOME", "DRAW", "AWAY"}
            or not isinstance(self.price, Decimal)
            or not self.price.is_finite()
            or self.price <= 1
            or not isinstance(self.probability, Decimal)
            or not self.probability.is_finite()
            or not ZERO <= self.probability <= 1
        ):
            raise ValueError("INVALID_CAPITAL_ECONOMIC_BASIS")

    @property
    def rank(self):
        return (-(self.probability * self.price - 1), self.kickoff, self.identity)


def run_event_path(opportunities, candidate, lag=150, *, trace=False):
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
                        opportunity=opportunity.identity,
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
        at = heapq.heappop(wakes)
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
            peak = max(peak, equity)
            drawdown = max(drawdown, (peak - equity) / peak)
            if equity < peak and underwater_at is None:
                underwater_at = at
            if underwater_at is not None:
                max_drawdown_seconds = max(
                    max_drawdown_seconds, (at - underwater_at).total_seconds()
                )
                if equity >= peak:
                    underwater_at = None
            statuses[opportunity.identity] = "SETTLED"
            record(
                "SETTLEMENT",
                settlement_at,
                opportunity,
                request=asdict(request),
                profit_loss=pnl,
                state_before=before,
                won=won,
            )
            invariant()
            if equity <= ZERO:
                ruined = True
                termination = termination or "BANKROLL_DEPLETED"
        for opportunity in sorted(tuple(pending.values()), key=lambda o: o.identity):
            if opportunity.kickoff <= at:
                del pending[opportunity.identity]
                statuses[opportunity.identity] = "EXPIRED_CAPACITY"
                record("EXPIRED_CAPACITY", at, opportunity)
        new = groups.pop(at, [])
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
                    request=asdict(request),
                )
                continue
            pending.pop(key, None)
            reserved += request.applied
            total_staked += request.applied
            stakes.append(request.applied)
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
                request=asdict(request),
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
            termination_reason=termination,
            economic_ruin=ruined or equity <= 0 or termination == "BANKROLL_DEPLETED",
            hard_risk="FAIL" if ruined or equity <= 0 or termination else "PASS",
            structurally_complete=len(statuses) == len(opportunities),
            opportunity_cost="UNAVAILABLE_CURRENCY_NOT_BOUND",
        )
    )
    return dict(
        metrics=metrics,
        ledger=ledger,
        ledger_hash=(
            hashlib.sha256(canonical(ledger).encode()).hexdigest() if trace else None
        ),
    )
