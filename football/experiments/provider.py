"""FS-018 private cache, durable audit and restart-safe physical traffic policy."""

import time
from pathlib import Path

from football.providers.oddspapi import (
    BASE_URL,
    OddsPapiTransport,
    ProviderError,
    fixture_params,
    historical_params,
    validate_fixtures,
)

from .spec import BOOKMAKERS
from .storage import atomic_json, identity, lock, read_json, require_dev, roots


def empty_traffic_audit():
    return {
        "physical_calls": {"fixtures": 0, "historical-odds": 0, "account": 0},
        "http_status_counts": {},
        "network_errors": 0,
        "retries": 0,
        "http_429": 0,
        "cache_hits": {"fixtures": 0, "historical-odds": 0},
        "in_flight": 0,
    }


class OddsPapiClient:
    """Experiment policy wrapper; the reusable transport owns HTTP and shape."""

    def __init__(
        self,
        *,
        cache_root=None,
        audit_path=None,
        session=None,
        clock=time.time,
        sleep=time.sleep,
    ):
        self.root = Path(cache_root or roots()[0])
        self.audit_path = Path(audit_path or roots()[1] / "standalone-traffic.json")
        self.clock, self.sleep = clock, sleep
        self.transport = OddsPapiTransport(session=session, clock=clock, sleep=sleep)

    def _audit(self, event, endpoint, retry_index=0, status=None, cooldown=0):
        audit = (
            read_json(self.audit_path)
            if self.audit_path.exists()
            else empty_traffic_audit()
        )
        if event == "CACHE":
            audit["cache_hits"][endpoint] += 1
        elif event == "START":
            audit["physical_calls"][endpoint] += 1
            audit["retries"] += int(retry_index > 0)
            audit["in_flight"] += 1
        else:
            audit["in_flight"] -= 1
            if cooldown:
                path = roots()[0] / "traffic-clock.json"
                traffic = read_json(path) if path.exists() else {}
                key = f"{endpoint}:not_before"
                traffic[key] = max(traffic.get(key, 0), self.clock() + cooldown)
                atomic_json(path, traffic)
            if status is None:
                audit["network_errors"] += 1
            else:
                key = str(status)
                audit["http_status_counts"][key] = (
                    audit["http_status_counts"].get(key, 0) + 1
                )
                audit["http_429"] += int(status == 429)
        atomic_json(self.audit_path, audit)

    def _before_attempt(self, endpoint, interval):
        path = roots()[0] / "traffic-clock.json"
        last = read_json(path) if path.exists() else {}
        delay = max(
            0,
            last.get(endpoint, 0) + interval - self.clock(),
            last.get(f"{endpoint}:not_before", 0) - self.clock(),
        )
        if delay:
            self.sleep(delay)
        last[endpoint] = self.clock()
        atomic_json(path, last)

    def _callbacks(self):
        return {"before_attempt": self._before_attempt, "on_attempt": self._audit}

    def _cached(self, endpoint, params, fetch, *, cache=True, revision=None):
        require_dev()
        key = identity({"base": BASE_URL, "endpoint": endpoint, "params": params})
        path = self.root / f"{key}{'.' + revision if revision else ''}.json"
        # This lock spans cache recheck, cooldown, retries and the physical request.
        with lock(roots()[0] / "traffic.lock", blocking=True):
            if cache and path.exists():
                saved = read_json(path)
                if identity(saved["payload"]) != saved["hash"]:
                    raise ProviderError("CACHE_HASH_MISMATCH")
                self._audit("CACHE", endpoint)
                return saved["payload"], "CACHED"
            payload, metadata = fetch(self._callbacks())
            if cache:
                atomic_json(
                    path,
                    {
                        "payload": payload,
                        "hash": identity(payload),
                        "etag": metadata["etag"],
                    },
                )
            return payload, "FETCHED"

    def request(self, endpoint, params, *, cache=True):
        # Narrow compatibility path for offline fixtures/tests. Production research
        # uses the endpoint-specific methods below, owned by the transport.
        return self._cached(
            endpoint,
            params,
            lambda callbacks: self.transport.request(endpoint, params, **callbacks),
            cache=cache,
        )

    def account(self):
        require_dev()
        with lock(roots()[0] / "traffic.lock", blocking=True):
            value, _ = self.transport.account(**self._callbacks())
        return value

    def fixtures(self, tournament, start, end, *, refresh_revision=None):
        params = fixture_params(tournament, start, end)
        payload, state = self._cached(
            "fixtures",
            params,
            lambda callbacks: self.transport.fixtures(
                tournament, start, end, **callbacks
            ),
            revision=refresh_revision,
        )
        return validate_fixtures(payload, tournament, start, end), state

    def historical(self, fixture_id, *, refresh_revision=None):
        books = tuple(BOOKMAKERS)
        params = historical_params(fixture_id, books)
        return self._cached(
            "historical-odds",
            params,
            lambda callbacks: self.transport.historical(fixture_id, books, **callbacks),
            revision=refresh_revision,
        )

    def has_historical_cache(self, fixture_id, *, refresh_revision=None):
        params = historical_params(fixture_id, tuple(BOOKMAKERS))
        key = identity(
            {"base": BASE_URL, "endpoint": "historical-odds", "params": params}
        )
        path = (
            self.root
            / f"{key}{'.' + refresh_revision if refresh_revision else ''}.json"
        )
        if not path.exists():
            return False
        saved = read_json(path)
        if identity(saved["payload"]) != saved["hash"]:
            raise ProviderError("CACHE_HASH_MISMATCH")
        return True
