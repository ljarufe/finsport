from contextlib import contextmanager
from threading import Lock

from django.db import connection

LOCK_NAME = "finsport:fs005:api_football"
_fallback_lock = Lock()


@contextmanager
def capture_single_flight():
    if connection.vendor != "postgresql":
        acquired = _fallback_lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                _fallback_lock.release()
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s))", [LOCK_NAME])
        acquired = bool(cursor.fetchone()[0])
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [LOCK_NAME])
