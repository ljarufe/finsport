"""Bounded identity bootstrap; operational execution is explicit, never scheduled."""

from datetime import UTC, timedelta
from urllib.parse import parse_qs, urlsplit

from django.utils import timezone

from football.models import BSDTeamMapping, CompetitionResultRoute, Match, Team

from .bsd_identity import bind_event, exact_unique_team_pairs


def _page(client, endpoint, params, identity):
    """Follow advertised pages with a hard bound and endpoint identity check."""
    rows = []
    current = dict(params)
    seen = set()
    for page in range(5):
        offset = int(current["offset"])
        if offset in seen:
            raise ValueError("BSD_BOOTSTRAP_PAGINATION_LOOP")
        seen.add(offset)
        data = client.get(
            endpoint,
            params=current,
            logical_identity=f"{identity}:offset:{offset}",
        )
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ValueError("BSD_BOOTSTRAP_MALFORMED_PAGE")
        rows.extend(data["results"])
        next_page = data.get("next")
        if not next_page:
            return rows
        parsed = urlsplit(str(next_page))
        if parsed.path.rstrip("/").split("/")[-1] != endpoint.rstrip("/"):
            raise ValueError("BSD_BOOTSTRAP_PAGINATION_ENDPOINT_MISMATCH")
        query = parse_qs(parsed.query)
        if not {"offset", "limit"} <= query.keys():
            raise ValueError("BSD_BOOTSTRAP_PAGINATION_MALFORMED_NEXT")
        try:
            next_offset = int(query["offset"][0])
            next_limit = int(query["limit"][0])
        except (TypeError, ValueError, IndexError) as error:
            raise ValueError("BSD_BOOTSTRAP_PAGINATION_MALFORMED_NEXT") from error
        if next_offset <= offset or next_limit != 200:
            raise ValueError("BSD_BOOTSTRAP_PAGINATION_MALFORMED_NEXT")
        current = {**params, "offset": next_offset}
    raise ValueError("BSD_BOOTSTRAP_PAGINATION_BOUND_EXCEEDED")


def bootstrap(*, client, at=None):
    at = at or timezone.now()
    utc_date = at.astimezone(UTC).date()
    routes = list(
        CompetitionResultRoute.objects.filter(bsd_league_ids__isnull=False)
        .select_related("competition")
        .order_by("competition_id")
    )
    routes = [route for route in routes if route.bsd_league_ids]
    if len(routes) != 23 or sum(len(route.bsd_league_ids) for route in routes) != 24:
        raise ValueError("BSD_FROZEN_TOPOLOGY_MISMATCH")
    catalog = _page(client, "leagues/", {"limit": 200, "offset": 0}, "bsd:catalog:v1")
    by_id = {row["id"]: row for row in catalog}
    needed = {league_id for route in routes for league_id in route.bsd_league_ids}
    if not needed <= by_id.keys():
        raise ValueError("BSD_MAPPED_LEAGUE_ABSENT_FROM_CATALOG")
    results = []
    for route in routes:
        season_ids = {}
        bound = 0
        exact = 0
        for league_id in route.bsd_league_ids:
            season_id = (by_id[league_id].get("current_season") or {}).get("id")
            if not isinstance(season_id, int):
                results.append(
                    {
                        "competition_id": route.competition_id,
                        "league_id": league_id,
                        "state": "TEMPORARILY_UNAVAILABLE",
                    }
                )
                continue
            season_ids[str(league_id)] = season_id
            teams = _page(
                client,
                "teams/",
                {
                    "league_id": league_id,
                    "season_id": season_id,
                    "in_competition": "true",
                    "limit": 200,
                    "offset": 0,
                },
                f"bsd:teams:{league_id}:{season_id}",
            )
            pairs = exact_unique_team_pairs(
                Team.objects.filter(competition=route.competition), teams
            )
            for local, provider in pairs:
                _, created = BSDTeamMapping.objects.get_or_create(
                    route=route,
                    canonical_team=local,
                    bsd_league_id=league_id,
                    defaults=dict(
                        bsd_team_id=provider["id"],
                        approval="EXACT_UNIQUE",
                        provenance={
                            "normalization": "FS023_UNICODE_CASE_WHITESPACE_PUNCTUATION_V1",
                            "provider_name": provider["name"],
                        },
                    ),
                )
                exact += int(created)
            events = _page(
                client,
                "events/",
                {
                    "league_id": league_id,
                    "season_id": season_id,
                    "date_from": utc_date.isoformat(),
                    "date_to": (utc_date + timedelta(days=14)).isoformat(),
                    "limit": 200,
                    "offset": 0,
                },
                f"bsd:events:{league_id}:{season_id}:{at.date()}",
            )
            for match in Match.objects.filter(
                season__competition=route.competition,
                kickoff__gte=at - timedelta(minutes=15),
                kickoff__lte=at + timedelta(days=14, minutes=15),
            ).select_related("season"):
                bound += int(bind_event(match, route, events) == "BOUND")
        upcoming = list(
            Match.objects.filter(
                season__competition=route.competition,
                kickoff__gte=at - timedelta(minutes=15),
                kickoff__lte=at + timedelta(days=14, minutes=15),
            ).values_list("home_team_id", "away_team_id")
        )
        participant_ids = {team_id for pair in upcoming for team_id in pair}
        mapped_ids = set(
            BSDTeamMapping.objects.filter(
                route=route,
                bsd_league_id__in=route.bsd_league_ids,
                approval__in=("EXACT_UNIQUE", "HUMAN_APPROVED"),
            ).values_list("canonical_team_id", flat=True)
        )
        identity_ready = bool(season_ids and bound and participant_ids <= mapped_ids)
        route.provenance = {
            **route.provenance,
            "bsd_season_ids": season_ids,
            "bootstrap_at": at.isoformat(),
            "participant_count": len(participant_ids),
            "mapped_participant_count": len(participant_ids & mapped_ids),
            "events_bound": bound,
        }
        if route.bsd_state not in {
            "BSD_AUTH_FAILED",
            "BSD_ENTITLEMENT_FAILED",
            "BSD_DEGRADED",
        }:
            route.bsd_state = (
                route.bsd_state
                if identity_ready and route.bsd_state == "BSD_PRIMARY_VALIDATED"
                else (
                    "BSD_SHADOW_VALIDATION"
                    if identity_ready
                    else "BSD_BOOTSTRAP_PENDING"
                )
            )
        route.save(update_fields=["bsd_state", "provenance"])
        results.append(
            {
                "competition_id": route.competition_id,
                "state": route.bsd_state,
                "exact_teams_new": exact,
                "events_bound": bound,
            }
        )
    return results
