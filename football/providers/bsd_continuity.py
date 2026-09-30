"""Bounded incremental BSD identity and shadow observation after API-F capture."""

from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Exists, OuterRef
from django.utils import timezone

from football.models import (
    BSDTeamMapping,
    Match,
    ProviderCallAudit,
    ResultProviderObservation,
)
from football.result_provider import TERMINAL, normalize_bsd, record
from football.result_routing import _failure, _ready, _success, maybe_promote_shadow

from .bsd import BSDClient, BSDError
from .bsd_bootstrap import _page
from .bsd_identity import bind_event

LIMA = ZoneInfo("America/Lima")
ACTIVE = ("BSD_BOOTSTRAP_PENDING", "BSD_SHADOW_VALIDATION", "BSD_PRIMARY_VALIDATED")
RETRYABLE_CIRCUIT = ("BSD_BACKOFF", "BSD_TASTER_EXHAUSTED")


def _continuity_state(route, at):
    if route.bsd_state in ACTIVE:
        return route.bsd_state
    if (
        route.bsd_state == "BSD_BACKOFF"
        and route.bsd_backoff_until is not None
        and at >= route.bsd_backoff_until
    ):
        prior = route.provenance.get("bsd_previous_state")
        return prior if prior in ACTIVE else None
    return None


def _attempted(prefix, *, route, at):
    last = (
        ProviderCallAudit.objects.filter(
            provider="BSD", logical_identity__startswith=prefix
        )
        .order_by("-id")
        .first()
    )
    return bool(
        last
        and not (
            route.bsd_state == "BSD_BACKOFF"
            and _continuity_state(route, at)
            and last.outcome in RETRYABLE_CIRCUIT
        )
    )


def _incremental_bind(*, at, client_factory):
    """At most one mapped route/date group and its two league IDs per wake."""
    matches = list(
        Match.objects.filter(
            kickoff__gt=at,
            kickoff__lte=at + timedelta(days=14),
            bsd_event__isnull=True,
            season__competition__result_route__bsd_state__in=(*ACTIVE, "BSD_BACKOFF"),
        )
        .select_related("season__competition__result_route")
        .order_by("kickoff", "pk")[:256]
    )
    today = at.astimezone(LIMA).date().isoformat()
    for first in matches:
        route = first.season.competition.result_route
        if _continuity_state(route, at) is None:
            continue
        day = first.kickoff.astimezone(UTC).date()
        batch = [
            match
            for match in matches
            if match.season.competition_id == route.competition_id
            and match.kickoff.astimezone(UTC).date() == day
        ]
        mappings = set(
            BSDTeamMapping.objects.filter(
                route=route,
                approval__in=("EXACT_UNIQUE", "HUMAN_APPROVED"),
            ).values_list("canonical_team_id", "bsd_league_id")
        )
        leagues = [
            league_id
            for league_id in route.bsd_league_ids
            if route.provenance.get("bsd_season_ids", {}).get(str(league_id))
            and any(
                (match.home_team_id, league_id) in mappings
                and (match.away_team_id, league_id) in mappings
                for match in batch
            )
        ]
        if not leagues:
            continue
        prefix = f"bsd:incremental:{route.pk}:{day}:{today}:"
        if _attempted(prefix, route=route, at=at):
            continue
        client = client_factory()
        events = []
        errors = []
        for league_id in leagues[:2]:
            season_id = route.provenance["bsd_season_ids"][str(league_id)]
            try:
                events.extend(
                    _page(
                        client,
                        "events/",
                        {
                            "league_id": league_id,
                            "season_id": season_id,
                            "date_from": day.isoformat(),
                            "date_to": (day + timedelta(days=1)).isoformat(),
                            "limit": 200,
                            "offset": 0,
                        },
                        f"{prefix}{league_id}",
                    )
                )
            except (BSDError, ValueError) as error:
                failure = (
                    error
                    if isinstance(error, BSDError)
                    else BSDError("RESULT_PROVIDER_MALFORMED")
                )
                _failure(route, failure, at)
                errors.append(failure.state)
                break
        if errors:
            return {"identity_calls": 1, "bindings": 0, "errors": errors}
        _success(route)
        bound = sum(bind_event(match, route, events) == "BOUND" for match in batch)
        if bound and route.bsd_state == "BSD_BOOTSTRAP_PENDING":
            upcoming = Match.objects.filter(
                season__competition_id=route.competition_id,
                kickoff__gte=at,
                kickoff__lte=at + timedelta(days=14),
            ).values_list("home_team_id", "away_team_id")
            participants = {team_id for pair in upcoming for team_id in pair}
            mapped = set(
                BSDTeamMapping.objects.filter(
                    route=route,
                    approval__in=("EXACT_UNIQUE", "HUMAN_APPROVED"),
                ).values_list("canonical_team_id", flat=True)
            )
            if participants <= mapped:
                route.bsd_state = "BSD_SHADOW_VALIDATION"
                route.save(update_fields=["bsd_state"])
        return {"identity_calls": len(leagues[:2]), "bindings": bound, "errors": []}
    return {"identity_calls": 0, "bindings": 0, "errors": []}


def _shadow_results(*, at, client_factory):
    """At most four terminal candidates per wake; one physical detail per match/day."""
    terminal = ResultProviderObservation.objects.filter(
        match_id=OuterRef("pk"),
        provider="BSD",
        status_short__in=TERMINAL,
    )
    matches = list(
        Match.objects.filter(
            bsd_event__isnull=False,
            season__competition__result_route__bsd_state__in=(
                "BSD_SHADOW_VALIDATION",
                "BSD_BACKOFF",
            ),
            kickoff__lte=at - timedelta(minutes=130),
            kickoff__gte=at - timedelta(days=7),
        )
        .annotate(bsd_terminal=Exists(terminal))
        .filter(bsd_terminal=False)
        .select_related("season__competition__result_route", "bsd_event")
        .order_by("kickoff", "pk")[:256]
    )
    today = at.astimezone(LIMA).date().isoformat()
    attempted_today = dict(
        ProviderCallAudit.objects.filter(
            provider="BSD",
            logical_identity__startswith="bsd:shadow:",
            logical_identity__endswith=f":{today}",
        )
        .order_by("id")
        .values_list("logical_identity", "outcome")
    )
    calls = observed = 0
    errors = []
    client = None
    for match in matches:
        if calls >= 4:
            break
        route = match.season.competition.result_route
        if (
            not _ready(route, at)
            or _continuity_state(route, at) != "BSD_SHADOW_VALIDATION"
        ):
            continue
        binding = match.bsd_event
        identity = f"bsd:shadow:{match.pk}:{binding.bsd_event_id}:{today}"
        if identity in attempted_today and not (
            route.bsd_state == "BSD_BACKOFF"
            and attempted_today[identity] in RETRYABLE_CIRCUIT
        ):
            continue
        client = client or client_factory()
        try:
            payload = client.get(
                f"events/{binding.bsd_event_id}/",
                logical_identity=identity,
                match_id=match.pk,
            )
            calls += 1
            result = normalize_bsd(match, binding, payload, observed_at=timezone.now())
            if result.status in TERMINAL:
                _, disposition = record(match, result, authoritative=False)
                observed += 1
                if disposition == "RESULT_CONFLICT":
                    errors.append(f"RESULT_CONFLICT:{match.pk}")
            _success(route)
        except BSDError as error:
            calls += 1
            _failure(route, error, at)
            errors.append(f"{error.state}:{match.pk}")
    if observed:
        maybe_promote_shadow()
    return {"shadow_calls": calls, "shadow_observations": observed, "errors": errors}


def run_bsd_continuity(*, at=None, client_factory=BSDClient):
    """BSD-only bounded work; never delays the preceding API-F capture."""
    if not settings.BSD_API_TOKEN:
        return {
            "status": "BSD_NOT_CONFIGURED",
            "identity_calls": 0,
            "shadow_calls": 0,
            "errors": [],
        }
    at = at or timezone.now()
    identity = _incremental_bind(at=at, client_factory=client_factory)
    shadow = _shadow_results(at=at, client_factory=client_factory)
    return {
        "status": "DEGRADED" if identity["errors"] or shadow["errors"] else "OK",
        **identity,
        **shadow,
        "errors": identity["errors"] + shadow["errors"],
    }
