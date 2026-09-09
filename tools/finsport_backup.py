#!/usr/bin/env python3
"""Create and verify the single rolling operational PostgreSQL backup."""

import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = "finsport"
SERVICE = "db"
DATABASE = "finsport"
DATABASE_USER = "finsport"
POSTGRES_VOLUME = "finsport_postgres_data"
POSTGRES_DESTINATION = "/var/lib/postgresql/data"
DEFAULT_BACKUP_DIRECTORY = Path.home() / ".local/share/finsport/backups"


class BackupError(RuntimeError):
    """An operational identity or backup validation failed."""


def _run(command, *, runner=subprocess.run, **kwargs):
    result = runner(command, **kwargs)
    if result.returncode:
        stderr = getattr(result, "stderr", b"") or b""
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        raise BackupError(f"Command failed: {' '.join(command)}: {stderr.strip()}")
    return result


def _container_inspect(container_id, *, runner=subprocess.run):
    result = _run(
        ["docker", "inspect", container_id],
        runner=runner,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        inspection = json.loads(result.stdout)[0]
    except (IndexError, json.JSONDecodeError, TypeError) as error:
        raise BackupError("Operational DB container inspection was invalid.") from error
    return inspection


def find_operational_database(*, runner=subprocess.run):
    result = _run(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            f"label=com.docker.compose.project={PROJECT}",
            "--filter",
            f"label=com.docker.compose.service={SERVICE}",
        ],
        runner=runner,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    container_ids = result.stdout.decode().split()
    if len(container_ids) != 1:
        raise BackupError(
            "Expected exactly one finsport/db container; "
            f"found {len(container_ids)}. Backup was not replaced."
        )

    container_id = container_ids[0]
    inspection = _container_inspect(container_id, runner=runner)
    labels = inspection.get("Config", {}).get("Labels", {}) or {}
    if labels.get("com.docker.compose.project") != PROJECT:
        raise BackupError("DB container is not owned by Compose project finsport.")
    if labels.get("com.docker.compose.service") != SERVICE:
        raise BackupError("Operational container is not Compose service db.")
    if not inspection.get("State", {}).get("Running"):
        raise BackupError("Operational finsport/db container is not running.")
    image = inspection.get("Config", {}).get("Image", "")
    if image != "postgres:17":
        raise BackupError(
            f"Expected postgres:17 operational DB image; found {image!r}."
        )

    matching_mounts = [
        mount
        for mount in inspection.get("Mounts", [])
        if mount.get("Destination") == POSTGRES_DESTINATION
    ]
    if len(matching_mounts) != 1:
        raise BackupError("Operational PostgreSQL data mount is missing or ambiguous.")
    mount = matching_mounts[0]
    if mount.get("Type") != "volume" or mount.get("Name") != POSTGRES_VOLUME:
        raise BackupError(
            "Operational DB does not mount finsport_postgres_data at the expected path."
        )

    identity = (
        _run(
            [
                "docker",
                "exec",
                container_id,
                "psql",
                "-XAt",
                "-U",
                DATABASE_USER,
                "-d",
                DATABASE,
                "-c",
                "select current_database() || ':' || current_user",
            ],
            runner=runner,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        .stdout.decode()
        .strip()
    )
    if identity != f"{DATABASE}:{DATABASE_USER}":
        raise BackupError(f"Unexpected operational PostgreSQL identity: {identity!r}.")
    return container_id


def refresh_backup(backup_directory=DEFAULT_BACKUP_DIRECTORY, *, runner=subprocess.run):
    backup_directory = Path(backup_directory)
    backup_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup_directory.chmod(0o700)
    destination = backup_directory / "latest.dump"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".latest.dump.", suffix=".tmp", dir=backup_directory
    )
    temporary = Path(temporary_name)
    os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
    try:
        container_id = find_operational_database(runner=runner)
        with os.fdopen(descriptor, "wb") as dump_file:
            descriptor = -1
            _run(
                [
                    "docker",
                    "exec",
                    container_id,
                    "pg_dump",
                    "-U",
                    DATABASE_USER,
                    "-d",
                    DATABASE,
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                ],
                runner=runner,
                stdout=dump_file,
                stderr=subprocess.PIPE,
            )
            dump_file.flush()
            os.fsync(dump_file.fileno())
        if not temporary.stat().st_size:
            raise BackupError("pg_dump produced an empty archive.")
        with temporary.open("rb") as dump_file:
            _run(
                ["docker", "exec", "-i", container_id, "pg_restore", "--list"],
                runner=runner,
                stdin=dump_file,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        temporary.chmod(0o600)
        os.replace(temporary, destination)
        destination.chmod(0o600)
        return destination
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backup-directory",
        type=Path,
        default=DEFAULT_BACKUP_DIRECTORY,
        help="Override only for isolated tests; normal operation uses the user data path.",
    )
    arguments = parser.parse_args()
    try:
        destination = refresh_backup(arguments.backup_directory)
    except (BackupError, OSError) as error:
        print(f"backup failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(f"Validated rolling backup replaced atomically: {destination}")


if __name__ == "__main__":
    main()
