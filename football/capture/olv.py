"""FS-023 opportunity learning value for acquisition priority, never strategy P&L."""

from datetime import datetime, time, timedelta
from math import sqrt
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, F, Q

from football.models import CaptureWorkItem, Season

PRODUCTION_WEIGHTS = (0.60, 0.25, 0.15)
DIAGNOSTIC_WEIGHTS = {(0.50, 0.30, 0.20), (0.70, 0.20, 0.10)}


def score(
    attempts_current,
    successes_current,
    attempts_previous,
    successes_previous,
    successful_today,
    *,
    weights=PRODUCTION_WEIGHTS,
):
    if weights != PRODUCTION_WEIGHTS and weights not in DIAGNOSTIC_WEIGHTS:
        raise ValueError("FS023_OLV_WEIGHTS_NOT_FROZEN")
    if (
        any(
            value < 0
            for value in (
                attempts_current,
                successes_current,
                attempts_previous,
                successes_previous,
                successful_today,
            )
        )
        or successes_current > attempts_current
        or successes_previous > attempts_previous
    ):
        raise ValueError("FS023_OLV_COUNTS_INVALID")
    attempts = attempts_current + 0.25 * attempts_previous
    successes = successes_current + 0.25 * successes_previous
    exploration = 1 / sqrt(1 + attempts)
    quality = (1 + successes) / (2 + attempts)
    coverage = 1 / (1 + successful_today)
    return weights[0] * exploration + weights[1] * quality + weights[2] * coverage


def _usable(work):
    if work.olv_usable is not None:
        return work.olv_usable
    usable = False
    if (
        work.status in {"SUCCESS", "LATE_CAPTURE"}
        and work.completed_at is not None
        and work.not_after is not None
        and work.executed_at is not None
        and work.completed_at <= work.not_after
        and work.completed_at < work.match.kickoff
    ):
        from football.prediction.market import market_selection_as_of

        selection = market_selection_as_of(
            work.match,
            work.completed_at,
            not_before=work.executed_at,
            capture_work=work,
        )
        usable = len(selection.quotes) >= 2
    if work.pk and work.actual_attempts:
        type(work).objects.filter(pk=work.pk, olv_usable__isnull=True).update(
            olv_usable=usable
        )
        work.olv_usable = usable
    return usable


def competition_score(competition_id, at, *, weights=PRODUCTION_WEIGHTS):
    seasons = list(
        Season.objects.filter(competition_id=competition_id)
        .order_by("-year")
        .values_list("pk", flat=True)[:2]
    )
    if not seasons:
        return score(0, 0, 0, 0, 0, weights=weights)
    eligible = CaptureWorkItem.objects.filter(
        match__season_id__in=seasons,
        intended_window="market-t10m",
        actual_attempts__gt=0,
        executed_at__isnull=False,
        not_after__isnull=False,
        executed_at__lte=F("not_after"),
    )
    # Legacy T10 rows are classified once. Subsequent wakes aggregate the
    # persisted result without revalidating every prior bookmaker observation.
    for work in eligible.filter(olv_usable__isnull=True).select_related("match"):
        _usable(work)
    local_day = at.astimezone(ZoneInfo(settings.TIME_ZONE)).date()
    day_start = datetime.combine(
        local_day, time.min, tzinfo=ZoneInfo(settings.TIME_ZONE)
    )
    day_end = day_start + timedelta(days=1)
    rows = {
        row["match__season_id"]: row
        for row in eligible.values("match__season_id").annotate(
            attempts=Count("pk"),
            successes=Count("pk", filter=Q(olv_usable=True)),
            successful_today=Count(
                "pk",
                filter=Q(
                    olv_usable=True,
                    completed_at__gte=day_start,
                    completed_at__lt=day_end,
                ),
            ),
        )
    }
    current = rows.get(seasons[0], {})
    previous = rows.get(seasons[1], {}) if len(seasons) > 1 else {}
    return score(
        current.get("attempts", 0),
        current.get("successes", 0),
        previous.get("attempts", 0),
        previous.get("successes", 0),
        sum(row["successful_today"] for row in rows.values()),
        weights=weights,
    )


def priority(item, at, value):
    remaining = max(0, (item.not_after - at).total_seconds())
    urgency_bucket = int(remaining // timedelta(seconds=180).total_seconds())
    return (
        2,
        urgency_bucket,
        -value,
        item.not_after,
        item.match.kickoff,
        item.match.pk,
    )
