from dataclasses import replace
from decimal import Decimal
from itertools import groupby

from .contracts import (
    ZERO,
    ReplayLedgerRow,
    ReplayResult,
    RunUnavailable,
    json_decimal,
)
from .metrics import deterministic_metrics


def _validate_actionable(decision, policy, *, require_outcome):
    if not decision.actionable:
        return
    if (
        decision.price is None
        or decision.observation_id is None
        or decision.observation_time is None
        or decision.observation_time >= decision.decision_time
    ):
        raise RunUnavailable("MISSING_TIMESTAMP_VALID_PRICE")
    if decision.price <= 1:
        raise RunUnavailable("INVALID_DECIMAL_PRICE")
    if require_outcome and not decision.outcome:
        raise RunUnavailable("UNRESOLVED_OUTCOME")
    if policy.requires_probability and decision.probability is None:
        raise RunUnavailable("MISSING_MODEL_PROBABILITY")


def validate_basis(decisions, policy, *, require_outcome):
    for decision in decisions:
        _validate_actionable(decision, policy, require_outcome=require_outcome)
    if policy.is_recovery:
        for _, grouped in groupby(decisions, key=lambda row: row.decision_time):
            if sum(row.actionable for row in grouped) > 1:
                raise RunUnavailable("UNAVAILABLE_CONCURRENT_RECOVERY_STEP")


def replay(decisions, policy, initial_bankroll):
    decisions = tuple(decisions)
    initial_bankroll = Decimal(initial_bankroll)
    if initial_bankroll <= 0:
        raise RunUnavailable("INVALID_INITIAL_BANKROLL")
    actionable = [row for row in decisions if row.actionable]
    if actionable and not any(row.outcome for row in actionable):
        raise RunUnavailable(
            "UNAVAILABLE_INSUFFICIENT_RESOLVED_TIMESTAMP_VALID_DECISIONS"
        )
    validate_basis(decisions, policy, require_outcome=True)
    bankroll = initial_bankroll
    state = policy.initial_state()
    ledger = []
    sequence_lengths = []
    incomplete_sequence_count = 0
    terminated = False

    for batch_index, (batch_time, grouped) in enumerate(
        groupby(decisions, key=lambda row: row.decision_time), start=1
    ):
        batch = tuple(grouped)
        bankroll_before = bankroll
        requests = []
        for decision in batch:
            if not decision.actionable:
                requests.append(None)
                continue
            request = policy.request(decision, bankroll_before, state)
            requests.append(request)

        if any(request and request.termination_reason for request in requests):
            for decision, request in zip(batch, requests, strict=True):
                request = request or policy_zero_request()
                ledger.append(
                    _ledger_row(
                        decision,
                        request,
                        batch_index,
                        bankroll_before,
                        bankroll_before,
                        ZERO,
                        state,
                        practical_ruin=False,
                    )
                )
            terminated = True
            break

        requested_exposure = sum(
            (request.requested for request in requests if request), ZERO
        )
        if requested_exposure > bankroll_before:
            for decision, request in zip(batch, requests, strict=True):
                request = request or policy_zero_request()
                unfunded = replace(
                    request,
                    applied=ZERO,
                    shortfall=request.shortfall + request.applied,
                    termination_reason="INSUFFICIENT_CAPITAL",
                )
                ledger.append(
                    _ledger_row(
                        decision,
                        unfunded,
                        batch_index,
                        bankroll_before,
                        bankroll_before,
                        ZERO,
                        state,
                        practical_ruin=decision.actionable,
                    )
                )
            terminated = True
            break

        settled = []
        batch_pnl = ZERO
        for decision, request in zip(batch, requests, strict=True):
            if request is None:
                settled.append((decision, policy_zero_request(), ZERO, state))
                continue
            won = decision.action == decision.outcome
            pnl = request.applied * (decision.price - 1) if won else -request.applied
            batch_pnl += pnl
            state, completed_length = policy.settle(state, request, won)
            if completed_length is not None:
                sequence_lengths.append(completed_length)
                if request.cap_hit and request.shortfall > 0:
                    incomplete_sequence_count += 1
            settled.append((decision, request, pnl, state))
        bankroll = bankroll_before + batch_pnl
        depleted = bankroll <= 0
        for decision, request, pnl, state_snapshot in settled:
            if depleted and decision.actionable:
                request = replace(
                    request,
                    termination_reason="BANKROLL_DEPLETED",
                )
            ledger.append(
                _ledger_row(
                    decision,
                    request,
                    batch_index,
                    bankroll_before,
                    bankroll,
                    pnl,
                    state_snapshot,
                    practical_ruin=depleted and decision.actionable,
                )
            )
        if depleted:
            terminated = True
            break

    incomplete_sequences = incomplete_sequence_count + int(
        policy.is_recovery and (state.get("step", 0) > 0 or terminated)
    )
    metrics = deterministic_metrics(
        decisions,
        ledger,
        initial_bankroll,
        sequence_lengths,
        incomplete_sequences,
    )
    return ReplayResult(metrics=metrics, ledger=tuple(ledger))


def policy_zero_request():
    from .contracts import StakeRequest

    return StakeRequest(ZERO, ZERO, reason="NO_BET")


def _ledger_row(
    decision,
    request,
    batch_index,
    bankroll_before,
    bankroll_after,
    pnl,
    state,
    *,
    practical_ruin,
):
    return ReplayLedgerRow(
        source_id=decision.source_id,
        batch_time=decision.decision_time,
        batch_index=batch_index,
        step=request.step,
        requested_stake=request.requested,
        applied_stake=request.applied,
        bankroll_before=bankroll_before,
        bankroll_after=bankroll_after,
        profit_loss=pnl,
        action=decision.action,
        outcome=decision.outcome,
        price=decision.price,
        capital_reason=request.reason,
        policy_state=json_decimal(state),
        cap_hit=request.cap_hit,
        shortfall=request.shortfall,
        practical_ruin=practical_ruin,
        termination_reason=request.termination_reason,
    )
