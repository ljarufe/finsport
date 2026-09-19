"""Deterministic, derived local run views; never include raw provider payloads."""

import gzip
import hashlib
import io
import math
import sys
from pathlib import Path

from football.prediction.constants import OUTCOMES
from football.prediction.datasets import local_day

from .artifacts import effective_baseline_config, human_report
from .storage import atomic_bytes, canonical, identity, instant


def _market_by_match(run):
    evidence = {}
    for league in run["acquisition"]["leagues"].values():
        for item in league["fixtures"].values():
            if item.get("evidence"):
                evidence[item["evidence"]["match_id"]] = item["evidence"]
    return evidence


def per_match_rows(run):
    data = run["spec"]
    summary = run["summary"]
    common = set(summary["cohorts"]["COMMON"])
    natural = {code: set(ids) for code, ids in summary["cohorts"]["NATURAL"].items()}
    market = _market_by_match(run)
    config_ids = {
        code: identity(effective_baseline_config(data, code)) for code in data["models"]
    }
    for match in sorted(
        run["manifest"],
        key=lambda r: (r["competition_id"], r["kickoff"], r["match_id"]),
    ):
        evidence = market.get(match["match_id"])
        for code in sorted(data["models"]):
            candidate = match["candidates"][code]
            vector = candidate.get("probabilities")
            actual = match["outcome"]
            loss = brier = rps = None
            if vector is not None and actual in OUTCOMES:
                target = [float(outcome == actual) for outcome in OUTCOMES]
                epsilon = sys.float_info.epsilon
                clipped = [max(epsilon, min(1 - epsilon, p)) for p in vector]
                loss = -math.log(clipped[OUTCOMES.index(actual)] / sum(clipped))
                brier = sum((p - y) ** 2 for p, y in zip(vector, target))
                rps = sum((sum(vector[:i]) - sum(target[:i])) ** 2 for i in (1, 2)) / 2
            source = evidence if code == "MARKET_CONSENSUS" else None
            books = source["books"] if source else {}
            yield {
                "match_id": match["match_id"],
                "competition_id": match["competition_id"],
                "kickoff": match["kickoff"],
                "lima_local_day": local_day(instant(match["kickoff"])).isoformat(),
                "eligible": match["eligible"],
                "model_code": code,
                "model_version": candidate["model_version"],
                "config_identity": config_ids[code],
                "competition_config_identity": (
                    identity(
                        data["configs"][str(match["competition_id"])]["selected"][
                            code.lower()
                        ]
                    )
                    if code != "MARKET_CONSENSUS"
                    else None
                ),
                "p_home": vector[0] if vector else None,
                "p_draw": vector[1] if vector else None,
                "p_away": vector[2] if vector else None,
                "actual_regulation_outcome": actual or None,
                "log_loss": loss,
                "multiclass_brier": brier,
                "rps": rps,
                "COMMON": match["match_id"] in common,
                "NATURAL": match["match_id"] in natural.get(code, set()),
                "status": candidate["status"],
                "reason": candidate["reason"],
                "evidence_profile": source["evidence_profile"] if source else None,
                "provider_fixture_id": source["fixture_id"] if source else None,
                "bookmaker_count": source["book_count"] if source else None,
                "selected_quote_timestamps": {
                    book: {
                        leg["outcome_id"]: leg["created_at"] for leg in value["legs"]
                    }
                    for book, value in sorted(books.items())
                },
                "quote_ages_seconds": {
                    book: {
                        leg["outcome_id"]: leg["quote_age_seconds"]
                        for leg in value["legs"]
                    }
                    for book, value in sorted(books.items())
                },
                "selected_prices": {
                    book: {leg["outcome_id"]: leg["price"] for leg in value["legs"]}
                    for book, value in sorted(books.items())
                },
                "raw_cache_hash": source["raw_hash"] if source else None,
            }


def deterministic_gzip(rows):
    content = "".join(canonical(row) + "\n" for row in rows).encode()
    stream = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as zipped:
        zipped.write(content)
    result = bytearray(stream.getvalue())
    result[9] = 255  # fixed OS header byte
    return bytes(result)


def materialize_views(directory, run):
    directory = Path(directory)
    summary = {
        **run["summary"],
        "acquisition_audit": run["acquisition"].get("audit", {}),
    }
    views = {
        "spec.json": (canonical(run["spec"]) + "\n").encode(),
        "manifest.json": (canonical(run["manifest"]) + "\n").encode(),
        "summary.json": (canonical(summary) + "\n").encode(),
        "per_match.jsonl.gz": deterministic_gzip(per_match_rows(run)),
        "report.md": human_report(run, local=True).encode(),
    }
    for name, content in views.items():
        path = directory / name
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError(f"RUN_VIEW_CONFLICT:{name}")
        else:
            atomic_bytes(path, content)
    return {
        name: hashlib.sha256(content).hexdigest() for name, content in views.items()
    }
