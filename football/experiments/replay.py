"""Read-only sporting replay with a frozen target batch per Lima calendar day."""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from football.prediction.contracts import (
    FailedPrediction,
    ProbabilityResult,
    UnavailablePrediction,
)
from football.prediction.datasets import (
    daily_batches,
    history_before_local_day,
    rows_from_matches,
)
from football.prediction.elo import EloMultinomialAdapter
from football.prediction.goal_models import DixonColesAdapter, IndependentPoissonAdapter
from football.prediction.readiness import ReadinessAssessment

from .spec import MODELS


def adapter_for(code, config):
    if code == "DIXON_COLES":
        return DixonColesAdapter(xi=config["xi"])
    if code == "INDEPENDENT_POISSON":
        return IndependentPoissonAdapter(xi=config["xi"])
    return EloMultinomialAdapter(k=config["k"], c=config["C"])


def frozen_readiness(profile, diagnostics):
    if not profile or not profile["approved"]:
        return ReadinessAssessment(False, "NO_APPROVED_READINESS_PROFILE")
    requirements = profile["requirements"]
    for requirement, diagnostic in (
        ("min_class_support", "class_support_min"),
        ("min_training_matches", "training_matches"),
        ("min_home_team_matches", "home_team_history"),
        ("min_away_team_matches", "away_team_history"),
    ):
        if diagnostics.get(diagnostic, 0) < requirements.get(requirement, 0):
            return ReadinessAssessment(False, "BELOW_FROZEN_PROFILE")
    if requirements.get("require_connected", True) and not diagnostics.get("connected"):
        return ReadinessAssessment(False, "TRAINING_GRAPH_NOT_CONNECTED")
    return ReadinessAssessment(True, "FROZEN_PROFILE_PASSED")


def prediction_entry(result, code):
    entry = {"model_version": MODELS[code], "diagnostics": result.diagnostics}
    if isinstance(result, ProbabilityResult):
        return {
            **entry,
            "status": "PRODUCED",
            "reason": "",
            "probabilities": list(result.as_tuple()),
        }
    return {
        **entry,
        "status": "FAILED" if isinstance(result, FailedPrediction) else "UNAVAILABLE",
        "reason": result.reason,
    }


def sporting_replay(matches, targets, frozen_config, *, factory=adapter_for):
    evidence, durations = {}, {
        code: 0.0 for code in MODELS if code != "MARKET_CONSENSUS"
    }
    # Fail closed on contradictory canonical outcomes before any scores are emitted.
    rows_from_matches(matches)
    for day, batch in daily_batches(targets):
        history = history_before_local_day(matches, day)
        cutoff = datetime.combine(
            day, datetime.min.time(), tzinfo=ZoneInfo("America/Lima")
        )
        for code in durations:
            started = time.perf_counter()
            config = frozen_config["executable"][code]
            try:
                if config.get("status") == "UNAVAILABLE":
                    fitted = UnavailablePrediction(config["reason"])
                    adapter = None
                else:
                    adapter = factory(code, config)
                    if adapter.model_version != MODELS[code]:
                        raise ValueError("ADAPTER_VERSION_MISMATCH")
                    if code == "DIXON_COLES":
                        profile = frozen_config["readiness_profiles"].get(code)
                        if profile and (
                            profile["model_version"] != adapter.model_version
                            or profile["model_config"] != adapter.config
                        ):
                            profile = None
                        fitted = adapter.fit_for_targets(
                            history,
                            cutoff,
                            batch,
                            readiness_assessor=lambda d: frozen_readiness(profile, d),
                        )
                    else:
                        fitted = adapter.fit(history, cutoff)
            except Exception as error:
                fitted = FailedPrediction(
                    "FIT_FAILED", {"error_class": type(error).__name__}
                )
            for match in batch:
                try:
                    result = (
                        fitted
                        if isinstance(fitted, (UnavailablePrediction, FailedPrediction))
                        else adapter.predict(match, cutoff)
                    )
                except Exception as error:
                    result = FailedPrediction(
                        "PREDICT_FAILED", {"error_class": type(error).__name__}
                    )
                evidence.setdefault(match.id, {})[code] = prediction_entry(result, code)
            durations[code] += time.perf_counter() - started
    return evidence, durations
