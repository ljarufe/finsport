from celery import shared_task
from django.conf import settings
from django.utils import timezone

from football.capture import run_capture
from football.models import CaptureRun, PipelineRun
from football.observability.events import emit_event, sanitize_text
from football.observability.pipeline import exception_diagnostic
from football.pipeline import run_pipeline


@shared_task(name="football.capture.wake")
def wake_capture_planner():
    """Wake the shared planner; all eligibility and quota logic stays in service."""
    if not settings.FOOTBALL_CAPTURE_ENABLED:
        return {"status": "DISABLED", "provider_attempts": 0}
    try:
        result = run_capture(trigger=CaptureRun.Trigger.SCHEDULER)
    except Exception as error:  # Persist failures that occur before executor audit.
        cause = exception_diagnostic(error)
        message = " ".join(sanitize_text(error, 500).split())
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
        emit_event(
            event_code="CAPTURE_TASK_FAILED",
            severity="ERROR",
            component="capture",
            operation="football.capture.wake",
            outcome="FAILED",
            failure_kind=cause["failure_kind"],
            human_summary="The scheduled capture task failed before normal audit.",
            capture_run_id=run.pk,
            provider=cause["provider"],
            exception=error,
            traceback_text=cause["traceback_text"],
            context=cause["context"],
        )
        return {"status": run.status, "run_id": run.pk, "provider_attempts": 0}
    if result.status in (CaptureRun.Status.PARTIAL, CaptureRun.Status.FAILED):
        cause = result.operational_cause
        emit_event(
            event_code=(
                "CAPTURE_DEGRADED"
                if result.status == CaptureRun.Status.PARTIAL
                else "CAPTURE_FAILED"
            ),
            severity=(
                "WARNING" if result.status == CaptureRun.Status.PARTIAL else "ERROR"
            ),
            component="capture",
            operation=cause.get("operation", "run_capture"),
            outcome=result.status,
            failure_kind=cause.get("failure_kind", "provider_request"),
            human_summary="Scheduled capture did not fully complete.",
            capture_run_id=result.run_id,
            provider=cause.get("provider", ""),
            exception=cause.get("exception"),
            traceback_text=cause.get("traceback_text", ""),
            context=cause.get("context", {}),
        )
    return result.as_dict()


@shared_task(name="football.pipeline.wake")
def wake_pipeline():
    """Wake the FS-006 orchestrator; the service owns all phase semantics."""
    if not settings.FOOTBALL_PIPELINE_ENABLED:
        return {"status": "DISABLED", "provider_attempts": 0}
    try:
        result = run_pipeline(trigger=PipelineRun.Trigger.SCHEDULER)
    except Exception as error:
        cause = exception_diagnostic(error)
        emit_event(
            event_code="PIPELINE_TASK_FAILED",
            severity="ERROR",
            component="pipeline",
            operation="football.pipeline.wake",
            outcome="FAILED",
            failure_kind=cause["failure_kind"],
            human_summary="The scheduled pipeline task failed outside normal audit.",
            provider=cause["provider"],
            exception=error,
            traceback_text=cause["traceback_text"],
            context=cause["context"],
        )
        raise
    return result.as_dict()
