"""Offline FS-023 candidate subset execution on the authenticated 2,605 corpus."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import numpy as np

from football.prediction.contracts import ProbabilityResult
from football.prediction.policies import selective_confidence

from .capital_analysis import block_draws, calendar_weeks, sampled_path, week_start
from .capital_events import Opportunity
from .capital_runner import CANDIDATES
from .economic_selector import INPUT_VERSION, select_economic_baseline
from .fs023_benchmark import validate_benchmark
from .fs023_corpus import authenticated_rows, corpus_identity
from .integrated_events import RULE, run_integrated_path
from .storage import canonical, identity, immutable_bytes

FROZEN = {209: Decimal("0.45"), 216: Decimal("0.50"), 223: Decimal("0.55")}
ACTIVITY = {"placements": 53, "competitions": 5, "weeks": 5}


def candidate_ids(value):
    if isinstance(value, str):
        try:
            ids = tuple(int(part.strip()) for part in value.split(","))
        except ValueError as error:
            raise ValueError("FS023_CANDIDATE_IDS_INVALID") from error
    else:
        ids = tuple(value)
    if not ids or len(ids) != len(set(ids)) or any(i not in FROZEN for i in ids):
        raise ValueError("FS023_CANDIDATE_SUBSET_UNKNOWN_DUPLICATE_OR_INELIGIBLE")
    if ids not in {(209,), (209, 216, 223)}:
        raise ValueError("FS023_CANDIDATE_SUBSET_NOT_PREREGISTERED")
    return ids


def _instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _stream(rows, integrated_index):
    threshold = float(FROZEN[integrated_index])
    result = []
    for row in rows:
        window = row["windows"]["T10"]
        if window["status"] != "PRODUCED" or window["book_count"] < 2:
            raise ValueError("FS023_FROZEN_T10_INPUT_INCOMPLETE")
        kickoff = _instant(row["kickoff_utc"])
        cutoff = _instant(window["cutoff"])
        if cutoff != kickoff - __import__("datetime").timedelta(minutes=10):
            raise ValueError("FS023_FROZEN_T10_CUTOFF_MISMATCH")
        probabilities = ProbabilityResult(*window["probabilities"])
        prices = {
            name: (None, Decimal(str(price)))
            for name, price in zip(
                ("HOME", "DRAW", "AWAY"), window["best_prices"], strict=True
            )
        }
        decision = selective_confidence(probabilities, threshold, prices)
        home, away = row["result"]["home_score"], row["result"]["away_score"]
        actual = "HOME" if home > away else "AWAY" if away > home else "DRAW"
        result.append(
            Opportunity(
                identity=row["fixture_id"],
                source_id=0,
                competition_id=row["country"],
                kickoff=kickoff,
                execution_at=cutoff,
                action="NO_BET" if decision.action == "NO_BET" else "BET",
                selected_outcome=(
                    None if decision.action == "NO_BET" else decision.action
                ),
                actual_outcome=actual,
                price=(
                    Decimal(str(decision.selected_price))
                    if decision.selected_price is not None
                    else None
                ),
                probability=(
                    Decimal(str(decision.model_probability))
                    if decision.action != "NO_BET"
                    else None
                ),
            )
        )
    return tuple(result)


def _write_once(path, value):
    content = (canonical(value) + "\n").encode()
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("FS023_IMMUTABLE_ARTIFACT_CONFLICT")
    else:
        immutable_bytes(path, content, conflict="FS023_IMMUTABLE_ARTIFACT_CONFLICT")


def run_subset(
    *,
    ids,
    benchmark,
    output_root,
    durable,
    mode="evaluation-only",
    replicates=5000,
):
    ids = candidate_ids(ids)
    expected_mode = "evaluation-only" if ids == (209,) else "selection"
    if mode != expected_mode:
        raise ValueError("FS023_RESULT_MODE_MISMATCH")
    if replicates != 5000:
        raise ValueError("FS023_FROZEN_BOOTSTRAP_REPLICATES_REQUIRED")
    benchmark = validate_benchmark(benchmark)
    rows = authenticated_rows(durable)
    spec = {
        "schema": "FS023_EXPERIMENT_SPEC_V1",
        "candidate_ids": list(ids),
        "candidate_composition": {
            str(i): {
                "prediction": "MARKET_CONSENSUS/fs013-market-consensus-v2",
                "decision": f"SELECTIVE_CONFIDENCE/{FROZEN[i]}",
                "capital": CANDIDATES[6].data(),
            }
            for i in ids
        },
        "corpus": corpus_identity(),
        "capture_window": "T10",
        "method": "FS021_SINGLE_ECONOMIC_SELECTOR_V1",
        "depletion_rule": RULE,
        "settlement_lags": [120, 130, 150],
        "bootstrap": {
            "lengths": [1, 2, 4],
            "replicates": replicates,
            "draws": "FS021_PCG64_FROZEN_SEED",
        },
        "activity": ACTIVITY,
        "benchmark": benchmark,
        "result_mode": mode,
        "selection_authority": mode == "selection",
        "promotion_eligible": mode == "selection",
        "activation": False,
    }
    execution_id = identity(spec)
    output = Path(output_root) / execution_id
    output.mkdir(parents=True, exist_ok=True)
    _write_once(output / "spec.json", spec)
    streams = {i: _stream(rows, i) for i in ids}
    observed = {str(lag): [] for lag in (120, 130, 150)}
    for lag in (120, 130, 150):
        for i in ids:
            observed[str(lag)].append(
                run_integrated_path(
                    streams[i],
                    CANDIDATES[6],
                    lag,
                )["metrics"]
            )
    _write_once(output / "observed.json", observed)
    if mode == "evaluation-only":
        publication = {
            "schema": "FS023_PUBLICATION_V1",
            "execution_id": execution_id,
            "candidate_ids": list(ids),
            "evaluation_only": True,
            "selection_authority": False,
            "promotion_eligible": False,
            "activation": False,
            "observed": observed,
        }
    else:
        weeks = calendar_weeks(streams[ids[0]])
        matrices = {}
        for length in (1, 2, 4):
            matrix = np.empty((replicates, len(ids)), dtype=np.float64)
            draws = block_draws(len(weeks), length, replicates=replicates)
            for replicate in range(replicates):
                for local_index, i in enumerate(ids):
                    replay = sampled_path(streams[i], weeks, draws[replicate], length)
                    path = run_integrated_path(replay, CANDIDATES[6], 150)
                    if not path["metrics"]["structurally_complete"]:
                        raise ValueError("FS023_BOOTSTRAP_PATH_INCOMPLETE")
                    matrix[replicate, local_index] = float(
                        path["metrics"]["total_return"]
                    )
            matrices[str(length)] = matrix.tolist()
        benchmark_for_selector = (
            {"status": "UNAVAILABLE"}
            if benchmark["primary"]["status"] == "UNAVAILABLE"
            else {
                "status": "AVAILABLE",
                "horizon_return": benchmark["primary"]["horizon_return"],
            }
        )
        selected = select_economic_baseline(
            {
                "schema": INPUT_VERSION,
                "candidates": [
                    {
                        "integrated_index": i,
                        "capital_index": 6,
                        "decision_threshold": str(FROZEN[i]),
                    }
                    for i in ids
                ],
                "candidate_ids": list(ids),
                "activity": ACTIVITY,
                "benchmark": benchmark_for_selector,
                "observed": observed,
                "scores": matrices,
                "scientific_disposition": "RESTRICTED_PREREGISTERED_CHALLENGE",
            }
        )
        slices = {}
        half = len(weeks) // 2
        definitions = {"H1": (set(weeks[:half]), None), "H2": (set(weeks[half:]), None)}
        definitions.update(
            {
                f"WITHOUT:{country}": (None, country)
                for country in sorted({o.competition_id for o in streams[ids[0]]})
            }
        )
        for name, (allowed, excluded) in definitions.items():
            slices[name] = {
                str(i): run_integrated_path(
                    tuple(
                        o
                        for o in streams[i]
                        if (allowed is None or week_start(o.execution_at) in allowed)
                        and o.competition_id != excluded
                    ),
                    CANDIDATES[6],
                    150,
                )["metrics"]
                for i in ids
            }
        publication = {
            "schema": "FS023_PUBLICATION_V1",
            "execution_id": execution_id,
            "candidate_ids": list(ids),
            "evaluation_only": False,
            "selection_authority": True,
            "promotion_eligible": True,
            "activation": False,
            "selection": selected,
            "stability": slices,
        }
    _write_once(output / "publication.json", publication)
    return output, publication
