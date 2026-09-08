"""Automatic DB-only provisioning owned by existing periodic maintenance."""

import json
from dataclasses import dataclass, field
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from football.historical import historical_coverage_is_current
from football.models import Competition, HistoricalCoverage, ReadinessProfile
from football.observability.events import emit_event

from . import calibration
from .readiness import active_profile, config_identity

AUTOMATIC_MODELS = (calibration.POISSON, calibration.ELO)
INSUFFICIENT = "EVIDENCE_INSUFFICIENT_TO_DEFINE_USABLE_PROFILE"


@dataclass(frozen=True)
class SportingBasis:
    """Competition-scoped canonical sporting evidence for one operation."""

    payload: dict
    seasons: tuple
    by_year: dict
    reason: str


@dataclass(frozen=True)
class ReadinessCurrentness:
    """Model-scoped identity derived from one SportingBasis."""

    model_code: str
    identity: str
    payload: dict
    reason: str


@dataclass
class CalibrationBudget:
    """Count only full calibration calls actually started during one wake."""

    maximum: int
    attempts: list[tuple[int, str]] = field(default_factory=list)

    @property
    def available(self):
        return len(self.attempts) < self.maximum

    def record_attempt(self, competition, model):
        if not self.available:
            raise RuntimeError("Full calibration budget exhausted.")
        self.attempts.append((competition.pk, model))


@lru_cache(maxsize=1)
def frozen_profiles():
    return json.loads(Path(__file__).with_name("fs012_profiles.json").read_text())[
        "profiles"
    ]


def build_sporting_basis(competition):
    """Read and hash canonical sporting evidence once per competition operation."""
    coverage = HistoricalCoverage.objects.filter(competition=competition).first()
    payload = {
        "competition": competition.pk,
        "coverage": None,
    }
    if coverage:
        payload["coverage"] = {
            "status": coverage.status,
            "strategy": coverage.strategy_version,
            "required": coverage.required_seasons,
            "covered": coverage.covered_seasons,
            "unresolved": coverage.unresolved_seasons,
        }
    seasons = list(competition.seasons.filter(is_current=False).order_by("year"))
    payload["completed_seasons"] = [season.year for season in seasons]
    if not historical_coverage_is_current(competition, coverage):
        return SportingBasis(
            payload=payload,
            seasons=(),
            by_year={},
            reason="HISTORICAL_COVERAGE_NOT_CURRENT",
        )
    seasons, by_year = calibration.load_competition(competition)
    payload["sporting_basis_hash"] = calibration.sporting_basis_hash(
        competition, seasons, by_year
    )
    reason = ""
    if len(seasons) < 3 or any(not by_year[season.year] for season in seasons):
        reason = "INSUFFICIENT_CALIBRATION_SEASONS"
    return SportingBasis(
        payload=payload,
        seasons=tuple(seasons),
        by_year=by_year,
        reason=reason,
    )


def currentness_for_model(sporting_basis, model_code):
    payload = {
        "model_code": model_code,
        "model_version": calibration.model_version(model_code),
        "strategy": calibration.STRATEGY_VERSION,
        "profile_rule": calibration.PROFILE_RULE_VERSION,
        **sporting_basis.payload,
    }
    return ReadinessCurrentness(
        model_code=model_code,
        identity=config_identity(payload),
        payload=payload,
        reason=sporting_basis.reason,
    )


def currentness_context(competition, model_codes=AUTOMATIC_MODELS):
    """Build one ephemeral basis and derive the requested model identities."""
    sporting_basis = build_sporting_basis(competition)
    return {
        model_code: currentness_for_model(sporting_basis, model_code)
        for model_code in model_codes
    }


def current_basis(competition, model_code):
    """Compatibility boundary for direct callers without operation context."""
    sporting_basis = build_sporting_basis(competition)
    currentness = currentness_for_model(sporting_basis, model_code)
    return (
        currentness.identity,
        currentness.payload,
        list(sporting_basis.seasons),
        sporting_basis.by_year,
        currentness.reason,
    )


def profile_is_current(competition, profile, *, currentness=None):
    if currentness is None:
        currentness = currentness_context(competition, (profile.model_code,))[
            profile.model_code
        ]
    return (
        currentness.model_code == profile.model_code
        and not currentness.reason
        and profile.basis_identity == currentness.identity
    )


def matching_frozen_profile(competition, model, payload):
    return next(
        (
            p
            for p in frozen_profiles()
            if p["competition_id"] == competition.pk
            and p["country"] == str(competition.country)
            and p["competition"] == competition.name
            and p["model_code"] == model
            and p["model_version"] == calibration.model_version(model)
            and p["calibration_strategy_version"] == calibration.STRATEGY_VERSION
            and calibration.PROFILE_RULE_VERSION == "fs012-readiness-v1"
            and p["sporting_basis_hash"] == payload.get("sporting_basis_hash")
        ),
        None,
    )


def _event(
    competition, model, outcome, identity, *, profile=None, reason="", error=None
):
    return emit_event(
        event_code="READINESS_PROFILE_TERMINAL",
        severity=(
            "ERROR" if error else ("WARNING" if outcome == "UNAVAILABLE" else "INFO")
        ),
        component="readiness",
        operation="calibrate_provision",
        outcome=outcome,
        human_summary="Automatic sporting readiness profile reached a classified state.",
        competition_id=competition.pk,
        exception=error,
        context={
            "model": model,
            "profile_version": profile.version if profile else "",
            "calibration_strategy_version": calibration.STRATEGY_VERSION,
            "evidence_identity": identity,
            "selected_config": profile.model_config if profile else {},
            "reason": reason,
            "retry_trigger": "sporting/model/profile basis change; failed execution retries after 7 days",
        },
    )


def _provision_profile(
    competition, model, currentness, sporting_basis, *, calibration_budget
):
    previous = active_profile(competition, model_code=model)
    identity = currentness.identity
    payload = currentness.payload
    seasons = sporting_basis.seasons
    by_year = sporting_basis.by_year
    reason = currentness.reason
    failed_retry_due = (
        previous
        and previous.evidence.get("reason") == "READINESS_CALIBRATION_FAILED"
        and previous.completed_at
        and timezone.now() >= previous.completed_at + timedelta(days=7)
    )
    if previous and previous.basis_identity == identity and not failed_retry_due:
        _event(competition, model, "NO_WORK", identity, profile=previous)
        return {
            "model": model,
            "competition_id": competition.pk,
            "outcome": "NO_WORK",
            "calibrated": False,
        }
    frozen = (
        matching_frozen_profile(competition, model, payload) if not reason else None
    )
    if not reason and not frozen and not calibration_budget.available:
        return {
            "model": model,
            "competition_id": competition.pk,
            "outcome": "DEFERRED",
            "calibrated": False,
        }
    calibrated = False
    error = None
    evidence = {}
    if not reason:
        try:
            if frozen:
                evidence = frozen
            else:
                calibration_budget.record_attempt(competition, model)
                calibrated = True
                result, _ = calibration.run_model_competition(
                    competition, model, seasons, by_year, payload["sporting_basis_hash"]
                )
                evidence = result["profile"]
            if evidence["disposition"] == INSUFFICIENT:
                reason = evidence["rationale"]
        except Exception as caught:
            error = caught
            reason = "READINESS_CALIBRATION_FAILED"
    approved = not reason
    if previous:
        previous.active = False
        previous.save(update_fields=["active", "modified"])
    base_version = evidence.get(
        "proposed_profile_version", f"fs012-{model.lower()}-pending"
    )
    version = (
        base_version
        if frozen and not previous
        else f"{base_version[:55]}-{identity[:16]}"
    )
    profile = ReadinessProfile(
        competition=competition,
        model_code=model,
        version=version,
        model_version=calibration.model_version(model),
        model_config=evidence.get("selected_model_config") or {},
        approved=approved,
        active=True,
        requirements=evidence.get("requirements", {}),
        calibration_strategy_version=calibration.STRATEGY_VERSION,
        profile_rule_version=calibration.PROFILE_RULE_VERSION,
        basis_identity=identity,
        disposition=evidence.get("disposition", INSUFFICIENT),
        evidence={
            "basis": payload,
            "calibration": evidence,
            "reason": reason,
            "source": "FROZEN_PHASE_A" if frozen else "AUTOMATIC_REVALIDATION",
        },
        rationale=evidence.get("rationale", reason),
        completed_at=timezone.now(),
        supersedes=previous,
    )
    # A returned earlier basis creates a new auditable version, not an overwritten row.
    if ReadinessProfile.objects.filter(
        competition=competition, model_code=model, version=version
    ).exists():
        profile.version = f"{version[:60]}-{ReadinessProfile.objects.filter(competition=competition, model_code=model).count()}"
    profile.full_clean()
    profile.save()
    outcome = (
        "FAILED"
        if error
        else ("UNAVAILABLE" if reason else ("UPDATED" if previous else "CREATED"))
    )
    _event(
        competition,
        model,
        outcome,
        identity,
        profile=profile,
        reason=reason,
        error=error,
    )
    return {
        "model": model,
        "competition_id": competition.pk,
        "outcome": outcome,
        "profile_id": profile.pk,
        "reason": reason,
        "calibrated": calibrated,
    }


@transaction.atomic
def provision_profile(competition, model, *, allow_calibration=True):
    """Direct caller boundary; it remains correct without a shared context."""
    competition = Competition.objects.select_for_update().get(pk=competition.pk)
    sporting_basis = build_sporting_basis(competition)
    return _provision_profile(
        competition,
        model,
        currentness_for_model(sporting_basis, model),
        sporting_basis,
        calibration_budget=CalibrationBudget(1 if allow_calibration else 0),
    )


@transaction.atomic
def provision_competition_profiles(competition, *, calibration_budget):
    """Provision both arms from one locked, operation-scoped SportingBasis."""
    competition = Competition.objects.select_for_update().get(pk=competition.pk)
    sporting_basis = build_sporting_basis(competition)
    results = []
    for model in AUTOMATIC_MODELS:
        result = _provision_profile(
            competition,
            model,
            currentness_for_model(sporting_basis, model),
            sporting_basis,
            calibration_budget=calibration_budget,
        )
        results.append(result)
    return results


def run_readiness_maintenance(*, maximum_calibrations=2):
    """Cheap unchanged checks; at most two changed model/competition studies per wake.

    Frozen initial evidence does not consume the full-calibration work budget.
    Expected unavailable basis is audited once and becomes due when evidence changes.
    """
    results = []
    calibration_budget = CalibrationBudget(max(0, maximum_calibrations))
    for competition in Competition.objects.filter(
        enabled=True, competition_type="League", country__gt=""
    ).order_by("pk"):
        attempts_before = len(calibration_budget.attempts)
        try:
            competition_results = provision_competition_profiles(
                competition,
                calibration_budget=calibration_budget,
            )
        except Exception as error:
            attempted_models = {
                model
                for competition_id, model in calibration_budget.attempts[
                    attempts_before:
                ]
                if competition_id == competition.pk
            }
            competition_results = []
            for model in AUTOMATIC_MODELS:
                _event(
                    competition,
                    model,
                    "FAILED",
                    "",
                    error=error,
                    reason="READINESS_LIFECYCLE_FAILED",
                )
                competition_results.append(
                    {
                        "model": model,
                        "competition_id": competition.pk,
                        "outcome": "FAILED",
                        "calibrated": model in attempted_models,
                    }
                )
        for result in competition_results:
            results.append(result)
    return {
        "results": results,
        "full_calibrations": len(calibration_budget.attempts),
    }
