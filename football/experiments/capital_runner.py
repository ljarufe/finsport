"""FS-020 local binding and restartable execution using Experiment Lab storage."""

import gzip
import hashlib
import io
import json
import platform
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, getcontext
from pathlib import Path

import numpy as np
from django.conf import settings

from .capital_analysis import (
    BLOCKS,
    LAGS,
    REPLICATES,
    SEED,
    array_hash,
    block_draws,
    bootstrap_scores,
    calendar_weeks,
    finalize_lags,
    observed_order,
    paired_max_t,
    stability_checks,
    week_start,
    within_lag,
)
from .capital_events import (
    RUNNER_VERSION,
    CapitalCandidate,
    Opportunity,
    run_event_path,
)
from .decision_artifacts import PROMOTION_REF as DECISION_REF
from .decision_artifacts import resolve_global_decision
from .decision_runner import snapshot_hash
from .storage import (
    canonical,
    experiment_workspace_root,
    identity,
    immutable_bytes,
    instant,
    lock,
    read_json,
    require_dev,
)

RESEARCH_REF = "docs/research/FS-020_global_capital_methodology_research.md"
SEMANTIC_SHA = "5ee79477d0e9c6709f0530b0971a853205780966bc5c8c40eabac148ef963391"
GZIP_SHA = "52f3a850e6c9781d26021878698199b54c014eb368e7262e1aec55f777ffd7cc"
REFERENCE_RNG_HASHES = {
    "1": "e631dccb1c9cec30ddb6531a83a6b242856001703bfe4a6fde46f35b746761bb",
    "2": "1bbed9db7c98fcc36403dec74f265260fdf3e414723e1d300d80466ccc6ef2e0",
    "4": "d069403cecf99c572c936699c6f01b88dea11b76951c3628decafbdc6c941835",
}
CANDIDATES = tuple(
    CapitalCandidate(code, version, canonical(config), lanes)
    for code, version, config, lanes in (
        ("FLAT_UNIT", "fs004-flat-unit-v1", {"unit": "1"}, 10),
        (
            "FIXED_FRACTION_BANKROLL",
            "fs004-fixed-fraction-bankroll-v1",
            {"fraction": "0.05"},
            10,
        ),
        (
            "FIXED_TARGET_PROFIT_NO_RECOVERY",
            "fs004-fixed-target-no-recovery-v1",
            {"target_profit": "1"},
            10,
        ),
        (
            "LEGACY_RECOVERY",
            "fs004-legacy-recovery-deviation-1-v1",
            {"initial_stake": "1"},
            1,
        ),
        (
            "LEGACY_CAPPED",
            "fs004-legacy-capped-v1",
            {"initial_stake": "1", "max_absolute_stake": "5"},
            1,
        ),
        (
            "LEGACY_PARTIAL",
            "fs004-legacy-partial-v1",
            {"target_profit": "1", "alpha": "0.5"},
            1,
        ),
        ("FRACTIONAL_KELLY", "fs004-fractional-kelly-v1", {"lambda": "0.25"}, 10),
    )
)
CONTRACT = dict(
    spec_version="FS020_E24_V1",
    changed_layer="Capital",
    runner_version=RUNNER_VERSION,
    candidates=[c.data() for c in CANDIDATES],
    initial_bankroll="100",
    metric="TOTAL_RETURN",
    lags=list(LAGS),
    primary_lag=150,
    timezone="America/Lima",
    execution="kickoff-30m",
    bootstrap=dict(
        blocks=list(BLOCKS),
        primary_block=2,
        replicates=REPLICATES,
        seed=SEED,
        rng="PCG64/SeedSequence([seed,L])",
        sampling="GLOBAL_PAIRED_STATEFUL_MOVING_BLOCK",
        tail="TRUNCATE_TO_W_WEEKS",
        empty_weeks="RETAIN",
        reference_rng_hashes=REFERENCE_RNG_HASHES,
        reference_hash_encoding="UNSPECIFIED_IN_RESEARCH",
    ),
    inference="E2.4_SECTION_11_ALL_PAIRS_MAX_T_DDOF1_LINEAR_95",
    stability="FIXED_FULL_TOP_VS_RUNNER_UP_FRESH_HALVES_AND_LOO",
    disposition="E2.4_SECTION_8",
    operational_activation=False,
)


def rng_manifest():
    """Our exact encoding is explicit; research artifact hashes remain opaque.

    E2.4 supplies reference hashes without a byte/serialization convention.
    Do not compare those to an invented encoding or claim byte equivalence.
    """
    return {
        str(length): {
            "shape": [CONTRACT["bootstrap"]["replicates"], (36 + length - 1) // length],
            "encoding": "C_ORDER_LITTLE_ENDIAN_INT64_BLOCK_STARTS",
            "sha256": array_hash(
                block_draws(36, length, replicates=CONTRACT["bootstrap"]["replicates"])
            ),
            "reference_sha256": REFERENCE_RNG_HASHES[str(length)],
            "reference_equivalence": "PENDING_ORIGINAL_ENCODING_OR_MANIFEST",
        }
        for length in BLOCKS
    }


def capital_root(workspace_root=None):
    return experiment_workspace_root(workspace_root) / "FS-020_experiments"


def local_capital_spec_path(path, *, workspace_root=None):
    path = Path(path).resolve()
    if (
        not path.is_relative_to(capital_root(workspace_root).resolve())
        or path.suffix != ".json"
    ):
        raise ValueError("CAPITAL_SPEC_OUTSIDE_EXPERIMENT_WORKSPACE")
    return path


def write_json_once(path, value):
    immutable_bytes(
        path, (canonical(value) + "\n").encode(), conflict="CAPITAL_ARTIFACT_CONFLICT"
    )


def source_binding(*, base=None):
    """Resolve through FS-019 first, then pin the exact local selected corpus."""
    base = Path(base or settings.BASE_DIR)
    try:
        source = resolve_global_decision(base=base)
        authority = read_json(base / DECISION_REF)
        content = (base / source.selected_decision_stream_path).read_bytes()
        rows = [
            json.loads(line) for line in gzip.decompress(content).decode().splitlines()
        ]
        if (
            source.model_code != "MARKET_CONSENSUS"
            or source.model_version != "fs013-market-consensus-v2"
            or source.decision_policy_code != "MODAL_ALL"
            or source.decision_policy_version != "fs003-modal-all-v1"
            or source.selected_decision_stream_semantic_hash != SEMANTIC_SHA
            or hashlib.sha256(content).hexdigest() != GZIP_SHA
            or snapshot_hash(rows) != SEMANTIC_SHA
            or len(rows) != 1906
            or len({r["match_id"] for r in rows}) != 1906
        ):
            raise ValueError("FROZEN_FS019_STREAM_MISMATCH")
        opportunities = tuple(
            Opportunity(
                identity=str(row["match_id"]),
                source_id=row["match_id"],
                competition_id=row["competition_id"],
                kickoff=instant(row["kickoff"]),
                execution_at=instant(row["kickoff"]) - timedelta(minutes=30),
                action=row["decision"]["action"],
                selected_outcome=row["decision"]["selected_outcome"],
                actual_outcome=row["historical_outcome"],
                price=(
                    Decimal(str(row["price"]["selected_raw_decimal"]))
                    if row["decision"]["action"] == "BET"
                    else None
                ),
                probability=(
                    Decimal(
                        str(row["upstream_prediction"]["selected_model_probability"])
                    )
                    if row["decision"]["action"] == "BET"
                    else None
                ),
            )
            for row in rows
        )
        weeks = calendar_weeks(opportunities)
        empty = [
            w.date().isoformat()
            for w in weeks
            if not any(week_start(o.execution_at) == w for o in opportunities)
        ]
        if (
            len(weeks) != 36
            or len(empty) != 6
            or weeks[0].date().isoformat() != "2026-01-12"
            or weeks[-1].date().isoformat() != "2026-09-14"
            or len({o.competition_id for o in opportunities}) != 10
        ):
            raise ValueError("FROZEN_CAPITAL_CALENDAR_MISMATCH")
        binding = dict(
            authority=authority,
            authority_hash=identity(authority),
            stream_semantic_sha256=SEMANTIC_SHA,
            stream_gzip_sha256=GZIP_SHA,
            row_count=len(rows),
            cohort_hash=source.decision_common_cohort_hash,
            calendar=dict(weeks=[w.isoformat() for w in weeks], empty_weeks=empty),
        )
        return opportunities, binding
    except (ValueError, KeyError, TypeError, OSError, ArithmeticError) as error:
        raise ValueError(f"INPUT_INTEGRITY_FAIL:{error}") from error


@dataclass(frozen=True)
class CapitalSpec:
    serialized: str

    def __post_init__(self):
        data = json.loads(self.serialized)
        if any(data.get(k) != v for k, v in CONTRACT.items()):
            raise ValueError("FROZEN_CAPITAL_METHODOLOGY_MISMATCH")
        binding = data["input"]
        if (
            binding["stream_semantic_sha256"] != SEMANTIC_SHA
            or binding["stream_gzip_sha256"] != GZIP_SHA
            or binding["row_count"] != 1906
            or binding["authority_hash"] != identity(binding["authority"])
            or data["candidate_matrix_id"] != identity(CONTRACT["candidates"])
            or data.get("rng_manifest") != rng_manifest()
            or len(data["research_sha256"]) != 64
        ):
            raise ValueError("FROZEN_CAPITAL_LINEAGE_MISMATCH")
        object.__setattr__(self, "serialized", canonical(data))

    @property
    def data(self):
        return json.loads(self.serialized)

    @property
    def id(self):
        return identity(self.data)

    @classmethod
    def load(cls, path):
        return cls(canonical(read_json(path)))

    def save(self, path):
        path = Path(path)
        with lock(path.with_suffix(".lock")):
            write_json_once(path, self.data)


def freeze_capital_spec(path, *, base=None):
    require_dev()
    base = Path(base or settings.BASE_DIR)
    _, binding = source_binding(base=base)
    for candidate in CANDIDATES:
        candidate.policy()
    spec = CapitalSpec(
        canonical(
            dict(
                CONTRACT,
                input=binding,
                candidate_matrix_id=identity(CONTRACT["candidates"]),
                rng_manifest=rng_manifest(),
                research_sha256=hashlib.sha256(
                    (base / RESEARCH_REF).read_bytes()
                ).hexdigest(),
            )
        )
    )
    spec.save(path)
    return spec


def capital_runtime():
    package = Path(__file__).resolve().parents[1]
    paths = sorted(
        [
            *(package / "experiments").glob("*.py"),
            *(package / "capital").glob("*.py"),
            package / "management/commands/run_capital_experiment.py",
        ]
    )
    context = getcontext()
    return dict(
        version=RUNNER_VERSION,
        python=platform.python_version(),
        numpy=np.__version__,
        decimal=dict(
            prec=context.prec,
            rounding=context.rounding,
            Emin=context.Emin,
            Emax=context.Emax,
            traps=sorted(
                signal.__name__ for signal, enabled in context.traps.items() if enabled
            ),
        ),
        code_hash=identity(
            {
                str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in paths
            }
        ),
    )


def execution_context(spec, *, base=None, workspace_root=None):
    require_dev()
    base = Path(base or settings.BASE_DIR)
    opportunities, binding = source_binding(base=base)
    if (
        binding != spec.data["input"]
        or hashlib.sha256((base / RESEARCH_REF).read_bytes()).hexdigest()
        != spec.data["research_sha256"]
    ):
        raise ValueError("INPUT_INTEGRITY_FAIL:FROZEN_BINDING_CHANGED")
    runtime = capital_runtime()
    execution_id = identity(
        dict(spec_id=spec.id, runtime=runtime, input=identity(binding))
    )
    return (
        opportunities,
        runtime,
        execution_id,
        capital_root(workspace_root) / execution_id,
    )


def execute_shard(opportunities, execution_id, directory, lag, length, start, stop):
    """Immutable absolute-range shards; a restart verifies rather than overwrites."""
    if lag not in LAGS or length not in BLOCKS or not 0 <= start < stop <= REPLICATES:
        raise ValueError("INVALID_CAPITAL_SHARD")
    key = dict(execution_id=execution_id, lag=lag, block=length, start=start, stop=stop)
    path = Path(directory) / "shards" / f"{lag}-{length}-{start:05d}-{stop:05d}.json"
    with lock(path.with_suffix(".lock")):
        if path.exists():
            result = read_json(path)
            verify_shard(result, key)
            return result
        try:
            scores = bootstrap_scores(
                opportunities, CANDIDATES, lag, length, start, stop
            )
            result = dict(key, status="COMPLETE", scores=scores.tolist(), error=None)
        except (ValueError, ArithmeticError) as error:
            result = dict(
                key, status="INSUFFICIENT_EVIDENCE", scores=None, error=str(error)
            )
        result["shard_id"] = identity(result)
        write_json_once(path, result)
        return result


def verify_shard(shard, key):
    if any(shard.get(k) != v for k, v in key.items()) or shard.get(
        "shard_id"
    ) != identity({k: v for k, v in shard.items() if k != "shard_id"}):
        raise ValueError("CAPITAL_SHARD_IDENTITY_MISMATCH")
    if shard["status"] == "COMPLETE":
        scores = np.asarray(shard["scores"], dtype=np.float64)
        if (
            scores.shape != (7, key["stop"] - key["start"])
            or not np.isfinite(scores).all()
        ):
            raise ValueError("CAPITAL_SHARD_SCORES_INVALID")
    elif shard["status"] != "INSUFFICIENT_EVIDENCE" or shard["scores"] is not None:
        raise ValueError("CAPITAL_SHARD_STATUS_INVALID")


def reduce_shards(shards, execution_id, lag, length):
    ordered = sorted(shards, key=lambda s: s["start"])
    cursor = 0
    for shard in ordered:
        key = dict(
            execution_id=execution_id,
            lag=lag,
            block=length,
            start=cursor,
            stop=shard["stop"],
        )
        verify_shard(shard, key)
        if shard["stop"] <= cursor or shard["stop"] > REPLICATES:
            raise ValueError("CAPITAL_SHARD_RANGE_MISMATCH")
        cursor = shard["stop"]
    if cursor != REPLICATES:
        raise ValueError("CAPITAL_SHARDS_INCOMPLETE")
    if any(s["status"] != "COMPLETE" for s in ordered):
        raise ValueError("CAPITAL_SHARD_PATH_UNESTIMABLE")
    return np.concatenate(
        [np.asarray(s["scores"], dtype=np.float64) for s in ordered], axis=1
    )


def _design_scores(opportunities, execution_id, directory, lag, length):
    # Discover prior shards so any complete, non-overlapping partition can resume.
    shards = [
        read_json(p)
        for p in sorted((directory / "shards").glob(f"{lag}-{length}-*.json"))
    ]
    shards.sort(key=lambda s: s["start"])
    cursor, complete = 0, []
    for shard in shards:
        if shard["start"] < cursor:
            raise ValueError("OVERLAPPING_CAPITAL_SHARDS")
        while cursor < shard["start"]:
            stop = min(cursor + 100, shard["start"])
            complete.append(
                execute_shard(
                    opportunities, execution_id, directory, lag, length, cursor, stop
                )
            )
            cursor = stop
        verify_shard(
            shard,
            dict(
                execution_id=execution_id,
                lag=lag,
                block=length,
                start=cursor,
                stop=shard["stop"],
            ),
        )
        complete.append(shard)
        cursor = shard["stop"]
    while cursor < REPLICATES:
        stop = min(cursor + 100, REPLICATES)
        complete.append(
            execute_shard(
                opportunities, execution_id, directory, lag, length, cursor, stop
            )
        )
        cursor = stop
    return reduce_shards(complete, execution_id, lag, length)


def run_capital_experiment(spec, *, base=None, workspace_root=None):
    opportunities, runtime, execution_id, directory = execution_context(
        spec, base=base, workspace_root=workspace_root
    )
    with lock(directory / "run.lock"):
        path = directory / "run.json"
        if path.exists():
            result = read_json(path)
            verify_capital_run(result, spec, directory=directory)
            return result
        lags, artifacts = {}, {}
        for lag in LAGS:
            try:
                observed = [
                    run_event_path(opportunities, c, lag, trace=True)
                    for c in CANDIDATES
                ]
                metrics = [r["metrics"] for r in observed]
                ledger_name = f"ledger-{lag}.json.gz"
                ledger_bytes = gzip.compress(
                    (canonical(observed) + "\n").encode(), mtime=0
                )
                immutable_bytes(
                    directory / ledger_name,
                    ledger_bytes,
                    conflict="CAPITAL_LEDGER_CONFLICT",
                )
                artifacts[ledger_name] = hashlib.sha256(ledger_bytes).hexdigest()
                top, second = observed_order(metrics)[:2]
                stability = stability_checks(
                    opportunities, CANDIDATES, lag, top, second
                )
                families = {}
                for length in BLOCKS:
                    scores = _design_scores(
                        opportunities, execution_id, directory, lag, length
                    )
                    buffer = io.BytesIO()
                    np.save(buffer, scores, allow_pickle=False)
                    name = f"scores-{lag}-{length}.npy"
                    content = buffer.getvalue()
                    immutable_bytes(
                        directory / name, content, conflict="CAPITAL_SCORES_CONFLICT"
                    )
                    artifacts[name] = hashlib.sha256(content).hexdigest()
                    families[str(length)] = dict(
                        paired_max_t([m["total_return"] for m in metrics], scores),
                        scores_hash=array_hash(scores),
                        draws_hash=array_hash(block_draws(36, length)),
                    )
                lags[str(lag)] = within_lag(CANDIDATES, metrics, families, stability)
            except (ValueError, ArithmeticError) as error:
                lags[str(lag)] = dict(
                    disposition="INSUFFICIENT_EVIDENCE",
                    error=str(error),
                    promotion="NO_PROMOTION",
                )
        summary = finalize_lags(lags)
        result = dict(
            schema="FS020_RUN_V1",
            spec=spec.data,
            spec_id=spec.id,
            execution_runtime=runtime,
            execution_runtime_id=identity(runtime),
            execution_id=execution_id,
            analysis_id=identity(
                dict(
                    execution_id=execution_id,
                    rule=CONTRACT["inference"],
                    disposition=CONTRACT["disposition"],
                )
            ),
            input_hash=identity(spec.data["input"]),
            lags=lags,
            summary=summary,
            artifacts=artifacts,
        )
        result["run_id"] = identity(result)
        write_json_once(path, result)
        return result


def verify_capital_run(run, spec, *, directory=None):
    if (
        run.get("schema") != "FS020_RUN_V1"
        or run.get("spec") != spec.data
        or run.get("spec_id") != spec.id
        or run.get("run_id")
        != identity({k: v for k, v in run.items() if k != "run_id"})
        or run.get("execution_runtime_id") != identity(run["execution_runtime"])
        or run.get("input_hash") != identity(spec.data["input"])
        or run.get("execution_id")
        != identity(
            dict(
                spec_id=spec.id,
                runtime=run["execution_runtime"],
                input=identity(spec.data["input"]),
            )
        )
        or run.get("summary") != finalize_lags(run["lags"])
        or run.get("analysis_id")
        != identity(
            dict(
                execution_id=run["execution_id"],
                rule=CONTRACT["inference"],
                disposition=CONTRACT["disposition"],
            )
        )
    ):
        raise ValueError("CAPITAL_RUN_IDENTITY_MISMATCH")
    if set(run["lags"]) != {"120", "130", "150"}:
        raise ValueError("CAPITAL_RUN_LAGS_INCOMPLETE")
    if directory is not None:
        directory = Path(directory).resolve()
        for name, digest in run["artifacts"].items():
            path = (directory / name).resolve()
            if (
                not path.is_relative_to(directory)
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest
            ):
                raise ValueError("CAPITAL_RUN_ARTIFACT_MISMATCH")
