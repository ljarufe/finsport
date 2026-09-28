"""Pre-cutover FS-016 fixture setup only; never imported by application code."""

from decimal import Decimal

from django.db import transaction

from football.capital.contracts import json_decimal
from football.capital.policies import POLICY_VERSIONS, make_policy
from football.capital.runtime import (
    AUTOMATIC_CONFIGS,
    AUTOMATIC_SOURCE,
    EXECUTION_VERSION,
    RUNTIME_VERSION,
    ZERO,
    CapitalRuntimeInvariantError,
    _config_identity,
)
from football.models import CapitalRuntimeConfig


@transaction.atomic
def provision_historical_configs():
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
            "entry_enabled": True,
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
