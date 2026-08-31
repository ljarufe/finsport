import traceback

from football.models import PipelineRun

from .events import emit_event


def exception_diagnostic(error):
    context = dict(getattr(error, "diagnostic_context", {}) or {})
    return {
        "exception": error,
        "failure_kind": getattr(error, "failure_kind", "unexpected_exception"),
        "provider": getattr(error, "provider", ""),
        "context": context,
        "traceback_text": "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        ),
    }


def emit_pipeline_terminal(run, *, causes=()):
    mapping = {
        PipelineRun.Status.SUCCESS: (
            "PIPELINE_SUCCEEDED",
            "INFO",
            "Pipeline completed successfully.",
        ),
        PipelineRun.Status.DEGRADED: (
            "PIPELINE_DEGRADED",
            "WARNING",
            "Pipeline completed with an incomplete result.",
        ),
        PipelineRun.Status.FAILED: (
            "PIPELINE_FAILED",
            "ERROR",
            "Pipeline could not fulfill its contract.",
        ),
    }
    if run.status not in mapping:
        return None
    event_code, severity, summary = mapping[run.status]
    first = causes[0] if causes else {}
    context = {
        "capture_run_ids": run.capture_run_ids,
        "pending_count": max(0, len(causes) - 1),
    }
    context.update(first.get("context", {}))
    return emit_event(
        event_code=event_code,
        severity=severity,
        component=first.get("component", "pipeline"),
        operation=first.get("operation", "run_pipeline"),
        outcome=run.status,
        failure_kind=first.get("failure_kind", ""),
        human_summary=summary,
        pipeline_run_id=run.pk,
        capture_run_id=(run.capture_run_ids or [None])[0],
        prediction_experiment_id=(run.prediction_experiment_ids or [None])[0],
        capital_experiment_id=(run.capital_experiment_ids or [None])[0],
        provider=first.get("provider", ""),
        provider_request_id=first.get("context", {}).get("provider_request_id"),
        exception=first.get("exception"),
        traceback_text=first.get("traceback_text", ""),
        context=context,
    )
