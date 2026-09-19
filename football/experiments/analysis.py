"""Reusable paired comparison of frozen per-Match prediction evidence."""

from collections import Counter, defaultdict
from itertools import combinations

import numpy as np

from football.prediction.constants import OUTCOMES
from football.prediction.contracts import ProbabilityResult
from football.prediction.datasets import local_day
from football.prediction.metrics import prediction_metrics

from .storage import identity, instant

STANDARD_SELECTION_POLICY = "GLOBAL_GUARDRAIL_FALLBACK_V1"
PAIRED_COMMON_SELECTION_POLICY = "PAIRED_COMMON_EQUAL_LEAGUE_LOG_LOSS_V1"


def week_id(kickoff):
    year, week, _ = local_day(instant(kickoff)).isocalendar()
    return f"{year}-W{week:02d}"


def legitimate(entry):
    if entry["status"] != "PRODUCED":
        return False
    ProbabilityResult(*entry["probabilities"])
    return True


def metrics(rows, code):
    return prediction_metrics(
        [r["outcome"] for r in rows],
        [r["candidates"][code]["probabilities"] for r in rows],
    )


def paired_bootstrap(rows, candidates, competitions, *, replicates=5000, seed=18092026):
    """Resample complete weeks within each league; share draws across all arms."""
    rng = np.random.default_rng(seed)
    scores = np.zeros((replicates, len(candidates)))
    blocks_report = {}
    for competition in competitions:
        blocks = defaultdict(list)
        for row in rows:
            if row["competition_id"] == competition:
                blocks[week_id(row["kickoff"])].append(row)
        if not blocks:
            raise ValueError("EMPTY_COMMON_LEAGUE")
        ordered = sorted(blocks)
        blocks_report[str(competition)] = ordered
        sums, counts = [], []
        for week in ordered:
            members = blocks[week]
            counts.append(len(members))
            sums.append(
                [
                    sum(
                        -np.log(
                            np.clip(
                                r["candidates"][code]["probabilities"][
                                    OUTCOMES.index(r["outcome"])
                                ],
                                np.finfo(float).eps,
                                1 - np.finfo(float).eps,
                            )
                        )
                        for r in members
                    )
                    for code in candidates
                ]
            )
        # Each row of draws defines a replicate shared by every candidate.
        draws = rng.integers(0, len(ordered), size=(replicates, len(ordered)))
        scores += (
            np.asarray(sums)[draws].sum(axis=1)
            / np.asarray(counts)[draws].sum(axis=1)[:, None]
            / len(competitions)
        )
    intervals = {}
    for a, b in combinations(range(len(candidates)), 2):
        delta = scores[:, a] - scores[:, b]
        intervals[f"{candidates[a]}|{candidates[b]}"] = {
            "a": candidates[a],
            "b": candidates[b],
            "lower": float(np.quantile(delta, 0.025)),
            "upper": float(np.quantile(delta, 0.975)),
            "mean_delta": float(delta.mean()),
        }
    return {
        "replicates": replicates,
        "seed": seed,
        "blocks": blocks_report,
        "paired_intervals": intervals,
    }


def compare(
    manifest,
    model_identities,
    competitions,
    resources,
    *,
    selection_policy=STANDARD_SELECTION_POLICY,
):
    if selection_policy not in {
        STANDARD_SELECTION_POLICY,
        PAIRED_COMMON_SELECTION_POLICY,
    }:
        raise ValueError("UNKNOWN_SELECTION_POLICY")
    rows = sorted(
        manifest, key=lambda r: (r["competition_id"], r["kickoff"], r["match_id"])
    )
    if len({r["match_id"] for r in rows}) != len(rows):
        raise ValueError("DUPLICATE_CANONICAL_MATCH")
    candidates = sorted(model_identities)
    eligible_count = sum(r["eligible"] for r in rows)
    natural = {
        code: [r for r in rows if r["eligible"] and legitimate(r["candidates"][code])]
        for code in candidates
    }
    global_candidates = [
        code
        for code in candidates
        if all(
            any(r["competition_id"] == league for r in natural[code])
            for league in competitions
        )
    ]
    paired_common = selection_policy == PAIRED_COMMON_SELECTION_POLICY
    all_four_globally_eligible = set(global_candidates) == set(candidates)
    comparison_candidates = (
        candidates
        if paired_common and all_four_globally_eligible
        else ([] if paired_common else global_candidates)
    )
    common = [
        r
        for r in rows
        if r["eligible"]
        and comparison_candidates
        and all(legitimate(r["candidates"][code]) for code in comparison_candidates)
    ]
    common_ids = [r["match_id"] for r in common]
    cohort = {
        "compared_candidates": comparison_candidates,
        "COMMON": common_ids,
        "NATURAL": {
            code: [r["match_id"] for r in natural[code]] for code in candidates
        },
    }
    reports = {}
    for code in candidates:
        # Partial challengers remain diagnostic on their own valid evidence.
        own_common = [r for r in common if legitimate(r["candidates"][code])]
        league_metrics = {
            str(league): {
                "NATURAL": metrics(
                    [r for r in natural[code] if r["competition_id"] == league], code
                ),
                "COMMON": metrics(
                    [r for r in own_common if r["competition_id"] == league], code
                ),
            }
            for league in competitions
        }
        weeks = sorted({week_id(r["kickoff"]) for r in rows})
        temporal = {
            week: metrics(
                [r for r in natural[code] if week_id(r["kickoff"]) == week], code
            )
            for week in weeks
        }
        losses = [
            v["NATURAL"]["log_loss"]
            for v in league_metrics.values()
            if v["NATURAL"]["sample_count"]
        ]
        time_losses = [v["log_loss"] for v in temporal.values() if v["sample_count"]]
        reasons = Counter(
            r["candidates"][code]["reason"]
            for r in rows
            if r["candidates"][code]["status"] != "PRODUCED"
        )
        primary = [v["COMMON"].get("log_loss") for v in league_metrics.values()]
        reports[code] = {
            "model_version": model_identities[code],
            "global_eligible": code in global_candidates,
            "role": (
                "GLOBAL_CANDIDATE"
                if code in global_candidates
                else "PARTIAL_DIAGNOSTIC"
            ),
            "NATURAL": metrics(natural[code], code),
            "COMMON": metrics(own_common, code),
            "coverage": len(natural[code]) / eligible_count if eligible_count else 0,
            "eligible_target_count": eligible_count,
            "failed_count": sum(
                r["candidates"][code]["status"] == "FAILED" for r in rows
            ),
            "unavailable_count": sum(
                r["candidates"][code]["status"] == "UNAVAILABLE" for r in rows
            ),
            "reasons": dict(reasons),
            "per_match_log_loss": {
                str(r["match_id"]): float(
                    -np.log(
                        np.clip(
                            r["candidates"][code]["probabilities"][
                                OUTCOMES.index(r["outcome"])
                            ],
                            np.finfo(float).eps,
                            1 - np.finfo(float).eps,
                        )
                    )
                )
                for r in natural[code]
            },
            "per_league": league_metrics,
            "temporal": temporal,
            "primary_score": (
                float(np.mean(primary))
                if primary
                and all(v is not None for v in primary)
                and code in global_candidates
                else None
            ),
            "stability": {
                "league_log_loss_sd": float(np.std(losses)) if losses else None,
                "week_log_loss_sd": float(np.std(time_losses)) if time_losses else None,
            },
        }
    exclusions = {
        str(r["match_id"]): {
            code: r["candidates"][code]["reason"]
            for code in comparison_candidates
            if not legitimate(r["candidates"][code])
        }
        for r in rows
        if r["match_id"] not in set(common_ids)
    }
    result = {
        "manifest_hash": identity(rows),
        "cohort_hash": identity(cohort),
        "cohorts": cohort,
        "common_exclusions": exclusions,
        "candidates": reports,
        "selection_policy": selection_policy,
        "selection_basis": (
            "LOWEST_EQUAL_LEAGUE_COMMON_LOG_LOSS"
            if paired_common
            else "FROZEN_GLOBAL_GUARDRAIL_FALLBACK"
        ),
        "coverage_used_for_selection": not paired_common,
        "natural_used_for_selection": not paired_common,
        "disposition": "INSUFFICIENT_EVIDENCE",
        "selected": None,
    }
    if paired_common and not all_four_globally_eligible:
        result["selection_failure"] = "ALL_FOUR_GLOBAL_CANDIDATES_REQUIRED"
        return result
    if not comparison_candidates or any(
        reports[c]["primary_score"] is None for c in comparison_candidates
    ):
        result["selection_failure"] = "COMMON_EVIDENCE_REQUIRED_IN_EVERY_LEAGUE"
        return result
    uncertainty = paired_bootstrap(common, comparison_candidates, competitions)
    result["uncertainty"] = uncertainty
    ordered = sorted(
        comparison_candidates,
        key=lambda c: (reports[c]["primary_score"], c, model_identities[c]),
    )
    best = ordered[0]

    def beats(other):
        a, b = sorted((best, other))
        interval = uncertainty["paired_intervals"][f"{a}|{b}"]
        return interval["upper"] < 0 if best == a else interval["lower"] > 0

    if paired_common:
        clear = len(ordered) > 1 and all(beats(c) for c in ordered[1:])
        result.update(
            selected=best,
            disposition="CLEAR_SUPERIORITY" if clear else "NO_CLEAR_SUPERIORITY",
            score_order=ordered,
            selection_diagnostics={
                "coverage": "DIAGNOSTIC_ONLY",
                "natural": "DIAGNOSTIC_ONLY",
                "stability": "DIAGNOSTIC_ONLY",
                "failures": "DIAGNOSTIC_ONLY",
                "dependencies": "DIAGNOSTIC_ONLY",
                "resources": "DIAGNOSTIC_ONLY",
            },
            resources=resources,
        )
        return result

    def stability(code):
        values = reports[code]["stability"]
        return (values["league_log_loss_sd"], values["week_log_loss_sd"])

    # Preserve the original frozen selection behavior for STANDARD runs.
    guardrails = {
        "coverage": all(
            reports[best]["coverage"] >= reports[c]["coverage"]
            for c in global_candidates
        ),
        "stability": all(stability(best) <= stability(c) for c in global_candidates),
        "failures": all(
            reports[best]["failed_count"] <= reports[c]["failed_count"]
            for c in global_candidates
        ),
    }
    clear = (
        len(ordered) > 1
        and all(beats(c) for c in ordered[1:])
        and all(guardrails.values())
    )
    missing_resources = [c for c in global_candidates if c not in resources]
    if missing_resources:
        raise ValueError("Measured resource evidence required for selection")
    fallback = sorted(
        global_candidates,
        key=lambda c: (
            -reports[c]["coverage"],
            *stability(c),
            reports[c]["failed_count"],
            int(c == "MARKET_CONSENSUS"),
            resources[c]["seconds"],
            resources[c]["rss_mib"],
            c,
            model_identities[c],
        ),
    )
    result.update(
        selected=best if clear else fallback[0],
        guardrails=guardrails,
        disposition="CLEAR_SUPERIORITY" if clear else "NO_CLEAR_SUPERIORITY",
        fallback_order=fallback,
        resources=resources,
    )
    return result
