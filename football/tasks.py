from celery import shared_task
from django.conf import settings
from django.utils import timezone

from football.capture import run_capture
from football.models import CaptureRun


@shared_task(name="football.capture.wake")
def wake_capture_planner():
    """Wake the shared planner; all eligibility and quota logic stays in service."""
    if not settings.FOOTBALL_CAPTURE_ENABLED:
        return {"status": "DISABLED", "provider_attempts": 0}
    try:
        result = run_capture(trigger=CaptureRun.Trigger.SCHEDULER)
    except Exception as error:  # Persist failures that occur before executor audit.
        message = " ".join(str(error or "").split())[:500]
        now = timezone.now()
        run = CaptureRun.objects.create(
            trigger=CaptureRun.Trigger.SCHEDULER,
            status=CaptureRun.Status.FAILED,
            planning_at=now,
            started_at=now,
            completed_at=now,
            failures=1,
            error_class=error.__class__.__name__[:120],
            error_message=message,
            summary={"status": "FAILED", "error": message},
        )
        return {"status": run.status, "run_id": run.pk, "provider_attempts": 0}
    return result.as_dict()
