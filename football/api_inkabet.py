import requests
from django.conf import settings


class InkabetError(Exception):
    """Base error for the read-only Inkabet JSON boundary."""


class InkabetConfigurationError(InkabetError):
    pass


class InkabetResponseError(InkabetError):
    pass


def _safe_metadata(value):
    return " ".join(str(value or "unknown").split())[:120]


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
            raise InkabetResponseError("Inkabet request timed out.") from error
        except requests.RequestException as error:
            raise InkabetResponseError("Inkabet was unreachable.") from error

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
                f"pop={pop})."
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise InkabetResponseError("Inkabet returned invalid JSON.") from error

        if not isinstance(payload, dict) or not isinstance(
            payload.get("data"),
            dict,
        ):
            raise InkabetResponseError("Inkabet returned an unexpected response shape.")

        return payload

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
