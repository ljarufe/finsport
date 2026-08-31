import logging

from .events import emit_event


class OperationalErrorHandler(logging.Handler):
    """Capture unhandled Django request errors without ingesting normal console logs."""

    def emit(self, record):
        if record.levelno < logging.ERROR:
            return
        exception = record.exc_info[1] if record.exc_info else None
        traceback_text = (
            self.formatException(record.exc_info) if record.exc_info else ""
        )
        emit_event(
            event_code="DJANGO_RUNTIME_FAILED",
            severity="ERROR",
            component="django",
            operation="request",
            outcome="FAILED",
            failure_kind="unexpected_exception",
            human_summary="An unhandled Django request error occurred.",
            exception=exception,
            traceback_text=traceback_text,
            context={"diagnostic_excerpt": record.getMessage()},
        )

    @staticmethod
    def formatException(exc_info):
        return logging.Formatter().formatException(exc_info)
