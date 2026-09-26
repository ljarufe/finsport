"""Publication verifies an existing execution; never invokes a replay."""

import csv
import gzip
import hashlib
import json
from pathlib import Path

from .integrated_events import expand_ledger
from .integrated_inputs import require
from .integrated_runner import execution_binding, existing_scores, read_artifact
from .storage import canonical, identity, immutable_bytes, lock, read_json


def verify_existing(directory, spec, streams):
    directory = Path(directory)
    binding = execution_binding(spec)
    run = json.loads(read_artifact(directory, "run.json", binding))
    require(
        run["status"] == "COMPLETE"
        and run["execution_id"] == directory.name
        and run["binding"] == binding,
        "RUN_INCOMPLETE",
    )
    observed = json.loads(read_artifact(directory, "observed.json", binding))
    for lag in (120, 130, 150):
        for i in range(231):
            key = dict(binding, lag=lag, integrated_index=i)
            result = json.loads(
                gzip.decompress(
                    read_artifact(directory, f"observed/{lag}-{i:03d}.json.gz", key)
                )
            )
            stream_sha = spec["input"]["streams"][i // 7]["original_stream_sha256"]
            require(
                result["ledger_hash"]
                == identity(expand_ledger(result, streams[i // 7], stream_sha)),
                "OBSERVED_LOGICAL_HASH",
            )
            require(
                result["metrics"] == observed[str(lag)][i]
                and result["metrics"]["input_count"] == 1877,
                "OBSERVED_SUMMARY",
            )
    for length in (1, 2, 4):
        _, covered = existing_scores(directory, spec, length)
        require(len(covered) == 5000, "PUBLISH_INCOMPLETE_SCIENCE")
        read_artifact(directory, f"scores-150-{length}.npy", binding)
    names = ["H1", "H2"] + [
        f"WITHOUT:{c}" for c in sorted({o.competition_id for o in streams[0]})
    ]
    for name in names:
        read_artifact(directory, f"stability/{name}.json", dict(binding, slice=name))
    return run, observed


def publish_existing(directory, spec, streams, base):
    directory, base = Path(directory), Path(base)
    run, observed = verify_existing(directory, spec, streams)
    selected = run["practical_selection"]
    require(
        run["activation"]
        == dict(automatic_operational_routing=False, real_betting=False),
        "ACTIVATION_FORBIDDEN",
    )
    inventory = []
    for path in sorted(directory.rglob("*.manifest.json")):
        payload = path.with_name(path.name.removesuffix(".manifest.json"))
        # Checkpoint readers already verify their own content when consumed.
        # The retention index is an inventory, not a second hash approval gate.
        require(payload.is_file(), "RETENTION_MISSING")
        inventory.append(
            dict(
                path=str(payload.relative_to(directory)),
                bytes=payload.stat().st_size,
                producer="FS-021",
                consumers=["FS-022", "FUTURE_CHALLENGERS"],
                delete_when="PRESERVE_ACTIVE_UNTIL_CONSUMERS_CLOSED_AND_EXPLICIT_DELETION_APPROVAL",
                license="INHERITED_PROVIDER_TERMS_NO_REDISTRIBUTION_AUTHORIZATION",
                restore="READ_CHECKPOINT_OR_RESTORE_ORIGINAL_INPUT",
            )
        )
    for name in ("spec.json", "gates.json", "restore.json"):
        payload = directory / name
        inventory.append(
            dict(
                path=name,
                bytes=payload.stat().st_size,
                producer="FS-021",
                consumers=["FS-022", "FUTURE_CHALLENGERS"],
                delete_when="PRESERVE_ACTIVE",
                license="LOCAL_RESEARCH_METADATA",
                restore="RETAIN_WITH_EXECUTION",
            )
        )
    retention_index = directory / "RETENTION_INDEX.tsv"
    # This index is immutable. New derived publications have their OWN retention
    # manifests; they must not rewrite the already-published original inventory.
    if retention_index.exists():
        with retention_index.open(newline="") as source:
            frozen = list(csv.DictReader(source, delimiter="\t"))
        require(
            frozen and len({row["path"] for row in frozen}) == len(frozen),
            "RETENTION_INDEX_INVALID",
        )
        inventory = []
        for row in frozen:
            name = Path(row["path"])
            require(
                not name.is_absolute() and ".." not in name.parts,
                "RETENTION_UNSAFE_PATH",
            )
            payload = directory / name
            require(
                payload.is_file() and payload.stat().st_size == int(row["bytes"]),
                "RETENTION_INDEX_MISMATCH",
            )
            inventory.append(
                dict(
                    path=str(name),
                    bytes=int(row["bytes"]),
                    producer=row["producer"],
                    consumers=row["consumers"].split(","),
                    delete_when=row["delete_when"],
                    license=row["license"],
                    restore=row["restore"],
                )
            )
    retention = dict(
        execution_id=directory.name,
        durable_root=str(directory),
        artifacts=inventory,
        upstream_retention="FS018_FS019_FS020_PRESERVE_ACTIVE",
    )
    tsv = "path\tbytes\tproducer\tconsumers\tlicense\tdelete_when\trestore\n"
    tsv += "".join(
        "\t".join(
            str(row[k]) if k != "consumers" else ",".join(row[k])
            for k in (
                "path",
                "bytes",
                "producer",
                "consumers",
                "license",
                "delete_when",
                "restore",
            )
        )
        + "\n"
        for row in inventory
    )
    immutable_bytes(retention_index, tsv.encode(), conflict="RETENTION_CONFLICT")
    report = f"""# FS-021 GLOBAL_STRATEGY_V1

Practical mode: {selected["mode"]}. Integrated index: {selected["selected"]["integrated_index"]}.
Historical loss making: {selected["historical_loss_making"]}.
Scientific leader T+150: {run["scientific_evidence"]["observed_leader"]}.
Scientific disposition: {run["scientific_evidence"]["disposition"]}.
CROSS_LAG_INFERENCE=NOT_EVALUATED_BY_FS021_V1.

231 compositions, 1,877 common matches, one 100u bankroll per composition.
Observed lags 120/130/150; scientific bootstrap T+150 only, 5,000 paired replicates per L=1/2/4 and twelve fresh slices.
Reconstructed historical 2026 evidence: ODDSPAPI_RECONSTRUCTED_T30_V1. Design conditioned on previously examined history; no prospective profitability claim.
Automatic operational routing: false. Real betting: false. Future activation belongs to FS-022.
Execution: {directory.name}. See summary for every candidate's veto and activity evidence.
"""
    authority = dict(
        schema="GLOBAL_STRATEGY_V1",
        execution_id=directory.name,
        binding=execution_binding(spec),
        practical_selection=selected,
        scientific_evidence={
            k: v for k, v in run["scientific_evidence"].items() if k != "families"
        },
        controls=[spec["input"]["candidates"][i] for i in (189, 195)],
        activation=run["activation"],
        sources=spec["sources"],
        profile=spec["input"]["profile"],
        gates=read_json(directory / "gates.json"),
    )
    root = directory / "original_publication_v1"
    root.mkdir(parents=True, exist_ok=True)
    values = {
        "FS-021_global_strategy_v1.json": authority,
        "FS-021_candidate_matrix.json": spec["input"]["candidates"],
        "FS-021_input_manifest.json": spec["input"],
        "FS-021_retention_manifest.json": retention,
        "FS-021_spec.json": spec,
        "FS-021_summary_231.json": dict(observed=observed, ranking=selected["ranking"]),
    }
    files = {
        root / name: (canonical(value) + "\n").encode()
        for name, value in values.items()
    }
    files[root / "FS-021_global_strategy_report.md"] = report.encode()
    with lock(root / ".FS-021_publication.lock"):
        for path, content in files.items():
            immutable_bytes(path, content, conflict="ORIGINAL_PUBLICATION_CONFLICT")
    # Git keeps only a compact, source-bound locator, not replicated evidence.
    index_root = base / "docs/experiments/FS-021" / directory.name
    index_root.mkdir(parents=True, exist_ok=True)
    authoritative = root / "FS-021_global_strategy_v1.json"
    index = dict(
        schema="FS021_ORIGINAL_PUBLICATION_INDEX_V1",
        execution_id=directory.name,
        relative_path="original_publication_v1/FS-021_global_strategy_v1.json",
        sha256=hashlib.sha256(authoritative.read_bytes()).hexdigest(),
        original_run_sha256=hashlib.sha256(
            (directory / "run.json").read_bytes()
        ).hexdigest(),
        selection_index=selected["selected"]["integrated_index"],
        scientific_disposition=run["scientific_evidence"]["disposition"],
        activation=False,
    )
    immutable_bytes(
        index_root / "original_v1.json",
        (canonical(index) + "\n").encode(),
        conflict="PUBLICATION_INDEX_CONFLICT",
    )
    return authority
