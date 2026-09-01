from io import StringIO
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from football.api_football import APIFootballQuotaReserveError
from football.api_inkabet import InkabetResponseError
from football.management.commands.sync_football_catalog import (
    Command as CatalogCommand,
)
from football.management.commands.sync_football_day import Command as DayCommand
from football.management.commands.sync_football_season import Command as SeasonCommand
from football.models import (
    CompetitionSourceRef,
    Match,
    OddsObservation,
    OddsSnapshot,
    Season,
    Team,
)
from football.sync import sync_catalog_payloads

from .helpers import (
    api_competition_ref,
    catalog_season,
    competition,
    fixture_payload,
    inkabet_categories_payload,
    inkabet_mw3w_payload,
    league_payload,
    odds_payload,
)

pytestmark = pytest.mark.django_db


class FakeClient:
    instances = []
    responses = {}

    def __init__(self):
        self.calls = 0
        self.daily_remaining = 77
        self.requests = []
        self.__class__.instances.append(self)

    def get_all(self, endpoint, params=None):
        self.calls += 1
        self.requests.append((endpoint, params or {}))
        response = self.__class__.responses[endpoint]
        return response(params or {}) if callable(response) else response


class FakeInkabetClient:
    instances = []
    categories_payload = {}
    mw3w_payload = {}
    categories_error = None
    mw3w_error = None

    def __init__(self):
        self.calls = 0
        self.requests = []
        self.__class__.instances.append(self)

    def categories(self):
        self.calls += 1
        self.requests.append(("categories", {}))
        if self.__class__.categories_error is not None:
            raise self.__class__.categories_error
        return self.__class__.categories_payload

    def match_winner(self, event_id):
        self.calls += 1
        self.requests.append(("mw3w", {"eventId": event_id}))
        if self.__class__.mw3w_error is not None:
            raise self.__class__.mw3w_error
        return self.__class__.mw3w_payload


@pytest.fixture(autouse=True)
def reset_fake_clients():
    FakeClient.instances = []
    FakeClient.responses = {}
    FakeInkabetClient.instances = []
    FakeInkabetClient.categories_payload = {}
    FakeInkabetClient.mw3w_payload = {}
    FakeInkabetClient.categories_error = None
    FakeInkabetClient.mw3w_error = None


def test_catalog_command_creates_idempotent_canonical_catalog_and_api_refs():
    FakeClient.responses = {
        "leagues": [league_payload()],
        "odds/bets": [{"id": 1, "name": "Match Winner"}],
    }
    output = StringIO()
    with mock.patch.object(CatalogCommand, "client_class", FakeClient):
        call_command("sync_football_catalog", stdout=output)
        call_command("sync_football_catalog", stdout=output)

    ref = CompetitionSourceRef.objects.get(external_id="39")
    tracked = ref.competition
    season = Season.objects.get(competition=tracked, year=2025)
    assert tracked.enabled is False
    assert season.start_date.isoformat() == "2025-08-15"
    assert len(FakeClient.instances) == 2
    assert all(
        instance.requests == [("leagues", {}), ("odds/bets", {})]
        for instance in FakeClient.instances
    )
    assert "calls=2" in output.getvalue()
    assert "daily_remaining=77" in output.getvalue()


def test_season_command_uses_api_ref_and_fixture_team_identity():
    tracked = competition()
    catalog_season(tracked)
    api_ref = api_competition_ref(tracked)
    FakeClient.responses = {"fixtures": [fixture_payload()]}
    output = StringIO()
    with mock.patch.object(SeasonCommand, "client_class", FakeClient):
        call_command("sync_football_season", tracked.id, 2025, stdout=output)
        FakeClient.responses = {
            "fixtures": [
                fixture_payload(
                    status_short="FT",
                    status_long="Match Finished",
                    home_score=0,
                    away_score=0,
                    home_winner=False,
                    away_winner=False,
                )
            ]
        }
        call_command("sync_football_season", tracked.id, 2025, stdout=output)

    assert Team.objects.count() == 2
    assert Match.objects.count() == 1
    assert Match.objects.get().outcome == Match.OUTCOME_DRAW
    assert all(
        instance.requests
        == [
            (
                "fixtures",
                {
                    "league": api_ref.external_id,
                    "season": 2025,
                    "timezone": "America/Lima",
                },
            )
        ]
        for instance in FakeClient.instances
    )
    assert all(endpoint != "teams" for endpoint, _ in FakeClient.instances[0].requests)


def test_season_command_rejects_unknown_season_before_provider_call():
    tracked = competition()
    output = StringIO()
    with mock.patch.object(SeasonCommand, "client_class", FakeClient):
        with pytest.raises(CommandError, match="run sync_football_catalog first"):
            call_command("sync_football_season", tracked.id, 2025, stdout=output)
    assert FakeClient.instances[0].requests == []
    assert Season.objects.count() == 0
    assert "calls=0" in output.getvalue()


@override_settings(INKABET_BRAND_ID="", INKABET_MARKET_CODE="")
def test_day_uses_one_global_fixture_call_and_per_fixture_api_odds():
    enabled = competition()
    catalog_season(enabled)
    competition(external_id=40, enabled=False, name="Disabled")
    sync_catalog_payloads([], [{"id": 1, "name": "Match Winner"}])
    FakeClient.responses = {
        "fixtures": [fixture_payload(), fixture_payload(fixture_id=2001, league_id=40)],
        "odds": [odds_payload()],
    }
    output = StringIO()
    with mock.patch.object(DayCommand, "client_class", FakeClient):
        call_command(
            "sync_football_day",
            date="2025-08-24",
            with_odds=True,
            stdout=output,
        )

    assert FakeClient.instances[0].requests == [
        (
            "fixtures",
            {"date": "2025-08-24", "timezone": "America/Lima"},
        ),
        ("odds", {"fixture": "1001", "bet": "1"}),
    ]
    assert Match.objects.count() == 1
    assert OddsSnapshot.objects.count() == 1
    assert OddsObservation.objects.count() == 1
    assert "INKABET_CONFIGURATION_REQUIRED" in output.getvalue()


@override_settings(INKABET_BRAND_ID="", INKABET_MARKET_CODE="")
@pytest.mark.parametrize(
    ("coverage", "expect_odds_call"),
    [({"odds": True}, True), ({"odds": False}, False), ({}, False)],
)
def test_day_api_odds_calls_require_explicit_catalogue_coverage(
    coverage, expect_odds_call
):
    tracked = competition()
    catalog_season(tracked, coverage=coverage)
    sync_catalog_payloads([], [{"id": 1, "name": "Match Winner"}])
    FakeClient.responses = {
        "fixtures": [fixture_payload()],
        "odds": [odds_payload()],
    }
    output = StringIO()
    with mock.patch.object(DayCommand, "client_class", FakeClient):
        call_command(
            "sync_football_day",
            date="2025-08-24",
            with_odds=True,
            stdout=output,
        )

    endpoints = [endpoint for endpoint, _ in FakeClient.instances[0].requests]
    assert ("odds" in endpoints) is expect_odds_call
    assert OddsSnapshot.objects.exists() is expect_odds_call


@override_settings(INKABET_BRAND_ID="", INKABET_MARKET_CODE="")
def test_day_unknown_api_odds_coverage_needs_no_market_or_odds_call():
    tracked = competition()
    catalog_season(tracked, coverage={})
    FakeClient.responses = {"fixtures": [fixture_payload()]}
    output = StringIO()
    with mock.patch.object(DayCommand, "client_class", FakeClient):
        call_command(
            "sync_football_day",
            date="2025-08-24",
            with_odds=True,
            stdout=output,
        )
    assert FakeClient.instances[0].requests == [
        (
            "fixtures",
            {"date": "2025-08-24", "timezone": "America/Lima"},
        )
    ]
    assert "skipped=2" in output.getvalue()


@override_settings(INKABET_BRAND_ID="local-brand", INKABET_MARKET_CODE="local-market")
def test_day_reconciles_inkabet_once_and_updates_one_current_inkabet_row():
    tracked = competition()
    catalog_season(tracked)
    sync_catalog_payloads([], [{"id": 1, "name": "Match Winner"}])
    FakeClient.responses = {
        "fixtures": [fixture_payload()],
        "odds": [odds_payload()],
    }
    FakeInkabetClient.categories_payload = inkabet_categories_payload()
    items = FakeInkabetClient.categories_payload["data"]["items"]
    items["indexBySlug"][
        "futbol/england/england-premier-league/future-home-future-away"
    ] = ["1", "11", "3", "f-unrelated-future"]
    items["byId"]["f-unrelated-future"] = {
        "label": "Future Home - Future Away",
        "startDate": "2025-09-12T20:00:00+00:00",
        "eventType": "Match",
        "homeTeam": {"name": "Future Home"},
        "awayTeam": {"name": "Future Away"},
    }
    FakeInkabetClient.mw3w_payload = inkabet_mw3w_payload()
    output = StringIO()
    with (
        mock.patch.object(DayCommand, "client_class", FakeClient),
        mock.patch.object(DayCommand, "inkabet_client_class", FakeInkabetClient),
    ):
        call_command(
            "sync_football_day",
            date="2025-08-24",
            with_odds=True,
            stdout=output,
        )

    assert FakeInkabetClient.instances[0].requests == [
        ("categories", {}),
        ("mw3w", {"eventId": "f-current-match"}),
    ]
    assert OddsSnapshot.objects.filter(source__code="inkabet").count() == 1
    assert OddsSnapshot.objects.count() == 2
    assert OddsObservation.objects.filter(source__code="inkabet").count() == 1
    assert "inkabet_calls=2" in output.getvalue()
    assert "pending_matches=0" in output.getvalue()
    assert "RECONCILIATION_REQUIRED" not in output.getvalue()


@override_settings(INKABET_BRAND_ID="local-brand", INKABET_MARKET_CODE="local-market")
def test_day_pending_match_skips_dependent_inkabet_odds_and_warns():
    tracked = competition()
    catalog_season(tracked)
    sync_catalog_payloads([], [{"id": 1, "name": "Match Winner"}])
    FakeClient.responses = {
        "fixtures": [fixture_payload()],
        "odds": [odds_payload()],
    }
    FakeInkabetClient.categories_payload = inkabet_categories_payload()
    metadata = FakeInkabetClient.categories_payload["data"]["items"]["byId"][
        "f-current-match"
    ]
    metadata["homeTeam"] = {"name": "Unknown Home"}
    metadata["awayTeam"] = {"name": "Unknown Away"}
    FakeInkabetClient.mw3w_payload = inkabet_mw3w_payload()
    output = StringIO()
    with (
        mock.patch.object(DayCommand, "client_class", FakeClient),
        mock.patch.object(DayCommand, "inkabet_client_class", FakeInkabetClient),
    ):
        call_command(
            "sync_football_day",
            date="2025-08-24",
            with_odds=True,
            stdout=output,
        )

    assert FakeInkabetClient.instances[0].requests == [("categories", {})]
    assert OddsSnapshot.objects.filter(source__code="inkabet").count() == 0
    assert "pending_matches=1" in output.getvalue()
    assert (
        "RECONCILIATION_REQUIRED: competitions=0 teams=0 matches=1; "
        "review Football > Match source refs in Django Admin; "
        "filter by source and reconciliation status" in output.getvalue()
    )


def test_evening_day_command_makes_no_odds_or_inkabet_request():
    tracked = competition()
    catalog_season(tracked)
    FakeClient.responses = {"fixtures": [fixture_payload()]}
    with mock.patch.object(DayCommand, "client_class", FakeClient):
        call_command("sync_football_day", date="2025-08-24", stdout=StringIO())
    assert FakeClient.instances[0].requests == [
        (
            "fixtures",
            {"date": "2025-08-24", "timezone": "America/Lima"},
        )
    ]
    assert FakeInkabetClient.instances == []


@override_settings(INKABET_BRAND_ID="", INKABET_MARKET_CODE="")
def test_day_command_reports_partial_counts_and_quota_stop_safely():
    tracked = competition()
    catalog_season(tracked)
    sync_catalog_payloads([], [{"id": 1, "name": "Match Winner"}])

    def quota_stop(params):
        raise APIFootballQuotaReserveError("Daily quota reserve reached.")

    FakeClient.responses = {
        "fixtures": [fixture_payload()],
        "odds": quota_stop,
    }
    output = StringIO()
    with mock.patch.object(DayCommand, "client_class", FakeClient):
        with pytest.raises(CommandError, match="quota reserve"):
            call_command(
                "sync_football_day",
                date="2025-08-24",
                with_odds=True,
                stdout=output,
            )
    report = output.getvalue()
    assert "created=3" in report
    assert "calls=2" in report
    assert "daily_remaining=77" in report
    assert "error=Daily quota reserve reached." in report


def test_day_request_uses_lima_boundary_for_late_night_fixture():
    tracked = competition()
    catalog_season(tracked)
    FakeClient.responses = {
        "fixtures": [
            fixture_payload(
                kickoff="2025-08-24T23:30:00-05:00",
                provider_timezone="America/Lima",
            )
        ]
    }
    with mock.patch.object(DayCommand, "client_class", FakeClient):
        call_command("sync_football_day", date="2025-08-24", stdout=StringIO())

    assert FakeClient.instances[0].requests == [
        (
            "fixtures",
            {"date": "2025-08-24", "timezone": settings.TIME_ZONE},
        )
    ]
    match = Match.objects.get()
    assert match.kickoff_timezone == "America/Lima"
    assert (
        timezone.localtime(match.kickoff, ZoneInfo(settings.TIME_ZONE))
        .date()
        .isoformat()
        == "2025-08-24"
    )


def test_day_unknown_season_fails_without_creating_incomplete_metadata():
    competition()
    FakeClient.responses = {"fixtures": [fixture_payload()]}
    output = StringIO()
    with mock.patch.object(DayCommand, "client_class", FakeClient):
        with pytest.raises(CommandError, match="run sync_football_catalog first"):
            call_command("sync_football_day", date="2025-08-24", stdout=output)

    assert FakeClient.instances[0].requests == [
        (
            "fixtures",
            {"date": "2025-08-24", "timezone": "America/Lima"},
        )
    ]
    assert Season.objects.count() == 0
    assert Team.objects.count() == 0
    assert Match.objects.count() == 0


@override_settings(
    INKABET_BRAND_ID="local-brand",
    INKABET_MARKET_CODE="local-market",
)
def test_day_inkabet_categories_failure_is_fail_soft():
    tracked = competition()
    catalog_season(tracked)
    sync_catalog_payloads([], [{"id": 1, "name": "Match Winner"}])

    FakeClient.responses = {
        "fixtures": [fixture_payload()],
        "odds": [odds_payload()],
    }
    FakeInkabetClient.categories_error = InkabetResponseError("Inkabet maintenance.")

    output = StringIO()

    with (
        mock.patch.object(DayCommand, "client_class", FakeClient),
        mock.patch.object(
            DayCommand,
            "inkabet_client_class",
            FakeInkabetClient,
        ),
        mock.patch("football.inkabet_capture.emit_event") as operational_event,
    ):
        call_command(
            "sync_football_day",
            date="2025-08-24",
            with_odds=True,
            stdout=output,
        )

    report = output.getvalue()

    assert OddsSnapshot.objects.filter(source__code="api_football").exists()
    assert not OddsSnapshot.objects.filter(source__code="inkabet").exists()

    assert "INKABET_DEGRADED" in report
    assert "inkabet_calls=1" in report
    assert "inkabet_errors=1" in report
    assert "error=none" in report
    operational_event.assert_called_once()
    assert operational_event.call_args.kwargs["event_code"] == "PROVIDER_DEGRADED"
    assert operational_event.call_args.kwargs["severity"] == "WARNING"


@override_settings(
    INKABET_BRAND_ID="local-brand",
    INKABET_MARKET_CODE="local-market",
)
def test_day_inkabet_mw3w_failure_is_fail_soft():
    tracked = competition()
    catalog_season(tracked)
    sync_catalog_payloads([], [{"id": 1, "name": "Match Winner"}])

    FakeClient.responses = {
        "fixtures": [fixture_payload()],
        "odds": [odds_payload()],
    }
    FakeInkabetClient.categories_payload = inkabet_categories_payload()
    FakeInkabetClient.mw3w_error = InkabetResponseError("Inkabet maintenance.")

    output = StringIO()

    with (
        mock.patch.object(DayCommand, "client_class", FakeClient),
        mock.patch.object(
            DayCommand,
            "inkabet_client_class",
            FakeInkabetClient,
        ),
    ):
        call_command(
            "sync_football_day",
            date="2025-08-24",
            with_odds=True,
            stdout=output,
        )

    report = output.getvalue()

    assert OddsSnapshot.objects.filter(source__code="api_football").exists()
    assert not OddsSnapshot.objects.filter(source__code="inkabet").exists()

    assert "INKABET_DEGRADED event=f-current-match" in report
    assert "inkabet_calls=2" in report
    assert "inkabet_errors=1" in report
    assert "error=none" in report


@override_settings(
    INKABET_BRAND_ID="local-brand",
    INKABET_MARKET_CODE="local-market",
)
def test_day_malformed_inkabet_categories_is_fail_soft():
    tracked = competition()
    catalog_season(tracked)
    sync_catalog_payloads([], [{"id": 1, "name": "Match Winner"}])

    FakeClient.responses = {
        "fixtures": [fixture_payload()],
        "odds": [odds_payload()],
    }

    # Top-level response is valid JSON/data, but the nested provider
    # categories shape has drifted.
    FakeInkabetClient.categories_payload = {
        "data": {
            "items": [],
        }
    }

    output = StringIO()

    with (
        mock.patch.object(DayCommand, "client_class", FakeClient),
        mock.patch.object(
            DayCommand,
            "inkabet_client_class",
            FakeInkabetClient,
        ),
    ):
        call_command(
            "sync_football_day",
            date="2025-08-24",
            with_odds=True,
            stdout=output,
        )

    report = output.getvalue()

    assert OddsSnapshot.objects.filter(
        source__code="api_football",
    ).exists()
    assert not OddsSnapshot.objects.filter(
        source__code="inkabet",
    ).exists()

    assert "INKABET_DEGRADED" in report
    assert "unexpected categories payload shape" in report
    assert "inkabet_calls=1" in report
    assert "inkabet_errors=1" in report
    assert "error=none" in report


@override_settings(
    INKABET_BRAND_ID="local-brand",
    INKABET_MARKET_CODE="local-market",
)
def test_day_malformed_inkabet_mw3w_is_diagnostic_and_fail_soft():
    tracked = competition()
    catalog_season(tracked)
    sync_catalog_payloads([], [{"id": 1, "name": "Match Winner"}])
    FakeClient.responses = {
        "fixtures": [fixture_payload()],
        "odds": [odds_payload()],
    }
    FakeInkabetClient.categories_payload = inkabet_categories_payload()
    FakeInkabetClient.mw3w_payload = {
        "data": {
            "accordions": {
                "MW3W": {
                    "markets": ["invalid-market-shape"],
                    "selections": [],
                }
            }
        }
    }
    output = StringIO()

    with (
        mock.patch.object(DayCommand, "client_class", FakeClient),
        mock.patch.object(
            DayCommand,
            "inkabet_client_class",
            FakeInkabetClient,
        ),
        mock.patch("football.inkabet_capture.emit_event") as operational_event,
    ):
        call_command(
            "sync_football_day",
            date="2025-08-24",
            with_odds=True,
            stdout=output,
        )

    report = output.getvalue()
    assert "INKABET_DEGRADED" in report
    assert "unexpected MW3W payload shape" in report
    assert "inkabet_calls=2" in report
    assert "inkabet_errors=1" in report
    assert "error=none" in report
    operational_event.assert_called_once()
    event = operational_event.call_args.kwargs
    assert event["event_code"] == "PROVIDER_DEGRADED"
    assert event["provider"] == "Inkabet"
    assert event["failure_kind"] == "provider_schema_drift"
    assert event["operation"] == "match_winner"
    assert event["context"]["endpoint_family"] == "match_winner"
    assert event["context"]["json_path"] == "$.data.accordions.MW3W"
