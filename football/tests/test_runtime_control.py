import json
import subprocess

import pytest

from tools import runtime_control


def completed(stdout="", *, returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_celery_reply_parser_counts_all_workers_and_fails_closed():
    assert (
        runtime_control._parse_task_reply(
            json.dumps({"celery@one": [{"id": "1"}], "celery@two": []}),
            "active",
        )
        == 1
    )
    with pytest.raises(runtime_control.RuntimeCheckError, match="no worker reply"):
        runtime_control._parse_task_reply("{}", "active")
    with pytest.raises(runtime_control.RuntimeCheckError, match="invalid JSON"):
        runtime_control._parse_task_reply("not-json", "active")


def test_quiescence_requires_empty_worker_queue_and_database_counts():
    snapshot = {
        "celery": {"active": 0, "reserved": 0, "scheduled": 0},
        "queue_depth": 0,
        "database": {"pipeline_runs": 0, "capture_runs": 0, "maintenance_runs": 0},
    }
    assert runtime_control.is_quiescent(snapshot)
    snapshot["database"]["capture_runs"] = 1
    assert not runtime_control.is_quiescent(snapshot)
    snapshot["database"]["capture_runs"] = 0
    snapshot["database"]["maintenance_runs"] = None
    assert runtime_control.is_quiescent(snapshot)
    snapshot["services"] = ["celery-beat"]
    assert not runtime_control.is_quiescent(snapshot)


def test_compose_inspection_always_enables_all_profiles(monkeypatch):
    commands = []

    def fake_run(command, **kwargs):
        commands.append((command, kwargs))
        return completed("grafana\ncelery-beat\nobservability-watch\n")

    monkeypatch.setattr(runtime_control.subprocess, "run", fake_run)

    services = runtime_control.running_services()

    assert services == {"grafana", "celery-beat", "observability-watch"}
    assert commands[0][0][:8] == (
        "docker",
        "compose",
        "--profile",
        "operational",
        "--profile",
        "observability",
        "ps",
        "--status",
    )


def test_safe_down_stops_dispatchers_then_uses_volume_preserving_down(monkeypatch):
    calls = []

    def fake_compose(*arguments, **kwargs):
        calls.append(arguments)
        return completed()

    monkeypatch.setattr(runtime_control, "_compose", fake_compose)
    monkeypatch.setattr(
        runtime_control,
        "quiescence_snapshot",
        lambda: {
            "services": [],
            "celery": {"active": 0, "reserved": 0, "scheduled": 0},
            "queue_depth": 0,
            "database": {
                "pipeline_runs": 0,
                "capture_runs": 0,
                "maintenance_runs": 0,
            },
        },
    )

    runtime_control.safe_down(1)

    assert calls[0][-2:] == ("stop", "celery-beat")
    assert calls[1][-2:] == ("stop", "observability-watch")
    down_call = next(call for call in calls if call[-1] == "down")
    assert "-v" not in down_call
    assert calls[-1][-4:] == ("ps", "--status", "running", "--services")
