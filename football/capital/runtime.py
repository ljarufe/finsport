"""FS-016 persistent, simulation-only Capital event-time runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Count, Q
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
    fixture_by_id,
    fixtures_by_date,
    relevant_fixture_payloads,
)
from football.quota import (
    DIRECTED_RESULT_FALLBACK,
    OPEN_RESULT_TIMEZONE,
    dynamic_reserve,
    quota_state,
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
    pending_capacity: int = 0
    settled: int = 0
    provider_calls: int = 0
    open_debt: int = 0
    result_debt_state: str = ""
    errors: tuple[str, ...] = ()
    evaluations: tuple[dict, ...] = ()

    def as_dict(self):
        return {
            "status": self.status,
            "runtime_version": RUNTIME_VERSION,
            "execution_version": EXECUTION_VERSION,
            "configs": self.configs,
            "config_ids": list(self.config_ids),
            "placed": self.placed,
            "not_placed": self.not_placed,
            "pending_capacity": self.pending_capacity,
            "settled": self.settled,
            "provider_calls": self.provider_calls,
            "open_debt": self.open_debt,
            "result_debt_state": self.result_debt_state,
            "errors": list(self.errors),
            "evaluations": list(self.evaluations),
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


def provision_automatic_configs():
    """The normal runtime can only provision the reviewed FS-022 authority."""
    from football.strategy.deployment import provision

    return provision()


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
        "execution_at": (
            decision.decision_time
            if decision and config.identity.startswith("fs022:")
            else work.completed_at or work.run.completed_at
        ),
        "evidence_not_before": work.executed_at,
        "evidence_cutoff": work.run.completed_at,
        "provenance": {
            "window": work.intended_window,
            "actual_event_time": True,
            "price_frozen": True,
            **(
                {
                    "prospective_config_identity": decision.prediction.model_config.get(
                        "prospective_config_identity"
                    ),
                    "scientific_selection_config_identity": decision.prediction.model_config.get(
                        "scientific_selection_config_identity"
                    ),
                    "quote_ids": decision.prediction.diagnostics.get("quote_ids", []),
                    "source_id": work.source_id,
                    "market_id": work.market_id,
                    "selected_observation_id": candidate.selected_observation_id,
                }
                if decision and config.identity.startswith("fs022:")
                else {}
            ),
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
        or work.intended_window
        != (
            basis.config.strategy_epoch.binding.contract["capture_window"]
            if basis.config.strategy_epoch_id
            else "market-t30m"
        )
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


def _terminalize_pending(state, reason, at, *, diagnostics=None):
    """Finish the existing zero-exposure opportunity without replacing its basis."""

    state.status = CapitalExecutionState.Status.NOT_PLACED
    state.non_placement_reason = reason
    state.terminal_at = at
    if diagnostics:
        state.diagnostics = {**state.diagnostics, **diagnostics}
    state.save(
        update_fields=[
            "status",
            "non_placement_reason",
            "terminal_at",
            "diagnostics",
            "modified",
        ]
    )
    return "NOT_PLACED"


@transaction.atomic
def place_candidate(config_id, candidate, *, at=None):
    """Place from frozen T-30 evidence, or retain it while capacity is unavailable."""

    from football.strategy.clock import effective_now
    from football.strategy.deployment import admission_reason, locked_deployment
    from football.strategy.prospective import validate_candidate

    deployment = locked_deployment()
    config = CapitalRuntimeConfig.objects.select_for_update().get(pk=config_id)
    match = Match.objects.select_for_update().get(pk=candidate.match.pk)
    candidate.work_item.match = match
    state = (
        CapitalExecutionState.objects.select_for_update()
        .filter(config=config, match=match)
        .first()
    )
    if (
        state is not None
        and state.status != CapitalExecutionState.Status.PENDING_CAPACITY
    ):
        return "NO_WORK"
    if state is not None:
        candidate = _candidate_from_basis(state.execution_basis)
    event_at = candidate.work_item.completed_at or candidate.work_item.run.completed_at
    placement_at = (
        effective_now(planning_at=at)
        if config.identity.startswith(("fs022:", "fs023:"))
        else at or event_at
    )
    if placement_at >= match.kickoff and state is not None:
        return _terminalize_pending(state, "EXPIRED_CAPACITY", placement_at)
    blocked = admission_reason(deployment, config)
    if not blocked and deployment.config_id == config.pk:
        blocked = validate_candidate(
            candidate, deployment, basis=state.execution_basis if state else None
        )
    if blocked:
        if state is not None:
            return _terminalize_pending(state, blocked, placement_at)
        _, created = _terminal_state(config, match, blocked, placement_at)
        return "NOT_PLACED" if created else "NO_WORK"
    expired_new = state is None and placement_at >= match.kickoff
    if placement_at >= match.kickoff and state is not None:
        return _terminalize_pending(state, "EXPIRED_CAPACITY", placement_at)
    if config.status != CapitalRuntimeConfig.Status.ACTIVE:
        if state is not None:
            return _terminalize_pending(state, "INELIGIBLE", placement_at)
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
    basis = (
        state.execution_basis
        if state is not None
        else CapitalExecutionBasis.objects.create(**_basis_values(config, candidate))
    )
    if candidate.result.action == Decision.ACTION_NO_BET:
        _terminal_state(config, match, "NO_BET", event_at, basis=basis)
        return "NOT_PLACED"
    if candidate.selected_price is None or candidate.selected_observation_id is None:
        _terminal_state(config, match, "NO_EXECUTION_PRICE", event_at, basis=basis)
        return "NOT_PLACED"
    if expired_new:
        _terminal_state(
            config,
            match,
            "EXPIRED_CAPACITY",
            placement_at,
            basis=basis,
        )
        return "NOT_PLACED"
    open_count = CapitalPosition.objects.filter(
        config=config, status=CapitalPosition.Status.OPEN
    ).count()
    if open_count >= config.max_lanes:
        if state is None:
            CapitalExecutionState.objects.create(
                config=config,
                match=match,
                status=CapitalExecutionState.Status.PENDING_CAPACITY,
                execution_basis=basis,
                diagnostics={"reason": "NO_AVAILABLE_LANE"},
            )
            return "PENDING_CAPACITY"
        return "NO_WORK"
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
        diagnostics = {"policy_reason": request.termination_reason}
        if state is not None:
            return _terminalize_pending(
                state, "INELIGIBLE", placement_at, diagnostics=diagnostics
            )
        _terminal_state(
            config, match, "INELIGIBLE", event_at, basis=basis, diagnostics=diagnostics
        )
        return "NOT_PLACED"
    if request.requested <= ZERO or request.applied <= ZERO:
        diagnostics = {"policy_reason": request.reason}
        if state is not None:
            return _terminalize_pending(
                state, "INELIGIBLE", placement_at, diagnostics=diagnostics
            )
        _terminal_state(
            config,
            match,
            "INELIGIBLE",
            event_at,
            basis=basis,
            diagnostics=diagnostics,
        )
        return "NOT_PLACED"
    available_before = config.available_cash
    if request.requested > available_before:
        diagnostics = {
            "reason": "INSUFFICIENT_AVAILABLE_CASH",
            "requested_stake": str(request.requested),
            "available_cash": str(available_before),
        }
        if state is None:
            CapitalExecutionState.objects.create(
                config=config,
                match=match,
                status=CapitalExecutionState.Status.PENDING_CAPACITY,
                execution_basis=basis,
                diagnostics=diagnostics,
            )
        else:
            if state.diagnostics != diagnostics:
                state.diagnostics = diagnostics
                state.save(update_fields=["diagnostics", "modified"])
            return "NO_WORK"
        return "PENDING_CAPACITY"
    if config.identity.startswith(("fs022:", "fs023:")):
        placement_at = effective_now(planning_at=at)
        if placement_at >= match.kickoff:
            if state is not None:
                return _terminalize_pending(state, "EXPIRED_CAPACITY", placement_at)
            _terminal_state(
                config, match, "MISSED_EXECUTION_WINDOW", placement_at, basis=basis
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
        placed_at=placement_at,
        next_result_check_at=match.kickoff + timedelta(minutes=130),
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
    if state is None:
        CapitalExecutionState.objects.create(
            config=config,
            match=match,
            status=CapitalExecutionState.Status.PLACED,
            execution_basis=basis,
            position=position,
        )
    else:
        state.status = CapitalExecutionState.Status.PLACED
        state.position = position
        state.diagnostics = {**state.diagnostics, "placed_after_capacity_wait": True}
        state.save(update_fields=["status", "position", "diagnostics", "modified"])
    return "PLACED"


def reconcile_execution_events(capture_run_id, *, at=None):
    """Consume current or partially processed durable final T-30 evidence."""

    configs = provision_automatic_configs()
    if not configs or configs[0].identity.startswith(("fs022:", "fs023:")):
        from football.strategy.prospective import reconcile_global

        return reconcile_global(capture_run_id, at=at or timezone.now())
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
    for state in (
        CapitalExecutionState.objects.filter(
            config__in=configs,
            status=CapitalExecutionState.Status.PENDING_CAPACITY,
            execution_basis__isnull=False,
        )
        .select_related(
            "execution_basis__capture_work_item__run",
            "execution_basis__capture_work_item__match",
            "execution_basis__originating_decision",
            "execution_basis__selected_odds_observation",
        )
        .order_by("match__kickoff", "match_id", "config_id")
    ):
        candidates_by_match.setdefault(
            state.match_id, _candidate_from_basis(state.execution_basis)
        )
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
    placed = not_placed = pending_capacity = 0
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
            outcome = (
                place_candidate(config.pk, candidate, at=at)
                if at is not None
                else place_candidate(config.pk, candidate)
            )
            placed += int(outcome == "PLACED")
            not_placed += int(outcome == "NOT_PLACED")
            pending_capacity += int(outcome == "PENDING_CAPACITY")
    status = "PRODUCED" if placed or not_placed or pending_capacity else "NO_WORK"
    return RuntimeResult(
        status,
        configs=len(configs),
        config_ids=tuple(config.pk for config in configs),
        placed=placed,
        not_placed=not_placed,
        pending_capacity=pending_capacity,
    )


@transaction.atomic
def observe_terminal_result(
    match, *, known_at=None, provenance=None, provider_result=None
):
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
    if ref is None and provider_result is None:
        return None, False
    known_at = known_at or timezone.now()
    observation, created = CapitalResultObservation.objects.get_or_create(
        match=match,
        defaults={
            "source": ref.source if ref is not None else None,
            "match_source_ref": ref,
            "provider_result": provider_result,
            "status_short": match.status_short,
            "outcome": match.outcome,
            "result_known_at": known_at,
            "provider_observed_at": (
                provider_result.provider_observed_at
                if provider_result
                else match.observed_at
            ),
            "provenance": provenance
            or {
                "authority": (
                    provider_result.provider
                    if provider_result
                    else "API_FOOTBALL_CANONICAL"
                )
            },
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

    from football.strategy.deployment import locked_deployment

    locked_deployment()
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
    if config.bankroll_equity <= ZERO and not config.identity.startswith(
        ("fs022:", "fs023:")
    ):
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
    position.next_result_check_at = None
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
        if match.provider_results.filter(conflict=True).exists():
            _mark_provider_degraded(
                list(
                    CapitalPosition.objects.filter(
                        match=match, status=CapitalPosition.Status.OPEN
                    ).values_list("id", flat=True)
                ),
                knowledge_at,
                CapitalRuntimeInvariantError("RESULT_CONFLICT"),
            )
            continue
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


def refresh_open_result_debt(
    *, at=None, client_factory=APIFootballClient, bsd_client_factory=None
):
    """Coalesce due OPEN debt into Lima-date sweeps and narrow directed recovery."""

    at = at or timezone.now()
    capture_config = CaptureConfig.from_settings()
    lima = ZoneInfo(OPEN_RESULT_TIMEZONE)
    due = list(
        CapitalPosition.objects.filter(
            status=CapitalPosition.Status.OPEN,
        )
        .exclude(match__status_short="PST")
        .exclude(result_refresh_error="RESULT_CONFLICT")
        .filter(
            Q(next_result_check_at__lte=at)
            | Q(
                next_result_check_at__isnull=True,
                match__kickoff__lte=at - timedelta(minutes=130),
            )
        )
        .select_related("match__season__competition")
        .order_by("match__kickoff", "match_id", "id")
    )
    from football.providers.bsd import BSDClient
    from football.result_routing import recheck_pending_conflicts

    conflict_calls, conflict_errors = recheck_pending_conflicts(
        at=at, client_factory=bsd_client_factory or BSDClient
    )
    due = [
        position
        for position in due
        if not position.match.provider_results.filter(conflict=True).exists()
    ]
    if not due:
        return RuntimeResult(
            (
                "DEGRADED"
                if conflict_errors
                else "PRODUCED" if conflict_calls else "NO_WORK"
            ),
            provider_calls=conflict_calls,
            errors=tuple(conflict_errors),
        )
    position_ids = [row.pk for row in due]
    CapitalPosition.objects.filter(pk__in=position_ids).update(
        debt_status=CapitalPosition.DebtStatus.OVERDUE
    )
    from football.providers.bsd import BSDClient
    from football.result_routing import process_due_bsd

    handled, bsd_settled, bsd_errors = process_due_bsd(
        due, at=at, client_factory=bsd_client_factory or BSDClient
    )
    due = [row for row in due if row.match_id not in handled]
    if not due:
        return RuntimeResult(
            "DEGRADED" if bsd_errors else "PRODUCED",
            settled=bsd_settled,
            open_debt=0,
            errors=tuple(bsd_errors),
        )
    position_ids = [row.pk for row in due]
    due_by_match = {}
    for position in due:
        due_by_match.setdefault(position.match_id, []).append(position)
    all_open = list(
        CapitalPosition.objects.filter(status=CapitalPosition.Status.OPEN)
        .exclude(match__status_short="PST")
        .select_related("match__season__competition")
    )
    match_by_id = {position.match_id: position.match for position in all_open}
    date_by_match = {
        match_id: match.kickoff.astimezone(lima).date()
        for match_id, match in match_by_id.items()
    }

    def debt_priority(match_id):
        attempted = [
            position.result_refresh_attempted_at
            for position in due_by_match[match_id]
            if position.result_refresh_attempted_at is not None
        ]
        match = match_by_id[match_id]
        if not attempted:
            return (0, match.kickoff, match.pk)
        return (1, max(attempted), match.kickoff, match.pk)

    due_dates = {date_by_match[match_id] for match_id in due_by_match}
    relevant_match_ids = {
        match_id
        for match_id, kickoff_date in date_by_match.items()
        if kickoff_date in due_dates
    }
    source = Source.objects.get(code=API_FOOTBALL_CODE)
    refs = {
        ref.match_id: ref
        for ref in MatchSourceRef.objects.filter(
            source=source,
            match_id__in=relevant_match_ids,
            reconciliation_status=ReconciliationStatus.RESOLVED,
        )
    }
    missing = set(due_by_match) - set(refs)
    if missing:
        _mark_provider_degraded(
            [row.pk for row in due if row.match_id in missing],
            at,
            CapitalRuntimeInvariantError("MISSING_API_FOOTBALL_MATCH_REF"),
        )
    due_with_ref = set(due_by_match) & set(refs)
    missing_ref_errors = ["MISSING_API_FOOTBALL_MATCH_REF"] if missing else []
    if not due_with_ref:
        return RuntimeResult(
            "DEGRADED", open_debt=len(due), errors=tuple(missing_ref_errors)
        )
    dates = sorted(
        {date_by_match[match_id] for match_id in due_with_ref},
        key=lambda day: (
            min(
                debt_priority(match_id)
                for match_id in due_with_ref
                if date_by_match[match_id] == day
            ),
            day,
        ),
    )
    relevant_by_date = {
        day: {
            refs[match_id].external_id: match_by_id[match_id]
            for match_id in relevant_match_ids & set(refs)
            if date_by_match[match_id] == day
        }
        for day in dates
    }
    competition_ids = {
        match_by_id[match_id].season.competition_id
        for match_id in relevant_match_ids & set(refs)
    }
    competitions = {
        ref.external_id: ref.competition
        for ref in CompetitionSourceRef.objects.filter(
            source=source,
            competition_id__in=competition_ids,
            reconciliation_status=ReconciliationStatus.RESOLVED,
        ).select_related("competition")
    }
    settled = bsd_settled
    errors = [*missing_ref_errors, *bsd_errors]
    client = None
    active_mode = "date_sweep"
    active_match_ids = {
        match_id for match_id in due_with_ref if date_by_match[match_id] == dates[0]
    }
    calls_before_attempt = 0
    current_quota = quota_state(at, capture_config)
    reserve = dynamic_reserve(at, capture_config)
    higher_priority_reserve = (
        reserve["fixture"] + reserve["t10"] + reserve["execution_quote"]
    )
    available_work = max(0, current_quota["remaining"] - higher_priority_reserve)
    if current_quota["basis"] == "BOUNDED_BOOTSTRAP":
        available_work = min(1, current_quota["remaining"])
    elif current_quota["basis"] == "HEADER_STALE_EPOCH":
        available_work = int(
            current_quota["stale_establishing_attempt_available"]
            and higher_priority_reserve == 0
        )
    admitted_dates = dates[: min(capture_config.max_provider_attempts, available_work)]
    if not admitted_dates:
        return RuntimeResult(
            "DEGRADED" if errors else "NO_WORK",
            open_debt=len(due),
            errors=tuple(errors),
        )

    def due_position_ids(match_ids):
        return [
            position.pk for match_id in match_ids for position in due_by_match[match_id]
        ]

    def schedule_due(match_id, next_check, *, error=""):
        CapitalPosition.objects.filter(
            pk__in=due_position_ids((match_id,)),
            status=CapitalPosition.Status.OPEN,
        ).update(
            next_result_check_at=next_check,
            debt_status=(
                CapitalPosition.DebtStatus.DEGRADED
                if error
                else CapitalPosition.DebtStatus.OVERDUE
            ),
            result_refresh_attempted_at=at,
            result_refresh_error=error,
        )

    @transaction.atomic
    def consume_payloads(payloads, expected, due_match_ids, *, mode, day):
        from football.strategy.deployment import locked_deployment, update_depletion

        # The request has already returned; admission is locked only while its
        # complete result batch is applied, never while HTTP is in progress.
        locked_deployment()
        nonlocal settled
        selected = relevant_fixture_payloads(payloads, expected)
        accepted = {}
        if selected:
            _, accepted = sync_fixture_payloads(selected, competitions)
        usable = set()
        terminal_without_outcome = set()
        knowledge_at = timezone.now()
        for external_id, accepted_match in accepted.items():
            expected_match = expected.get(str(external_id))
            if expected_match is None or accepted_match.pk != expected_match.pk:
                continue
            match = Match.objects.get(pk=expected_match.pk)
            usable.add(match.pk)
            from football.result_provider import api_football_result, record
            from football.result_routing import maybe_promote_shadow

            provider_result = None
            if match.status_short in TERMINAL_RESULT_STATUSES:
                provider_result, disposition = record(
                    match,
                    api_football_result(
                        match,
                        external_id,
                        provenance={
                            "acquisition": mode,
                            "kickoff_date_lima": day.isoformat(),
                        },
                    ),
                    authoritative=True,
                )
                if disposition == "RESULT_CONFLICT":
                    errors.append(f"RESULT_CONFLICT:{match.pk}")
                    continue
                maybe_promote_shadow()
            observation, _ = observe_terminal_result(
                match,
                known_at=knowledge_at,
                provider_result=provider_result,
                provenance={
                    "authority": "API_FOOTBALL_CANONICAL",
                    "acquisition": mode,
                    "kickoff_date_lima": day.isoformat(),
                    "fixture_id": str(external_id),
                },
            )
            if observation:
                settled += settle_observation(observation, settled_at=knowledge_at)
            elif match.status_short == "PST":
                CapitalPosition.objects.filter(
                    match=match, status=CapitalPosition.Status.OPEN
                ).update(
                    next_result_check_at=None,
                    debt_status=CapitalPosition.DebtStatus.DEGRADED,
                    result_refresh_error="WAITING_FOR_FIXTURE_RECONCILIATION",
                )
            elif match.pk in due_match_ids:
                if match.status_short in FINISHED_STATUSES:
                    terminal_without_outcome.add(match.pk)
                else:
                    retry_minutes = 60 if match.status_short == "SUSP" else 30
                    schedule_due(match.pk, at + timedelta(minutes=retry_minutes))
        try:
            update_depletion(at=at)
        except (RuntimeError, ValueError) as error:
            errors.append(f"{type(error).__name__}:{error}"[:500])
        return usable, terminal_without_outcome

    try:
        client = client_factory(
            max_pages=capture_config.max_operation_pages,
            max_retries=capture_config.max_retries,
            daily_reserve=0,
        )

        def guard(active_client):
            if active_client.calls >= capture_config.max_provider_attempts:
                raise APIFootballOperationBudgetError(
                    "Capital result refresh reached its provider-attempt bound."
                )
            request_at = timezone.now()
            fresh_quota = quota_state(request_at, capture_config)
            observed_remaining = getattr(active_client, "daily_remaining", None)
            if (
                observed_remaining is None
                and fresh_quota["basis"] == "HEADER_STALE_EPOCH"
            ):
                live_reserve = dynamic_reserve(request_at, capture_config)
                higher_priority = (
                    live_reserve["fixture"]
                    + live_reserve["t10"]
                    + live_reserve["execution_quote"]
                )
                if (
                    active_client.calls == 0
                    and higher_priority == 0
                    and fresh_quota["stale_establishing_attempt_available"]
                ):
                    return
                raise APIFootballOperationBudgetError(
                    "A stale quota epoch permits only one critical establishing attempt."
                )
            live_remaining = fresh_quota["remaining"]
            if observed_remaining is not None:
                live_remaining = min(live_remaining, observed_remaining)
            live_reserve = dynamic_reserve(request_at, capture_config)
            higher_priority = (
                live_reserve["fixture"]
                + live_reserve["t10"]
                + live_reserve["execution_quote"]
            )
            if live_remaining - 1 < higher_priority:
                raise APIFootballOperationBudgetError(
                    "Capital result attempt would cross the dynamic reserve."
                )

        client.attempt_guard = guard
        for day in admitted_dates:
            expected = relevant_by_date[day]
            due_match_ids = {
                match_id for match_id in due_with_ref if date_by_match[match_id] == day
            }
            sweep_due = {
                match_id
                for match_id in due_match_ids
                if any(
                    not position.result_refresh_error.startswith(
                        DIRECTED_RESULT_FALLBACK
                    )
                    for position in due_by_match[match_id]
                )
            }
            if sweep_due:
                active_mode = "date_sweep"
                active_match_ids = sweep_due
                calls_before_attempt = client.calls
                if hasattr(client, "set_audit_context"):
                    client.set_audit_context(
                        "OPEN_RESULT_BATCH",
                        f"open-results:date:{day.isoformat()}:{at.isoformat()}",
                        request_metadata={
                            "acquisition": "date_sweep",
                            "kickoff_date_lima": day.isoformat(),
                            "trigger_match_ids": sorted(sweep_due),
                            "relevant_fixture_ids": sorted(expected),
                        },
                        represented_fixture_count=len(expected),
                    )
                payloads = fixtures_by_date(client, day, OPEN_RESULT_TIMEZONE)
                CapitalPosition.objects.filter(
                    pk__in=due_position_ids(sweep_due),
                    status=CapitalPosition.Status.OPEN,
                ).update(result_refresh_attempted_at=at)
                usable, blank_terminal = consume_payloads(
                    payloads,
                    expected,
                    due_match_ids,
                    mode="date_sweep",
                    day=day,
                )
                for match_id in (sweep_due - usable) | blank_terminal:
                    schedule_due(match_id, at, error=DIRECTED_RESULT_FALLBACK)
            # A successful sweep can settle a known fallback incidentally. Only
            # one still-due directed recovery is attempted per date and wake.
            fallback_due = sorted(
                (
                    match_id
                    for match_id in due_match_ids
                    if CapitalPosition.objects.filter(
                        pk__in=due_position_ids((match_id,)),
                        status=CapitalPosition.Status.OPEN,
                        next_result_check_at__lte=at,
                        result_refresh_error__startswith=DIRECTED_RESULT_FALLBACK,
                    ).exists()
                ),
                key=debt_priority,
            )
            if not fallback_due:
                continue
            match_id = fallback_due[0]
            external_id = refs[match_id].external_id
            active_mode = "directed_id_fallback"
            active_match_ids = {match_id}
            calls_before_attempt = client.calls
            if hasattr(client, "set_audit_context"):
                client.set_audit_context(
                    "OPEN_RESULT_BATCH",
                    f"open-results:id:{external_id}:{at.isoformat()}",
                    request_metadata={
                        "acquisition": "directed_id_fallback",
                        "reason": DIRECTED_RESULT_FALLBACK,
                        "match_id": match_id,
                        "kickoff_date_lima": day.isoformat(),
                    },
                    represented_fixture_count=1,
                )
            payloads = fixture_by_id(client, external_id)
            CapitalPosition.objects.filter(
                pk__in=due_position_ids((match_id,)),
                status=CapitalPosition.Status.OPEN,
            ).update(result_refresh_attempted_at=at)
            usable, blank_terminal = consume_payloads(
                payloads,
                {external_id: match_by_id[match_id]},
                {match_id},
                mode="directed_id_fallback",
                day=day,
            )
            if match_id not in usable or match_id in blank_terminal:
                schedule_due(
                    match_id,
                    at + timedelta(minutes=30),
                    error=DIRECTED_RESULT_FALLBACK,
                )
    except (APIFootballError, OSError) as error:
        errors.append(f"{type(error).__name__}:{error}"[:500])
        # The current due work remains unresolved; never infer terminal truth
        # from a blocked attempt or a provider error.
        if active_mode == "directed_id_fallback":
            if (
                not isinstance(error, APIFootballOperationBudgetError)
                or client is None
                or client.calls > calls_before_attempt
            ):
                schedule_due(
                    next(iter(active_match_ids)),
                    at + timedelta(minutes=30),
                    error=f"{DIRECTED_RESULT_FALLBACK}:{type(error).__name__}",
                )
        else:
            affected = due_position_ids(active_match_ids)
            _mark_provider_degraded(affected, at, error)
            CapitalPosition.objects.filter(
                pk__in=affected, status=CapitalPosition.Status.OPEN
            ).update(next_result_check_at=at + timedelta(minutes=30))
    remaining = CapitalPosition.objects.filter(
        pk__in=position_ids, status=CapitalPosition.Status.OPEN
    )
    open_debt = remaining.count()
    # Only debt successfully scheduled into the future by a valid nonterminal
    # poll is OPEN_RESULT_NOT_DUE. Unattempted due dates are deferred.
    all_checked_and_not_due = (
        open_debt
        and not remaining.filter(
            Q(next_result_check_at__lte=at) | Q(next_result_check_at__isnull=True)
        ).exists()
    )
    unresolved = list(
        remaining.exclude(result_refresh_error="")
        .order_by("result_refresh_error")
        .values_list("result_refresh_error", flat=True)
        .distinct()
    )
    errors = list(dict.fromkeys([*errors, *unresolved]))
    status = (
        "DEGRADED"
        if errors
        else (
            "OPEN_RESULT_NOT_DUE"
            if all_checked_and_not_due
            else (
                "PRODUCED"
                if settled or (client is not None and client.calls)
                else "NO_WORK"
            )
        )
    )
    return RuntimeResult(
        status,
        settled=settled,
        provider_calls=(client.calls if client is not None else 0),
        open_debt=open_debt,
        result_debt_state=(
            "OPEN_RESULT_NOT_DUE" if status == "OPEN_RESULT_NOT_DUE" else ""
        ),
        errors=tuple(errors),
    )


def run_automatic_runtime(
    *, capture_run_id=None, at=None, client_factory=APIFootballClient
):
    """Admit expiring T-30 work before lower-priority result HTTP."""

    from football.strategy.clock import effective_now
    from football.strategy.deployment import locked_deployment, update_depletion
    from football.strategy.recovery import record_authority_failure

    planning_at = at or timezone.now()
    # Historical FS-016 replay keeps its event-time contract. The governed
    # successor uses wall time for every admission and result-debt check.
    active_identity = (
        CapitalRuntimeConfig.objects.filter(automatic=True, entry_enabled=True)
        .order_by("pk")
        .values_list("identity", flat=True)
        .first()
    )
    legacy_mode = bool(
        active_identity and not active_identity.startswith(("fs022:", "fs023:"))
    )

    def operation_now():
        return planning_at if legacy_mode else effective_now(planning_at=planning_at)

    errors = []
    local_settled = 0
    executions = []
    configs = ()

    def local_batch(run_id):
        nonlocal local_settled, configs
        with transaction.atomic():
            locked_deployment()
            local_settled += settle_locally_known_open_positions()
            now = operation_now()
            try:
                update_depletion(at=now)
                configs = provision_automatic_configs()
                return reconcile_execution_events(run_id, at=now)
            except (RuntimeError, ValueError) as error:
                errors.append(f"{type(error).__name__}:{error}"[:500])
                evaluations = record_authority_failure(run_id, at=now, error=error)
                return RuntimeResult("DEGRADED", evaluations=tuple(evaluations))

    # The admission lock is held only for local database work. Capture has
    # already run; a slow results provider cannot consume a valid T-30 window.
    executions.append(local_batch(capture_run_id))
    try:
        refresh = refresh_open_result_debt(
            at=operation_now(), client_factory=client_factory
        )
    except Exception as error:
        refresh = RuntimeResult(
            "DEGRADED",
            errors=(f"{type(error).__name__}:{error}"[:500],),
            open_debt=CapitalPosition.objects.filter(
                status=CapitalPosition.Status.OPEN
            ).count(),
        )
    # A result may release capacity or complete the old-bank drain. Retry any
    # still-valid work with a fresh wall clock, never the old planning time.
    if not errors:
        executions.append(local_batch(None))
    evaluations = {
        row["work_id"]: row for execution in executions for row in execution.evaluations
    }
    errors.extend(refresh.errors)
    errors.extend(error for execution in executions for error in execution.errors)
    placed = sum(row.placed for row in executions)
    not_placed = sum(row.not_placed for row in executions)
    pending = sum(row.pending_capacity for row in executions)
    settled = local_settled + refresh.settled
    status = (
        "DEGRADED"
        if errors or refresh.status == "DEGRADED"
        else (
            "PRODUCED"
            if placed or not_placed or pending or settled
            else (
                "OPEN_RESULT_NOT_DUE"
                if refresh.status == "OPEN_RESULT_NOT_DUE"
                else "NO_WORK"
            )
        )
    )
    return RuntimeResult(
        status,
        configs=len(configs),
        config_ids=tuple(config.pk for config in configs),
        placed=placed,
        not_placed=not_placed,
        pending_capacity=pending,
        settled=settled,
        provider_calls=refresh.provider_calls,
        open_debt=refresh.open_debt,
        result_debt_state=refresh.result_debt_state,
        errors=tuple(errors),
        evaluations=tuple(evaluations.values()),
    )
