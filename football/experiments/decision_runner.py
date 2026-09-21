"""Freeze and execute FS-019 solely from immutable FS-018 artifact lineage."""

import gzip
import hashlib
import json
import resource
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from football.prediction.contracts import ProbabilityResult

from .comparison import compare_decisions
from .decision import (
    CANDIDATE_IDS,
    candidate_matrix,
    replay_decisions,
    validate_frozen_action_counts,
)
from .historical_prices import EVIDENCE_PROFILE, validate_price_evidence
from .reward import settle_rows, summarize_decisions
from .spec import _runtime_identity as execution_runtime
from .storage import (
    atomic_json,
    canonical,
    decision_root,
    identity,
    immutable_bytes,
    instant,
    lock,
    read_json,
    require_dev,
)
from .views import deterministic_gzip, per_match_rows

UPSTREAM = {
    "baseline": "GLOBAL_PREDICTION_V1",
    "model_code": "MARKET_CONSENSUS",
    "model_version": "fs013-market-consensus-v2",
    "config_identity": "c35e58fb446145fa698d4d122b1ddbb0e9e213dee4b1d04a756232979bb5ff7b",
    "experiment_spec_id": "de5dc600168fd249f93848e9ca3d550b0de05eed07824f9874bf5fec68d4f9d0",
    "source_acquisition_id": "55e2c9682f20d229b3ca67a102d4c084c581f33686fea094139333e041838b81",
    "execution_runtime_id": "7cbeae3db86c33001e5c82f8aa66d9619a54be247569ec5abddf465730e09cd3",
    "analysis_id": "15f313269bf23ed189ff3e50599b0b30785c23b61a1c361a7a7816f691a8ccc8",
    "full_run_id": "b41fd8a324f4fd0265c8a9d43a1308dc21f5b862d45f6583b3a75542df5c711b",
    "manifest_hash": "3339a7f8247feee99e232d94be109cb32424234661bf1a7c6c2179b4db82c61e",
    "prediction_cohort_hash": "08d8f7c2852444c2e66ed28c4075e2bc51708d3ac918cdb7cf75daf858ae2c1c",
    "data_cutoff": "2026-09-19T03:17:33.457781+00:00",
}
COMPETITION_COUNTS = {
    1270: 144,
    1272: 160,
    1273: 191,
    1274: 177,
    1275: 216,
    1276: 188,
    1277: 132,
    1278: 241,
    1325: 163,
    1459: 294,
}
COMPETITION_IDS = tuple(COMPETITION_COUNTS)

METHODOLOGY = {
    "spec_version": "fs019-v1",
    "changed_layer": "Decision",
    "candidate_matrix": candidate_matrix(),
    "price_contract": {
        "profile": EVIDENCE_PROFILE,
        "outcomes": {"101": "HOME", "102": "DRAW", "103": "AWAY"},
        "bookmakers": ["pinnacle", "bet365", "unibet"],
        "selection": "MAX_RAW_DECIMAL_PRICE",
        "representative_order": ["pinnacle", "bet365", "unibet"],
        "de_vig_payout": False,
        "cutoff": "LATEST_ACTIVE_VALID_COMPLETE_1X2_AT_OR_BEFORE_KICKOFF_MINUS_30M",
    },
    "settlement": "FIXED_UNIT_V1",
    "primary_metric": "EQUAL_LEAGUE_FIXED_UNIT_PPO_PER_DECISION_COMMON_OPPORTUNITY",
    "bootstrap": {
        "stratum": "Competition",
        "block": "Competition×Lima-ISO-week",
        "replicates": 5000,
        "seed": 18092026,
        "rng": "numpy.random.default_rng",
        "quantile": 0.95,
        "quantile_method": "LINEAR_R7",
        "rule": "MAX_CENTERED_ADVERSE_UNSTUDENTIZED_V1",
    },
    "stability": {
        "top_and_alternative": "FIXED_FROM_FULL_CORPUS",
        "leave_one_league_out": 10,
        "chronological_halves": 2,
        "sort": "kickoff-UTC-ASC,match_id-ASC",
    },
    "selection_rule": "FS019_E1_2_FALLBACK_V1",
}


@dataclass(frozen=True)
class DecisionSpec:
    serialized: str

    def __post_init__(self):
        data = json.loads(self.serialized)
        if any(data.get(key) != value for key, value in METHODOLOGY.items()):
            raise ValueError("FROZEN_DECISION_METHODOLOGY_MISMATCH")
        if data.get("upstream") != UPSTREAM:
            raise ValueError("FROZEN_UPSTREAM_LINEAGE_MISMATCH")
        if data.get("competition_ids") != list(COMPETITION_IDS):
            raise ValueError("FROZEN_DECISION_COMPETITION_SCOPE_MISMATCH")
        snapshot = data.get("snapshot", {})
        content_hash = snapshot.get("content_hash")
        cohort_hash = data.get("decision_common_cohort_hash")
        if (
            snapshot.get("row_count") != 1906
            or snapshot.get("per_league")
            != {str(key): value for key, value in COMPETITION_COUNTS.items()}
            or not isinstance(content_hash, str)
            or len(content_hash) != 64
            or any(character not in "0123456789abcdef" for character in content_hash)
            or snapshot.get("file") != f"decision-input-{content_hash}.jsonl.gz"
            or not isinstance(cohort_hash, str)
            or len(cohort_hash) != 64
            or any(character not in "0123456789abcdef" for character in cohort_hash)
        ):
            raise ValueError("FROZEN_DECISION_SNAPSHOT_CONTRACT_MISMATCH")
        object.__setattr__(self, "serialized", canonical(data))

    @property
    def data(self):
        return json.loads(self.serialized)

    @property
    def id(self):
        return identity(self.data)

    def save(self, path):
        path = Path(path)
        with lock(path.with_suffix(".lock")):
            if path.exists() and read_json(path) != self.data:
                raise ValueError("REFUSING_TO_OVERWRITE_FROZEN_DECISION_SPEC")
            atomic_json(path, self.data)

    @classmethod
    def load(cls, path):
        return cls(canonical(read_json(path)))


def _semantic_rows(rows):
    return b"".join((canonical(row) + "\n").encode() for row in rows)


def snapshot_hash(rows):
    return hashlib.sha256(_semantic_rows(rows)).hexdigest()


def decision_common_cohort_hash(rows):
    """Identify immutable opportunities independently of decisions and rewards."""
    opportunities = sorted(
        (
            {
                "match_id": row["match_id"],
                "competition_id": row["competition_id"],
                "kickoff": instant(row["kickoff"]).isoformat(),
            }
            for row in rows
        ),
        key=lambda row: (row["competition_id"], row["kickoff"], row["match_id"]),
    )
    if len({row["match_id"] for row in opportunities}) != len(opportunities):
        raise ValueError("DUPLICATE_DECISION_COMMON_OPPORTUNITY")
    return identity(opportunities)


def _verify_per_match_view(path, run):
    expected = deterministic_gzip(per_match_rows(run))
    if Path(path).read_bytes() != expected:
        raise ValueError("UPSTREAM_PER_MATCH_VIEW_MISMATCH")


def _verify_upstream(authority_path, run_directory):
    authority = read_json(authority_path)
    for key in (
        "baseline",
        "model_code",
        "model_version",
        "config_identity",
        "experiment_spec_id",
        "full_run_id",
        "manifest_hash",
        "data_cutoff",
    ):
        if authority.get(key) != UPSTREAM[key]:
            raise ValueError(f"UPSTREAM_AUTHORITY_MISMATCH:{key}")
    if authority.get("cohort_hash") != UPSTREAM["prediction_cohort_hash"]:
        raise ValueError("UPSTREAM_AUTHORITY_MISMATCH:cohort_hash")
    run_directory = Path(run_directory)
    required = ("run.json", "manifest.json", "per_match.jsonl.gz")
    if any(not (run_directory / name).is_file() for name in required):
        raise ValueError("UPSTREAM_ARTIFACTS_UNREADABLE")
    run = read_json(run_directory / "run.json")
    checks = {
        "run_id": "full_run_id",
        "analysis_id": "analysis_id",
        "source_acquisition_id": "source_acquisition_id",
        "execution_runtime_id": "execution_runtime_id",
        "spec_id": "experiment_spec_id",
    }
    for run_key, upstream_key in checks.items():
        if run.get(run_key) != UPSTREAM[upstream_key]:
            raise ValueError(f"UPSTREAM_RUN_LINEAGE_MISMATCH:{run_key}")
    if (
        identity({key: value for key, value in run.items() if key != "run_id"})
        != run["run_id"]
    ):
        raise ValueError("UPSTREAM_RUN_HASH_MISMATCH")
    if identity(run["spec"]) != run["spec_id"]:
        raise ValueError("UPSTREAM_SPEC_HASH_MISMATCH")
    if run["spec"].get("data_cutoff") != UPSTREAM["data_cutoff"]:
        raise ValueError("UPSTREAM_DATA_CUTOFF_MISMATCH")
    manifest = read_json(run_directory / "manifest.json")
    if manifest != run["manifest"] or identity(manifest) != UPSTREAM["manifest_hash"]:
        raise ValueError("UPSTREAM_MANIFEST_HASH_MISMATCH")
    if run["summary"].get("cohort_hash") != UPSTREAM["prediction_cohort_hash"]:
        raise ValueError("UPSTREAM_COHORT_HASH_MISMATCH")
    backfill_path = (
        run_directory.parent / UPSTREAM["source_acquisition_id"] / "backfill.json"
    )
    if not backfill_path.is_file():
        raise ValueError("UPSTREAM_BACKFILL_ARTIFACT_UNREADABLE")
    backfill = read_json(backfill_path)
    if (
        backfill != run.get("acquisition")
        or backfill.get("run_id") != UPSTREAM["source_acquisition_id"]
        or backfill.get("spec_id") != UPSTREAM["experiment_spec_id"]
    ):
        raise ValueError("UPSTREAM_BACKFILL_LINEAGE_MISMATCH")
    _verify_per_match_view(run_directory / "per_match.jsonl.gz", run)
    return run, manifest, backfill


def _manifest_evidence(manifest):
    result = {}
    for row in manifest:
        candidate = row.get("candidates", {}).get("MARKET_CONSENSUS", {})
        evidence_id = candidate.get("evidence_id")
        if candidate.get("status") == "PRODUCED" and evidence_id:
            if row["match_id"] in result:
                raise ValueError("DUPLICATE_UPSTREAM_MANIFEST_MATCH")
            result[row["match_id"]] = {
                "evidence_id": evidence_id,
                "outcome": row["outcome"],
                "kickoff": row["kickoff"],
                "probabilities": candidate["probabilities"],
            }
    return result


def _authoritative_evidence(backfill):
    result = {}
    for league in backfill.get("leagues", {}).values():
        for fixture in league.get("fixtures", {}).values():
            evidence = fixture.get("evidence")
            if not evidence or evidence.get("status") != "PRODUCED":
                continue
            evidence_id = evidence.get("evidence_id")
            if (
                identity(
                    {
                        key: value
                        for key, value in evidence.items()
                        if key != "evidence_id"
                    }
                )
                != evidence_id
            ):
                raise ValueError("FS018_AUTHORITATIVE_EVIDENCE_HASH_MISMATCH")
            match_id = evidence.get("match_id")
            if match_id in result:
                raise ValueError("DUPLICATE_FS018_AUTHORITATIVE_MATCH")
            result[match_id] = evidence
    return result


def _materialized_price_fields(evidence):
    books = evidence["books"]
    return {
        "match_id": evidence["match_id"],
        "provider_fixture_id": evidence["fixture_id"],
        "kickoff": evidence["kickoff"],
        "model_code": evidence["model_code"],
        "model_version": evidence["model_version"],
        "evidence_profile": evidence["evidence_profile"],
        "raw_cache_hash": evidence["raw_hash"],
        "bookmaker_count": evidence["book_count"],
        "selected_prices": {
            book: {leg["outcome_id"]: leg["price"] for leg in value["legs"]}
            for book, value in sorted(books.items())
        },
        "selected_quote_timestamps": {
            book: {leg["outcome_id"]: leg["created_at"] for leg in value["legs"]}
            for book, value in sorted(books.items())
        },
        "quote_ages_seconds": {
            book: {leg["outcome_id"]: leg["quote_age_seconds"] for leg in value["legs"]}
            for book, value in sorted(books.items())
        },
    }


def verify_authoritative_price(source, linked, retained):
    if not retained:
        raise ValueError("MISSING_FS018_AUTHORITATIVE_PRICE_EVIDENCE")
    if retained.get("evidence_id") != linked["evidence_id"]:
        raise ValueError("FS018_AUTHORITATIVE_EVIDENCE_ID_MISMATCH")
    expected = _materialized_price_fields(retained)
    if any(source.get(key) != value for key, value in expected.items()):
        raise ValueError("FS018_AUTHORITATIVE_PRICE_MISMATCH")


def build_snapshot_rows(per_match_path, manifest, backfill):
    evidence = _manifest_evidence(manifest)
    authoritative = _authoritative_evidence(backfill)
    rows = []
    with gzip.open(per_match_path, "rt") as stream:
        for line in stream:
            source = json.loads(line)
            if source.get("model_code") != "MARKET_CONSENSUS" or not source.get(
                "NATURAL"
            ):
                continue
            linked = evidence.get(source["match_id"])
            if not linked:
                raise ValueError("MISSING_FS018_MARKET_EVIDENCE_ID")
            retained = authoritative.get(source["match_id"])
            verify_authoritative_price(source, linked, retained)
            if (
                source.get("status") != "PRODUCED"
                or source.get("model_version") != UPSTREAM["model_version"]
                or source.get("config_identity") != UPSTREAM["config_identity"]
                or source.get("actual_regulation_outcome") != linked["outcome"]
                or source.get("kickoff") != linked["kickoff"]
                or [source.get(key) for key in ("p_home", "p_draw", "p_away")]
                != linked["probabilities"]
            ):
                raise ValueError("FS018_MARKET_ROW_LINEAGE_MISMATCH")
            row = {
                "match_id": source["match_id"],
                "competition_id": source["competition_id"],
                "kickoff": source["kickoff"],
                "actual_regulation_outcome": source["actual_regulation_outcome"],
                "model_code": source["model_code"],
                "model_version": source["model_version"],
                "config_identity": source["config_identity"],
                "p_home": source["p_home"],
                "p_draw": source["p_draw"],
                "p_away": source["p_away"],
                "evidence_profile": source["evidence_profile"],
                "bookmaker_count": source["bookmaker_count"],
                "selected_prices": source["selected_prices"],
                "selected_quote_timestamps": source["selected_quote_timestamps"],
                "quote_ages_seconds": source["quote_ages_seconds"],
                "provider_fixture_id": source["provider_fixture_id"],
                "fs018_evidence_id": linked["evidence_id"],
                "raw_cache_hash": source["raw_cache_hash"],
            }
            validate_price_evidence(row)
            rows.append(row)
    rows.sort(key=lambda row: (row["competition_id"], row["kickoff"], row["match_id"]))
    _validate_snapshot(rows)
    return rows


def _validate_snapshot(rows):
    if (
        len(rows) != 1906
        or len({row["match_id"] for row in rows}) != len(rows)
        or len({row["fs018_evidence_id"] for row in rows}) != len(rows)
        or len({row["provider_fixture_id"] for row in rows}) != len(rows)
    ):
        raise ValueError("DECISION_COMMON_COUNT_MISMATCH")
    if rows != sorted(
        rows,
        key=lambda row: (row["competition_id"], row["kickoff"], row["match_id"]),
    ):
        raise ValueError("DECISION_INPUT_ORDER_MISMATCH")
    counts = Counter(row["competition_id"] for row in rows)
    if counts != Counter(COMPETITION_COUNTS):
        raise ValueError("DECISION_COMMON_LEAGUE_COUNTS_MISMATCH")
    for row in rows:
        if (
            row["model_code"] != UPSTREAM["model_code"]
            or row["model_version"] != UPSTREAM["model_version"]
            or row["config_identity"] != UPSTREAM["config_identity"]
            or row["actual_regulation_outcome"] not in {"HOME", "DRAW", "AWAY"}
        ):
            raise ValueError("DECISION_INPUT_CONTRACT_MISMATCH")
        ProbabilityResult(row["p_home"], row["p_draw"], row["p_away"])
        validate_price_evidence(row)


def freeze_decision_spec(
    spec_path, *, authority_path=None, upstream_run_directory=None
):
    require_dev()
    base = Path(__file__).resolve().parents[2]
    authority_path = Path(
        authority_path or base / "docs/research/FS-018_global_prediction_v1.json"
    )
    upstream_run_directory = Path(
        upstream_run_directory
        or base / "tmp/FS-018_experiments" / UPSTREAM["analysis_id"]
    )
    _, manifest, backfill = _verify_upstream(authority_path, upstream_run_directory)
    rows = build_snapshot_rows(
        upstream_run_directory / "per_match.jsonl.gz", manifest, backfill
    )
    content_hash = snapshot_hash(rows)
    cohort_hash = decision_common_cohort_hash(rows)
    snapshot_name = f"decision-input-{content_hash}.jsonl.gz"
    spec = DecisionSpec(
        canonical(
            {
                **METHODOLOGY,
                "upstream": UPSTREAM,
                "competition_ids": list(COMPETITION_IDS),
                "decision_common_cohort_hash": cohort_hash,
                "snapshot": {
                    "file": snapshot_name,
                    "content_hash": content_hash,
                    "row_count": len(rows),
                    "per_league": {
                        str(key): value for key, value in COMPETITION_COUNTS.items()
                    },
                },
            }
        )
    )
    spec_path = Path(spec_path)
    immutable_bytes(
        spec_path.parent / snapshot_name,
        deterministic_gzip(rows),
        conflict="DECISION_INPUT_SNAPSHOT_CONFLICT",
    )
    spec.save(spec_path)
    return spec


def read_snapshot(spec, spec_path):
    snapshot_path = Path(spec_path).parent / spec.data["snapshot"]["file"]
    if snapshot_path.parent.resolve() != Path(spec_path).parent.resolve():
        raise ValueError("DECISION_SNAPSHOT_PATH_ESCAPE")
    rows = []
    try:
        with gzip.open(snapshot_path, "rt") as stream:
            rows = [json.loads(line) for line in stream]
    except (OSError, json.JSONDecodeError):
        raise ValueError("DECISION_INPUT_SNAPSHOT_UNREADABLE") from None
    if snapshot_hash(rows) != spec.data["snapshot"]["content_hash"]:
        raise ValueError("DECISION_INPUT_SNAPSHOT_HASH_MISMATCH")
    _validate_snapshot(rows)
    if decision_common_cohort_hash(rows) != spec.data["decision_common_cohort_hash"]:
        raise ValueError("DECISION_COMMON_COHORT_HASH_MISMATCH")
    return rows


def execution_identity(spec_id, snapshot_content_hash, runtime_id):
    return identity(
        {
            "lineage_version": "FS019_EXECUTION_RUNTIME_V1",
            "spec_id": spec_id,
            "snapshot_content_hash": snapshot_content_hash,
            "execution_runtime_id": runtime_id,
        }
    )


def read_decision_rows(directory, run):
    path = Path(directory) / "decision-rows.jsonl.gz"
    try:
        with gzip.open(path, "rt") as stream:
            rows = [json.loads(line) for line in stream]
    except (OSError, json.JSONDecodeError):
        raise ValueError("DECISION_ROWS_UNREADABLE") from None
    if len(rows) != run.get("decision_row_count") or snapshot_hash(rows) != run.get(
        "decision_rows_hash"
    ):
        raise ValueError("DECISION_ROWS_HASH_MISMATCH")
    return rows


def run_decision_experiment(spec, spec_path, *, base=None, workspace_root=None):
    require_dev()
    started = time.perf_counter()
    rows = read_snapshot(spec, spec_path)
    runtime = execution_runtime()
    runtime_id = identity(runtime)
    execution_id = execution_identity(
        spec.id, spec.data["snapshot"]["content_hash"], runtime_id
    )
    directory = decision_root(workspace_root) / execution_id
    with lock(directory / "analysis.lock"):
        complete = directory / "run.json"
        if complete.exists():
            result = read_json(complete)
            verify_decision_run(result, spec)
            read_decision_rows(directory, result)
            from .decision_artifacts import materialize_decision_artifacts

            materialize_decision_artifacts(directory, result, base=base)
            return result
        replayed = replay_decisions(rows)
        action_counts = validate_frozen_action_counts(replayed)
        decision_rows = settle_rows(replayed)
        metrics = summarize_decisions(decision_rows, CANDIDATE_IDS, COMPETITION_IDS)
        comparison = compare_decisions(decision_rows, CANDIDATE_IDS, COMPETITION_IDS)
        decision_content = deterministic_gzip(decision_rows)
        decision_rows_hash = snapshot_hash(decision_rows)
        resources = {
            "decision_seconds": time.perf_counter() - started,
            "rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            "decision_rows_bytes": len(decision_content),
        }
        warnings = []
        if resources["decision_seconds"] > 60:
            warnings.append("DECISION_RUNTIME_EXCEEDS_60_SECONDS")
        if resources["rss_mib"] > 512:
            warnings.append("DECISION_RSS_EXCEEDS_512_MIB")
        result = {
            "lineage_version": "FS019_EXECUTION_RUNTIME_V1",
            "execution_id": execution_id,
            "execution_runtime": runtime,
            "execution_runtime_id": runtime_id,
            "spec_id": spec.id,
            "spec": spec.data,
            "input_snapshot_hash": spec.data["snapshot"]["content_hash"],
            "decision_common_cohort_hash": spec.data["decision_common_cohort_hash"],
            "decision_rows_hash": decision_rows_hash,
            "decision_row_count": len(decision_rows),
            "summary": {
                "natural_count": len(rows),
                "decision_common_count": len(rows),
                "price_coverage": 1.0,
                "action_counts": action_counts,
                "candidate_metrics": metrics,
                **comparison,
            },
            "resources": resources,
            "warnings": warnings,
        }
        result["run_id"] = identity(result)
        immutable_bytes(
            directory / "decision-rows.jsonl.gz",
            decision_content,
            conflict="DECISION_ROWS_CONFLICT",
        )
        atomic_json(complete, result)
        from .decision_artifacts import materialize_decision_artifacts

        materialize_decision_artifacts(directory, result, base=base)
        return result


def verify_decision_run(result, spec):
    if result.get("spec_id") != spec.id or result.get("spec") != spec.data:
        raise ValueError("DECISION_RUN_SPEC_MISMATCH")
    if identity(
        {key: value for key, value in result.items() if key != "run_id"}
    ) != result.get("run_id"):
        raise ValueError("DECISION_RUN_HASH_MISMATCH")
    if result.get("input_snapshot_hash") != spec.data["snapshot"]["content_hash"]:
        raise ValueError("DECISION_RUN_INPUT_MISMATCH")
    if (
        result.get("decision_common_cohort_hash")
        != spec.data["decision_common_cohort_hash"]
    ):
        raise ValueError("DECISION_RUN_COHORT_MISMATCH")
    if identity(result.get("execution_runtime")) != result.get("execution_runtime_id"):
        raise ValueError("DECISION_RUNTIME_IDENTITY_MISMATCH")
    expected = execution_identity(
        spec.id, result["input_snapshot_hash"], result["execution_runtime_id"]
    )
    if result.get("execution_id") != expected:
        raise ValueError("DECISION_EXECUTION_LINEAGE_MISMATCH")
