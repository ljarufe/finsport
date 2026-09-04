import hashlib
import json

from .constants import DIXON_COLES_VERSION
from .datasets import eligible_finished_matches, local_day
from .readiness import active_profile


def dixon_coles_evidence_basis(competition, targets, *, cutoff, config):
    targets = sorted(targets, key=lambda match: match.pk)
    target_days = {local_day(match.kickoff) for match in targets}
    if len(target_days) != 1:
        raise ValueError("A Dixon-Coles evidence batch must use one local day.")
    day = next(iter(target_days))
    history = [
        match
        for match in eligible_finished_matches(competition, before=cutoff)
        if local_day(match.kickoff) < day
    ]
    profile = active_profile(competition)
    payload = {
        "model_version": DIXON_COLES_VERSION,
        "model_config": config,
        "cutoff": cutoff.isoformat(),
        "readiness_profile": (
            {
                "id": profile.pk,
                "version": profile.version,
                "model_version": profile.model_version,
                "model_config": profile.model_config,
                "approved": profile.approved,
                "requirements": profile.requirements,
            }
            if profile
            else None
        ),
        "targets": [
            {
                "id": match.pk,
                "season": match.season_id,
                "home": match.home_team_id,
                "away": match.away_team_id,
                "kickoff": match.kickoff.isoformat(),
                "modified": match.modified.isoformat(),
            }
            for match in targets
        ],
        "training": [
            {
                "id": match.pk,
                "season": match.season_id,
                "home": match.home_team_id,
                "away": match.away_team_id,
                "kickoff": match.kickoff.isoformat(),
                "home_score": match.home_score,
                "away_score": match.away_score,
                "outcome": match.outcome,
                "modified": match.modified.isoformat(),
            }
            for match in history
        ],
    }
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode()).hexdigest(), payload, history
