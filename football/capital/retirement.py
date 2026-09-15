"""Fail-closed, manifest-bound retirement of derived Capital v1 rows."""

from __future__ import annotations

import hashlib
import json

from django.db import transaction
from django.db.models import Max, Min

from football.models import (
    CapitalExperiment,
    CapitalLedgerEntry,
    CapitalLongitudinalSeries,
    CapitalPolicyRun,
    CapitalRuntimeConfig,
    CaptureRun,
    CaptureWorkItem,
    Decision,
    HistoricalMarketEvidence,
    Match,
    OddsObservation,
    PipelineRun,
    Prediction,
    PredictionExperiment,
)

V1_ENGINE_VERSION = "fs004-v1"
V1_LONGITUDINAL_SCHEMA = "fs010-longitudinal-capital-v1"


class CapitalRetirementScopeError(RuntimeError):
    """The current v1 graph is mixed, ambiguous, or drifted from its manifest."""


def _hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _bounds(queryset, field):
    values = queryset.aggregate(lower=Min(field), upper=Max(field))
    return {
        "min": values["lower"].isoformat() if values["lower"] else None,
        "max": values["upper"].isoformat() if values["upper"] else None,
    }


def _upstream_counts():
    return {
        "Match": Match.objects.count(),
        "OddsObservation": OddsObservation.objects.count(),
        "HistoricalMarketEvidence": HistoricalMarketEvidence.objects.count(),
        "PredictionExperiment": PredictionExperiment.objects.count(),
        "Prediction": Prediction.objects.count(),
        "Decision": Decision.objects.count(),
        "CaptureRun": CaptureRun.objects.count(),
        "CaptureWorkItem": CaptureWorkItem.objects.count(),
        "PipelineRun": PipelineRun.objects.count(),
    }


def _compatible_series(series, selected_ids):
    snapshot_ids = set(series.snapshots.values_list("id", flat=True))
    if not snapshot_ids or not snapshot_ids <= selected_ids:
        return False
    schemas = {
        (manifest or {}).get("schema")
        for manifest in series.snapshots.values_list("input_manifest", flat=True)
    }
    return (
        series.source_model_code == "DIXON_COLES"
        and series.decision_policy_code == "MODAL_ALL"
        and series.mode == CapitalExperiment.MODE_REPLAY
        and schemas == {V1_LONGITUDINAL_SCHEMA}
    )


def build_v1_retirement_manifest():
    experiments = CapitalExperiment.objects.filter(engine_version=V1_ENGINE_VERSION)
    experiment_ids = set(experiments.values_list("id", flat=True))
    referenced_series = CapitalLongitudinalSeries.objects.filter(
        snapshots__id__in=experiment_ids
    ).distinct()
    series_ids = []
    for series in referenced_series:
        if not _compatible_series(series, experiment_ids):
            raise CapitalRetirementScopeError(
                f"AMBIGUOUS_OR_MIXED_V1_SERIES:{series.pk}"
            )
        series_ids.append(series.pk)
    runs = CapitalPolicyRun.objects.filter(experiment_id__in=experiment_ids)
    ledger = CapitalLedgerEntry.objects.filter(
        policy_run__experiment_id__in=experiment_ids
    )
    identities = list(
        experiments.order_by("id").values(
            "id",
            "engine_version",
            "mode",
            "source_model_code",
            "source_model_variant",
            "source_comparator_code",
            "decision_policy_code",
            "decision_policy_variant",
            "logical_identity",
            "semantic_identity",
            "input_hash",
        )
    )
    config_hashes = {
        str(row["id"]): _hash(row["config"])
        for row in experiments.order_by("id").values("id", "config")
    }
    manifest = {
        "schema": "fs016-capital-v1-retirement-manifest-v1",
        "selector": {"CapitalExperiment.engine_version": V1_ENGINE_VERSION},
        "counts": {
            "CapitalLongitudinalSeries": len(series_ids),
            "CapitalExperiment": len(experiment_ids),
            "CapitalPolicyRun": runs.count(),
            "CapitalLedgerEntry": ledger.count(),
            "upstream_selected_for_deletion": 0,
        },
        "ids": {
            "CapitalLongitudinalSeries": sorted(series_ids),
            "CapitalExperiment": sorted(experiment_ids),
            "CapitalPolicyRun": list(runs.order_by("id").values_list("id", flat=True)),
            "CapitalLedgerEntry": list(
                ledger.order_by("id").values_list("id", flat=True)
            ),
        },
        "timestamp_bounds": {
            "CapitalLongitudinalSeries.created": _bounds(
                CapitalLongitudinalSeries.objects.filter(pk__in=series_ids), "created"
            ),
            "CapitalExperiment.created": _bounds(experiments, "created"),
            "CapitalLedgerEntry.batch_time": _bounds(ledger, "batch_time"),
        },
        "experiment_identities": identities,
        "config_hashes": config_hashes,
        "upstream_counts": _upstream_counts(),
        "v2_counts": {
            "CapitalRuntimeConfig": CapitalRuntimeConfig.objects.count(),
        },
    }
    manifest["manifest_sha256"] = _hash(manifest)
    return manifest


@transaction.atomic
def retire_v1_capital(*, expected_manifest=None, apply=False):
    """Dry-run by default; apply only an exact, revalidated manifest."""

    if apply and expected_manifest is None:
        raise CapitalRetirementScopeError("APPLY_REQUIRES_DRY_RUN_MANIFEST")
    list(
        CapitalExperiment.objects.select_for_update()
        .filter(engine_version=V1_ENGINE_VERSION)
        .values_list("id", flat=True)
    )
    list(
        CapitalLongitudinalSeries.objects.select_for_update()
        .filter(snapshots__engine_version=V1_ENGINE_VERSION)
        .values_list("id", flat=True)
    )
    current = build_v1_retirement_manifest()
    if not current["counts"]["CapitalExperiment"]:
        return {"status": "NO_WORK", "manifest": current}
    if not apply:
        return {"status": "DRY_RUN", "manifest": current}
    if current != expected_manifest:
        raise CapitalRetirementScopeError("RETIREMENT_SCOPE_DRIFT")
    upstream_before = current["upstream_counts"]
    v2_before = current["v2_counts"]
    CapitalExperiment.objects.filter(
        pk__in=current["ids"]["CapitalExperiment"]
    ).delete()
    CapitalLongitudinalSeries.objects.filter(
        pk__in=current["ids"]["CapitalLongitudinalSeries"],
        snapshots__isnull=True,
    ).delete()
    if _upstream_counts() != upstream_before:
        raise CapitalRetirementScopeError("UPSTREAM_COUNT_CHANGED")
    if CapitalRuntimeConfig.objects.count() != v2_before["CapitalRuntimeConfig"]:
        raise CapitalRetirementScopeError("V2_COUNT_CHANGED")
    if CapitalExperiment.objects.filter(engine_version=V1_ENGINE_VERSION).exists():
        raise CapitalRetirementScopeError("V1_EXPERIMENTS_REMAIN")
    return {
        "status": "APPLIED",
        "deleted": current["counts"],
        "manifest_sha256": current["manifest_sha256"],
    }
