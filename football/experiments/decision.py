"""Frozen FS-019 Decision candidates and exact CURRENT policy replay."""

from dataclasses import asdict, dataclass

from football.prediction.constants import (
    MODAL_ALL_VERSION,
    SELECTIVE_CONFIDENCE_VERSION,
)
from football.prediction.contracts import ProbabilityResult
from football.prediction.policies import modal_all, selective_confidence

from .historical_prices import best_price, validate_price_evidence


@dataclass(frozen=True)
class DecisionCandidate:
    candidate_id: str
    order: int
    policy: str
    version: str
    variant: str
    threshold: float | None = None

    def record(self):
        return asdict(self)


CANDIDATES = (
    DecisionCandidate("MODAL_ALL", 1, "MODAL_ALL", MODAL_ALL_VERSION, ""),
    *(
        DecisionCandidate(
            f"SELECTIVE_CONFIDENCE_{threshold:.2f}",
            order,
            "SELECTIVE_CONFIDENCE",
            SELECTIVE_CONFIDENCE_VERSION,
            f"{threshold:.2f}",
            threshold,
        )
        for order, threshold in enumerate((0.40, 0.45, 0.50, 0.55, 0.60), 2)
    ),
)
CANDIDATE_IDS = tuple(candidate.candidate_id for candidate in CANDIDATES)
MODAL_CANDIDATE_ID = CANDIDATES[0].candidate_id
EXPECTED_ACTION_COUNTS = {
    "MODAL_ALL": {"BET": 1906, "NO_BET": 0, "HOME": 1295, "DRAW": 23, "AWAY": 588},
    "SELECTIVE_CONFIDENCE_0.40": {
        "BET": 1507,
        "NO_BET": 399,
        "HOME": 1084,
        "DRAW": 2,
        "AWAY": 421,
    },
    "SELECTIVE_CONFIDENCE_0.45": {
        "BET": 1141,
        "NO_BET": 765,
        "HOME": 823,
        "DRAW": 0,
        "AWAY": 318,
    },
    "SELECTIVE_CONFIDENCE_0.50": {
        "BET": 862,
        "NO_BET": 1044,
        "HOME": 624,
        "DRAW": 0,
        "AWAY": 238,
    },
    "SELECTIVE_CONFIDENCE_0.55": {
        "BET": 650,
        "NO_BET": 1256,
        "HOME": 472,
        "DRAW": 0,
        "AWAY": 178,
    },
    "SELECTIVE_CONFIDENCE_0.60": {
        "BET": 450,
        "NO_BET": 1456,
        "HOME": 337,
        "DRAW": 0,
        "AWAY": 113,
    },
}


def candidate_matrix():
    return [candidate.record() for candidate in CANDIDATES]


def _probability(row):
    return ProbabilityResult(row["p_home"], row["p_draw"], row["p_away"])


def replay_candidate(snapshot_row, candidate):
    validate_price_evidence(snapshot_row)
    probability = _probability(snapshot_row)
    if candidate.policy == "MODAL_ALL":
        policy = modal_all(probability)
    elif candidate.policy == "SELECTIVE_CONFIDENCE":
        policy = selective_confidence(probability, candidate.threshold)
    else:  # Defensive: VALUE and future policy families are ineligible.
        raise ValueError("INELIGIBLE_DECISION_POLICY")
    is_bet = policy.action != "NO_BET"
    price = best_price(snapshot_row, policy.action) if is_bet else {}
    return {
        "match_id": snapshot_row["match_id"],
        "competition_id": snapshot_row["competition_id"],
        "kickoff": snapshot_row["kickoff"],
        "actual_regulation_outcome": snapshot_row["actual_regulation_outcome"],
        "candidate_id": candidate.candidate_id,
        "candidate_order": candidate.order,
        "policy": candidate.policy,
        "policy_version": candidate.version,
        "variant": candidate.variant,
        "threshold": candidate.threshold,
        "action": "BET" if is_bet else "NO_BET",
        "selected_outcome": policy.action if is_bet else None,
        "reason": policy.reason,
        "model_probability": policy.model_probability,
        "upstream_probabilities": {
            "HOME": snapshot_row["p_home"],
            "DRAW": snapshot_row["p_draw"],
            "AWAY": snapshot_row["p_away"],
        },
        "provider_fixture_id": snapshot_row["provider_fixture_id"],
        "fs018_evidence_id": snapshot_row["fs018_evidence_id"],
        "raw_cache_hash": snapshot_row["raw_cache_hash"],
        **price,
    }


def replay_decisions(snapshot_rows):
    rows = []
    seen = set()
    for source in snapshot_rows:
        match_id = source["match_id"]
        if match_id in seen:
            raise ValueError("DUPLICATE_DECISION_INPUT_MATCH")
        seen.add(match_id)
        rows.extend(replay_candidate(source, candidate) for candidate in CANDIDATES)
    return rows


def validate_frozen_action_counts(rows):
    observed = {}
    for candidate_id in CANDIDATE_IDS:
        members = [row for row in rows if row["candidate_id"] == candidate_id]
        observed[candidate_id] = {
            "BET": sum(row["action"] == "BET" for row in members),
            "NO_BET": sum(row["action"] == "NO_BET" for row in members),
            **{
                outcome: sum(row.get("selected_outcome") == outcome for row in members)
                for outcome in ("HOME", "DRAW", "AWAY")
            },
        }
    if observed != EXPECTED_ACTION_COUNTS:
        raise ValueError("FROZEN_DECISION_ACTION_COUNTS_MISMATCH")
    return observed
