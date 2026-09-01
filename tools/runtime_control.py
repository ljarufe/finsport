#!/usr/bin/env python3
"""Host-side safe runtime status and graceful Compose shutdown."""

import argparse
import json
import os
import subprocess
import sys
import time

COMPOSE = (
    "docker",
    "compose",
    "--profile",
    "operational",
    "--profile",
    "observability",
)
QUEUE_NAME = "finsport.local.safe"
BROKER_DATABASE = "14"


class RuntimeCheckError(RuntimeError):
    pass


def _compose(*arguments, check=True, capture_output=True):
    return subprocess.run(
        (*COMPOSE, *arguments),
        check=check,
        capture_output=capture_output,
        text=True,
    )


def running_services():
    result = _compose("ps", "--status", "running", "--services")
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _parse_task_reply(output, operation):
    try:
        replies = json.loads(output)
    except json.JSONDecodeError as error:
        raise RuntimeCheckError(f"Celery {operation} returned invalid JSON.") from error
    if not isinstance(replies, dict) or not replies:
        raise RuntimeCheckError(f"Celery {operation} received no worker reply.")
    if any(not isinstance(tasks, list) for tasks in replies.values()):
        raise RuntimeCheckError(f"Celery {operation} returned an invalid task list.")
    return sum(len(tasks) for tasks in replies.values())


def celery_counts(services):
    if "celery" not in services:
        return {name: 0 for name in ("active", "reserved", "scheduled")}
    counts = {}
    for operation in ("active", "reserved", "scheduled"):
        result = _compose(
            "exec",
            "-T",
            "celery",
            "celery",
            "-A",
            "finsport",
            "inspect",
            operation,
            "--json",
            "--timeout=2",
            check=False,
        )
        if result.returncode:
            raise RuntimeCheckError(
                f"Celery {operation} inspection failed: {result.stderr.strip()}"
            )
        counts[operation] = _parse_task_reply(result.stdout, operation)
    return counts


def queue_depth(services):
    if "redis" not in services:
        if "celery" in services or "celery-beat" in services:
            raise RuntimeCheckError("Redis is unavailable while Celery is running.")
        return 0
    result = _compose(
        "exec", "-T", "redis", "redis-cli", "-n", BROKER_DATABASE, "LLEN", QUEUE_NAME
    )
    try:
        return int(result.stdout.strip())
    except ValueError as error:
        raise RuntimeCheckError("Redis queue depth was not an integer.") from error


def database_running_counts(services):
    if "db" not in services:
        if {"django-web", "celery", "celery-beat"} & services:
            raise RuntimeCheckError("PostgreSQL is unavailable while app services run.")
        return {"pipeline_runs": 0, "capture_runs": 0, "maintenance_runs": 0}
    code = (
        "import json, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', "
        "'finsport.settings'); import django; django.setup(); "
        "from django.db import connection; "
        "from football.models import CaptureRun, MaintenanceRun, PipelineRun; "
        "tables=set(connection.introspection.table_names()); "
        "models={'pipeline_runs': PipelineRun, 'capture_runs': CaptureRun, "
        "'maintenance_runs': MaintenanceRun}; "
        "print(json.dumps({key: (model.objects.filter(status='RUNNING').count() "
        "if model._meta.db_table in tables else None) "
        "for key, model in models.items()}))"
    )
    if "django-web" in services:
        arguments = ("exec", "-T", "django-web", "python", "-c", code)
    else:
        arguments = (
            "run",
            "--rm",
            "--no-deps",
            "django-web",
            "python",
            "-c",
            code,
        )
    result = _compose(*arguments)
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise RuntimeCheckError(
            "Django run-state check returned invalid JSON."
        ) from error


def automation_state(services):
    if "django-web" not in services:
        return {
            "pipeline_enabled": None,
            "capture_enabled": None,
            "registered_schedules": [],
            "scheduled_dispatch_possible": False,
        }
    code = (
        "import json, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', "
        "'finsport.settings'); import django; django.setup(); "
        "from django.conf import settings; "
        "print(json.dumps({'pipeline_enabled': settings.FOOTBALL_PIPELINE_ENABLED, "
        "'capture_enabled': settings.FOOTBALL_CAPTURE_ENABLED, "
        "'registered_schedules': sorted(settings.CELERY_BEAT_SCHEDULE)}))"
    )
    result = _compose("exec", "-T", "django-web", "python", "-c", code)
    try:
        state = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise RuntimeCheckError(
            "Django automation check returned invalid JSON."
        ) from error
    state["scheduled_dispatch_possible"] = bool(
        state["registered_schedules"] and "celery-beat" in services
    )
    return state


def maintenance_state(services):
    if "django-web" not in services:
        return None
    code = (
        "import json, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', "
        "'finsport.settings'); import django; django.setup(); "
        "from football.maintenance import maintenance_status; "
        "print(json.dumps(maintenance_status()))"
    )
    result = _compose("exec", "-T", "django-web", "python", "-c", code)
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise RuntimeCheckError(
            "Django maintenance-state check returned invalid JSON."
        ) from error


def quiescence_snapshot():
    services = running_services()
    return {
        "services": sorted(services),
        "celery": celery_counts(services),
        "queue_depth": queue_depth(services),
        "database": database_running_counts(services),
    }


def is_quiescent(snapshot):
    if {"celery-beat", "observability-watch"} & set(snapshot.get("services", [])):
        return False
    return not any(
        [
            *snapshot["celery"].values(),
            snapshot["queue_depth"],
            *snapshot["database"].values(),
        ]
    )


def status():
    _compose("ps", capture_output=False)
    services = running_services()
    report = {"automation": automation_state(services)}
    try:
        report["maintenance"] = maintenance_state(services)
    except (RuntimeCheckError, subprocess.CalledProcessError) as error:
        report["maintenance_error"] = str(error)
    try:
        report["quiescence"] = quiescence_snapshot()
    except (RuntimeCheckError, subprocess.CalledProcessError) as error:
        report["quiescence_error"] = str(error)
    print(json.dumps(report, indent=2, sort_keys=True))


def safe_down(timeout_seconds):
    _compose("stop", "celery-beat", check=False)
    _compose("stop", "observability-watch", check=False)
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() <= deadline:
        try:
            snapshot = quiescence_snapshot()
            print(json.dumps(snapshot, sort_keys=True))
            if is_quiescent(snapshot):
                _compose("down", capture_output=False)
                remaining = running_services()
                if remaining:
                    raise RuntimeCheckError(
                        "Compose down left Finsport services running: "
                        + ", ".join(sorted(remaining))
                    )
                return
            last_error = "runtime is not quiescent"
        except RuntimeCheckError as error:
            last_error = str(error)
            print(f"safe-down check failed: {error}", file=sys.stderr)
        time.sleep(2)
    raise RuntimeCheckError(
        f"safe-down timed out after {timeout_seconds}s; stack left running with "
        f"dispatchers stopped ({last_error})."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("status", "safe-down"))
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("FINSPORT_SAFE_DOWN_TIMEOUT_SECONDS", "120")),
    )
    arguments = parser.parse_args()
    if arguments.timeout < 1:
        parser.error("--timeout must be positive")
    try:
        if arguments.operation == "status":
            status()
        else:
            safe_down(arguments.timeout)
    except (RuntimeCheckError, subprocess.CalledProcessError) as error:
        print(f"runtime control failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
