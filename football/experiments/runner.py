"""Freeze canonical inputs once, replay offline, retain immutable run lineage."""

import resource
import time
from types import SimpleNamespace

from football.models import Competition, Match
from football.prediction.datasets import eligible_finished_matches, rows_from_matches

from .analysis import (
    PAIRED_COMMON_SELECTION_POLICY,
    STANDARD_SELECTION_POLICY,
    compare,
)
from .replay import sporting_replay
from .spec import MODELS, PROFILE
from .spec import _runtime_identity as execution_runtime
from .storage import atomic_json, identity, instant, lock, read_json, require_dev, roots

ANALYSIS_LINEAGE_VERSION = "FS018_EXECUTION_RUNTIME_V1"


def analysis_identity(spec_id, acquisition_id, *, mode, selection_policy, runtime_id):
    return identity(
        {
            "lineage_version": ANALYSIS_LINEAGE_VERSION,
            "spec_id": spec_id,
            "acquisition_id": acquisition_id,
            "analysis_mode": mode,
            "selection_policy": selection_policy,
            "execution_runtime_id": runtime_id,
        }
    )


def snapshot_matches(spec):
    data = spec.data
    snapshot = []
    for competition_id in data["competition_ids"]:
        competition = Competition.objects.get(pk=competition_id)
        matches = list(
            eligible_finished_matches(competition, before=instant(data["data_cutoff"]))
        )
        rows = rows_from_matches(matches)
        for row in rows:
            snapshot.append(
                {
                    "match_id": row.match_id,
                    "competition_id": competition_id,
                    "kickoff": row.kickoff.isoformat(),
                    "season_year": row.season_year,
                    "home_team_id": int(row.home_team),
                    "away_team_id": int(row.away_team),
                    "home_score": row.home_score,
                    "away_score": row.away_score,
                    "outcome": row.outcome,
                }
            )
    return snapshot


def thaw(row):
    return SimpleNamespace(
        id=row["match_id"],
        kickoff=instant(row["kickoff"]),
        season=SimpleNamespace(year=row["season_year"]),
        **{
            key: row[key]
            for key in (
                "home_team_id",
                "away_team_id",
                "home_score",
                "away_score",
                "outcome",
            )
        },
    )


def excluded_targets(spec, matches):
    ids = {r["match_id"] for r in matches}
    data = spec.data
    excluded = []
    for match in (
        Match.objects.filter(
            season__competition_id__in=data["competition_ids"],
            kickoff__gte=instant(data["window_start"]),
            kickoff__lt=instant(data["data_cutoff"]),
        )
        .select_related("season")
        .order_by("kickoff", "pk")
    ):
        if match.pk in ids:
            continue
        reason = "NOT_CANONICAL_FT_WITH_VALID_SCORE"
        excluded.append(
            {
                "match_id": match.pk,
                "competition_id": match.season.competition_id,
                "kickoff": match.kickoff.isoformat(),
                "outcome": match.outcome,
                "result": [match.home_score, match.away_score],
                "eligible": False,
                "eligibility_reason": reason,
                "candidates": {
                    code: {
                        "status": "UNAVAILABLE",
                        "reason": reason,
                        "model_version": version,
                    }
                    for code, version in MODELS.items()
                },
            }
        )
    return excluded


def market_evidence(backfill):
    by_match, reasons = {}, {}
    for league in backfill["leagues"].values():
        for item in league["fixtures"].values():
            mapping = item.get("mapping", {})
            match_id = mapping.get("match_id")
            if match_id is None:
                continue
            evidence = item.get("evidence")
            if evidence:
                content = {k: v for k, v in evidence.items() if k != "evidence_id"}
                if identity(content) != evidence["evidence_id"]:
                    raise ValueError("MARKET_EVIDENCE_HASH_MISMATCH")
                if (
                    evidence["evidence_profile"] != PROFILE
                    or evidence["evidence_class"] != "HISTORICAL_RESEARCH"
                    or evidence["model_version"] != MODELS["MARKET_CONSENSUS"]
                    or evidence["match_id"] != match_id
                    or (evidence["status"] == "PRODUCED" and evidence["book_count"] < 2)
                ):
                    raise ValueError("MARKET_EVIDENCE_CONTRACT_MISMATCH")
                if match_id in by_match:
                    raise ValueError("MULTIPLE_PROVIDER_FIXTURES_FOR_CANONICAL_MATCH")
                by_match[match_id] = evidence
            else:
                reasons[match_id] = item.get("reason") or item["status"]
    return by_match, reasons


def run_experiment(spec, *, pilot=False, confirm=False):
    require_dev()
    acquisition_id = identity({"spec_id": spec.id, "pilot": pilot})
    if spec.data.get("acquisition", {}).get("mode") == "RECOVERY_V1" and pilot:
        raise ValueError("Recovery requires full scope")
    if spec.data.get("acquisition", {}).get("mode") == "RECOVERY_V1" and not confirm:
        raise ValueError("RECOVERY_REQUIRES_FRESH_CONFIRMATION")
    mode = "FRESH_CONFIRMATION_V2" if confirm else "STANDARD"
    selection_policy = (
        PAIRED_COMMON_SELECTION_POLICY if confirm else STANDARD_SELECTION_POLICY
    )
    actual_runtime = execution_runtime()
    runtime_id = identity(actual_runtime)
    analysis_id = analysis_identity(
        spec.id,
        acquisition_id,
        mode=mode,
        selection_policy=selection_policy,
        runtime_id=runtime_id,
    )
    directory = roots()[1] / analysis_id
    with lock(directory / "analysis.lock"):
        complete = directory / "run.json"
        if complete.exists():
            result = read_json(complete)
            verify_run(result, spec)
            from .views import materialize_views

            materialize_views(directory, result)
            return result
        state = read_json(roots()[1] / acquisition_id / "backfill.json")
        if state["spec_id"] != spec.id or state["status"] not in {
            "COMPLETE",
            "PARTIAL",
            "FAILED",
        }:
            raise ValueError("BACKFILL_NOT_TERMINAL_FOR_SPEC")
        if set(state["leagues"]) != {str(i) for i in spec.data["competition_ids"]}:
            raise ValueError("ALL_LEAGUES_MUST_BE_ATTEMPTED")
        snapshot_path = directory / "inputs.json"
        if not snapshot_path.exists():
            matches = snapshot_matches(spec)
            inputs = {
                "spec_id": spec.id,
                "matches": matches,
                "excluded_targets": excluded_targets(spec, matches),
                "acquisition": state,
            }
            atomic_json(snapshot_path, {"hash": identity(inputs), "inputs": inputs})
        saved = read_json(snapshot_path)
        inputs = saved["inputs"]
        if identity(inputs) != saved["hash"] or inputs["spec_id"] != spec.id:
            raise ValueError("INPUT_SNAPSHOT_HASH_MISMATCH")
        state = inputs["acquisition"]
        market, missing = market_evidence(state)
        data, manifest, resources = spec.data, inputs["excluded_targets"].copy(), {}
        started = time.perf_counter()
        for competition_id in data["competition_ids"]:
            rows = [
                r for r in inputs["matches"] if r["competition_id"] == competition_id
            ]
            targets = [
                r
                for r in rows
                if instant(data["window_start"])
                <= instant(r["kickoff"])
                < instant(data["data_cutoff"])
            ]
            replay_path = directory / f"sporting-{competition_id}.json"
            if replay_path.exists():
                replay = read_json(replay_path)
                if replay["input_hash"] != saved["hash"]:
                    raise ValueError("REPLAY_INPUT_MISMATCH")
                if replay["hash"] != identity(
                    {k: v for k, v in replay.items() if k != "hash"}
                ):
                    raise ValueError("REPLAY_HASH_MISMATCH")
            else:
                predictions, durations = sporting_replay(
                    [thaw(r) for r in rows],
                    [thaw(r) for r in targets],
                    data["configs"][str(competition_id)],
                )
                replay = {
                    "input_hash": saved["hash"],
                    "predictions": {str(k): v for k, v in predictions.items()},
                    "durations": durations,
                    "rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                    / 1024,
                }
                replay["hash"] = identity(replay)
                atomic_json(replay_path, replay)
            for code, seconds in replay["durations"].items():
                measure = resources.setdefault(code, {"seconds": 0.0, "rss_mib": 0.0})
                measure["seconds"] += seconds
                measure["rss_mib"] = max(measure["rss_mib"], replay["rss_mib"])
            market_started = time.perf_counter()
            for row in targets:
                candidates = replay["predictions"][str(row["match_id"])].copy()
                evidence = market.get(row["match_id"])
                if evidence and instant(evidence["kickoff"]) != instant(row["kickoff"]):
                    raise ValueError("CANONICAL_KICKOFF_CHANGED_SINCE_ACQUISITION")
                candidates["MARKET_CONSENSUS"] = {
                    "model_version": MODELS["MARKET_CONSENSUS"],
                    "status": evidence["status"] if evidence else "UNAVAILABLE",
                    "reason": (
                        evidence["reason"]
                        if evidence
                        else missing.get(
                            row["match_id"], "NO_MAPPED_HISTORICAL_EVIDENCE"
                        )
                    ),
                    **(
                        {"probabilities": evidence["probabilities"]}
                        if evidence and evidence["status"] == "PRODUCED"
                        else {}
                    ),
                    "evidence_id": evidence["evidence_id"] if evidence else None,
                }
                manifest.append(
                    {
                        **row,
                        "eligible": True,
                        "eligibility_reason": "CANONICAL_FT_WITH_SCORE",
                        "candidates": candidates,
                    }
                )
            measure = resources.setdefault(
                "MARKET_CONSENSUS", {"seconds": 0.0, "rss_mib": 0.0}
            )
            measure["seconds"] += time.perf_counter() - market_started
            measure["rss_mib"] = (
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
            )
        manifest.sort(key=lambda r: (r["competition_id"], r["kickoff"], r["match_id"]))
        summary = compare(
            manifest,
            data["models"],
            data["competition_ids"],
            resources,
            selection_policy=selection_policy,
        )
        if identity(execution_runtime()) != runtime_id:
            raise ValueError("EXECUTION_RUNTIME_CHANGED_DURING_ANALYSIS")
        result = {
            "analysis_lineage_version": ANALYSIS_LINEAGE_VERSION,
            "analysis_id": analysis_id,
            "analysis_mode": mode,
            "source_acquisition_id": acquisition_id,
            "execution_runtime": actual_runtime,
            "execution_runtime_id": runtime_id,
            "spec_id": spec.id,
            "spec": data,
            "input_hash": saved["hash"],
            "acquisition": state,
            "manifest": manifest,
            "summary": summary,
            "resources": {
                "analysis_seconds": time.perf_counter() - started,
                "rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            },
        }
        result["warnings"] = []
        if sum(r["seconds"] for r in resources.values()) > 3600:
            result["warnings"].append(
                "REPLAY_EXCEEDS_60_MINUTES_INVESTIGATE_IF_REPEATABLE"
            )
        if result["resources"]["rss_mib"] > 1024:
            result["warnings"].append("RSS_EXCEEDS_1_GIB_INVESTIGATE_IF_REPEATABLE")
        result["run_id"] = identity(result)
        atomic_json(complete, result)
        from .views import materialize_views

        materialize_views(directory, result)
        return result


def verify_run(result, spec):
    if result["spec_id"] != spec.id or result["spec"] != spec.data:
        raise ValueError("RUN_SPEC_MISMATCH")
    if identity({k: v for k, v in result.items() if k != "run_id"}) != result["run_id"]:
        raise ValueError("RUN_HASH_MISMATCH")
    if identity(result["manifest"]) != result["summary"]["manifest_hash"]:
        raise ValueError("MANIFEST_HASH_MISMATCH")
    runtime_fields = (
        "analysis_lineage_version",
        "execution_runtime",
        "execution_runtime_id",
    )
    if any(field in result for field in runtime_fields):
        if not all(field in result for field in runtime_fields):
            raise ValueError("EXECUTION_RUNTIME_PROVENANCE_INCOMPLETE")
        if (
            result["analysis_lineage_version"] != ANALYSIS_LINEAGE_VERSION
            or identity(result["execution_runtime"]) != result["execution_runtime_id"]
        ):
            raise ValueError("EXECUTION_RUNTIME_IDENTITY_MISMATCH")
        acquisition_id = identity(
            {"spec_id": spec.id, "pilot": result["acquisition"]["pilot"]}
        )
        mode = result["analysis_mode"]
        if mode not in {"STANDARD", "FRESH_CONFIRMATION_V2"}:
            raise ValueError("ANALYSIS_MODE_MISMATCH")
        expected_policy = (
            PAIRED_COMMON_SELECTION_POLICY
            if mode == "FRESH_CONFIRMATION_V2"
            else STANDARD_SELECTION_POLICY
        )
        if (
            result["source_acquisition_id"] != acquisition_id
            or result["acquisition"]["run_id"] != acquisition_id
            or result["summary"]["selection_policy"] != expected_policy
            or result["analysis_id"]
            != analysis_identity(
                spec.id,
                acquisition_id,
                mode=mode,
                selection_policy=expected_policy,
                runtime_id=result["execution_runtime_id"],
            )
        ):
            raise ValueError("ANALYSIS_LINEAGE_MISMATCH")
