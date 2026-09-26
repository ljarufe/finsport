"""Offline, fail-closed FS-021 input resolver; no database or provider access."""

import gzip
import hashlib
import platform
from collections import Counter
from datetime import timedelta
from decimal import Decimal, getcontext
from pathlib import Path

import numpy as np

from football.prediction.contracts import ProbabilityResult
from football.prediction.policies import modal_all, selective_confidence, value_policy

from .capital_analysis import calendar_weeks, week_start
from .capital_events import RUNNER_VERSION, Opportunity
from .capital_runner import CANDIDATES, write_json_once
from .historical_prices import best_price
from .integrated_events import RULE, opportunity_hash
from .storage import canonical, identity, instant, read_json

PROFILE = "ODDSPAPI_RECONSTRUCTED_T30_V1"
RESEARCH = "docs/research/FS-021_integrated_strategy_methodology_research.md"
ADDENDUM = "docs/research/FS-021_approved_scope_addendum.md"
# Presence and structure, not fixed file digests. Editable source files are
# validated by cross-source semantics, not by historical byte fingerprints.
PACK_FILES = (
    "pd_candidate_matrix.json",
    "pd_stream_manifest.json",
    "common_cohort_manifest.json",
    "pd_capital_equivalence_manifest.json",
    "repo_binding.json",
    "pd_33_streams.jsonl.gz",
    "common_cohort.jsonl.gz",
    "fs018_retained_binding.json",
)


def sha_file(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def lines_hash(rows):
    digest = hashlib.sha256()
    for row in rows:
        digest.update((canonical(row) + "\n").encode())
    return digest.hexdigest()


def read_rows(path):
    import json

    with gzip.open(path, "rt") as stream:
        return [json.loads(line) for line in stream]


def require(condition, reason):
    if not condition:
        raise ValueError(f"STOP_TECHNICAL:{reason}")


def row_opportunity(row):
    bet = row["action"] == "BET"
    return Opportunity(
        str(row["match_id"]),
        row["match_id"],
        row["competition_id"],
        instant(row["kickoff"]),
        instant(row["synthetic_execution_at"]),
        row["action"],
        row["selected_outcome"],
        row["actual_regulation_outcome"],
        Decimal(str(row["selected_price"])) if bet else None,
        Decimal(str(row["model_probability"])) if bet else None,
    )


def resolve_inputs(base, pack, per_match):
    base, pack, per_match = Path(base), Path(pack), Path(per_match)
    files = {}
    for name in PACK_FILES:
        path = pack / name
        require(path.is_file(), f"PACK_MISSING:{name}")
        files[name] = dict(kind="producer_input")
    matrix = read_json(pack / "pd_candidate_matrix.json")
    manifest = read_json(pack / "pd_stream_manifest.json")
    # Manifest identities and upstream SHA declarations are historical metadata.
    # Scientific checks below reconstruct predictions, decisions, prices and
    # ordering from the actual records supplied to this run.
    prediction_rows = [r for r in read_rows(per_match) if r["COMMON"]]
    predictions = {(r["model_code"], r["match_id"]): r for r in prediction_rows}
    require(len(prediction_rows) == len(predictions), "DUPLICATE_COMMON_PREDICTION")
    cohort = read_rows(pack / "common_cohort.jsonl.gz")
    require(
        len(cohort) == 1877 and len({r["match_id"] for r in cohort}) == 1877,
        "COHORT_CARDINALITY",
    )
    require(
        cohort
        == sorted(
            cohort, key=lambda r: (r["competition_id"], r["kickoff"], r["match_id"])
        ),
        "COHORT_ORDER",
    )
    ids = [r["match_id"] for r in cohort]
    rows = read_rows(pack / "pd_33_streams.jsonl.gz")
    require(
        len(rows) == 61941,
        "COMBINED_STREAM",
    )
    order = matrix["candidate_order"]
    require(len(order) == len(set(order)) == 33, "PD_COUNT")
    prices = {
        r["match_id"]: {
            outcome: best_price(
                dict(
                    predictions[("MARKET_CONSENSUS", r["match_id"])],
                    fs018_evidence_id=r["fs018_evidence_id"],
                ),
                outcome,
            )
            for outcome in ("HOME", "DRAW", "AWAY")
        }
        for r in cohort
    }
    streams, stream_bindings = [], []
    for i, candidate in enumerate(matrix["candidates"]):
        subset = rows[i * 1877 : (i + 1) * 1877]
        expected = manifest["candidates"][i]
        require(
            candidate["candidate_id"] == order[i] == expected["candidate_id"],
            "PD_ORDER",
        )
        require(candidate["candidate_index"] == i, "PD_INDEX")
        require([r["match_id"] for r in subset] == ids, "MATCH_ORDER")
        for row, common in zip(subset, cohort, strict=True):
            require(all(row[k] == v for k, v in common.items()), "COMMON_FIELDS")
            require(
                row["candidate_id"] == order[i] and row["candidate_index"] == i,
                "ROW_CANDIDATE",
            )
            for key in (
                "prediction_code",
                "prediction_version",
                "prediction_config_identity",
                "decision_policy",
                "decision_policy_version",
                "decision_config",
                "decision_variant",
            ):
                require(row[key] == candidate[key], f"ROW_{key}")
            require(row["evidence_profile"] == PROFILE, "PROFILE")
            require(
                instant(row["synthetic_execution_at"])
                == instant(row["kickoff"]) - timedelta(minutes=30),
                "EXECUTION_TIME",
            )
            prediction = predictions[(row["prediction_code"], row["match_id"])]
            require(
                prediction["status"] == "PRODUCED" and prediction["eligible"],
                "PREDICTION_READY",
            )
            require(
                all(
                    prediction[k] == row[k]
                    for k in (
                        "p_home",
                        "p_draw",
                        "p_away",
                        "kickoff",
                        "competition_id",
                        "actual_regulation_outcome",
                    )
                ),
                "PREDICTION_FIELDS",
            )
            probability = ProbabilityResult(row["p_home"], row["p_draw"], row["p_away"])
            market = {
                o: (None, p["selected_price"])
                for o, p in prices[row["match_id"]].items()
            }
            code = candidate["decision_policy"]
            decision = (
                modal_all(probability, market)
                if code == "MODAL_ALL"
                else (
                    selective_confidence(
                        probability, candidate["decision_config"]["threshold"], market
                    )
                    if code == "SELECTIVE_CONFIDENCE"
                    else value_policy(
                        probability, market, candidate["decision_config"]["minimum_ev"]
                    )
                )
            )
            require(
                row["action"] == ("NO_BET" if decision.action == "NO_BET" else "BET"),
                "DECISION_ACTION",
            )
            require(row["reason"] == decision.reason, "DECISION_REASON")
            if row["action"] == "BET":
                require(row["selected_outcome"] == decision.action, "DECISION_OUTCOME")
                require(
                    all(
                        row[k] == v
                        for k, v in prices[row["match_id"]][decision.action].items()
                    ),
                    "PRICE_PROVENANCE",
                )
                require(
                    row["model_probability"]
                    == row[f'p_{row["selected_outcome"].lower()}'],
                    "SELECTED_PROBABILITY",
                )
                require(
                    instant(row["selected_quote_timestamp"])
                    <= instant(row["synthetic_execution_at"]),
                    "QUOTE_TIME",
                )
                age = (
                    instant(row["kickoff"]) - instant(row["selected_quote_timestamp"])
                ).total_seconds()
                require(age == row["selected_quote_age_seconds"], "QUOTE_AGE")
        opportunities = tuple(row_opportunity(row) for row in subset)
        streams.append(opportunities)
        stream_bindings.append(
            dict(
                candidate_id=order[i],
                original_stream_sha256=lines_hash(subset),
                opportunity_sha256=opportunity_hash(opportunities),
                actions=dict(Counter(r["action"] for r in subset)),
            )
        )
    weeks = calendar_weeks(streams[0])
    empty = [
        w.isoformat()
        for w in weeks
        if w not in {week_start(o.execution_at) for o in streams[0]}
    ]
    require(
        len(weeks) == 36
        and len(empty) == 6
        and len({o.competition_id for o in streams[0]}) == 10,
        "CALENDAR",
    )
    calendar = dict(weeks=[w.isoformat() for w in weeks], empty_weeks=empty)
    integrated = [
        dict(
            integrated_index=i * 7 + j,
            pd_index=i,
            capital_index=j,
            prediction_decision=pd,
            capital=c.data(),
        )
        for i, pd in enumerate(matrix["candidates"])
        for j, c in enumerate(CANDIDATES)
    ]
    binding = dict(
        schema="FS021_INPUT_MANIFEST_V1",
        files=files,
        cohort_sha=lines_hash(cohort),
        matrix_sha=identity(matrix["candidates"]),
        stream_sha=lines_hash(rows),
        streams=stream_bindings,
        calendar=calendar,
        calendar_sha=identity(calendar),
        candidates=integrated,
        profile=PROFILE,
        counts=dict(pd=33, integrated=231, matches=1877, rows=61941),
        status="INPUT_AND_ARTIFACT_INTEGRITY_PASS",
    )
    return tuple(streams), binding


def freeze_spec(base, binding, path):
    spec = dict(
        schema="FS021_SPEC_V1",
        input=binding,
        depletion_rule=RULE,
        initial_bankroll="100",
        observed_lags=[120, 130, 150],
        scientific_lag=150,
        bootstrap=dict(
            lengths=[1, 2, 4],
            replicates=5000,
            risk_schema="FS021_BOOTSTRAP_RISK_V1",
            seed=21092026,
            encoding="C_ORDER_LITTLE_ENDIAN_INT64_BLOCK_STARTS",
        ),
        scores_encoding="C_ORDER_LITTLE_ENDIAN_FLOAT64_REPLICATE_CANDIDATE",
        selection=dict(
            rule="FS021_INTEGRATED_MAXIMIN_LAG_5U_V1",
            placements=38,
            competitions=3,
            weeks=4,
            order=[
                "min_return_DESC",
                "return150_DESC",
                "worst_drawdown_ASC",
                "min_placed_DESC",
                "worst_exposure_ASC",
                "integrated_index_ASC",
            ],
        ),
        inference="ALL_26565_PAIRS_MAX_T_95_DDOF1_LINEAR_EXACT_ZERO_SE",
        stability="12_FRESH_SLICES_FIXED_T150_TOP_VS_ALL",
        CROSS_LAG_INFERENCE="NOT_EVALUATED_BY_FS021_V1",
        runner=integrated_runtime(),
        sources=[RESEARCH, ADDENDUM],
        activation=dict(automatic_operational_routing=False, real_betting=False),
    )
    write_json_once(path, spec)
    return spec


def integrated_runtime():
    # Environment/version metadata only; no source-file traversal or SHA sweep.
    context = getcontext()
    return dict(
        version=RULE,
        capital_version=RUNNER_VERSION,
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
    )
