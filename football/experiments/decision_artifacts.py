"""Deterministic local views, durable handoff, and FS-019 promotion authority."""

import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from django.conf import settings

from .decision import CANDIDATES
from .decision_runner import (
    UPSTREAM,
    decision_common_cohort_hash,
    read_decision_rows,
    snapshot_hash,
    verify_decision_run,
)
from .storage import (
    atomic_json,
    canonical,
    decision_root,
    identity,
    immutable_bytes,
    lock,
    read_json,
)
from .views import deterministic_gzip

REPORT_REF = "docs/research/FS-019_global_decision_baseline_report.md"
EVIDENCE_REF = "docs/research/FS-019_decision_baseline_evidence"
PROMOTION_REF = "docs/research/FS-019_global_decision_v1.json"
RESEARCH_REF = "docs/research/FS-019_global_decision_methodology_research.md"
AUTHORITY_SCHEMA = "FS019_GLOBAL_DECISION_AUTHORITY_V1"
STREAM_SCHEMA = "FS019_SELECTED_DECISION_STREAM_V1"


def _policy_config(candidate):
    return {} if candidate.threshold is None else {"threshold": candidate.threshold}


def _candidate(candidate_id):
    candidate = next(
        (item for item in CANDIDATES if item.candidate_id == candidate_id), None
    )
    if candidate is None:
        raise ValueError("SELECTED_DECISION_CANDIDATE_UNKNOWN")
    return candidate


def _compact_selection(run, stream=None):
    summary = run["summary"]
    bootstrap = summary["bootstrap"]
    result = {
        "run_id": run["run_id"],
        "execution_id": run["execution_id"],
        "execution_runtime_id": run["execution_runtime_id"],
        "spec_id": run["spec_id"],
        "input_snapshot_hash": run["input_snapshot_hash"],
        "decision_common_cohort_hash": run["decision_common_cohort_hash"],
        "decision_rows_hash": run["decision_rows_hash"],
        "decision_row_count": run["decision_row_count"],
        "natural_count": summary["natural_count"],
        "decision_common_count": summary["decision_common_count"],
        "price_coverage": summary["price_coverage"],
        "observed_global_ppo": summary["observed_global_ppo"],
        "observed_order": summary["observed_order"],
        "observed_top": summary["observed_top"],
        "observed_strongest_alternative": summary["observed_strongest_alternative"],
        "bootstrap": {
            key: bootstrap[key]
            for key in (
                "method",
                "quantile_method",
                "replicates",
                "seed",
                "block_count",
                "draws_hash",
                "replicate_scores_hash",
                "observed_deltas",
                "simultaneous_q95",
                "simultaneous_lower_bounds",
            )
        },
        "stability": summary["stability"],
        "disposition": summary["disposition"],
        "survivors": summary["survivors"],
        "selected": summary["selected"],
        "promotion_permitted": summary["promotion_permitted"],
        "resources": run["resources"],
        "warnings": run["warnings"],
    }
    if stream is not None:
        result["selected_decision_stream"] = stream
    return result


def _diagnostic_detail(metrics):
    return (
        f"Natural/common N={metrics['common_opportunities']}/"
        f"{metrics['common_opportunities']}; BET={metrics['bet_count']} "
        f"({metrics['bet_rate']}); NO_BET={metrics['no_bet_count']} "
        f"({metrics['no_bet_rate']}); "
        f"NO_BET reasons={canonical(metrics['no_bet_reasons'])}; "
        f"H/D/A={canonical(metrics['action_outcomes'])}; "
        f"P&L={metrics['fixed_unit_profit']}; PPO={metrics['ppo']}; "
        f"yield={metrics['yield']}; hit={metrics['hit_rate']}; "
        f"odds={canonical(metrics['selected_raw_odds'])}; "
        f"books={canonical(metrics['representative_bookmakers'])}; "
        f"co-best={canonical(metrics['co_best_bookmakers'])}; "
        f"quote-age={canonical(metrics['selected_quote_age_seconds'])}; "
        f"monthly={canonical(metrics['monthly_profit'])}; "
        f"longest losing bet streak={metrics['longest_losing_bet_streak']}"
    )


def human_report(run, *, local=False):
    summary = run["summary"]
    title = "FS-019 Local Decision Run" if local else "FS-019 Global Decision Baseline"
    lines = [
        f"# {title}",
        "",
        f"Run: `{run['run_id']}`",
        f"Spec: `{run['spec_id']}`",
        f"Input snapshot: `{run['input_snapshot_hash']}`",
        f"Decision-common cohort: `{run['decision_common_cohort_hash']}`",
        f"Natural/common N: {summary['natural_count']}/{summary['decision_common_count']}",
        f"Disposition: **{summary['disposition']}**",
        f"Selected: `{summary['selected'] or 'NO_PROMOTION'}`",
        "",
        "## Global diagnostics",
        "",
        "| Candidate | BET | NO_BET | Fixed-unit P&L | Equal-league PPO | Pooled PPO |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for candidate in run["spec"]["candidate_matrix"]:
        candidate_id = candidate["candidate_id"]
        metrics = summary["candidate_metrics"][candidate_id]
        lines.append(
            f"| {candidate_id} | {metrics['bet_count']} | "
            f"{metrics['no_bet_count']} | {metrics['fixed_unit_profit']} | "
            f"{metrics['global_ppo']} | {metrics['pooled_ppo_diagnostic']} |"
        )
    for candidate in run["spec"]["candidate_matrix"]:
        candidate_id = candidate["candidate_id"]
        metrics = summary["candidate_metrics"][candidate_id]
        lines += ["", f"### {candidate_id}", "", _diagnostic_detail(metrics), ""]
        lines += [
            "| League | Natural/common N | BET/rate | NO_BET/rate | P&L | PPO | yield | hit rate |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for league, league_metrics in metrics["per_league"].items():
            lines.append(
                f"| {league} | {league_metrics['common_opportunities']} | "
                f"{league_metrics['bet_count']} / {league_metrics['bet_rate']} | "
                f"{league_metrics['no_bet_count']} / "
                f"{league_metrics['no_bet_rate']} | "
                f"{league_metrics['fixed_unit_profit']} | {league_metrics['ppo']} | "
                f"{league_metrics['yield']} | {league_metrics['hit_rate']} |"
            )
            lines += ["", f"League {league}: {_diagnostic_detail(league_metrics)}", ""]
        league_ppos = {
            league: value["ppo"] for league, value in metrics["per_league"].items()
        }
        lines += [
            f"Required-league PPO: {canonical(league_ppos)}",
            f"Pooled PPO diagnostic: {metrics['pooled_ppo_diagnostic']}",
            "",
        ]
    lines += [
        "Diagnostics do not select the winner; election uses only frozen equal-league PPO and the frozen selection contract.",
        "",
        "## Selection evidence",
        "",
        "```json",
        canonical(_compact_selection(run)),
        "```",
        "",
        "Read-only historical research; no provider call, bankroll mutation, real bet, or operational routing change is part of this run.",
        "",
    ]
    return "\n".join(lines)


def materialize_decision_artifacts(directory, run, *, base=None):
    """Materialize disposable local views; durable files belong to promotion."""
    directory = Path(directory)
    views = {
        "spec.json": (canonical(run["spec"]) + "\n").encode(),
        "summary.json": (canonical(run["summary"]) + "\n").encode(),
        "report.md": human_report(run, local=True).encode(),
    }
    for name, content in views.items():
        immutable_bytes(
            directory / name, content, conflict=f"DECISION_RUN_VIEW_CONFLICT:{name}"
        )
    return directory


def selected_stream_rows(run, decision_rows):
    selected = run["summary"]["selected"]
    candidate = _candidate(selected)
    rows = [row for row in decision_rows if row["candidate_id"] == selected]
    rows.sort(key=lambda row: (row["competition_id"], row["kickoff"], row["match_id"]))
    if (
        len(rows) != run["summary"]["decision_common_count"]
        or len({row["match_id"] for row in rows}) != len(rows)
        or decision_common_cohort_hash(rows) != run["decision_common_cohort_hash"]
    ):
        raise ValueError("SELECTED_DECISION_STREAM_COHORT_MISMATCH")
    result = []
    for row in rows:
        is_bet = row["action"] == "BET"
        result.append(
            {
                "match_id": row["match_id"],
                "competition_id": row["competition_id"],
                "kickoff": row["kickoff"],
                "upstream_prediction": {
                    "baseline": run["spec"]["upstream"]["baseline"],
                    "model_code": run["spec"]["upstream"]["model_code"],
                    "model_version": run["spec"]["upstream"]["model_version"],
                    "config_identity": run["spec"]["upstream"]["config_identity"],
                    "probabilities": row["upstream_probabilities"],
                    "selected_model_probability": row["model_probability"],
                    "evidence_id": row["fs018_evidence_id"],
                },
                "decision": {
                    "policy_code": candidate.policy,
                    "policy_version": candidate.version,
                    "policy_variant": candidate.variant,
                    "policy_config": _policy_config(candidate),
                    "action": row["action"],
                    "reason": row["reason"],
                    "selected_outcome": row["selected_outcome"],
                },
                "price": {
                    "selected_raw_decimal": (
                        row.get("selected_price") if is_bet else None
                    ),
                    "representative_bookmaker": (
                        row.get("representative_bookmaker") if is_bet else None
                    ),
                    "co_best_bookmakers": (
                        row.get("co_best_bookmakers") if is_bet else None
                    ),
                    "selected_quote_timestamp": (
                        row.get("selected_quote_timestamp") if is_bet else None
                    ),
                    "selected_quote_age_seconds": (
                        row.get("selected_quote_age_seconds") if is_bet else None
                    ),
                    "provider_fixture_id": row["provider_fixture_id"],
                    "fs018_evidence_id": row["fs018_evidence_id"],
                    "raw_cache_hash": row["raw_cache_hash"],
                },
                "historical_outcome": row["actual_regulation_outcome"],
                "research": {"fixed_unit_reward": row["reward"]},
            }
        )
    return result


def _stream_descriptor(run, content, rows):
    relative = f"{EVIDENCE_REF}/{run['run_id'][:16]}/selected-decision-stream.jsonl.gz"
    return {
        "schema": STREAM_SCHEMA,
        "path": relative,
        "row_count": len(rows),
        "semantic_sha256": snapshot_hash(rows),
        "gzip_sha256": hashlib.sha256(content).hexdigest(),
    }


def promotion_record(run, selected_stream):
    summary = run["summary"]
    if summary["disposition"] == "INSUFFICIENT_EVIDENCE":
        return None
    if (
        summary["disposition"]
        not in {"CLEAR_SUPERIORITY", "NO_CLEAR_SUPERIORITY", "UNSTABLE"}
        or not summary["promotion_permitted"]
    ):
        raise ValueError("DECISION_DISPOSITION_NOT_PROMOTABLE")
    candidate = _candidate(summary["selected"])
    bootstrap_identity = identity(run["spec"]["bootstrap"])
    selection_identity = identity(
        {
            "primary_metric": run["spec"]["primary_metric"],
            "bootstrap": run["spec"]["bootstrap"],
            "stability": run["spec"]["stability"],
            "selection_rule": run["spec"]["selection_rule"],
        }
    )
    return {
        "schema": AUTHORITY_SCHEMA,
        "baseline": "GLOBAL_DECISION_V1",
        "upstream_prediction": run["spec"]["upstream"],
        "decision": {
            "policy_code": candidate.policy,
            "policy_version": candidate.version,
            "policy_variant": candidate.variant,
            "policy_config": _policy_config(candidate),
            "selected_candidate_id": candidate.candidate_id,
        },
        "experiment": {
            "decision_spec_id": run["spec_id"],
            "input_snapshot_semantic_hash": run["input_snapshot_hash"],
            "decision_common_cohort_hash": run["decision_common_cohort_hash"],
            "decision_run_id": run["run_id"],
            "execution_runtime_identity": run["execution_runtime_id"],
            "price_evidence_profile": run["spec"]["price_contract"]["profile"],
            "price_contract_identity": identity(run["spec"]["price_contract"]),
            "bootstrap_policy_identity": bootstrap_identity,
            "selection_policy_identity": selection_identity,
            "scientific_disposition": summary["disposition"],
            "fallback_rule_identity": identity(
                {"selection_rule": run["spec"]["selection_rule"]}
            ),
        },
        "selected_decision_stream": selected_stream,
        "research_ref": RESEARCH_REF,
        "report_ref": REPORT_REF,
        "evidence_ref": f"{EVIDENCE_REF}/{run['run_id'][:16]}",
    }


def _write_immutable_json(path, value, conflict):
    immutable_bytes(path, (canonical(value) + "\n").encode(), conflict=conflict)


def promote_decision(run, spec, *, base=None, workspace_root=None):
    verify_decision_run(run, spec)
    if run["summary"]["disposition"] == "INSUFFICIENT_EVIDENCE":
        return None
    base = Path(base or settings.BASE_DIR)
    directory = decision_root(workspace_root) / run["execution_id"]
    decision_rows = read_decision_rows(directory, run)
    stream_rows = selected_stream_rows(run, decision_rows)
    stream_content = deterministic_gzip(stream_rows)
    stream = _stream_descriptor(run, stream_content, stream_rows)
    record = promotion_record(run, stream)
    path = base / PROMOTION_REF
    with lock(decision_root(workspace_root) / "promotion.lock"):
        if path.exists():
            if read_json(path) == record:
                resolve_global_decision(base=base)
                return record
            raise ValueError("GLOBAL_DECISION_V1_ALREADY_FROZEN")
        evidence = base / EVIDENCE_REF / run["run_id"][:16]
        immutable_bytes(
            evidence / "selected-decision-stream.jsonl.gz",
            stream_content,
            conflict="SELECTED_DECISION_STREAM_CONFLICT",
        )
        selection = _compact_selection(run, stream)
        _write_immutable_json(
            evidence / "selection-summary.json",
            selection,
            "DURABLE_DECISION_SELECTION_CONFLICT",
        )
        selection_content = (canonical(selection) + "\n").encode()
        checksums = (
            f"{hashlib.sha256(selection_content).hexdigest()}  selection-summary.json\n"
            f"{stream['gzip_sha256']}  selected-decision-stream.jsonl.gz\n"
        )
        immutable_bytes(
            evidence / "SHA256SUMS",
            checksums.encode(),
            conflict="DURABLE_DECISION_CHECKSUMS_CONFLICT",
        )
        immutable_bytes(
            base / REPORT_REF,
            human_report(run).encode(),
            conflict="GLOBAL_DECISION_REPORT_ALREADY_FROZEN",
        )
        atomic_json(path, record)
    return record


@dataclass(frozen=True)
class DecisionSourceDescriptor:
    model_code: str
    model_version: str
    prediction_config_identity: str
    decision_policy_code: str
    decision_policy_version: str
    decision_policy_variant: str
    decision_policy_config: MappingProxyType
    decision_common_cohort_hash: str
    selected_decision_stream_path: str
    selected_decision_stream_semantic_hash: str


def resolve_global_decision(*, base=None):
    base = Path(base or settings.BASE_DIR).resolve()
    path = base / PROMOTION_REF
    try:
        authority = read_json(path)
        if (
            authority["schema"] != AUTHORITY_SCHEMA
            or authority["baseline"] != "GLOBAL_DECISION_V1"
            or authority["upstream_prediction"] != UPSTREAM
        ):
            raise ValueError("UNSUPPORTED_GLOBAL_DECISION_AUTHORITY")
        decision = authority["decision"]
        candidate = _candidate(decision["selected_candidate_id"])
        expected_decision = {
            "policy_code": candidate.policy,
            "policy_version": candidate.version,
            "policy_variant": candidate.variant,
            "policy_config": _policy_config(candidate),
            "selected_candidate_id": candidate.candidate_id,
        }
        if decision != expected_decision:
            raise ValueError("GLOBAL_DECISION_POLICY_MISMATCH")
        stream = authority["selected_decision_stream"]
        if stream["schema"] != STREAM_SCHEMA:
            raise ValueError("UNSUPPORTED_SELECTED_DECISION_STREAM")
        stream_path = (base / stream["path"]).resolve()
        evidence_root = (base / EVIDENCE_REF).resolve()
        if not stream_path.is_relative_to(evidence_root):
            raise ValueError("SELECTED_DECISION_STREAM_PATH_ESCAPE")
        content = stream_path.read_bytes()
        if hashlib.sha256(content).hexdigest() != stream["gzip_sha256"]:
            raise ValueError("SELECTED_DECISION_STREAM_GZIP_HASH_MISMATCH")
        with gzip.open(stream_path, "rt") as source:
            rows = [json.loads(line) for line in source]
        if (
            len(rows) != stream["row_count"]
            or snapshot_hash(rows) != stream["semantic_sha256"]
        ):
            raise ValueError("SELECTED_DECISION_STREAM_SEMANTIC_HASH_MISMATCH")
        upstream = authority["upstream_prediction"]
        cohort_hash = authority["experiment"]["decision_common_cohort_hash"]
        if decision_common_cohort_hash(rows) != cohort_hash:
            raise ValueError("SELECTED_DECISION_STREAM_COHORT_HASH_MISMATCH")
        for row in rows:
            prediction = row["upstream_prediction"]
            row_decision = row["decision"]
            price = row["price"]
            prediction_lineage = {
                key: prediction[key]
                for key in (
                    "baseline",
                    "model_code",
                    "model_version",
                    "config_identity",
                )
            }
            expected_prediction = {
                key: upstream[key]
                for key in (
                    "baseline",
                    "model_code",
                    "model_version",
                    "config_identity",
                )
            }
            decision_lineage = {
                key: row_decision[key]
                for key in (
                    "policy_code",
                    "policy_version",
                    "policy_variant",
                    "policy_config",
                )
            }
            expected_policy = {
                key: decision[key]
                for key in (
                    "policy_code",
                    "policy_version",
                    "policy_variant",
                    "policy_config",
                )
            }
            if (
                prediction_lineage != expected_prediction
                or decision_lineage != expected_policy
                or row_decision["action"] not in {"BET", "NO_BET"}
                or row["historical_outcome"] not in {"HOME", "DRAW", "AWAY"}
                or not isinstance(row["research"]["fixed_unit_reward"], (int, float))
            ):
                raise ValueError("SELECTED_DECISION_STREAM_LINEAGE_MISMATCH")
            if row_decision["action"] == "NO_BET" and (
                row_decision["selected_outcome"] is not None
                or any(
                    price[key] is not None
                    for key in (
                        "selected_raw_decimal",
                        "representative_bookmaker",
                        "co_best_bookmakers",
                        "selected_quote_timestamp",
                        "selected_quote_age_seconds",
                    )
                )
            ):
                raise ValueError("SELECTED_DECISION_STREAM_NO_BET_MISMATCH")
            if row_decision["action"] == "BET" and (
                row_decision["selected_outcome"] not in {"HOME", "DRAW", "AWAY"}
                or not isinstance(price["selected_raw_decimal"], (int, float))
                or price["selected_raw_decimal"] <= 1
                or not price["representative_bookmaker"]
                or not price["co_best_bookmakers"]
            ):
                raise ValueError("SELECTED_DECISION_STREAM_BET_MISMATCH")
        return DecisionSourceDescriptor(
            model_code=upstream["model_code"],
            model_version=upstream["model_version"],
            prediction_config_identity=upstream["config_identity"],
            decision_policy_code=decision["policy_code"],
            decision_policy_version=decision["policy_version"],
            decision_policy_variant=decision["policy_variant"],
            decision_policy_config=MappingProxyType(dict(decision["policy_config"])),
            decision_common_cohort_hash=cohort_hash,
            selected_decision_stream_path=stream["path"],
            selected_decision_stream_semantic_hash=stream["semantic_sha256"],
        )
    except FileNotFoundError:
        raise ValueError("GLOBAL_DECISION_AUTHORITY_OR_STREAM_MISSING") from None
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        raise ValueError("MALFORMED_GLOBAL_DECISION_AUTHORITY_OR_STREAM") from None
