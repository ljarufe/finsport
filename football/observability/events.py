import hashlib
import json
import os
import re
import socket
import sys
import traceback as traceback_module
import uuid
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

SCHEMA_VERSION = "finsport.observability.v1"
SUMMARY_LIMIT = 512
EXCEPTION_MESSAGE_LIMIT = 1024
TRACEBACK_LIMIT = 8192
DIAGNOSTIC_EXCERPT_LIMIT = 2048
CONTEXT_VALUE_LIMIT = 512
EVENT_SIZE_LIMIT = 16384
EVENT_FILE_SIZE_LIMIT = 1024 * 1024
EVENT_FILE_BACKUPS = 4

SEVERITIES = {"INFO", "WARNING", "ERROR"}
ID_FIELDS = {
    "pipeline_run_id",
    "capture_run_id",
    "prediction_experiment_id",
    "capital_experiment_id",
    "match_id",
    "competition_id",
    "provider_request_id",
    "task_id",
}
CONTEXT_ALLOWLIST = {
    "actual_category",
    "attempts",
    "capture_run_ids",
    "competition_pending",
    "content_type",
    "diagnostic_excerpt",
    "enabled",
    "endpoint_family",
    "expected_category",
    "grace_seconds",
    "http_status",
    "json_path",
    "last_scheduler_activity_at",
    "capability",
    "maintenance_run_id",
    "oldest_pending_age_seconds",
    "occurrence_count",
    "pending_count",
    "provider_error_category",
    "provider_error_keys",
    "provider_error_summary",
    "response_size",
    "scheduler_activity_status",
    "team_pending",
    "threshold_seconds",
    "top_level_keys",
    "transport_category",
    "match_pending",
}
SECRET_KEY_PATTERN = re.compile(
    r"(^|[\s_-])(authorization|cookie|api[\s_-]?key|apikey|token|"
    r"access[\s_-]?token|password|passwd|secret|database[\s_-]?url|dsn)"
    r"([\s_-]|$)",
    re.IGNORECASE,
)
INLINE_SECRET_PATTERN = re.compile(
    r"(?i)(authorization|cookie|api[\s_-]?key|apikey|token|"
    r"access[\s_-]?token|password|passwd|secret|database[\s_-]?url|dsn)"
    r"([\"']?\s*[=:]\s*)"
    r"(\"[^\"]*\"|'[^']*'|[^\s,;\]&]+)",
)
AUTHORIZATION_PATTERN = re.compile(
    r"(?i)(authorization\s*[=:]\s*)(?:bearer\s+)?[^\s,;]+"
)
COOKIE_PATTERN = re.compile(r"(?i)(cookie\s*[=:]\s*)[^\n]+")
URL_SECRET_PATTERN = re.compile(
    r"(?i)([?&](?:api[_-]?key|apikey|token|access[_-]?token|password|passwd|"
    r"secret)=)([^&#\s]+)"
)


def _known_secret_values():
    values = set()
    for key, value in os.environ.items():
        if SECRET_KEY_PATTERN.search(key) and len(value) >= 4:
            values.add(value)
    for name in (
        "SECRET_KEY",
        "API_FOOTBALL_KEY",
        "DATABASE_PASSWORD",
        "DATABASE_URL",
        "INKABET_BRAND_ID",
        "INKABET_MARKET_CODE",
    ):
        value = getattr(settings, name, "")
        if value and len(str(value)) >= 4:
            values.add(str(value))
    return sorted(values, key=len, reverse=True)


def sanitize_text(value, limit):
    text = str(value or "")
    text = AUTHORIZATION_PATTERN.sub(r"\1[REDACTED]", text)
    text = COOKIE_PATTERN.sub(r"\1[REDACTED]", text)
    text = INLINE_SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = URL_SECRET_PATTERN.sub(lambda match: f"{match.group(1)}[REDACTED]", text)
    for secret in _known_secret_values():
        text = text.replace(secret, "[REDACTED]")
    return text[:limit]


def safe_provider_error_diagnostic(value):
    """Reduce provider-reported errors to bounded, redacted scalar evidence."""

    category = {
        dict: "object",
        list: "array",
        tuple: "array",
        str: "string",
        bool: "boolean",
        int: "number",
        float: "number",
        type(None): "null",
    }.get(type(value), type(value).__name__)
    keys = []
    if isinstance(value, dict):
        keys = [
            sanitize_text(key, 120)
            for key in list(value)[:20]
            if not SECRET_KEY_PATTERN.search(str(key))
        ]

    parts = []

    def visit(node, path="", depth=0):
        if depth > 3 or len(parts) >= 8:
            return
        if isinstance(node, dict):
            for key, nested in list(node.items())[:20]:
                key = str(key)
                if SECRET_KEY_PATTERN.search(key):
                    continue
                nested_path = f"{path}.{key}" if path else key
                visit(nested, nested_path, depth + 1)
            return
        if isinstance(node, (list, tuple)):
            for index, nested in enumerate(node[:8]):
                visit(nested, f"{path}[{index}]", depth + 1)
            return
        if not isinstance(node, (str, bool, int, float)):
            return
        safe_value = " ".join(sanitize_text(node, 160).split())
        if safe_value:
            parts.append(f"{path}: {safe_value}" if path else safe_value)

    visit(value)
    return {
        "provider_error_category": category,
        "provider_error_keys": keys,
        "provider_error_summary": sanitize_text("; ".join(parts), 512),
    }


def _safe_context(context):
    safe = {}
    for key, value in (context or {}).items():
        key = str(key)
        if key not in CONTEXT_ALLOWLIST or SECRET_KEY_PATTERN.search(key):
            continue
        if isinstance(value, (list, tuple)):
            safe[key] = [
                sanitize_text(item, CONTEXT_VALUE_LIMIT) for item in value[:20]
            ]
        elif isinstance(value, (bool, int, float)) or value is None:
            safe[key] = value
        else:
            limit = (
                DIAGNOSTIC_EXCERPT_LIMIT
                if key == "diagnostic_excerpt"
                else CONTEXT_VALUE_LIMIT
            )
            safe[key] = sanitize_text(value, limit)
    return safe


def _fingerprint(event):
    dimensions = [
        event.get("event_code", ""),
        event.get("service_name", ""),
        event.get("component", ""),
        event.get("operation", ""),
        event.get("provider", ""),
        event.get("failure_kind", ""),
        event.get("exception_type", ""),
        event.get("context", {}).get("json_path", ""),
    ]
    canonical = "\x1f".join(str(value).casefold() for value in dimensions)
    return hashlib.sha256(canonical.encode()).hexdigest()[:24]


def _service_name(value=None):
    candidate = value or getattr(settings, "OBSERVABILITY_SERVICE_NAME", "django-web")
    return re.sub(r"[^a-zA-Z0-9_.-]", "-", str(candidate))[:80] or "unknown"


def _current_task_id():
    try:
        from celery import current_task

        return getattr(getattr(current_task, "request", None), "id", None)
    except (ImportError, RuntimeError):
        return None


def build_event(
    *,
    event_code,
    severity,
    component,
    operation,
    outcome,
    human_summary,
    service_name=None,
    failure_kind="",
    provider="",
    exception=None,
    traceback_text="",
    context=None,
    occurred_at=None,
    **identifiers,
):
    severity = str(severity).upper()
    if severity not in SEVERITIES:
        raise ValueError(f"Unsupported operational severity: {severity}")
    occurred_at = occurred_at or datetime.now(timezone.utc)
    event = {
        "schema": SCHEMA_VERSION,
        "timestamp": occurred_at.astimezone(timezone.utc).isoformat(),
        "event_id": str(uuid.uuid4()),
        "event_code": sanitize_text(event_code, 120),
        "severity": severity,
        "service_name": _service_name(service_name),
        "component": sanitize_text(component, 120),
        "operation": sanitize_text(operation, 120),
        "outcome": sanitize_text(outcome, 80),
        "human_summary": sanitize_text(human_summary, SUMMARY_LIMIT),
        "process_id": os.getpid(),
        "hostname": sanitize_text(socket.gethostname(), 120),
        "git_commit": sanitize_text(
            getattr(settings, "FINSPORT_GIT_COMMIT", "unknown"), 80
        ),
    }
    if failure_kind:
        event["failure_kind"] = sanitize_text(failure_kind, 120)
    if provider:
        event["provider"] = sanitize_text(provider, 120)
    identifiers.setdefault("task_id", _current_task_id())
    for key in ID_FIELDS:
        value = identifiers.get(key)
        if value not in (None, "", []):
            event[key] = sanitize_text(value, 200)
    if exception is not None:
        event["exception_type"] = exception.__class__.__name__[:120]
        event["exception_message"] = sanitize_text(exception, EXCEPTION_MESSAGE_LIMIT)
        if not traceback_text:
            traceback_text = "".join(
                traceback_module.format_exception(
                    type(exception), exception, exception.__traceback__
                )
            )
    if traceback_text:
        event["stacktrace"] = sanitize_text(traceback_text, TRACEBACK_LIMIT)
    safe_context = _safe_context(context)
    if safe_context:
        event["context"] = safe_context
    event["incident_fingerprint"] = _fingerprint(event)
    return _fit_event(event)


def _serialized(event):
    return json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fit_event(event):
    if len(_serialized(event).encode()) <= EVENT_SIZE_LIMIT:
        return event
    event = dict(event)
    event["context"] = {"diagnostic_excerpt": "event context truncated by size bound"}
    if "stacktrace" in event:
        event["stacktrace"] = event["stacktrace"][:4096]
    if "exception_message" in event:
        event["exception_message"] = event["exception_message"][:512]
    if len(_serialized(event).encode()) <= EVENT_SIZE_LIMIT:
        return event
    event.pop("stacktrace", None)
    event["stacktrace_truncated"] = True
    return event


def _rotate_and_append(path, payload):
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        current_size = path.stat().st_size if path.exists() else 0
        if current_size and current_size + len(payload) > EVENT_FILE_SIZE_LIMIT:
            oldest = path.with_name(f"{path.name}.{EVENT_FILE_BACKUPS}")
            oldest.unlink(missing_ok=True)
            for index in range(EVENT_FILE_BACKUPS - 1, 0, -1):
                source = path.with_name(f"{path.name}.{index}")
                if source.exists():
                    source.replace(path.with_name(f"{path.name}.{index + 1}"))
            path.replace(path.with_name(f"{path.name}.1"))
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
        try:
            os.write(descriptor, payload)
        finally:
            os.close(descriptor)


def emit_event(**kwargs):
    event = build_event(**kwargs)
    if not getattr(settings, "OBSERVABILITY_EVENTS_ENABLED", True):
        return event
    directory = Path(settings.OBSERVABILITY_EVENT_DIR)
    path = directory / f"{event['service_name']}.jsonl"
    payload = (_serialized(event) + "\n").encode("utf-8")
    try:
        _rotate_and_append(path, payload)
    except OSError as error:
        fallback = sanitize_text(error, 240)
        sys.stderr.write(f"Finsport operational event spool unavailable: {fallback}\n")
    return event


def event_from_exception(*, exception, traceback_text=None, **kwargs):
    return emit_event(
        exception=exception,
        traceback_text=traceback_text or "",
        **kwargs,
    )
