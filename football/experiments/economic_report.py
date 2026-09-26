"""Read-only upstream verification and separate, immutable economic publication."""

import csv
import gzip
import hashlib
import io
import json
from datetime import timedelta
from pathlib import Path

import numpy as np

from .economic_metrics import METRICS_VERSION, derive_observed_metrics
from .economic_selector import (
    BLOCKS,
    INPUT_VERSION,
    LAGS,
    METHOD_VERSION,
    select_economic_baseline,
    selector_contract,
)
from .integrated_events import expand_ledger
from .integrated_inputs import require, sha_file
from .integrated_runner import RISK_COLUMNS, execution_binding, read_artifact
from .storage import canonical, identity, immutable_bytes, lock

# Reporting v1.1 fixes top20 ordering and removes mutable retention state from
# immutable economic results. Preserve the already-published v1 directory.
OUTPUT_DIR = "economic_selection_v1_1"
REPORT_VERSION = "FS021_ECONOMIC_REPORTING_V1_1"


def _csv(rows, columns):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: canonical(value) if isinstance(value, (dict, list)) else value
                for key, value in row.items()
            }
        )
    return stream.getvalue().encode()


def build_economic_analysis(directory, spec, streams):
    """Verify source manifests and logical ledgers; never run any path or RNG."""
    directory = Path(directory)
    binding = execution_binding(spec)
    run_bytes = read_artifact(directory, "run.json", binding)
    run = json.loads(run_bytes)
    require(
        run["status"] == "COMPLETE"
        and run["execution_id"] == directory.name
        and run["binding"] == binding,
        "ECONOMIC_UPSTREAM_INCOMPLETE",
    )
    require(
        run["activation"]
        == dict(automatic_operational_routing=False, real_betting=False),
        "ECONOMIC_ACTIVATION_FORBIDDEN",
    )
    observed = json.loads(read_artifact(directory, "observed.json", binding))
    candidates = spec["input"]["candidates"]
    n = len(candidates)
    require(
        n > 0 and [c["integrated_index"] for c in candidates] == list(range(n)),
        "ECONOMIC_CANDIDATE_ORDER",
    )
    require(
        set(observed) == {str(lag) for lag in LAGS}
        and all(len(observed[str(lag)]) == n for lag in LAGS),
        "ECONOMIC_OBSERVED_CARDINALITY",
    )
    require(
        len(streams) > max(c["pd_index"] for c in candidates),
        "ECONOMIC_STREAM_CARDINALITY",
    )
    start = spec["input"]["calendar"]["weeks"][0]
    enriched = []
    source_hashes = dict(
        spec=sha_file(directory / "spec.json"),
        run=hashlib.sha256(run_bytes).hexdigest(),
        observed=sha_file(directory / "observed.json"),
    )
    suffix_count = 0
    for lag in LAGS:
        for i, candidate in enumerate(candidates):
            key = dict(binding, lag=lag, integrated_index=i)
            name = f"observed/{lag}-{i:03d}.json.gz"
            result = json.loads(gzip.decompress(read_artifact(directory, name, key)))
            pd = candidate["pd_index"]
            stream_sha = spec["input"]["streams"][pd]["original_stream_sha256"]
            require(
                result["ledger_hash"]
                == identity(expand_ledger(result, streams[pd], stream_sha)),
                "ECONOMIC_LOGICAL_LEDGER_HASH",
            )
            require(
                result["metrics"] == observed[str(lag)][i],
                "ECONOMIC_OBSERVED_METRICS_MISMATCH",
            )
            require(
                result["metrics"]["input_count"] == spec["input"]["counts"]["matches"],
                "ECONOMIC_INPUT_COUNT",
            )
            suffix_count += result["suffix"] is not None
            path_horizon = max(o.kickoff + timedelta(minutes=lag) for o in streams[pd])
            metrics = derive_observed_metrics(
                result, start, path_horizon=path_horizon.isoformat()
            )
            # Daily points remain in the versioned analysis JSON; the CSV is compact.
            enriched.append(dict(lag=lag, integrated_index=i, **metrics))
            source_hashes[name] = sha_file(directory / name)
    matrices = {}
    for block in BLOCKS:
        name = f"scores-150-{block}.npy"
        data = read_artifact(directory, name, binding)
        matrix = np.load(io.BytesIO(data), allow_pickle=False)
        require(
            matrix.shape == (spec["bootstrap"]["replicates"], n)
            and np.isfinite(matrix).all(),
            "ECONOMIC_MATRIX_SHAPE",
        )
        matrices[str(block)] = matrix
        source_hashes[name] = hashlib.sha256(data).hexdigest()
    risk_status = dict(
        status="UNAVAILABLE_UPSTREAM",
        reason="ORIGINAL_RUN_RETAINED_TERMINAL_RETURNS_ONLY",
    )
    if spec["bootstrap"].get("risk_schema") == "FS021_BOOTSTRAP_RISK_V1":
        for block in BLOCKS:
            name = f"risk-150-{block}.npy"
            data = read_artifact(
                directory,
                name,
                dict(
                    binding,
                    risk_schema="FS021_BOOTSTRAP_RISK_V1",
                    columns=list(RISK_COLUMNS),
                ),
            )
            matrix = np.load(io.BytesIO(data), allow_pickle=False)
            require(
                matrix.shape == (spec["bootstrap"]["replicates"], n, len(RISK_COLUMNS))
                and np.isfinite(matrix).all(),
                "ECONOMIC_RISK_MATRIX",
            )
            source_hashes[name] = hashlib.sha256(data).hexdigest()
        risk_status = dict(
            status="AVAILABLE",
            schema="FS021_BOOTSTRAP_RISK_V1",
            columns=list(RISK_COLUMNS),
        )
    slices = []
    for path in sorted((directory / "stability").glob("*.json")):
        if path.name.endswith(".manifest.json"):
            continue
        name = path.stem
        entry = json.loads(
            read_artifact(
                directory, f"stability/{path.name}", dict(binding, slice=name)
            )
        )
        require(entry["slice"] == name and len(entry["scores"]) == n, "ECONOMIC_SLICE")
        slices.append(entry)
        source_hashes[f"stability/{path.name}"] = sha_file(path)
    require(
        len(slices) == 12 and {s["slice"] for s in slices} >= {"H1", "H2"},
        "ECONOMIC_SLICES_CARDINALITY",
    )
    payload = dict(
        schema=INPUT_VERSION,
        execution_id=directory.name,
        spec_sha=source_hashes["spec"],
        run_sha=source_hashes["run"],
        candidates=candidates,
        observed=observed,
        scores=matrices,
        scientific_disposition=run["scientific_evidence"]["disposition"],
    )
    result = select_economic_baseline(payload)
    metric_lookup = {(r["lag"], r["integrated_index"]): r for r in enriched}
    for row in result["rows"]:
        i = row["integrated_index"]
        values = [metric_lookup[(lag, i)] for lag in LAGS]
        row["observed_diagnostics"] = {
            str(lag): {
                k: v for k, v in metric_lookup[(lag, i)].items() if k != "daily_equity"
            }
            for lag in LAGS
        }
        row["worst_cdar95_daily"] = str(max(float(v["cdar95_daily"]) for v in values))
        row["max_top5_gain_concentration"] = str(
            max(
                (
                    float(v["top5_positive_pnl_concentration"])
                    for v in values
                    if v["top5_positive_pnl_concentration"] is not None
                ),
                default=0,
            )
        )
        row["stability_slices"] = {s["slice"]: s["scores"][i] for s in slices}
        row["cross_lag_sensitivity"] = "OBSERVED_ONLY_NO_CROSS_LAG_INFERENCE"
    result["execution_id"] = directory.name
    result["source_hashes"] = source_hashes
    result["source_binding"] = binding
    result["reconciled_ledgers"] = len(enriched)
    result["logical_suffixes_verified"] = suffix_count
    result["original_practical_winner"] = run["practical_selection"]["selected"][
        "integrated_index"
    ]
    result["original_scientific_evidence"] = {
        k: v for k, v in run["scientific_evidence"].items() if k != "families"
    }
    result["bootstrap_intrareplicate_diagnostics"] = risk_status
    # Retention is verified as a separate mutable *status*, not frozen into
    # the economic result; original v1 retained MISSING_REVIEW historically.
    return result, enriched


def output_files(result, enriched):
    rows = result["rows"]
    columns = (
        "integrated_index",
        "tier",
        "R",
        "D",
        "L",
        "min_placements",
        "selection_reason",
        "clean_reasons",
        "activity_reasons",
        "bootstrap_medians",
        "bootstrap_cvar5",
        "terminal_equity_le_5_proxy",
        "returns_by_lag",
        "drawdowns_by_lag",
        "worst_cdar95_daily",
        "max_top5_gain_concentration",
        "stability_slices",
        "observed_diagnostics",
    )
    # An explanatory top20 begins with the actual selected composition, then
    # remaining risk-budget survivors, then non-surviving frontier members.
    # Complete CSV retains all 231 in canonical integrated-index order.
    from decimal import Decimal

    frontier = set(result["frontier"])
    survivors = set(result["survivors"])

    def explanatory_rank(row):
        i = row["integrated_index"]
        group = (
            0
            if i == result["winner"]
            else (
                1
                if i in survivors
                else (
                    2
                    if i in frontier
                    else (
                        3
                        if row["tier"] == result["tier"]
                        else 4 if row["tier"] is not None else 5
                    )
                )
            )
        )
        return (
            group,
            row["tier"] if row["tier"] is not None else 99,
            -Decimal(row["R"]),
            row["L"],
            Decimal(row["D"]),
            -row["min_placements"],
            i,
        )

    ranking = sorted(rows, key=explanatory_rank)
    metrics_columns = (
        "lag",
        "integrated_index",
        "equity_final",
        "profit_loss",
        "total_return",
        "maximum_drawdown",
        "drawdown_duration_seconds",
        "recovery_duration_seconds",
        "underwater_unrecovered",
        "weekly_loss_frequency",
        "cdar95_daily",
        "mean_reserved_exposure",
        "peak_reserved_exposure",
        "minimum_equity",
        "minimum_available_cash",
        "top5_positive_pnl_concentration",
        "settled_count",
        "operational_depletion",
        "opportunity_cost",
        "bootstrap_path_risk",
    )
    report = f"""# FS-021 economic selector v1

Execution: `{result['execution_id']}`. Method: `{METHOD_VERSION}`.

Simulation-only selection: integrated #{result['winner']} ({result['mode']}); original practical selection #{result['original_practical_winner']} remains immutable. Scientific disposition: `{result['scientific_disposition']}`.

Tier {result['tier']}; frontier {result['frontier']}; risk-budget survivors {result['survivors']}; thresholds {result['thresholds']}; fallback {result['fallback']}. Risk warnings: {result['risk_warnings']}.

All {result['reconciled_ledgers']} observed ledgers were reconciled; {result['logical_suffixes_verified']} logical depletion suffixes were verified against retained streams. Bootstrap matrices are terminal T+150 only. Intrareplicate drawdown and depletion are `UNAVAILABLE_UPSTREAM`; terminal equity <=5u is only a proxy. Cross-lag results are observed sensitivity, not inference. Selection used the same historical sample and is post-hoc, not prospective validation. 7% over 36 weeks is a hypothetical benchmark without comparable risk.

Operational routing: false. Real betting: false. Retention is verified in a separate execution status, never inside this immutable economic result.
"""
    return {
        "FS-021_economic_selector_v1.json": (canonical(result) + "\n").encode(),
        "FS-021_economic_231.csv": _csv(rows, columns),
        "FS-021_economic_top20.csv": _csv(ranking[:20], columns),
        "FS-021_observed_economic_metrics.csv": _csv(enriched, metrics_columns),
        "FS-021_economic_report.md": report.encode(),
        "FS-021_daily_equity_693.json": (
            canonical(
                [
                    dict(
                        lag=r["lag"],
                        integrated_index=r["integrated_index"],
                        daily_equity=r["daily_equity"],
                    )
                    for r in enriched
                ]
            )
            + "\n"
        ).encode(),
    }


def analyze_existing(directory, spec, streams):
    """Persist a separate result; existing original checkpoints are read-only."""
    directory = Path(directory)
    with lock(directory / ".economic_selection_v1_1.lock"):
        result, enriched = build_economic_analysis(directory, spec, streams)
        files = output_files(result, enriched)
        target = directory / OUTPUT_DIR
        manifest = dict(
            schema="FS021_ECONOMIC_PUBLICATION_MANIFEST_V1_1",
            report_version=REPORT_VERSION,
            method_version=METHOD_VERSION,
            metrics_version=METRICS_VERSION,
            execution_id=directory.name,
            selector_spec_sha=identity(
                dict(
                    contract=selector_contract(),
                    bootstrap=spec["bootstrap"],
                    candidate_count=len(spec["input"]["candidates"]),
                    reporting=REPORT_VERSION,
                    metrics_version=METRICS_VERSION,
                )
            ),
            input_sha256=result["source_hashes"],
            outputs={
                name: dict(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
                for name, data in files.items()
            },
            retention="PRESERVE_ACTIVE_UNTIL_CONSUMERS_CLOSED_AND_EXPLICIT_DELETION_APPROVAL",
            activation=False,
        )
        retention = "path\tbytes\tsha256\tdelete_when\n" + "".join(
            f"{name}\t{entry['bytes']}\t{entry['sha256']}\t{manifest['retention']}\n"
            for name, entry in sorted(manifest["outputs"].items())
        )
        files["FS-021_economic_retention.tsv"] = retention.encode()
        manifest["outputs"]["FS-021_economic_retention.tsv"] = dict(
            sha256=hashlib.sha256(files["FS-021_economic_retention.tsv"]).hexdigest(),
            bytes=len(files["FS-021_economic_retention.tsv"]),
        )
        # Retain a published v1.1 manifest byte-for-byte. A historical
        # source-code SHA is provenance, not a formatting validity gate.
        previous_path = target / "FS-021_economic_manifest_v1.json"
        if previous_path.is_file():
            previous = json.loads(previous_path.read_text())
            new_fields = dict(manifest)
            previous_fields = dict(previous)
            new_fields.pop("selector_code_sha256", None)
            previous_fields.pop("selector_code_sha256", None)
            require(
                previous_fields == new_fields,
                "ECONOMIC_PUBLICATION_CONFLICT",
            )
            manifest = previous
        files["FS-021_economic_manifest_v1.json"] = (
            canonical(manifest) + "\n"
        ).encode()
        # Detect every conflict before creating any artifact.
        for name, data in files.items():
            path = target / name
            require(
                not path.exists() or path.read_bytes() == data,
                "ECONOMIC_PUBLICATION_CONFLICT",
            )
        for name, data in files.items():
            immutable_bytes(
                target / name, data, conflict="ECONOMIC_PUBLICATION_CONFLICT"
            )
    return result


def publish_economic_existing(directory, base):
    """Publish a compact Git locator; full results remain in the execution."""
    directory, base = Path(directory), Path(base)
    source = directory / OUTPUT_DIR
    manifest_bytes = (source / "FS-021_economic_manifest_v1.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    require(manifest["execution_id"] == directory.name, "ECONOMIC_MANIFEST_ID")
    for name, record in manifest["outputs"].items():
        data = (source / name).read_bytes()
        require(
            len(data) == record["bytes"]
            and hashlib.sha256(data).hexdigest() == record["sha256"],
            "ECONOMIC_OUTPUT_HASH",
        )
    result = json.loads((source / "FS-021_economic_selector_v1.json").read_text())
    require(
        result["activation"]
        == dict(automatic_operational_routing=False, real_betting=False),
        "ECONOMIC_ACTIVATION_FORBIDDEN",
    )
    index = dict(
        schema="FS021_ECONOMIC_PUBLICATION_INDEX_V1_1",
        execution_id=directory.name,
        relative_path=f"{OUTPUT_DIR}/FS-021_economic_manifest_v1.json",
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        selector_spec_sha=manifest["selector_spec_sha"],
        winner=result["winner"],
        scientific_disposition=result["scientific_disposition"],
        activation=False,
    )
    root = base / "docs/experiments/FS-021" / directory.name
    root.mkdir(parents=True, exist_ok=True)
    with lock(root / ".FS-021_economic_publication.lock"):
        immutable_bytes(
            root / "economic_v1_1.json",
            (canonical(index) + "\n").encode(),
            conflict="ECONOMIC_INDEX_CONFLICT",
        )
    return manifest
