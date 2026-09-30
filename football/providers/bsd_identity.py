"""Deterministic BSD identities; non-exact names never authorize settlement."""

import unicodedata
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from football.models import BSDEventBinding, BSDTeamMapping


def normalized_name(value):
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = "".join(
        (
            char
            if char.isalnum() or char.isspace()
            else " " if unicodedata.category(char).startswith("P") else ""
        )
        for char in text
    )
    return " ".join(text.split())


def exact_unique_team_pairs(local_teams, provider_teams):
    locals_by_name = {}
    bsd_by_name = {}
    for team in local_teams:
        locals_by_name.setdefault(normalized_name(team.name), []).append(team)
    for team in provider_teams:
        bsd_by_name.setdefault(normalized_name(team["name"]), []).append(team)
    return [
        (locals_[0], bsd_by_name[name][0])
        for name, locals_ in locals_by_name.items()
        if name and len(locals_) == 1 and len(bsd_by_name.get(name, ())) == 1
    ]


def event_candidates(match, events, league_ids, mapped_home, mapped_away):
    result = []
    for event in events:
        if event.get("league_id") not in league_ids or (
            event.get("home_team_id"),
            event.get("away_team_id"),
        ) != (mapped_home, mapped_away):
            continue
        try:
            kickoff = datetime.fromisoformat(event["event_date"].replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError):
            continue
        if abs((kickoff - match.kickoff).total_seconds()) <= 900:
            result.append(event)
    return result


@transaction.atomic
def bind_event(match, route, events):
    if not route.bsd_league_ids:
        return "API_FOOTBALL_ONLY"
    mapped = {
        (row.canonical_team_id, row.bsd_league_id): row.bsd_team_id
        for row in BSDTeamMapping.objects.filter(
            route=route, approval__in=("EXACT_UNIQUE", "HUMAN_APPROVED")
        )
    }
    candidates = []
    for league_id in route.bsd_league_ids:
        home = mapped.get((match.home_team_id, league_id))
        away = mapped.get((match.away_team_id, league_id))
        if home is not None and away is not None:
            candidates.extend(event_candidates(match, events, [league_id], home, away))
    if not candidates:
        return "BSD_IDENTITY_UNRESOLVED"
    if len(candidates) != 1:
        return "BSD_IDENTITY_AMBIGUOUS"
    event = candidates[0]
    binding, created = BSDEventBinding.objects.get_or_create(
        match=match,
        defaults=dict(
            bsd_league_id=event["league_id"],
            bsd_event_id=event["id"],
            provenance={"rule": "EXACT_TEAMS_KICKOFF_PLUS_MINUS_15M"},
        ),
    )
    if not created and (binding.bsd_event_id, binding.bsd_league_id) != (
        event["id"],
        event["league_id"],
    ):
        return "BSD_IDENTITY_AMBIGUOUS"
    return "BOUND"


def approve_nonexact_team(
    *,
    route,
    canonical_team,
    bsd_team_id,
    bsd_league_id,
    provider_name,
    approved_by,
    approved_alias,
):
    if not approved_by or not approved_alias:
        raise ValueError("BSD_HUMAN_APPROVAL_PROVENANCE_REQUIRED")
    if (
        canonical_team.competition_id != route.competition_id
        or bsd_league_id not in route.bsd_league_ids
    ):
        raise ValueError("BSD_TEAM_ROUTE_MISMATCH")
    return BSDTeamMapping.objects.create(
        route=route,
        canonical_team=canonical_team,
        bsd_team_id=bsd_team_id,
        bsd_league_id=bsd_league_id,
        approval="HUMAN_APPROVED",
        provenance={
            "provider_name": provider_name,
            "approved_alias": approved_alias,
            "approved_by": approved_by,
            "approved_at": timezone.now().isoformat(),
            "version": "FS023_EXPLICIT_TEAM_MAPPING_V1",
        },
    )


def rebind_stale_event(match, route, binding, *, client, at):
    """One bounded exact collection lookup after a bound event returns 404."""
    from datetime import UTC, timedelta

    from .bsd_bootstrap import _page

    binding.provenance = {
        **binding.provenance,
        "state": "STALE_404",
        "stale_event_id": binding.bsd_event_id,
        "stale_at": at.isoformat(),
    }
    binding.save(update_fields=["provenance"])
    mapped = {
        (row.canonical_team_id, row.bsd_league_id): row.bsd_team_id
        for row in BSDTeamMapping.objects.filter(
            route=route, approval__in=("EXACT_UNIQUE", "HUMAN_APPROVED")
        )
    }
    candidates = []
    for league_id in route.bsd_league_ids:
        season_id = route.provenance.get("bsd_season_ids", {}).get(str(league_id))
        home = mapped.get((match.home_team_id, league_id))
        away = mapped.get((match.away_team_id, league_id))
        if season_id is None or home is None or away is None:
            continue
        earliest = (match.kickoff - timedelta(minutes=15)).astimezone(UTC).date()
        latest = (match.kickoff + timedelta(minutes=15)).astimezone(UTC).date()
        events = _page(
            client,
            "events/",
            {
                "league_id": league_id,
                "season_id": season_id,
                "date_from": earliest.isoformat(),
                "date_to": (latest + timedelta(days=1)).isoformat(),
                "limit": 200,
                "offset": 0,
            },
            f"bsd:rebind:{match.pk}:{league_id}:{at.isoformat()}",
        )
        candidates.extend(event_candidates(match, events, [league_id], home, away))
    if len(candidates) != 1 or candidates[0]["id"] == binding.bsd_event_id:
        return "BSD_IDENTITY_UNRESOLVED" if not candidates else "BSD_IDENTITY_AMBIGUOUS"
    event = candidates[0]
    binding.bsd_event_id = event["id"]
    binding.bsd_league_id = event["league_id"]
    binding.bound_at = at
    binding.provenance = {
        **binding.provenance,
        "state": "BOUND_REPLACEMENT",
        "replacement_event_id": event["id"],
    }
    binding.save(
        update_fields=["bsd_event_id", "bsd_league_id", "bound_at", "provenance"]
    )
    return "BOUND"
