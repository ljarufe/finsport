"""Provider-free API-Football quota authority, reserve, and operator summary."""

from __future__ import annotations

from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.utils import timezone

from football.models import (
    CapitalExecutionState,
    CapitalPosition,
    CaptureRun,
    CaptureWorkItem,
    MaintenanceRun,
    Match,
    ProviderCallAudit,
)
from football.providers.api_football import FIXTURE_TIMEZONE

FULFILLED = {
    CaptureWorkItem.Status.SUCCESS,
    CaptureWorkItem.Status.SUCCESS_EMPTY,
    CaptureWorkItem.Status.LATE_CAPTURE,
}
OPEN_RESULT_TIMEZONE = FIXTURE_TIMEZONE
DIRECTED_RESULT_FALLBACK = "DATE_SWEEP_EXPECTED_FIXTURE_MISSING"
RESULT_WAKE_SECONDS = 300


def epoch_bounds(at):
    utc_at = at.astimezone(UTC)
    start = utc_at.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _unattributed_legacy_attempts(model, *, after=None, since=None, at):
    """Count only run-summary attempts not covered by linked physical audits."""

    runs = model.objects.filter(
        started_at__lte=at,
        quota_observed_at__isnull=True,
    )
    if after is not None:
        runs = runs.filter(started_at__gt=after)
    if since is not None:
        runs = runs.filter(started_at__gte=since)
    runs = runs.annotate(
        audited_attempts=Count(
            "provider_call_audits",
            filter=Q(provider_call_audits__provider="API_FOOTBALL"),
        )
    )
    return sum(max(0, row.provider_attempts - row.audited_attempts) for row in runs)


def _epoch_physical_attempts(epoch_start, at):
    audited = ProviderCallAudit.objects.filter(
        provider="API_FOOTBALL", started_at__gte=epoch_start, started_at__lte=at
    ).count()
    legacy = sum(
        _unattributed_legacy_attempts(model, since=epoch_start, at=at)
        for model in (CaptureRun, MaintenanceRun)
    )
    return audited + legacy


def quota_state(at, config):
    """Return conservative header authority without synthesizing a reset."""

    latest = (
        ProviderCallAudit.objects.filter(
            provider="API_FOOTBALL",
            quota_remaining__isnull=False,
            quota_observed_at__lte=at,
        )
        .order_by("-quota_observed_at", "-id")
        .first()
    )
    if latest is None:
        legacy_candidates = [
            row
            for row in (
                CaptureRun.objects.filter(
                    quota_remaining_after__isnull=False,
                    quota_observed_at__lte=at,
                )
                .order_by("-quota_observed_at", "-id")
                .first(),
                MaintenanceRun.objects.filter(
                    quota_remaining_after__isnull=False,
                    quota_observed_at__lte=at,
                )
                .order_by("-quota_observed_at", "-id")
                .first(),
            )
            if row is not None
        ]
        legacy = max(
            legacy_candidates,
            key=lambda row: row.quota_observed_at,
            default=None,
        )
        epoch_start, epoch_end = epoch_bounds(at)
        if legacy is not None:
            later_attempts = ProviderCallAudit.objects.filter(
                provider="API_FOOTBALL",
                started_at__gt=legacy.quota_observed_at,
                started_at__lte=at,
            ).count()
            later_attempts += sum(
                _unattributed_legacy_attempts(
                    model, after=legacy.quota_observed_at, at=at
                )
                for model in (CaptureRun, MaintenanceRun)
            )
            current = epoch_start <= legacy.quota_observed_at < epoch_end
            return {
                "basis": (
                    "HEADER_CURRENT_UTC_EPOCH" if current else "HEADER_STALE_EPOCH"
                ),
                "limit": legacy.quota_limit,
                "remaining": max(0, legacy.quota_remaining_after - later_attempts),
                "observed_at": legacy.quota_observed_at,
                "freshness_seconds": max(
                    0, int((at - legacy.quota_observed_at).total_seconds())
                ),
                "stale_establishing_attempt_available": (
                    not current and _epoch_physical_attempts(epoch_start, at) == 0
                ),
            }
        attempts = _epoch_physical_attempts(epoch_start, at)
        return {
            "basis": "BOUNDED_BOOTSTRAP",
            "limit": None,
            "remaining": max(0, config.bootstrap_max_attempts - attempts),
            "observed_at": None,
            "freshness_seconds": None,
            "stale_establishing_attempt_available": False,
        }
    later_attempts = (
        ProviderCallAudit.objects.filter(
            provider="API_FOOTBALL",
            started_at__lte=at,
        )
        .filter(
            Q(started_at__gt=latest.quota_observed_at)
            | Q(started_at=latest.quota_observed_at, pk__gt=latest.pk)
        )
        .count()
    )
    epoch_start, epoch_end = epoch_bounds(at)
    current = epoch_start <= latest.quota_observed_at < epoch_end
    return {
        "basis": "HEADER_CURRENT_UTC_EPOCH" if current else "HEADER_STALE_EPOCH",
        "limit": latest.quota_limit,
        "remaining": max(0, latest.quota_remaining - later_attempts),
        "observed_at": latest.quota_observed_at,
        "freshness_seconds": max(
            0, int((at - latest.quota_observed_at).total_seconds())
        ),
        "stale_establishing_attempt_available": (
            not current and _epoch_physical_attempts(epoch_start, at) == 0
        ),
    }


def _fixture_dates(at, config):
    local_day = at.astimezone(ZoneInfo(settings.TIME_ZONE)).date()
    return [
        local_day + timedelta(days=offset)
        for offset in range(config.discovery_days_ahead + 1)
    ]


def _fixture_reserve(at, config):
    if not config.discovery_enabled:
        return 0, []
    dates = _fixture_dates(at, config)
    fulfilled = set(
        CaptureWorkItem.objects.filter(
            logical_identity__in=[
                f"api_football:discovery:{day.isoformat()}" for day in dates
            ],
            status__in=FULFILLED,
        ).values_list("logical_identity", flat=True)
    )
    missing = [
        day
        for day in dates
        if f"api_football:discovery:{day.isoformat()}" not in fulfilled
    ]
    recovery_count = (
        CapitalPosition.objects.filter(
            status=CapitalPosition.Status.OPEN,
            match__status_short="PST",
            match__source_refs__source__code="api_football",
            match__source_refs__reconciliation_status="RESOLVED",
        )
        .values("match_id")
        .distinct()
        .count()
    )
    return len(missing) + recovery_count, missing


def _t30_obligations(at, config, epoch_end):
    window = next(item for item in config.windows if item.name == "market-t30m")
    matches = Match.objects.filter(
        season__competition__enabled=True,
        status_short__in=("NS", "TBD"),
        kickoff__gt=at,
        kickoff__lte=epoch_end + window.offset,
    ).order_by("kickoff", "id")
    obligations = []
    for match in matches:
        target = match.kickoff - window.offset
        if target >= epoch_end:
            continue
        work = CaptureWorkItem.objects.filter(
            match=match,
            purpose=CaptureWorkItem.Purpose.ODDS_CAPTURE,
            intended_window=window.name,
        )
        if work.filter(status__in=FULFILLED).exists():
            continue
        if at > target + window.late_tolerance:
            continue
        obligations.append((match.pk, target))
    return obligations


def result_check_opportunity(deadline, at):
    """First five-minute UTC wake for future debt; overdue debt uses this wake."""

    if deadline <= at:
        return at.astimezone(UTC)
    utc_deadline = deadline.astimezone(UTC)
    bucket_minutes = RESULT_WAKE_SECONDS // 60
    floor = utc_deadline.replace(
        minute=utc_deadline.minute - utc_deadline.minute % bucket_minutes,
        second=0,
        microsecond=0,
    )
    return (
        floor
        if utc_deadline == floor
        else floor + timedelta(seconds=RESULT_WAKE_SECONDS)
    )


def _open_result_matches(at, epoch_end):
    match_ids = set()
    sweep_opportunities = set()
    fallback_match_ids = set()
    next_deadlines = []
    positions = (
        CapitalPosition.objects.filter(status=CapitalPosition.Status.OPEN)
        .exclude(match__status_short="PST")
        .select_related("match")
    )
    for position in positions:
        deadline = position.next_result_check_at or (
            position.match.kickoff + timedelta(minutes=130)
        )
        wake = result_check_opportunity(deadline, at)
        if wake < epoch_end:
            match_ids.add(position.match_id)
            if position.result_refresh_error.startswith(DIRECTED_RESULT_FALLBACK):
                fallback_match_ids.add(position.match_id)
            else:
                sweep_opportunities.add(
                    (
                        position.match.kickoff.astimezone(
                            ZoneInfo(OPEN_RESULT_TIMEZONE)
                        ).date(),
                        wake,
                    )
                )
            next_deadlines.append(deadline)
    return match_ids, sweep_opportunities, fallback_match_ids, next_deadlines


def dynamic_reserve(at, config):
    _, epoch_end = epoch_bounds(at)
    fixture, missing_dates = _fixture_reserve(at, config)
    t30 = _t30_obligations(at, config, epoch_end)
    open_ids, sweep_opportunities, fallback_ids, open_deadlines = _open_result_matches(
        at, epoch_end
    )
    sweep_dates = {day for day, _ in sweep_opportunities}
    components = {
        "fixture": fixture,
        "t30": len(t30),
        "open_result": len(sweep_opportunities) + len(fallback_ids),
        "execution_quote": 0,
    }
    components["total"] = sum(components.values())
    deadlines = [target for _, target in t30] + open_deadlines
    return {
        **components,
        "epoch_end": epoch_end,
        "next_critical_deadline": min(deadlines) if deadlines else None,
        "missing_fixture_dates": missing_dates,
        "t30_match_ids": [match_id for match_id, _ in t30],
        "open_result_match_ids": sorted(open_ids),
        "open_result_sweep_dates": sorted(sweep_dates),
        "open_result_sweep_opportunities": [
            {"date": day.isoformat(), "wake_at": wake.isoformat()}
            for day, wake in sorted(sweep_opportunities)
        ],
        "open_result_fallback_match_ids": sorted(fallback_ids),
    }


def quota_summary(*, at=None, config=None):
    from football.capture.contracts import CaptureConfig

    at = at or timezone.now()
    config = config or CaptureConfig.from_settings()
    state = quota_state(at, config)
    reserve = dynamic_reserve(at, config)
    remaining = state["remaining"]
    surplus = max(0, remaining - reserve["total"])
    epoch_start, epoch_end = epoch_bounds(at)
    usage = {
        row["capability"]: {
            "attempts": row["attempts"],
            "pages": row["pages"] or 0,
            "retries": row["retries"] or 0,
        }
        for row in ProviderCallAudit.objects.filter(
            provider="API_FOOTBALL",
            started_at__gte=epoch_start,
            started_at__lt=epoch_end,
        )
        .values("capability")
        .annotate(
            attempts=Count("id"),
            pages=Count("id", filter=Q(outcome="SUCCESS")),
            retries=Sum("retry_number"),
        )
    }
    local_day = at.astimezone(ZoneInfo(settings.TIME_ZONE)).date()
    latest_reconciliation = (
        MaintenanceRun.objects.filter(
            capability=MaintenanceRun.Capability.CURRENT_SEASON_RECONCILIATION
        )
        .order_by("-period_start", "-id")
        .first()
    )
    return {
        "provider": "API_FOOTBALL",
        "local_date": local_day.isoformat(),
        "epoch_start": epoch_start.isoformat(),
        "epoch_end": epoch_end.isoformat(),
        "quota": {
            **state,
            "observed_at": (
                state["observed_at"].isoformat() if state["observed_at"] else None
            ),
        },
        "reserve": {
            key: reserve[key]
            for key in ("fixture", "t30", "open_result", "execution_quote", "total")
        },
        "surplus": surplus,
        "next_critical_deadline": (
            reserve["next_critical_deadline"].isoformat()
            if reserve["next_critical_deadline"]
            else None
        ),
        "usage_by_capability": usage,
        "backlog": {
            "fixture_dates_missing": [
                value.isoformat() for value in reserve["missing_fixture_dates"]
            ],
            "t30_obligations": len(reserve["t30_match_ids"]),
            "open_positions": CapitalPosition.objects.filter(
                status=CapitalPosition.Status.OPEN
            ).count(),
            "open_result_fixtures": len(reserve["open_result_match_ids"]),
            "open_result_sweep_dates": [
                value.isoformat() for value in reserve["open_result_sweep_dates"]
            ],
            "open_result_sweep_opportunities": reserve[
                "open_result_sweep_opportunities"
            ],
            "open_result_directed_fallbacks": len(
                reserve["open_result_fallback_match_ids"]
            ),
            "pending_capacity": CapitalExecutionState.objects.filter(
                status=CapitalExecutionState.Status.PENDING_CAPACITY,
                match__kickoff__gt=at,
            ).count(),
            "nonbet_result_debt": Match.objects.filter(
                season__competition__enabled=True,
                kickoff__lt=at,
                outcome="",
            )
            .exclude(capital_positions__status=CapitalPosition.Status.OPEN)
            .count(),
            "last_current_season_reconciliation": (
                latest_reconciliation.completed_at.isoformat()
                if latest_reconciliation and latest_reconciliation.completed_at
                else None
            ),
        },
    }
