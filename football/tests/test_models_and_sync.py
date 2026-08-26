from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.apps import apps
from django.db import IntegrityError, transaction
from django.utils import timezone
from django_countries.fields import CountryField

from football.models import (
    Competition,
    CompetitionSourceRef,
    Match,
    MatchSourceRef,
    OddsMarket,
    OddsSnapshot,
    ReconciliationStatus,
    Season,
    Team,
    TeamSourceRef,
)
from football.sync import (
    FootballSyncError,
    sync_catalog_payloads,
    sync_fixture_payloads,
    sync_odds_payloads,
)

from .helpers import (
    api_competition_ref,
    catalog_season,
    competition,
    fixture_payload,
    inkabet_source,
    league_payload,
    odds_payload,
    source,
)

pytestmark = pytest.mark.django_db


def test_catalog_uses_country_field_and_creates_resolved_api_reference():
    stats, market = sync_catalog_payloads(
        [league_payload()], [{"id": 1, "name": "Match Winner"}]
    )
    ref = CompetitionSourceRef.objects.get(source=source(), external_id="39")
    tracked = ref.competition
    season = tracked.seasons.get(year=2025)

    assert isinstance(Competition._meta.get_field("country"), CountryField)
    assert tracked.country.code == "EN"
    assert tracked.enabled is False
    assert ref.reconciliation_status == ReconciliationStatus.RESOLVED
    assert season.start_date == date(2025, 8, 15)
    assert season.end_date == date(2026, 5, 24)
    assert season.is_current is True
    assert season.coverage["odds"] is True
    assert market.external_id == "1"
    assert stats.created == 3

    second_stats, _ = sync_catalog_payloads(
        [league_payload()], [{"id": 1, "name": "Match Winner"}]
    )
    assert second_stats.created == 0
    assert second_stats.unchanged == 3


def test_canonical_entities_have_no_provider_identity_and_no_season_ref_model():
    assert "source" not in {field.name for field in Competition._meta.fields}
    assert "external_id" not in {field.name for field in Competition._meta.fields}
    assert "source" not in {field.name for field in Team._meta.fields}
    assert "external_id" not in {field.name for field in Team._meta.fields}
    assert "source" not in {field.name for field in Match._meta.fields}
    assert "external_id" not in {field.name for field in Match._meta.fields}
    with pytest.raises(LookupError):
        apps.get_model("football", "SeasonSourceRef")


def test_source_ref_identity_is_unique_but_two_sources_share_canonical_objects():
    tracked = competition()
    api_ref = api_competition_ref(tracked)
    secondary = CompetitionSourceRef.objects.create(
        source=inkabet_source(),
        competition=tracked,
        external_id="3",
        external_name="England Premier League",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    assert api_ref.competition == secondary.competition
    with transaction.atomic(), pytest.raises(IntegrityError):
        CompetitionSourceRef.objects.create(
            source=source(),
            external_id="39",
            external_name="Duplicate",
        )


def test_team_and_match_source_external_identity_are_unique():
    tracked = competition()
    catalog_season(tracked)
    sync_fixture_payloads([fixture_payload()], {"39": tracked})
    team_ref = TeamSourceRef.objects.filter(source=source()).first()
    match_ref = MatchSourceRef.objects.get(source=source())
    with transaction.atomic(), pytest.raises(IntegrityError):
        TeamSourceRef.objects.create(
            source=source(),
            competition=tracked,
            external_id=team_ref.external_id,
            external_name="Duplicate team",
        )
    with transaction.atomic(), pytest.raises(IntegrityError):
        MatchSourceRef.objects.create(
            source=source(),
            external_id=match_ref.external_id,
            external_label="Duplicate match",
        )


def test_fixture_ingestion_creates_canonical_teams_match_and_resolved_refs():
    tracked = competition()
    catalog_season(tracked)
    stats, accepted = sync_fixture_payloads([fixture_payload()], {"39": tracked})
    match = accepted["1001"]

    assert stats.created == 3
    assert Team.objects.count() == 2
    assert (
        TeamSourceRef.objects.filter(
            source=source(), reconciliation_status=ReconciliationStatus.RESOLVED
        ).count()
        == 2
    )
    assert (
        MatchSourceRef.objects.get(source=source(), external_id="1001").match == match
    )
    assert match.status_short == "NS"
    assert match.outcome == ""

    repeated, _ = sync_fixture_payloads([fixture_payload()], {"39": tracked})
    assert repeated.unchanged == 3
    assert Match.objects.count() == 1


def test_fixture_update_keeps_api_football_as_result_authority():
    tracked = competition()
    catalog_season(tracked)
    sync_fixture_payloads([fixture_payload()], {"39": tracked})
    finished = fixture_payload(
        status_short="FT",
        status_long="Match Finished",
        home_score=2,
        away_score=1,
        home_winner=True,
        away_winner=False,
    )
    changed, accepted = sync_fixture_payloads([finished], {"39": tracked})
    match = accepted["1001"]
    assert changed.updated == 1
    assert match.status_short == "FT"
    assert match.outcome == Match.OUTCOME_HOME
    assert match.home_score == 2


def test_disabled_competition_boundary_is_applied_by_selected_mapping():
    disabled = competition(enabled=False)
    stats, accepted = sync_fixture_payloads([fixture_payload()], {})
    assert stats.skipped == 1
    assert accepted == {}
    assert disabled.teams.count() == 0


def test_stable_team_cannot_be_silently_moved_between_competitions():
    first = competition()
    second = competition(external_id=40, name="Other League")
    catalog_season(first)
    catalog_season(second)
    sync_fixture_payloads([fixture_payload()], {"39": first})
    conflicting = fixture_payload(league_id=40)
    conflicting["teams"]["home"]["id"] = 3901
    with pytest.raises(FootballSyncError, match="different tracked competition"):
        sync_fixture_payloads([conflicting], {"40": second})


def test_odds_changed_value_updates_current_row_in_place():
    tracked = competition()
    catalog_season(tracked)
    _, accepted = sync_fixture_payloads([fixture_payload()], {"39": tracked})
    market = OddsMarket.objects.create(
        source=source(), external_id="1", name="Match Winner"
    )

    first = sync_odds_payloads([odds_payload()], accepted, market)
    repeated = sync_odds_payloads([odds_payload()], accepted, market)
    changed = sync_odds_payloads(
        [
            odds_payload(
                update="2025-08-24T13:00:00+00:00",
                home="2.25",
            )
        ],
        accepted,
        market,
    )

    assert first.created == 2
    assert repeated.unchanged == 2
    assert changed.updated == 1
    assert changed.unchanged == 1
    assert OddsSnapshot.objects.count() == 1
    assert OddsSnapshot.objects.get().home == Decimal("2.2500")


def test_upcoming_query_is_timezone_aware_and_excludes_started_statuses():
    tracked = competition()
    catalog_season(tracked)
    _, accepted = sync_fixture_payloads([fixture_payload()], {"39": tracked})
    match = accepted["1001"]
    match.kickoff = timezone.now() + timedelta(hours=1)
    match.save(update_fields=["kickoff"])
    assert list(Match.objects.upcoming()) == [match]

    match.status_short = "1H"
    match.save(update_fields=["status_short"])
    assert not Match.objects.upcoming().exists()


def test_fixture_sync_requires_catalogued_season_and_creates_no_partial_metadata():
    tracked = competition()
    with pytest.raises(FootballSyncError, match="run sync_football_catalog first"):
        sync_fixture_payloads([fixture_payload()], {"39": tracked})

    assert Season.objects.count() == 0
    assert Team.objects.count() == 0
    assert Match.objects.count() == 0


def test_fixture_sync_does_not_change_authoritative_catalogue_metadata():
    tracked = competition()
    season = catalog_season(
        tracked,
        coverage={"fixtures": {"statistics_fixtures": True}, "odds": False},
    )
    original = {
        "start_date": season.start_date,
        "end_date": season.end_date,
        "is_current": season.is_current,
        "coverage": season.coverage,
    }

    sync_fixture_payloads([fixture_payload()], {"39": tracked})
    season.refresh_from_db()
    assert {
        "start_date": season.start_date,
        "end_date": season.end_date,
        "is_current": season.is_current,
        "coverage": season.coverage,
    } == original
