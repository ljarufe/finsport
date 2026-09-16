"""Read-only API-Football source integration."""

import json
import socket
import time
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from football.observability.events import (
    safe_provider_error_diagnostic,
    sanitize_text,
)


class APIFootballError(Exception):
    """Base error for the read-only API-Football boundary."""

    provider = "API-Football"
    failure_kind = "provider_request"

    def __init__(self, message, *, failure_kind=None, diagnostic_context=None):
        super().__init__(message)
        if failure_kind:
            self.failure_kind = failure_kind
        self.diagnostic_context = diagnostic_context or {}


class APIFootballConfigurationError(APIFootballError):
    failure_kind = "provider_configuration"


class APIFootballAuthenticationError(APIFootballError):
    failure_kind = "provider_authentication"


class APIFootballRateLimitError(APIFootballError):
    failure_kind = "provider_rate_limit"


class APIFootballResponseError(APIFootballError):
    pass


class APIFootballTransientError(APIFootballError):
    pass


class APIFootballQuotaReserveError(APIFootballError):
    failure_kind = "provider_quota"


class APIFootballPaginationError(APIFootballError):
    failure_kind = "provider_pagination"


class APIFootballOperationBudgetError(APIFootballError):
    failure_kind = "provider_budget"


FIXTURE_TIMEZONE = "America/Lima"
AUDIT_SECRET_KEYS = (
    "key",
    "token",
    "secret",
    "password",
    "credential",
    "authorization",
)


def _safe_audit_metadata(value, *, depth=0):
    if depth > 3:
        return "<truncated>"
    if isinstance(value, dict):
        return {
            sanitize_text(key, 80): (
                "<redacted>"
                if any(marker in str(key).casefold() for marker in AUDIT_SECRET_KEYS)
                else _safe_audit_metadata(item, depth=depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_audit_metadata(item, depth=depth + 1) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize_text(value, 200)


def fixture_date_params(day, timezone_name):
    """The supported plan's date-shaped fixture request."""

    return {
        "date": day.isoformat() if isinstance(day, date) else str(day),
        "timezone": str(timezone_name),
    }


def fixture_id_params(fixture_id):
    """The supported plan's singular directed fixture request."""

    return {"id": str(fixture_id)}


def fixtures_by_date(client, day, timezone_name=FIXTURE_TIMEZONE):
    return client.get_all("fixtures", fixture_date_params(day, timezone_name))


def fixture_by_id(client, fixture_id):
    return client.get_all("fixtures", fixture_id_params(fixture_id))


def relevant_fixture_payloads(payloads, external_ids):
    """Keep only known Finsport fixtures before canonical domain sync."""

    expected = {str(external_id) for external_id in external_ids}
    return [
        item
        for item in payloads
        if str((item.get("fixture") or {}).get("id")) in expected
    ]


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
        attempt_guard=None,
        capability="OTHER_EXPLICIT_MAINTENANCE",
        logical_identity="unclassified",
        audit_links=None,
        request_metadata=None,
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
        self.attempt_guard = attempt_guard
        self.capability = capability
        self.logical_identity = logical_identity
        self.audit_links = dict(audit_links or {})
        self.request_metadata = dict(request_metadata or {})
        self.represented_fixture_count = None
        self.audit_enabled = False
        self._last_request_at = None

        self.calls = 0
        self.pages = 0
        self.retries = 0
        self.daily_limit = None
        self.daily_remaining = None
        self.minute_limit = None
        self.minute_remaining = None
        self.quota_observed_at = None
        self.quota_observed_calls = 0
        self.minute_observed_calls = 0

    def set_audit_context(
        self,
        capability,
        logical_identity,
        *,
        audit_links=None,
        request_metadata=None,
        represented_fixture_count=None,
    ):
        self.capability = capability
        self.logical_identity = logical_identity
        self.audit_links = dict(audit_links or {})
        self.request_metadata = dict(request_metadata or {})
        if represented_fixture_count is not None and (
            isinstance(represented_fixture_count, bool)
            or not isinstance(represented_fixture_count, int)
            or represented_fixture_count < 0
        ):
            raise ValueError("represented_fixture_count must be a nonnegative integer")
        self.represented_fixture_count = represented_fixture_count
        self.audit_enabled = True

    def _start_audit(self, endpoint, params, attempt):
        if not self.audit_enabled:
            return None
        from football.models import ProviderCallAudit

        safe_params = _safe_audit_metadata(params or {})
        fixture_count = self.represented_fixture_count
        if fixture_count is None:
            fixture_count = int(
                bool((params or {}).get("fixture") or (params or {}).get("id"))
            )
        return ProviderCallAudit.objects.create(
            capability=self.capability,
            logical_identity=self.logical_identity,
            endpoint_family=endpoint,
            request_metadata={
                **safe_params,
                **_safe_audit_metadata(self.request_metadata),
            },
            fixture_count=fixture_count,
            attempt_number=self.calls,
            page_number=self._positive_int((params or {}).get("page"), 1),
            retry_number=attempt,
            started_at=timezone.now(),
            capture_run_id=self.audit_links.get("capture_run_id"),
            capture_work_item_id=self.audit_links.get("capture_work_item_id"),
            maintenance_run_id=self.audit_links.get("maintenance_run_id"),
        )

    def _finish_audit(self, audit, outcome, *, http_status=None, retry_reason=""):
        if audit is None:
            return
        audit.completed_at = timezone.now()
        audit.outcome = outcome
        audit.http_status = http_status
        audit.retry_reason = retry_reason[:120]
        if self.quota_observed_calls == self.calls:
            audit.quota_limit = self.daily_limit
            audit.quota_remaining = self.daily_remaining
            audit.quota_observed_at = self.quota_observed_at
        if self.minute_observed_calls == self.calls:
            audit.minute_limit = self.minute_limit
            audit.minute_remaining = self.minute_remaining
        audit.save()

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
                f"{self.max_pages}.",
                diagnostic_context={"endpoint_family": endpoint.strip("/")},
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
                    "Provider pagination changed unexpectedly during synchronization.",
                    diagnostic_context={"endpoint_family": endpoint.strip("/")},
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
            if self.attempt_guard is not None:
                try:
                    self.attempt_guard(self)
                except APIFootballError as error:
                    error.diagnostic_context = {
                        "endpoint_family": endpoint,
                        **error.diagnostic_context,
                    }
                    raise
            if attempt > 0:
                self.retries += 1
            self._guard_daily_reserve(endpoint)
            self._pace()
            self.calls += 1
            audit = self._start_audit(endpoint, params, attempt)
            response_metadata = {"endpoint_family": endpoint}
            try:
                with self._opener(request, timeout=self.timeout) as response:
                    self._read_quota_headers(response.headers)
                    raw_payload = response.read()
                    response_metadata = self._response_metadata(
                        endpoint,
                        response.headers,
                        http_status=getattr(response, "status", 200),
                        response_size=len(raw_payload),
                    )
                    payload = json.loads(raw_payload.decode("utf-8"))
            except HTTPError as error:
                self._read_quota_headers(error.headers)
                diagnostic_context = self._response_metadata(
                    endpoint,
                    error.headers,
                    http_status=error.code,
                )
                if error.code in (401, 403):
                    self._finish_audit(
                        audit, "AUTHENTICATION_ERROR", http_status=error.code
                    )
                    raise APIFootballAuthenticationError(
                        f"API-Football rejected authentication (HTTP {error.code}).",
                        diagnostic_context=diagnostic_context,
                    ) from error
                if error.code == 429:
                    self._finish_audit(audit, "RATE_LIMITED", http_status=error.code)
                    raise APIFootballRateLimitError(
                        "API-Football rate limit reached (HTTP 429).",
                        diagnostic_context=diagnostic_context,
                    ) from error
                if 500 <= error.code < 600:
                    if attempt < self.max_retries:
                        self._finish_audit(
                            audit,
                            "TRANSIENT_RETRY",
                            http_status=error.code,
                            retry_reason="HTTP_5XX",
                        )
                        continue
                    self._finish_audit(
                        audit, "TRANSIENT_FAILURE", http_status=error.code
                    )
                    raise APIFootballTransientError(
                        f"API-Football failed after bounded retries (HTTP {error.code}).",
                        failure_kind="provider_http",
                        diagnostic_context=diagnostic_context,
                    ) from error
                self._finish_audit(
                    audit, "DETERMINISTIC_HTTP_ERROR", http_status=error.code
                )
                raise APIFootballResponseError(
                    f"API-Football request failed (HTTP {error.code}).",
                    failure_kind="provider_http",
                    diagnostic_context=diagnostic_context,
                ) from error
            except (TimeoutError, socket.timeout, URLError) as error:
                if attempt < self.max_retries:
                    self._finish_audit(
                        audit,
                        "TRANSIENT_RETRY",
                        retry_reason=error.__class__.__name__,
                    )
                    continue
                transport_category = (
                    "timeout"
                    if isinstance(error, (TimeoutError, socket.timeout))
                    else "unreachable"
                )
                self._finish_audit(
                    audit,
                    "TRANSIENT_FAILURE",
                    retry_reason=error.__class__.__name__,
                )
                raise APIFootballTransientError(
                    "API-Football timed out or was unreachable after bounded retries.",
                    failure_kind="provider_transport",
                    diagnostic_context={
                        "endpoint_family": endpoint,
                        "transport_category": transport_category,
                    },
                ) from error
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                self._finish_audit(audit, "SCHEMA_ERROR")
                raise APIFootballResponseError(
                    "API-Football returned an invalid JSON response.",
                    failure_kind="provider_schema_drift",
                    diagnostic_context={
                        **response_metadata,
                        "expected_category": "JSON object",
                        "actual_category": "invalid JSON",
                        "json_path": "$",
                    },
                ) from error

            errors = payload.get("errors") if isinstance(payload, dict) else None
            if errors:
                provider_diagnostic = safe_provider_error_diagnostic(errors)
                diagnostic_context = {
                    **response_metadata,
                    **provider_diagnostic,
                }
                error_summary = provider_diagnostic["provider_error_summary"]
                if (
                    "free plans do not have access" in error_summary.casefold()
                    or "limited to" in error_summary.casefold()
                ):
                    self._finish_audit(
                        audit,
                        "PLAN_ACCESS_DENIED",
                        http_status=response_metadata.get("http_status"),
                    )
                    raise APIFootballResponseError(
                        "API-Football denied the requested season/date under "
                        "the current plan.",
                        failure_kind="provider_access_denied",
                        diagnostic_context=diagnostic_context,
                    )
                message = "API-Football returned a provider application error."
                if error_summary:
                    message = sanitize_text(
                        f"API-Football reported: {error_summary}",
                        500,
                    )
                self._finish_audit(
                    audit,
                    "PROVIDER_APPLICATION_ERROR",
                    http_status=response_metadata.get("http_status"),
                )
                raise APIFootballResponseError(
                    message,
                    failure_kind="provider_application_error",
                    diagnostic_context=diagnostic_context,
                )
            if not isinstance(payload, dict) or not isinstance(
                payload.get("response"), list
            ):
                self._finish_audit(
                    audit,
                    "SCHEMA_ERROR",
                    http_status=response_metadata.get("http_status"),
                )
                raise APIFootballResponseError(
                    "API-Football returned an unexpected response shape.",
                    failure_kind="provider_schema_drift",
                    diagnostic_context={
                        **response_metadata,
                        "expected_category": "object with response array",
                        "actual_category": type(payload).__name__,
                        "json_path": "$.response",
                        "top_level_keys": (
                            sorted(str(key) for key in payload)[:20]
                            if isinstance(payload, dict)
                            else []
                        ),
                    },
                )
            self.pages += 1
            self._finish_audit(
                audit,
                "SUCCESS",
                http_status=response_metadata.get("http_status", 200),
            )
            return payload

        raise APIFootballTransientError("API-Football retry bound was exhausted.")

    @staticmethod
    def _response_metadata(endpoint, headers, *, http_status, response_size=None):
        headers = headers or {}
        content_length = APIFootballClient._optional_int(
            headers.get("content-length"),
            response_size,
        )
        metadata = {
            "endpoint_family": endpoint,
            "http_status": http_status,
            "content_type": sanitize_text(
                headers.get("content-type", "unknown"),
                120,
            ),
            "provider_request_id": sanitize_text(
                headers.get("x-request-id", ""),
                200,
            ),
        }
        if content_length is not None:
            metadata["response_size"] = max(0, content_length)
        return metadata

    def _guard_daily_reserve(self, endpoint):
        if (
            self.daily_remaining is not None
            and self.daily_remaining <= self.daily_reserve
        ):
            raise APIFootballQuotaReserveError(
                f"Daily quota reserve reached ({self.daily_remaining} remaining; "
                f"reserve {self.daily_reserve}).",
                diagnostic_context={"endpoint_family": endpoint},
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
        if (
            self._optional_int(normalized.get("x-ratelimit-requests-remaining"), None)
            is not None
        ):
            self.quota_observed_at = timezone.now()
            self.quota_observed_calls = self.calls
        if (
            self._optional_int(normalized.get("x-ratelimit-remaining"), None)
            is not None
        ):
            self.minute_observed_calls = self.calls

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
