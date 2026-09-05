"""Read-only Inkabet HTTP source integration."""

import requests
from django.conf import settings

from football.observability.events import sanitize_text


class InkabetError(Exception):
    """Base error for the read-only Inkabet JSON boundary."""

    provider = "Inkabet"
    failure_kind = "provider_request"

    def __init__(self, message, *, failure_kind=None, diagnostic_context=None):
        super().__init__(message)
        if failure_kind:
            self.failure_kind = failure_kind
        self.diagnostic_context = diagnostic_context or {}


class InkabetConfigurationError(InkabetError):
    failure_kind = "provider_configuration"


class InkabetResponseError(InkabetError):
    pass


def _safe_metadata(value):
    return " ".join(sanitize_text(value or "unknown", 120).split())


class InkabetClient:
    def __init__(
        self,
        *,
        brand_id=None,
        market_code=None,
        base_url=None,
        timeout=None,
        session=None,
    ):
        self.brand_id = settings.INKABET_BRAND_ID if brand_id is None else brand_id
        self.market_code = (
            settings.INKABET_MARKET_CODE if market_code is None else market_code
        )

        if not self.brand_id or not self.market_code:
            raise InkabetConfigurationError(
                "INKABET_BRAND_ID and INKABET_MARKET_CODE are required for "
                "Inkabet odds synchronization."
            )

        configured_url = base_url or settings.INKABET_BASE_URL
        self.base_url = configured_url.rstrip("/") + "/"
        self.timeout = timeout or settings.INKABET_TIMEOUT
        self._session = session or requests.Session()
        self.calls = 0

    def get_json(self, endpoint, params=None):
        url = f"{self.base_url}{endpoint.strip('/')}"

        headers = {
            "brandId": self.brand_id,
            "marketCode": self.market_code,
            "x-sb-type": "b2b",
            "Accept-Encoding": None,
        }

        self.calls += 1

        try:
            response = self._session.get(
                url,
                params=params or None,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.Timeout as error:
            raise InkabetResponseError(
                "Inkabet request timed out.",
                failure_kind="provider_transport",
                diagnostic_context={
                    "endpoint_family": endpoint,
                    "transport_category": "timeout",
                },
            ) from error
        except requests.RequestException as error:
            raise InkabetResponseError(
                "Inkabet was unreachable.",
                failure_kind="provider_transport",
                diagnostic_context={
                    "endpoint_family": endpoint,
                    "transport_category": "unreachable",
                },
            ) from error

        response_metadata = {
            "endpoint_family": endpoint,
            "http_status": response.status_code,
            "content_type": _safe_metadata(response.headers.get("content-type")),
            "response_size": self._response_size(response),
            "provider_request_id": sanitize_text(
                response.headers.get("x-request-id", ""),
                200,
            ),
        }

        if response.status_code >= 400:
            content_type = _safe_metadata(response.headers.get("content-type"))
            server = _safe_metadata(response.headers.get("server"))
            cache = _safe_metadata(response.headers.get("x-cache"))
            pop = _safe_metadata(response.headers.get("x-amz-cf-pop"))

            body_prefix = response.text[:4096].casefold()
            kind = "maintenance" if "maintenance page" in body_prefix else "http"

            raise InkabetResponseError(
                "Inkabet request failed "
                f"(HTTP {response.status_code}, "
                f"kind={kind}, "
                f"content_type={content_type}, "
                f"server={server}, "
                f"cache={cache}, "
                f"pop={pop}).",
                failure_kind="provider_http",
                diagnostic_context=response_metadata,
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise InkabetResponseError(
                "Inkabet returned invalid JSON.",
                failure_kind="provider_schema_drift",
                diagnostic_context={
                    **response_metadata,
                    "expected_category": "JSON object",
                    "actual_category": "invalid JSON",
                    "json_path": "$",
                },
            ) from error

        if not isinstance(payload, dict) or not isinstance(
            payload.get("data"),
            dict,
        ):
            raise InkabetResponseError(
                "Inkabet returned an unexpected response shape.",
                failure_kind="provider_schema_drift",
                diagnostic_context={
                    **response_metadata,
                    "expected_category": "object with data object",
                    "actual_category": type(payload).__name__,
                    "json_path": "$.data",
                    "top_level_keys": (
                        sorted(str(key) for key in payload)[:20]
                        if isinstance(payload, dict)
                        else []
                    ),
                },
            )

        return payload

    @staticmethod
    def _response_size(response):
        content = getattr(response, "content", None)
        if content is not None:
            return len(content)
        return len(str(getattr(response, "text", "")).encode())

    def categories(self):
        return self.get_json("widgets/categories/v2")

    def match_winner(self, event_id):
        return self.get_json(
            "widgets/accordion/v1",
            {
                "eventId": event_id,
                "groupableId": "MW3W",
            },
        )
