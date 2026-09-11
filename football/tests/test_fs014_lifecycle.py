import json
import stat
import subprocess
from pathlib import Path

import pytest
from django.test import Client

from tools import finsport_backup, fs014_lifecycle

ROOT = Path(__file__).resolve().parents[2]


def completed(stdout=b"", *, returncode=0, stderr=b""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def operational_inspection():
    return {
        "Config": {
            "Image": "postgres:17",
            "Labels": {
                "com.docker.compose.project": "finsport",
                "com.docker.compose.service": "db",
            },
        },
        "State": {"Running": True},
        "Mounts": [
            {
                "Type": "volume",
                "Name": "finsport_postgres_data",
                "Destination": "/var/lib/postgresql/data",
            }
        ],
    }


def backup_runner(*, fail_validation=False):
    def fake_run(command, **kwargs):
        if command[:3] == ["docker", "ps", "-aq"]:
            return completed(b"operational-db\n")
        if command[:2] == ["docker", "inspect"]:
            return completed(json.dumps([operational_inspection()]).encode())
        if "psql" in command:
            return completed(b"finsport:finsport\n")
        if "pg_dump" in command:
            kwargs["stdout"].write(b"postgres-custom-archive")
            return completed()
        if "pg_restore" in command:
            if fail_validation:
                return completed(returncode=1, stderr=b"invalid archive")
            return completed()
        raise AssertionError(command)

    return fake_run


def test_backup_replaces_atomically_with_private_modes(tmp_path):
    destination = finsport_backup.refresh_backup(
        tmp_path / "backups", runner=backup_runner()
    )

    assert destination.read_bytes() == b"postgres-custom-archive"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert stat.S_IMODE(destination.parent.stat().st_mode) == 0o700
    assert list(destination.parent.iterdir()) == [destination]


def test_backup_validation_failure_preserves_previous_good_file(tmp_path):
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir()
    previous = backup_directory / "latest.dump"
    previous.write_bytes(b"known-good")

    with pytest.raises(finsport_backup.BackupError, match="pg_restore"):
        finsport_backup.refresh_backup(
            backup_directory, runner=backup_runner(fail_validation=True)
        )

    assert previous.read_bytes() == b"known-good"
    assert list(backup_directory.iterdir()) == [previous]


def test_compose_boundaries_are_frozen_and_dev_has_no_beat():
    operational = (ROOT / "compose.yml").read_text()
    development = (ROOT / "compose.dev.yml").read_text()

    assert "name: finsport\n" in operational
    assert "build:" not in operational
    assert ".:/app" not in operational
    assert "./config/" not in operational
    assert "./nginx.conf" not in operational
    assert "finsport-app:operational" in operational
    assert "external: true" in operational

    assert "name: finsport-dev\n" in development
    assert "celery-beat" not in development
    assert '"15432:5432"' in development
    assert '"16379:6379"' in development
    assert '"18000:8000"' in development
    assert '"18001:80"' in development
    assert ".:/app" in development
    assert "finsport_postgres_data" not in development
    assert 'FOOTBALL_CAPTURE_ENABLED: "False"' in development
    assert 'FOOTBALL_PIPELINE_ENABLED: "False"' in development
    assert "DATABASE_HOST: db" in development
    assert fs014_lifecycle.DEV_COMPOSE[3:6] == ("finsport-dev", "-f", "compose.dev.yml")
    assert fs014_lifecycle.OPERATIONAL_COMPOSE[3:6] == (
        "finsport",
        "-f",
        "compose.yml",
    )
    assert operational.count("http://127.0.0.1:8000/healthz/") == 1
    assert development.count("http://127.0.0.1:8000/healthz/") == 1
    assert "urlopen('http://127.0.0.1:8000/'," not in operational
    assert "urlopen('http://127.0.0.1:8000/'," not in development


def test_healthz_is_constant_and_does_not_require_database_access():
    response = Client().get("/healthz/")

    assert response.status_code == 200
    assert response.content == b"ok\n"
    assert response["Content-Type"] == "text/plain"


def test_dev_create_analyzes_after_migrations_and_before_app_start(monkeypatch):
    events = []

    monkeypatch.setattr(fs014_lifecycle, "assert_dev_absent", lambda: None)
    monkeypatch.setattr(
        fs014_lifecycle, "_assert_dev_compose_has_no_beat", lambda: None
    )
    monkeypatch.setattr(
        fs014_lifecycle,
        "_assert_database_mount",
        lambda project, volume: "dev-db",
    )
    monkeypatch.setattr(
        fs014_lifecycle,
        "_clone_operational_database",
        lambda container: events.append("restore"),
    )
    monkeypatch.setattr(
        fs014_lifecycle,
        "_analyze_dev_database",
        lambda: events.append("analyze"),
    )
    monkeypatch.setattr(fs014_lifecycle, "assert_dev_created", lambda **kwargs: None)
    monkeypatch.setattr(
        fs014_lifecycle, "_assert_dev_automation_disabled", lambda: None
    )

    def fake_compose(base, *arguments, **kwargs):
        if arguments[0] == "run" and "migrate" in arguments:
            events.append("migrate")
        if arguments[0] == "up" and "django-web" in arguments:
            events.append("app-start")

    monkeypatch.setattr(fs014_lifecycle, "compose", fake_compose)

    fs014_lifecycle.dev_create()

    assert events == ["restore", "migrate", "analyze", "app-start"]


def test_analyze_reverifies_and_targets_only_dev_database(monkeypatch):
    checks = []
    commands = []

    def fake_mount(project, volume):
        checks.append((project, volume))
        return "verified-dev-db"

    monkeypatch.setattr(fs014_lifecycle, "_assert_database_mount", fake_mount)
    monkeypatch.setattr(
        fs014_lifecycle,
        "_assert_database_identity",
        lambda container, project: checks.append((container, project)),
    )
    monkeypatch.setattr(
        fs014_lifecycle,
        "run",
        lambda command, **kwargs: commands.append(command),
    )

    fs014_lifecycle._analyze_dev_database()

    assert checks == [
        ("finsport-dev", "finsport-dev_postgres_data"),
        ("verified-dev-db", "finsport-dev"),
    ]
    assert commands == [
        [
            "docker",
            "exec",
            "verified-dev-db",
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "finsport",
            "-d",
            "finsport",
            "-c",
            "ANALYZE",
        ]
    ]


def test_dev_create_refuses_stale_resources(monkeypatch):
    monkeypatch.setattr(
        fs014_lifecycle,
        "dev_resources",
        lambda: {"containers": {"stale"}, "networks": set(), "volumes": set()},
    )

    with pytest.raises(fs014_lifecycle.LifecycleError, match="Unexpected"):
        fs014_lifecycle.assert_dev_absent()


def test_dev_destroy_refuses_container_with_operational_volume(monkeypatch):
    monkeypatch.setattr(
        fs014_lifecycle,
        "dev_resources",
        lambda: {"containers": {"bad"}, "networks": {"dev"}, "volumes": set()},
    )
    monkeypatch.setattr(
        fs014_lifecycle,
        "_inspect",
        lambda unused: {
            "Config": {"Labels": {"com.docker.compose.project": "finsport-dev"}},
            "Mounts": [{"Name": "finsport_postgres_data"}],
        },
    )

    with pytest.raises(fs014_lifecycle.LifecycleError, match="protected"):
        fs014_lifecycle.dev_destroy()


def test_deploy_refuses_non_master_branch(monkeypatch):
    monkeypatch.setattr(
        fs014_lifecycle,
        "run",
        lambda unused: subprocess.CompletedProcess([], 0, "FS-014-ticket\n", ""),
    )

    with pytest.raises(fs014_lifecycle.LifecycleError, match="requires branch master"):
        fs014_lifecycle._git_deploy_preconditions()


def test_ci_workflow_uses_only_the_repository_ci_contract():
    workflow = (ROOT / ".github/workflows/pr-validation.yml").read_text()
    makefile = (ROOT / "Makefile").read_text()
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "run: make ci-check" in workflow
    assert "run: make ci-clean" in workflow
    assert "run: make check\n" not in workflow
    assert "make dev-create" not in workflow
    assert "docker compose" not in workflow
    assert "make up" not in workflow
    assert "finsport-ci-${{ github.run_id }}-${{ github.run_attempt }}" in workflow
    assert "APP = python3 tools/fs014_lifecycle.py dev-assert-ready" in makefile
    assert "check: format-check lint django-check" in makefile
    assert "FROM application AS ci-check" in dockerfile
    assert "apt-get install -y --no-install-recommends make" in dockerfile


def test_ci_compose_is_disposable_portless_and_provider_safe():
    ci_compose = (ROOT / "compose.ci.yml").read_text()

    assert "name: finsport-ci-default" in ci_compose
    assert "image: postgres:17" in ci_compose
    assert "image: redis:7" in ci_compose
    assert "ports:" not in ci_compose
    assert "volumes:" not in ci_compose
    assert ci_compose.count("tmpfs:") == 2
    assert "finsport_postgres_data" not in ci_compose
    assert "external:" not in ci_compose
    assert "celery-beat" not in ci_compose
    assert "  celery:" not in ci_compose
    assert "  nginx:" not in ci_compose
    assert "  grafana:" not in ci_compose
    assert "  loki:" not in ci_compose
    assert "  alloy:" not in ci_compose
    assert "  observability-watch:" not in ci_compose
    assert 'FOOTBALL_CAPTURE_ENABLED: "False"' in ci_compose
    assert 'FOOTBALL_PIPELINE_ENABLED: "False"' in ci_compose
    assert 'INKABET_AUTOMATIC_ENABLED: "False"' in ci_compose
    assert "image: finsport-ci-app:check" in ci_compose
    assert "target: ci-check" in ci_compose
    assert "command: make check" in ci_compose


@pytest.mark.parametrize(
    "project",
    (
        "finsport",
        "finsport-dev",
        "other-project",
        "finsport-ci-UPPER",
        "finsport-ci-bad.name",
    ),
)
def test_ci_project_validation_rejects_unsafe_names(project):
    with pytest.raises(fs014_lifecycle.LifecycleError):
        fs014_lifecycle.ci_project_name(project)


def test_ci_project_identities_are_independent_and_use_one_compose_file():
    first = fs014_lifecycle.ci_compose("finsport-ci-run-1")
    second = fs014_lifecycle.ci_compose("finsport-ci-run-2")

    assert first != second
    assert first[2:6] == ("-p", "finsport-ci-run-1", "-f", "compose.ci.yml")
    assert second[2:6] == ("-p", "finsport-ci-run-2", "-f", "compose.ci.yml")


def test_ci_cleanup_is_scoped_to_selected_project(monkeypatch):
    calls = []
    monkeypatch.setattr(
        fs014_lifecycle,
        "compose",
        lambda base, *arguments, **kwargs: calls.append((base, arguments)),
    )
    monkeypatch.setattr(
        fs014_lifecycle,
        "ci_resources",
        lambda project: {"containers": set(), "networks": set(), "volumes": set()},
    )

    fs014_lifecycle.ci_cleanup("finsport-ci-selected")

    assert calls == [
        (
            (
                "docker",
                "compose",
                "-p",
                "finsport-ci-selected",
                "-f",
                "compose.ci.yml",
            ),
            ("down", "--volumes", "--remove-orphans"),
        )
    ]


def test_ci_check_runs_existing_gate_and_cleans_after_failure(monkeypatch):
    events = []
    monkeypatch.setattr(
        fs014_lifecycle,
        "assert_ci_absent",
        lambda project: events.append(("absent", project)),
    )
    monkeypatch.setattr(
        fs014_lifecycle,
        "ci_cleanup",
        lambda project: events.append(("cleanup", project)),
    )

    def fake_compose(base, *arguments, **kwargs):
        events.append(("compose", base, arguments, kwargs.get("check", True)))
        return subprocess.CompletedProcess(
            [], 17 if arguments[0] == "run" else 0, "", ""
        )

    monkeypatch.setattr(fs014_lifecycle, "compose", fake_compose)

    result = fs014_lifecycle.ci_check("finsport-ci-failure")

    assert result == 17
    assert ("cleanup", "finsport-ci-failure") in events
    validation = next(
        event for event in events if event[0] == "compose" and event[2][0] == "run"
    )
    assert validation[2][-3:] == ("django-web", "make", "check")
    assert validation[3] is False


def test_ci_check_reports_cleanup_failure_without_hiding_check_status(
    monkeypatch, capsys
):
    monkeypatch.setattr(fs014_lifecycle, "assert_ci_absent", lambda project: None)
    monkeypatch.setattr(
        fs014_lifecycle,
        "compose",
        lambda base, *arguments, **kwargs: subprocess.CompletedProcess(
            [], 9 if arguments[0] == "run" else 0, "", ""
        ),
    )
    monkeypatch.setattr(
        fs014_lifecycle,
        "ci_cleanup",
        lambda project: (_ for _ in ()).throw(
            fs014_lifecycle.LifecycleError("residue remains")
        ),
    )

    result = fs014_lifecycle.ci_check("finsport-ci-double-failure")

    assert result == 9
    error = capsys.readouterr().err
    assert "exit 9" in error
    assert "residue remains" in error


def test_ci_check_fails_when_cleanup_fails_after_success(monkeypatch):
    monkeypatch.setattr(fs014_lifecycle, "assert_ci_absent", lambda project: None)
    monkeypatch.setattr(
        fs014_lifecycle,
        "compose",
        lambda base, *arguments, **kwargs: subprocess.CompletedProcess([], 0, "", ""),
    )
    monkeypatch.setattr(
        fs014_lifecycle,
        "ci_cleanup",
        lambda project: (_ for _ in ()).throw(
            fs014_lifecycle.LifecycleError("residue remains")
        ),
    )

    with pytest.raises(fs014_lifecycle.LifecycleError, match="passed, but"):
        fs014_lifecycle.ci_check("finsport-ci-cleanup-failure")


def test_ci_check_refuses_stale_exact_project_without_cleanup(monkeypatch):
    monkeypatch.setattr(
        fs014_lifecycle,
        "ci_resources",
        lambda project: {"containers": {"stale"}, "networks": set(), "volumes": set()},
    )
    cleanup_calls = []
    monkeypatch.setattr(
        fs014_lifecycle,
        "ci_cleanup",
        lambda project: cleanup_calls.append(project),
    )

    with pytest.raises(fs014_lifecycle.LifecycleError, match="Unexpected resources"):
        fs014_lifecycle.ci_check("finsport-ci-stale")

    assert cleanup_calls == []
