"""Supplementary FS-021 diagnostics; never feeds back into the frozen selector."""

import gzip
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from .capital_analysis import week_start
from .economic_selector import TOLERANCE, _scale, _threshold
from .integrated_inputs import require
from .integrated_runner import execution_binding, read_artifact
from .storage import canonical, immutable_bytes, lock

SCHEMA = "FS021_ECONOMIC_DIAGNOSTICS_V1"
FOLDER = "economic_diagnostics_v1_1"
NAME = "FS-021_economic_diagnostics_v1.json"
MANIFEST_NAME = "FS-021_economic_diagnostics_manifest_v1.json"


def _choice(rows):
    """Evaluate the published risk budget after omitting one frontier arm."""
    d_limit = _threshold([float(row["D"]) for row in rows])
    l_limit = _threshold([row["L"] for row in rows])
    survivors = [
        row
        for row in rows
        if float(row["D"]) <= d_limit + TOLERANCE and row["L"] <= l_limit + TOLERANCE
    ]

    def preference(row):
        return (
            -Decimal(row["R"]),
            row["L"],
            Decimal(row["D"]),
            -row["min_placements"],
            row["integrated_index"],
        )

    fallback = not survivors
    if fallback:
        d_scale = _scale([float(row["D"]) for row in rows])
        l_scale = _scale([row["L"] for row in rows])
        winner = min(
            rows,
            key=lambda row: (
                max(
                    0,
                    (float(row["D"]) - d_limit) / d_scale,
                    (row["L"] - l_limit) / l_scale,
                ),
                *preference(row),
            ),
        )
    else:
        winner = min(survivors, key=preference)
    return dict(
        winner=winner["integrated_index"],
        thresholds=dict(D=d_limit, L=l_limit),
        survivors=[row["integrated_index"] for row in survivors],
        fallback=fallback,
    )


def build_diagnostics(directory, spec, streams, result):
    directory = Path(directory)
    require(result["execution_id"] == directory.name, "DIAGNOSTIC_EXECUTION_ID")
    binding = execution_binding(spec)
    enrichment = []
    for pd, stream in enumerate(streams):
        indexes = {
            o.identity: (str(o.competition_id), week_start(o.execution_at).isoformat())
            for o in stream
        }
        require(len(indexes) == len(stream), "DIAGNOSTIC_STREAM_IDENTITIES")
        for candidate in spec["input"]["candidates"]:
            if candidate["pd_index"] != pd:
                continue
            i = candidate["integrated_index"]
            for lag in (120, 130, 150):
                key = dict(binding, lag=lag, integrated_index=i)
                ledger = json.loads(
                    gzip.decompress(
                        read_artifact(directory, f"observed/{lag}-{i:03d}.json.gz", key)
                    )
                )["ledger"]
                league = defaultdict(Decimal)
                week = defaultdict(Decimal)
                gross = Decimal(0)
                for event in ledger:
                    if event["kind"] != "SETTLEMENT":
                        continue
                    gain = Decimal(event["profit_loss"])
                    if gain <= 0:
                        continue
                    require(
                        event["opportunity"] in indexes, "DIAGNOSTIC_OPPORTUNITY_JOIN"
                    )
                    competition, start = indexes[event["opportunity"]]
                    league[competition] += gain
                    week[start] += gain
                    gross += gain
                enrichment.append(
                    dict(
                        lag=lag,
                        integrated_index=i,
                        gross_positive_pnl=str(gross),
                        positive_pnl_by_competition={
                            k: str(v) for k, v in sorted(league.items())
                        },
                        positive_pnl_by_week={
                            k: str(v) for k, v in sorted(week.items())
                        },
                        largest_competition_share=(
                            str(max(league.values()) / gross) if gross else None
                        ),
                        largest_week_share=(
                            str(max(week.values()) / gross) if gross else None
                        ),
                    )
                )
    n = len(spec["input"]["candidates"])
    require(len(enrichment) == 3 * n, "DIAGNOSTIC_CARDINALITY")
    by_index = {row["integrated_index"]: row for row in result["rows"]}
    frontier = [by_index[i] for i in result["frontier"]]
    omit = {
        str(row["integrated_index"]): (
            _choice([other for other in frontier if other is not row])
            if len(frontier) > 1
            else dict(status="SINGLETON_FRONTIER")
        )
        for row in frontier
    }
    original = result["original_practical_winner"]
    comparison = {
        str(i): {
            key: by_index[i][key] for key in ("R", "D", "L", "tier", "min_placements")
        }
        for i in {result["winner"], original}
    }
    cross_lag = [
        row["integrated_index"]
        for row in result["rows"]
        if min(Decimal(v) for v in row["returns_by_lag"].values()) < 0
        and max(Decimal(v) for v in row["returns_by_lag"].values()) > 0
    ]
    return dict(
        schema=SCHEMA,
        execution_id=directory.name,
        selector_result_sha256=hashlib.sha256(
            (
                directory / "economic_selection_v1_1/FS-021_economic_selector_v1.json"
            ).read_bytes()
        ).hexdigest(),
        positive_pnl_attribution=enrichment,
        frontier_omission_sensitivity=omit,
        winner_vs_original_practical=comparison,
        positive_one_lag_negative_another=cross_lag,
        interpretation="POST_HOC_DIAGNOSTICS_ONLY_NO_SELECTION_WEIGHTS_NO_CROSS_LAG_INFERENCE",
        activation=False,
    )


def analyze_diagnostics_existing(directory, spec, streams, result):
    directory = Path(directory)
    with lock(directory / ".economic_diagnostics_v1_1.lock"):
        diagnostics = build_diagnostics(directory, spec, streams, result)
        data = (canonical(diagnostics) + "\n").encode()
        manifest = dict(
            schema="FS021_ECONOMIC_DIAGNOSTICS_MANIFEST_V1",
            execution_id=directory.name,
            source_selector_sha256=diagnostics["selector_result_sha256"],
            output_sha256=hashlib.sha256(data).hexdigest(),
            output_bytes=len(data),
            retention="PRESERVE_ACTIVE_UNTIL_CONSUMERS_CLOSED_AND_EXPLICIT_DELETION_APPROVAL",
            activation=False,
        )
        files = {NAME: data, MANIFEST_NAME: (canonical(manifest) + "\n").encode()}
        for name, content in files.items():
            path = directory / FOLDER / name
            require(
                not path.exists() or path.read_bytes() == content,
                "ECONOMIC_DIAGNOSTICS_CONFLICT",
            )
        for name, content in files.items():
            immutable_bytes(
                directory / FOLDER / name,
                content,
                conflict="ECONOMIC_DIAGNOSTICS_CONFLICT",
            )
    return diagnostics


def publish_diagnostics_existing(directory, base):
    """Publish a compact index, never a research-directory data dump."""
    directory, base = Path(directory), Path(base)
    source = directory / FOLDER
    manifest_data = (source / MANIFEST_NAME).read_bytes()
    manifest = json.loads(manifest_data)
    require(manifest["execution_id"] == directory.name, "DIAGNOSTIC_MANIFEST_ID")
    data = (source / NAME).read_bytes()
    require(
        len(data) == manifest["output_bytes"]
        and hashlib.sha256(data).hexdigest() == manifest["output_sha256"],
        "ECONOMIC_DIAGNOSTICS_HASH",
    )
    index = dict(
        schema="FS021_ECONOMIC_DIAGNOSTICS_INDEX_V1_1",
        execution_id=directory.name,
        relative_path=f"{FOLDER}/{MANIFEST_NAME}",
        manifest_sha256=hashlib.sha256(manifest_data).hexdigest(),
        source_selector_sha256=manifest["source_selector_sha256"],
        activation=False,
    )
    root = base / "docs/experiments/FS-021" / directory.name
    root.mkdir(parents=True, exist_ok=True)
    with lock(root / ".FS-021_economic_diagnostics.lock"):
        immutable_bytes(
            root / "diagnostics_v1_1.json",
            (canonical(index) + "\n").encode(),
            conflict="ECONOMIC_DIAGNOSTICS_INDEX_CONFLICT",
        )
    return manifest
