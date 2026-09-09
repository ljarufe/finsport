#!/usr/bin/env python3
"""Fail-closed host lifecycle for isolated development and local deployment."""

import argparse
import json
import stat
import subprocess
import sys
import time
from pathlib import Path

try:
    from tools import finsport_backup
except ModuleNotFoundError:  # Direct execution adds tools/, not the repository root.
    import finsport_backup

REPOSITORY = Path(__file__).resolve().parents[1]
OPERATIONAL_PROJECT = "finsport"
DEV_PROJECT = "finsport-dev"
OPERATIONAL_COMPOSE = (
    "docker",
    "compose",
    "-p",
    OPERATIONAL_PROJECT,
    "-f",
    "compose.yml",
)
DEV_COMPOSE = ("docker", "compose", "-p", DEV_PROJECT, "-f", "compose.dev.yml")
OPERATIONAL_VOLUME = "finsport_postgres_data"
DEV_VOLUMES = {
    "finsport-dev_postgres_data",
    "finsport-dev_redis_data",
    "finsport-dev_static_volume",
    "finsport-dev_logs_volume",
}
DEV_CONTAINERS = {
    "finsport-dev-db-1",
    "finsport-dev-redis-1",
    "finsport-dev-django-web-1",
    "finsport-dev-celery-1",
    "finsport-dev-nginx-1",
    "finsport-dev-init-logs-1",
}
DEV_NETWORKS = {"finsport-dev_default"}
PROTECTED_VOLUMES = {
    OPERATIONAL_VOLUME,
    "finsport_redis_data",
    "finsport_static_volume",
    "finsport_logs_volume",
    "finsport_loki_data",
    "finsport_alloy_data",
    "finsport_grafana_data",
}
OPERATIONAL_IMAGES = (
    "finsport-app:operational",
    "finsport-nginx:operational",
    "finsport-loki:operational",
    "finsport-alloy:operational",
    "finsport-grafana:operational",
)
OPERATIONAL_SERVICES = {
    "redis",
    "db",
    "django-web",
    "celery",
    "celery-beat",
    "nginx",
    "observability-watch",
    "loki",
    "alloy",
    "grafana",
}
VERIFY_CONTAINER = "finsport-backup-verify-db"
VERIFY_LABEL = "com.finsport.purpose=backup-restore-drill"


class LifecycleError(RuntimeError):
    """A lifecycle safety invariant failed."""


def run(command, *, check=True, capture_output=True, **kwargs):
    result = subprocess.run(
        command,
        cwd=REPOSITORY,
        check=False,
        capture_output=capture_output,
        text=True,
        **kwargs,
    )
    if check and result.returncode:
        detail = result.stderr.strip() if result.stderr else "no diagnostic output"
        raise LifecycleError(f"Command failed: {' '.join(command)}: {detail}")
    return result


def compose(base, *arguments, **kwargs):
    return run([*base, *arguments], **kwargs)


def _ids_for_label(resource, label):
    if resource == "container":
        command = ["docker", "ps", "-aq", "--filter", f"label={label}"]
    else:
        command = ["docker", resource, "ls", "-q", "--filter", f"label={label}"]
    return set(run(command).stdout.split())


def _existing_named(resource, names):
    existing = set()
    for name in names:
        result = run(["docker", resource, "inspect", name], check=False)
        if result.returncode == 0:
            existing.add(name)
    return existing


def dev_resources():
    project_label = f"com.docker.compose.project={DEV_PROJECT}"
    return {
        "containers": _ids_for_label("container", project_label)
        | _existing_named("container", DEV_CONTAINERS),
        "networks": _ids_for_label("network", project_label)
        | _existing_named("network", DEV_NETWORKS),
        "volumes": _ids_for_label("volume", project_label)
        | _existing_named("volume", DEV_VOLUMES),
    }


def assert_dev_absent():
    resources = dev_resources()
    present = {kind: sorted(values) for kind, values in resources.items() if values}
    if present:
        raise LifecycleError(
            "Unexpected finsport-dev resources exist. Refusing to clean them at ticket "
            f"start; inspect them and use make dev-destroy deliberately: {present}"
        )


def _inspect(container_id):
    result = run(["docker", "inspect", container_id])
    try:
        return json.loads(result.stdout)[0]
    except (IndexError, json.JSONDecodeError) as error:
        raise LifecycleError(
            f"Invalid Docker inspection for {container_id}."
        ) from error


def _service_container(project, service):
    result = run(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--filter",
            f"label=com.docker.compose.service={service}",
        ]
    )
    container_ids = result.stdout.split()
    if len(container_ids) != 1:
        raise LifecycleError(
            f"Expected exactly one {project}/{service} container; "
            f"found {len(container_ids)}."
        )
    return container_ids[0]


def _assert_database_mount(project, expected_volume):
    container_id = _service_container(project, "db")
    inspection = _inspect(container_id)
    labels = inspection.get("Config", {}).get("Labels", {}) or {}
    if labels.get("com.docker.compose.project") != project:
        raise LifecycleError(f"Database container is not owned by {project}.")
    mounts = [
        mount
        for mount in inspection.get("Mounts", [])
        if mount.get("Destination") == "/var/lib/postgresql/data"
    ]
    if (
        len(mounts) != 1
        or mounts[0].get("Type") != "volume"
        or mounts[0].get("Name") != expected_volume
    ):
        raise LifecycleError(
            f"{project}/db does not use expected isolated volume {expected_volume}."
        )
    if mounts[0].get("Name") == OPERATIONAL_VOLUME and project == DEV_PROJECT:
        raise LifecycleError("Development DB is mounted on the operational volume.")
    return container_id


def _assert_dev_redis_mount():
    container_id = _service_container(DEV_PROJECT, "redis")
    inspection = _inspect(container_id)
    mounts = [
        mount
        for mount in inspection.get("Mounts", [])
        if mount.get("Destination") == "/data"
    ]
    if (
        len(mounts) != 1
        or mounts[0].get("Type") != "volume"
        or mounts[0].get("Name") != "finsport-dev_redis_data"
    ):
        raise LifecycleError(
            "finsport-dev/redis does not use its isolated Redis volume."
        )


def _assert_database_identity(container_id, project):
    inspection = _inspect(container_id)
    if not inspection.get("State", {}).get("Running"):
        raise LifecycleError(f"{project}/db is not running.")
    if inspection.get("Config", {}).get("Image") != "postgres:17":
        raise LifecycleError(f"{project}/db is not the frozen postgres:17 image.")
    result = run(
        [
            "docker",
            "exec",
            container_id,
            "psql",
            "-XAt",
            "-U",
            "finsport",
            "-d",
            "finsport",
            "-c",
            "select current_database() || ':' || current_user",
        ]
    )
    if result.stdout.strip() != "finsport:finsport":
        raise LifecycleError(f"Unexpected {project} PostgreSQL identity.")


def _assert_dev_compose_has_no_beat():
    services = set(compose(DEV_COMPOSE, "config", "--services").stdout.split())
    if "celery-beat" in services:
        raise LifecycleError("Development Compose unexpectedly defines Celery Beat.")


def _assert_dev_automation_disabled():
    code = (
        "import json, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', "
        "'finsport.settings'); import django; django.setup(); "
        "from django.conf import settings; "
        "print(json.dumps({'capture': settings.FOOTBALL_CAPTURE_ENABLED, "
        "'pipeline': settings.FOOTBALL_PIPELINE_ENABLED, "
        "'inkabet': settings.INKABET_AUTOMATIC_ENABLED}))"
    )
    result = compose(DEV_COMPOSE, "exec", "-T", "django-web", "python", "-c", code)
    try:
        state = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise LifecycleError(
            "Development automation check returned invalid JSON."
        ) from error
    if state != {"capture": False, "pipeline": False, "inkabet": False}:
        raise LifecycleError(f"Development provider automation is enabled: {state}")


def assert_dev_created(*, require_running=False, require_schema=True):
    _assert_dev_compose_has_no_beat()
    resources = dev_resources()
    if not resources["networks"]:
        raise LifecycleError(
            "finsport-dev network is absent; run make dev-create first."
        )
    dev_db = _assert_database_mount(DEV_PROJECT, "finsport-dev_postgres_data")
    _assert_dev_redis_mount()
    if require_running:
        for service in ("db", "redis", "django-web", "celery", "nginx"):
            inspection = _inspect(_service_container(DEV_PROJECT, service))
            if not inspection.get("State", {}).get("Running"):
                raise LifecycleError(f"Development service {service} is not running.")
    if require_schema:
        _assert_database_identity(dev_db, DEV_PROJECT)
        result = run(
            [
                "docker",
                "exec",
                dev_db,
                "psql",
                "-XAt",
                "-U",
                "finsport",
                "-d",
                "finsport",
                "-c",
                "select to_regclass('public.django_migrations') is not null",
            ]
        )
        if result.stdout.strip() != "t":
            raise LifecycleError("Development DB clone/schema marker is absent.")


def _clone_operational_database(dev_db):
    operational_db = _assert_database_mount(OPERATIONAL_PROJECT, OPERATIONAL_VOLUME)
    _assert_database_identity(operational_db, OPERATIONAL_PROJECT)
    _assert_database_identity(dev_db, DEV_PROJECT)
    source = subprocess.Popen(
        [
            "docker",
            "exec",
            operational_db,
            "pg_dump",
            "-U",
            "finsport",
            "-d",
            "finsport",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
        ],
        cwd=REPOSITORY,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    restore = subprocess.Popen(
        [
            "docker",
            "exec",
            "-i",
            dev_db,
            "pg_restore",
            "-U",
            "finsport",
            "-d",
            "finsport",
            "--no-owner",
            "--no-privileges",
            "--clean",
            "--if-exists",
            "--exit-on-error",
        ],
        cwd=REPOSITORY,
        stdin=source.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if source.stdout:
        source.stdout.close()
    _, restore_stderr = restore.communicate()
    source_stderr = source.stderr.read() if source.stderr else b""
    source_returncode = source.wait()
    if source_returncode or restore.returncode:
        raise LifecycleError(
            "Operational-to-development clone failed; operational DB was read only. "
            f"pg_dump={source_stderr.decode(errors='replace').strip()!r}, "
            f"pg_restore={restore_stderr.decode(errors='replace').strip()!r}"
        )


def _analyze_dev_database():
    dev_db = _assert_database_mount(DEV_PROJECT, "finsport-dev_postgres_data")
    _assert_database_identity(dev_db, DEV_PROJECT)
    run(
        [
            "docker",
            "exec",
            dev_db,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "finsport",
            "-d",
            "finsport",
            "-c",
            "ANALYZE",
        ],
        capture_output=False,
    )


def dev_create():
    assert_dev_absent()
    _assert_dev_compose_has_no_beat()
    compose(DEV_COMPOSE, "up", "-d", "--wait", "db", "redis", capture_output=False)
    dev_db = _assert_database_mount(DEV_PROJECT, "finsport-dev_postgres_data")
    _clone_operational_database(dev_db)
    compose(DEV_COMPOSE, "build", "django-web", capture_output=False)
    compose(
        DEV_COMPOSE,
        "run",
        "--rm",
        "--no-deps",
        "django-web",
        "python",
        "manage.py",
        "migrate",
        "--noinput",
        capture_output=False,
    )
    _analyze_dev_database()
    compose(
        DEV_COMPOSE,
        "up",
        "-d",
        "--wait",
        "django-web",
        "celery",
        "nginx",
        capture_output=False,
    )
    assert_dev_created(require_running=True)
    _assert_dev_automation_disabled()
    print("finsport-dev created from the operational DB; Beat is absent.")


def dev_up():
    assert_dev_created(require_schema=False)
    compose(
        DEV_COMPOSE,
        "up",
        "-d",
        "--wait",
        "db",
        "redis",
        "django-web",
        "celery",
        "nginx",
        capture_output=False,
    )
    assert_dev_created(require_running=True)
    _assert_dev_automation_disabled()
    print("Existing finsport-dev stack is running; operational finsport was untouched.")


def assert_dev_topology():
    assert_dev_created(require_schema=False)


def assert_dev_ready():
    assert_dev_created(require_schema=True)


def dev_destroy():
    resources = dev_resources()
    if not any(resources.values()):
        print("finsport-dev is already absent.")
        return
    for container_id in resources["containers"]:
        inspection = _inspect(container_id)
        labels = inspection.get("Config", {}).get("Labels", {}) or {}
        if labels.get("com.docker.compose.project") != DEV_PROJECT:
            raise LifecycleError(
                "Refusing destruction: container ownership is ambiguous."
            )
        mounted = {mount.get("Name") for mount in inspection.get("Mounts", [])}
        protected = mounted & PROTECTED_VOLUMES
        if protected:
            raise LifecycleError(
                f"Refusing destruction: finsport-dev container mounts protected {protected}."
            )
    for volume_id in resources["volumes"]:
        inspection = json.loads(run(["docker", "volume", "inspect", volume_id]).stdout)[
            0
        ]
        labels = inspection.get("Labels", {}) or {}
        if labels.get("com.docker.compose.project") != DEV_PROJECT:
            raise LifecycleError("Refusing destruction: volume ownership is ambiguous.")
        if inspection.get("Name") in PROTECTED_VOLUMES:
            raise LifecycleError("Refusing destruction of an operational volume.")
    for network_id in resources["networks"]:
        inspection = json.loads(
            run(["docker", "network", "inspect", network_id]).stdout
        )[0]
        labels = inspection.get("Labels", {}) or {}
        if labels.get("com.docker.compose.project") != DEV_PROJECT:
            raise LifecycleError(
                "Refusing destruction: network ownership is ambiguous."
            )
    compose(
        DEV_COMPOSE,
        "down",
        "--volumes",
        "--remove-orphans",
        capture_output=False,
    )
    remaining = dev_resources()
    if remaining["containers"]:
        raise LifecycleError(
            f"finsport-dev cleanup left containers behind: {remaining['containers']}"
        )
    for resource in ("volume", "network"):
        key = f"{resource}s"
        for resource_id in remaining[key]:
            inspection = json.loads(
                run(["docker", resource, "inspect", resource_id]).stdout
            )[0]
            labels = inspection.get("Labels", {}) or {}
            if labels.get("com.docker.compose.project") != DEV_PROJECT:
                raise LifecycleError(
                    f"Refusing cleanup of ambiguous residual {resource} {resource_id}."
                )
            if resource == "volume" and inspection.get("Name") in PROTECTED_VOLUMES:
                raise LifecycleError("Refusing destruction of an operational volume.")
            run(["docker", resource, "rm", resource_id], capture_output=False)
    final = dev_resources()
    if any(final.values()):
        raise LifecycleError(f"finsport-dev cleanup left resources behind: {final}")
    print("Removed only finsport-dev containers, network, and volumes.")


def operational_image_check():
    missing = [
        image
        for image in OPERATIONAL_IMAGES
        if run(["docker", "image", "inspect", image], check=False).returncode
    ]
    if missing:
        raise LifecycleError(
            "Operational images are missing; ordinary make up never builds branch source. "
            "Deploy synchronized master with make deploy-local. Missing: "
            + ", ".join(missing)
        )


def operational_running_check():
    result = compose(
        OPERATIONAL_COMPOSE,
        "--profile",
        "operational",
        "--profile",
        "observability",
        "ps",
        "--status",
        "running",
        "--services",
    )
    running = set(result.stdout.split())
    missing = OPERATIONAL_SERVICES - running
    if missing:
        raise LifecycleError(
            "Operational stack is missing running services: "
            + ", ".join(sorted(missing))
        )


def _git_deploy_preconditions():
    branch = run(["git", "branch", "--show-current"]).stdout.strip()
    if branch != "master":
        raise LifecycleError(
            f"deploy-local requires branch master; current branch is {branch or 'detached'}"
        )
    status = run(["git", "status", "--porcelain", "--untracked-files=normal"]).stdout
    if status.strip():
        raise LifecycleError("deploy-local requires a clean master worktree.")


def deploy_local():
    _git_deploy_preconditions()
    finsport_backup.refresh_backup()
    builds = (
        (["docker", "build", "-t", "finsport-app:operational", "."]),
        (
            [
                "docker",
                "build",
                "-f",
                "docker/operational/Dockerfile",
                "--target",
                "nginx",
                "-t",
                "finsport-nginx:operational",
                ".",
            ]
        ),
        (
            [
                "docker",
                "build",
                "-f",
                "docker/operational/Dockerfile",
                "--target",
                "loki",
                "-t",
                "finsport-loki:operational",
                ".",
            ]
        ),
        (
            [
                "docker",
                "build",
                "-f",
                "docker/operational/Dockerfile",
                "--target",
                "alloy",
                "-t",
                "finsport-alloy:operational",
                ".",
            ]
        ),
        (
            [
                "docker",
                "build",
                "-f",
                "docker/operational/Dockerfile",
                "--target",
                "grafana",
                "-t",
                "finsport-grafana:operational",
                ".",
            ]
        ),
    )
    for command in builds:
        run(command, capture_output=False)
    run([sys.executable, "tools/runtime_control.py", "safe-down"], capture_output=False)
    compose(
        OPERATIONAL_COMPOSE, "up", "-d", "--wait", "db", "redis", capture_output=False
    )
    compose(OPERATIONAL_COMPOSE, "run", "--rm", "init-logs", capture_output=False)
    compose(
        OPERATIONAL_COMPOSE,
        "run",
        "--rm",
        "--no-deps",
        "django-web",
        "python",
        "manage.py",
        "migrate",
        "--noinput",
        capture_output=False,
    )
    compose(
        OPERATIONAL_COMPOSE,
        "--profile",
        "operational",
        "--profile",
        "observability",
        "up",
        "-d",
        "--wait",
        capture_output=False,
    )
    operational_running_check()
    run([sys.executable, "tools/runtime_control.py", "status"], capture_output=False)
    print("Operational finsport deployed from clean local master.")


def backup_verify(backup_path=finsport_backup.DEFAULT_BACKUP_DIRECTORY / "latest.dump"):
    backup_path = Path(backup_path)
    if not backup_path.is_file():
        raise LifecycleError(f"Rolling backup is absent: {backup_path}")
    if stat.S_IMODE(backup_path.stat().st_mode) != 0o600:
        raise LifecycleError("Rolling backup must have mode 0600 before restore.")
    if (
        run(
            ["docker", "container", "inspect", VERIFY_CONTAINER], check=False
        ).returncode
        == 0
    ):
        raise LifecycleError(
            f"Scratch container {VERIFY_CONTAINER} already exists; refusing implicit cleanup."
        )
    cleanup_allowed = False
    try:
        cleanup_allowed = True
        run(
            [
                "docker",
                "run",
                "-d",
                "--pull=never",
                "--name",
                VERIFY_CONTAINER,
                "--label",
                VERIFY_LABEL,
                "--network",
                "none",
                "--tmpfs",
                "/var/lib/postgresql/data:rw,nosuid,nodev",
                "-e",
                "POSTGRES_DB=finsport_restore_verify",
                "-e",
                "POSTGRES_USER=finsport_restore_verify",
                "-e",
                "POSTGRES_PASSWORD=isolated-restore-only",
                "postgres:17",
            ]
        )
        for _ in range(30):
            ready = run(
                [
                    "docker",
                    "exec",
                    VERIFY_CONTAINER,
                    "pg_isready",
                    "-U",
                    "finsport_restore_verify",
                    "-d",
                    "finsport_restore_verify",
                ],
                check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise LifecycleError("Scratch PostgreSQL did not become ready.")
        with backup_path.open("rb") as archive:
            result = subprocess.run(
                ["docker", "exec", "-i", VERIFY_CONTAINER, "pg_restore", "--list"],
                cwd=REPOSITORY,
                stdin=archive,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
            )
        if result.returncode:
            raise LifecycleError("Rolling backup archive validation failed in scratch.")
        with backup_path.open("rb") as archive:
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    VERIFY_CONTAINER,
                    "pg_restore",
                    "-U",
                    "finsport_restore_verify",
                    "-d",
                    "finsport_restore_verify",
                    "--no-owner",
                    "--no-privileges",
                    "--exit-on-error",
                ],
                cwd=REPOSITORY,
                stdin=archive,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
            )
        if result.returncode:
            raise LifecycleError(
                "Isolated restore failed: "
                + result.stderr.decode(errors="replace").strip()
            )
        smoke = run(
            [
                "docker",
                "exec",
                VERIFY_CONTAINER,
                "psql",
                "-XAt",
                "-U",
                "finsport_restore_verify",
                "-d",
                "finsport_restore_verify",
                "-c",
                "select (to_regclass('public.django_migrations') is not null) "
                "and ((select count(*) from information_schema.tables "
                "where table_schema='public') > 0)",
            ]
        )
        if smoke.stdout.strip() != "t":
            raise LifecycleError(
                "Restored database failed the basic schema smoke check."
            )
        print(
            "Rolling backup restored and passed schema smoke in isolated tmpfs PostgreSQL."
        )
    finally:
        if cleanup_allowed:
            inspection = run(
                ["docker", "container", "inspect", VERIFY_CONTAINER], check=False
            )
            if inspection.returncode == 0:
                try:
                    labels = json.loads(inspection.stdout)[0]["Config"]["Labels"] or {}
                except (IndexError, KeyError, json.JSONDecodeError):
                    labels = {}
                if labels.get("com.finsport.purpose") != "backup-restore-drill":
                    raise LifecycleError(
                        "Scratch cleanup refused a container with unexpected ownership."
                    )
                run(["docker", "rm", "-f", VERIFY_CONTAINER])
                if (
                    run(
                        ["docker", "container", "inspect", VERIFY_CONTAINER],
                        check=False,
                    ).returncode
                    == 0
                ):
                    raise LifecycleError("Scratch restore container was not removed.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "operation",
        choices=(
            "dev-create",
            "dev-up",
            "dev-destroy",
            "dev-assert-created",
            "dev-assert-ready",
            "operational-image-check",
            "operational-running-check",
            "deploy-local",
            "backup-verify",
        ),
    )
    arguments = parser.parse_args()
    operations = {
        "dev-create": dev_create,
        "dev-up": dev_up,
        "dev-destroy": dev_destroy,
        "dev-assert-created": assert_dev_topology,
        "dev-assert-ready": assert_dev_ready,
        "operational-image-check": operational_image_check,
        "operational-running-check": operational_running_check,
        "deploy-local": deploy_local,
        "backup-verify": backup_verify,
    }
    try:
        operations[arguments.operation]()
    except (LifecycleError, finsport_backup.BackupError, OSError) as error:
        print(f"FS-014 lifecycle failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
