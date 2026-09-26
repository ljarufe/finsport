"""FS-021 bounded workers, immutable checkpoints and explicit staged execution."""

import gzip
import io
import json
import multiprocessing
import os
import resource
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

import numpy as np

from .capital_analysis import block_draws, calendar_weeks, sampled_path, week_start
from .capital_runner import CANDIDATES, write_json_once
from .integrated_analysis import practical_selection, scientific_evidence
from .integrated_events import run_integrated_path
from .integrated_inputs import require, resolve_inputs, sha_file
from .storage import atomic_json, canonical, identity, immutable_bytes, lock, read_json

RISK_COLUMNS = (
    "maximum_drawdown",
    "minimum_equity",
    "minimum_available_cash",
    "operational_depletion",
    "ever_nonpositive_equity",
    "mean_reserved_exposure",
    "peak_reserved_exposure",
    "drawdown_duration_seconds",
    "recovery_duration_seconds",
    "underwater_unrecovered",
)


class ResourcePause(Exception):
    """Checkpointed work remains valid; only explicit resume may continue."""


def store_artifact(directory, name, content, binding):
    path = Path(directory) / name
    meta = path.with_name(path.name + ".manifest.json")
    expected = dict(
        binding=binding,
        bytes=len(content),
        sha256=__import__("hashlib").sha256(content).hexdigest(),
        status="COMPLETE",
    )
    with lock(path.with_name(path.name + ".lock")):
        if path.exists() or meta.exists():
            require(
                path.exists() and meta.exists(),
                "INCOMPLETE_CHECKPOINT_RESTORE_REQUIRED",
            )
            require(
                read_json(meta) == expected and sha_file(path) == expected["sha256"],
                "CORRUPT_CHECKPOINT",
            )
        else:
            immutable_bytes(path, content, conflict="ARTIFACT_CONFLICT")
            require(
                sha_file(path) == expected["sha256"]
                and path.stat().st_size == expected["bytes"],
                "CHECKPOINT_READBACK",
            )
            write_json_once(meta, expected)
    return expected


def read_artifact(directory, name, binding):
    path = Path(directory) / name
    meta = read_json(path.with_name(path.name + ".manifest.json"))
    require(
        meta["status"] == "COMPLETE"
        and meta["binding"] == binding
        and path.stat().st_size == meta["bytes"]
        and sha_file(path) == meta["sha256"],
        "CORRUPT_CHECKPOINT",
    )
    return path.read_bytes()


def json_artifact(directory, name, value, binding):
    return store_artifact(directory, name, (canonical(value) + "\n").encode(), binding)


def execution_binding(spec):
    return dict(
        spec_sha=identity(spec),
        runner_sha=identity(spec["runner"]),
        cohort_sha=spec["input"]["cohort_sha"],
        stream_sha=spec["input"]["stream_sha"],
        calendar_sha=spec["input"]["calendar_sha"],
    )


def validate_execution(directory, base, pack, per_match):
    directory = Path(directory)
    spec = read_json(directory / "spec.json")
    streams, binding = resolve_inputs(base, pack, per_match)
    require(binding == spec["input"], "FROZEN_INPUT_CHANGED")
    require(directory.name == identity(execution_binding(spec)), "EXECUTION_ID")
    gates = read_json(directory / "gates.json")
    require(gates["binding"] == execution_binding(spec), "GATE_BINDING")
    require(
        all(
            gates.get(k) == "PASS"
            for k in (
                "INPUT_AND_ARTIFACT_INTEGRITY",
                "SEMANTIC_CONFORMANCE",
                "RUNNER_EQUIVALENCE",
            )
        ),
        "TECHNICAL_GATES_REQUIRED",
    )
    for gate in ("SEMANTIC_CONFORMANCE", "RUNNER_EQUIVALENCE"):
        evidence = gates[gate + "_evidence"]
        require((directory / evidence["log"]).is_file(), "GATE_LOG_MISSING")
        require(
            (directory / evidence["log"]).with_suffix(".xml").is_file(),
            "GATE_JUNIT_MISSING",
        )
    reference = json.loads(
        read_artifact(directory, "technical/v2r.json", execution_binding(spec))
    )
    require(
        reference["status"] == "PASS" and len(reference["cells"]) == 21,
        "V2R_GATE_REQUIRED",
    )
    return streams, spec


class Progress:
    def __init__(self, directory, stage):
        self.directory = Path(directory)
        self.state = dict(
            stage=stage,
            completed=0,
            total=0,
            candidate=None,
            workers=0,
            last_checkpoint=None,
        )
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._heartbeat, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def _heartbeat(self):
        while not self.stop.is_set():
            atomic_json(
                self.directory / "heartbeat.json", dict(self.state, time=time.time())
            )
            self.stop.wait(3)

    def check(self):
        control = read_json(self.directory / "control.json")
        if control.get("pause") or time.time() - control.get("time", 0) > 20:
            raise ResourcePause("PAUSE_RESOURCE:SUPERVISOR_CONTROL")

    def update(self, **values):
        self.state.update(values)

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join()


def observe(directory, streams, spec, progress):
    directory = Path(directory)
    binding = execution_binding(spec)
    observed = {str(lag): [] for lag in (120, 130, 150)}
    start = time.monotonic()
    cpu = time.process_time()
    wakes = 0
    physical_events = 0
    fresh = 0
    progress.update(total=693, workers=1)
    for lag in (120, 130, 150):
        for i, arm in enumerate(spec["input"]["candidates"]):
            progress.check()
            name = f"observed/{lag}-{i:03d}.json.gz"
            key = dict(binding, lag=lag, integrated_index=i)
            if (directory / name).exists():
                result = json.loads(
                    gzip.decompress(read_artifact(directory, name, key))
                )
            else:
                pd = arm["pd_index"]
                result = run_integrated_path(
                    streams[pd],
                    CANDIDATES[arm["capital_index"]],
                    lag,
                    trace=True,
                    original_stream_sha=spec["input"]["streams"][pd][
                        "original_stream_sha256"
                    ],
                )
                store_artifact(
                    directory,
                    name,
                    gzip.compress((canonical(result) + "\n").encode(), mtime=0),
                    key,
                )
                wakes += result["physical_wakes"]
                physical_events += len(result["ledger"])
                fresh += 1
            observed[str(lag)].append(result["metrics"])
            progress.update(
                completed=sum(map(len, observed.values())),
                candidate=i,
                composition=arm,
                lag=lag,
                last_termination=result["metrics"]["termination_reason"]
                or "COMPLETED_HORIZON",
                last_checkpoint=name,
            )
    json_artifact(directory, "observed.json", observed, binding)
    elapsed = time.monotonic() - start
    # Restart measurements are explicitly partial; never pretend cached work was timed.
    measurement = dict(
        wall_seconds=elapsed,
        cpu_seconds=time.process_time() - cpu,
        process_max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        physical_wakes=wakes,
        physical_events=physical_events,
        fresh_paths=fresh,
        cached_paths=693 - fresh,
        fresh_paths_per_second=fresh / elapsed,
        observed_bytes=sum(
            p.stat().st_size for p in (directory / "observed").glob("*.gz")
        ),
    )
    json_artifact(
        directory, f"measurements/{identity(measurement)}.json", measurement, binding
    )
    if not (directory / "budget.json").exists():
        require(fresh > 0, "OBSERVED_MEASUREMENT_REQUIRED")
        budget = dict(
            evidence=measurement,
            max_workers=24,
            shard_replicates=1,
            nominal_bootstrap_paths=3465000,
            estimated_cpu_seconds=(measurement["cpu_seconds"] / fresh) * 3465000,
            max_new_artifact_gib=50,
            min_free_gib=80,
            qualification="ARITHMETIC_PROJECTION_FROM_OBSERVED_NOT_SUSTAINED_THERMAL_CERTIFICATION",
        )
        json_artifact(directory, "budget.json", budget, binding)
    return observed


_POOL_STREAMS = None
_POOL_WEEKS = None
_POOL_DIRECTORY = None


def init_pool(streams, directory=None):
    global _POOL_STREAMS, _POOL_WEEKS, _POOL_DIRECTORY
    _POOL_DIRECTORY = Path(directory) if directory else None
    _POOL_STREAMS = streams
    _POOL_WEEKS = calendar_weeks(streams[0])


def replicate_scores(task):
    length, starts, *options = task
    with_risk = bool(options and options[0])
    result = []
    risks = []
    last_update = 0
    last_reason = "NOT_STARTED"
    for pd, stream in enumerate(_POOL_STREAMS):
        replay = sampled_path(stream, _POOL_WEEKS, starts, length)
        for j, capital in enumerate(CANDIDATES):
            # A shard holds one full paired replicate. Abort it *before the next
            # candidate* on a resource pause; no partial 231-row shard is saved.
            # Previously the worker ignored control.json until all 231 paths
            # finished, which could prolong an unsafe resource condition.
            if _POOL_DIRECTORY is not None:
                control = read_json(_POOL_DIRECTORY / "control.json")
                if control.get("pause") or time.time() - control.get("time", 0) > 20:
                    raise ResourcePause("PAUSE_RESOURCE:WORKER_CONTROL")
            if _POOL_DIRECTORY is not None and time.monotonic() - last_update >= 3:
                atomic_json(
                    _POOL_DIRECTORY / "compute" / f"{os.getpid()}.json",
                    dict(
                        time=time.time(),
                        candidate=pd * 7 + j,
                        block_length=length,
                        pid=os.getpid(),
                        last_termination=last_reason,
                    ),
                )
                last_update = time.monotonic()
            path = run_integrated_path(
                replay,
                capital,
                150,
                risk_horizon_start=_POOL_WEEKS[0] if with_risk else None,
            )
            if with_risk:
                risk = path["risk_accumulators"]
                risks.append([float(risk[key]) for key in RISK_COLUMNS])
            last_reason = path["metrics"]["termination_reason"] or "COMPLETED_HORIZON"
            require(
                path["metrics"]["structurally_complete"], "BOOTSTRAP_PATH_INCOMPLETE"
            )
            result.append(float(path["metrics"]["total_return"]))
    return (result, risks) if with_risk else result


def shard_key(spec, execution_id, length, start, stop):
    return dict(
        execution_binding(spec),
        execution_id=execution_id,
        lag=150,
        block_length=length,
        replicate_start=start,
        replicate_stop=stop,
    )


def save_shard(directory, spec, length, start, stop, scores):
    scores = np.asarray(scores, dtype="<f8")
    require(
        scores.shape == (stop - start, 231) and np.isfinite(scores).all(), "SHARD_SHAPE"
    )
    name = f"shards/150-{length}-{start:05d}-{stop:05d}.npy"
    buffer = io.BytesIO()
    np.save(buffer, scores, allow_pickle=False)
    return store_artifact(
        directory,
        name,
        buffer.getvalue(),
        shard_key(spec, Path(directory).name, length, start, stop),
    )


def save_risk_shard(directory, spec, length, start, stop, risks):
    values = np.asarray(risks, dtype="<f8")
    require(
        values.shape == (stop - start, 231, len(RISK_COLUMNS))
        and np.isfinite(values).all(),
        "RISK_SHARD_SHAPE",
    )
    name = f"risk-shards/150-{length}-{start:05d}-{stop:05d}.npy"
    buffer = io.BytesIO()
    np.save(buffer, values, allow_pickle=False)
    return store_artifact(
        directory,
        name,
        buffer.getvalue(),
        dict(
            shard_key(spec, Path(directory).name, length, start, stop),
            risk_schema="FS021_BOOTSTRAP_RISK_V1",
            columns=list(RISK_COLUMNS),
        ),
    )


def existing_risks(directory, spec, length):
    values = np.empty((5000, 231, len(RISK_COLUMNS)), dtype=np.float64)
    covered = set()
    for meta_path in sorted(
        (Path(directory) / "risk-shards").glob(f"150-{length}-*.npy.manifest.json")
    ):
        name = str(meta_path.relative_to(directory)).removesuffix(".manifest.json")
        key = read_json(meta_path)["binding"]
        start, stop = key["replicate_start"], key["replicate_stop"]
        require(
            0 <= start < stop <= 5000 and not covered.intersection(range(start, stop)),
            "RISK_SHARD_OVERLAP",
        )
        data = read_artifact(
            directory,
            name,
            dict(
                shard_key(spec, Path(directory).name, length, start, stop),
                risk_schema="FS021_BOOTSTRAP_RISK_V1",
                columns=list(RISK_COLUMNS),
            ),
        )
        matrix = np.load(io.BytesIO(data), allow_pickle=False)
        require(
            matrix.shape == (stop - start, 231, len(RISK_COLUMNS))
            and np.isfinite(matrix).all(),
            "RISK_SHARD_CONTENT",
        )
        values[start:stop] = matrix
        covered.update(range(start, stop))
    for path in (Path(directory) / "risk-shards").glob(f"150-{length}-*.npy"):
        require(
            path.with_name(path.name + ".manifest.json").exists(), "ORPHAN_RISK_SHARD"
        )
    return values, covered


def existing_scores(directory, spec, length):
    scores = np.empty((5000, 231), dtype=np.float64)
    covered = set()
    for meta_path in sorted(
        (Path(directory) / "shards").glob(f"150-{length}-*.npy.manifest.json")
    ):
        name = str(meta_path.relative_to(directory)).removesuffix(".manifest.json")
        meta = read_json(meta_path)
        key = meta["binding"]
        start, stop = key["replicate_start"], key["replicate_stop"]
        require(
            0 <= start < stop <= 5000 and not covered.intersection(range(start, stop)),
            "SHARD_OVERLAP_OR_RANGE",
        )
        matrix = np.load(
            io.BytesIO(
                read_artifact(
                    directory,
                    name,
                    shard_key(spec, Path(directory).name, length, start, stop),
                )
            ),
            allow_pickle=False,
        )
        require(
            matrix.shape == (stop - start, 231)
            and matrix.dtype == np.dtype("float64")
            and np.isfinite(matrix).all(),
            "SHARD_SCORES",
        )
        scores[start:stop] = matrix
        covered.update(range(start, stop))
    # Orphans are never silently replaced.
    for path in (Path(directory) / "shards").glob(f"150-{length}-*.npy"):
        require(
            path.with_name(path.name + ".manifest.json").exists(),
            "ORPHAN_SHARD_RESTORE_REQUIRED",
        )
    return scores, covered


def bootstrap(directory, streams, spec, progress, workers=4):
    require(1 <= workers <= 24, "WORKER_LIMIT")
    binding = execution_binding(spec)
    budget = json.loads(read_artifact(directory, "budget.json", binding))
    budget["max_workers"] = min(24, len(os.sched_getaffinity(0)))
    require(workers <= budget["max_workers"], "BUDGET_WORKERS")
    families = {}
    with ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("fork"),
        initializer=init_pool,
        initargs=(streams, str(directory)),
    ) as pool:
        for length in (1, 2, 4):
            scores, covered = existing_scores(directory, spec, length)
            with_risk = (
                spec["bootstrap"].get("risk_schema") == "FS021_BOOTSTRAP_RISK_V1"
            )
            if with_risk:
                risks, risk_covered = existing_risks(directory, spec, length)
                require(covered <= risk_covered, "SCORE_WITHOUT_RISK_SHARD")
            draws = block_draws(36, length)
            store_artifact(
                directory, f"rng/{length}.i64", draws.astype("<i8").tobytes(), binding
            )
            missing = iter(i for i in range(5000) if i not in covered)
            active = {}
            exhausted = False
            paused = False
            while active or not exhausted:
                try:
                    progress.check()
                except ResourcePause:
                    paused = True
                    exhausted = True
                while not exhausted and len(active) < workers:
                    index = next(missing, None)
                    if index is None:
                        exhausted = True
                        break
                    active[
                        pool.submit(replicate_scores, (length, draws[index], with_risk))
                    ] = index
                if not active:
                    break
                progress.update(
                    stage="BOOTSTRAP",
                    block_length=length,
                    completed=len(covered),
                    total=5000,
                    workers=len(active),
                )
                done, _ = wait(active, timeout=3, return_when=FIRST_COMPLETED)
                for future in done:
                    index = active.pop(future)
                    try:
                        output = future.result()
                    except ResourcePause:
                        # The paired replicate is incomplete: its index stays
                        # absent from covered and must be rebuilt after resume.
                        paused = True
                        exhausted = True
                        continue
                    if with_risk:
                        row, risk_row = output
                        save_risk_shard(
                            directory, spec, length, index, index + 1, [risk_row]
                        )
                        risks[index] = risk_row
                        risk_covered.add(index)
                    else:
                        row = output
                    save_shard(directory, spec, length, index, index + 1, [row])
                    scores[index] = row
                    covered.add(index)
                    progress.update(
                        stage="BOOTSTRAP",
                        block_length=length,
                        completed=len(covered),
                        total=5000,
                        candidate=230,
                        workers=len(active),
                        last_checkpoint=f"{length}:{index}",
                    )
            if paused:
                raise ResourcePause("PAUSE_RESOURCE:CHECKPOINTS_CONFIRMED")
            require(len(covered) == 5000, "BOOTSTRAP_INCOMPLETE")
            buffer = io.BytesIO()
            np.save(buffer, scores.astype("<f8"), allow_pickle=False)
            store_artifact(
                directory, f"scores-150-{length}.npy", buffer.getvalue(), binding
            )
            if with_risk:
                require(len(risk_covered) == 5000, "RISK_BOOTSTRAP_INCOMPLETE")
                risk_buffer = io.BytesIO()
                np.save(risk_buffer, risks.astype("<f8"), allow_pickle=False)
                store_artifact(
                    directory,
                    f"risk-150-{length}.npy",
                    risk_buffer.getvalue(),
                    dict(
                        binding,
                        risk_schema="FS021_BOOTSTRAP_RISK_V1",
                        columns=list(RISK_COLUMNS),
                    ),
                )
            families[str(length)] = scores
    return families


def stability(directory, streams, spec, progress):
    weeks = calendar_weeks(streams[0])
    competitions = sorted({o.competition_id for o in streams[0]})
    definitions = [("H1", set(weeks[:18]), None), ("H2", set(weeks[18:]), None)]
    definitions += [(f"WITHOUT:{c}", None, c) for c in competitions]
    result = []
    for name, allowed, excluded in definitions:
        key = dict(execution_binding(spec), slice=name)
        path = f"stability/{name}.json"
        if (Path(directory) / path).exists():
            result.append(json.loads(read_artifact(directory, path, key)))
            continue
        scores = []
        for pd, stream in enumerate(streams):
            subset = tuple(
                o
                for o in stream
                if (allowed is None or week_start(o.execution_at) in allowed)
                and o.competition_id != excluded
            )
            require(bool(subset), "STABILITY_EMPTY")
            for j, capital in enumerate(CANDIDATES):
                progress.check()
                scores.append(
                    run_integrated_path(subset, capital, 150)["metrics"]["total_return"]
                )
                progress.update(
                    stage="STABILITY",
                    candidate=pd * 7 + j,
                    completed=len(result) * 231 + len(scores),
                    total=2772,
                    slice=name,
                    workers=1,
                )
        entry = dict(slice=name, scores=scores)
        json_artifact(directory, path, entry, key)
        result.append(entry)
    return result


def finish(directory, spec, scores, slices):
    binding = execution_binding(spec)
    observed = json.loads(read_artifact(directory, "observed.json", binding))
    run = dict(
        schema="FS021_RUN_V1",
        execution_id=Path(directory).name,
        binding=binding,
        practical_selection=practical_selection(observed, spec["input"]["candidates"]),
        scientific_evidence=scientific_evidence(observed["150"], scores, slices),
        activation=spec["activation"],
        status="COMPLETE",
    )
    json_artifact(directory, "run.json", run, binding)
    return run
