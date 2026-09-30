"""Read-only BSD v2 client with physical-call audit and bounded retries."""

import time

import requests
from django.conf import settings
from django.utils import timezone

from football.models import ProviderCallAudit


class BSDError(RuntimeError):
    def __init__(self, state, *, status=None, retry_after=None):
        super().__init__(state)
        self.state = state
        self.status = status
        self.retry_after = retry_after


class BSDClient:
    def __init__(self, *, token=None, session=None, sleep=None):
        self.token = settings.BSD_API_TOKEN if token is None else token
        self.session = session or requests.Session()
        self.sleep = sleep or time.sleep
        self.base_url = settings.BSD_API_BASE_URL.rstrip("/") + "/"

    def get(self, path, *, params=None, logical_identity, match_id=None):
        if not self.token:
            raise BSDError("BSD_NOT_CONFIGURED")
        if path.startswith("/") or ".." in path or path.startswith("http"):
            raise BSDError("BSD_INVALID_ENDPOINT")
        params = params or {}
        # The authorization header is deliberately absent from persistent audit.
        for attempt in (1, 2):
            started = timezone.now()
            audit = ProviderCallAudit.objects.create(
                provider="BSD",
                capability=(
                    "BSD_RESULT"
                    if path.startswith("events/") and path != "events/"
                    else "BSD_BOOTSTRAP"
                ),
                logical_identity=logical_identity,
                endpoint_family=path.split("/")[0],
                request_metadata={"path": path, "params": params, "match_id": match_id},
                fixture_count=int(match_id is not None),
                attempt_number=attempt,
                retry_number=attempt - 1,
                started_at=started,
            )
            response = None
            try:
                response = self.session.get(
                    self.base_url + path,
                    params=params,
                    headers={"Authorization": f"Token {self.token}"},
                    timeout=(3, 10),
                )
                audit.http_status = response.status_code
                audit.quota_remaining = _int_header(
                    response.headers, "X-RateLimit-Remaining"
                )
                audit.quota_limit = _int_header(response.headers, "X-RateLimit-Limit")
                audit.quota_observed_at = timezone.now()
                if response.status_code >= 400:
                    retry_after = _int_header(response.headers, "Retry-After")
                    if response.status_code == 401:
                        raise BSDError("BSD_AUTH_FAILED", status=401)
                    if response.status_code == 402:
                        raise BSDError("BSD_ENTITLEMENT_FAILED", status=402)
                    if response.status_code == 404:
                        raise BSDError("BSD_IDENTITY_UNRESOLVED", status=404)
                    if response.status_code == 429:
                        try:
                            code = response.json().get("code")
                        except ValueError:
                            code = None
                        state = (
                            "BSD_TASTER_EXHAUSTED"
                            if code == "taster_exhausted"
                            else "BSD_BACKOFF"
                        )
                        if (
                            state == "BSD_BACKOFF"
                            and attempt == 1
                            and retry_after is not None
                            and retry_after <= 5
                        ):
                            audit.outcome = state
                            audit.completed_at = timezone.now()
                            audit.save()
                            self.sleep(retry_after)
                            continue
                        raise BSDError(state, status=429, retry_after=retry_after)
                    if response.status_code >= 500 and attempt == 1:
                        audit.outcome = "RESULT_PROVIDER_ERROR"
                        audit.completed_at = timezone.now()
                        audit.save()
                        self.sleep(2)
                        continue
                    raise BSDError("RESULT_PROVIDER_ERROR", status=response.status_code)
                try:
                    data = response.json()
                except ValueError as error:
                    raise BSDError("RESULT_PROVIDER_MALFORMED") from error
                if not isinstance(data, (dict, list)):
                    raise BSDError("RESULT_PROVIDER_MALFORMED")
                audit.outcome = "SUCCESS"
                return data
            except requests.RequestException as error:
                audit.outcome = "RESULT_PROVIDER_ERROR"
                if attempt == 1:
                    self.sleep(2)
                    continue
                raise BSDError("RESULT_PROVIDER_ERROR") from error
            except BSDError as error:
                audit.outcome = error.state
                raise
            finally:
                if audit.completed_at is None:
                    audit.completed_at = timezone.now()
                    audit.save()
        raise BSDError("RESULT_PROVIDER_ERROR")


def _int_header(headers, name):
    try:
        return max(0, int(headers[name]))
    except (KeyError, ValueError, TypeError):
        return None
