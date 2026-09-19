"""Reusable OddsPapi v4 HTTP boundary; no football experiment dependency."""

import json
import math
import os
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

SOURCE = "oddspapi"
BASE_URL = "https://api.oddspapi.io/v4"
MIN_INTERVAL_SECONDS = {"fixtures": 2, "historical-odds": 10, "account": 0}
ALLOWED_ENDPOINTS = frozenset(MIN_INTERVAL_SECONDS)


class ProviderError(ValueError):
    """A safe error code; response bodies and secret-bearing URLs never cross out."""


def utc_instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timezone required")
    return result.astimezone(timezone.utc)


def fixture_params(tournament, start, end):
    return {"tournamentId": tournament, "from": start, "to": end, "statusId": 2}


def historical_params(fixture_id, bookmakers):
    if (
        not isinstance(fixture_id, str)
        or not fixture_id
        or not 1 <= len(bookmakers) <= 3
        or len(set(bookmakers)) != len(bookmakers)
        or any(
            not isinstance(book, str) or not re.fullmatch(r"[a-z0-9_-]+", book)
            for book in bookmakers
        )
    ):
        raise ProviderError("INVALID_HISTORICAL_REQUEST")
    return {"fixtureId": fixture_id, "bookmakers": ",".join(bookmakers)}


def validate_fixtures(payload, tournament, start, end):
    if not isinstance(payload, list):
        raise ProviderError("FIXTURES_SHAPE_MISMATCH")
    seen, derived = set(), []
    for row in payload:
        try:
            fixture_id = row["fixtureId"]
            kickoff = utc_instant(row["startTime"])
            if (
                not isinstance(fixture_id, str)
                or not fixture_id
                or row["tournamentId"] != tournament
                or row["statusId"] != 2
                or not utc_instant(start) <= kickoff <= utc_instant(end)
            ):
                raise ValueError
            if fixture_id in seen:
                raise ProviderError("DUPLICATE_FIXTURE_ID")
            seen.add(fixture_id)
            names = [row["participant1Name"], row["participant2Name"]]
            if not all(isinstance(name, str) and name.strip() for name in names):
                raise ValueError
            derived.append(
                {
                    "fixture_id": fixture_id,
                    "kickoff": kickoff.isoformat(),
                    "home_name": names[0],
                    "away_name": names[1],
                }
            )
        except ProviderError:
            raise
        except (KeyError, ValueError, TypeError, AttributeError):
            raise ProviderError("FIXTURES_SHAPE_MISMATCH") from None
    return sorted(derived, key=lambda row: (row["kickoff"], row["fixture_id"]))


def parse_account(payload):
    """Only two quota integers leave this parser, never account identity."""
    try:
        if not isinstance(payload, dict) or not isinstance(
            payload.get("subscriptions"), list
        ):
            raise ValueError
        subscriptions = payload["subscriptions"]
        current_id = payload.get("current_subscription_id")
        current = [
            row
            for row in subscriptions
            if isinstance(row, dict)
            and current_id is not None
            and row.get("subscription_id") == current_id
            and row.get("is_active") is True
        ]
        if len(current) == 1:
            selected = current[0]
        elif len(current) > 1:
            raise ValueError
        else:
            active = [
                row
                for row in subscriptions
                if isinstance(row, dict) and row.get("is_active") is True
            ]
            if len(active) != 1:
                raise ValueError
            selected = active[0]
        limit, count = selected["request_limit"], selected["request_count"]
        if type(limit) is not int or type(count) is not int or limit < 0 or count < 0:
            raise ValueError
        return {"request_limit": limit, "request_count": count}
    except (KeyError, TypeError, ValueError):
        raise ProviderError("ACCOUNT_SHAPE_MISMATCH") from None


def classify_status(status):
    if status == 429:
        return "RATE_LIMITED"
    if status in (401, 403):
        return "ACCESS_DENIED"
    if status == 404:
        return "NOT_FOUND"
    if status >= 500:
        return "UPSTREAM_ERROR"
    return "HTTP_REJECTED"


class OddsPapiTransport:
    """Physical attempts and safe callbacks; caller owns storage and scheduling."""

    def __init__(self, *, session=None, clock=time.time, sleep=time.sleep, key=None):
        self.session = session or requests.Session()
        self.clock, self.sleep = clock, sleep
        self.key = key
        self.last_attempt = {}

    def request(self, endpoint, params, *, before_attempt=None, on_attempt=None):
        if endpoint not in ALLOWED_ENDPOINTS:
            raise ProviderError("UNSUPPORTED_ENDPOINT")
        secret = (
            self.key if self.key is not None else os.environ.get("ODDSPAPI_API_KEY")
        )
        if not secret:
            raise ProviderError("MISSING_ODDSPAPI_API_KEY")
        interval = MIN_INTERVAL_SECONDS[endpoint]
        for retry_index in range(3):
            delay = max(0, self.last_attempt.get(endpoint, 0) + interval - self.clock())
            if delay:
                self.sleep(delay)
            if before_attempt:
                before_attempt(endpoint, interval)
            self.last_attempt[endpoint] = self.clock()
            if on_attempt:
                on_attempt("START", endpoint, retry_index, None)
            response = None
            try:
                response = self.session.get(
                    f"{BASE_URL}/{endpoint}",
                    params={**params, "apiKey": secret},
                    timeout=(10, 60),
                    allow_redirects=False,
                )
            except requests.RequestException:
                pass  # requests exceptions may contain the full secret-bearing URL
            status = response.status_code if response is not None else None
            retryable = status is None or status == 429 or status >= 500
            cooldown = (
                max(
                    interval * (retry_index + 1),
                    2**retry_index,
                    _retry_after(response, self.clock()) if response is not None else 0,
                )
                if retryable
                else 0
            )
            if on_attempt:
                on_attempt("FINISH", endpoint, retry_index, status, cooldown)
            if status == 200:
                try:
                    payload = response.json()
                    if endpoint == "account":
                        # Project before the generic JSON/secret boundary. The real
                        # account response echoes api_key at its top level.
                        payload = parse_account(payload)
                    serialized = json.dumps(payload, sort_keys=True, allow_nan=False)
                except (TypeError, ValueError):
                    raise ProviderError("INVALID_SAFE_JSON") from None
                if secret in serialized:
                    raise ProviderError("SECRET_ECHO_REJECTED")
                return payload, {
                    "attempts": retry_index + 1,
                    "http_status": 200,
                    "etag": _safe_etag(response, secret),
                }
            classification = (
                classify_status(status) if status is not None else "NETWORK_ERROR"
            )
            if status is not None and status != 429 and status < 500:
                raise ProviderError(classification)
            if retry_index < 2:
                self.sleep(cooldown)
        raise ProviderError(classification)

    def account(self, **callbacks):
        payload, metadata = self.request("account", {}, **callbacks)
        return payload, metadata

    def fixtures(self, tournament, start, end, **callbacks):
        payload, metadata = self.request(
            "fixtures", fixture_params(tournament, start, end), **callbacks
        )
        validate_fixtures(payload, tournament, start, end)
        return payload, metadata

    def historical(self, fixture_id, bookmakers, **callbacks):
        return self.request(
            "historical-odds", historical_params(fixture_id, bookmakers), **callbacks
        )


def _safe_etag(response, secret):
    etag = response.headers.get("ETag", "")
    return etag if isinstance(etag, str) and secret not in etag else ""


def _retry_after(response, now):
    value = response.headers.get("Retry-After", "")
    try:
        seconds = float(value)
        return max(0, seconds) if math.isfinite(seconds) else 0
    except (TypeError, ValueError):
        try:
            return max(0, parsedate_to_datetime(value).timestamp() - now)
        except (TypeError, ValueError, IndexError, OverflowError):
            return 0
