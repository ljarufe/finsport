import io
import json
import socket
from urllib.error import HTTPError

import pytest

from football.api_football import (
    APIFootballAuthenticationError,
    APIFootballClient,
    APIFootballPaginationError,
    APIFootballQuotaReserveError,
    APIFootballRateLimitError,
    APIFootballResponseError,
    APIFootballTransientError,
)


class Response:
    def __init__(self, payload, headers=None):
        self.payload = payload
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class QueueOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def payload(response=None, current=1, total=1, errors=None):
    return {
        "get": "fixtures",
        "parameters": {},
        "errors": errors or [],
        "results": len(response or []),
        "paging": {"current": current, "total": total},
        "response": response or [],
    }


def client(opener, **kwargs):
    return APIFootballClient(
        api_key="fictional-provider-secret",
        opener=opener,
        minimum_interval=0,
        max_retries=kwargs.pop("max_retries", 0),
        **kwargs,
    )


def http_error(code, headers=None):
    return HTTPError(
        "https://provider.test/fixtures",
        code,
        "error",
        headers or {},
        io.BytesIO(b"{}"),
    )


def test_success_empty_response_and_quota_headers():
    opener = QueueOpener(
        Response(
            payload(),
            {
                "x-ratelimit-requests-limit": "100",
                "x-ratelimit-requests-remaining": "81",
                "X-RateLimit-Limit": "10",
                "X-RateLimit-Remaining": "9",
            },
        )
    )
    api = client(opener)

    assert api.get_all("fixtures", {"date": "2025-08-24"}) == []
    assert api.calls == 1
    assert api.daily_limit == 100
    assert api.daily_remaining == 81
    assert api.minute_limit == 10
    assert api.minute_remaining == 9
    request, timeout = opener.requests[0]
    assert request.method == "GET"
    assert timeout == api.timeout
    assert "fictional-provider-secret" not in request.full_url


def test_minute_only_header_is_not_a_daily_quota_observation():
    api = client(
        QueueOpener(
            Response(
                payload(),
                {"X-RateLimit-Limit": "10", "X-RateLimit-Remaining": "9"},
            )
        )
    )
    api.get_page("fixtures")
    assert api.minute_remaining == 9
    assert api.daily_remaining is None
    assert api.quota_observed_at is None


def test_pagination_requests_each_page_and_has_hard_bound():
    opener = QueueOpener(
        Response(payload([{"id": 1}], current=1, total=2)),
        Response(payload([{"id": 2}], current=2, total=2)),
    )
    api = client(opener, max_pages=2)
    assert api.get_all("odds", {"league": 39}) == [{"id": 1}, {"id": 2}]
    assert "page=2" in opener.requests[1][0].full_url

    bounded = client(
        QueueOpener(Response(payload([{"id": 1}], current=1, total=3))),
        max_pages=2,
    )
    with pytest.raises(APIFootballPaginationError, match="configured bound"):
        bounded.get_all("odds")
    assert bounded.calls == 1


def test_attempt_guard_rechecks_before_every_page():
    opener = QueueOpener(
        Response(payload([{"id": 1}], current=1, total=2)),
        Response(payload([{"id": 2}], current=2, total=2)),
    )
    admitted_calls = []
    api = client(opener, max_pages=2)
    api.attempt_guard = lambda active: admitted_calls.append(active.calls)

    assert api.get_all("odds", {"fixture": 1}) == [{"id": 1}, {"id": 2}]
    assert admitted_calls == [0, 1]
    assert api.pages == 2


@pytest.mark.parametrize(
    ("status", "exception"),
    [
        (401, APIFootballAuthenticationError),
        (403, APIFootballAuthenticationError),
        (429, APIFootballRateLimitError),
    ],
)
def test_explicit_authentication_and_rate_limit_errors(status, exception):
    with pytest.raises(exception) as captured:
        client(QueueOpener(http_error(status))).get_page("fixtures")
    assert "fictional-provider-secret" not in str(captured.value)


def test_provider_error_response_does_not_leak_secret():
    api = client(
        QueueOpener(Response(payload(errors={"token": "fictional-provider-secret"})))
    )
    with pytest.raises(APIFootballResponseError) as captured:
        api.get_page("fixtures")
    assert "fictional-provider-secret" not in str(captured.value)


def test_free_plan_restriction_has_clear_sanitized_error():
    api = client(
        QueueOpener(
            Response(
                payload(errors={"plan": "Free plans do not have access to this season"})
            )
        )
    )
    with pytest.raises(APIFootballResponseError, match="current plan"):
        api.get_page("fixtures")


def test_timeout_and_5xx_retries_are_bounded():
    timeouts = QueueOpener(socket.timeout(), socket.timeout())
    timeout_client = client(timeouts, max_retries=1)
    with pytest.raises(APIFootballTransientError):
        timeout_client.get_page("fixtures")
    assert len(timeouts.requests) == 2
    assert timeout_client.retries == 1

    failures = QueueOpener(http_error(503), http_error(503))
    with pytest.raises(APIFootballTransientError, match="bounded retries"):
        client(failures, max_retries=1).get_page("fixtures")
    assert len(failures.requests) == 2


def test_daily_reserve_stops_before_another_request():
    opener = QueueOpener(Response(payload(), {"x-ratelimit-requests-remaining": "20"}))
    api = client(opener, daily_reserve=20)
    api.get_page("fixtures")
    with pytest.raises(APIFootballQuotaReserveError, match="reserve reached"):
        api.get_page("fixtures")
    assert api.calls == 1


def test_default_daily_reserve_is_zero_and_stops_at_exhaustion(settings):
    settings.API_FOOTBALL_DAILY_RESERVE = 0
    opener = QueueOpener(Response(payload(), {"x-ratelimit-requests-remaining": "0"}))
    api = client(opener)
    api.get_page("fixtures")
    with pytest.raises(APIFootballQuotaReserveError, match="0 remaining"):
        api.get_page("fixtures")
    assert api.daily_reserve == 0
    assert api.calls == 1


def test_sequential_requests_are_paced_from_minute_limit():
    current_time = [0.0]
    sleeps = []

    def monotonic():
        return current_time[0]

    def sleep(seconds):
        sleeps.append(seconds)
        current_time[0] += seconds

    opener = QueueOpener(
        Response(payload(), {"X-RateLimit-Limit": "10"}), Response(payload())
    )
    api = APIFootballClient(
        api_key="fictional-provider-secret",
        opener=opener,
        minimum_interval=1,
        max_retries=0,
        sleep=sleep,
        monotonic=monotonic,
    )
    api.get_page("fixtures")
    api.get_page("fixtures")
    assert sleeps == [6.0]
