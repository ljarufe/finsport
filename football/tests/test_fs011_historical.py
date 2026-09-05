from dataclasses import replace
from datetime import date, datetime, timedelta
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.management import call_command
from django.utils import timezone

from football.admin import CompetitionAdmin
from football.historical.contracts import (
    HistoricalMappingError,
    HistoricalParserError,
    HistoricalResult,
    HistoricalSourceUnavailable,
)
from football.historical.reconciliation import (
    _normalized_team_name,
    reconcile_result,
)
from football.historical.service import (
    historical_coverage_is_current,
    process_historical_bootstrap,
    request_historical_bootstrap,
)
from football.models import (
    Competition,
    HistoricalCoverage,
    Match,
    MatchSourceRef,
    ReconciliationStatus,
    Season,
    Source,
    Team,
    TeamSourceRef,
)
from football.pipeline.service import _dixon_coles_candidates
from football.providers.football_data import (
    DIRECT_COMPETITIONS,
    EUROPE_COMPETITIONS,
    SOURCE_TIMEZONE_NAME,
    DirectFootballDataCSVAdapter,
    EuropeFootballDataAdapter,
    _technical_kickoff,
    source_contract,
)


class FrozenAdapter:
    external_competition = "ENG Premier League"

    def __init__(self, records):
        self.records = records
        self.download_count = 0

    def records_for_season(self, season):
        self.download_count += 1
        value = self.records.get(season.year, [])
        if isinstance(value, Exception):
            raise value
        return value


def result(year, home="Home", away="Away", home_score=2, away_score=1):
    kickoff = datetime(year, 8, 20, 12, tzinfo=ZoneInfo("America/Lima"))
    return HistoricalResult(
        source_code="football_data",
        competition_external_id="ENG Premier League",
        season_year=year,
        external_id=f"{year}:{home}:{away}",
        home_external_id=f"ENG Premier League:{home}",
        home_name=home,
        away_external_id=f"ENG Premier League:{away}",
        away_name=away,
        kickoff=kickoff,
        kickoff_precision="DATE_ONLY",
        home_score=home_score,
        away_score=away_score,
        provenance={"authority": "football-data.co.uk"},
    )


def exact_result(
    year,
    kickoff,
    *,
    home="Home",
    away="Away",
    home_score=2,
    away_score=1,
    external_id="exact-source-match",
):
    return HistoricalResult(
        source_code="football_data",
        competition_external_id="ENG Premier League",
        season_year=year,
        external_id=external_id,
        home_external_id=f"ENG Premier League:{home}",
        home_name=home,
        away_external_id=f"ENG Premier League:{away}",
        away_name=away,
        kickoff=kickoff,
        kickoff_precision="EXACT",
        home_score=home_score,
        away_score=away_score,
        provenance={
            "authority": "football-data.co.uk",
            "raw_source_date": kickoff.date().isoformat(),
            "raw_source_time": kickoff.time().isoformat(),
            "source_timezone_contract": "Europe/London",
            "normalized_source_kickoff": kickoff.isoformat(),
        },
    )


def competition_with_catalogue():
    competition = Competition.objects.create(
        name="Premier League", competition_type="League", country="EN", enabled=True
    )
    Team.objects.create(competition=competition, name="Home", is_active=True)
    Team.objects.create(competition=competition, name="Away", is_active=True)
    completed = Season.objects.create(
        competition=competition,
        year=2024,
        start_date=date(2024, 8, 1),
        end_date=date(2025, 5, 31),
    )
    current = Season.objects.create(
        competition=competition,
        year=2025,
        start_date=date(2025, 8, 1),
        end_date=date(2026, 5, 31),
        is_current=True,
    )
    return competition, completed, current


@pytest.mark.django_db
def test_activation_is_blocked_until_every_completed_season_is_covered():
    competition, completed, current = competition_with_catalogue()
    coverage = request_historical_bootstrap(competition)
    competition.refresh_from_db()
    assert competition.enabled is False
    assert coverage.status == HistoricalCoverage.Status.NOT_ATTEMPTED

    coverage = process_historical_bootstrap(
        competition, adapter=FrozenAdapter({completed.year: [result(completed.year)]})
    )
    competition.refresh_from_db()
    assert coverage.status == HistoricalCoverage.Status.COMPLETE
    assert coverage.required_seasons == [completed.year]
    assert coverage.covered_seasons == [completed.year]
    assert current.year not in coverage.required_seasons
    assert competition.enabled is True
    assert coverage.download_count == 1
    assert Match.objects.filter(season=completed, status_short="FT").count() == 1
    ref = MatchSourceRef.objects.get(source__code="football_data")
    assert ref.context["authority"] == "football-data.co.uk"
    assert ref.context["kickoff_precision"] == "DATE_ONLY"


@pytest.mark.django_db
def test_complete_basis_becomes_stale_and_explicit_retry_restores_it():
    competition, completed, current = competition_with_catalogue()
    request_historical_bootstrap(competition)
    coverage = process_historical_bootstrap(
        competition, adapter=FrozenAdapter({completed.year: [result(completed.year)]})
    )
    assert historical_coverage_is_current(competition, coverage) is True
    assert current.year not in coverage.required_seasons

    at = timezone.now()
    home, away = Team.objects.filter(competition=competition).order_by("pk")[:2]
    Match.objects.create(
        season=current,
        home_team=home,
        away_team=away,
        kickoff=at + timedelta(hours=1),
        status_short="NS",
        status_long="Not Started",
    )
    assert _dixon_coles_candidates(at)

    newly_completed = Season.objects.create(
        competition=competition,
        year=2026,
        start_date=date(2026, 8, 1),
        end_date=date(2027, 5, 31),
        is_current=False,
    )
    assert historical_coverage_is_current(competition, coverage) is False
    assert _dixon_coles_candidates(at) == []
    request_historical_bootstrap(competition, activate=True)
    competition.refresh_from_db()
    assert competition.enabled is False

    request_historical_bootstrap(
        competition, activate=True, reason="MANUAL_RETRY_REQUESTED"
    )
    restored = process_historical_bootstrap(
        competition,
        adapter=FrozenAdapter(
            {
                completed.year: [result(completed.year)],
                newly_completed.year: [result(newly_completed.year)],
            }
        ),
    )
    competition.refresh_from_db()
    assert historical_coverage_is_current(competition, restored) is True
    assert restored.required_seasons == [completed.year, newly_completed.year]
    assert current.year not in restored.required_seasons
    assert competition.enabled is True

    restored.strategy_version = "incompatible-strategy"
    restored.save(update_fields=["strategy_version", "modified"])
    assert historical_coverage_is_current(competition, restored) is False
    assert _dixon_coles_candidates(at) == []


@pytest.mark.django_db
def test_missing_season_and_source_failure_are_terminal_without_daily_retry():
    competition, completed, _ = competition_with_catalogue()
    request_historical_bootstrap(competition)
    partial = process_historical_bootstrap(
        competition, adapter=FrozenAdapter({completed.year: []})
    )
    competition.refresh_from_db()
    assert partial.status == HistoricalCoverage.Status.PARTIAL
    assert partial.unresolved_seasons == [completed.year]
    assert competition.enabled is False
    assert partial.diagnostics["automatic_retry"] is False

    partial.status = HistoricalCoverage.Status.NOT_ATTEMPTED
    partial.save(update_fields=["status", "modified"])
    unavailable = process_historical_bootstrap(
        competition,
        adapter=FrozenAdapter(
            {completed.year: HistoricalSourceUnavailable("FROZEN_UNAVAILABLE")}
        ),
    )
    assert unavailable.status == HistoricalCoverage.Status.UNAVAILABLE
    assert unavailable.reason == "FROZEN_UNAVAILABLE"

    retried = request_historical_bootstrap(
        competition, activate=True, reason="MANUAL_RETRY_REQUESTED"
    )
    assert retried.status == HistoricalCoverage.Status.NOT_ATTEMPTED
    assert retried.activation_requested is True


@pytest.mark.django_db
def test_unexpected_adapter_failure_is_failed_and_disables_competition():
    competition, completed, _ = competition_with_catalogue()
    request_historical_bootstrap(competition)
    failed = process_historical_bootstrap(
        competition, adapter=FrozenAdapter({completed.year: RuntimeError("boom")})
    )
    competition.refresh_from_db()
    assert failed.status == HistoricalCoverage.Status.FAILED
    assert failed.reason == "UNEXPECTED_HISTORICAL_INGESTION_FAILURE"
    assert failed.diagnostics["error_class"] == "RuntimeError"
    assert competition.enabled is False


@pytest.mark.django_db
def test_reimport_is_idempotent_and_trusted_api_result_is_not_overwritten():
    competition, completed, _ = competition_with_catalogue()
    request_historical_bootstrap(competition)
    first_adapter = FrozenAdapter({completed.year: [result(completed.year)]})
    first = process_historical_bootstrap(competition, adapter=first_adapter)
    assert first.rows_created == 1
    match = Match.objects.get(season=completed)
    count = Match.objects.count()

    first.status = HistoricalCoverage.Status.NOT_ATTEMPTED
    first.save(update_fields=["status", "modified"])
    repeated = process_historical_bootstrap(
        competition, adapter=FrozenAdapter({completed.year: [result(completed.year)]})
    )
    assert repeated.status == HistoricalCoverage.Status.COMPLETE
    assert repeated.rows_unchanged == 1
    assert Match.objects.count() == count

    api = Source.objects.get(code="api_football")
    MatchSourceRef.objects.create(
        source=api,
        external_id="trusted-api-match",
        match=match,
        reconciliation_status=ReconciliationStatus.RESOLVED,
        confidence=1,
    )
    repeated.status = HistoricalCoverage.Status.NOT_ATTEMPTED
    repeated.save(update_fields=["status", "modified"])
    conflict = process_historical_bootstrap(
        competition,
        adapter=FrozenAdapter(
            {completed.year: [result(completed.year, home_score=0, away_score=4)]}
        ),
    )
    match.refresh_from_db()
    assert conflict.status == HistoricalCoverage.Status.PARTIAL
    assert conflict.conflict_count == 1
    assert (match.home_score, match.away_score) == (2, 1)


@pytest.mark.django_db
def test_exact_secondary_with_one_hour_delta_reuses_api_match_idempotently():
    competition, season, _ = competition_with_catalogue()
    home, away = Team.objects.filter(competition=competition).order_by("pk")[:2]
    canonical_kickoff = datetime(2024, 8, 20, 15, tzinfo=ZoneInfo("Europe/London"))
    canonical = Match.objects.create(
        season=season,
        home_team=home,
        away_team=away,
        kickoff=canonical_kickoff,
        status_short="FT",
        status_long="Match Finished",
        home_score=2,
        away_score=1,
        outcome=Match.OUTCOME_HOME,
    )
    api_source, _ = Source.objects.get_or_create(
        code="api_football",
        defaults={"name": "API-Football", "base_url": "https://example.test/"},
    )
    MatchSourceRef.objects.create(
        source=api_source,
        external_id="api-primary",
        match=canonical,
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    secondary, _ = Source.objects.get_or_create(
        code="football_data",
        defaults={"name": "football-data", "base_url": "https://example.test/"},
    )
    record = exact_result(season.year, canonical_kickoff + timedelta(hours=1))

    first = reconcile_result(secondary, competition, season, record)
    repeated = reconcile_result(secondary, competition, season, record)

    canonical.refresh_from_db()
    assert Match.objects.filter(season=season).count() == 1
    assert canonical.kickoff == canonical_kickoff
    assert (canonical.home_score, canonical.away_score, canonical.outcome) == (
        2,
        1,
        Match.OUTCOME_HOME,
    )
    secondary_ref = MatchSourceRef.objects.get(
        source=secondary, external_id=record.external_id
    )
    assert secondary_ref.match == canonical
    assert secondary_ref.reconciliation_status == ReconciliationStatus.RESOLVED
    assert secondary_ref.context["source_canonical_delta_seconds"] == -3600
    assert (
        datetime.fromisoformat(secondary_ref.context["canonical_kickoff"])
        == canonical_kickoff
    )
    assert first.reconciled == 1
    assert repeated.unchanged == 1


@pytest.mark.django_db
def test_exact_reimport_outside_tolerance_is_conflict_not_unchanged():
    competition, season, _ = competition_with_catalogue()
    home, away = Team.objects.filter(competition=competition).order_by("pk")[:2]
    canonical_kickoff = datetime(2024, 8, 20, 15, tzinfo=ZoneInfo("Europe/London"))
    canonical = Match.objects.create(
        season=season,
        home_team=home,
        away_team=away,
        kickoff=canonical_kickoff,
        status_short="FT",
        status_long="Match Finished",
        home_score=2,
        away_score=1,
        outcome=Match.OUTCOME_HOME,
    )
    api_source, _ = Source.objects.get_or_create(
        code="api_football",
        defaults={"name": "API-Football", "base_url": "https://example.test/"},
    )
    MatchSourceRef.objects.create(
        source=api_source,
        external_id="api-reimport-primary",
        match=canonical,
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    secondary, _ = Source.objects.get_or_create(
        code="football_data",
        defaults={"name": "football-data", "base_url": "https://example.test/"},
    )
    original = exact_result(
        season.year,
        canonical_kickoff + timedelta(hours=1),
        external_id="secondary-reimport-time",
    )
    first = reconcile_result(secondary, competition, season, original)
    assert first.reconciled == 1

    corrected = exact_result(
        season.year,
        canonical_kickoff + timedelta(hours=3),
        external_id=original.external_id,
    )
    repeated = reconcile_result(secondary, competition, season, corrected)

    canonical.refresh_from_db()
    ref = MatchSourceRef.objects.get(source=secondary, external_id=original.external_id)
    assert repeated.unchanged == 0
    assert repeated.conflicts == 1
    assert ref.context["reconciliation"] == "SOURCE_REIMPORT_CONFLICT"
    assert canonical.kickoff == canonical_kickoff
    assert (canonical.home_score, canonical.away_score, canonical.outcome) == (
        2,
        1,
        Match.OUTCOME_HOME,
    )


@pytest.mark.django_db
def test_bounded_secondary_score_conflict_preserves_api_canonical_result():
    competition, season, _ = competition_with_catalogue()
    home, away = Team.objects.filter(competition=competition).order_by("pk")[:2]
    canonical_kickoff = datetime(2024, 8, 20, 15, tzinfo=ZoneInfo("Europe/London"))
    canonical = Match.objects.create(
        season=season,
        home_team=home,
        away_team=away,
        kickoff=canonical_kickoff,
        status_short="FT",
        status_long="Match Finished",
        home_score=2,
        away_score=1,
        outcome=Match.OUTCOME_HOME,
    )
    api_source, _ = Source.objects.get_or_create(
        code="api_football",
        defaults={"name": "API-Football", "base_url": "https://example.test/"},
    )
    MatchSourceRef.objects.create(
        source=api_source,
        external_id="api-conflict-primary",
        match=canonical,
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    secondary, _ = Source.objects.get_or_create(
        code="football_data",
        defaults={"name": "football-data", "base_url": "https://example.test/"},
    )
    record = exact_result(
        season.year,
        canonical_kickoff + timedelta(hours=1),
        home_score=0,
        away_score=3,
        external_id="secondary-conflict",
    )

    stats = reconcile_result(secondary, competition, season, record)

    canonical.refresh_from_db()
    assert Match.objects.filter(season=season).count() == 1
    assert canonical.kickoff == canonical_kickoff
    assert (canonical.home_score, canonical.away_score, canonical.outcome) == (
        2,
        1,
        Match.OUTCOME_HOME,
    )
    ref = MatchSourceRef.objects.get(source=secondary, external_id=record.external_id)
    assert ref.reconciliation_status == ReconciliationStatus.PENDING
    assert ref.proposed_match == canonical
    assert ref.context["reconciliation"] == "RESULT_CONFLICT"
    assert stats.conflicts == 1


@pytest.mark.django_db
def test_two_bounded_secondary_candidates_fail_closed():
    competition, season, _ = competition_with_catalogue()
    home, away = Team.objects.filter(competition=competition).order_by("pk")[:2]
    source_kickoff = datetime(2024, 8, 20, 16, tzinfo=ZoneInfo("Europe/London"))
    for offset in (-1, 1):
        Match.objects.create(
            season=season,
            home_team=home,
            away_team=away,
            kickoff=source_kickoff + timedelta(hours=offset),
            status_short="FT",
            status_long="Match Finished",
            home_score=2,
            away_score=1,
            outcome=Match.OUTCOME_HOME,
        )
    secondary, _ = Source.objects.get_or_create(
        code="football_data",
        defaults={"name": "football-data", "base_url": "https://example.test/"},
    )
    record = exact_result(
        season.year, source_kickoff, external_id="secondary-ambiguous"
    )

    stats = reconcile_result(secondary, competition, season, record)

    assert Match.objects.filter(season=season).count() == 2
    ref = MatchSourceRef.objects.get(source=secondary, external_id=record.external_id)
    assert ref.reconciliation_status == ReconciliationStatus.PENDING
    assert ref.match_id is None
    assert ref.context["reconciliation"] == "AMBIGUOUS_MATCH"
    assert stats.ambiguities == 1


@pytest.mark.django_db
def test_exact_secondary_without_candidate_creates_canonical_match():
    competition, season, _ = competition_with_catalogue()
    source, _ = Source.objects.get_or_create(
        code="football_data",
        defaults={"name": "football-data", "base_url": "https://example.test/"},
    )
    record = exact_result(
        season.year,
        datetime(2024, 8, 20, 16, tzinfo=ZoneInfo("Europe/London")),
        external_id="secondary-new-match",
    )

    stats = reconcile_result(source, competition, season, record)

    match = Match.objects.get(season=season)
    assert match.kickoff == record.kickoff
    assert match.status_short == "FT"
    assert stats.created == 1


@pytest.mark.django_db
def test_explicit_alias_maps_and_ambiguous_identity_fails_closed():
    competition, completed, _ = competition_with_catalogue()
    canonical = Team.objects.create(
        competition=competition, name="Manchester City", is_active=True
    )
    request_historical_bootstrap(competition)
    mapped = process_historical_bootstrap(
        competition,
        adapter=FrozenAdapter(
            {completed.year: [result(completed.year, home="Man City")]}
        ),
    )
    assert mapped.status == HistoricalCoverage.Status.COMPLETE
    assert Match.objects.get(season=completed).home_team == canonical

    unknown_target = Team.objects.create(
        competition=competition, name="Manchester United", is_active=False
    )
    team_count = Team.objects.filter(competition=competition).count()
    mapped.status = HistoricalCoverage.Status.NOT_ATTEMPTED
    mapped.save(update_fields=["status", "modified"])
    unresolved = process_historical_bootstrap(
        competition,
        adapter=FrozenAdapter(
            {completed.year: [result(completed.year, home="Manchester U")]}
        ),
    )
    assert unresolved.status == HistoricalCoverage.Status.PARTIAL
    assert Team.objects.filter(competition=competition).count() == team_count
    assert unresolved.diagnostics["issues"][0]["reason"] == "UNMAPPED_TEAM_IDENTITY"
    assert unresolved.diagnostics["issues"][0]["external_team_name"] == ("Manchester U")

    TeamSourceRef.objects.create(
        source=Source.objects.get(code="football_data"),
        competition=competition,
        external_id="ENG Premier League:Manchester U",
        external_name="Manchester U",
        team=unknown_target,
        reconciliation_status=ReconciliationStatus.RESOLVED,
        confidence=1,
    )
    unresolved.status = HistoricalCoverage.Status.NOT_ATTEMPTED
    unresolved.save(update_fields=["status", "modified"])
    reconciled = process_historical_bootstrap(
        competition,
        adapter=FrozenAdapter(
            {completed.year: [result(completed.year, home="Manchester U")]}
        ),
    )
    assert reconciled.status == HistoricalCoverage.Status.COMPLETE
    assert (
        Match.objects.get(season=completed, home_team=unknown_target).status_short
        == "FT"
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("canonical_name", "source_name"),
    (("Málaga", "malaga"), ("St. Pauli", "  ST   PAULI ")),
)
def test_unique_orthographic_team_equivalence_resolves_existing_team(
    canonical_name, source_name
):
    competition, season, _ = competition_with_catalogue()
    canonical = Team.objects.create(
        competition=competition, name=canonical_name, is_active=False
    )
    source, _ = Source.objects.get_or_create(
        code="football_data",
        defaults={"name": "football-data", "base_url": "https://example.test/"},
    )
    record = exact_result(
        season.year,
        datetime(2024, 9, 1, 15, tzinfo=ZoneInfo("Europe/London")),
        home=source_name,
        external_id=f"normalized:{source_name}",
    )

    stats = reconcile_result(source, competition, season, record)

    ref = TeamSourceRef.objects.get(
        source=source, external_id=f"ENG Premier League:{source_name}"
    )
    assert ref.team == canonical
    assert ref.reconciliation_status == ReconciliationStatus.RESOLVED
    assert ref.confidence == 1
    assert Match.objects.get(season=season).home_team == canonical
    assert stats.created == 1


@pytest.mark.django_db
def test_normalized_team_collision_fails_closed():
    competition, season, _ = competition_with_catalogue()
    Team.objects.create(competition=competition, name="Málaga")
    Team.objects.create(competition=competition, name="Malaga")
    source, _ = Source.objects.get_or_create(
        code="football_data",
        defaults={"name": "football-data", "base_url": "https://example.test/"},
    )
    record = exact_result(
        season.year,
        datetime(2024, 9, 1, 15, tzinfo=ZoneInfo("Europe/London")),
        home="MALAGA",
        external_id="normalized-collision",
    )

    with pytest.raises(HistoricalMappingError, match="AMBIGUOUS_TEAM_MAPPING:MALAGA"):
        reconcile_result(source, competition, season, record)

    assert not TeamSourceRef.objects.filter(
        source=source, external_id="ENG Premier League:MALAGA"
    ).exists()
    assert not Match.objects.filter(season=season).exists()


def test_colon_source_variants_have_the_same_normalized_identity():
    assert _normalized_team_name("Colon Santa FE") == _normalized_team_name(
        "Colon Santa Fe"
    )


@pytest.mark.django_db
def test_normalized_same_source_ref_reuses_team_without_creating_second_ref():
    competition, season, _ = competition_with_catalogue()
    colon = Team.objects.create(
        competition=competition, name="Colon Santa Fe", is_active=False
    )
    source, _ = Source.objects.get_or_create(
        code="football_data",
        defaults={"name": "football-data", "base_url": "https://example.test/"},
    )
    TeamSourceRef.objects.create(
        source=source,
        competition=competition,
        external_id="ARG:Colon Santa FE",
        external_name="Colon Santa FE",
        team=colon,
        reconciliation_status=ReconciliationStatus.RESOLVED,
        confidence=1,
    )
    record = replace(
        exact_result(
            season.year,
            datetime(2024, 9, 1, 15, tzinfo=ZoneInfo("Europe/London")),
            home="Colon Santa Fe",
            external_id="colon-source-name-variant",
        ),
        home_external_id="ARG:Colon Santa Fe",
    )

    stats = reconcile_result(source, competition, season, record)

    assert Match.objects.get(season=season).home_team == colon
    assert stats.created == 1
    assert (
        Team.objects.filter(competition=competition, name="Colon Santa Fe").count() == 1
    )
    assert TeamSourceRef.objects.filter(source=source, team=colon).count() == 1
    assert not TeamSourceRef.objects.filter(
        source=source, external_id="ARG:Colon Santa Fe"
    ).exists()


@pytest.mark.django_db
def test_normalized_same_source_refs_to_different_teams_fail_closed():
    competition, season, _ = competition_with_catalogue()
    first = Team.objects.create(competition=competition, name="Colon First")
    second = Team.objects.create(competition=competition, name="Colon Second")
    source, _ = Source.objects.get_or_create(
        code="football_data",
        defaults={"name": "football-data", "base_url": "https://example.test/"},
    )
    for external_id, external_name, team in (
        ("ARG:Colon Santa FE", "Colon Santa FE", first),
        ("ARG:COLON SANTA-FE", "COLÓN SANTA-FE", second),
    ):
        TeamSourceRef.objects.create(
            source=source,
            competition=competition,
            external_id=external_id,
            external_name=external_name,
            team=team,
            reconciliation_status=ReconciliationStatus.RESOLVED,
            confidence=1,
        )
    record = replace(
        exact_result(
            season.year,
            datetime(2024, 9, 1, 15, tzinfo=ZoneInfo("Europe/London")),
            home="Colon Santa Fe",
            external_id="ambiguous-colon-source-refs",
        ),
        home_external_id="ARG:Colon Santa Fe",
    )

    with pytest.raises(
        HistoricalMappingError, match="AMBIGUOUS_TEAM_MAPPING:Colon Santa Fe"
    ):
        reconcile_result(source, competition, season, record)

    assert not Match.objects.filter(season=season).exists()
    assert TeamSourceRef.objects.filter(source=source).count() == 2


@pytest.mark.django_db
def test_invalid_normalized_same_source_ref_fails_closed():
    competition, season, _ = competition_with_catalogue()
    source, _ = Source.objects.get_or_create(
        code="football_data",
        defaults={"name": "football-data", "base_url": "https://example.test/"},
    )
    TeamSourceRef.objects.create(
        source=source,
        competition=competition,
        external_id="ARG:Colon Santa FE",
        external_name="Colon Santa FE",
        reconciliation_status=ReconciliationStatus.PENDING,
    )
    record = replace(
        exact_result(
            season.year,
            datetime(2024, 9, 1, 15, tzinfo=ZoneInfo("Europe/London")),
            home="Colon Santa Fe",
            external_id="invalid-colon-source-ref",
        ),
        home_external_id="ARG:Colon Santa Fe",
    )

    with pytest.raises(
        HistoricalMappingError, match="AMBIGUOUS_TEAM_MAPPING:Colon Santa Fe"
    ):
        reconcile_result(source, competition, season, record)

    assert not Match.objects.filter(season=season).exists()


@pytest.mark.django_db
def test_exact_team_external_id_still_takes_precedence():
    competition, season, _ = competition_with_catalogue()
    huracan = Team.objects.create(competition=competition, name="Huracan")
    source, _ = Source.objects.get_or_create(
        code="football_data",
        defaults={"name": "football-data", "base_url": "https://example.test/"},
    )
    TeamSourceRef.objects.create(
        source=source,
        competition=competition,
        external_id="ARG:Huracan",
        external_name="Huracan",
        team=huracan,
        reconciliation_status=ReconciliationStatus.RESOLVED,
        confidence=1,
    )
    record = replace(
        exact_result(
            season.year,
            datetime(2024, 9, 1, 15, tzinfo=ZoneInfo("Europe/London")),
            home="Incoming unrelated spelling",
            external_id="exact-team-source-ref",
        ),
        home_external_id="ARG:Huracan",
    )

    reconcile_result(source, competition, season, record)

    assert Match.objects.get(season=season).home_team == huracan
    assert TeamSourceRef.objects.filter(source=source, team=huracan).count() == 1


@pytest.mark.django_db
def test_explicit_alias_lookup_uses_normalized_case():
    competition, season, _ = competition_with_catalogue()
    canonical = Team.objects.create(
        competition=competition, name="Manchester City", is_active=True
    )
    source, _ = Source.objects.get_or_create(
        code="football_data",
        defaults={"name": "football-data", "base_url": "https://example.test/"},
    )
    record = exact_result(
        season.year,
        datetime(2024, 9, 1, 15, tzinfo=ZoneInfo("Europe/London")),
        home="mAn CiTy",
        external_id="normalized-explicit-alias",
    )

    reconcile_result(source, competition, season, record)

    ref = TeamSourceRef.objects.get(
        source=source, external_id="ENG Premier League:mAn CiTy"
    )
    assert ref.team == canonical
    assert Match.objects.get(season=season).home_team == canonical


@pytest.mark.django_db
def test_genuinely_different_unknown_team_remains_unmapped():
    competition, season, _ = competition_with_catalogue()
    source, _ = Source.objects.get_or_create(
        code="football_data",
        defaults={"name": "football-data", "base_url": "https://example.test/"},
    )
    record = exact_result(
        season.year,
        datetime(2024, 9, 1, 15, tzinfo=ZoneInfo("Europe/London")),
        home="Genuinely Different Club",
        external_id="genuinely-different-team",
    )

    with pytest.raises(
        HistoricalMappingError,
        match="UNMAPPED_TEAM_IDENTITY:Genuinely Different Club",
    ):
        reconcile_result(source, competition, season, record)

    assert not Team.objects.filter(
        competition=competition, name="Genuinely Different Club"
    ).exists()
    assert not Match.objects.filter(season=season).exists()


@pytest.mark.django_db
def test_repeated_unknown_team_diagnostics_are_bounded_and_deduplicated():
    competition, completed, _ = competition_with_catalogue()
    second = Season.objects.create(
        competition=competition,
        year=2023,
        start_date=date(2023, 8, 1),
        end_date=date(2024, 5, 31),
    )
    records = {
        season.year: [
            exact_result(
                season.year,
                datetime(season.year, 9, 1, 15, tzinfo=ZoneInfo("Europe/London")),
                home="Unknown Historical Club",
                external_id=f"unknown:{season.year}:{index}",
            )
            for index in range(75)
        ]
        for season in (second, completed)
    }
    team_count = Team.objects.filter(competition=competition).count()
    request_historical_bootstrap(competition)

    coverage = process_historical_bootstrap(competition, adapter=FrozenAdapter(records))

    summaries = [
        issue
        for issue in coverage.diagnostics["issues"]
        if issue["reason"] == "UNMAPPED_TEAM_IDENTITY"
    ]
    assert coverage.status == HistoricalCoverage.Status.PARTIAL
    assert len(summaries) == 1
    assert summaries[0]["external_team_name"] == "Unknown Historical Club"
    assert summaries[0]["affected_seasons"] == [2023, 2024]
    assert summaries[0]["count"] == 150
    assert len(coverage.diagnostics["issues"]) == 1
    assert Team.objects.filter(competition=competition).count() == team_count


@pytest.mark.django_db
def test_admin_has_no_direct_enabled_edit_and_command_request_does_not_fetch():
    competition, _, _ = competition_with_catalogue()
    admin = CompetitionAdmin(Competition, AdminSite())
    assert "enabled" in admin.readonly_fields
    assert not admin.list_editable
    output = StringIO()
    with patch("football.providers.football_data.requests.get") as network:
        call_command(
            "bootstrap_football_history",
            competition.pk,
            "--request-only",
            stdout=output,
        )
    assert network.call_count == 0
    competition.refresh_from_db()
    assert competition.enabled is False
    assert '"automatic_retry": false' in output.getvalue()


@pytest.mark.parametrize("key", sorted(EUROPE_COMPETITIONS))
def test_all_eight_europe_mappings_are_explicit(key):
    country, name = key
    competition = Competition(name=name, country=country)
    assert source_contract(competition) == (
        "EUROPE_PENALTYBLOG",
        EUROPE_COMPETITIONS[key],
    )


def test_europe_adapter_normalizes_frozen_penaltyblog_fixture():
    class FrozenRow:
        def to_dict(self):
            return {
                "datetime": datetime(2024, 8, 20, 19, 30),
                "team_home": "Alpha",
                "team_away": "Beta",
                "goals_home": 2,
                "goals_away": 1,
            }

    class FrozenFrame:
        def iterrows(self):
            return iter([(0, FrozenRow())])

    class FrozenScraper:
        def __init__(self, competition, season):
            assert competition == "ENG Premier League"
            assert season == "2024-2025"

        def get_fixtures(self):
            return FrozenFrame()

    competition = Competition(name="Premier League", country="EN")
    season = Season(competition=competition, year=2024)
    adapter = EuropeFootballDataAdapter(competition, scraper_factory=FrozenScraper)
    rows = adapter.records_for_season(season)
    assert len(rows) == 1
    assert rows[0].source_code == "football_data"
    assert rows[0].competition_external_id == "ENG Premier League"
    assert rows[0].kickoff_precision == "EXACT"
    assert rows[0].kickoff.utcoffset() == timedelta(hours=1)
    assert rows[0].provenance["authority"] == "football-data.co.uk"
    assert rows[0].provenance["raw_source_date"] == "2024-08-20"
    assert rows[0].provenance["raw_source_time"] == "19:30:00"
    assert rows[0].provenance["source_timezone_contract"] == SOURCE_TIMEZONE_NAME
    assert rows[0].provenance["normalized_source_kickoff"].endswith("+01:00")
    assert rows[0].provenance["source_season"] == "2024-2025"
    assert adapter.download_count == 1


@pytest.mark.parametrize(
    ("value", "expected_offset"),
    (
        (datetime(2024, 8, 20, 19, 30), timedelta(hours=1)),
        (datetime(2024, 12, 20, 19, 30), timedelta(0)),
        (datetime(2024, 10, 27, 0, 30), timedelta(hours=1)),
        (datetime(2024, 10, 27, 2, 30), timedelta(0)),
    ),
)
def test_football_data_naive_time_uses_london_dst_contract(value, expected_offset):
    kickoff, precision, provenance = _technical_kickoff(value)
    assert precision == "EXACT"
    assert kickoff.utcoffset() == expected_offset
    assert provenance["source_timezone_contract"] == "Europe/London"
    assert provenance["normalized_source_kickoff"] == kickoff.isoformat()


def test_football_data_aware_datetime_is_not_reinterpreted():
    aware = datetime(2024, 8, 20, 19, 30, tzinfo=ZoneInfo("UTC"))
    kickoff, precision, provenance = _technical_kickoff(aware)
    assert precision == "EXACT"
    assert kickoff == aware
    assert kickoff.hour == 19
    assert provenance["source_datetime_was_aware"] is True


def test_provider_parser_failure_is_not_classified_as_source_unavailable():
    class BrokenScraper:
        def __init__(self, competition, season):
            del competition, season

        def get_fixtures(self):
            raise HistoricalParserError("FROZEN_PARSER_FAILURE")

    competition = Competition(name="Premier League", country="EN")
    season = Season(competition=competition, year=2024)
    adapter = EuropeFootballDataAdapter(competition, scraper_factory=BrokenScraper)
    with pytest.raises(HistoricalParserError, match="FROZEN_PARSER_FAILURE"):
        adapter.records_for_season(season)


@pytest.mark.django_db
@pytest.mark.parametrize("key", sorted(DIRECT_COMPETITIONS))
def test_direct_argentina_brazil_usa_csv_is_frozen_and_source_aware(key):
    country, name = key
    competition = Competition.objects.create(
        name=name, country=country, competition_type="League"
    )
    season = Season.objects.create(
        competition=competition,
        year=2024,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )
    payload = "Season,Date,Home,Away,HG,AG\n2024,20/08/2024,Alpha,Beta,1,0\n"
    adapter = DirectFootballDataCSVAdapter(
        competition, http_get=lambda url: payload.encode()
    )
    rows = adapter.records_for_season(season)
    assert len(rows) == 1
    assert rows[0].source_code == "football_data"
    assert rows[0].kickoff_precision == "DATE_ONLY"
    assert rows[0].kickoff.tzinfo == ZoneInfo("Europe/London")
    assert rows[0].provenance["raw_source_time"] == ""
    assert rows[0].provenance["source_timezone_contract"] == "Europe/London"
    assert rows[0].provenance["url"] == DIRECT_COMPETITIONS[key][1]
    assert adapter.download_count == 1


@pytest.mark.django_db
def test_direct_csv_time_uses_same_london_source_contract():
    competition = Competition.objects.create(
        name="Major League Soccer", country="US", competition_type="League"
    )
    season = Season.objects.create(
        competition=competition,
        year=2024,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )
    payload = (
        "Season,Date,Time,Home,Away,HG,AG\n" "2024,20/08/2024,19:30,Alpha,Beta,1,0\n"
    )
    adapter = DirectFootballDataCSVAdapter(
        competition, http_get=lambda url: payload.encode()
    )

    row = adapter.records_for_season(season)[0]

    assert row.kickoff_precision == "EXACT"
    assert row.kickoff.utcoffset() == timedelta(hours=1)
    assert row.provenance["raw_source_date"] == "20/08/2024"
    assert row.provenance["raw_source_time"] == "19:30"
    assert row.provenance["source_timezone_contract"] == "Europe/London"


@pytest.mark.django_db
def test_direct_csv_partition_uses_non_overlapping_canonical_season_dates():
    competition = Competition.objects.create(
        name="Liga Profesional Argentina",
        country="AR",
        competition_type="League",
    )
    season_2016 = Season.objects.create(
        competition=competition,
        year=2016,
        start_date=date(2016, 8, 26),
        end_date=date(2017, 6, 27),
    )
    season_2017 = Season.objects.create(
        competition=competition,
        year=2017,
        start_date=date(2017, 8, 25),
        end_date=date(2018, 5, 15),
    )
    payload = "\n".join(
        (
            "Season,Date,Home,Away,HG,AG",
            "2016,01/03/2016,Early,Excluded,1,0",
            "2016/2017,01/09/2016,Alpha,Beta,2,1",
            "2016/2017,01/03/2017,Gamma,Delta,0,0",
            "2017/2018,01/09/2017,Epsilon,Zeta,3,2",
        )
    )
    adapter = DirectFootballDataCSVAdapter(
        competition, http_get=lambda url: payload.encode()
    )

    rows_2016 = adapter.records_for_season(season_2016)
    rows_2017 = adapter.records_for_season(season_2017)
    repeated_2016 = adapter.records_for_season(season_2016)

    assert [row.provenance["source_season"] for row in rows_2016] == [
        "2016/2017",
        "2016/2017",
    ]
    assert [row.provenance["source_season"] for row in rows_2017] == ["2017/2018"]
    assert {row.external_id for row in rows_2016}.isdisjoint(
        {row.external_id for row in rows_2017}
    )
    assert [row.external_id for row in repeated_2016] == [
        row.external_id for row in rows_2016
    ]
    assert all(row.home_name != "Early" for row in [*rows_2016, *rows_2017])


@pytest.mark.django_db
def test_direct_csv_skips_explicit_non_final_row_with_bounded_diagnostics():
    competition = Competition.objects.create(
        name="Serie A", country="BR", competition_type="League"
    )
    season = Season.objects.create(
        competition=competition,
        year=2016,
        start_date=date(2016, 1, 1),
        end_date=date(2016, 12, 31),
    )
    payload = "\n".join(
        (
            "Season,Date,Home,Away,HG,AG,FTR",
            "2016,01/05/2016,Alpha,Beta,2,1,H",
            "2016,02/05/2016,Gamma,Delta,, ,",
        )
    )
    adapter = DirectFootballDataCSVAdapter(
        competition, http_get=lambda url: payload.encode()
    )

    rows = adapter.records_for_season(season)

    assert len(rows) == 1
    assert rows[0].home_name == "Alpha"
    assert adapter.season_diagnostics[2016]["non_final_rows_skipped"] == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("home_score", "away_score", "result_claim", "reason"),
    (
        ("", "", "H", "SOURCE_ROW_FINAL_RESULT_WITHOUT_SCORES"),
        ("1", "", "", "SOURCE_ROW_PARTIAL_FULL_TIME_SCORE"),
    ),
)
def test_direct_csv_inconsistent_missing_score_fails_closed(
    home_score, away_score, result_claim, reason
):
    competition = Competition.objects.create(
        name="Serie A", country="BR", competition_type="League"
    )
    season = Season.objects.create(
        competition=competition,
        year=2016,
        start_date=date(2016, 1, 1),
        end_date=date(2016, 12, 31),
    )
    payload = (
        "Season,Date,Home,Away,HG,AG,FTR\n"
        f"2016,01/05/2016,Alpha,Beta,{home_score},{away_score},{result_claim}\n"
    )
    adapter = DirectFootballDataCSVAdapter(
        competition, http_get=lambda url: payload.encode()
    )

    with pytest.raises(HistoricalParserError, match=reason):
        adapter.records_for_season(season)


@pytest.mark.django_db
def test_brazil_leading_source_gap_does_not_block_complete_supported_window():
    competition = Competition.objects.create(
        name="Serie A", country="BR", competition_type="League", enabled=False
    )
    Team.objects.create(competition=competition, name="Alpha")
    Team.objects.create(competition=competition, name="Beta")
    for year in (2010, 2011, 2012):
        Season.objects.create(
            competition=competition,
            year=year,
            start_date=date(year, 1, 1),
            end_date=date(year, 12, 31),
        )
    payload = chr(10).join(
        (
            "Season,Date,Home,Away,HG,AG",
            "2012,01/05/2012,Alpha,Beta,2,1",
            "",
        )
    )
    adapter = DirectFootballDataCSVAdapter(
        competition, http_get=lambda url: payload.encode()
    )
    request_historical_bootstrap(competition, activate=True)

    coverage = process_historical_bootstrap(competition, adapter=adapter)

    competition.refresh_from_db()
    assert coverage.status == HistoricalCoverage.Status.COMPLETE
    assert coverage.required_seasons == [2012]
    assert coverage.covered_seasons == [2012]
    assert coverage.unresolved_seasons == []
    assert competition.enabled is True
    assert coverage.reason == "ALL_SOURCE_SUPPORTED_COMPLETED_SEASONS_COVERED"

    outside = [
        issue["season"]
        for issue in coverage.diagnostics["issues"]
        if issue["reason"] == "SOURCE_OUTSIDE_AVAILABLE_HISTORY_WINDOW"
    ]
    assert outside == [2010, 2011]
    assert historical_coverage_is_current(competition, coverage)

    # A shortened persisted requirement is valid only while the omitted
    # catalogue prefix remains explicitly audited as source-unavailable.
    coverage.diagnostics = {"issues": []}
    coverage.save(update_fields=["diagnostics", "modified"])
    assert not historical_coverage_is_current(competition, coverage)


@pytest.mark.django_db
def test_internal_source_gap_still_blocks_complete():
    competition = Competition.objects.create(
        name="Serie A", country="BR", competition_type="League", enabled=False
    )
    Team.objects.create(competition=competition, name="Alpha")
    Team.objects.create(competition=competition, name="Beta")

    for year in (2010, 2011, 2012, 2013, 2014):
        Season.objects.create(
            competition=competition,
            year=year,
            start_date=date(year, 1, 1),
            end_date=date(year, 12, 31),
        )

    payload = chr(10).join(
        (
            "Season,Date,Home,Away,HG,AG",
            "2012,01/05/2012,Alpha,Beta,2,1",
            "2014,01/05/2014,Alpha,Beta,1,1",
            "",
        )
    )
    adapter = DirectFootballDataCSVAdapter(
        competition, http_get=lambda url: payload.encode()
    )
    request_historical_bootstrap(competition, activate=True)

    coverage = process_historical_bootstrap(competition, adapter=adapter)

    competition.refresh_from_db()
    assert coverage.status == HistoricalCoverage.Status.PARTIAL
    assert coverage.required_seasons == [2012, 2013, 2014]
    assert coverage.covered_seasons == [2012, 2014]
    assert coverage.unresolved_seasons == [2013]
    assert competition.enabled is False
    assert not historical_coverage_is_current(competition, coverage)


@pytest.mark.django_db
def test_mls_complete_direct_source_can_pass_the_data_driven_gate():
    competition = Competition.objects.create(
        name="Major League Soccer",
        country="US",
        competition_type="League",
        enabled=False,
    )
    Team.objects.create(competition=competition, name="Alpha")
    Team.objects.create(competition=competition, name="Beta")
    for year in (2012, 2013):
        Season.objects.create(
            competition=competition,
            year=year,
            start_date=date(year, 1, 1),
            end_date=date(year, 12, 31),
        )
    payload = "\n".join(
        (
            "Season,Date,Home,Away,HG,AG",
            "2012,01/05/2012,Alpha,Beta,2,1",
            "2013,01/05/2013,Alpha,Beta,1,1",
        )
    )
    adapter = DirectFootballDataCSVAdapter(
        competition, http_get=lambda url: payload.encode()
    )
    request_historical_bootstrap(competition, activate=True)

    coverage = process_historical_bootstrap(competition, adapter=adapter)

    competition.refresh_from_db()
    assert coverage.status == HistoricalCoverage.Status.COMPLETE
    assert coverage.covered_seasons == [2012, 2013]
    assert competition.enabled is True
