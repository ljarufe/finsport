"""Durable, serial admission barrier; settlement never depends on admission."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from football.capital.policies import make_policy
from football.models import (
    CapitalDeployment,
    CapitalDeploymentEvent,
    CapitalExecutionState,
    CapitalPosition,
    CapitalRuntimeConfig,
)

from . import clock
from .authority import resolve_authority
from .constants import DEPLETION_FLOOR, INITIAL_BANKROLL

CONFIG_IDENTITY = "fs022:fs021-economic-209:prospective-v1"
RUNTIME_VERSION = "fs022-global-simulation-v1"
EXECUTION_VERSION = "fs022-prospective-t30-v2"
PENDING = (
    CapitalExecutionState.Status.PENDING,
    CapitalExecutionState.Status.PENDING_CAPACITY,
)


def locked_deployment():
    # get_or_create's unique singleton serializes simultaneous first wakes too.
    CapitalDeployment.objects.get_or_create(pk=1)
    return CapitalDeployment.objects.select_for_update().get(pk=1)


def event(deployment, state, reason, at, **evidence):
    deployment.state = state
    CapitalDeploymentEvent.objects.create(
        deployment=deployment, at=at, state=state, reason=reason, evidence=evidence
    )


def cancel_pending(config_ids, deployment, at):
    for state in CapitalExecutionState.objects.select_for_update().filter(
        config_id__in=config_ids, status__in=PENDING
    ):
        if state.position_id:
            raise RuntimeError("FS022_PENDING_WITH_POSITION")
        previous_status = state.status
        state.status = CapitalExecutionState.Status.NOT_PLACED
        state.non_placement_reason = "STRATEGY_DRAINING"
        state.terminal_at = at
        state.diagnostics = {
            **state.diagnostics,
            "cutover_id": str(deployment.cutover_id),
            "previous_status": previous_status,
        }
        state.save()


def drain_complete(deployment):
    configs = list(
        CapitalRuntimeConfig.objects.select_for_update()
        .filter(pk__in=deployment.retiring_config_ids)
        .order_by("pk")
    )
    for config in configs:
        # A nonzero reservation without matching OPEN is a material error, not a
        # reason to zero money. Unresolved debt remains a blocker after restart.
        positions = config.positions.all()
        exposure = positions.filter(status=CapitalPosition.Status.OPEN).aggregate(
            total=Sum("applied_stake")
        )["total"] or Decimal(0)
        if exposure != config.reserved_exposure:
            raise RuntimeError("FS022_LEDGER_EXPOSURE_MISMATCH")
        if positions.filter(status=CapitalPosition.Status.OPEN).exists():
            return False
        if positions.exclude(debt_status=CapitalPosition.DebtStatus.RESOLVED).exists():
            return False
        if config.execution_states.filter(status__in=PENDING).exists():
            return False
    return True


@transaction.atomic
def provision(*, at=None):
    at = at or timezone.now()
    authority = resolve_authority()
    deployment = locked_deployment()
    if deployment.selection and deployment.selection != authority:
        raise RuntimeError("FS022_DEPLOYMENT_AUTHORITY_DRIFT")
    if deployment.real_betting or deployment.mode != "SIMULATION_ONLY":
        raise RuntimeError("FS022_REAL_BETTING_FORBIDDEN")
    if deployment.state == "OLD_ACTIVE":
        old = list(
            CapitalRuntimeConfig.objects.select_for_update()
            .filter(automatic=True)
            .order_by("pk")
        )
        deployment.retiring_config_ids = [row.pk for row in old]
        deployment.selection = authority
        deployment.entry_enabled = False
        CapitalRuntimeConfig.objects.filter(
            pk__in=deployment.retiring_config_ids
        ).update(entry_enabled=False)
        cancel_pending(deployment.retiring_config_ids, deployment, at)
        event(
            deployment,
            "DRAINING",
            "INITIAL_CUTOVER",
            at,
            config_ids=deployment.retiring_config_ids,
        )
    if deployment.state == "DRAINING" and drain_complete(deployment):
        # A drain may finish long after planning; only a new transition gets this time.
        at = clock.effective_now(planning_at=at)
        event(deployment, "DRAINED", "NO_OPEN_OR_PLACEABLE_PENDING_OR_DEBT", at)
        # Lifecycle can change, balances and every old position/basis stay intact.
        CapitalRuntimeConfig.objects.filter(
            pk__in=deployment.retiring_config_ids
        ).update(current=False, entry_enabled=False)
        if deployment.successor_mode:
            event(deployment, "STOPPED", deployment.successor_mode, at)
        else:
            capital = authority["winner_candidate"]["capital"]
            pd = authority["winner_candidate"]["prediction_decision"]
            policy = make_policy(capital["code"], capital["config"])
            config, created = CapitalRuntimeConfig.objects.get_or_create(
                identity=CONFIG_IDENTITY,
                defaults=dict(
                    runtime_version=RUNTIME_VERSION,
                    execution_version=EXECUTION_VERSION,
                    mode=CapitalRuntimeConfig.Mode.CURRENT,
                    automatic=True,
                    current=True,
                    entry_enabled=True,
                    source_model_code=pd["prediction_code"],
                    decision_policy_code=pd["decision_policy"],
                    decision_policy_variant=pd["decision_variant"],
                    policy_code=capital["code"],
                    policy_version=capital["version"],
                    policy_config=capital["config"],
                    max_lanes=capital["max_lanes"],
                    initial_bankroll=Decimal(INITIAL_BANKROLL),
                    bankroll_equity=Decimal(INITIAL_BANKROLL),
                    reserved_exposure=0,
                    peak_equity=Decimal(INITIAL_BANKROLL),
                    policy_state=policy.initial_state(),
                    started_at=at,
                    provenance=dict(selection=authority, real_betting=False),
                ),
            )
            if not created and not deployment.config_id:
                raise RuntimeError("FS022_UNBOUND_EXISTING_BANKROLL")
            deployment.config = config
            if deployment.activated_at is None:
                deployment.activated_at = at
            deployment.entry_enabled = True
            event(
                deployment,
                "ACTIVE",
                "ECONOMIC_209_SIMULATION_AUTHORIZED",
                at,
                config_id=config.pk,
            )
    deployment.save()
    if deployment.config_id:
        verify_config(deployment)
        return (deployment.config,)
    return ()


def verify_config(deployment):
    config = deployment.config
    pd = deployment.selection["winner_candidate"]["prediction_decision"]
    capital = deployment.selection["winner_candidate"]["capital"]
    expected = dict(
        identity=CONFIG_IDENTITY,
        automatic=True,
        source_model_code=pd["prediction_code"],
        decision_policy_code=pd["decision_policy"],
        decision_policy_variant=pd["decision_variant"],
        policy_code=capital["code"],
        policy_version=capital["version"],
        policy_config=capital["config"],
        max_lanes=10,
        initial_bankroll=Decimal(INITIAL_BANKROLL),
        runtime_version=RUNTIME_VERSION,
        execution_version=EXECUTION_VERSION,
    )
    if any(getattr(config, key) != value for key, value in expected.items()):
        raise RuntimeError("FS022_BANKROLL_CONFIG_DRIFT")


@transaction.atomic
def request_drain(*, successor_mode="STOPPED", at=None):
    """Strategic stop/diagnostic rollback closes entries, then drains actual OPEN.

    Ordinary technical restart calls provision instead and never resets money.
    A future different funded authority requires a new reviewed deployment path.
    """
    if successor_mode not in {"STOPPED", "DIAGNOSTIC_ONLY__NO_NEW_STAKES"}:
        raise ValueError("FS022_UNAUTHORIZED_REPLACEMENT")
    deployment = locked_deployment()
    at = at or timezone.now()
    if deployment.state == "STOPPED":
        return deployment
    ids = set(deployment.retiring_config_ids)
    if deployment.config_id:
        ids.add(deployment.config_id)
    deployment.retiring_config_ids = sorted(ids)
    deployment.successor_mode = successor_mode
    deployment.entry_enabled = False
    CapitalRuntimeConfig.objects.filter(pk__in=ids).update(entry_enabled=False)
    cancel_pending(ids, deployment, at)
    if deployment.state != "DRAINING":
        event(deployment, "DRAINING", successor_mode, at)
    deployment.save()
    return deployment


def admission_reason(deployment, config):
    if deployment.depletion_floor != DEPLETION_FLOOR and config.automatic:
        raise RuntimeError("FS022_DEPLETION_FLOOR_DRIFT")
    if not config.automatic:
        return ""  # Explicit manual Lab/study execution remains available.
    if not config.entry_enabled:
        return (
            "STRATEGY_DRAINING"
            if deployment.state == "DRAINING"
            else "STRATEGY_STOPPED"
        )
    if deployment.state == "OLD_ACTIVE":
        return ""  # Only pre-cutover historical regression fixtures use this.
    if (
        deployment.config_id != config.pk
        or not deployment.entry_enabled
        or deployment.state != "ACTIVE"
    ):
        return (
            "STRATEGY_DRAINING"
            if deployment.state == "DRAINING"
            else "STRATEGY_STOPPED"
        )
    if config.status != CapitalRuntimeConfig.Status.ACTIVE or not config.current:
        return "STRATEGY_STOPPED"
    if resolve_authority() != deployment.selection:
        raise RuntimeError("FS022_DEPLOYMENT_AUTHORITY_DRIFT")
    verify_config(deployment)
    if deployment.depletion_state != "ACTIVE":
        return deployment.depletion_state
    return ""


@transaction.atomic
def update_depletion(*, at=None):
    """Called after ALL locally known/due settlements, before any new request."""
    deployment = locked_deployment()
    if deployment.config_id is None or deployment.state != "ACTIVE":
        return
    config = CapitalRuntimeConfig.objects.select_for_update().get(
        pk=deployment.config_id
    )
    if deployment.depletion_floor != Decimal(DEPLETION_FLOOR):
        raise RuntimeError("FS022_DEPLETION_FLOOR_DRIFT")
    has_open = config.positions.filter(status=CapitalPosition.Status.OPEN).exists()
    previous = deployment.depletion_state
    if previous == "AWAITING_FINAL_OPEN_SETTLEMENT" and has_open:
        return
    if config.bankroll_equity <= deployment.depletion_floor:
        deployment.depletion_state = (
            "AWAITING_FINAL_OPEN_SETTLEMENT" if has_open else "OPERATIONAL_DEPLETION"
        )
    elif not has_open or previous == "ACTIVE":
        deployment.depletion_state = "ACTIVE"
    if deployment.depletion_state != previous:
        CapitalDeploymentEvent.objects.create(
            deployment=deployment,
            at=at or timezone.now(),
            state=deployment.depletion_state,
            reason="EQUITY_FLOOR_AFTER_SETTLEMENT_BATCH",
            evidence=dict(equity=str(config.bankroll_equity), has_open=has_open),
        )
        deployment.save()
