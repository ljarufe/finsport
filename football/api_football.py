import json
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings


class APIFootballError(Exception):
    """Base error for the read-only API-Football boundary."""


class APIFootballConfigurationError(APIFootballError):
    pass


class APIFootballAuthenticationError(APIFootballError):
    pass


class APIFootballRateLimitError(APIFootballError):
    pass


class APIFootballResponseError(APIFootballError):
    pass


class APIFootballTransientError(APIFootballError):
    pass


class APIFootballQuotaReserveError(APIFootballError):
    pass


class APIFootballPaginationError(APIFootballError):
    pass


class APIFootballClient:
    def __init__(
        self,
        *,
        api_key=None,
        base_url=None,
        timeout=None,
        daily_reserve=None,
        max_pages=None,
        max_retries=None,
        minimum_interval=None,
        opener=None,
        sleep=None,
        monotonic=None,
    ):
        self.api_key = api_key if api_key is not None else settings.API_FOOTBALL_KEY
        if not self.api_key:
            raise APIFootballConfigurationError(
                "API_FOOTBALL_KEY is required for provider synchronization."
            )
        configured_url = base_url or settings.API_FOOTBALL_BASE_URL
        self.base_url = configured_url.rstrip("/") + "/"
        self.timeout = timeout or settings.API_FOOTBALL_TIMEOUT
        self.daily_reserve = (
            settings.API_FOOTBALL_DAILY_RESERVE
            if daily_reserve is None
            else daily_reserve
        )
        self.max_pages = max_pages or settings.API_FOOTBALL_MAX_PAGES
        self.max_retries = (
            settings.API_FOOTBALL_MAX_RETRIES if max_retries is None else max_retries
        )
        self.minimum_interval = (
            settings.API_FOOTBALL_MINIMUM_INTERVAL
            if minimum_interval is None
            else minimum_interval
        )
        self._opener = opener or urlopen
        self._sleep = sleep or time.sleep
        self._monotonic = monotonic or time.monotonic
        self._last_request_at = None

        self.calls = 0
        self.daily_limit = None
        self.daily_remaining = None
        self.minute_limit = None
        self.minute_remaining = None

    def get_all(self, endpoint, params=None):
        params = dict(params or {})
        first_page = self.get_page(endpoint, params)
        response = list(first_page.get("response") or [])
        paging = first_page.get("paging") or {}
        current = self._positive_int(paging.get("current"), default=1)
        total = self._positive_int(paging.get("total"), default=current)
        if total > self.max_pages:
            raise APIFootballPaginationError(
                f"Provider pagination requires {total} pages; configured bound is "
                f"{self.max_pages}."
            )
        while current < total:
            current += 1
            page_params = {**params, "page": current}
            page = self.get_page(endpoint, page_params)
            response.extend(page.get("response") or [])
            page_paging = page.get("paging") or {}
            reported_current = self._positive_int(
                page_paging.get("current"), default=current
            )
            reported_total = self._positive_int(page_paging.get("total"), default=total)
            if reported_current != current or reported_total != total:
                raise APIFootballPaginationError(
                    "Provider pagination changed unexpectedly during synchronization."
                )
        return response

    def get_page(self, endpoint, params=None):
        endpoint = endpoint.strip("/")
        query = urlencode(params or {})
        url = f"{self.base_url}{endpoint}"
        if query:
            url = f"{url}?{query}"
        request = Request(
            url,
            headers={"x-apisports-key": self.api_key, "Accept": "application/json"},
            method="GET",
        )

        for attempt in range(self.max_retries + 1):
            self._guard_daily_reserve()
            self._pace()
            self.calls += 1
            try:
                with self._opener(request, timeout=self.timeout) as response:
                    self._read_quota_headers(response.headers)
                    payload = json.loads(response.read().decode("utf-8"))
            except HTTPError as error:
                self._read_quota_headers(error.headers)
                if error.code in (401, 403):
                    raise APIFootballAuthenticationError(
                        f"API-Football rejected authentication (HTTP {error.code})."
                    ) from error
                if error.code == 429:
                    raise APIFootballRateLimitError(
                        "API-Football rate limit reached (HTTP 429)."
                    ) from error
                if 500 <= error.code < 600:
                    if attempt < self.max_retries:
                        continue
                    raise APIFootballTransientError(
                        f"API-Football failed after bounded retries (HTTP {error.code})."
                    ) from error
                raise APIFootballResponseError(
                    f"API-Football request failed (HTTP {error.code})."
                ) from error
            except (TimeoutError, socket.timeout, URLError) as error:
                if attempt < self.max_retries:
                    continue
                raise APIFootballTransientError(
                    "API-Football timed out or was unreachable after bounded retries."
                ) from error
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise APIFootballResponseError(
                    "API-Football returned an invalid JSON response."
                ) from error

            errors = payload.get("errors") if isinstance(payload, dict) else None
            if errors:
                error_summary = json.dumps(errors).casefold()
                if (
                    "free plans do not have access" in error_summary
                    or "limited to" in error_summary
                ):
                    raise APIFootballResponseError(
                        "API-Football denied the requested season/date under "
                        "the current plan."
                    )
                raise APIFootballResponseError(
                    "API-Football returned a provider error response."
                )
            if not isinstance(payload, dict) or not isinstance(
                payload.get("response", []), list
            ):
                raise APIFootballResponseError(
                    "API-Football returned an unexpected response shape."
                )
            return payload

        raise APIFootballTransientError("API-Football retry bound was exhausted.")

    def _guard_daily_reserve(self):
        if (
            self.daily_remaining is not None
            and self.daily_remaining <= self.daily_reserve
        ):
            raise APIFootballQuotaReserveError(
                f"Daily quota reserve reached ({self.daily_remaining} remaining; "
                f"reserve {self.daily_reserve})."
            )

    def _pace(self):
        now = self._monotonic()
        if self._last_request_at is not None:
            interval = self.minimum_interval
            if self.minute_limit:
                interval = max(interval, 60 / self.minute_limit)
            elapsed = now - self._last_request_at
            if elapsed < interval:
                self._sleep(interval - elapsed)
                now = self._monotonic()
        self._last_request_at = now

    def _read_quota_headers(self, headers):
        if not headers:
            return
        normalized = {str(key).lower(): value for key, value in headers.items()}
        self.daily_limit = self._optional_int(
            normalized.get("x-ratelimit-requests-limit"), self.daily_limit
        )
        self.daily_remaining = self._optional_int(
            normalized.get("x-ratelimit-requests-remaining"), self.daily_remaining
        )
        self.minute_limit = self._optional_int(
            normalized.get("x-ratelimit-limit"), self.minute_limit
        )
        self.minute_remaining = self._optional_int(
            normalized.get("x-ratelimit-remaining"), self.minute_remaining
        )

    @staticmethod
    def _optional_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _positive_int(value, default):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default
