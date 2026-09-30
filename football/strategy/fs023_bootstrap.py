"""Fail-closed post-migration convergence for a fresh FS-023 installation."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from football.models import (
    CapitalRuntimeConfig,
    Competition,
    CompetitionResultRoute,
    CompetitionSourceRef,
    ReconciliationStatus,
    Source,
    StrategyEpoch,
    StrategySwitch,
)

from .authority import resolve_authority
from .constants import INITIAL_BANKROLL
from .epochs import (
    approved_target_binding,
    create_epoch_config,
    selection_for_binding,
    target_contract,
)

MAPPING_SHA256 = "7c0b4b38e3fd6f9ddeb4b7ae61315b628a6fc71cf47b6a11d8b795fbad2b6941"
NOT_READY = "FS023_NOT_READY"


def _mapping():
    path = Path(__file__).resolve().parents[1] / "data/fs023_live_mapping.json"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MAPPING_SHA256:
        raise RuntimeError("FS023_FROZEN_MAPPING_HASH_MISMATCH")
    mapping = json.loads(raw)
    rows = mapping["rows"]
    ids = {row["local_competition_id"] for row in rows}
    if (
        mapping["schema"] != "FS023_BSD_LEAGUE_MAPPING_V1"
        or len(rows) != 28
        or len(ids) != 28
        or sum(bool(row["bsd_league_ids"]) for row in rows) != 23
        or sum(not row["bsd_league_ids"] for row in rows) != 5
    ):
        raise RuntimeError("FS023_FROZEN_MAPPING_TOPOLOGY_MISMATCH")
    return mapping, rows, ids


def _canonical_ready(rows, ids):
    if Competition.objects.filter(pk__in=ids).count() != 28:
        return False
    source = Source.objects.filter(code="api_football").first()
    if source is None:
        return False
    refs = {}
    for ref in CompetitionSourceRef.objects.filter(
        source=source, competition_id__in=ids
    ):
        refs.setdefault(ref.competition_id, []).append(ref)
    for row in rows:
        matching = refs.get(row["local_competition_id"], [])
        if not matching:
            return False
        if (
            len(matching) != 1
            or matching[0].external_id != str(row["api_football_league_id"])
            or matching[0].reconciliation_status != ReconciliationStatus.RESOLVED
        ):
            raise RuntimeError(
                f"FS023_API_F_LEAGUE_IDENTITY_MISMATCH:{row['local_competition_id']}"
            )
    return True


def _ensure_routes(mapping, rows, ids):
    if CompetitionResultRoute.objects.exclude(competition_id__in=ids).exists():
        raise RuntimeError("FS023_ROUTE_TOPOLOGY_DRIFT")
    for row in rows:
        competition_id = row["local_competition_id"]
        route, created = CompetitionResultRoute.objects.get_or_create(
            competition_id=competition_id,
            defaults=dict(
                api_football_league_id=row["api_football_league_id"],
                bsd_league_ids=row["bsd_league_ids"],
                bsd_state=(
                    "BSD_BOOTSTRAP_PENDING"
                    if row["bsd_league_ids"]
                    else "API_FOOTBALL_ONLY"
                ),
                provenance={
                    "mapping_sha256": MAPPING_SHA256,
                    "schema": mapping["schema"],
                },
            ),
        )
        if not created and (
            route.api_football_league_id != row["api_football_league_id"]
            or route.bsd_league_ids != row["bsd_league_ids"]
            or route.provenance.get("mapping_sha256") != MAPPING_SHA256
        ):
            raise RuntimeError(f"FS023_ROUTE_TOPOLOGY_DRIFT:{competition_id}")
    Competition.objects.exclude(pk__in=ids).update(enabled=False)
    Competition.objects.filter(pk__in=ids).update(enabled=True)


def _legacy_contract(authority):
    """Describe the approved FS-022 lineage without persisting a fake T30 era."""
    pd = authority["winner_candidate"]["prediction_decision"]
    capital = authority["winner_candidate"]["capital"]
    return {
        "schema": "FS023_STRATEGY_BINDING_V1",
        "name": "FS022_BINDING_209_T30_V1",
        "candidate_id": 209,
        "prediction": {
            "code": pd["prediction_code"],
            "version": pd["prediction_version"],
        },
        "decision": {
            "code": pd["decision_policy"],
            "variant": pd["decision_variant"],
        },
        "capital": {
            "code": capital["code"],
            "version": capital["version"],
            "config": capital["config"],
            "max_lanes": capital["max_lanes"],
        },
        "capture_window": "market-t30m",
        "wake_seconds": 300,
        "required_capabilities": ["LIVE_MARKET_ODDS"],
        "promotion_lineage": authority,
        "provider_topology": "API_FOOTBALL_RESULT_PRIMARY",
        "real_betting": False,
    }


def converge_fresh(deployment, *, at):
    """Called under the singleton deployment lock; no partial topology on not-ready."""
    from .deployment import event, verify_config

    if deployment.config_id or deployment.active_epoch_id or deployment.selection:
        raise RuntimeError("FS023_FRESH_BOOTSTRAP_EXISTING_DEPLOYMENT")
    if deployment.state not in {"OLD_ACTIVE", NOT_READY} or deployment.successor_mode:
        raise RuntimeError("FS023_FRESH_BOOTSTRAP_STOPPED")
    if deployment.real_betting or deployment.mode != "SIMULATION_ONLY":
        raise RuntimeError("FS023_REAL_BETTING_FORBIDDEN")
    mapping, rows, ids = _mapping()
    if not _canonical_ready(rows, ids):
        if deployment.state != NOT_READY:
            deployment.entry_enabled = False
            event(deployment, NOT_READY, "CANONICAL_PREREQUISITES_INCOMPLETE", at)
            deployment.save(update_fields=["state", "entry_enabled"])
        return ()
    if (
        StrategyEpoch.objects.exists()
        or StrategySwitch.objects.exists()
        or CapitalRuntimeConfig.objects.filter(automatic=True).exists()
    ):
        raise RuntimeError("FS023_FRESH_BOOTSTRAP_EXISTING_STRATEGY_STATE")
    authority = resolve_authority()
    _ensure_routes(mapping, rows, ids)
    binding = approved_target_binding(target_contract(_legacy_contract(authority)))
    epoch = StrategyEpoch.objects.create(
        binding=binding,
        state=StrategyEpoch.State.ACTIVE,
        initial_bankroll=Decimal(INITIAL_BANKROLL),
        activated_at=at,
    )
    config = create_epoch_config(binding, epoch, Decimal(INITIAL_BANKROLL), at)
    deployment.selection = selection_for_binding(authority, binding)
    deployment.active_epoch = epoch
    deployment.config = config
    deployment.activated_at = at
    deployment.entry_enabled = True
    event(
        deployment,
        "ACTIVE",
        "FS023_FRESH_T10_EPOCH",
        at,
        epoch_id=epoch.pk,
        binding_digest=binding.digest,
        initial_bankroll=str(INITIAL_BANKROLL),
    )
    deployment.save()
    verify_config(deployment)
    return (config,)
