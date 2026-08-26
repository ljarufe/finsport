import pytest
import requests

from football.api_inkabet import (
    InkabetClient,
    InkabetConfigurationError,
    InkabetResponseError,
)


class Response:
    def __init__(
        self,
        payload=None,
        *,
        status_code=200,
        headers=None,
        text="",
        json_error=None,
    ):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def get(self, url, *, params, headers, timeout):
        prepared = requests.Session().prepare_request(
            requests.Request("GET", url, params=params, headers=headers)
        )
        self.requests.append(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "timeout": timeout,
                "prepared": prepared,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def client_with(session):
    return InkabetClient(
        brand_id="fictional-brand",
        market_code="fictional-market",
        base_url="https://inkabet.test/api/sb/v1/",
        timeout=7,
        session=session,
    )


def test_client_uses_get_with_observed_metadata_and_no_browser_state():
    session = Session(Response({"data": {"items": {"indexBySlug": {}}}}))
    client = client_with(session)

    client.categories()

    request = session.requests[0]
    assert request["headers"] == {
        "brandId": "fictional-brand",
        "marketCode": "fictional-market",
        "x-sb-type": "b2b",
        "Accept-Encoding": None,
    }
    assert "Accept-Encoding" not in request["prepared"].headers
    assert request["prepared"].headers["User-Agent"].startswith("python-requests/")
    assert "Cookie" not in request["prepared"].headers
    assert request["timeout"] == 7
    assert client.calls == 1


def test_client_requests_only_categories_and_mw3w_contracts():
    session = Session(Response({"data": {}}), Response({"data": {}}))
    client = client_with(session)

    client.categories()
    client.match_winner("f-fixture")

    assert session.requests[0]["url"].endswith("/widgets/categories/v2")
    assert session.requests[0]["params"] is None
    assert session.requests[1]["url"].endswith("/widgets/accordion/v1")
    assert session.requests[1]["params"] == {
        "eventId": "f-fixture",
        "groupableId": "MW3W",
    }
    assert client.calls == 2


def test_client_rejects_missing_configuration():
    with pytest.raises(InkabetConfigurationError, match="are required"):
        InkabetClient(brand_id="", market_code="")


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (Response(json_error=ValueError("bad body")), "invalid JSON"),
        (Response({"unexpected": []}), "unexpected response shape"),
        (Response({"data": []}), "unexpected response shape"),
    ],
)
def test_client_rejects_invalid_json_and_shapes(response, message):
    client = client_with(Session(response))

    with pytest.raises(InkabetResponseError, match=message):
        client.categories()

    assert client.calls == 1


def test_client_sanitizes_http_maintenance_diagnostics():
    session = Session(
        Response(
            status_code=503,
            headers={
                "content-type": "text/html\nunsafe",
                "server": "CloudFront",
                "x-cache": "Error from cloudfront",
                "x-amz-cf-pop": "MIA3-P2",
            },
            text="Maintenance page private-token=must-not-leak",
        )
    )
    client = client_with(session)

    with pytest.raises(InkabetResponseError) as captured:
        client.categories()

    message = str(captured.value)
    assert "HTTP 503" in message
    assert "kind=maintenance" in message
    assert "content_type=text/html unsafe" in message
    assert "must-not-leak" not in message
    assert client.calls == 1


def test_client_reports_sanitized_non_maintenance_http_diagnostics():
    client = client_with(
        Session(
            Response(
                status_code=403,
                headers={"content-type": "application/json"},
                text='{"private_token": "must-not-leak"}',
            )
        )
    )

    with pytest.raises(InkabetResponseError) as captured:
        client.categories()

    message = str(captured.value)
    assert "HTTP 403" in message
    assert "kind=http" in message
    assert "must-not-leak" not in message


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (requests.Timeout(), "timed out"),
        (requests.ConnectionError(), "unreachable"),
    ],
)
def test_client_sanitizes_transport_errors_and_counts_calls(error, message):
    client = client_with(Session(error))

    with pytest.raises(InkabetResponseError, match=message):
        client.categories()

    assert client.calls == 1
