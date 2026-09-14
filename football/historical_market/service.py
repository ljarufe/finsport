from collections import Counter
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from football.historical import historical_coverage_is_current
from football.historical.reconciliation import _normalized_team_name
from football.models import (
    HistoricalCoverage,
    HistoricalMarketCoverage,
    HistoricalMarketEvidence,
    HistoricalMarketUnavailable,
    Match,
    MatchSourceRef,
    ReconciliationStatus,
    Source,
    TeamSourceRef,
)

from .contracts import (
    HistoricalMarketScopeError,
    SourceSchemaError,
    SourceUnsupported,
)
from .source import (
    PROVENANCE_VERSION,
    SOURCE_BASE_URL,
    SOURCE_CODE,
    SOURCE_NAME,
    acquire_source,
    parse_market_file,
    source_spec,
)

STRATEGY_VERSION = "fs015-football-data-v1"
SOURCE_TIMEZONE = ZoneInfo("Europe/London")


def _source():
    source, _ = Source.objects.get_or_create(
        code=SOURCE_CODE,
        defaults={"name": SOURCE_NAME, "base_url": SOURCE_BASE_URL},
    )
    return source


def authoritative_market_seasons(competition):
    try:
        sporting = competition.historical_coverage
    except HistoricalCoverage.DoesNotExist as error:
        raise HistoricalMarketScopeError(
            "CURRENT_SPORTING_HISTORICAL_COVERAGE_REQUIRED"
        ) from error
    try:
        required_years = sorted({int(year) for year in sporting.required_seasons})
    except (TypeError, ValueError) as error:
        raise HistoricalMarketScopeError(
            "INVALID_AUTHORITATIVE_REQUIRED_SEASONS"
        ) from error
    seasons = list(
        competition.seasons.filter(is_current=False, year__in=required_years).order_by(
            "year", "id"
        )
    )
    existing_years = {season.year for season in seasons}
    missing_years = sorted(set(required_years) - existing_years)
    if missing_years:
        raise HistoricalMarketScopeError(
            f"AUTHORITATIVE_COMPLETED_SEASONS_MISSING:{missing_years}"
        )
    if not historical_coverage_is_current(competition, sporting):
        raise HistoricalMarketScopeError(
            "CURRENT_SPORTING_HISTORICAL_COVERAGE_REQUIRED"
        )
    return seasons


def historical_market_required_seasons(competition):
    try:
        return authoritative_market_seasons(competition)
    except HistoricalMarketScopeError:
        return []


def historical_market_required_years(competition):
    return [season.year for season in historical_market_required_seasons(competition)]


def historical_market_is_current(competition, season=None):
    required_seasons = historical_market_required_seasons(competition)
    if not historical_coverage_is_current(competition):
        return False
    required_ids = {item.pk for item in required_seasons}
    if season is not None and season.pk not in required_ids:
        return True
    queryset = HistoricalMarketCoverage.objects.filter(
        competition=competition,
        source__code=SOURCE_CODE,
        status=HistoricalMarketCoverage.Status.COMPLETE,
        strategy_version=STRATEGY_VERSION,
        unresolved_rows=0,
        conflict_rows=0,
    )
    if season is not None:
        return queryset.filter(season=season).exists()
    required = required_ids
    covered = set(queryset.values_list("season_id", flat=True))
    return required <= covered


def historical_market_is_terminal(competition):
    if not historical_coverage_is_current(competition):
        return False
    required = {season.pk for season in historical_market_required_seasons(competition)}
    terminal = set(
        HistoricalMarketCoverage.objects.filter(
            competition=competition,
            source__code=SOURCE_CODE,
            status__in=(
                HistoricalMarketCoverage.Status.COMPLETE,
                HistoricalMarketCoverage.Status.UNSUPPORTED_SOURCE,
            ),
            strategy_version=STRATEGY_VERSION,
            unresolved_rows=0,
            conflict_rows=0,
        ).values_list("season_id", flat=True)
    )
    return required <= terminal


def market_required_matches(queryset):
    """Return usable historical-market matches plus explicit skip accounting."""
    input_ids = set(queryset.values_list("pk", flat=True).distinct())
    evidence_ids = set(
        HistoricalMarketEvidence.objects.filter(
            source__code=SOURCE_CODE, match_id__in=input_ids
        ).values_list("match_id", flat=True)
    )
    usable = queryset.filter(pk__in=evidence_ids).distinct()
    skipped = Counter(
        HistoricalMarketUnavailable.objects.filter(
            source__code=SOURCE_CODE,
            match_id__in=input_ids - evidence_ids,
        ).values_list("reason", flat=True)
    )
    explicitly_skipped = sum(skipped.values())
    skipped["NO_HISTORICAL_MARKET_STATE"] += (
        len(input_ids) - len(evidence_ids) - explicitly_skipped
    )
    if skipped["NO_HISTORICAL_MARKET_STATE"] == 0:
        del skipped["NO_HISTORICAL_MARKET_STATE"]
    return usable, dict(sorted(skipped.items()))


def _outcome(row):
    if row.home_score > row.away_score:
        return Match.OUTCOME_HOME
    if row.home_score < row.away_score:
        return Match.OUTCOME_AWAY
    return Match.OUTCOME_DRAW


def _matching_team(source, competition, external_name):
    normalized = _normalized_team_name(external_name)
    refs = [
        ref
        for ref in TeamSourceRef.objects.filter(
            source=source,
            competition=competition,
            reconciliation_status=ReconciliationStatus.RESOLVED,
            team__isnull=False,
        ).select_related("team")
        if _normalized_team_name(ref.external_name) == normalized
    ]
    teams = {ref.team_id: ref.team for ref in refs}
    if len(teams) == 1:
        return next(iter(teams.values())), ""
    if len(teams) > 1:
        return None, "AMBIGUOUS_TEAM_IDENTITY"
    return None, "UNRESOLVED_TEAM_IDENTITY"


def _resolved_match(source, competition, season, row):
    ref = (
        MatchSourceRef.objects.filter(source=source, external_id=row.external_id)
        .select_related("match", "match__season")
        .first()
    )
    if ref is not None:
        if (
            ref.reconciliation_status != ReconciliationStatus.RESOLVED
            or ref.match_id is None
        ):
            return None, "UNRESOLVED_MATCH_SOURCE_REF"
        if ref.match.season_id != season.pk:
            return None, "MATCH_SOURCE_REF_SEASON_CONFLICT"
        return ref.match, ""

    home, home_reason = _matching_team(source, competition, row.home_name)
    away, away_reason = _matching_team(source, competition, row.away_name)
    if home is None or away is None:
        return None, home_reason or away_reason
    candidates = list(
        Match.objects.filter(
            season=season,
            home_team=home,
            away_team=away,
            kickoff__date__gte=row.match_date - timedelta(days=2),
            kickoff__date__lte=row.match_date + timedelta(days=2),
        ).order_by("id")[:2]
    )
    if not candidates:
        return None, "OUTSIDE_CANONICAL_POOL"
    if len(candidates) > 1:
        return None, "AMBIGUOUS_CANONICAL_MATCH"
    match = candidates[0]
    MatchSourceRef.objects.create(
        source=source,
        external_id=row.external_id,
        external_label=f"{row.home_name} - {row.away_name}",
        match=match,
        reconciliation_status=ReconciliationStatus.RESOLVED,
        confidence=1,
        context={
            "authority": SOURCE_NAME,
            "reconciliation": "FS015_DETERMINISTIC_EXISTING_MATCH",
            "source_date": row.match_date.isoformat(),
        },
    )
    return match, ""


def _result_agrees(match, row):
    return (
        match.home_score == row.home_score
        and match.away_score == row.away_score
        and match.outcome == _outcome(row)
    )


def _relative_source_file(path):
    from django.conf import settings

    try:
        return str(path.relative_to(settings.BASE_DIR))
    except ValueError:
        return str(path)


def _source_locator(cached):
    if cached.provenance_locator.startswith(("http://", "https://")):
        return cached.provenance_locator
    return _relative_source_file(
        Path(cached.provenance_locator or cached.spec.cache_path)
    )


def _evidence_values(source, match, row, cached):
    return {
        "match": match,
        "source": source,
        "home_price": row.price.home,
        "draw_price": row.price.draw,
        "away_price": row.price.away,
        "selected_group": row.price.group,
        "time_semantics": row.price.time_semantics,
        "source_price_is_real": True,
        "timestamp_is_imputed": True,
        "evidence_class": HistoricalMarketEvidence.EVIDENCE_CLASS,
        "source_competition": cached.spec.external_competition,
        "source_season": cached.spec.source_season,
        "source_file": _source_locator(cached),
        "source_file_checksum": cached.checksum,
        "source_row_identity": row.row_identity,
        "provenance_version": PROVENANCE_VERSION,
    }


def _same_evidence(existing, values):
    fields = (
        "home_price",
        "draw_price",
        "away_price",
        "selected_group",
        "time_semantics",
        "source_competition",
        "source_season",
        "source_file_checksum",
        "source_row_identity",
        "provenance_version",
    )
    return all(getattr(existing, field) == values[field] for field in fields)


def _persist_market(source, match, row, cached, *, allow_unavailable_fill=False):
    evidence = HistoricalMarketEvidence.objects.filter(
        source=source, match=match
    ).first()
    unavailable = HistoricalMarketUnavailable.objects.filter(
        source=source, match=match
    ).first()
    source_file = _source_locator(cached)
    if row.price is None:
        if evidence is not None:
            return "CONFLICT"
        values = {
            "reason": HistoricalMarketUnavailable.SOURCE_NO_COMPLETE_1X2,
            "source_file": source_file,
            "source_file_checksum": cached.checksum,
            "source_row_identity": row.row_identity,
            "provenance_version": PROVENANCE_VERSION,
        }
        if unavailable is None:
            HistoricalMarketUnavailable.objects.create(
                source=source, match=match, **values
            )
            return "UNAVAILABLE_CREATED"
        if all(getattr(unavailable, key) == value for key, value in values.items()):
            return "UNAVAILABLE_UNCHANGED"
        return "CONFLICT"

    if unavailable is not None:
        if not allow_unavailable_fill:
            return "CONFLICT"
        unavailable.delete()
    values = _evidence_values(source, match, row, cached)
    if evidence is None:
        instance = HistoricalMarketEvidence(**values)
        instance.full_clean()
        instance.save()
        return "EVIDENCE_FILLED" if unavailable is not None else "EVIDENCE_CREATED"
    if _same_evidence(evidence, values):
        return "EVIDENCE_UNCHANGED"
    return "CONFLICT"


def _coverage_summary(coverage):
    return {
        "competition_id": coverage.competition_id,
        "season_id": coverage.season_id,
        "season_year": coverage.season.year,
        "status": coverage.status,
        "reason": coverage.reason,
        "source_url": coverage.source_url,
        "source_file": coverage.source_file,
        "source_file_checksum": coverage.source_file_checksum,
        "source_rows": coverage.source_rows,
        "valid_rows": coverage.valid_rows,
        "complete_triplet_rows": coverage.complete_triplet_rows,
        "imported_rows": coverage.imported_rows,
        "unavailable_rows": coverage.unavailable_rows,
        "outside_canonical_pool_rows": coverage.outside_canonical_pool_rows,
        "unresolved_rows": coverage.unresolved_rows,
        "conflict_rows": coverage.conflict_rows,
        "invalid_rows": coverage.invalid_rows,
        "download_count": coverage.download_count,
    }


@transaction.atomic
def ingest_completed_season(
    competition,
    season,
    *,
    cache_only=False,
    cache_root=None,
    expected_checksum="",
    http_get=None,
    force=False,
):
    if season.competition_id != competition.pk or season.is_current:
        raise ValueError("A completed Season belonging to Competition is required.")
    required_season_ids = {
        item.pk for item in authoritative_market_seasons(competition)
    }
    if season.pk not in required_season_ids:
        raise HistoricalMarketScopeError(
            f"SEASON_OUTSIDE_AUTHORITATIVE_REQUIRED_SCOPE:{season.year}"
        )
    source = _source()
    coverage, _ = HistoricalMarketCoverage.objects.select_for_update().get_or_create(
        competition=competition, season=season, source=source
    )
    if not force and historical_market_is_current(competition, season):
        return {**_coverage_summary(coverage), "outcome": "NO_WORK"}
    coverage.status = HistoricalMarketCoverage.Status.RUNNING
    coverage.attempted = True
    coverage.attempt_count += 1
    coverage.last_attempt_at = timezone.now()
    coverage.completed_at = None
    coverage.reason = "HISTORICAL_MARKET_SYNC_STARTED"
    coverage.save()
    try:
        spec = source_spec(competition, season, cache_root=cache_root)
    except SourceUnsupported:
        coverage.status = HistoricalMarketCoverage.Status.UNSUPPORTED_SOURCE
        coverage.strategy_version = STRATEGY_VERSION
        coverage.reason = "NO_APPROVED_FOOTBALL_DATA_SOURCE"
        coverage.completed_at = timezone.now()
        coverage.save()
        return {**_coverage_summary(coverage), "outcome": "UNSUPPORTED_SOURCE"}

    cached = acquire_source(
        spec,
        cache_only=cache_only,
        expected_checksum=expected_checksum,
        http_get=http_get,
    )
    parsed = parse_market_file(cached, season)
    if parsed.source_rows == 0:
        raise SourceSchemaError("SOURCE_HAS_NO_ROWS_FOR_REQUESTED_SEASON")
    outcomes = Counter()
    issues = []
    time_semantics = set()
    for row in parsed.rows:
        match, reason = _resolved_match(source, competition, season, row)
        if match is None:
            outcomes[reason] += 1
            if len(issues) < 100:
                issues.append(
                    {
                        "csv_line": row.csv_line,
                        "external_id": row.external_id,
                        "home": row.home_name,
                        "away": row.away_name,
                        "reason": reason,
                    }
                )
            continue
        if not _result_agrees(match, row):
            outcomes["RESULT_CONFLICT"] += 1
            continue
        market_outcome = _persist_market(source, match, row, cached)
        outcomes[market_outcome] += 1
        if row.price is not None:
            time_semantics.add(row.price.time_semantics)

    imported = outcomes["EVIDENCE_CREATED"] + outcomes["EVIDENCE_UNCHANGED"]
    unavailable = outcomes["UNAVAILABLE_CREATED"] + outcomes["UNAVAILABLE_UNCHANGED"]
    unresolved = sum(
        count
        for name, count in outcomes.items()
        if name.startswith(("UNRESOLVED", "AMBIGUOUS"))
    )
    conflicts = outcomes["CONFLICT"] + sum(
        count for name, count in outcomes.items() if name.endswith("_CONFLICT")
    )
    outside = outcomes["OUTSIDE_CANONICAL_POOL"]
    coverage.status = (
        HistoricalMarketCoverage.Status.COMPLETE
        if unresolved == 0 and conflicts == 0
        else HistoricalMarketCoverage.Status.PARTIAL
    )
    coverage.available = True
    coverage.strategy_version = STRATEGY_VERSION
    coverage.source_url = spec.url
    coverage.source_file = _source_locator(cached)
    coverage.source_file_checksum = cached.checksum
    coverage.source_rows = parsed.source_rows
    coverage.valid_rows = len(parsed.rows)
    coverage.complete_triplet_rows = sum(
        1 for row in parsed.rows if row.price is not None
    )
    coverage.imported_rows = imported
    coverage.unavailable_rows = unavailable
    coverage.outside_canonical_pool_rows = outside
    coverage.unresolved_rows = unresolved
    coverage.conflict_rows = conflicts
    coverage.invalid_rows = parsed.invalid_rows
    coverage.download_count += int(cached.downloaded)
    coverage.reason = (
        "SOURCE_SCOPE_PROCESSED"
        if coverage.status == HistoricalMarketCoverage.Status.COMPLETE
        else "SOURCE_SCOPE_HAS_RECONCILIATION_GAPS"
    )
    coverage.time_semantics = sorted(time_semantics)
    coverage.diagnostics = {
        "schema_family": parsed.schema_family,
        "header_signature": parsed.header_signature,
        "invalid_reasons": parsed.invalid_reasons,
        "outcomes": dict(sorted(outcomes.items())),
        "issues": issues,
        "accounting": {
            "valid_rows": len(parsed.rows),
            "classified_rows": imported
            + unavailable
            + outside
            + unresolved
            + conflicts,
        },
    }
    coverage.completed_at = timezone.now()
    coverage.save()
    return {**_coverage_summary(coverage), "outcome": coverage.status}


def process_competition_market_bootstrap(
    competition, *, cache_only=False, cache_root=None, http_get=None
):
    required_seasons = authoritative_market_seasons(competition)
    summaries = []
    for season in required_seasons:
        if historical_market_is_current(competition, season):
            coverage = HistoricalMarketCoverage.objects.get(
                competition=competition, season=season, source__code=SOURCE_CODE
            )
            summaries.append({**_coverage_summary(coverage), "outcome": "NO_WORK"})
            continue
        summaries.append(
            ingest_completed_season(
                competition,
                season,
                cache_only=cache_only,
                cache_root=cache_root,
                http_get=http_get,
            )
        )
    statuses = {row["status"] for row in summaries}
    if not summaries or statuses <= {HistoricalMarketCoverage.Status.COMPLETE}:
        status = "COMPLETE"
    elif statuses <= {HistoricalMarketCoverage.Status.UNSUPPORTED_SOURCE}:
        status = "UNSUPPORTED_SOURCE"
    else:
        status = "PARTIAL"
    return {
        "competition_id": competition.pk,
        "status": status,
        "seasons": summaries,
    }
