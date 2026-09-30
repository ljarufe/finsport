"""FS-023 serial, restart-safe simulation strategy transitions."""

import hashlib
import json
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from football.capital.policies import make_policy
from football.models import (
    CapitalRuntimeConfig,
    StrategyBinding,
    StrategyEpoch,
    StrategySwitch,
)

from .constants import INITIAL_BANKROLL

TARGET_NAME = "FS023_BINDING_209_T10_V1"


def target_contract(source):
    contract = dict(source.contract)
    contract.update(
        name=TARGET_NAME,
        capture_window="market-t10m",
        wake_seconds=180,
        provider_topology="API_FOOTBALL_DISCOVERY_ODDS_BSD_SHADOW_RESULT",
        required_capabilities=["LIVE_MARKET_ODDS"],
        real_betting=False,
    )
    return contract


def target_binding(source):
    contract = target_contract(source)
    digest = StrategyBinding.digest_for(contract)
    binding, _ = StrategyBinding.objects.get_or_create(
        digest=digest,
        defaults=dict(
            name=TARGET_NAME,
            candidate_id=source.candidate_id,
            contract=contract,
            approved=True,
        ),
    )
    if (
        binding.contract != contract
        or not binding.approved
        or binding.name != TARGET_NAME
        or binding.candidate_id != source.candidate_id
    ):
        raise RuntimeError("FS023_TARGET_BINDING_DRIFT")
    return binding


def _source_config(epoch):
    return CapitalRuntimeConfig.objects.select_for_update().get(strategy_epoch=epoch)


def _start(deployment, source, target, bankroll, at):
    from .deployment import cancel_pending, event

    if source.state == StrategyEpoch.State.DRAINED:
        raise RuntimeError("FS023_DRAINED_SOURCE_CANNOT_SWITCH")
    switch, _ = StrategySwitch.objects.get_or_create(
        source_epoch=source,
        target_binding=target,
        initial_bankroll=bankroll,
        defaults=dict(requested_at=at),
    )
    if source.state == StrategyEpoch.State.ACTIVE:
        config = _source_config(source)
        source.state = StrategyEpoch.State.DRAINING
        source.save(update_fields=["state"])
        deployment.retiring_config_ids = [config.pk]
        deployment.entry_enabled = False
        config.entry_enabled = False
        config.save(update_fields=["entry_enabled"])
        cancel_pending([config.pk], deployment, at)
        event(
            deployment,
            "DRAINING",
            "STRATEGY_SWITCH",
            at,
            source_epoch_id=source.pk,
            target_binding_digest=target.digest,
        )
        deployment.save()
    return switch


def _activate(deployment, switch, at):
    from .deployment import drain_complete, event

    source = StrategyEpoch.objects.select_for_update().get(pk=switch.source_epoch_id)
    if switch.target_epoch_id:
        if deployment.active_epoch_id != switch.target_epoch_id:
            raise RuntimeError("FS023_SWITCH_TARGET_DEPLOYMENT_MISMATCH")
        return (deployment.config,)
    if source.state != StrategyEpoch.State.DRAINING or not drain_complete(deployment):
        return ()
    source.state = StrategyEpoch.State.DRAINED
    source.drained_at = at
    source.save(update_fields=["state", "drained_at"])
    CapitalRuntimeConfig.objects.filter(strategy_epoch=source).update(
        current=False, entry_enabled=False
    )
    event(
        deployment,
        "DRAINED",
        "NO_OPEN_PENDING_RESULT_DEBT_OR_RESERVE",
        at,
        source_epoch_id=source.pk,
    )
    binding = StrategyBinding.objects.get(pk=switch.target_binding_id)
    if (
        not binding.approved
        or binding.digest != StrategyBinding.digest_for(binding.contract)
        or binding.contract.get("candidate_id", binding.candidate_id)
        != binding.candidate_id
        or binding.contract.get("name") != binding.name
    ):
        raise RuntimeError("FS023_UNAPPROVED_OR_MUTATED_BINDING")
    capital = binding.contract["capital"]
    decision = binding.contract["decision"]
    prediction = binding.contract["prediction"]
    bankroll = switch.initial_bankroll
    epoch = StrategyEpoch.objects.create(
        binding=binding,
        state=StrategyEpoch.State.ACTIVE,
        initial_bankroll=bankroll,
        activated_at=at,
    )
    policy = make_policy(capital["code"], capital["config"])
    config = CapitalRuntimeConfig.objects.create(
        identity=f"fs023:epoch:{epoch.pk}:{binding.digest}",
        strategy_epoch=epoch,
        runtime_version="fs023-epoch-simulation-v1",
        execution_version=f"fs023-{binding.contract['capture_window']}-v1",
        mode=CapitalRuntimeConfig.Mode.CURRENT,
        automatic=True,
        current=True,
        entry_enabled=True,
        source_model_code=prediction["code"],
        decision_policy_code=decision["code"],
        decision_policy_variant=decision["variant"],
        policy_code=capital["code"],
        policy_version=capital["version"],
        policy_config=capital["config"],
        max_lanes=capital["max_lanes"],
        initial_bankroll=bankroll,
        bankroll_equity=bankroll,
        reserved_exposure=0,
        peak_equity=bankroll,
        policy_state=policy.initial_state(),
        started_at=at,
        provenance={"binding_digest": binding.digest, "real_betting": False},
    )
    switch.target_epoch = epoch
    switch.completed_at = at
    switch.save(update_fields=["target_epoch", "completed_at"])
    selection = dict(deployment.selection)
    prospective = dict(selection["prospective_prediction_effective_config"])
    prospective["capture_window"] = binding.contract["capture_window"]
    selection["prospective_prediction_effective_config"] = prospective
    selection["prospective_prediction_config_identity"] = hashlib.sha256(
        json.dumps(prospective, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    deployment.selection = selection
    deployment.active_epoch = epoch
    deployment.config = config
    deployment.activated_at = at
    deployment.entry_enabled = True
    deployment.retiring_config_ids = []
    deployment.depletion_state = "ACTIVE"
    event(
        deployment,
        "ACTIVE",
        "FS023_NEW_STRATEGY_EPOCH",
        at,
        epoch_id=epoch.pk,
        binding_digest=binding.digest,
        initial_bankroll=str(bankroll),
    )
    deployment.save()
    return (config,)


@transaction.atomic
def request_switch(target, *, at=None, bankroll=Decimal(INITIAL_BANKROLL)):
    """Explicit switch/rollback; equal full digest is the sole ALREADY_ACTIVE case."""
    from .deployment import locked_deployment

    at = at or timezone.now()
    deployment = locked_deployment()
    source = StrategyEpoch.objects.select_for_update().get(
        pk=deployment.active_epoch_id
    )
    if (
        target.digest == source.binding.digest
        and source.state == StrategyEpoch.State.ACTIVE
    ):
        return "ALREADY_ACTIVE", source
    if (
        not target.approved
        or target.contract.get("real_betting") is not False
        or target.digest != StrategyBinding.digest_for(target.contract)
        or target.contract.get("candidate_id", target.candidate_id)
        != target.candidate_id
        or target.contract.get("name") != target.name
    ):
        raise RuntimeError("FS023_TARGET_NOT_APPROVED_SIMULATION_BINDING")
    if source.state == StrategyEpoch.State.DRAINING:
        existing = StrategySwitch.objects.get(
            source_epoch=source, target_epoch__isnull=True
        )
        if (
            existing.target_binding_id != target.pk
            or existing.initial_bankroll != bankroll
        ):
            raise RuntimeError("FS023_SWITCH_ALREADY_IN_PROGRESS")
        switch = existing
    else:
        switch = _start(deployment, source, target, bankroll, at)
    return "DRAINING", switch


@transaction.atomic
def advance(*, at=None):
    from .deployment import locked_deployment

    at = at or timezone.now()
    deployment = locked_deployment()
    if deployment.active_epoch_id is None:
        return None
    source = StrategyEpoch.objects.select_for_update().get(
        pk=deployment.active_epoch_id
    )
    if source.state == StrategyEpoch.State.ACTIVE:
        if source.binding.contract["capture_window"] == "market-t30m":
            target = target_binding(source.binding)
            _start(deployment, source, target, Decimal(INITIAL_BANKROLL), at)
        else:
            return (deployment.config,)
    switch = StrategySwitch.objects.select_for_update().get(
        source_epoch=source, target_epoch__isnull=True
    )
    return _activate(deployment, switch, at)
