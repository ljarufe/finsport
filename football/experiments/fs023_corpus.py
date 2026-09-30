"""Fail-closed restore of the authenticated FS-023 A ∪ B research population."""

import gzip
import hashlib
import json
import shutil
from pathlib import Path

ARTIFACTS = (
    (
        "state_corrected_common_T30_T10_T5.jsonl.gz",
        "f4e841ab89c303198b31e307b2fd7a76ffe65a9751a9908b131e6a2c1bbf15e8",
        2059,
    ),
    (
        "eligible_common_T30_T10_T5.jsonl.gz",
        "f15554f3180bbecc89bf17947f30ff2a075aaf92d5893cabd94160f94784151e",
        546,
    ),
)
DEFAULT_DURABLE = Path(
    "/home/ljarufe/Documents/finsport/research-evidence/FS-023/final"
)


def authenticated_rows(durable=DEFAULT_DURABLE, *, restore_to=None):
    durable = Path(durable)
    groups = []
    for name, digest, count in ARTIFACTS:
        path = durable / name
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise ValueError(f"FS023_CORPUS_HASH_MISMATCH:{name}")
        with gzip.open(path, "rt", encoding="utf-8") as source:
            rows = [json.loads(line) for line in source]
        if len(rows) != count or len({row["fixture_id"] for row in rows}) != count:
            raise ValueError(f"FS023_CORPUS_CARDINALITY_MISMATCH:{name}")
        groups.append(rows)
    if {row["fixture_id"] for row in groups[0]} & {
        row["fixture_id"] for row in groups[1]
    }:
        raise ValueError("FS023_CORPUS_OVERLAP")
    rows = sorted(
        groups[0] + groups[1], key=lambda row: (row["kickoff_utc"], row["fixture_id"])
    )
    if len(rows) != 2605 or len({row["country"] for row in rows}) != 16:
        raise ValueError("FS023_CORPUS_UNION_MISMATCH")
    if restore_to is not None:
        target = Path(restore_to)
        target.mkdir(parents=True, exist_ok=True)
        for name, digest, _ in ARTIFACTS:
            dest = target / name
            if (
                dest.exists()
                and hashlib.sha256(dest.read_bytes()).hexdigest() != digest
            ):
                raise ValueError(f"FS023_RESTORE_CONFLICT:{name}")
            if not dest.exists():
                shutil.copyfile(durable / name, dest)
    return rows


def corpus_identity():
    return {
        "schema": "PRIMARY_FS023_CORPUS_A_UNION_B_BY_FIXTURE_ID",
        "rows": 2605,
        "overlap": 0,
        "artifacts": [
            {"name": name, "sha256": digest, "rows": count}
            for name, digest, count in ARTIFACTS
        ],
    }
