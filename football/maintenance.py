from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone

from football.api_football import (
    APIFootballClient,
    APIFootballError,
    APIFootballOperationBudgetError,
    APIFootballQuotaReserveError,
)
from football.capture.contracts import CaptureConfig
from football.capture.planner import quota_state
from football.models import (
    Competition,
    CompetitionSourceRef,
    MaintenanceRun,
    Match,
    ReconciliationStatus,
    Season,
)
from football.observability.events import emit_event, sanitize_text
from football.prediction.evaluation import run_backtest
from football.sync import sync_catalog_payloads, sync_fixture_payloads


def _local_day(at):
    return at.astimezone(ZoneInfo(settings.TIME_ZONE)).date()


def _claim(run, at):
    run.status = MaintenanceRun.Status.RUNNING
    run.attempt_count += 1
    run.last_attempt_at = at
    run.completed_at = None
    run.error_class = ""
    run.error_message = ""
    run.save(
        update_fields=[
            "status",
            "attempt_count",
            "last_attempt_at",
            "completed_at",
            "error_class",
            "error_message",
            "modified",
        ]
    )
    return run


def _finish(run, status, at, summary, *, error=None, client=None, next_eligible=None):
    run.status = status
    run.completed_at = at
    run.next_eligible_at = next_eligible
    run.summary = summary
    if client is not None:
        run.provider_attempts += getattr(client, "calls", 0)
        run.quota_limit = getattr(client, "daily_limit", None)
        run.quota_remaining_after = getattr(client, "daily_remaining", None)
        run.quota_observed_at = getattr(client, "quota_observed_at", None)
    if error is not None:
        run.error_class = error.__class__.__name__[:120]
        run.error_message = " ".join(sanitize_text(error, 500).split())
    run.save()
    _emit_terminal(run, error=error)
    return {
        "run_id": run.pk,
        "capability": run.capability,
        "status": run.status,
        "due": True,
        "attempt_count": run.attempt_count,
        "summary": run.summary,
    }


def _not_due(run, reason):
    return {
        "run_id": run.pk if run else None,
        "capability": run.capability if run else None,
        "status": "NOT_DUE",
        "due": False,
        "reason": reason,
        "last_status": run.status if run else None,
    }


def _emit_terminal(run, *, error=None):
    if run.status in (MaintenanceRun.Status.SUCCESS, MaintenanceRun.Status.NO_WORK):
        severity = "INFO"
    elif run.status in (
        MaintenanceRun.Status.SKIPPED_QUOTA,
        MaintenanceRun.Status.DEGRADED,
    ):
        severity = "WARNING"
    else:
        severity = "ERROR"
    emit_event(
        event_code="PERIODIC_MAINTENANCE_TERMINAL",
        severity=severity,
        component="maintenance",
        operation=run.capability.casefold(),
        outcome=run.status,
        failure_kind=(
            getattr(error, "failure_kind", "")
            if error is not None
            else (
                "provider_quota"
                if run.status == MaintenanceRun.Status.SKIPPED_QUOTA
                else ""
            )
        ),
        human_summary="A due periodic maintenance capability reached a terminal state.",
        provider=getattr(error, "provider", "") if error is not None else "",
        exception=error,
        context={"capability": run.capability, "maintenance_run_id": run.pk},
    )


def _bounded_client(client_factory, *, at, maximum_attempts, maximum_pages):
    state = quota_state(at, CaptureConfig.from_settings())
    available = state.remaining
    if state.basis == "BOUNDED_BOOTSTRAP":
        available = settings.FOOTBALL_MAINTENANCE_BOOTSTRAP_MAX_ATTEMPTS
    reserve = settings.FOOTBALL_CAPTURE_MANDATORY_RESERVE
    if available - reserve < maximum_attempts:
        raise APIFootballQuotaReserveError(
            "Periodic maintenance cannot fit inside the conservative quota budget.",
            diagnostic_context={"attempts": 0},
        )
    client = client_factory(
        max_pages=maximum_pages,
        max_retries=0,
        daily_reserve=reserve,
    )

    def guard(active_client):
        if active_client.calls >= maximum_attempts:
            raise APIFootballOperationBudgetError(
                "Periodic maintenance reached its provider-attempt bound."
            )

    client.attempt_guard = guard
    return client


@transaction.atomic
def _daily_run(capability, identity, day, at, *, config_snapshot=None):
    run, created = MaintenanceRun.objects.select_for_update().get_or_create(
        logical_identity=identity,
        defaults={
            "capability": capability,
            "period_start": day,
            "started_at": at,
            "last_attempt_at": at,
            "config_snapshot": config_snapshot or {},
        },
    )
    if created:
        return _claim(run, at), None
    if run.status == MaintenanceRun.Status.SKIPPED_QUOTA:
        if run.attempt_count >= settings.FOOTBALL_MAINTENANCE_DAILY_MAX_ATTEMPTS:
            return None, _not_due(run, "DAILY_ATTEMPT_BOUND_REACHED")
        if run.next_eligible_at and at < run.next_eligible_at:
            return None, _not_due(run, "QUOTA_RETRY_NOT_DUE")
        return _claim(run, at), None
    return None, _not_due(run, "DAILY_IDENTITY_ALREADY_TERMINAL")


def run_catalogue_maintenance(*, at=None, client_factory=APIFootballClient):
    at = at or timezone.now()
    day = _local_day(at)
    run, existing = _daily_run(
        MaintenanceRun.Capability.CATALOGUE,
        f"catalogue:{day.isoformat()}",
        day,
        at,
        config_snapshot={
            "timezone": settings.TIME_ZONE,
            "max_attempts": settings.FOOTBALL_MAINTENANCE_CATALOGUE_MAX_ATTEMPTS,
        },
    )
    if existing:
        return existing
    client = None
    try:
        client = _bounded_client(
            client_factory,
            at=at,
            maximum_attempts=settings.FOOTBALL_MAINTENANCE_CATALOGUE_MAX_ATTEMPTS,
            maximum_pages=settings.FOOTBALL_MAINTENANCE_CATALOGUE_MAX_PAGES,
        )
        leagues = client.get_all("leagues")
        bets = client.get_all("odds/bets")
        stats, market = sync_catalog_payloads(leagues, bets)
        summary = {
            "reason": "DAILY_CATALOGUE_EXECUTED",
            "created": stats.created,
            "updated": stats.updated,
            "unchanged": stats.unchanged,
            "skipped": stats.skipped,
            "market_id": market.pk,
            "provider_attempts": client.calls,
        }
        return _finish(run, MaintenanceRun.Status.SUCCESS, at, summary, client=client)
    except APIFootballQuotaReserveError as error:
        retry_at = at + timedelta(hours=settings.FOOTBALL_MAINTENANCE_QUOTA_RETRY_HOURS)
        return _finish(
            run,
            MaintenanceRun.Status.SKIPPED_QUOTA,
            at,
            {"reason": "DEFERRED_DUE_TO_QUOTA"},
            error=error,
            client=client,
            next_eligible=retry_at,
        )
    except APIFootballError as error:
        return _finish(
            run,
            MaintenanceRun.Status.DEGRADED,
            at,
            {"reason": "PROVIDER_FAILURE"},
            error=error,
            client=client,
        )
    except Exception as error:
        return _finish(
            run,
            MaintenanceRun.Status.FAILED,
            at,
            {"reason": "LOCAL_MAINTENANCE_FAILURE"},
            error=error,
            client=client,
        )


def _season_candidates():
    return list(
        Season.objects.filter(
            is_current=True,
            competition__enabled=True,
            matches__isnull=True,
            competition__source_refs__source__code="api_football",
            competition__source_refs__reconciliation_status=ReconciliationStatus.RESOLVED,
        )
        .select_related("competition")
        .distinct()
        .order_by("competition_id", "-year", "id")
    )


def _claim_season(season, day, at):
    identity = f"season-bootstrap:{season.pk}"
    with transaction.atomic():
        run, created = MaintenanceRun.objects.select_for_update().get_or_create(
            logical_identity=identity,
            defaults={
                "capability": MaintenanceRun.Capability.SEASON_BOOTSTRAP,
                "period_start": day,
                "subject_type": "Season",
                "subject_id": season.pk,
                "started_at": at,
                "last_attempt_at": at,
                "config_snapshot": {"timezone": settings.TIME_ZONE},
            },
        )
        if not created:
            if run.status == MaintenanceRun.Status.SUCCESS:
                return None
            if _local_day(run.last_attempt_at) >= day:
                return None
        return _claim(run, at)


def _bootstrap_season(season, day, at, client_factory):
    run = _claim_season(season, day, at)
    if run is None:
        return {"season_id": season.pk, "status": "NOT_DUE"}
    client = None
    try:
        client = _bounded_client(
            client_factory,
            at=at,
            maximum_attempts=settings.FOOTBALL_MAINTENANCE_SEASON_MAX_ATTEMPTS,
            maximum_pages=settings.FOOTBALL_MAINTENANCE_SEASON_MAX_PAGES,
        )
        ref = CompetitionSourceRef.objects.get(
            competition=season.competition,
            source__code="api_football",
            reconciliation_status=ReconciliationStatus.RESOLVED,
        )
        fixtures = client.get_all(
            "fixtures",
            {
                "league": ref.external_id,
                "season": season.year,
                "timezone": settings.TIME_ZONE,
            },
        )
        stats, accepted = sync_fixture_payloads(
            fixtures,
            {ref.external_id: season.competition},
            expected_year=season.year,
        )
        status = (
            MaintenanceRun.Status.SUCCESS if accepted else MaintenanceRun.Status.NO_WORK
        )
        return _finish(
            run,
            status,
            at,
            {
                "reason": (
                    "SEASON_BOOTSTRAP_COMPLETED"
                    if accepted
                    else "SEASON_BOOTSTRAP_EMPTY"
                ),
                "season_id": season.pk,
                "competition_id": season.competition_id,
                "accepted_matches": len(accepted),
                "created": stats.created,
                "updated": stats.updated,
                "unchanged": stats.unchanged,
                "provider_attempts": client.calls,
            },
            client=client,
        )
    except APIFootballQuotaReserveError as error:
        return _finish(
            run,
            MaintenanceRun.Status.SKIPPED_QUOTA,
            at,
            {"reason": "DEFERRED_DUE_TO_QUOTA", "season_id": season.pk},
            error=error,
            client=client,
        )
    except APIFootballError as error:
        return _finish(
            run,
            MaintenanceRun.Status.DEGRADED,
            at,
            {"reason": "PROVIDER_FAILURE", "season_id": season.pk},
            error=error,
            client=client,
        )
    except Exception as error:
        return _finish(
            run,
            MaintenanceRun.Status.FAILED,
            at,
            {"reason": "LOCAL_MAINTENANCE_FAILURE", "season_id": season.pk},
            error=error,
            client=client,
        )


def run_season_maintenance(*, at=None, client_factory=APIFootballClient):
    at = at or timezone.now()
    day = _local_day(at)
    detection, existing = _daily_run(
        MaintenanceRun.Capability.SEASON_BOOTSTRAP,
        f"season-detection:{day.isoformat()}",
        day,
        at,
        config_snapshot={
            "timezone": settings.TIME_ZONE,
            "maximum_bootstraps": settings.FOOTBALL_MAINTENANCE_MAX_SEASONS_PER_DAY,
        },
    )
    if existing:
        return existing
    candidates = _season_candidates()
    results = []
    attempted = 0
    for season in candidates:
        if attempted >= settings.FOOTBALL_MAINTENANCE_MAX_SEASONS_PER_DAY:
            results.append({"season_id": season.pk, "status": "BOUNDED_DEFERRED"})
            continue
        result = _bootstrap_season(season, day, at, client_factory)
        results.append(result)
        if result["status"] != "NOT_DUE":
            attempted += 1
    statuses = {row["status"] for row in results}
    if statuses & {
        MaintenanceRun.Status.FAILED,
        MaintenanceRun.Status.DEGRADED,
        MaintenanceRun.Status.SKIPPED_QUOTA,
    }:
        status = MaintenanceRun.Status.DEGRADED
    elif not candidates or statuses <= {
        "NOT_DUE",
        MaintenanceRun.Status.NO_WORK,
    }:
        status = MaintenanceRun.Status.NO_WORK
    else:
        status = MaintenanceRun.Status.SUCCESS
    return _finish(
        detection,
        status,
        at,
        {
            "reason": "DAILY_SEASON_ELIGIBILITY_CHECK",
            "candidate_season_ids": [season.pk for season in candidates],
            "results": results,
        },
    )


def _evidence_signature():
    aggregate = Match.objects.filter(
        season__competition__enabled=True,
        outcome__in=[value for value, _ in Match.OUTCOMES],
    ).aggregate(
        count=Count("id"), latest_modified=Max("modified"), maximum_id=Max("id")
    )
    return {
        "count": aggregate["count"],
        "maximum_id": aggregate["maximum_id"],
        "latest_modified": (
            aggregate["latest_modified"].isoformat()
            if aggregate["latest_modified"]
            else None
        ),
    }


def _weekly_due(at, *, force=False):
    latest_terminal = (
        MaintenanceRun.objects.filter(
            capability=MaintenanceRun.Capability.WEEKLY_EVALUATION,
            completed_at__isnull=False,
        )
        .order_by("-completed_at", "-id")
        .first()
    )
    latest_evidence = (
        MaintenanceRun.objects.filter(
            capability=MaintenanceRun.Capability.WEEKLY_EVALUATION,
            status__in=(MaintenanceRun.Status.SUCCESS, MaintenanceRun.Status.NO_WORK),
        )
        .order_by("-completed_at", "-id")
        .first()
    )
    if not force and latest_terminal and latest_terminal.completed_at:
        if at < latest_terminal.completed_at + timedelta(
            days=settings.FOOTBALL_MAINTENANCE_WEEKLY_INTERVAL_DAYS
        ):
            return False, latest_terminal
    return True, latest_evidence


def maintenance_status(*, at=None):
    """Return a provider-free due/last-run view for operator status."""
    at = at or timezone.now()
    day = _local_day(at)

    def daily_state(capability, identity):
        run = MaintenanceRun.objects.filter(logical_identity=identity).first()
        due = run is None
        if run and run.status == MaintenanceRun.Status.SKIPPED_QUOTA:
            due = (
                run.attempt_count < settings.FOOTBALL_MAINTENANCE_DAILY_MAX_ATTEMPTS
                and (run.next_eligible_at is None or at >= run.next_eligible_at)
            )
        return {
            "due": due,
            "run_id": run.pk if run else None,
            "last_status": run.status if run else None,
            "attempt_count": run.attempt_count if run else 0,
            "next_eligible_at": (
                run.next_eligible_at.isoformat()
                if run and run.next_eligible_at
                else None
            ),
            "capability": capability,
        }

    latest_weekly = (
        MaintenanceRun.objects.filter(
            capability=MaintenanceRun.Capability.WEEKLY_EVALUATION,
            completed_at__isnull=False,
        )
        .order_by("-completed_at", "-id")
        .first()
    )
    weekly_due = latest_weekly is None or at >= latest_weekly.completed_at + timedelta(
        days=settings.FOOTBALL_MAINTENANCE_WEEKLY_INTERVAL_DAYS
    )
    return {
        "enabled": settings.FOOTBALL_MAINTENANCE_ENABLED,
        "local_day": day.isoformat(),
        "timezone": settings.TIME_ZONE,
        "catalogue": daily_state(
            MaintenanceRun.Capability.CATALOGUE,
            f"catalogue:{day.isoformat()}",
        ),
        "season_detection": daily_state(
            MaintenanceRun.Capability.SEASON_BOOTSTRAP,
            f"season-detection:{day.isoformat()}",
        ),
        "weekly_evaluation": {
            "due": weekly_due,
            "run_id": latest_weekly.pk if latest_weekly else None,
            "last_status": latest_weekly.status if latest_weekly else None,
            "completed_at": (
                latest_weekly.completed_at.isoformat() if latest_weekly else None
            ),
            "interval_days": settings.FOOTBALL_MAINTENANCE_WEEKLY_INTERVAL_DAYS,
            "capability": MaintenanceRun.Capability.WEEKLY_EVALUATION,
        },
    }


def _backtest_population(competition):
    seasons = list(competition.seasons.order_by("-is_current", "-year"))
    for season in seasons:
        years = (season.year - 2, season.year - 1, season.year)
        counts = {
            row["season__year"]: row["count"]
            for row in Match.objects.filter(
                season__competition=competition,
                season__year__in=years,
                outcome__in=[value for value, _ in Match.OUTCOMES],
            )
            .values("season__year")
            .annotate(count=Count("id"))
        }
        if all(counts.get(year, 0) for year in years):
            return season
    return None


def run_weekly_evaluation(*, at=None, force=False, backtest_runner=run_backtest):
    at = at or timezone.now()
    due, previous = _weekly_due(at, force=force)
    if not due:
        return _not_due(previous, "WEEKLY_INTERVAL_NOT_ELAPSED")
    day = _local_day(at)
    identity = f"weekly-evaluation:{day.isoformat()}"
    with transaction.atomic():
        run, created = MaintenanceRun.objects.select_for_update().get_or_create(
            logical_identity=identity,
            defaults={
                "capability": MaintenanceRun.Capability.WEEKLY_EVALUATION,
                "period_start": day,
                "started_at": at,
                "last_attempt_at": at,
                "config_snapshot": {
                    "timezone": settings.TIME_ZONE,
                    "interval_days": settings.FOOTBALL_MAINTENANCE_WEEKLY_INTERVAL_DAYS,
                },
            },
        )
        if not created:
            return _not_due(run, "WEEKLY_IDENTITY_ALREADY_EXISTS")
        _claim(run, at)
    signature = _evidence_signature()
    previous_signature = (
        (previous.summary or {}).get("evidence_signature") if previous else None
    )
    if previous_signature == signature:
        return _finish(
            run,
            MaintenanceRun.Status.NO_WORK,
            at,
            {"reason": "NO_NEW_RESOLVED_EVIDENCE", "evidence_signature": signature},
        )
    experiments = []
    unavailable = []
    errors = []
    for competition in Competition.objects.filter(enabled=True).order_by("id"):
        season = _backtest_population(competition)
        if season is None:
            unavailable.append(
                {"competition_id": competition.pk, "reason": "INSUFFICIENT_SEASONS"}
            )
            continue
        try:
            experiment = backtest_runner(competition, season)
        except Exception as error:
            errors.append(
                {
                    "competition_id": competition.pk,
                    "error_class": error.__class__.__name__,
                    "error_message": " ".join(sanitize_text(error, 500).split()),
                }
            )
            continue
        experiments.append(
            {
                "competition_id": competition.pk,
                "season_id": season.pk,
                "prediction_experiment_id": experiment.pk,
                "selected_hyperparameters": experiment.config.get(
                    "selected_hyperparameters", {}
                ),
            }
        )
    summary = {
        "reason": (
            "WEEKLY_EVALUATION_EXECUTED" if experiments else "NO_ELIGIBLE_POPULATION"
        ),
        "evidence_signature": signature,
        "experiments": experiments,
        "unavailable": unavailable,
        "errors": errors,
    }
    status = (
        MaintenanceRun.Status.DEGRADED
        if errors
        else (
            MaintenanceRun.Status.SUCCESS
            if experiments
            else MaintenanceRun.Status.NO_WORK
        )
    )
    return _finish(run, status, at, summary)


def run_periodic_maintenance(
    *,
    at=None,
    force_weekly=False,
    api_client_factory=APIFootballClient,
    backtest_runner=run_backtest,
):
    at = at or timezone.now()
    if not settings.FOOTBALL_MAINTENANCE_ENABLED:
        return {"status": "DISABLED"}
    catalogue = run_catalogue_maintenance(at=at, client_factory=api_client_factory)
    catalogue_status = catalogue.get("status")
    if catalogue_status == "NOT_DUE":
        catalogue_status = catalogue.get("last_status")
    catalogue_allows_seasons = catalogue_status in {
        MaintenanceRun.Status.SUCCESS,
        MaintenanceRun.Status.NO_WORK,
    }
    seasons = (
        run_season_maintenance(at=at, client_factory=api_client_factory)
        if catalogue_allows_seasons
        else {"status": "SKIPPED", "reason": "CATALOGUE_NOT_HEALTHY"}
    )
    weekly = run_weekly_evaluation(
        at=at,
        force=force_weekly,
        backtest_runner=backtest_runner,
    )
    return {
        "status": "COMPLETED",
        "catalogue": catalogue,
        "seasons": seasons,
        "weekly": weekly,
    }
