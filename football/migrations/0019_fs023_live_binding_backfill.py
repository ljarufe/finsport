"""Install the authenticated FS-023 topology and preserve the actual FS-022 era."""

import hashlib
import json
from pathlib import Path

from django.db import migrations

MAPPING_SHA256 = "7c0b4b38e3fd6f9ddeb4b7ae61315b628a6fc71cf47b6a11d8b795fbad2b6941"


def _digest(contract):
    return hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def forwards(apps, schema_editor):
    Competition = apps.get_model("football", "Competition")
    Route = apps.get_model("football", "CompetitionResultRoute")
    Source = apps.get_model("football", "Source")
    SourceRef = apps.get_model("football", "CompetitionSourceRef")
    Binding = apps.get_model("football", "StrategyBinding")
    Epoch = apps.get_model("football", "StrategyEpoch")
    Deployment = apps.get_model("football", "CapitalDeployment")
    Config = apps.get_model("football", "CapitalRuntimeConfig")
    path = Path(__file__).resolve().parents[1] / "data/fs023_live_mapping.json"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MAPPING_SHA256:
        raise RuntimeError("FS023_FROZEN_MAPPING_HASH_MISMATCH")
    mapping = json.loads(raw)
    rows = mapping["rows"]
    ids = {r["local_competition_id"] for r in rows}
    if (len(rows), len(ids), sum(bool(r["bsd_league_ids"]) for r in rows)) != (28, 28, 23):
        raise RuntimeError("FS023_FROZEN_MAPPING_TOPOLOGY_MISMATCH")
    # Empty isolated test databases bootstrap fixtures after migrations.
    if not Competition.objects.exists():
        return
    if Competition.objects.filter(pk__in=ids).count() != 28:
        raise RuntimeError("FS023_CANONICAL_COMPETITION_MISSING")
    source = Source.objects.get(code="api_football")
    for row in rows:
        competition_id = row["local_competition_id"]
        ref = SourceRef.objects.filter(source=source, competition_id=competition_id).first()
        if ref is None or ref.external_id != str(row["api_football_league_id"]):
            raise RuntimeError(f"FS023_API_F_LEAGUE_IDENTITY_MISMATCH:{competition_id}")
        Route.objects.update_or_create(
            competition_id=competition_id,
            defaults=dict(
                api_football_league_id=row["api_football_league_id"],
                bsd_league_ids=row["bsd_league_ids"],
                bsd_state=("BSD_BOOTSTRAP_PENDING" if row["bsd_league_ids"] else "API_FOOTBALL_ONLY"),
                provenance={"mapping_sha256": MAPPING_SHA256, "schema": mapping["schema"]},
            ),
        )
    Competition.objects.exclude(pk__in=ids).update(enabled=False)
    Competition.objects.filter(pk__in=ids).update(enabled=True)

    deployment = Deployment.objects.filter(pk=1).first()
    if deployment is None or deployment.config_id is None or deployment.activated_at is None:
        return
    config = Config.objects.get(pk=deployment.config_id)
    if config.strategy_epoch_id or deployment.active_epoch_id:
        raise RuntimeError("FS023_EPOCH_ALREADY_BOUND")
    if config.initial_bankroll != 100 or deployment.real_betting:
        raise RuntimeError("FS023_LEGACY_ERA_INVARIANT")
    contract = {
        "schema": "FS023_STRATEGY_BINDING_V1",
        "name": "FS022_BINDING_209_T30_V1",
        "candidate_id": 209,
        "prediction": {"code": config.source_model_code, "version": "fs013-market-consensus-v2"},
        "decision": {"code": config.decision_policy_code, "variant": config.decision_policy_variant},
        "capital": {"code": config.policy_code, "version": config.policy_version,
                    "config": config.policy_config, "max_lanes": config.max_lanes},
        "capture_window": "market-t30m",
        "wake_seconds": 300,
        "required_capabilities": ["LIVE_MARKET_ODDS"],
        "promotion_lineage": deployment.selection,
        "provider_topology": "API_FOOTBALL_RESULT_PRIMARY",
        "real_betting": False,
    }
    binding, _ = Binding.objects.get_or_create(
        digest=_digest(contract),
        defaults=dict(name="FS022_BINDING_209_T30_V1", candidate_id=209,
                      contract=contract, approved=True),
    )
    epoch = Epoch.objects.create(
        binding=binding, state="ACTIVE", initial_bankroll=config.initial_bankroll,
        activated_at=deployment.activated_at,
    )
    config.strategy_epoch_id = epoch.pk
    config.save(update_fields=["strategy_epoch"])
    deployment.active_epoch_id = epoch.pk
    deployment.save(update_fields=["active_epoch"])


def backwards(apps, schema_editor):
    # Historical epochs and operational topology are evidence. A reverse schema
    # migration removes the tables; never silently re-enable previous leagues.
    pass


class Migration(migrations.Migration):
    dependencies = [("football", "0018_strategybinding_bsdeventbinding_and_more")]
    operations = [migrations.RunPython(forwards, backwards)]
