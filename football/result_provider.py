"""One result observation boundary feeding the existing canonical settlement engine."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from football.models import (
    BSDTeamMapping,
    Match,
    ResultProviderObservation,
)
from football.providers.bsd import BSDError

TERMINAL = {"FT", "ET", "P", "AET", "PEN", "CANC", "ABD", "AWD", "WO"}


@dataclass(frozen=True)
class Result:
    provider: str
    external_ref: str
    status: str
    home: int | None
    away: int | None
    outcome: str
    observed_at: datetime
    provenance: dict


def _outcome(home, away):
    return "HOME" if home > away else "AWAY" if away > home else "DRAW"


def normalize_bsd(match, binding, payload, *, observed_at=None):
    if not isinstance(payload, dict) or payload.get("id") != binding.bsd_event_id:
        raise BSDError("RESULT_PROVIDER_MALFORMED")
    if payload.get("league_id") != binding.bsd_league_id:
        raise BSDError("BSD_IDENTITY_UNRESOLVED")
    mapped = {
        row.canonical_team_id: row.bsd_team_id
        for row in BSDTeamMapping.objects.filter(
            route__competition_id=match.season.competition_id,
            bsd_league_id=binding.bsd_league_id,
            approval__in=("EXACT_UNIQUE", "HUMAN_APPROVED"),
        )
    }
    if (mapped.get(match.home_team_id), mapped.get(match.away_team_id)) != (
        payload.get("home_team_id"),
        payload.get("away_team_id"),
    ):
        raise BSDError("BSD_IDENTITY_UNRESOLVED")
    try:
        kickoff = datetime.fromisoformat(payload["event_date"].replace("Z", "+00:00"))
    except (KeyError, ValueError, TypeError) as error:
        raise BSDError("RESULT_PROVIDER_MALFORMED") from error
    if abs((kickoff - match.kickoff).total_seconds()) > 15 * 60:
        raise BSDError("BSD_IDENTITY_UNRESOLVED")
    status = str(payload.get("status", "")).casefold()
    if status == "finished":
        home, away = payload.get("home_score"), payload.get("away_score")
        if not all(isinstance(value, int) and value >= 0 for value in (home, away)):
            raise BSDError("RESULT_PROVIDER_MALFORMED")
        canonical, outcome = "FT", _outcome(home, away)
    elif status in {"cancelled", "canceled", "abandoned"}:
        canonical = "ABD" if status == "abandoned" else "CANC"
        home = away = None
        outcome = ""
    elif status == "postponed":
        canonical, home, away, outcome = "PST", None, None, ""
    elif status in {"awarded", "walkover"}:
        canonical = "AWD" if status == "awarded" else "WO"
        explicit = payload.get("outcome")
        if explicit not in {"HOME", "DRAW", "AWAY"} or not payload.get("award_reason"):
            canonical, home, away, outcome = "UNRESOLVED_AWARD", None, None, ""
        else:
            home, away, outcome = (
                payload.get("home_score"),
                payload.get("away_score"),
                explicit,
            )
    else:
        canonical, home, away, outcome = "NONTERMINAL", None, None, ""
    return Result(
        "BSD",
        str(binding.bsd_event_id),
        canonical,
        home,
        away,
        outcome,
        observed_at or timezone.now(),
        {
            "bsd_league_id": binding.bsd_league_id,
            "bsd_event_id": binding.bsd_event_id,
            "raw_status": status,
            "score_scope": "REGULATION_90_PLUS_STOPPAGE",
        },
    )


def api_football_result(match, external_ref, *, provenance=None):
    """Normalize canonical API-F regulation scores without using ET/penalty totals."""
    home, away = match.fulltime_home_score, match.fulltime_away_score
    if (home is None or away is None) and match.status_short == "FT":
        home, away = match.home_score, match.away_score
    if home is None or away is None:
        home = away = None
    outcome = match.outcome if home is not None and away is not None else ""
    if match.status_short in {"CANC", "ABD"}:
        home = away = None
        outcome = ""
    return Result(
        "API_FOOTBALL",
        str(external_ref),
        match.status_short,
        home,
        away,
        outcome,
        match.observed_at,
        {**(provenance or {}), "score_scope": "REGULATION_90_PLUS_STOPPAGE"},
    )


def _different(left, right):
    return (
        left.status_short != right.status
        or left.outcome != right.outcome
        or left.home_regulation != right.home
        or left.away_regulation != right.away
    )


def _feed_lag_converged(result, previous_same, first_bsd, counterpart, discrepancy):
    """A nonauthoritative first BSD report may converge on API-F after 30m.

    Do not treat revision of already-authoritative/settled BSD truth as feed lag.
    """
    return bool(
        result.provider == "BSD"
        and previous_same is not None
        and first_bsd is not None
        and previous_same.pk == first_bsd.pk
        and not previous_same.authoritative
        and not previous_same.conflict
        and first_bsd.provenance.get("pending_conflict")
        and counterpart is not None
        and not discrepancy
        and result.observed_at >= first_bsd.provider_observed_at + timedelta(minutes=30)
    )


@transaction.atomic
def record(match, result, *, authoritative=False, fallback_reason=""):
    match = Match.objects.select_for_update().get(pk=match.pk)
    other_provider = "API_FOOTBALL" if result.provider == "BSD" else "BSD"
    counterpart = (
        ResultProviderObservation.objects.filter(
            match=match,
            provider=other_provider,
            status_short__in=TERMINAL,
        )
        .order_by("-provider_observed_at", "-id")
        .first()
    )
    discrepancy = bool(
        result.status in TERMINAL and counterpart and _different(counterpart, result)
    )
    previous_same = (
        ResultProviderObservation.objects.filter(
            match=match,
            provider=result.provider,
            status_short__in=TERMINAL,
        )
        .order_by("-provider_observed_at", "-id")
        .first()
    )
    same_provider_revision = bool(
        result.status in TERMINAL
        and previous_same
        and _different(previous_same, result)
    )
    first_bsd = (
        ResultProviderObservation.objects.filter(
            match=match,
            provider="BSD",
            status_short__in=TERMINAL,
        )
        .order_by("provider_observed_at", "id")
        .first()
    )
    confirmed = bool(
        discrepancy
        and result.provider == "BSD"
        and first_bsd
        and result.observed_at >= first_bsd.provider_observed_at + timedelta(minutes=30)
    )
    feed_lag_converged = same_provider_revision and _feed_lag_converged(
        result, previous_same, first_bsd, counterpart, discrepancy
    )
    observation, created = ResultProviderObservation.objects.get_or_create(
        match=match,
        provider=result.provider,
        external_ref=result.external_ref,
        provider_observed_at=result.observed_at,
        defaults=dict(
            result_known_at=timezone.now(),
            status_short=result.status,
            home_regulation=result.home,
            away_regulation=result.away,
            outcome=result.outcome,
            authoritative=authoritative
            and not discrepancy
            and not same_provider_revision,
            conflict=confirmed or (same_provider_revision and not feed_lag_converged),
            fallback_reason=fallback_reason,
            provenance={
                **result.provenance,
                "pending_conflict": discrepancy and not confirmed,
                "same_provider_revision": same_provider_revision,
                **(
                    {"conflict_resolution": "FEED_LAG_CONVERGED"}
                    if feed_lag_converged
                    else {}
                ),
            },
        ),
    )
    if same_provider_revision and not feed_lag_converged:
        if not observation.conflict:
            observation.conflict = True
            observation.authoritative = False
            observation.provenance = {
                **observation.provenance,
                "same_provider_revision": True,
            }
            observation.save(update_fields=["conflict", "authoritative", "provenance"])
        return observation, "RESULT_CONFLICT"
    if discrepancy and result.provider == "API_FOOTBALL" and first_bsd:
        first_bsd.provenance = {**first_bsd.provenance, "pending_conflict": True}
        first_bsd.save(update_fields=["provenance"])
    if confirmed:
        if not observation.conflict:
            observation.conflict = True
            observation.provenance = {
                **observation.provenance,
                "pending_conflict": False,
            }
            observation.save(update_fields=["conflict", "provenance"])
        return observation, "RESULT_CONFLICT"
    if discrepancy:
        return observation, "PENDING_CONFLICT"
    if (
        first_bsd
        and result.provider == "BSD"
        and first_bsd.provenance.get("pending_conflict")
    ):
        first_bsd.provenance = {
            **first_bsd.provenance,
            "pending_conflict": False,
            "conflict_resolution": "FEED_LAG_CONVERGED",
        }
        first_bsd.save(update_fields=["provenance"])
    if authoritative and result.status in TERMINAL:
        canonical_home = match.fulltime_home_score
        canonical_away = match.fulltime_away_score
        if match.status_short == "FT" and (
            canonical_home is None or canonical_away is None
        ):
            canonical_home, canonical_away = match.home_score, match.away_score
        if match.status_short in TERMINAL and (
            match.outcome != result.outcome
            or canonical_home != result.home
            or canonical_away != result.away
        ):
            observation.conflict = True
            observation.authoritative = False
            observation.save(update_fields=["conflict", "authoritative"])
            return observation, "RESULT_CONFLICT"
        if match.status_short not in TERMINAL:
            match.status_short = result.status
            match.outcome = result.outcome
            match.fulltime_home_score = result.home
            match.fulltime_away_score = result.away
            fields = [
                "status_short",
                "outcome",
                "fulltime_home_score",
                "fulltime_away_score",
                "observed_at",
                "modified",
            ]
            if result.status == "FT":
                match.home_score = result.home
                match.away_score = result.away
                fields.extend(["home_score", "away_score"])
            match.observed_at = result.observed_at
            match.save(update_fields=fields)
        elif (
            result.status == "FT"
            and match.status_short == "FT"
            and (match.home_score is None or match.away_score is None)
        ):
            # Repair a prior BSD terminal write only after an identical
            # independently observed regulation result.
            match.home_score = result.home
            match.away_score = result.away
            match.save(update_fields=["home_score", "away_score", "modified"])
    return observation, "RECORDED" if created else "ALREADY_RECORDED"


def shadow_gate():
    """Comparable terminal results, distinct dates, exact scores, and conflicts."""
    from collections import defaultdict

    paired = defaultdict(dict)
    for row in (
        ResultProviderObservation.objects.filter(status_short="FT")
        .select_related("match__season")
        .order_by("provider_observed_at", "id")
    ):
        paired[row.match_id][row.provider] = row
    comparable = [
        rows
        for rows in paired.values()
        if {"BSD", "API_FOOTBALL"} <= rows.keys()
        and all(
            rows[provider].home_regulation is not None
            and rows[provider].away_regulation is not None
            for provider in ("BSD", "API_FOOTBALL")
        )
    ]
    competitions = {rows["BSD"].match.season.competition_id for rows in comparable}
    dates = {
        rows["BSD"].match.kickoff.astimezone(ZoneInfo("America/Lima")).date()
        for rows in comparable
    }
    outcome_agreements = sum(
        rows["BSD"].outcome == rows["API_FOOTBALL"].outcome for rows in comparable
    )
    score_agreements = sum(
        (rows["BSD"].home_regulation, rows["BSD"].away_regulation)
        == (rows["API_FOOTBALL"].home_regulation, rows["API_FOOTBALL"].away_regulation)
        for rows in comparable
    )
    confirmed = (
        ResultProviderObservation.objects.filter(
            conflict=True,
            match__season__competition__result_route__bsd_league_ids__isnull=False,
        )
        .exclude(match__season__competition__result_route__bsd_league_ids=[])
        .count()
    )
    disagreements = sum(
        rows["BSD"].outcome != rows["API_FOOTBALL"].outcome
        or (rows["BSD"].home_regulation, rows["BSD"].away_regulation)
        != (rows["API_FOOTBALL"].home_regulation, rows["API_FOOTBALL"].away_regulation)
        for rows in comparable
    )
    passed = (
        len(comparable) >= 30
        and len(competitions) >= 5
        and len(dates) >= 7
        and not disagreements
        and not confirmed
    )
    status = (
        "FAIL"
        if confirmed
        else "PASS" if passed else "NO_SAMPLE" if not comparable else "PENDING"
    )
    return {
        "status": status,
        "matches": len(comparable),
        "competitions": len(competitions),
        "lima_dates": len(dates),
        "outcome_agreements": outcome_agreements,
        "regulation_score_agreements": score_agreements,
        "disagreements": disagreements,
        "confirmed_conflicts": confirmed,
        "conflicts": disagreements,
    }


def sentinel_phase(gate=None):
    gate = shadow_gate() if gate is None else gate
    return (
        "STEADY"
        if gate["matches"] >= 100
        and gate["competitions"] >= 10
        and gate["confirmed_conflicts"] == 0
        else "PROBATION"
    )
