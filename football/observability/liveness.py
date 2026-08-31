from dataclasses import dataclass
from datetime import timedelta

from football.models import PipelineRun

TERMINAL_ATTEMPT_STATUSES = (
    PipelineRun.Status.SUCCESS,
    PipelineRun.Status.DEGRADED,
    PipelineRun.Status.FAILED,
)
SCHEDULER_LIVENESS_STATUSES = (*TERMINAL_ATTEMPT_STATUSES, PipelineRun.Status.NO_WORK)


@dataclass(frozen=True)
class LivenessState:
    enabled: bool
    overdue: bool
    threshold_seconds: int
    last_attempted: PipelineRun | None
    last_scheduler_activity: PipelineRun | None
    reference_at: object


def last_attempted():
    return (
        PipelineRun.objects.filter(
            completed_at__isnull=False,
            status__in=TERMINAL_ATTEMPT_STATUSES,
        )
        .order_by("-completed_at", "-id")
        .first()
    )


def last_scheduler_activity():
    return (
        PipelineRun.objects.filter(
            trigger=PipelineRun.Trigger.SCHEDULER,
            completed_at__isnull=False,
            status__in=SCHEDULER_LIVENESS_STATUSES,
        )
        .order_by("-completed_at", "-id")
        .first()
    )


def evaluate_liveness(
    *, now, enabled, cadence_seconds, grace_seconds, monitoring_since
):
    threshold_seconds = cadence_seconds + grace_seconds
    attempted = last_attempted()
    scheduler_activity = last_scheduler_activity()
    reference_at = monitoring_since
    if scheduler_activity and (
        reference_at is None or scheduler_activity.completed_at > reference_at
    ):
        reference_at = scheduler_activity.completed_at
    overdue = bool(
        enabled
        and reference_at is not None
        and now - reference_at > timedelta(seconds=threshold_seconds)
    )
    return LivenessState(
        enabled=enabled,
        overdue=overdue,
        threshold_seconds=threshold_seconds,
        last_attempted=attempted,
        last_scheduler_activity=scheduler_activity,
        reference_at=reference_at,
    )
