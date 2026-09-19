from difflib import SequenceMatcher

from football.models import Match
from football.reconciliation import (
    GENERIC_TEAM_TOKENS,
    MATCH_KICKOFF_TOLERANCE,
    find_team_candidate,
    normalized_entity_name,
)

from .storage import instant

MAPPING_POLICY = {
    "version": "FS018_ORDERED_PAIR_CONTEXT_V2",
    "minimum_leg": 0.6,
    "minimum_pair": 0.78,
    "minimum_margin": 0.1,
}


def _name_score(provider_name, canonical_name):
    left = set(normalized_entity_name(provider_name).split()) - GENERIC_TEAM_TOKENS
    right = set(normalized_entity_name(canonical_name).split()) - GENERIC_TEAM_TOKENS
    if not left or not right or not left & right:
        return 0.0
    if left == right:
        return 1.0
    overlap = len(left & right)
    containment = overlap / min(len(left), len(right))
    precision = overlap / max(len(left), len(right))
    sequence = SequenceMatcher(
        None, " ".join(sorted(left)), " ".join(sorted(right))
    ).ratio()
    return round(0.55 * containment + 0.25 * precision + 0.20 * sequence, 6)


def map_fixture(competition, fixture):
    home, home_confidence = find_team_candidate(competition, fixture["home_name"])
    away, away_confidence = find_team_candidate(competition, fixture["away_name"])
    result = {
        "status": "UNMATCHED",
        "reason": "TEAM_UNRESOLVED",
        "home_confidence": home_confidence,
        "away_confidence": away_confidence,
        "method": "TEAM_FIRST_V1",
        "confidence": 0.0,
    }
    kickoff = instant(fixture["kickoff"])
    window = Match.objects.filter(
        season__competition=competition,
        kickoff__gte=kickoff - MATCH_KICKOFF_TOLERANCE,
        kickoff__lte=kickoff + MATCH_KICKOFF_TOLERANCE,
    )
    candidates = (
        list(window.filter(home_team=home, away_team=away).order_by("pk")[:2])
        if home is not None and away is not None
        else []
    )
    result["candidate_ids"] = [item.pk for item in candidates]
    result["reason"] = "NO_MATCH" if not candidates else "MULTIPLE_MATCHES"
    if len(candidates) > 1:
        result["status"] = "AMBIGUOUS"
    elif candidates:
        result.update(
            status="MATCHED",
            reason="",
            match_id=candidates[0].pk,
            canonical_kickoff=candidates[0].kickoff.isoformat(),
            confidence=min(home_confidence, away_confidence),
        )
    if candidates:
        return result
    ranked = []
    for candidate in window.select_related("home_team", "away_team").order_by("pk"):
        home_score = _name_score(fixture["home_name"], candidate.home_team.name)
        away_score = _name_score(fixture["away_name"], candidate.away_team.name)
        if min(home_score, away_score) < MAPPING_POLICY["minimum_leg"]:
            continue
        ranked.append(
            ((home_score + away_score) / 2, candidate, home_score, away_score)
        )
    ranked.sort(key=lambda row: (-row[0], row[1].pk))
    result["method"] = MAPPING_POLICY["version"]
    result["candidate_ids"] = [row[1].pk for row in ranked]
    if not ranked:
        result["reason"] = "NO_CONFIDENT_ORDERED_PAIR"
        return result
    score, candidate, home_score, away_score = ranked[0]
    result.update(
        confidence=round(score, 6),
        home_confidence=home_score,
        away_confidence=away_score,
    )
    if score < MAPPING_POLICY["minimum_pair"]:
        result["reason"] = "LOW_PAIR_CONFIDENCE"
    elif len(ranked) > 1 and score - ranked[1][0] < MAPPING_POLICY["minimum_margin"]:
        result.update(status="AMBIGUOUS", reason="PAIR_MARGIN_TOO_SMALL")
    else:
        result.update(
            status="MATCHED",
            reason="",
            match_id=candidate.pk,
            canonical_kickoff=candidate.kickoff.isoformat(),
        )
    return result
