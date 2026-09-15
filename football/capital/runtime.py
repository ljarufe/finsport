"""FS-016 persistent, simulation-only Capital event-time runtime."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from football.capture.contracts import CaptureConfig
from football.models import (
    CapitalExecutionBasis,
    CapitalExecutionState,
    CapitalPosition,
    CapitalResultObservation,
    CapitalRuntimeConfig,
    CaptureWorkItem,
    CompetitionSourceRef,
    Decision,
    Match,
    MatchSourceRef,
    Prediction,
    PredictionExperiment,
    ReconciliationStatus,
    Source,
)
from football.prediction.contracts import ProbabilityResult
from football.prediction.market import best_prices_as_of
from football.prediction.policies import (
    POLICY_VERSIONS as DECISION_POLICY_VERSIONS,
)
from football.prediction.policies import (
    PolicyResult,
    modal_all,
    readiness_no_bet,
    selective_confidence,
    value_policy,
)
from football.providers.api_football import (
    APIFootballClient,
    APIFootballError,
    APIFootballOperationBudgetError,
)
from football.sync import (
    API_FOOTBALL_CODE,
    FINISHED_STATUSES,
    sync_fixture_payloads,
)

from .contracts import CapitalDecision, StakeRequest, json_decimal
from .policies import (
    FIXED_FRACTION_BANKROLL,
    FIXED_TARGET_PROFIT_NO_RECOVERY,
    FLAT_UNIT,
    FRACTIONAL_KELLY,
    LEGACY_CAPPED,
    LEGACY_PARTIAL,
    LEGACY_RECOVERY,
    POLICY_VERSIONS,
    make_policy,
)

RUNTIME_VERSION = "fs016-capital-runtime-v2"
EXECUTION_VERSION = "fs016-market-t30m-v2"
AUTOMATIC_SOURCE = (Prediction.DIXON_COLES, "MODAL_ALL", "")
TERMINAL_RESULT_STATUSES = FINISHED_STATUSES | {"CANC", "ABD"}
VOID_STATUSES = {"CANC", "ABD"}
ACCEPTED_CAPTURE_STATUSES = {
    CaptureWorkItem.Status.SUCCESS,
    CaptureWorkItem.Status.SUCCESS_EMPTY,
    CaptureWorkItem.Status.LATE_CAPTURE,
}
ZERO = Decimal("0")

AUTOMATIC_CONFIGS = (
    (FLAT_UNIT, {"unit": "1"}, 10),
    (FIXED_FRACTION_BANKROLL, {"fraction": "0.05"}, 10),
    (
        FIXED_TARGET_PROFIT_NO_RECOVERY,
        {"target_profit": "1"},
        10,
    ),
    (LEGACY_RECOVERY, {"initial_stake": "1"}, 1),
    (
        LEGACY_CAPPED,
        {"initial_stake": "1", "max_absolute_stake": "5"},
        1,
    ),
    (LEGACY_PARTIAL, {"target_profit": "1", "alpha": "0.5"}, 1),
    (FRACTIONAL_KELLY, {"lambda": "0.25"}, 10),
)


class CapitalRuntimeInvariantError(RuntimeError):
    """Durable Capital state contradicts the approved v2 contract."""


@dataclass(frozen=True)
class RuntimeResult:
    status: str
    configs: int = 0
    config_ids: tuple[int, ...] = ()
    placed: int = 0
    not_placed: int = 0
    settled: int = 0
    provider_calls: int = 0
    open_debt: int = 0
    errors: tuple[str, ...] = ()

    def as_dict(self):
        return {
            "status": self.status,
            "runtime_version": RUNTIME_VERSION,
            "execution_version": EXECUTION_VERSION,
            "configs": self.configs,
            "config_ids": list(self.config_ids),
            "placed": self.placed,
            "not_placed": self.not_placed,
            "settled": self.settled,
            "provider_calls": self.provider_calls,
            "open_debt": self.open_debt,
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class ExecutionCandidate:
    work_item: CaptureWorkItem
    decision: Decision | None
    result: object | None
    selected_price: Decimal | None
    selected_observation_id: int | None
    model_probability: Decimal | None
    expected_value: Decimal | None

    @property
    def match(self):
        return self.work_item.match


def _decimal(value):
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _decimal_state(value):
    if isinstance(value, dict):
        return {key: _decimal_state(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimal_state(item) for item in value]
    if value is None or isinstance(value, (bool, int)):
        return value
    return Decimal(str(value))


def _config_identity(policy_code):
    return f"{RUNTIME_VERSION}:automatic:{policy_code}"


@transaction.atomic
def provision_automatic_configs():
    """Idempotently provision the exact seven independent automatic bankrolls."""

    configs = []
    expected_identities = {_config_identity(code) for code, _, _ in AUTOMATIC_CONFIGS}
    unexpected = CapitalRuntimeConfig.objects.filter(
        automatic=True, current=True
    ).exclude(identity__in=expected_identities)
    if unexpected.exists():
        raise CapitalRuntimeInvariantError("UNEXPECTED_CURRENT_AUTOMATIC_CONFIG")
    for policy_code, policy_config, max_lanes in AUTOMATIC_CONFIGS:
        policy = make_policy(policy_code, policy_config)
        expected = {
            "runtime_version": RUNTIME_VERSION,
            "execution_version": EXECUTION_VERSION,
            "mode": CapitalRuntimeConfig.Mode.CURRENT,
            "automatic": True,
            "current": True,
            "source_model_code": AUTOMATIC_SOURCE[0],
            "decision_policy_code": AUTOMATIC_SOURCE[1],
            "decision_policy_variant": AUTOMATIC_SOURCE[2],
            "policy_code": policy_code,
            "policy_version": POLICY_VERSIONS[policy_code],
            "policy_config": policy_config,
            "max_lanes": max_lanes,
            "initial_bankroll": Decimal("100"),
        }
        config, created = CapitalRuntimeConfig.objects.get_or_create(
            identity=_config_identity(policy_code),
            defaults={
                **expected,
                "bankroll_equity": Decimal("100"),
                "reserved_exposure": ZERO,
                "policy_state": json_decimal(policy.initial_state()),
                "peak_equity": Decimal("100"),
                "peak_reserved_exposure": ZERO,
                "provenance": {
                    "automatic_source": "DIXON_COLES+MODAL_ALL",
                    "initial_bankroll_semantics": "one independent bankroll per config",
                },
            },
        )
        if not created:
            for field, value in expected.items():
                if getattr(config, field) != value:
                    raise CapitalRuntimeInvariantError(
                        f"AUTOMATIC_CONFIG_DRIFT:{policy_code}:{field}"
                    )
        configs.append(config)
    return tuple(configs)


def _probability(prediction):
    return ProbabilityResult(
        prediction.p_home,
        prediction.p_draw,
        prediction.p_away,
        diagnostics={"source_prediction_id": prediction.pk},
    )


def _latest_execution_decision(match, policy_code, policy_variant):
    return (
        Decision.objects.filter(
            match=match,
            prediction__model_code=Prediction.DIXON_COLES,
            experiment__mode=PredictionExperiment.MODE_PROSPECTIVE,
            policy_code=policy_code,
            policy_variant=policy_variant,
        )
        .select_related("prediction", "experiment")
        .order_by("-created", "-id")
        .first()
    )


def build_execution_candidate(
    work_item,
    *,
    policy_code="MODAL_ALL",
    policy_variant="",
):
    """Re-evaluate one Decision against only its governed final T-30 batch."""

    if (
        work_item.purpose != CaptureWorkItem.Purpose.ODDS_CAPTURE
        or work_item.intended_window != "market-t30m"
        or work_item.status not in ACCEPTED_CAPTURE_STATUSES
        or not work_item.executed_at
        or not work_item.run.completed_at
    ):
        raise CapitalRuntimeInvariantError("INVALID_T30_EXECUTION_WORK_ITEM")
    decision = _latest_execution_decision(work_item.match, policy_code, policy_variant)
    if decision is None:
        return ExecutionCandidate(work_item, None, None, None, None, None, None)
    probability = _probability(decision.prediction)
    prices = best_prices_as_of(
        work_item.match,
        work_item.run.completed_at,
        not_before=work_item.executed_at,
    )
    if not decision.prediction.bet_eligible:
        result = readiness_no_bet(decision.prediction.readiness_reason, probability)
    elif policy_code == "MODAL_ALL":
        result = modal_all(probability, prices)
    elif policy_code == "SELECTIVE_CONFIDENCE":
        result = selective_confidence(probability, float(policy_variant), prices)
    elif policy_code == "VALUE":
        result = value_policy(probability, prices, float(policy_variant))
    else:
        raise CapitalRuntimeInvariantError(f"UNSUPPORTED_DECISION_POLICY:{policy_code}")
    selected = result.selected_observation
    price = _decimal(result.selected_price)
    model_probability = _decimal(result.model_probability)
    expected_value = _decimal(result.expected_value)
    return ExecutionCandidate(
        work_item,
        decision,
        result,
        price,
        selected.pk if selected else None,
        model_probability,
        expected_value,
    )


def _basis_values(config, candidate):
    decision = candidate.decision
    result = candidate.result
    work = candidate.work_item
    return {
        "config": config,
        "match": work.match,
        "prediction": decision.prediction if decision else None,
        "originating_decision": decision,
        "decision_policy_code": decision.policy_code if decision else "MODAL_ALL",
        "decision_policy_variant": decision.policy_variant if decision else "",
        "decision_policy_version": (
            decision.policy_version
            if decision
            else DECISION_POLICY_VERSIONS["MODAL_ALL"]
        ),
        "decision_policy_config": result.config if result else {},
        "action": result.action if result else Decision.ACTION_NO_BET,
        "reason": result.reason if result else "NO_DECISION_AT_EXECUTION",
        "model_probability": candidate.model_probability,
        "selected_odds_observation_id": candidate.selected_observation_id,
        "selected_price": candidate.selected_price,
        "expected_value": candidate.expected_value,
        "capture_work_item": work,
        "capture_run": work.run,
        "execution_at": work.completed_at or work.run.completed_at,
        "evidence_not_before": work.executed_at,
        "evidence_cutoff": work.run.completed_at,
        "provenance": {
            "window": "market-t30m",
            "actual_event_time": True,
            "price_frozen": True,
        },
    }


def _state_exists(config, match):
    return CapitalExecutionState.objects.filter(config=config, match=match).exists()


def _candidate_from_basis(basis):
    work = basis.capture_work_item
    if (
        work is None
        or work.status not in ACCEPTED_CAPTURE_STATUSES
        or work.purpose != CaptureWorkItem.Purpose.ODDS_CAPTURE
        or work.intended_window != "market-t30m"
        or work.match_id != basis.match_id
        or work.run_id != basis.capture_run_id
    ):
        raise CapitalRuntimeInvariantError("PARTIAL_EXECUTION_BASIS_WITHOUT_VALID_T30")
    result = PolicyResult(
        action=basis.action,
        reason=basis.reason,
        model_probability=basis.model_probability,
        selected_observation=basis.selected_odds_observation,
        selected_price=basis.selected_price,
        expected_value=basis.expected_value,
        config=basis.decision_policy_config,
    )
    return ExecutionCandidate(
        work,
        basis.originating_decision,
        result,
        basis.selected_price,
        basis.selected_odds_observation_id,
        basis.model_probability,
        basis.expected_value,
    )


def _partially_processed_execution_candidates(configs):
    """Recover only fulfilled T-30 events already anchored by partial Capital state."""

    config_ids = [config.pk for config in configs]
    partial_match_ids = list(
        CapitalExecutionState.objects.filter(config_id__in=config_ids)
        .values("match_id")
        .annotate(config_count=Count("config_id", distinct=True))
        .filter(config_count__lt=len(config_ids))
        .values_list("match_id", flat=True)
    )
    if not partial_match_ids:
        return ()
    states_by_match = {}
    for state in (
        CapitalExecutionState.objects.filter(
            config_id__in=config_ids,
            match_id__in=partial_match_ids,
        )
        .select_related(
            "execution_basis__capture_work_item__run",
            "execution_basis__capture_work_item__match",
            "execution_basis__originating_decision",
            "execution_basis__selected_odds_observation",
        )
        .order_by("match_id", "config_id")
    ):
        states_by_match.setdefault(state.match_id, []).append(state)
    fulfilled_by_match = {}
    for work in (
        CaptureWorkItem.objects.filter(
            match_id__in=partial_match_ids,
            purpose=CaptureWorkItem.Purpose.ODDS_CAPTURE,
            intended_window="market-t30m",
            status__in=ACCEPTED_CAPTURE_STATUSES,
        )
        .select_related("run", "match")
        .order_by("match_id", "run__completed_at", "id")
    ):
        fulfilled_by_match.setdefault(work.match_id, work)
    candidates = []
    for match_id in sorted(states_by_match):
        states = states_by_match[match_id]
        anchored = next(
            (state.execution_basis for state in states if state.execution_basis_id),
            None,
        )
        if anchored is not None:
            candidates.append(_candidate_from_basis(anchored))
            continue
        reasons = {state.non_placement_reason for state in states}
        work = fulfilled_by_match.get(match_id)
        if reasons == {"UNAVAILABLE_NO_DECISION_AT_EXECUTION"} and work is not None:
            candidates.append(
                ExecutionCandidate(work, None, None, None, None, None, None)
            )
            continue
        raise CapitalRuntimeInvariantError(
            f"AMBIGUOUS_PARTIAL_EXECUTION_EVIDENCE:{match_id}"
        )
    return tuple(candidates)


def _terminal_state(config, match, reason, at, *, basis=None, diagnostics=None):
    state, created = CapitalExecutionState.objects.get_or_create(
        config=config,
        match=match,
        defaults={
            "status": CapitalExecutionState.Status.NOT_PLACED,
            "non_placement_reason": reason,
            "execution_basis": basis,
            "terminal_at": at,
            "diagnostics": diagnostics or {},
        },
    )
    return state, created


@transaction.atomic
def place_candidate(config_id, candidate):
    """Apply one config-scoped placement mutation under a row lock."""

    config = CapitalRuntimeConfig.objects.select_for_update().get(pk=config_id)
    match = candidate.match
    if _state_exists(config, match):
        return "NO_WORK"
    event_at = candidate.work_item.completed_at or candidate.work_item.run.completed_at
    if config.status != CapitalRuntimeConfig.Status.ACTIVE:
        _, created = _terminal_state(config, match, "INELIGIBLE", event_at)
        return "NOT_PLACED" if created else "NO_WORK"
    if candidate.decision is None:
        _, created = _terminal_state(
            config,
            match,
            "UNAVAILABLE_NO_DECISION_AT_EXECUTION",
            event_at,
        )
        return "NOT_PLACED" if created else "NO_WORK"
    basis = CapitalExecutionBasis.objects.create(**_basis_values(config, candidate))
    if candidate.result.action == Decision.ACTION_NO_BET:
        _terminal_state(config, match, "NO_BET", event_at, basis=basis)
        return "NOT_PLACED"
    if candidate.selected_price is None or candidate.selected_observation_id is None:
        _terminal_state(config, match, "NO_EXECUTION_PRICE", event_at, basis=basis)
        return "NOT_PLACED"
    open_count = CapitalPosition.objects.filter(
        config=config, status=CapitalPosition.Status.OPEN
    ).count()
    if open_count >= config.max_lanes:
        _terminal_state(config, match, "EXPIRED_CAPACITY", event_at, basis=basis)
        return "NOT_PLACED"
    policy = make_policy(config.policy_code, config.policy_config)
    policy_state = _decimal_state(config.policy_state)
    decision = CapitalDecision(
        source_id=candidate.decision.pk,
        decision_time=event_at,
        action=candidate.result.action,
        outcome="",
        price=candidate.selected_price,
        probability=candidate.model_probability,
        observation_id=candidate.selected_observation_id,
        observation_time=candidate.work_item.executed_at,
    )
    request = policy.request(decision, config.bankroll_equity, policy_state)
    if request.termination_reason:
        config.status = CapitalRuntimeConfig.Status.TERMINATED
        config.practical_ruin = True
        config.termination_reason = request.termination_reason
        config.completed_at = event_at
        config.save(
            update_fields=[
                "status",
                "practical_ruin",
                "termination_reason",
                "completed_at",
                "modified",
            ]
        )
        _terminal_state(
            config,
            match,
            "INELIGIBLE",
            event_at,
            basis=basis,
            diagnostics={"policy_reason": request.termination_reason},
        )
        return "NOT_PLACED"
    if request.requested <= ZERO or request.applied <= ZERO:
        _terminal_state(
            config,
            match,
            "INELIGIBLE",
            event_at,
            basis=basis,
            diagnostics={"policy_reason": request.reason},
        )
        return "NOT_PLACED"
    available_before = config.available_cash
    if request.requested > available_before:
        _terminal_state(
            config,
            match,
            "INSUFFICIENT_AVAILABLE_CASH",
            event_at,
            basis=basis,
            diagnostics={
                "requested_stake": str(request.requested),
                "available_cash": str(available_before),
            },
        )
        return "NOT_PLACED"
    equity_before = config.bankroll_equity
    reserved_before = config.reserved_exposure
    config.reserved_exposure += request.applied
    if config.reserved_exposure > config.bankroll_equity:
        raise CapitalRuntimeInvariantError("NEGATIVE_AVAILABLE_CASH")
    config.peak_reserved_exposure = max(
        config.peak_reserved_exposure, config.reserved_exposure
    )
    config.save(
        update_fields=["reserved_exposure", "peak_reserved_exposure", "modified"]
    )
    position = CapitalPosition.objects.create(
        config=config,
        match=match,
        execution_basis=basis,
        placed_at=event_at,
        requested_stake=request.requested,
        applied_stake=request.applied,
        policy_step=request.step,
        request_metadata=json_decimal(request.metadata),
        placement_equity_before=equity_before,
        placement_reserved_before=reserved_before,
        placement_available_before=available_before,
        placement_equity_after=config.bankroll_equity,
        placement_reserved_after=config.reserved_exposure,
        placement_available_after=config.available_cash,
        policy_state_before=json_decimal(policy_state),
        policy_state_after=json_decimal(policy_state),
        cap_hit=request.cap_hit,
        shortfall=request.shortfall,
    )
    CapitalExecutionState.objects.create(
        config=config,
        match=match,
        status=CapitalExecutionState.Status.PLACED,
        execution_basis=basis,
        position=position,
    )
    return "PLACED"


def reconcile_execution_events(capture_run_id, *, at=None):
    """Consume current or partially processed durable final T-30 evidence."""

    configs = provision_automatic_configs()
    work_items = []
    if capture_run_id:
        work_items = list(
            CaptureWorkItem.objects.filter(
                run_id=capture_run_id,
                purpose=CaptureWorkItem.Purpose.ODDS_CAPTURE,
                intended_window="market-t30m",
                match__isnull=False,
            )
            .select_related("run", "match")
            .order_by("match__kickoff", "match_id", "id")
        )
    candidates_by_match = {
        candidate.match.pk: candidate
        for candidate in _partially_processed_execution_candidates(configs)
    }
    missed = {
        row.match_id: row
        for row in work_items
        if row.status == CaptureWorkItem.Status.MISSED_WINDOW
        and row.match_id not in candidates_by_match
    }
    for row in work_items:
        if (
            row.status in ACCEPTED_CAPTURE_STATUSES
            and row.match_id not in candidates_by_match
        ):
            candidates_by_match[row.match_id] = build_execution_candidate(row)
            missed.pop(row.match_id, None)
    placed = not_placed = 0
    for match_id, work in missed.items():
        for config in configs:
            _, created = _terminal_state(
                config,
                work.match,
                "MISSED_EXECUTION_WINDOW",
                work.completed_at or work.run.completed_at or timezone.now(),
                diagnostics={"capture_work_item_id": work.pk},
            )
            not_placed += int(created)
    candidates = list(candidates_by_match.values())
    candidates.sort(
        key=lambda row: (
            -(
                row.expected_value
                if row.expected_value is not None
                else Decimal("-Infinity")
            ),
            row.match.kickoff,
            row.match.pk,
            row.decision.pk if row.decision else 0,
        )
    )
    for config in configs:
        for candidate in candidates:
            outcome = place_candidate(config.pk, candidate)
            placed += int(outcome == "PLACED")
            not_placed += int(outcome == "NOT_PLACED")
    status = "PRODUCED" if placed or not_placed else "NO_WORK"
    return RuntimeResult(
        status,
        configs=len(configs),
        config_ids=tuple(config.pk for config in configs),
        placed=placed,
        not_placed=not_placed,
    )


@transaction.atomic
def observe_terminal_result(match, *, known_at=None, provenance=None):
    """Persist canonical terminal knowledge without backdating it."""

    if not isinstance(match, Match):
        match = Match.objects.get(pk=match)
    if match.status_short not in TERMINAL_RESULT_STATUSES:
        return None, False
    if match.status_short in FINISHED_STATUSES and not match.outcome:
        return None, False
    ref = (
        MatchSourceRef.objects.filter(
            match=match,
            source__code=API_FOOTBALL_CODE,
            reconciliation_status=ReconciliationStatus.RESOLVED,
        )
        .select_related("source")
        .first()
    )
    if ref is None:
        return None, False
    known_at = known_at or timezone.now()
    observation, created = CapitalResultObservation.objects.get_or_create(
        match=match,
        defaults={
            "source": ref.source,
            "match_source_ref": ref,
            "status_short": match.status_short,
            "outcome": match.outcome,
            "result_known_at": known_at,
            "provider_observed_at": match.observed_at,
            "provenance": provenance or {"authority": "API_FOOTBALL_CANONICAL"},
        },
    )
    if not created and (
        observation.status_short != match.status_short
        or observation.outcome != match.outcome
    ):
        raise CapitalRuntimeInvariantError("CANONICAL_RESULT_CONFLICT")
    return observation, created


@transaction.atomic
def settle_position(position_id, observation_id, *, settled_at=None):
    """Release exposure and apply realized P&L exactly once."""

    position = (
        CapitalPosition.objects.select_for_update()
        .select_related("execution_basis")
        .get(pk=position_id)
    )
    if position.status != CapitalPosition.Status.OPEN:
        return "NO_WORK"
    config = CapitalRuntimeConfig.objects.select_for_update().get(pk=position.config_id)
    observation = CapitalResultObservation.objects.get(pk=observation_id)
    if observation.match_id != position.match_id:
        raise CapitalRuntimeInvariantError("RESULT_POSITION_MATCH_MISMATCH")
    settled_at = settled_at or timezone.now()
    state_before = _decimal_state(position.policy_state_before)
    price = position.execution_basis.selected_price
    if observation.status_short in VOID_STATUSES:
        status = CapitalPosition.Status.VOID
        pnl = ZERO
        state_after = state_before
    else:
        won = position.execution_basis.action == observation.outcome
        status = (
            CapitalPosition.Status.SETTLED_WIN
            if won
            else CapitalPosition.Status.SETTLED_LOSS
        )
        pnl = (
            position.applied_stake * (price - Decimal("1"))
            if won
            else -position.applied_stake
        )
        policy = make_policy(config.policy_code, config.policy_config)
        request = StakeRequest(
            position.requested_stake,
            position.applied_stake,
            cap_hit=position.cap_hit,
            shortfall=position.shortfall,
            step=position.policy_step,
            metadata=_decimal_state(position.request_metadata),
        )
        state_after, _ = policy.settle(state_before, request, won)
    if config.reserved_exposure < position.applied_stake:
        raise CapitalRuntimeInvariantError("RESERVED_EXPOSURE_UNDERFLOW")
    config.reserved_exposure -= position.applied_stake
    config.bankroll_equity += pnl
    config.policy_state = json_decimal(state_after)
    config.peak_equity = max(config.peak_equity, config.bankroll_equity)
    if config.peak_equity > ZERO:
        drawdown = (config.peak_equity - config.bankroll_equity) / config.peak_equity
        config.maximum_drawdown = max(config.maximum_drawdown, drawdown)
    if config.bankroll_equity <= ZERO:
        config.status = CapitalRuntimeConfig.Status.TERMINATED
        config.practical_ruin = True
        config.termination_reason = "BANKROLL_DEPLETED"
        config.completed_at = settled_at
    config.save()
    position.status = status
    position.result_observation = observation
    position.result_known_at = observation.result_known_at
    position.settled_at = settled_at
    position.realized_pnl = pnl
    position.settlement_equity_after = config.bankroll_equity
    position.settlement_reserved_after = config.reserved_exposure
    position.settlement_available_after = config.available_cash
    position.policy_state_after = json_decimal(state_after)
    position.practical_ruin = config.practical_ruin
    position.termination_reason = config.termination_reason
    position.debt_status = CapitalPosition.DebtStatus.RESOLVED
    position.result_refresh_error = ""
    position.save()
    return status


def settle_observation(observation, *, settled_at=None):
    position_ids = list(
        CapitalPosition.objects.filter(
            match_id=observation.match_id, status=CapitalPosition.Status.OPEN
        ).values_list("id", flat=True)
    )
    settled = 0
    for position_id in position_ids:
        settled += int(
            settle_position(position_id, observation.pk, settled_at=settled_at)
            != "NO_WORK"
        )
    return settled


def settle_locally_known_open_positions(*, known_at=None):
    knowledge_at = known_at or timezone.now()
    match_ids = list(
        CapitalPosition.objects.filter(status=CapitalPosition.Status.OPEN)
        .filter(match__status_short__in=TERMINAL_RESULT_STATUSES)
        .values_list("match_id", flat=True)
        .distinct()
    )
    settled = 0
    for match in Match.objects.filter(pk__in=match_ids):
        observation, _ = observe_terminal_result(match, known_at=knowledge_at)
        if observation:
            settled += settle_observation(observation, settled_at=knowledge_at)
            continue
        has_ref = MatchSourceRef.objects.filter(
            match=match,
            source__code=API_FOOTBALL_CODE,
            reconciliation_status=ReconciliationStatus.RESOLVED,
        ).exists()
        reason = (
            "UNRESOLVED_CANONICAL_OUTCOME"
            if has_ref
            else "MISSING_API_FOOTBALL_MATCH_REF"
        )
        _mark_provider_degraded(
            list(
                CapitalPosition.objects.filter(
                    match=match, status=CapitalPosition.Status.OPEN
                ).values_list("id", flat=True)
            ),
            knowledge_at,
            CapitalRuntimeInvariantError(reason),
        )
    return settled


def _mark_provider_degraded(position_ids, at, error):
    CapitalPosition.objects.filter(
        pk__in=position_ids, status=CapitalPosition.Status.OPEN
    ).update(
        debt_status=CapitalPosition.DebtStatus.DEGRADED,
        result_refresh_attempted_at=at,
        result_refresh_error=f"{type(error).__name__}:{error}"[:500],
    )


def refresh_open_result_debt(*, at=None, client_factory=APIFootballClient):
    """Refresh unique overdue API-Football fixtures in bounded batches of twenty."""

    at = at or timezone.now()
    capture_config = CaptureConfig.from_settings()
    delay = capture_config.result_delay
    due = list(
        CapitalPosition.objects.filter(
            status=CapitalPosition.Status.OPEN,
            match__kickoff__lte=at - delay,
        )
        .select_related("match__season__competition")
        .order_by("match__kickoff", "match_id", "id")
    )
    if not due:
        return RuntimeResult("NO_WORK")
    position_ids = [row.pk for row in due]
    CapitalPosition.objects.filter(pk__in=position_ids).update(
        debt_status=CapitalPosition.DebtStatus.OVERDUE
    )
    positions_by_match = {}
    for position in due:
        positions_by_match.setdefault(position.match_id, []).append(position)
    match_by_id = {
        match_id: positions[0].match
        for match_id, positions in positions_by_match.items()
    }

    def debt_priority(match_id):
        attempted = [
            position.result_refresh_attempted_at
            for position in positions_by_match[match_id]
            if position.result_refresh_attempted_at is not None
        ]
        match = match_by_id[match_id]
        if not attempted:
            return (0, match.kickoff, match.pk)
        return (1, max(attempted), match.kickoff, match.pk)

    ordered_match_ids = sorted(match_by_id, key=debt_priority)
    source = Source.objects.get(code=API_FOOTBALL_CODE)
    refs = {
        ref.match_id: ref
        for ref in MatchSourceRef.objects.filter(
            source=source,
            match_id__in=match_by_id,
            reconciliation_status=ReconciliationStatus.RESOLVED,
        )
    }
    missing = set(match_by_id) - set(refs)
    if missing:
        _mark_provider_degraded(
            [row.pk for row in due if row.match_id in missing],
            at,
            CapitalRuntimeInvariantError("MISSING_API_FOOTBALL_MATCH_REF"),
        )
    external_debt = [
        (refs[match_id].external_id, match_by_id[match_id])
        for match_id in ordered_match_ids
        if match_id in refs
    ]
    external_to_match = dict(external_debt)
    if not external_to_match:
        return RuntimeResult(
            "DEGRADED", open_debt=len(due), errors=("MISSING_API_FOOTBALL_MATCH_REF",)
        )
    calls = settled = 0
    errors = []
    client = None
    admitted_ids = [
        external_id
        for external_id, _ in external_debt[: 20 * capture_config.max_provider_attempts]
    ]
    admitted_position_ids = [
        position.pk
        for external_id in admitted_ids
        for position in positions_by_match[external_to_match[external_id].pk]
    ]
    attempted_position_ids = []
    try:
        client = client_factory(
            max_pages=capture_config.max_operation_pages,
            max_retries=capture_config.max_retries,
            daily_reserve=capture_config.mandatory_reserve,
        )

        def guard(active_client):
            if active_client.calls >= capture_config.max_provider_attempts:
                raise APIFootballOperationBudgetError(
                    "Capital result refresh reached its provider-attempt bound."
                )

        client.attempt_guard = guard
        for offset in range(0, len(admitted_ids), 20):
            batch = admitted_ids[offset : offset + 20]
            batch_match_ids = [external_to_match[item].pk for item in batch]
            batch_position_ids = [
                position.pk
                for match_id in batch_match_ids
                for position in positions_by_match[match_id]
            ]
            attempted_position_ids.extend(batch_position_ids)
            CapitalPosition.objects.filter(
                pk__in=batch_position_ids,
                status=CapitalPosition.Status.OPEN,
            ).update(
                result_refresh_attempted_at=at,
                result_refresh_error="",
            )
            payloads = client.get_all("fixtures", {"ids": "-".join(batch)})
            calls += 1
            competition_ids = {
                external_to_match[item].season.competition_id for item in batch
            }
            competitions = {
                ref.external_id: ref.competition
                for ref in CompetitionSourceRef.objects.filter(
                    source=source,
                    competition_id__in=competition_ids,
                    reconciliation_status=ReconciliationStatus.RESOLVED,
                ).select_related("competition")
            }
            sync_fixture_payloads(payloads, competitions)
            knowledge_at = timezone.now()
            for match in Match.objects.filter(
                pk__in=[external_to_match[item].pk for item in batch]
            ):
                observation, _ = observe_terminal_result(
                    match,
                    known_at=knowledge_at,
                    provenance={
                        "authority": "API_FOOTBALL_CANONICAL",
                        "batched_fixture_ids": batch,
                    },
                )
                if observation:
                    settled += settle_observation(observation, settled_at=knowledge_at)
    except APIFootballError as error:
        errors.append(f"{type(error).__name__}:{error}"[:500])
        _mark_provider_degraded(
            attempted_position_ids or admitted_position_ids,
            at,
            error,
        )
    open_debt = CapitalPosition.objects.filter(
        pk__in=position_ids, status=CapitalPosition.Status.OPEN
    ).count()
    status = "DEGRADED" if errors or open_debt else "PRODUCED"
    return RuntimeResult(
        status,
        settled=settled,
        provider_calls=(client.calls if client is not None else calls),
        open_debt=open_debt,
        errors=tuple(errors),
    )


def run_automatic_runtime(
    *, capture_run_id=None, at=None, client_factory=APIFootballClient
):
    """Pipeline-owned automatic placement, catch-up, and settlement boundary."""

    at = at or timezone.now()
    configs = provision_automatic_configs()
    execution = reconcile_execution_events(capture_run_id, at=at)
    local_settled = settle_locally_known_open_positions()
    refresh = refresh_open_result_debt(at=at, client_factory=client_factory)
    status = (
        "DEGRADED"
        if refresh.status == "DEGRADED"
        else (
            "PRODUCED"
            if execution.status == "PRODUCED" or local_settled or refresh.settled
            else "NO_WORK"
        )
    )
    return RuntimeResult(
        status,
        configs=len(configs),
        config_ids=tuple(config.pk for config in configs),
        placed=execution.placed,
        not_placed=execution.not_placed,
        settled=local_settled + refresh.settled,
        provider_calls=refresh.provider_calls,
        open_debt=refresh.open_debt,
        errors=refresh.errors,
    )
