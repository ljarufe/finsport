"""Frozen FS-019 uncertainty, stability, disposition and fallback election."""

import math
from collections import defaultdict
from statistics import mean
from zoneinfo import ZoneInfo

import numpy as np

from .decision import CANDIDATE_IDS, MODAL_CANDIDATE_ID
from .storage import identity, instant

BOOTSTRAP_REPLICATES = 5000
BOOTSTRAP_SEED = 18092026
LIMA = ZoneInfo("America/Lima")


def week_id(kickoff):
    local = instant(kickoff).astimezone(LIMA).date()
    year, week, _ = local.isocalendar()
    return f"{year}-W{week:02d}"


def _candidate_order(candidate_ids):
    return {candidate: order for order, candidate in enumerate(candidate_ids)}


def equal_league_ppo(rows, candidate_id, competition_ids):
    league_values = []
    for competition in competition_ids:
        members = [
            row
            for row in rows
            if row["candidate_id"] == candidate_id
            and row["competition_id"] == competition
        ]
        if not members:
            raise ValueError("EMPTY_DECISION_COMMON_LEAGUE")
        league_values.append(sum(row["reward"] for row in members) / len(members))
    return float(mean(league_values))


def observed_ranking(rows, candidate_ids, competition_ids):
    scores = {
        candidate: equal_league_ppo(rows, candidate, competition_ids)
        for candidate in candidate_ids
    }
    order = _candidate_order(candidate_ids)
    ranking = sorted(
        candidate_ids, key=lambda candidate: (-scores[candidate], order[candidate])
    )
    return scores, ranking


def _match_matrix(rows, candidate_ids):
    matches = {}
    for row in rows:
        match = matches.setdefault(
            row["match_id"],
            {
                "match_id": row["match_id"],
                "competition_id": row["competition_id"],
                "kickoff": row["kickoff"],
                "rewards": {},
            },
        )
        if (
            match["competition_id"] != row["competition_id"]
            or match["kickoff"] != row["kickoff"]
            or row["candidate_id"] in match["rewards"]
        ):
            raise ValueError("DECISION_ROW_COHORT_MISMATCH")
        match["rewards"][row["candidate_id"]] = float(row["reward"])
    expected = set(candidate_ids)
    if not matches or any(
        set(match["rewards"]) != expected for match in matches.values()
    ):
        raise ValueError("INCOMPLETE_CANDIDATE_MATCH_MATRIX")
    return list(matches.values())


def paired_weekly_bootstrap(
    rows,
    candidate_ids=CANDIDATE_IDS,
    competition_ids=(),
    *,
    replicates=BOOTSTRAP_REPLICATES,
    seed=BOOTSTRAP_SEED,
):
    """Paired Competition × Lima ISO-week bootstrap with the frozen max guard."""
    candidate_ids = tuple(candidate_ids)
    competition_ids = tuple(competition_ids)
    if replicates <= 0 or not competition_ids or len(candidate_ids) < 2:
        raise ValueError("INVALID_BOOTSTRAP_GEOMETRY")
    matches = _match_matrix(rows, candidate_ids)
    rng = np.random.default_rng(seed)
    replicate_scores = np.zeros((replicates, len(candidate_ids)), dtype=float)
    blocks_report = {}
    draw_identities = {}
    for competition in competition_ids:
        blocks = defaultdict(list)
        for match in matches:
            if match["competition_id"] == competition:
                blocks[week_id(match["kickoff"])].append(match)
        if not blocks:
            raise ValueError("EMPTY_DECISION_COMMON_LEAGUE")
        ordered = sorted(blocks)
        blocks_report[str(competition)] = [
            {
                "week": week,
                "match_ids": sorted(item["match_id"] for item in blocks[week]),
            }
            for week in ordered
        ]
        sums = np.asarray(
            [
                [
                    sum(item["rewards"][candidate] for item in blocks[week])
                    for candidate in candidate_ids
                ]
                for week in ordered
            ],
            dtype=float,
        )
        counts = np.asarray([len(blocks[week]) for week in ordered], dtype=int)
        draws = rng.integers(0, len(ordered), size=(replicates, len(ordered)))
        draw_identities[str(competition)] = identity(draws.tolist())
        replicate_scores += (
            sums[draws].sum(axis=1)
            / counts[draws].sum(axis=1)[:, None]
            / len(competition_ids)
        )
    observed, ranking = observed_ranking(rows, candidate_ids, competition_ids)
    top = ranking[0]
    top_index = candidate_ids.index(top)
    competitors = [candidate for candidate in candidate_ids if candidate != top]
    observed_deltas = {
        candidate: observed[top] - observed[candidate] for candidate in competitors
    }
    adverse = []
    for candidate in competitors:
        index = candidate_ids.index(candidate)
        bootstrap_delta = replicate_scores[:, top_index] - replicate_scores[:, index]
        adverse.append(observed_deltas[candidate] - bootstrap_delta)
    maxima = np.max(np.column_stack(adverse), axis=1)
    q95 = float(np.quantile(maxima, 0.95, method="linear"))
    lower_bounds = {
        candidate: observed_deltas[candidate] - q95 for candidate in competitors
    }
    scores = {
        candidate: replicate_scores[:, index].tolist()
        for index, candidate in enumerate(candidate_ids)
    }
    return {
        "method": "MAX_CENTERED_ADVERSE_UNSTUDENTIZED_V1",
        "quantile_method": "LINEAR_R7",
        "replicates": replicates,
        "seed": seed,
        "blocks": blocks_report,
        "block_count": sum(len(value) for value in blocks_report.values()),
        "draw_identities": draw_identities,
        "draws_hash": identity(draw_identities),
        "replicate_scores": scores,
        "replicate_scores_hash": identity(scores),
        "observed_top": top,
        "observed_deltas": observed_deltas,
        "simultaneous_q95": q95,
        "simultaneous_lower_bounds": lower_bounds,
    }


def stability_checks(rows, top, runner_up, competition_ids):
    """Keep full-corpus T/R fixed across ten LOO and two chronological halves."""
    competition_ids = tuple(competition_ids)
    loo = []
    for removed in competition_ids:
        remaining = tuple(value for value in competition_ids if value != removed)
        subset = [row for row in rows if row["competition_id"] != removed]
        delta = equal_league_ppo(subset, top, remaining) - equal_league_ppo(
            subset, runner_up, remaining
        )
        loo.append({"removed_competition_id": removed, "delta": delta})
    pair_rows = [row for row in rows if row["candidate_id"] in {top, runner_up}]
    matches = sorted(
        _match_matrix(pair_rows, (top, runner_up)),
        key=lambda row: (instant(row["kickoff"]), row["match_id"]),
    )
    split_index = len(matches) // 2
    halves = []
    for name, selected in (
        ("FIRST", matches[:split_index]),
        ("SECOND", matches[split_index:]),
    ):
        match_ids = {match["match_id"] for match in selected}
        subset = [row for row in pair_rows if row["match_id"] in match_ids]
        delta = equal_league_ppo(subset, top, competition_ids) - equal_league_ppo(
            subset, runner_up, competition_ids
        )
        halves.append({"half": name, "sample_count": len(selected), "delta": delta})
    return {
        "fixed_top": top,
        "fixed_strongest_alternative": runner_up,
        "leave_one_league_out": loo,
        "chronological_split_index": split_index,
        "chronological_halves": halves,
        "deltas": [item["delta"] for item in loo + halves],
    }


def scientific_disposition(evidence_available, lower_bounds, stability_deltas):
    lower_bounds = list(lower_bounds)
    stability_deltas = list(stability_deltas)
    if (
        not evidence_available
        or len(lower_bounds) != 5
        or len(stability_deltas) != 12
        or not all(math.isfinite(value) for value in lower_bounds + stability_deltas)
    ):
        return "INSUFFICIENT_EVIDENCE"
    if any(delta < 0 for delta in stability_deltas):
        return "UNSTABLE"
    if all(bound > 0 for bound in lower_bounds) and all(
        delta > 0 for delta in stability_deltas
    ):
        return "CLEAR_SUPERIORITY"
    return "NO_CLEAR_SUPERIORITY"


def fallback_selection(
    disposition, top, scores, lower_bounds, candidate_ids=CANDIDATE_IDS
):
    if disposition == "INSUFFICIENT_EVIDENCE":
        return {"selected": None, "promotion_permitted": False, "survivors": []}
    survivors = [top] + [
        candidate
        for candidate in candidate_ids
        if candidate != top and lower_bounds[candidate] <= 0
    ]
    if disposition == "CLEAR_SUPERIORITY":
        selected = top
    elif MODAL_CANDIDATE_ID in survivors:
        selected = MODAL_CANDIDATE_ID
    else:
        order = _candidate_order(candidate_ids)
        selected = sorted(
            survivors, key=lambda candidate: (-scores[candidate], order[candidate])
        )[0]
    return {"selected": selected, "promotion_permitted": True, "survivors": survivors}


def compare_decisions(rows, candidate_ids=CANDIDATE_IDS, competition_ids=()):
    scores, ranking = observed_ranking(rows, candidate_ids, competition_ids)
    bootstrap = paired_weekly_bootstrap(rows, candidate_ids, competition_ids)
    stability = stability_checks(rows, ranking[0], ranking[1], competition_ids)
    lower_bounds = bootstrap["simultaneous_lower_bounds"]
    disposition = scientific_disposition(
        True, lower_bounds.values(), stability["deltas"]
    )
    fallback = fallback_selection(
        disposition, ranking[0], scores, lower_bounds, candidate_ids
    )
    return {
        "primary_metric": "EQUAL_LEAGUE_FIXED_UNIT_PPO_PER_DECISION_COMMON_OPPORTUNITY",
        "observed_global_ppo": scores,
        "observed_order": ranking,
        "observed_top": ranking[0],
        "observed_strongest_alternative": ranking[1],
        "bootstrap": bootstrap,
        "stability": stability,
        "disposition": disposition,
        **fallback,
    }
