import hashlib
import json
from dataclasses import dataclass

from football.models import DixonColesReadinessProfile


@dataclass(frozen=True)
class ReadinessAssessment:
    eligible: bool
    reason: str
    profile: DixonColesReadinessProfile | None = None


def active_profile(competition):
    return (
        competition.dc_readiness_profiles.filter(active=True)
        .order_by("-created", "-id")
        .first()
    )


def config_identity(config):
    material = json.dumps(
        config or {}, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(material.encode()).hexdigest()


def assess_bet_eligibility(competition, diagnostics, *, model_version, model_config):
    profile = active_profile(competition)
    if profile is None or not profile.approved:
        return ReadinessAssessment(False, "NO_APPROVED_READINESS_PROFILE", profile)
    if profile.model_version != model_version:
        return ReadinessAssessment(False, "READINESS_MODEL_VERSION_MISMATCH", profile)
    if config_identity(profile.model_config) != config_identity(model_config):
        return ReadinessAssessment(False, "READINESS_MODEL_CONFIG_MISMATCH", profile)
    requirements = profile.requirements or {}
    checks = (
        ("min_training_matches", "training_matches", "TRAINING_HISTORY_BELOW_PROFILE"),
        (
            "min_home_team_matches",
            "home_team_history",
            "HOME_TEAM_HISTORY_BELOW_PROFILE",
        ),
        (
            "min_away_team_matches",
            "away_team_history",
            "AWAY_TEAM_HISTORY_BELOW_PROFILE",
        ),
    )
    for requirement, diagnostic, reason in checks:
        minimum = requirements.get(requirement)
        if minimum is not None and diagnostics.get(diagnostic, 0) < minimum:
            return ReadinessAssessment(False, reason, profile)
    if requirements.get("require_connected", True) and not diagnostics.get("connected"):
        return ReadinessAssessment(False, "TRAINING_GRAPH_NOT_CONNECTED", profile)
    return ReadinessAssessment(True, "APPROVED_READINESS_PROFILE_PASSED", profile)
