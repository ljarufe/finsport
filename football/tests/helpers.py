from datetime import date

from football.models import (
    Competition,
    CompetitionSourceRef,
    ReconciliationStatus,
    Season,
    Source,
)


def source():
    return Source.objects.get(code="api_football")


def inkabet_source():
    return Source.objects.get(code="inkabet")


def competition(
    external_id=39,
    enabled=True,
    name="Premier League",
    country="EN",
    competition_type="League",
):
    tracked = Competition.objects.create(
        name=name,
        competition_type=competition_type,
        country=country,
        enabled=enabled,
    )
    CompetitionSourceRef.objects.create(
        source=source(),
        competition=tracked,
        external_id=str(external_id),
        external_name=name,
        reconciliation_status=ReconciliationStatus.RESOLVED,
        confidence=1,
    )
    return tracked


def api_competition_ref(tracked):
    return tracked.source_refs.get(source=source())


def catalog_season(tracked, year=2025, coverage=None):
    if coverage is None:
        coverage = {"odds": True}
    return Season.objects.create(
        competition=tracked,
        year=year,
        start_date=date(2025, 8, 15),
        end_date=date(2026, 5, 24),
        is_current=True,
        coverage=coverage,
    )


def league_payload(external_id=39, year=2025):
    return {
        "league": {"id": external_id, "name": "Premier League", "type": "League"},
        "country": {"name": "England", "code": "GB"},
        "seasons": [
            {
                "year": year,
                "start": "2025-08-15",
                "end": "2026-05-24",
                "current": True,
                "coverage": {
                    "fixtures": {
                        "events": True,
                        "lineups": True,
                        "statistics_fixtures": True,
                    },
                    "odds": True,
                },
            }
        ],
    }


def fixture_payload(
    fixture_id=1001,
    league_id=39,
    year=2025,
    status_short="NS",
    status_long="Not Started",
    home_score=None,
    away_score=None,
    home_winner=None,
    away_winner=None,
    kickoff="2025-08-24T20:00:00+00:00",
    provider_timezone="UTC",
    home_name="Home",
    away_name="Away",
):
    return {
        "fixture": {
            "id": fixture_id,
            "date": kickoff,
            "timezone": provider_timezone,
            "status": {"long": status_long, "short": status_short},
        },
        "league": {
            "id": league_id,
            "name": "Premier League",
            "country": "England",
            "season": year,
        },
        "teams": {
            "home": {
                "id": league_id * 100 + 1,
                "name": home_name,
                "winner": home_winner,
            },
            "away": {
                "id": league_id * 100 + 2,
                "name": away_name,
                "winner": away_winner,
            },
        },
        "goals": {"home": home_score, "away": away_score},
        "score": {
            "halftime": {"home": home_score, "away": away_score},
            "fulltime": {"home": home_score, "away": away_score},
            "extratime": {"home": None, "away": None},
            "penalty": {"home": None, "away": None},
        },
    }


def odds_payload(
    fixture_id=1001,
    update="2025-08-24T12:00:00+00:00",
    home="2.10",
):
    return {
        "fixture": {"id": fixture_id},
        "league": {"id": 39, "season": 2025},
        "update": update,
        "bookmakers": [
            {
                "id": 8,
                "name": "Demo Bookmaker",
                "bets": [
                    {
                        "id": 1,
                        "name": "Match Winner",
                        "values": [
                            {"value": "Home", "odd": home},
                            {"value": "Draw", "odd": "3.25"},
                            {"value": "Away", "odd": "3.40"},
                        ],
                    }
                ],
            }
        ],
    }


def inkabet_categories_payload(
    *,
    country_slug="england",
    region_id="11",
    competition_id="3",
    competition_slug="england-premier-league",
    event_id="f-current-match",
    event_slug="home-away",
    event_label="Home - Away",
    kickoff="2025-08-24T20:00:00+00:00",
    event_type="Match",
):
    competition_path = f"futbol/{country_slug}/{competition_slug}"
    event_path = f"{competition_path}/{event_slug}"
    return {
        "data": {
            "items": {
                "indexBySlug": {
                    "futbol": ["1"],
                    f"futbol/{country_slug}": ["1", region_id],
                    competition_path: ["1", region_id, competition_id],
                    event_path: ["1", region_id, competition_id, event_id],
                },
                "byId": {
                    event_id: {
                        "id": event_id,
                        "label": event_label,
                        "startDate": kickoff,
                        "eventType": event_type,
                        "homeTeam": {"name": "Home"},
                        "awayTeam": {"name": "Away"},
                    }
                },
            }
        }
    }


def inkabet_mw3w_payload(home="1.80", draw="3.40", away="4.20"):
    return {
        "data": {
            "accordions": {
                "MW3W": {
                    "markets": [
                        {
                            "marketTemplateId": "MW3W",
                            "marketFriendlyName": "Ganador del partido",
                            "status": "Open",
                        }
                    ],
                    "selections": [
                        {
                            "selectionTemplateId": "HOME",
                            "participantId": "home-inkabet",
                            "participantLabel": "Home",
                            "odds": home,
                        },
                        {
                            "selectionTemplateId": "DRAW",
                            "participantLabel": "Empate",
                            "odds": draw,
                        },
                        {
                            "selectionTemplateId": "AWAY",
                            "participantId": "away-inkabet",
                            "participantLabel": "Away",
                            "odds": away,
                        },
                    ],
                }
            }
        }
    }
