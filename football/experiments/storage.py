"""Canonical artifacts, atomic writes and process locks on the shared dev mount."""

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def identity(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timezone required")
    return result.astimezone(timezone.utc)


def read_json(path):
    return json.loads(Path(path).read_text())


def atomic_json(path, value):
    atomic_text(path, canonical(value) + "\n")


def atomic_text(path, value):
    atomic_bytes(path, value.encode())


def atomic_bytes(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def lock(path, *, blocking=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            raise ValueError("ALREADY_RUNNING") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def roots():
    base = Path(settings.BASE_DIR) / "tmp"
    return base / "FS-018_oddspapi", base / "FS-018_experiments"


def require_dev():
    if (
        os.environ.get("FINSPORT_EXPERIMENT_RUNTIME") != "finsport-dev"
        or settings.FOOTBALL_PIPELINE_ENABLED
        or settings.FOOTBALL_CAPTURE_ENABLED
        or settings.TIME_ZONE != "America/Lima"
        or settings.CELERY_TASK_DEFAULT_QUEUE != "finsport.local.safe"
    ):
        raise ValueError("RESEARCH_REQUIRES_ISOLATED_FINSPORT_DEV")


def local_spec_path(path):
    root = roots()[1].resolve()
    path = Path(path).resolve()
    if not path.is_relative_to(root) or path.suffix != ".json":
        raise ValueError("Spec must be a JSON file under tmp/FS-018_experiments")
    return path
