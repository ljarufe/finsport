import logging

from django.db import transaction
from django.utils import timezone

from football.models import Competition, HistoricalCoverage, Source
from football.observability.events import emit_event, sanitize_text
from football.providers.football_data import (
    SOURCE_BASE_URL,
    SOURCE_CODE,
    SOURCE_NAME,
    adapter_for,
)

from .contracts import (
    HistoricalMappingError,
    HistoricalParserError,
    HistoricalSourceUnavailable,
)
from .reconciliation import (
    ReconciliationStats,
    ensure_competition_ref,
    reconcile_result,
)

logger = logging.getLogger(__name__)
STRATEGY_VERSION = "fs011-football-data-v1"
TEAM_MAPPING_ISSUES = {
    "AMBIGUOUS_TEAM_MAPPING",
    "EXPLICIT_TEAM_ALIAS_TARGET_MISSING",
    "UNMAPPED_TEAM_IDENTITY",
}


def _required_seasons(competition):
    return list(competition.seasons.filter(is_current=False).order_by("year", "id"))


def required_season_years(competition):
    return [season.year for season in _required_seasons(competition)]


def _required_window_is_current(required, current_required, coverage):
    """Accept only an audited contiguous old prefix outside source availability."""
    if not current_required:
        return not required
    if not required:
        return False

    try:
        start = current_required.index(required[0])
    except ValueError:
        return False

    if required != current_required[start:]:
        return False

    omitted_prefix = current_required[:start]
    if not omitted_prefix:
        return True

    outside_source_window = []
    for issue in (coverage.diagnostics or {}).get("issues", []):
        if issue.get("reason") != "SOURCE_OUTSIDE_AVAILABLE_HISTORY_WINDOW":
            continue
        try:
            outside_source_window.append(int(issue["season"]))
        except (KeyError, TypeError, ValueError):
            return False

    return sorted(set(outside_source_window)) == omitted_prefix


def historical_coverage_is_current(competition, coverage=None):
    if coverage is None:
        try:
            coverage = competition.historical_coverage
        except HistoricalCoverage.DoesNotExist:
            return False
    try:
        required = sorted(int(year) for year in coverage.required_seasons)
        covered = sorted(int(year) for year in coverage.covered_seasons)
    except (TypeError, ValueError):
        return False
    current_required = required_season_years(competition)
    return (
        coverage.status == HistoricalCoverage.Status.COMPLETE
        and coverage.strategy_version == STRATEGY_VERSION
        and _required_window_is_current(required, current_required, coverage)
        and covered == required
        and not coverage.unresolved_seasons
    )


def _bounded_issues(issues, unresolved_teams):
    team_summaries = [
        {
            "reason": code,
            "source": SOURCE_CODE,
            "external_team_name": external_name,
            "affected_seasons": sorted(item["seasons"]),
            "count": item["count"],
        }
        for (code, external_name), item in sorted(unresolved_teams.items())
    ]
    return [*issues, *team_summaries][:100]


@transaction.atomic
def request_historical_bootstrap(
    competition, *, activate=True, reason="OPERATOR_REQUEST"
):
    if not isinstance(competition, Competition):
        competition = Competition.objects.select_for_update().get(pk=competition)
    else:
        competition = Competition.objects.select_for_update().get(pk=competition.pk)
    now = timezone.now()
    coverage, _ = HistoricalCoverage.objects.select_for_update().get_or_create(
        competition=competition,
        defaults={"strategy_version": STRATEGY_VERSION},
    )
    if coverage.status == HistoricalCoverage.Status.RUNNING:
        return coverage
    coverage.activation_requested = activate or coverage.activation_requested
    coverage.requested_at = now
    coverage.reason = reason
    if (
        reason == "MANUAL_RETRY_REQUESTED"
        and coverage.status != coverage.Status.RUNNING
    ):
        coverage.status = coverage.Status.NOT_ATTEMPTED
    coverage.save(
        update_fields=[
            "activation_requested",
            "requested_at",
            "reason",
            "status",
            "modified",
        ]
    )
    operationally_complete = historical_coverage_is_current(competition, coverage)
    if activate and operationally_complete:
        competition.enabled = True
        competition.save(update_fields=["enabled", "modified"])
    if competition.enabled and not operationally_complete:
        competition.enabled = False
        competition.save(update_fields=["enabled", "modified"])
    event_code = (
        "HISTORICAL_BOOTSTRAP_MANUAL_RETRY_REQUESTED"
        if reason == "MANUAL_RETRY_REQUESTED"
        else "HISTORICAL_BOOTSTRAP_REQUESTED"
    )
    emit_event(
        event_code=event_code,
        severity="INFO",
        component="historical_ingestion",
        operation="request",
        outcome="REQUESTED",
        human_summary="An operator requested one-shot completed-season ingestion.",
        competition_id=competition.pk,
        context={"activation_requested": coverage.activation_requested},
    )
    if activate and not operationally_complete:
        emit_event(
            event_code="HISTORICAL_ACTIVATION_BLOCKED",
            severity="WARNING",
            component="historical_ingestion",
            operation="activation",
            outcome="BLOCKED",
            human_summary="Competition activation remains blocked by incomplete historical coverage.",
            competition_id=competition.pk,
            context={
                "status": coverage.status,
                "reason": coverage.reason,
                "automatic_retry": False,
            },
        )
    return coverage


def _finish(
    coverage,
    *,
    status,
    reason,
    covered,
    unresolved,
    stats,
    downloads,
    error=None,
    issues=None,
):
    now = timezone.now()
    coverage.status = status
    coverage.covered_seasons = sorted(covered)
    coverage.unresolved_seasons = sorted(unresolved)
    coverage.download_count = downloads
    coverage.rows_mapped = stats.mapped
    coverage.rows_reconciled = stats.reconciled
    coverage.rows_unchanged = stats.unchanged
    coverage.rows_created = stats.created
    coverage.ambiguity_count = stats.ambiguities
    coverage.conflict_count = stats.conflicts
    coverage.reason = reason[:200]
    coverage.completed_at = now
    coverage.diagnostics = {
        "required_seasons": coverage.required_seasons,
        "covered_seasons": coverage.covered_seasons,
        "unresolved_seasons": coverage.unresolved_seasons,
        "automatic_retry": False,
        "error_class": type(error).__name__ if error else "",
        "error_message": sanitize_text(error, 500) if error else "",
        "issues": (issues or [])[:100],
    }
    coverage.save()
    competition = coverage.competition
    should_enable = (
        historical_coverage_is_current(coverage.competition, coverage)
        and coverage.activation_requested
    )
    if competition.enabled != should_enable:
        competition.enabled = should_enable
        competition.save(update_fields=["enabled", "modified"])
    severity = "INFO" if status == HistoricalCoverage.Status.COMPLETE else "WARNING"
    if status == HistoricalCoverage.Status.FAILED:
        severity = "ERROR"
    emit_event(
        event_code=f"HISTORICAL_BOOTSTRAP_{status}",
        severity=severity,
        component="historical_ingestion",
        operation="bootstrap",
        outcome=status,
        failure_kind="historical_ingestion" if error else "",
        human_summary="One-shot completed-season historical ingestion reached a terminal state.",
        exception=error if status == HistoricalCoverage.Status.FAILED else None,
        competition_id=competition.pk,
        context={
            "source": coverage.source.code if coverage.source_id else "",
            "required_seasons": coverage.required_seasons,
            "covered_seasons": coverage.covered_seasons,
            "unresolved_seasons": coverage.unresolved_seasons,
            "rows_fetched": coverage.rows_fetched,
            "rows_mapped": coverage.rows_mapped,
            "rows_reconciled": coverage.rows_reconciled,
            "rows_unchanged": coverage.rows_unchanged,
            "rows_created": coverage.rows_created,
            "ambiguity_count": coverage.ambiguity_count,
            "conflict_count": coverage.conflict_count,
            "reason": coverage.reason,
            "activated": competition.enabled,
            "automatic_retry": False,
        },
    )
    return coverage


def process_historical_bootstrap(competition, *, adapter=None, adapter_kwargs=None):
    if not isinstance(competition, Competition):
        competition = Competition.objects.get(pk=competition)
    coverage = request_historical_bootstrap(
        competition, activate=False, reason="PROCESS_REQUESTED"
    )
    if historical_coverage_is_current(competition, coverage):
        return coverage
    required = _required_seasons(competition)
    now = timezone.now()
    source, _ = Source.objects.get_or_create(
        code=SOURCE_CODE, defaults={"name": SOURCE_NAME, "base_url": SOURCE_BASE_URL}
    )
    coverage.source = source
    coverage.status = HistoricalCoverage.Status.RUNNING
    coverage.strategy_version = STRATEGY_VERSION
    coverage.required_seasons = [season.year for season in required]
    coverage.covered_seasons = []
    coverage.unresolved_seasons = []
    coverage.attempt_count += 1
    coverage.rows_fetched = 0
    coverage.started_at = now
    coverage.completed_at = None
    coverage.reason = "HISTORICAL_BOOTSTRAP_STARTED"
    coverage.save()
    emit_event(
        event_code="HISTORICAL_BOOTSTRAP_STARTED",
        severity="INFO",
        component="historical_ingestion",
        operation="bootstrap",
        outcome="RUNNING",
        human_summary="One-shot completed-season historical ingestion started.",
        competition_id=competition.pk,
        context={
            "required_seasons": coverage.required_seasons,
            "source": SOURCE_CODE,
        },
    )
    totals = ReconciliationStats()
    covered = []
    unresolved = []
    issues = []
    unresolved_teams = {}
    source_empty_seasons = set()
    active_adapter = adapter
    try:
        active_adapter = active_adapter or adapter_for(
            competition, **(adapter_kwargs or {})
        )
        ensure_competition_ref(source, competition, active_adapter.external_competition)
        for season in required:
            records = active_adapter.records_for_season(season)
            coverage.rows_fetched += len(records)
            skipped_non_final = (
                getattr(active_adapter, "season_diagnostics", {})
                .get(season.year, {})
                .get("non_final_rows_skipped", 0)
            )
            if skipped_non_final:
                issues.append(
                    {
                        "season": season.year,
                        "reason": "NON_FINAL_SOURCE_ROWS_SKIPPED",
                        "count": skipped_non_final,
                    }
                )
            season_stats = ReconciliationStats()
            if not records:
                if not skipped_non_final:
                    source_empty_seasons.add(season.year)
                unresolved.append(season.year)
                issues.append(
                    {
                        "season": season.year,
                        "reason": "SOURCE_HAS_NO_ROWS_FOR_REQUIRED_SEASON",
                    }
                )
                continue
            for record in records:
                try:
                    if record.source_code != SOURCE_CODE:
                        raise HistoricalMappingError("SOURCE_IDENTITY_MISMATCH")
                    if (
                        record.competition_external_id
                        != active_adapter.external_competition
                    ):
                        raise HistoricalMappingError("COMPETITION_MAPPING_MISMATCH")
                    if record.season_year != season.year:
                        raise HistoricalMappingError("SEASON_MAPPING_MISMATCH")
                    season_stats.add(
                        reconcile_result(source, competition, season, record)
                    )
                except HistoricalMappingError as error:
                    season_stats.ambiguities += 1
                    mapping_reason = sanitize_text(error, 200)
                    code, separator, external_name = mapping_reason.partition(":")
                    if separator and code in TEAM_MAPPING_ISSUES:
                        item = unresolved_teams.setdefault(
                            (code, external_name), {"seasons": set(), "count": 0}
                        )
                        item["seasons"].add(season.year)
                        item["count"] += 1
                    else:
                        issues.append(
                            {
                                "season": season.year,
                                "external_id": record.external_id,
                                "reason": mapping_reason,
                            }
                        )
            totals.add(season_stats)
            if season_stats.ambiguities or season_stats.conflicts:
                unresolved.append(season.year)
            elif season_stats.reconciled == len(records):
                covered.append(season.year)
            else:
                unresolved.append(season.year)
        downloads = active_adapter.download_count

        catalogue_years = [season.year for season in required]
        source_supported_years = [
            year for year in catalogue_years if year not in source_empty_seasons
        ]
        outside_source_window = []

        if source_supported_years:
            first_supported_year = source_supported_years[0]
            outside_source_window = [
                year for year in catalogue_years if year < first_supported_year
            ]

        if outside_source_window:
            outside_source_window_set = set(outside_source_window)

            coverage.required_seasons = [
                year
                for year in catalogue_years
                if year not in outside_source_window_set
            ]

            unresolved = [
                year for year in unresolved if year not in outside_source_window_set
            ]

            for issue in issues:
                if (
                    issue.get("season") in outside_source_window_set
                    and issue.get("reason") == "SOURCE_HAS_NO_ROWS_FOR_REQUIRED_SEASON"
                ):
                    issue["reason"] = "SOURCE_OUTSIDE_AVAILABLE_HISTORY_WINDOW"

        coverage.save(
            update_fields=[
                "rows_fetched",
                "required_seasons",
                "modified",
            ]
        )

        missing = set(coverage.required_seasons) - set(covered)
        unresolved = sorted(set(unresolved) | missing)

        if not required:
            status = HistoricalCoverage.Status.COMPLETE
            reason = "NO_COMPLETED_SEASONS_REQUIRED"
        elif not unresolved:
            status = HistoricalCoverage.Status.COMPLETE
            reason = (
                "ALL_SOURCE_SUPPORTED_COMPLETED_SEASONS_COVERED"
                if outside_source_window
                else "ALL_REQUIRED_COMPLETED_SEASONS_COVERED"
            )
        else:
            status = HistoricalCoverage.Status.PARTIAL
            reason = "REQUIRED_COMPLETED_SEASONS_UNRESOLVED"
        return _finish(
            coverage,
            status=status,
            reason=reason,
            covered=covered,
            unresolved=unresolved,
            stats=totals,
            downloads=downloads,
            issues=_bounded_issues(issues, unresolved_teams),
        )
    except HistoricalSourceUnavailable as error:
        unresolved = sorted(set(coverage.required_seasons) - set(covered))
        status = (
            HistoricalCoverage.Status.PARTIAL
            if covered
            else HistoricalCoverage.Status.UNAVAILABLE
        )
        return _finish(
            coverage,
            status=status,
            reason=str(error) or "APPROVED_SOURCE_UNAVAILABLE",
            covered=covered,
            unresolved=unresolved,
            stats=totals,
            downloads=getattr(active_adapter, "download_count", 0),
            error=error,
            issues=_bounded_issues(issues, unresolved_teams),
        )
    except HistoricalParserError as error:
        unresolved = sorted(set(coverage.required_seasons) - set(covered))
        return _finish(
            coverage,
            status=HistoricalCoverage.Status.FAILED,
            reason=str(error) or "HISTORICAL_SOURCE_PARSER_FAILURE",
            covered=covered,
            unresolved=unresolved,
            stats=totals,
            downloads=getattr(active_adapter, "download_count", 0),
            error=error,
            issues=_bounded_issues(issues, unresolved_teams),
        )
    except Exception as error:
        logger.exception(
            "Unexpected historical bootstrap failure for competition_id=%s",
            competition.pk,
        )
        unresolved = sorted(set(coverage.required_seasons) - set(covered))
        return _finish(
            coverage,
            status=HistoricalCoverage.Status.FAILED,
            reason="UNEXPECTED_HISTORICAL_INGESTION_FAILURE",
            covered=covered,
            unresolved=unresolved,
            stats=totals,
            downloads=getattr(active_adapter, "download_count", 0),
            error=error,
            issues=_bounded_issues(issues, unresolved_teams),
        )
