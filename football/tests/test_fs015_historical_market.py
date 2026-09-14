import json
from datetime import date, datetime, timedelta
from datetime import timezone as datetime_timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from football.historical.service import STRATEGY_VERSION as SPORTING_STRATEGY
from football.historical.service import request_historical_bootstrap
from football.historical_market.contracts import (
    CachedSource,
    HistoricalMarketScopeError,
    PackageConflict,
    PackageIntegrityError,
    SourceSchemaError,
    SourceSpec,
)
from football.historical_market.current_season import (
    _resolve_team,
    recover_current_season,
)
from football.historical_market.package import (
    build_package_payload,
    export_package,
    import_package,
)
from football.historical_market.promotion import (
    BASELINE_PROMOTION_IDENTITY,
    market_baseline_is_promoted,
    promote_market_baseline,
)
from football.historical_market.service import (
    historical_market_is_current,
    historical_market_is_terminal,
    historical_market_required_years,
    ingest_completed_season,
    market_required_matches,
)
from football.historical_market.source import (
    PRICE_GROUPS,
    acquire_source,
    parse_market_file,
    select_price_triplet,
    source_spec,
)
from football.maintenance import (
    run_historical_bootstrap_maintenance,
    run_historical_market_maintenance,
)
from football.models import (
    Bookmaker,
    Competition,
    HistoricalCoverage,
    HistoricalMarketCoverage,
    HistoricalMarketEvidence,
    HistoricalMarketUnavailable,
    MaintenanceRun,
    Match,
    MatchSourceRef,
    OddsMarket,
    OddsObservation,
    ReconciliationStatus,
    Season,
    Source,
    Team,
    TeamSourceRef,
)
from football.providers.football_data import _external_id

pytestmark = pytest.mark.django_db


def _competition(
    *, name="Premier League", country="EN", enabled=True, year=2024, current=False
):
    competition = Competition.objects.create(
        name=name,
        country=country,
        competition_type="League",
        enabled=enabled,
    )
    season = Season.objects.create(
        competition=competition,
        year=year,
        start_date=date(year, 1 if country in {"AR", "BR"} else 8, 1),
        end_date=(
            date(year, 12, 31) if country in {"AR", "BR"} else date(year + 1, 6, 30)
        ),
        is_current=current,
    )
    return competition, season


def _football_data_source():
    return Source.objects.get_or_create(
        code="football_data",
        defaults={
            "name": "football-data.co.uk",
            "base_url": "https://www.football-data.co.uk/",
        },
    )[0]


def _teams(competition, home="Arsenal", away="Chelsea", *, refs=True):
    source = _football_data_source()
    home_team = Team.objects.create(competition=competition, name=home)
    away_team = Team.objects.create(competition=competition, name=away)
    if refs:
        external = source_spec_external(competition)
        for team, name in ((home_team, home), (away_team, away)):
            TeamSourceRef.objects.create(
                source=source,
                competition=competition,
                team=team,
                external_id=f"{external}:{name}",
                external_name=name,
                reconciliation_status=ReconciliationStatus.RESOLVED,
                confidence=1,
            )
    return home_team, away_team


def source_spec_external(competition):
    class Stub:
        year = 2024

    return source_spec(competition, Stub()).external_competition


def _match(season, home, away, *, scores=(2, 1), status="FT"):
    return Match.objects.create(
        season=season,
        home_team=home,
        away_team=away,
        kickoff=datetime(2024, 8, 10, 14, tzinfo=datetime_timezone.utc),
        kickoff_timezone="UTC",
        status_short=status,
        status_long="Match Finished" if status == "FT" else "",
        outcome=(Match.OUTCOME_HOME if scores == (2, 1) else ""),
        home_score=scores[0],
        away_score=scores[1],
        fulltime_home_score=scores[0],
        fulltime_away_score=scores[1],
    )


def _europe_csv(*, home="Arsenal", away="Chelsea", prices=None, scores=(2, 1)):
    prices = prices or {"PSCH": "2.10", "PSCD": "3.20", "PSCA": "3.40"}
    header = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", *prices]
    values = [
        "10/08/2024",
        home,
        away,
        str(scores[0]),
        str(scores[1]),
        *prices.values(),
    ]
    return (",".join(header) + "\n" + ",".join(values) + "\n").encode()


def _direct_csv():
    return (
        "Season,Date,Home,Away,HG,AG,Res,AvgCH,AvgCD,AvgCA\n"
        "2023,10/08/2023,Old Home,Old Away,1,0,H,2.0,3.0,4.0\n"
        "2024,10/08/2024,River Plate,Boca Juniors,2,1,H,2.1,3.1,3.8\n"
    ).encode()


def _write_cache(competition, season, root, payload, *, current=False):
    spec = source_spec(competition, season, cache_root=root, current_cache=current)
    path = Path(spec.cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return spec


def _sporting_current(competition, required_seasons, *, omitted_seasons=()):
    return HistoricalCoverage.objects.create(
        competition=competition,
        status=HistoricalCoverage.Status.COMPLETE,
        strategy_version=SPORTING_STRATEGY,
        required_seasons=[season.year for season in required_seasons],
        covered_seasons=[season.year for season in required_seasons],
        unresolved_seasons=[],
        diagnostics={
            "issues": [
                {
                    "season": season.year,
                    "reason": "SOURCE_OUTSIDE_AVAILABLE_HISTORY_WINDOW",
                }
                for season in omitted_seasons
            ]
        },
    )


def _promote_baseline():
    assert promote_market_baseline() in {"CREATED", "ALREADY_COMPLETE"}
    assert market_baseline_is_promoted()


@pytest.mark.parametrize("index", range(len(PRICE_GROUPS)))
def test_every_approved_price_group_is_detected_with_frozen_semantics(index):
    group, columns, semantics = PRICE_GROUPS[index]
    row = dict(zip(columns, ("2.1", "3.2", "3.4"), strict=True))
    selected = select_price_triplet(row, list(row))
    assert selected.group == group
    assert selected.time_semantics == semantics


def test_price_selection_prefers_closing_and_never_mixes_partial_groups():
    row = {
        "PSCH": "2.0",
        "PSCD": "3.0",
        "PSCA": "4.0",
        "B365H": "2.2",
        "B365D": "3.2",
        "B365A": "3.8",
    }
    assert select_price_triplet(row, list(row)).group == "PINNACLE_CLOSING"
    partial = {"PSCH": "2", "PSCD": "3", "B365A": "4"}
    assert select_price_triplet(partial, list(partial)) is None


def test_parser_supports_old_pre_only_and_direct_multi_season_filtering():
    old = _europe_csv(prices={"B365H": "2.1", "B365D": "3.2", "B365A": "3.4"})
    spec = SourceSpec("EUROPE_SEASON_FILE", "ENG Premier League", "2024-25", "x", "x")
    parsed = parse_market_file(
        CachedSource(spec, old, "a" * 64, False), type("S", (), {"year": 2024})()
    )
    assert parsed.schema_family == "EUROPE_SEASON_FILE"
    assert parsed.rows[0].price.group == "BET365_PRE"

    direct_spec = SourceSpec("DIRECT_MULTI_SEASON_CSV", "ARG", "2024", "x", "x")
    direct = parse_market_file(
        CachedSource(direct_spec, _direct_csv(), "b" * 64, False),
        type("S", (), {"year": 2024})(),
    )
    assert direct.schema_family == "DIRECT_MULTI_SEASON_CSV"
    assert direct.source_rows == 1
    assert direct.rows[0].home_name == "River Plate"


def test_live_fetch_ignores_old_cache_and_cache_only_never_calls_network(tmp_path):
    spec = SourceSpec(
        "EUROPE_SEASON_FILE",
        "ENG Premier League",
        "2024-25",
        "https://x",
        str(tmp_path / "x.csv"),
    )
    old_payload = _europe_csv(scores=(1, 0))
    Path(spec.cache_path).write_bytes(old_payload)
    new_payload = _europe_csv(scores=(2, 1))
    network = Mock(return_value=new_payload)
    first = acquire_source(spec, http_get=network)
    assert first.downloaded is True
    assert first.payload == new_payload
    assert first.provenance_locator == spec.url
    assert len(first.checksum) == 64
    network.assert_called_once_with(spec.url)
    assert Path(spec.cache_path).read_bytes() == old_payload
    second_network = Mock(side_effect=AssertionError("network called"))
    second = acquire_source(spec, cache_only=True, http_get=second_network)
    assert second.downloaded is False
    assert second.payload == old_payload
    assert second.provenance_locator == spec.cache_path
    second_network.assert_not_called()

    Path(spec.cache_path).unlink()
    assert parse_market_file(first, type("S", (), {"year": 2024})()).source_rows == 1


def test_completed_import_is_idempotent_and_unavailable_is_market_specific(tmp_path):
    competition, season = _competition()
    _sporting_current(competition, [season])
    home, away = _teams(competition)
    match = _match(season, home, away)
    source = _football_data_source()
    external = source_spec_external(competition)
    MatchSourceRef.objects.create(
        source=source,
        match=match,
        external_id=_external_id(
            external, season.year, date(2024, 8, 10), "Arsenal", "Chelsea"
        ),
        external_label="Arsenal - Chelsea",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    _write_cache(competition, season, tmp_path, _europe_csv())
    first = ingest_completed_season(
        competition, season, cache_only=True, cache_root=tmp_path
    )
    assert first["status"] == HistoricalMarketCoverage.Status.COMPLETE
    evidence = HistoricalMarketEvidence.objects.get(match=match)
    assert evidence.evidence_class == "SYNTHETIC_TIME_RESEARCH_ONLY"
    assert evidence.timestamp_is_imputed is True
    second = ingest_completed_season(
        competition, season, cache_only=True, cache_root=tmp_path
    )
    assert second["outcome"] == "NO_WORK"
    assert HistoricalMarketEvidence.objects.count() == 1

    other_home = Team.objects.create(competition=competition, name="Everton")
    other_away = Team.objects.create(competition=competition, name="Liverpool")
    unavailable_match = Match.objects.create(
        season=season,
        home_team=other_home,
        away_team=other_away,
        kickoff=datetime(2024, 8, 11, 14, tzinfo=datetime_timezone.utc),
        status_short="FT",
        status_long="Match Finished",
        outcome=Match.OUTCOME_DRAW,
        home_score=0,
        away_score=0,
    )
    HistoricalMarketUnavailable.objects.create(
        match=unavailable_match,
        source=source,
        reason=HistoricalMarketUnavailable.SOURCE_NO_COMPLETE_1X2,
        source_file="x.csv",
        source_file_checksum="c" * 64,
        source_row_identity="r",
    )
    neither_home = Team.objects.create(competition=competition, name="Fulham")
    neither_away = Team.objects.create(competition=competition, name="Brentford")
    neither_match = Match.objects.create(
        season=season,
        home_team=neither_home,
        away_team=neither_away,
        kickoff=datetime(2024, 8, 12, 14, tzinfo=datetime_timezone.utc),
        status_short="FT",
        status_long="Match Finished",
        outcome=Match.OUTCOME_AWAY,
        home_score=0,
        away_score=1,
    )
    usable, skipped = market_required_matches(Match.objects.filter(season=season))
    assert list(usable) == [match]
    assert skipped == {
        "NO_HISTORICAL_MARKET_STATE": 1,
        "SOURCE_NO_COMPLETE_1X2": 1,
    }
    assert Match.objects.filter(season=season).count() == len(usable) + sum(
        skipped.values()
    )
    unavailable_match.refresh_from_db()
    assert unavailable_match.outcome == Match.OUTCOME_DRAW
    neither_match.refresh_from_db()
    assert neither_match.outcome == Match.OUTCOME_AWAY


def test_malformed_relevant_row_keeps_completed_season_partial(tmp_path):
    competition, season = _competition()
    _sporting_current(competition, [season])
    arsenal, chelsea = _teams(competition)
    everton, liverpool = _teams(competition, "Everton", "Liverpool")
    complete_match = _match(season, arsenal, chelsea)
    malformed_match = Match.objects.create(
        season=season,
        home_team=everton,
        away_team=liverpool,
        kickoff=datetime(2024, 8, 11, 14, tzinfo=datetime_timezone.utc),
        kickoff_timezone="UTC",
        status_short="FT",
        status_long="Match Finished",
        outcome=Match.OUTCOME_HOME,
        home_score=1,
        away_score=0,
    )
    payload = _europe_csv().rstrip() + (
        b"\n11/08/2024,Everton,Liverpool,,0,2.2,3.1,3.5\n"
    )
    _write_cache(competition, season, tmp_path, payload)

    result = ingest_completed_season(
        competition, season, cache_only=True, cache_root=tmp_path
    )

    coverage = HistoricalMarketCoverage.objects.get(season=season)
    accounting = coverage.diagnostics["accounting"]
    assert result["status"] == HistoricalMarketCoverage.Status.PARTIAL
    assert result["unresolved_rows"] == 1
    assert accounting["structural_invalid_rows"] == 1
    assert accounting["classified_source_rows"] == 2
    assert historical_market_is_current(competition, season) is False
    assert HistoricalMarketEvidence.objects.filter(match=complete_match).exists()
    assert not HistoricalMarketEvidence.objects.filter(match=malformed_match).exists()
    assert not HistoricalMarketUnavailable.objects.filter(
        match=malformed_match
    ).exists()


def test_all_relevant_rows_malformed_are_retried_after_source_correction(tmp_path):
    competition, season = _competition()
    _sporting_current(competition, [season])
    home, away = _teams(competition)
    match = _match(season, home, away)
    malformed = _europe_csv().replace(b",2,1,", b",,1,")
    _write_cache(competition, season, tmp_path, malformed)

    first = ingest_completed_season(
        competition, season, cache_only=True, cache_root=tmp_path
    )

    coverage = HistoricalMarketCoverage.objects.get(season=season)
    assert first["status"] == HistoricalMarketCoverage.Status.PARTIAL
    assert first["valid_rows"] == 0
    assert first["invalid_rows"] == 1
    assert first["unresolved_rows"] == 1
    assert historical_market_is_current(competition, season) is False
    assert MatchSourceRef.objects.filter(match=match).count() == 0
    assert HistoricalMarketEvidence.objects.count() == 0

    _write_cache(competition, season, tmp_path, _europe_csv())
    retried = ingest_completed_season(
        competition, season, cache_only=True, cache_root=tmp_path
    )

    coverage.refresh_from_db()
    assert retried["status"] == HistoricalMarketCoverage.Status.COMPLETE
    assert retried["outcome"] != "NO_WORK"
    assert coverage.attempt_count == 2
    assert historical_market_is_current(competition, season)
    assert HistoricalMarketEvidence.objects.filter(match=match).exists()


def test_structural_accounting_cannot_be_current_or_terminal():
    competition, season = _competition()
    _sporting_current(competition, [season])
    HistoricalMarketCoverage.objects.create(
        competition=competition,
        season=season,
        source=_football_data_source(),
        status=HistoricalMarketCoverage.Status.COMPLETE,
        strategy_version="fs015-football-data-v1",
        source_rows=1,
        valid_rows=0,
        invalid_rows=1,
        unresolved_rows=0,
        diagnostics={
            "accounting": {
                "source_artifact_rows": 0,
                "structural_invalid_rows": 1,
                "classified_source_rows": 1,
            }
        },
    )

    assert historical_market_is_current(competition, season) is False
    assert historical_market_is_terminal(competition) is False


def test_safely_classified_malformed_artifacts_are_audited_not_persisted(tmp_path):
    competition, season = _competition()
    _sporting_current(competition, [season])
    home, away = _teams(competition)
    match = _match(season, home, away)
    _teams(competition, "Never Played Home", "Never Played Away")
    payload = _europe_csv().rstrip() + (
        b"\n11/08/2024,Never Played Home,Never Played Away,,,2.2,3.1,3.5" b"\n,,,,,,,\n"
    )
    _write_cache(competition, season, tmp_path, payload)

    result = ingest_completed_season(
        competition, season, cache_only=True, cache_root=tmp_path
    )

    coverage = HistoricalMarketCoverage.objects.get(season=season)
    accounting = coverage.diagnostics["accounting"]
    assert result["status"] == HistoricalMarketCoverage.Status.COMPLETE
    assert result["invalid_rows"] == 2
    assert accounting == {
        "valid_rows": 1,
        "classified_rows": 1,
        "classified_valid_rows": 1,
        "source_artifact_rows": 2,
        "structural_invalid_rows": 0,
        "classified_source_rows": 3,
    }
    assert coverage.diagnostics["invalid_outcomes"] == {
        "MALFORMED_ROW_OUTSIDE_CANONICAL_POOL": 1,
        "SOURCE_ARTIFACT_EMPTY_MATCH_FIELDS": 1,
    }
    assert len(coverage.diagnostics["invalid_issues"]) == 2
    assert historical_market_is_current(competition, season)
    assert list(Match.objects.values_list("pk", flat=True)) == [match.pk]
    assert HistoricalMarketEvidence.objects.filter(match=match).exists()
    assert MatchSourceRef.objects.count() == 1


def test_completed_source_row_outside_pool_is_counted_not_persisted(tmp_path):
    competition, season = _competition()
    _sporting_current(competition, [season])
    _teams(competition)
    _write_cache(competition, season, tmp_path, _europe_csv())
    result = ingest_completed_season(
        competition, season, cache_only=True, cache_root=tmp_path
    )
    assert result["outside_canonical_pool_rows"] == 1
    assert result["status"] == HistoricalMarketCoverage.Status.COMPLETE
    assert Match.objects.count() == 0
    assert HistoricalMarketUnavailable.objects.count() == 0


def test_completed_no_price_row_persists_only_market_unavailable(tmp_path):
    competition, season = _competition()
    _sporting_current(competition, [season])
    home, away = _teams(competition)
    match = _match(season, home, away)
    source = _football_data_source()
    external = source_spec_external(competition)
    MatchSourceRef.objects.create(
        source=source,
        match=match,
        external_id=_external_id(
            external, season.year, date(2024, 8, 10), "Arsenal", "Chelsea"
        ),
        external_label="Arsenal - Chelsea",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    payload = _europe_csv(prices={"PSCH": "2.1", "PSCD": "", "PSCA": "3.4"})
    _write_cache(competition, season, tmp_path, payload)
    result = ingest_completed_season(
        competition, season, cache_only=True, cache_root=tmp_path
    )
    assert result["status"] == HistoricalMarketCoverage.Status.COMPLETE
    assert result["unavailable_rows"] == 1
    assert HistoricalMarketEvidence.objects.count() == 0
    assert HistoricalMarketUnavailable.objects.get(match=match).reason == (
        "SOURCE_NO_COMPLETE_1X2"
    )
    match.refresh_from_db()
    assert (match.home_score, match.away_score, match.outcome) == (2, 1, "HOME")


def test_current_recovery_is_dry_by_default_then_additive_and_idempotent(tmp_path):
    competition, season = _competition(year=2024, current=True)
    home, away = _teams(competition)
    existing = _match(season, home, away)
    api = Source.objects.get(code="api_football")
    bookmaker = Bookmaker.objects.create(source=api, external_id="8", name="Bet365")
    market = OddsMarket.objects.create(source=api, external_id="1", name="1X2")
    OddsObservation.objects.create(
        match=existing,
        source=api,
        bookmaker=bookmaker,
        market=market,
        home=2,
        draw=3,
        away=4,
        observed_at=datetime(2024, 8, 10, 12, tzinfo=datetime_timezone.utc),
    )
    payload = (
        _europe_csv().rstrip() + b"\n11/08/2024,Everton,Liverpool,1,0,2.2,3.1,3.5\n"
    )
    Team.objects.create(competition=competition, name="Everton")
    Team.objects.create(competition=competition, name="Liverpool")
    _write_cache(competition, season, tmp_path, payload, current=True)
    planned = recover_current_season(
        competition, season, cache_only=True, cache_root=tmp_path
    )
    assert planned["mode"] == "DRY_RUN"
    assert Match.objects.count() == 1
    assert HistoricalMarketEvidence.objects.count() == 0
    applied = recover_current_season(
        competition, season, apply=True, cache_only=True, cache_root=tmp_path
    )
    assert applied["counts"]["CREATE_MISSING_MATCH"] == 1
    assert Match.objects.count() == 2
    assert HistoricalMarketEvidence.objects.count() == 2
    assert OddsObservation.objects.count() == 1
    repeated = recover_current_season(
        competition, season, apply=True, cache_only=True, cache_root=tmp_path
    )
    assert repeated["counts"]["NO_WORK"] == 2
    assert Match.objects.count() == 2
    assert HistoricalMarketEvidence.objects.count() == 2


def test_current_recovery_conflicts_preserve_canonical_result_and_market(tmp_path):
    competition, season = _competition(year=2024, current=True)
    home, away = _teams(competition)
    match = _match(season, home, away, scores=(3, 0))
    source = _football_data_source()
    HistoricalMarketEvidence.objects.create(
        match=match,
        source=source,
        home_price=Decimal("9.0"),
        draw_price=Decimal("8.0"),
        away_price=Decimal("7.0"),
        selected_group="PINNACLE_CLOSING",
        time_semantics="ASSUMED_T30M",
        source_competition="ENG Premier League",
        source_season="2024-25",
        source_file="old.csv",
        source_file_checksum="a" * 64,
        source_row_identity="old",
    )
    _write_cache(competition, season, tmp_path, _europe_csv(), current=True)
    result = recover_current_season(
        competition,
        season,
        apply=True,
        cache_only=True,
        cache_root=tmp_path,
    )
    assert result["counts"] == {"RESULT_CONFLICT": 1}
    match.refresh_from_db()
    evidence = HistoricalMarketEvidence.objects.get(match=match)
    assert (match.home_score, match.away_score) == (3, 0)
    assert evidence.home_price == Decimal("9.0000")


def test_current_exact_match_ref_wins_over_kickoff_drift(tmp_path):
    competition, season = _competition(year=2024, current=True)
    home, away = _teams(competition)
    match = Match.objects.create(
        season=season,
        home_team=home,
        away_team=away,
        kickoff=datetime(2024, 8, 20, 14, tzinfo=datetime_timezone.utc),
        kickoff_timezone="UTC",
        status_short="FT",
        status_long="Match Finished",
        outcome=Match.OUTCOME_HOME,
        home_score=2,
        away_score=1,
        fulltime_home_score=2,
        fulltime_away_score=1,
    )
    source = _football_data_source()
    MatchSourceRef.objects.create(
        source=source,
        match=match,
        external_id=_external_id(
            source_spec_external(competition),
            season.year,
            date(2024, 8, 10),
            "Arsenal",
            "Chelsea",
        ),
        external_label="Arsenal - Chelsea",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    _write_cache(competition, season, tmp_path, _europe_csv(), current=True)

    result = recover_current_season(
        competition, season, apply=True, cache_only=True, cache_root=tmp_path
    )

    assert result["counts"]["CREATE_HISTORICAL_1X2"] == 1
    assert Match.objects.count() == 1
    assert HistoricalMarketEvidence.objects.get().match_id == match.pk


def test_current_incompatible_exact_match_ref_fails_closed(tmp_path):
    competition, season = _competition(year=2024, current=True)
    home, away = _teams(competition)
    incompatible = _match(season, away, home)
    source = _football_data_source()
    ref = MatchSourceRef.objects.create(
        source=source,
        match=incompatible,
        external_id=_external_id(
            source_spec_external(competition),
            season.year,
            date(2024, 8, 10),
            "Arsenal",
            "Chelsea",
        ),
        external_label="Arsenal - Chelsea",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    _write_cache(competition, season, tmp_path, _europe_csv(), current=True)

    result = recover_current_season(
        competition, season, apply=True, cache_only=True, cache_root=tmp_path
    )

    assert result["counts"] == {"MATCH_SOURCE_REF_CONFLICT": 1}
    assert Match.objects.count() == 1
    ref.refresh_from_db()
    assert ref.match_id == incompatible.pk
    assert HistoricalMarketEvidence.objects.count() == 0


def test_current_market_conflict_does_not_overwrite_existing_evidence(tmp_path):
    competition, season = _competition(year=2024, current=True)
    home, away = _teams(competition)
    match = _match(season, home, away)
    source = _football_data_source()
    HistoricalMarketEvidence.objects.create(
        match=match,
        source=source,
        home_price=Decimal("9.0"),
        draw_price=Decimal("8.0"),
        away_price=Decimal("7.0"),
        selected_group="PINNACLE_CLOSING",
        time_semantics="ASSUMED_T30M",
        source_competition="ENG Premier League",
        source_season="2024-25",
        source_file="old.csv",
        source_file_checksum="a" * 64,
        source_row_identity="old",
    )
    _write_cache(competition, season, tmp_path, _europe_csv(), current=True)
    result = recover_current_season(
        competition,
        season,
        apply=True,
        cache_only=True,
        cache_root=tmp_path,
    )
    assert result["counts"]["HISTORICAL_MARKET_CONFLICT"] == 1
    assert HistoricalMarketEvidence.objects.get(match=match).home_price == Decimal(
        "9.0000"
    )


def test_current_direct_file_cannot_leak_another_season(tmp_path):
    competition, season = _competition(
        name="Liga Profesional Argentina", country="AR", year=2024, current=True
    )
    for name in ("River Plate", "Boca Juniors"):
        Team.objects.create(competition=competition, name=name)
    _write_cache(competition, season, tmp_path, _direct_csv(), current=True)
    result = recover_current_season(
        competition, season, cache_only=True, cache_root=tmp_path
    )
    assert result["source_rows"] == 1
    assert result["valid_rows"] == 1


def test_current_dry_run_rolls_back_even_source_and_source_refs(tmp_path):
    competition, season = _competition(year=2024, current=True)
    Team.objects.create(competition=competition, name="Arsenal")
    Team.objects.create(competition=competition, name="Chelsea")
    _write_cache(competition, season, tmp_path, _europe_csv(), current=True)
    assert not Source.objects.filter(code="football_data").exists()
    recover_current_season(competition, season, cache_only=True, cache_root=tmp_path)
    assert not Source.objects.filter(code="football_data").exists()
    assert TeamSourceRef.objects.filter(source__code="football_data").count() == 0
    assert HistoricalMarketEvidence.objects.count() == 0
    applied = recover_current_season(
        competition, season, apply=True, cache_only=True, cache_root=tmp_path
    )
    assert applied["counts"]["CREATE_MISSING_MATCH"] == 1
    assert Match.objects.count() == 1
    assert HistoricalMarketEvidence.objects.count() == 1


@pytest.mark.parametrize(
    ("country", "competition_name", "external", "team_id"),
    [
        ("EN", "Premier League", "Coventry", 59),
        ("PT", "Primeira Liga", "Academico Viseu", 429),
        ("BR", "Serie A", "Remo", 428),
    ],
)
def test_known_exact_current_names_create_refs_to_the_existing_canonical_team(
    country, competition_name, external, team_id
):
    competition, _ = _competition(name=competition_name, country=country)
    expected = Team.objects.create(id=team_id, competition=competition, name=external)
    source = _football_data_source()
    team, basis, created = _resolve_team(source, competition, external, apply=True)
    assert (team, basis, created) == (expected, "EXACT_CANONICAL_NAME", False)
    assert (
        TeamSourceRef.objects.get(source=source, team=expected).external_name
        == external
    )


@pytest.mark.parametrize(
    ("country", "competition_name", "external", "canonical"),
    [
        ("DE", "Bundesliga", "Elversberg", "SV Elversberg"),
        (
            "AR",
            "Liga Profesional Argentina",
            "Estudiantes Rio Cuarto",
            "Estudiantes de Rio Cuarto",
        ),
    ],
)
def test_frozen_aliases_reuse_only_the_approved_canonical_team(
    country, competition_name, external, canonical
):
    competition, _ = _competition(name=competition_name, country=country)
    expected = Team.objects.create(competition=competition, name=canonical)
    team, basis, created = _resolve_team(
        _football_data_source(), competition, external, apply=True
    )
    assert (team, basis, created) == (expected, "FROZEN_MAPPING", False)


@pytest.mark.parametrize(
    ("country", "competition_name", "external", "canonical"),
    [
        ("FR", "Ligue 1", "Le Mans", "Le Mans"),
        ("AR", "Liga Profesional Argentina", "Gimnasia Mendoza", "Gimnasia Mendoza"),
        ("TR", "Süper Lig", "Amedspor", "Amed"),
        ("TR", "Süper Lig", "Corum", "Çorum FK"),
        ("TR", "Süper Lig", "Erzurumspor", "Erzurumspor FK"),
    ],
)
def test_only_frozen_missing_teams_can_be_created(
    country, competition_name, external, canonical
):
    competition, _ = _competition(name=competition_name, country=country)
    team, _, created = _resolve_team(
        _football_data_source(), competition, external, apply=True
    )
    assert team.name == canonical
    assert created is True
    unknown, reason, _ = _resolve_team(
        _football_data_source(), competition, "Unknown Club", apply=True
    )
    assert unknown is None
    assert reason == "BLOCKED_TEAM_IDENTITY"


def test_blocked_row_does_not_partially_create_an_approved_team(tmp_path):
    competition, season = _competition(name="Ligue 1", country="FR", current=True)
    payload = _europe_csv(home="Le Mans", away="Unknown Club")
    _write_cache(competition, season, tmp_path, payload, current=True)
    result = recover_current_season(
        competition, season, apply=True, cache_only=True, cache_root=tmp_path
    )
    assert result["counts"] == {"BLOCKED_TEAM_IDENTITY": 1}
    assert not Team.objects.filter(competition=competition, name="Le Mans").exists()
    assert Match.objects.count() == 0


def test_current_recovery_fills_only_missing_compatible_result_fields(tmp_path):
    competition, season = _competition(year=2024, current=True)
    home, away = _teams(competition)
    match = Match.objects.create(
        season=season,
        home_team=home,
        away_team=away,
        kickoff=datetime(2024, 8, 10, 14, tzinfo=datetime_timezone.utc),
        kickoff_timezone="UTC",
        status_short="NS",
        status_long="Not Started",
    )
    _write_cache(competition, season, tmp_path, _europe_csv(), current=True)
    result = recover_current_season(
        competition, season, apply=True, cache_only=True, cache_root=tmp_path
    )
    assert result["counts"]["FILL_MISSING_RESULT"] == 1
    match.refresh_from_db()
    assert (match.home_score, match.away_score, match.outcome, match.status_short) == (
        2,
        1,
        Match.OUTCOME_HOME,
        "FT",
    )
    assert match.status_long == "Match Finished"


@pytest.mark.parametrize(
    ("status_short", "status_long"),
    [("CANC", "Match Cancelled"), ("PST", "Match Postponed")],
)
def test_current_recovery_preserves_terminal_result_empty_match(
    tmp_path, status_short, status_long
):
    competition, season = _competition(year=2024, current=True)
    home, away = _teams(competition)
    match = Match.objects.create(
        season=season,
        home_team=home,
        away_team=away,
        kickoff=datetime(2024, 8, 10, 14, tzinfo=datetime_timezone.utc),
        kickoff_timezone="UTC",
        status_short=status_short,
        status_long=status_long,
    )
    _write_cache(competition, season, tmp_path, _europe_csv(), current=True)
    result = recover_current_season(
        competition, season, apply=True, cache_only=True, cache_root=tmp_path
    )
    assert result["counts"] == {"RESULT_CONFLICT": 1}
    match.refresh_from_db()
    assert (match.status_short, match.home_score, match.outcome) == (
        status_short,
        None,
        "",
    )


def test_current_no_complete_triplet_is_explicitly_market_unavailable(tmp_path):
    competition, season = _competition(year=2024, current=True)
    home, away = _teams(competition)
    match = _match(season, home, away)
    payload = _europe_csv(prices={"PSCH": "2.1", "PSCD": "", "PSCA": "3.4"})
    _write_cache(competition, season, tmp_path, payload, current=True)
    result = recover_current_season(
        competition, season, apply=True, cache_only=True, cache_root=tmp_path
    )
    assert result["counts"]["SOURCE_NO_COMPLETE_1X2"] == 1
    assert HistoricalMarketEvidence.objects.count() == 0
    assert HistoricalMarketUnavailable.objects.get(match=match).reason == (
        "SOURCE_NO_COMPLETE_1X2"
    )
    assert Match.objects.filter(pk=match.pk, outcome=Match.OUTCOME_HOME).exists()

    _write_cache(competition, season, tmp_path, _europe_csv(), current=True)
    filled = recover_current_season(
        competition, season, apply=True, cache_only=True, cache_root=tmp_path
    )
    assert filled["counts"]["FILL_HISTORICAL_1X2"] == 1
    assert not HistoricalMarketUnavailable.objects.filter(match=match).exists()
    assert HistoricalMarketEvidence.objects.filter(match=match).exists()

    repeated = recover_current_season(
        competition, season, apply=True, cache_only=True, cache_root=tmp_path
    )
    assert repeated["counts"]["NO_WORK"] == 1


def test_current_live_fetch_uses_url_provenance_without_persisting_raw_csv(tmp_path):
    competition, season = _competition(year=2024, current=True)
    Team.objects.create(competition=competition, name="Arsenal")
    Team.objects.create(competition=competition, name="Chelsea")
    network = Mock(return_value=_europe_csv())
    result = recover_current_season(
        competition,
        season,
        cache_root=tmp_path,
        http_get=network,
    )
    assert result["downloaded"] is True
    assert len(result["source_file_checksum"]) == 64
    assert result["source_file"].startswith("https://www.football-data.co.uk/")
    assert not Path(
        source_spec(
            competition, season, cache_root=tmp_path, current_cache=True
        ).cache_path
    ).exists()
    network.assert_called_once()


def test_completed_source_with_no_requested_season_rows_is_structural_failure(tmp_path):
    competition, season = _competition(
        name="Liga Profesional Argentina", country="AR", year=2024
    )
    _sporting_current(competition, [season])
    payload = _direct_csv().replace(b"2024,", b"2023,")
    _write_cache(competition, season, tmp_path, payload)
    with pytest.raises(SourceSchemaError, match="SOURCE_HAS_NO_ROWS"):
        ingest_completed_season(
            competition, season, cache_only=True, cache_root=tmp_path
        )


def test_current_command_requires_explicit_scope_and_is_dry_run(tmp_path):
    with pytest.raises(Exception, match="one of the arguments"):
        call_command("backfill_football_current_season_gaps")


def _manual_scope_competition():
    competition, newest = _competition(year=2024)
    required = Season.objects.create(
        competition=competition,
        year=2023,
        start_date=date(2023, 8, 1),
        end_date=date(2024, 6, 30),
    )
    legacy = Season.objects.create(
        competition=competition,
        year=2010,
        start_date=date(2010, 8, 1),
        end_date=date(2011, 6, 30),
    )
    _sporting_current(
        competition,
        [required, newest],
        omitted_seasons=[legacy],
    )
    return competition, required, newest, legacy


def test_manual_historical_command_processes_only_authoritative_required_scope(
    monkeypatch,
):
    competition, older, newer, legacy = _manual_scope_competition()
    processed = []

    def fake_ingest(target, season, **kwargs):
        processed.append((target.pk, season.year, kwargs))
        return {"competition_id": target.pk, "season_year": season.year}

    monkeypatch.setattr(
        "football.management.commands.backfill_football_historical_market."
        "ingest_completed_season",
        fake_ingest,
    )

    call_command(
        "backfill_football_historical_market",
        "--competition-id",
        str(competition.pk),
        "--apply",
    )

    assert [row[1] for row in processed] == [older.year, newer.year]
    assert all(row[2]["cache_only"] is False for row in processed)
    assert not HistoricalMarketCoverage.objects.filter(season=legacy).exists()


@pytest.mark.parametrize(
    "requested_years",
    [(2010,), (2024, 2010)],
)
def test_manual_historical_command_rejects_non_required_scope_before_work(
    monkeypatch, requested_years
):
    competition, _, _, legacy = _manual_scope_competition()
    ingest = Mock(side_effect=AssertionError("historical ingestion called"))
    acquire = Mock(side_effect=AssertionError("provider called"))
    monkeypatch.setattr(
        "football.management.commands.backfill_football_historical_market."
        "ingest_completed_season",
        ingest,
    )
    monkeypatch.setattr("football.historical_market.service.acquire_source", acquire)
    arguments = [
        "--competition-id",
        str(competition.pk),
        "--apply",
    ]
    for year in requested_years:
        arguments.extend(("--season-year", str(year)))

    with pytest.raises(
        CommandError, match="SEASONS_OUTSIDE_AUTHORITATIVE_REQUIRED_SCOPE"
    ):
        call_command("backfill_football_historical_market", *arguments)

    ingest.assert_not_called()
    acquire.assert_not_called()
    assert not HistoricalMarketCoverage.objects.filter(season=legacy).exists()


def test_completed_service_rejects_non_required_season_before_write_or_fetch():
    competition, _, _, legacy = _manual_scope_competition()
    network = Mock(side_effect=AssertionError("provider called"))

    with pytest.raises(
        HistoricalMarketScopeError,
        match="SEASON_OUTSIDE_AUTHORITATIVE_REQUIRED_SCOPE:2010",
    ):
        ingest_completed_season(competition, legacy, http_get=network)

    network.assert_not_called()
    assert HistoricalMarketCoverage.objects.count() == 0


def test_manual_historical_command_reports_missing_authoritative_canonical_season():
    competition, season = _competition(year=2024)
    HistoricalCoverage.objects.create(
        competition=competition,
        status=HistoricalCoverage.Status.COMPLETE,
        strategy_version=SPORTING_STRATEGY,
        required_seasons=[season.year, 2025],
        covered_seasons=[season.year, 2025],
    )

    with pytest.raises(
        CommandError, match="AUTHORITATIVE_COMPLETED_SEASONS_MISSING.*2025"
    ):
        call_command(
            "backfill_football_historical_market",
            "--competition-id",
            str(competition.pk),
            "--apply",
        )

    assert HistoricalMarketCoverage.objects.count() == 0


def test_scoped_package_checksum_and_import_are_idempotent(tmp_path):
    competition, season = _competition()
    home, away = _teams(competition)
    match = _match(season, home, away)
    source = _football_data_source()
    HistoricalMarketEvidence.objects.create(
        match=match,
        source=source,
        home_price=Decimal("2.1"),
        draw_price=Decimal("3.2"),
        away_price=Decimal("3.4"),
        selected_group="PINNACLE_CLOSING",
        time_semantics="ASSUMED_T30M",
        source_competition="ENG Premier League",
        source_season="2024-25",
        source_file="tmp/source.csv",
        source_file_checksum="d" * 64,
        source_row_identity="row",
    )
    HistoricalMarketCoverage.objects.create(
        competition=competition,
        season=season,
        source=source,
        status=HistoricalMarketCoverage.Status.COMPLETE,
        strategy_version="fs015-football-data-v1",
        attempted=True,
        available=True,
        source_rows=1,
        valid_rows=1,
        complete_triplet_rows=1,
        imported_rows=1,
    )
    package = tmp_path / "data.dump"
    manifest = tmp_path / "manifest.json"
    exported = export_package(package, manifest)
    assert exported["counts"]["evidence"] == 1
    assert exported["aggregates"]["by_competition"][0]["competition"] == {
        "country": "EN",
        "name": "Premier League",
        "competition_type": "League",
    }
    HistoricalMarketEvidence.objects.all().delete()
    HistoricalMarketCoverage.objects.all().delete()
    first = import_package(package, manifest, apply=True)
    second = import_package(package, manifest, apply=True)
    assert first["counts"]["evidence_created"] == 1
    assert second["counts"]["evidence_unchanged"] == 1
    assert HistoricalMarketEvidence.objects.count() == 1

    package.write_bytes(package.read_bytes() + b"corrupt")
    with pytest.raises(PackageIntegrityError, match="PACKAGE_CHECKSUM_MISMATCH"):
        import_package(package, manifest, apply=True)


def test_package_rejects_tampered_competition_season_aggregate(tmp_path):
    competition, season = _competition()
    home, away = _teams(competition)
    match = _match(season, home, away)
    source = _football_data_source()
    HistoricalMarketEvidence.objects.create(
        match=match,
        source=source,
        home_price=Decimal("2.1"),
        draw_price=Decimal("3.2"),
        away_price=Decimal("3.4"),
        selected_group="PINNACLE_CLOSING",
        time_semantics="ASSUMED_T30M",
        source_competition="ENG Premier League",
        source_season="2024-25",
        source_file="https://example.invalid/E0.csv",
        source_file_checksum="d" * 64,
        source_row_identity="row",
    )
    package = tmp_path / "aggregate.dump"
    manifest = tmp_path / "aggregate-manifest.json"
    export_package(package, manifest)
    document = json.loads(manifest.read_text())
    document["aggregates"]["by_competition_season"][0]["counts"]["evidence"] = 0
    manifest.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(PackageIntegrityError, match="PACKAGE_AGGREGATE_MISMATCH"):
        import_package(package, manifest, apply=True)


def test_package_reconciles_an_existing_current_match_and_preserves_prospective(
    tmp_path,
):
    competition, season = _competition(year=2024, current=True)
    home, away = _teams(competition)
    match = _match(season, home, away)
    _write_cache(competition, season, tmp_path, _europe_csv(), current=True)
    recover_current_season(
        competition, season, apply=True, cache_only=True, cache_root=tmp_path
    )
    api = Source.objects.get(code="api_football")
    bookmaker = Bookmaker.objects.create(source=api, external_id="8", name="Bet365")
    market = OddsMarket.objects.create(source=api, external_id="1", name="1X2")
    observation = OddsObservation.objects.create(
        match=match,
        source=api,
        bookmaker=bookmaker,
        market=market,
        home=2,
        draw=3,
        away=4,
        observed_at=datetime(2024, 8, 10, 12, tzinfo=datetime_timezone.utc),
    )
    package = tmp_path / "current.dump"
    manifest = tmp_path / "current-manifest.json"
    exported = export_package(package, manifest)
    assert exported["counts"]["created_matches"] == 0
    assert exported["counts"]["current_match_refs"] == 1
    HistoricalMarketEvidence.objects.all().delete()
    MatchSourceRef.objects.filter(source__code="football_data").delete()
    Match.objects.filter(pk=match.pk).update(
        status_short="NS",
        status_long="Not Started",
        outcome="",
        home_score=None,
        away_score=None,
        fulltime_home_score=None,
        fulltime_away_score=None,
    )

    first = import_package(package, manifest, apply=True)
    second = import_package(package, manifest, apply=True)
    assert first["counts"]["match_refs_created"] == 1
    assert first["counts"]["evidence_created"] == 1
    assert first["counts"]["matches_filled"] == 1
    assert second["counts"]["matches_unchanged"] == 1
    match.refresh_from_db()
    assert (match.pk, match.status_short, match.home_score, match.away_score) == (
        match.pk,
        "FT",
        2,
        1,
    )
    observation.refresh_from_db()
    assert (observation.home, observation.draw, observation.away) == (
        Decimal("2.0000"),
        Decimal("3.0000"),
        Decimal("4.0000"),
    )


def test_package_exact_match_ref_wins_over_kickoff_drift_and_conflicts_closed(
    tmp_path,
):
    competition, season = _competition(year=2024, current=True)
    home, away = _teams(competition)
    match = _match(season, home, away)
    _write_cache(competition, season, tmp_path, _europe_csv(), current=True)
    recover_current_season(
        competition, season, apply=True, cache_only=True, cache_root=tmp_path
    )
    package = tmp_path / "ref-current.dump"
    manifest = tmp_path / "ref-current-manifest.json"
    export_package(package, manifest)
    Match.objects.filter(pk=match.pk).update(kickoff=match.kickoff + timedelta(days=10))

    imported = import_package(package, manifest, apply=True)

    assert imported["counts"]["matches_unchanged"] == 1
    assert Match.objects.count() == 1

    incompatible = Match.objects.create(
        season=season,
        home_team=away,
        away_team=home,
        kickoff=match.kickoff,
        kickoff_timezone="UTC",
        status_short="FT",
        status_long="Match Finished",
        outcome=Match.OUTCOME_AWAY,
        home_score=1,
        away_score=2,
        fulltime_home_score=1,
        fulltime_away_score=2,
    )
    MatchSourceRef.objects.filter(source__code="football_data", match=match).update(
        match=incompatible
    )
    with pytest.raises(PackageConflict, match="PACKAGE_MATCH_REF_CONFLICT"):
        import_package(package, manifest, apply=True)
    assert Match.objects.count() == 2


def test_package_conflicting_final_result_is_never_overwritten(tmp_path):
    competition, season = _competition(year=2024, current=True)
    home, away = _teams(competition)
    match = _match(season, home, away)
    _write_cache(competition, season, tmp_path, _europe_csv(), current=True)
    recover_current_season(
        competition, season, apply=True, cache_only=True, cache_root=tmp_path
    )
    package = tmp_path / "result-conflict.dump"
    manifest = tmp_path / "result-conflict-manifest.json"
    export_package(package, manifest)
    Match.objects.filter(pk=match.pk).update(
        home_score=3,
        away_score=0,
        fulltime_home_score=3,
        fulltime_away_score=0,
        outcome=Match.OUTCOME_HOME,
    )

    with pytest.raises(PackageConflict, match="PACKAGE_CANONICAL_MATCH_CONFLICT"):
        import_package(package, manifest, apply=True)

    match.refresh_from_db()
    assert (match.home_score, match.away_score, match.outcome) == (3, 0, "HOME")
    assert not market_baseline_is_promoted()


def test_package_import_atomically_promotes_baseline_and_unlocks_future_league(
    tmp_path,
):
    existing, existing_season = _competition(name="Existing League", country="US")
    _sporting_current(existing, [existing_season])
    source = _football_data_source()
    HistoricalMarketCoverage.objects.create(
        competition=existing,
        season=existing_season,
        source=source,
        status=HistoricalMarketCoverage.Status.UNSUPPORTED_SOURCE,
        strategy_version="fs015-football-data-v1",
        attempted=True,
        available=False,
        reason="NO_APPROVED_FOOTBALL_DATA_SOURCE",
    )
    package = tmp_path / "baseline.dump"
    manifest = tmp_path / "baseline-manifest.json"
    export_package(package, manifest)
    HistoricalMarketCoverage.objects.all().delete()

    blocked_runner = Mock(side_effect=AssertionError("baseline race occurred"))
    blocked = run_historical_market_maintenance(runner=blocked_runner)
    assert blocked == {
        "status": MaintenanceRun.Status.NO_WORK,
        "due": False,
        "reason": "FS015_MARKET_BASELINE_NOT_PROMOTED",
    }
    blocked_runner.assert_not_called()

    dry = import_package(package, manifest)
    assert dry["baseline_promotion"] == "NOT_APPLIED"
    assert not market_baseline_is_promoted()
    assert HistoricalMarketCoverage.objects.count() == 0

    conflicting = HistoricalMarketCoverage.objects.create(
        competition=existing,
        season=existing_season,
        source=source,
        status=HistoricalMarketCoverage.Status.PARTIAL,
        strategy_version="conflicting-version",
        attempted=True,
    )
    with pytest.raises(PackageConflict, match="PACKAGE_HISTORICAL_COVERAGE_CONFLICT"):
        import_package(package, manifest, apply=True)
    assert not market_baseline_is_promoted()
    conflicting.delete()

    applied = import_package(package, manifest, apply=True)
    repeated = import_package(package, manifest, apply=True)
    assert applied["baseline_promotion"] == "CREATED"
    assert repeated["baseline_promotion"] == "ALREADY_COMPLETE"
    assert market_baseline_is_promoted()
    assert (
        MaintenanceRun.objects.filter(
            logical_identity=BASELINE_PROMOTION_IDENTITY,
            status=MaintenanceRun.Status.SUCCESS,
        ).count()
        == 1
    )

    future, future_season = _competition(name="Future League", country="CA")
    _sporting_current(future, [future_season])

    def future_runner(target):
        assert target == future
        HistoricalMarketCoverage.objects.create(
            competition=target,
            season=future_season,
            source=source,
            status=HistoricalMarketCoverage.Status.UNSUPPORTED_SOURCE,
            strategy_version="fs015-football-data-v1",
            attempted=True,
            available=False,
        )
        return {"competition_id": target.pk, "status": "UNSUPPORTED_SOURCE"}

    future_result = run_historical_market_maintenance(runner=future_runner)
    assert future_result["status"] == MaintenanceRun.Status.SUCCESS
    assert future_result["summary"]["competition_id"] == future.pk
    assert run_historical_market_maintenance(runner=Mock())["status"] == (
        MaintenanceRun.Status.NO_WORK
    )


def test_package_exports_only_team_refs_required_by_fs015_current_matches(tmp_path):
    competition, season = _competition(year=2024, current=True)
    source = _football_data_source()
    teams = []
    for index in range(100):
        name = f"Legacy Team {index:03d}"
        team = Team.objects.create(competition=competition, name=name)
        TeamSourceRef.objects.create(
            source=source,
            competition=competition,
            team=team,
            external_id=f"ENG Premier League:{name}",
            external_name=name,
            reconciliation_status=ReconciliationStatus.RESOLVED,
            confidence=1,
        )
        teams.append(team)
    match = _match(season, teams[-2], teams[-1])
    MatchSourceRef.objects.create(
        source=source,
        match=match,
        external_id="fs015-current-required-match",
        external_label=f"{teams[-2].name} - {teams[-1].name}",
        reconciliation_status=ReconciliationStatus.RESOLVED,
        confidence=1,
        context={"fs015_current_season_reconciled": True},
    )

    first_payload = build_package_payload()
    second_payload = build_package_payload()
    required_external_ids = {
        f"ENG Premier League:{teams[-2].name}",
        f"ENG Premier League:{teams[-1].name}",
    }
    assert {row["external_id"] for row in first_payload["team_refs"]} == (
        required_external_ids
    )
    assert first_payload["team_refs"] == second_payload["team_refs"]
    assert len(first_payload["team_refs"]) == 2
    assert len(first_payload["current_match_refs"]) == 1

    package = tmp_path / "narrow-team-refs.dump"
    manifest = tmp_path / "narrow-team-refs-manifest.json"
    exported = export_package(package, manifest)
    assert exported["counts"]["team_refs"] == 2
    assert exported["aggregates"]["by_competition"][0]["counts"]["team_refs"] == 2
    TeamSourceRef.objects.filter(external_id__in=required_external_ids).delete()
    assert TeamSourceRef.objects.count() == 98

    imported = import_package(package, manifest, apply=True)

    assert imported["counts"]["team_refs_created"] == 2
    assert imported["baseline_promotion"] == "CREATED"
    assert TeamSourceRef.objects.count() == 100
    assert (
        set(
            TeamSourceRef.objects.filter(
                external_id__in=required_external_ids
            ).values_list("external_id", flat=True)
        )
        == required_external_ids
    )


def test_package_can_recreate_an_fs015_authorized_current_match(tmp_path):
    competition, season = _competition(year=2024, current=True)
    _teams(competition)
    _write_cache(competition, season, tmp_path, _europe_csv(), current=True)
    recover_current_season(
        competition, season, apply=True, cache_only=True, cache_root=tmp_path
    )
    package = tmp_path / "created-current.dump"
    manifest = tmp_path / "created-current-manifest.json"
    exported = export_package(package, manifest)
    assert exported["counts"]["created_matches"] == 1
    Match.objects.all().delete()

    first = import_package(package, manifest, apply=True)
    second = import_package(package, manifest, apply=True)
    assert first["counts"]["matches_created"] == 1
    assert first["counts"]["evidence_created"] == 1
    assert second["counts"]["matches_unchanged"] == 1
    assert Match.objects.filter(season=season, outcome=Match.OUTCOME_HOME).count() == 1


def test_existing_owner_converges_sporting_and_market_to_no_work():
    competition, season = _competition(enabled=False)
    requested = request_historical_bootstrap(competition, activate=True)
    assert requested.activation_requested is True
    competition.refresh_from_db()
    assert competition.enabled is False

    def sporting_runner(target):
        coverage = HistoricalCoverage.objects.get(competition=target)
        coverage.status = HistoricalCoverage.Status.COMPLETE
        coverage.strategy_version = SPORTING_STRATEGY
        coverage.required_seasons = [season.year]
        coverage.covered_seasons = [season.year]
        coverage.unresolved_seasons = []
        coverage.save()
        target.enabled = True
        target.save(update_fields=["enabled", "modified"])
        return coverage

    first = run_historical_bootstrap_maintenance(runner=sporting_runner)
    assert first["status"] == "SUCCESS"
    competition.refresh_from_db()
    assert competition.enabled is True
    _promote_baseline()

    def market_runner(target):
        source = _football_data_source()
        HistoricalMarketCoverage.objects.create(
            competition=target,
            season=season,
            source=source,
            status=HistoricalMarketCoverage.Status.COMPLETE,
            strategy_version="fs015-football-data-v1",
            attempted=True,
            available=True,
        )
        return {"competition_id": target.pk, "status": "COMPLETE", "seasons": []}

    market = run_historical_market_maintenance(runner=market_runner)
    assert market["status"] == "SUCCESS"
    assert historical_market_is_current(competition, season)
    assert run_historical_market_maintenance(runner=Mock())["status"] == "NO_WORK"


def test_non_required_old_season_does_not_make_market_bootstrap_due():
    _promote_baseline()
    competition, required = _competition(year=2024)
    omitted = Season.objects.create(
        competition=competition,
        year=2023,
        start_date=date(2023, 8, 1),
        end_date=date(2024, 6, 30),
    )
    _sporting_current(competition, [required], omitted_seasons=[omitted])
    source = _football_data_source()
    HistoricalMarketCoverage.objects.create(
        competition=competition,
        season=required,
        source=source,
        status=HistoricalMarketCoverage.Status.COMPLETE,
        strategy_version="fs015-football-data-v1",
        attempted=True,
        available=True,
    )

    assert historical_market_required_years(competition) == [required.year]
    assert historical_market_is_terminal(competition)
    runner = Mock(side_effect=AssertionError("non-required season fetched"))
    assert run_historical_market_maintenance(runner=runner)["status"] == "NO_WORK"
    runner.assert_not_called()


def test_growing_authoritative_required_set_makes_market_work_due():
    competition, newer = _competition(year=2024)
    older = Season.objects.create(
        competition=competition,
        year=2023,
        start_date=date(2023, 8, 1),
        end_date=date(2024, 6, 30),
    )
    sporting = _sporting_current(competition, [newer], omitted_seasons=[older])
    source = _football_data_source()
    HistoricalMarketCoverage.objects.create(
        competition=competition,
        season=newer,
        source=source,
        status=HistoricalMarketCoverage.Status.COMPLETE,
        strategy_version="fs015-football-data-v1",
        attempted=True,
        available=True,
    )
    assert historical_market_is_terminal(competition)

    sporting.required_seasons = [older.year, newer.year]
    sporting.covered_seasons = [older.year, newer.year]
    sporting.diagnostics = {"issues": []}
    sporting.save()

    assert historical_market_required_years(competition) == [older.year, newer.year]
    assert historical_market_is_current(competition) is False
    assert historical_market_is_terminal(competition) is False


def test_unsupported_future_source_is_terminal_and_not_retried():
    _promote_baseline()
    competition, season = _competition(name="Future League", country="US")
    HistoricalCoverage.objects.create(
        competition=competition,
        status=HistoricalCoverage.Status.COMPLETE,
        strategy_version=SPORTING_STRATEGY,
        required_seasons=[season.year],
        covered_seasons=[season.year],
    )
    first = run_historical_market_maintenance()
    assert first["status"] == MaintenanceRun.Status.SUCCESS
    assert first["summary"]["status"] == "UNSUPPORTED_SOURCE"
    assert historical_market_is_terminal(competition)
    runner = Mock(side_effect=AssertionError("unsupported source retried"))
    second = run_historical_market_maintenance(runner=runner)
    assert second["status"] == MaintenanceRun.Status.NO_WORK
    runner.assert_not_called()


def test_prior_one_shot_attempt_does_not_block_the_next_competition():
    _promote_baseline()
    blocked, blocked_season = _competition(name="Attempted League", country="US")
    following, following_season = _competition(name="Following League", country="CA")
    for competition, season in (
        (blocked, blocked_season),
        (following, following_season),
    ):
        HistoricalCoverage.objects.create(
            competition=competition,
            status=HistoricalCoverage.Status.COMPLETE,
            strategy_version=SPORTING_STRATEGY,
            required_seasons=[season.year],
            covered_seasons=[season.year],
        )
    MaintenanceRun.objects.create(
        capability=MaintenanceRun.Capability.HISTORICAL_MARKET_BOOTSTRAP,
        logical_identity=(
            f"historical-market-bootstrap:{blocked.pk}:{blocked_season.year}"
        ),
        period_start=date.today(),
        subject_type="Competition",
        subject_id=blocked.pk,
        status=MaintenanceRun.Status.FAILED,
    )
    result = run_historical_market_maintenance()
    assert result["summary"]["competition_id"] == following.pk
    assert historical_market_is_terminal(following)


def test_existing_match_ref_result_fill_is_promoted_by_package(tmp_path):
    competition, season = _competition(year=2024, current=True)
    home, away = _teams(competition)

    match = Match.objects.create(
        season=season,
        home_team=home,
        away_team=away,
        kickoff=datetime(2024, 8, 10, 14, tzinfo=datetime_timezone.utc),
        kickoff_timezone="UTC",
        status_short="NS",
        status_long="Not Started",
    )

    source = _football_data_source()
    external_id = _external_id(
        source_spec_external(competition),
        season.year,
        date(2024, 8, 10),
        "Arsenal",
        "Chelsea",
    )
    ref = MatchSourceRef.objects.create(
        source=source,
        match=match,
        external_id=external_id,
        external_label="Arsenal - Chelsea",
        reconciliation_status=ReconciliationStatus.RESOLVED,
        confidence=1,
        context={"legacy_context": "preserve-me"},
    )

    api = Source.objects.get(code="api_football")
    bookmaker = Bookmaker.objects.create(
        source=api,
        external_id="fs015-existing-ref-bookmaker",
        name="FS015 Existing Ref Bookmaker",
    )
    market = OddsMarket.objects.create(
        source=api,
        external_id="fs015-existing-ref-market",
        name="1X2",
    )
    odds = OddsObservation.objects.create(
        match=match,
        source=api,
        bookmaker=bookmaker,
        market=market,
        home=Decimal("2.10"),
        draw=Decimal("3.20"),
        away=Decimal("3.40"),
        observed_at=datetime(2024, 8, 10, 12, tzinfo=datetime_timezone.utc),
    )
    odds_before = {
        "home": odds.home,
        "draw": odds.draw,
        "away": odds.away,
        "observed_at": odds.observed_at,
    }

    _write_cache(
        competition,
        season,
        tmp_path,
        _europe_csv(),
        current=True,
    )

    recovered = recover_current_season(
        competition,
        season,
        apply=True,
        cache_only=True,
        cache_root=tmp_path,
    )

    assert recovered["counts"]["FILL_MISSING_RESULT"] == 1

    match.refresh_from_db()
    assert (
        match.status_short,
        match.home_score,
        match.away_score,
        match.outcome,
    ) == ("FT", 2, 1, Match.OUTCOME_HOME)

    ref.refresh_from_db()
    assert ref.context["legacy_context"] == "preserve-me"
    assert ref.context["fs015_current_season_reconciled"] is True

    payload = build_package_payload()
    assert [
        row["source_external_id"]
        for row in payload["current_match_refs"]
        if row["source_external_id"] == external_id
    ] == [external_id]

    package = tmp_path / "existing-ref-result-fill.dump"
    manifest = tmp_path / "existing-ref-result-fill-manifest.json"
    export_package(package, manifest)

    # Simulate operational state still missing the result.
    HistoricalMarketEvidence.objects.filter(match=match).delete()
    Match.objects.filter(pk=match.pk).update(
        status_short="NS",
        status_long="Not Started",
        outcome="",
        home_score=None,
        away_score=None,
        fulltime_home_score=None,
        fulltime_away_score=None,
    )
    MatchSourceRef.objects.filter(pk=ref.pk).update(
        context={"legacy_context": "preserve-me"}
    )

    imported = import_package(package, manifest, apply=True)

    assert imported["counts"]["matches_filled"] == 1

    match.refresh_from_db()
    assert (
        match.status_short,
        match.home_score,
        match.away_score,
        match.outcome,
    ) == ("FT", 2, 1, Match.OUTCOME_HOME)

    odds.refresh_from_db()
    assert {
        "home": odds.home,
        "draw": odds.draw,
        "away": odds.away,
        "observed_at": odds.observed_at,
    } == odds_before

    ref.refresh_from_db()
    assert ref.match_id == match.pk
    assert ref.external_id == external_id
