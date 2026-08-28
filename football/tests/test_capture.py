import socket
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from football.api_football import (
    APIFootballClient,
    APIFootballConfigurationError,
    APIFootballPaginationError,
    APIFootballResponseError,
)
from football.capture import run_capture
from football.capture.contracts import CaptureConfig
from football.capture.executor import CaptureExecutor
from football.capture.planner import CapturePlanner
from football.models import (
    CaptureRun,
    CaptureWorkItem,
    Match,
    OddsMarket,
    OddsObservation,
    OddsSnapshot,
)
from football.sync import sync_catalog_payloads, sync_fixture_payloads
from football.tasks import wake_capture_planner

from .helpers import catalog_season, competition, fixture_payload, odds_payload

pytestmark = pytest.mark.django_db

WINDOWS = [
    {
        "name": "early",
        "offset_minutes": 60,
        "before_tolerance_minutes": 5,
        "normal_tolerance_minutes": 2,
        "late_tolerance_minutes": 15,
    },
    {
        "name": "middle",
        "offset_minutes": 30,
        "before_tolerance_minutes": 5,
        "normal_tolerance_minutes": 2,
        "late_tolerance_minutes": 15,
    },
]

CAPTURE_SETTINGS = {
    "FOOTBALL_CAPTURE_WINDOWS": WINDOWS,
    "FOOTBALL_CAPTURE_HORIZON_HOURS": 72,
    "FOOTBALL_CAPTURE_MANDATORY_RESERVE": 0,
    "FOOTBALL_CAPTURE_MAX_OPERATION_PAGES": 1,
    "FOOTBALL_CAPTURE_MAX_PROVIDER_ATTEMPTS": 4,
    "FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS": 4,
    "FOOTBALL_CAPTURE_DISCOVERY_ENABLED": False,
    "FOOTBALL_CAPTURE_DISCOVERY_DAYS_AHEAD": 0,
    "FOOTBALL_CAPTURE_RESULT_REFRESH_ENABLED": True,
    "FOOTBALL_CAPTURE_RESULT_DELAY_MINUTES": 60,
    "FOOTBALL_CAPTURE_RESULT_CADENCE_MINUTES": 360,
    "API_FOOTBALL_MAX_RETRIES": 0,
}


class FakeCaptureClient:
    instances = []
    responses = {}
    error = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = 0
        self.pages = 0
        self.retries = 0
        self.daily_limit = None
        self.daily_remaining = None
        self.minute_limit = None
        self.minute_remaining = None
        self.quota_observed_at = None
        self.quota_observed_calls = 0
        self.attempt_guard = None
        self.requests = []
        self.__class__.instances.append(self)

    def get_all(self, endpoint, params=None):
        self.attempt_guard(self)
        self.calls += 1
        self.requests.append((endpoint, params or {}))
        if self.__class__.error:
            raise self.__class__.error
        self.pages += 1
        self.daily_limit = 100
        self.daily_remaining = 99
        self.quota_observed_at = timezone.now()
        self.quota_observed_calls = self.calls
        response = self.__class__.responses.get(endpoint, [])
        return response(params or {}) if callable(response) else response


@pytest.fixture(autouse=True)
def reset_capture_client():
    FakeCaptureClient.instances = []
    FakeCaptureClient.responses = {}
    FakeCaptureClient.error = None


def create_match(*, league_id, name, kickoff, status="NS"):
    tracked = competition(external_id=league_id, name=name)
    catalog_season(tracked)
    sync_catalog_payloads([], [{"id": 1, "name": "Match Winner"}])
    payload = fixture_payload(
        fixture_id=league_id * 1000 + 1,
        league_id=league_id,
        kickoff=kickoff.isoformat(),
        status_short=status,
    )
    _, accepted = sync_fixture_payloads([payload], {str(league_id): tracked})
    return next(iter(accepted.values())), payload


@override_settings(**CAPTURE_SETTINGS)
def test_dry_run_is_write_free_provider_free_and_multi_competition():
    now = timezone.now().replace(microsecond=0)
    first, _ = create_match(
        league_id=39, name="First League", kickoff=now + timedelta(hours=1)
    )
    second, _ = create_match(
        league_id=40, name="Second League", kickoff=now + timedelta(hours=1)
    )

    result = run_capture(
        at=now,
        dry_run=True,
        allow_bootstrap=True,
        client_factory=FakeCaptureClient,
    )

    assert result.status == "DRY_RUN"
    assert {item["match_id"] for item in result.plan["items"]} >= {
        first.pk,
        second.pk,
    }
    assert result.plan["due"] == 2
    assert FakeCaptureClient.instances == []
    assert CaptureRun.objects.count() == 0
    assert CaptureWorkItem.objects.count() == 0
    assert OddsObservation.objects.count() == 0


@override_settings(**CAPTURE_SETTINGS)
def test_service_rejects_naive_time_and_unknown_window_before_writes():
    now = timezone.now().replace(microsecond=0)
    create_match(league_id=39, name="League", kickoff=now + timedelta(hours=1))

    with pytest.raises(ValueError, match="timezone offset"):
        run_capture(at=now.replace(tzinfo=None), dry_run=True)
    with pytest.raises(ValueError, match="Unknown capture window"):
        run_capture(at=now, dry_run=True, window="unsupported")
    assert CaptureRun.objects.count() == 0


@override_settings(**CAPTURE_SETTINGS)
def test_same_window_executes_once_and_later_window_allows_unchanged_price():
    now = timezone.now().replace(microsecond=0)
    match, _ = create_match(
        league_id=39, name="League", kickoff=now + timedelta(hours=1)
    )
    external_id = str(39 * 1000 + 1)
    FakeCaptureClient.responses = {"odds": [odds_payload(fixture_id=int(external_id))]}

    first = run_capture(at=now, allow_bootstrap=True, client_factory=FakeCaptureClient)
    repeated = run_capture(
        at=now, allow_bootstrap=True, client_factory=FakeCaptureClient
    )
    with mock.patch(
        "football.capture.executor.timezone.now",
        return_value=now + timedelta(minutes=30),
    ):
        later = run_capture(
            at=now + timedelta(minutes=30),
            allow_bootstrap=True,
            client_factory=FakeCaptureClient,
        )

    assert first.observations_created == 1
    assert repeated.provider_attempts == 0
    assert any(
        item["status"] == CaptureWorkItem.Status.ALREADY_FULFILLED
        for item in repeated.skipped_work
    )
    assert later.observations_created == 1
    assert OddsObservation.objects.filter(match=match).count() == 2
    assert OddsSnapshot.objects.filter(match=match).count() == 1
    assert len(FakeCaptureClient.instances) == 2


@override_settings(**CAPTURE_SETTINGS)
def test_temporal_late_missed_and_kickoff_reschedule_identity():
    now = timezone.now().replace(microsecond=0)
    match, _ = create_match(
        league_id=39, name="League", kickoff=now + timedelta(minutes=57)
    )
    external_id = 39 * 1000 + 1
    FakeCaptureClient.responses = {"odds": [odds_payload(fixture_id=external_id)]}

    late = run_capture(
        at=now,
        window="early",
        allow_bootstrap=True,
        client_factory=FakeCaptureClient,
    )
    assert late.completed_work[0]["status"] == CaptureWorkItem.Status.LATE_CAPTURE
    observation = OddsObservation.objects.get(match=match)
    assert observation.observed_at.isoformat() != late.plan["items"][0]["target_at"]

    missed_match, _ = create_match(
        league_id=40, name="Missed League", kickoff=now + timedelta(minutes=44)
    )
    missed_plan = run_capture(
        at=now,
        dry_run=True,
        match_id=missed_match.pk,
        window="early",
    )
    assert missed_plan.plan["items"][0]["status"] == (
        CaptureWorkItem.Status.MISSED_WINDOW
    )

    old_identity = late.plan["items"][0]["logical_identity"]
    match.kickoff += timedelta(hours=1)
    match.save(update_fields=["kickoff", "modified"])
    rescheduled = run_capture(
        at=now + timedelta(minutes=57), dry_run=True, window="early"
    )
    assert rescheduled.plan["items"][0]["logical_identity"] != old_identity


@override_settings(
    **(
        CAPTURE_SETTINGS
        | {
            "FOOTBALL_CAPTURE_MANDATORY_RESERVE": 2,
            "FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS": 2,
        }
    )
)
def test_quota_reserve_blocks_without_provider_call():
    now = timezone.now().replace(microsecond=0)
    create_match(league_id=39, name="League", kickoff=now + timedelta(hours=1))
    CaptureRun.objects.create(
        trigger=CaptureRun.Trigger.MANUAL,
        status=CaptureRun.Status.SUCCESS,
        planning_at=now - timedelta(minutes=1),
        started_at=now - timedelta(minutes=1),
        quota_remaining_after=2,
        quota_observed_at=now - timedelta(minutes=1),
    )

    result = run_capture(at=now, client_factory=FakeCaptureClient)

    assert result.provider_attempts == 0
    assert result.skipped_work[0]["status"] == CaptureWorkItem.Status.QUOTA_RESERVE
    assert FakeCaptureClient.instances == []


@override_settings(
    **(
        CAPTURE_SETTINGS
        | {
            "FOOTBALL_CAPTURE_MAX_OPERATION_PAGES": 3,
            "FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS": 1,
            "FOOTBALL_CAPTURE_MANDATORY_RESERVE": 0,
        }
    )
)
def test_explicit_bootstrap_is_bounded_to_one_attempt():
    now = timezone.now().replace(microsecond=0)
    create_match(league_id=39, name="League", kickoff=now + timedelta(hours=1))
    FakeCaptureClient.responses = {"odds": [odds_payload(fixture_id=39001)]}

    blocked = run_capture(at=now, client_factory=FakeCaptureClient)
    executed = run_capture(
        at=now,
        allow_bootstrap=True,
        client_factory=FakeCaptureClient,
    )

    assert blocked.provider_attempts == 0
    assert blocked.skipped_work[0]["status"] == CaptureWorkItem.Status.QUOTA_RESERVE
    assert blocked.skipped_work[0]["reason"] == (
        "optional odds bootstrap requires explicit opt-in"
    )
    assert executed.provider_attempts == 1
    assert executed.quota_before["basis"] == "BOUNDED_BOOTSTRAP"


@override_settings(
    **(
        CAPTURE_SETTINGS
        | {
            "FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS": 1,
            "FOOTBALL_CAPTURE_MANDATORY_RESERVE": 0,
        }
    )
)
def test_executor_revalidates_optional_bootstrap_opt_in_under_lock():
    now = timezone.now().replace(microsecond=0)
    create_match(league_id=39, name="League", kickoff=now + timedelta(hours=1))
    config = CaptureConfig.from_settings()
    stale_plan = CapturePlanner(config=config).plan(at=now, allow_bootstrap=True)
    assert stale_plan.executable
    stale_plan.allow_bootstrap = False

    result = CaptureExecutor(client_factory=FakeCaptureClient).execute(
        stale_plan, trigger=CaptureRun.Trigger.MANUAL
    )

    assert result.provider_attempts == 0
    assert result.skipped_work[0]["status"] == CaptureWorkItem.Status.QUOTA_RESERVE
    assert result.skipped_work[0]["reason"] == (
        "optional odds bootstrap requires explicit opt-in"
    )
    assert FakeCaptureClient.instances == []


@override_settings(**CAPTURE_SETTINGS)
def test_current_utc_header_and_later_attempts_form_conservative_quota_state():
    now = timezone.now().replace(microsecond=0)
    create_match(league_id=39, name="League", kickoff=now + timedelta(hours=1))
    CaptureRun.objects.create(
        trigger=CaptureRun.Trigger.MANUAL,
        status=CaptureRun.Status.SUCCESS,
        planning_at=now - timedelta(minutes=10),
        started_at=now - timedelta(minutes=10),
        quota_limit=100,
        quota_remaining_after=20,
        quota_observed_at=now - timedelta(minutes=10),
    )
    CaptureRun.objects.create(
        trigger=CaptureRun.Trigger.MANUAL,
        status=CaptureRun.Status.FAILED,
        planning_at=now - timedelta(minutes=5),
        started_at=now - timedelta(minutes=5),
        provider_attempts=2,
    )

    current = run_capture(at=now, dry_run=True)
    after_reset = run_capture(at=now + timedelta(days=1), dry_run=True)

    assert current.quota_before["basis"] == "HEADER_CURRENT_UTC_EPOCH"
    assert current.quota_before["remaining"] == 18
    assert after_reset.quota_before["basis"] == "BOUNDED_BOOTSTRAP"


@override_settings(
    **(
        CAPTURE_SETTINGS
        | {
            "FOOTBALL_CAPTURE_MAX_OPERATION_PAGES": 3,
            "FOOTBALL_CAPTURE_MAX_PROVIDER_ATTEMPTS": 3,
        }
    )
)
def test_worst_case_admission_blocks_before_provider_call():
    now = timezone.now().replace(microsecond=0)
    create_match(league_id=39, name="League", kickoff=now + timedelta(hours=1))
    CaptureRun.objects.create(
        trigger=CaptureRun.Trigger.MANUAL,
        status=CaptureRun.Status.SUCCESS,
        planning_at=now - timedelta(minutes=1),
        started_at=now - timedelta(minutes=1),
        quota_remaining_after=2,
        quota_observed_at=now - timedelta(minutes=1),
    )

    result = run_capture(at=now, client_factory=FakeCaptureClient)

    assert result.provider_attempts == 0
    assert result.skipped_work[0]["status"] == (
        CaptureWorkItem.Status.INSUFFICIENT_WORST_CASE_BUDGET
    )


@override_settings(**CAPTURE_SETTINGS)
@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (
            APIFootballPaginationError("second page blocked"),
            CaptureWorkItem.Status.PARTIAL_PAGINATION,
        ),
        (
            APIFootballResponseError("provider failed"),
            CaptureWorkItem.Status.FAILED_PROVIDER,
        ),
    ],
)
def test_partial_or_failed_provider_never_fabricates_observation(
    error, expected_status
):
    now = timezone.now().replace(microsecond=0)
    match, _ = create_match(
        league_id=39, name="League", kickoff=now + timedelta(hours=1)
    )

    class FailingClient(FakeCaptureClient):
        def get_all(self, endpoint, params=None):
            self.attempt_guard(self)
            self.calls += 1
            self.requests.append((endpoint, params or {}))
            if isinstance(error, APIFootballPaginationError):
                self.pages += 1
            raise error

    result = run_capture(at=now, allow_bootstrap=True, client_factory=FailingClient)

    assert result.provider_attempts == 1
    assert CaptureWorkItem.objects.get(status=expected_status)
    assert not OddsObservation.objects.filter(match=match).exists()
    assert not OddsSnapshot.objects.filter(match=match).exists()


@override_settings(
    **(
        CAPTURE_SETTINGS
        | {
            "FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS": 1,
            "FOOTBALL_CAPTURE_MANDATORY_RESERVE": 0,
        }
    )
)
def test_headerless_failed_attempt_exhausts_bounded_bootstrap_for_utc_epoch():
    now = timezone.now().replace(microsecond=0)
    create_match(league_id=39, name="League", kickoff=now + timedelta(hours=1))

    class FailingClient(FakeCaptureClient):
        def get_all(self, endpoint, params=None):
            self.attempt_guard(self)
            self.calls += 1
            raise APIFootballResponseError("provider failed")

    first = run_capture(at=now, allow_bootstrap=True, client_factory=FailingClient)
    repeated = run_capture(
        at=now, allow_bootstrap=True, client_factory=FakeCaptureClient
    )

    assert first.provider_attempts == 1
    assert repeated.provider_attempts == 0
    assert repeated.quota_before["remaining"] == 0
    assert len(FakeCaptureClient.instances) == 1


@override_settings(**CAPTURE_SETTINGS)
def test_stale_concurrent_plan_is_revalidated_before_provider_call():
    now = timezone.now().replace(microsecond=0)
    match, _ = create_match(
        league_id=39, name="League", kickoff=now + timedelta(hours=1)
    )
    FakeCaptureClient.responses = {"odds": [odds_payload(fixture_id=39001)]}
    config = CaptureConfig.from_settings()
    first_plan = CapturePlanner(config=config).plan(at=now, allow_bootstrap=True)
    stale_plan = CapturePlanner(config=config).plan(at=now, allow_bootstrap=True)
    executor = CaptureExecutor(client_factory=FakeCaptureClient)

    executor.execute(first_plan, trigger=CaptureRun.Trigger.MANUAL)
    repeated = executor.execute(stale_plan, trigger=CaptureRun.Trigger.SCHEDULER)

    assert repeated.provider_attempts == 0
    assert repeated.skipped_work[0]["status"] == (
        CaptureWorkItem.Status.ALREADY_FULFILLED
    )
    assert len(FakeCaptureClient.instances) == 1
    assert OddsObservation.objects.filter(match=match).count() == 1


@override_settings(**CAPTURE_SETTINGS)
def test_kickoff_change_after_planning_forces_replan_without_provider_call():
    now = timezone.now().replace(microsecond=0)
    match, _ = create_match(
        league_id=39, name="League", kickoff=now + timedelta(hours=1)
    )
    config = CaptureConfig.from_settings()
    stale_plan = CapturePlanner(config=config).plan(at=now, allow_bootstrap=True)
    old_identity = stale_plan.items[0].logical_identity
    match.kickoff += timedelta(hours=1)
    match.save(update_fields=["kickoff", "modified"])

    result = CaptureExecutor(client_factory=FakeCaptureClient).execute(
        stale_plan, trigger=CaptureRun.Trigger.SCHEDULER
    )
    current = run_capture(at=now + timedelta(hours=1), dry_run=True, window="early")

    assert result.provider_attempts == 0
    assert result.skipped_work[0]["status"] == CaptureWorkItem.Status.NOT_DUE
    assert current.plan["items"][0]["logical_identity"] != old_identity
    assert FakeCaptureClient.instances == []


@override_settings(**CAPTURE_SETTINGS)
def test_window_expiring_after_plan_is_missed_before_provider_call():
    now = timezone.now().replace(microsecond=0)
    create_match(league_id=39, name="League", kickoff=now + timedelta(hours=1))
    config = CaptureConfig.from_settings()
    plan = CapturePlanner(config=config).plan(
        at=now, window="early", allow_bootstrap=True
    )

    with mock.patch(
        "football.capture.executor.timezone.now",
        return_value=now + timedelta(minutes=16),
    ):
        result = CaptureExecutor(client_factory=FakeCaptureClient).execute(
            plan, trigger=CaptureRun.Trigger.SCHEDULER
        )

    assert result.provider_attempts == 0
    assert result.skipped_work[0]["status"] == CaptureWorkItem.Status.MISSED_WINDOW
    assert FakeCaptureClient.instances == []


@override_settings(**CAPTURE_SETTINGS)
def test_client_configuration_failure_is_persisted_not_left_running():
    now = timezone.now().replace(microsecond=0)
    create_match(league_id=39, name="League", kickoff=now + timedelta(hours=1))

    def missing_key(**kwargs):
        del kwargs
        raise APIFootballConfigurationError("provider key is not configured")

    result = run_capture(at=now, allow_bootstrap=True, client_factory=missing_key)

    run = CaptureRun.objects.get()
    work = run.work_items.get(status=CaptureWorkItem.Status.FAILED_PROVIDER)
    assert result.status == CaptureRun.Status.FAILED
    assert run.completed_at is not None
    assert run.error_class == "APIFootballConfigurationError"
    assert work.error_message == "provider key is not configured"

    FakeCaptureClient.responses = {"odds": [odds_payload(fixture_id=39001)]}
    recovered = run_capture(
        at=now, allow_bootstrap=True, client_factory=FakeCaptureClient
    )
    assert recovered.provider_attempts == 1
    assert recovered.observations_created == 1


@override_settings(**CAPTURE_SETTINGS)
def test_first_provider_failure_halts_remaining_work_without_retry_loop():
    now = timezone.now().replace(microsecond=0)
    create_match(league_id=39, name="First", kickoff=now + timedelta(hours=1))
    create_match(league_id=40, name="Second", kickoff=now + timedelta(hours=1))

    class FailingClient(FakeCaptureClient):
        def get_all(self, endpoint, params=None):
            self.attempt_guard(self)
            self.calls += 1
            raise APIFootballResponseError("provider failed")

    result = run_capture(at=now, allow_bootstrap=True, client_factory=FailingClient)

    assert result.provider_attempts == 1
    assert (
        CaptureWorkItem.objects.filter(
            status=CaptureWorkItem.Status.PROVIDER_BACKOFF
        ).count()
        == 1
    )

    FakeCaptureClient.responses = {
        "odds": lambda params: [odds_payload(fixture_id=int(params["fixture"]))]
    }
    recovered = run_capture(
        at=now, allow_bootstrap=True, client_factory=FakeCaptureClient
    )
    assert recovered.provider_attempts == 1
    assert recovered.observations_created == 1


@override_settings(
    **(
        CAPTURE_SETTINGS
        | {
            "FOOTBALL_CAPTURE_MAX_PROVIDER_ATTEMPTS": 1,
            "FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS": 1,
            "API_FOOTBALL_MAX_RETRIES": 1,
        }
    )
)
def test_real_attempt_blocked_before_retry_backs_off_same_identity():
    now = timezone.now().replace(microsecond=0)
    match, _ = create_match(
        league_id=39, name="League", kickoff=now + timedelta(hours=1)
    )
    opener_attempts = []
    clients = []

    def timeout_opener(request, timeout):
        opener_attempts.append((request, timeout))
        raise socket.timeout()

    def client_factory(**kwargs):
        client = APIFootballClient(
            api_key="fictional-provider-secret",
            opener=timeout_opener,
            minimum_interval=0,
            **kwargs,
        )
        clients.append(client)
        return client

    first = run_capture(
        at=now,
        window="early",
        allow_bootstrap=True,
        client_factory=client_factory,
    )
    first_work = CaptureWorkItem.objects.get(run_id=first.run_id)
    repeated = run_capture(
        at=now,
        window="early",
        allow_bootstrap=True,
        client_factory=client_factory,
    )

    assert len(opener_attempts) == 1
    assert len(clients) == 1
    assert first.provider_attempts == 1
    assert first_work.actual_attempts == 1
    assert first_work.status == CaptureWorkItem.Status.PROVIDER_BACKOFF
    assert not OddsObservation.objects.filter(match=match).exists()
    assert repeated.provider_attempts == 0
    assert repeated.skipped_work[0]["status"] == (
        CaptureWorkItem.Status.PROVIDER_BACKOFF
    )


@override_settings(**CAPTURE_SETTINGS)
def test_result_refresh_reuses_canonical_sync_and_resolves_outcome():
    now = timezone.now().replace(microsecond=0)
    match, _ = create_match(
        league_id=39,
        name="League",
        kickoff=now - timedelta(hours=3),
    )
    finished = fixture_payload(
        fixture_id=39 * 1000 + 1,
        league_id=39,
        kickoff=match.kickoff.isoformat(),
        status_short="FT",
        status_long="Match Finished",
        home_score=2,
        away_score=1,
        home_winner=True,
        away_winner=False,
    )
    FakeCaptureClient.responses = {"fixtures": [finished]}

    result = run_capture(
        at=now,
        purpose=CaptureWorkItem.Purpose.RESULT_REFRESH,
        client_factory=FakeCaptureClient,
    )

    match.refresh_from_db()
    assert result.matches_resolved == 1
    assert match.outcome == Match.OUTCOME_HOME
    assert FakeCaptureClient.instances[0].requests == [
        ("fixtures", {"id": str(39 * 1000 + 1)})
    ]


@override_settings(
    **(
        CAPTURE_SETTINGS
        | {
            "FOOTBALL_CAPTURE_MANDATORY_RESERVE": 10,
            "FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS": 1,
        }
    )
)
def test_result_debt_has_priority_and_can_use_bounded_mandatory_reserve():
    now = timezone.now().replace(microsecond=0)
    past, _ = create_match(
        league_id=39,
        name="Past League",
        kickoff=now - timedelta(hours=3),
    )
    create_match(
        league_id=40,
        name="Future League",
        kickoff=now + timedelta(hours=1),
    )
    FakeCaptureClient.responses = {"fixtures": []}

    plan = run_capture(at=now, dry_run=True)
    result = run_capture(at=now, client_factory=FakeCaptureClient)

    assert plan.plan["items"][0]["purpose"] == (CaptureWorkItem.Purpose.RESULT_REFRESH)
    assert result.provider_attempts == 1
    assert FakeCaptureClient.instances[0].requests == [
        ("fixtures", {"id": str(39 * 1000 + 1)})
    ]
    assert result.completed_work[0]["match_id"] == past.pk


@override_settings(
    **(
        CAPTURE_SETTINGS
        | {
            "FOOTBALL_CAPTURE_DISCOVERY_ENABLED": True,
            "FOOTBALL_CAPTURE_DISCOVERY_CADENCE_MINUTES": 720,
            "FOOTBALL_CAPTURE_MAX_PROVIDER_ATTEMPTS": 2,
        }
    )
)
def test_result_then_due_odds_precede_discovery_under_constrained_budget():
    now = timezone.now().replace(microsecond=0)
    create_match(
        league_id=39,
        name="Past League",
        kickoff=now - timedelta(hours=3),
    )
    create_match(
        league_id=40,
        name="Future League",
        kickoff=now + timedelta(hours=1),
    )
    CaptureRun.objects.create(
        trigger=CaptureRun.Trigger.MANUAL,
        status=CaptureRun.Status.SUCCESS,
        planning_at=now - timedelta(minutes=1),
        started_at=now - timedelta(minutes=1),
        quota_remaining_after=2,
        quota_observed_at=now - timedelta(minutes=1),
    )

    plan = run_capture(at=now, dry_run=True)
    executable = [
        item
        for item in plan.plan["items"]
        if item["status"] == CaptureWorkItem.Status.PLANNED
    ]
    discovery = next(
        item
        for item in plan.plan["items"]
        if item["purpose"] == CaptureWorkItem.Purpose.FIXTURE_REFRESH
    )

    assert [item["purpose"] for item in executable] == [
        CaptureWorkItem.Purpose.RESULT_REFRESH,
        CaptureWorkItem.Purpose.ODDS_CAPTURE,
    ]
    assert discovery["status"] == CaptureWorkItem.Status.QUOTA_RESERVE


@override_settings(**CAPTURE_SETTINGS)
def test_competition_day_stratum_uses_finsport_local_calendar_day():
    planning_at = datetime(2026, 8, 28, 22, 30, tzinfo=UTC)
    tracked = competition(external_id=39, name="League")
    catalog_season(tracked)
    sync_catalog_payloads([], [{"id": 1, "name": "Match Winner"}])
    first_payload = fixture_payload(
        fixture_id=39001,
        league_id=39,
        kickoff="2026-08-28T23:30:00+00:00",
    )
    second_payload = fixture_payload(
        fixture_id=39002,
        league_id=39,
        kickoff="2026-08-29T04:30:00+00:00",
    )
    _, accepted = sync_fixture_payloads(
        [first_payload, second_payload], {"39": tracked}
    )
    first = accepted["39001"]
    second = accepted["39002"]
    market = OddsMarket.objects.get(source__code="api_football", external_id="1")
    run = CaptureRun.objects.create(
        trigger=CaptureRun.Trigger.MANUAL,
        status=CaptureRun.Status.SUCCESS,
        planning_at=planning_at,
        started_at=planning_at,
    )
    CaptureWorkItem.objects.create(
        run=run,
        purpose=CaptureWorkItem.Purpose.ODDS_CAPTURE,
        status=CaptureWorkItem.Status.SUCCESS,
        source=market.source,
        match=first,
        market=market,
        logical_identity="local-day-stratum-fixture-one",
    )

    plan = run_capture(
        at=planning_at,
        dry_run=True,
        window="early",
        allow_bootstrap=True,
    )
    items = {
        item["match_id"]: item
        for item in plan.plan["items"]
        if item["purpose"] == CaptureWorkItem.Purpose.ODDS_CAPTURE
    }
    local_timezone = ZoneInfo("America/Lima")

    assert first.kickoff.date() != second.kickoff.date()
    assert first.kickoff.astimezone(local_timezone).date() == (
        second.kickoff.astimezone(local_timezone).date()
    )
    assert items[first.pk]["priority"][2] == 1
    assert items[second.pk]["priority"][2] == 1


@override_settings(**CAPTURE_SETTINGS)
def test_terminal_no_outcome_is_explicit_and_never_polled():
    now = timezone.now().replace(microsecond=0)
    match, _ = create_match(
        league_id=39,
        name="League",
        kickoff=now - timedelta(hours=3),
    )
    match.status_short = "CANC"
    match.status_long = "Cancelled"
    match.save(update_fields=["status_short", "status_long", "modified"])

    result = run_capture(
        at=now,
        purpose=CaptureWorkItem.Purpose.RESULT_REFRESH,
        client_factory=FakeCaptureClient,
    )

    assert result.provider_attempts == 0
    assert result.skipped_work[0]["status"] == (
        CaptureWorkItem.Status.STATUS_INELIGIBLE
    )
    assert FakeCaptureClient.instances == []


@override_settings(
    **(
        CAPTURE_SETTINGS
        | {
            "FOOTBALL_CAPTURE_HORIZON_HOURS": 24,
        }
    )
)
def test_unresolved_result_debt_survives_future_capture_horizon():
    now = timezone.now().replace(microsecond=0)
    match, _ = create_match(
        league_id=39,
        name="Past League",
        kickoff=now - timedelta(hours=48),
    )

    result = run_capture(
        at=now,
        dry_run=True,
        match_id=match.pk,
        purpose=CaptureWorkItem.Purpose.RESULT_REFRESH,
    )

    assert len(result.plan["items"]) == 1
    item = result.plan["items"][0]

    assert item["match_id"] == match.pk
    assert item["purpose"] == CaptureWorkItem.Purpose.RESULT_REFRESH
    assert item["status"] == CaptureWorkItem.Status.PLANNED


@override_settings(
    **(
        CAPTURE_SETTINGS
        | {
            "FOOTBALL_CAPTURE_DISCOVERY_ENABLED": True,
            "FOOTBALL_CAPTURE_DISCOVERY_CADENCE_MINUTES": 720,
        }
    )
)
def test_fixture_discovery_is_shared_bounded_capability_not_every_wake():
    now = timezone.now().replace(microsecond=0)
    tracked = competition(external_id=39, name="League")
    catalog_season(tracked)
    payload = fixture_payload(
        fixture_id=39001,
        league_id=39,
        kickoff=(now + timedelta(days=1)).isoformat(),
    )
    FakeCaptureClient.responses = {"fixtures": [payload]}

    first = run_capture(
        at=now,
        purpose=CaptureWorkItem.Purpose.FIXTURE_REFRESH,
        client_factory=FakeCaptureClient,
    )
    repeated = run_capture(
        at=now,
        purpose=CaptureWorkItem.Purpose.FIXTURE_REFRESH,
        client_factory=FakeCaptureClient,
    )

    assert first.provider_attempts == 1
    assert first.fixtures_changed > 0
    assert repeated.provider_attempts == 0
    assert repeated.skipped_work[0]["status"] == (
        CaptureWorkItem.Status.ALREADY_FULFILLED
    )


@override_settings(**CAPTURE_SETTINGS)
def test_advisory_lock_loser_is_audited_and_makes_zero_calls():
    now = timezone.now().replace(microsecond=0)
    create_match(league_id=39, name="League", kickoff=now + timedelta(hours=1))

    @contextmanager
    def locked():
        yield False

    with mock.patch("football.capture.executor.capture_single_flight", locked):
        result = run_capture(
            at=now, allow_bootstrap=True, client_factory=FakeCaptureClient
        )

    assert result.status == CaptureRun.Status.CONCURRENT_EXECUTOR
    assert result.provider_attempts == 0
    assert CaptureWorkItem.objects.get().status == (
        CaptureWorkItem.Status.CONCURRENT_EXECUTOR
    )
    assert FakeCaptureClient.instances == []


@override_settings(FOOTBALL_CAPTURE_ENABLED=False)
def test_disabled_scheduler_wake_is_provider_free():
    result = wake_capture_planner()
    assert result == {"status": "DISABLED", "provider_attempts": 0}
    assert FakeCaptureClient.instances == []


@override_settings(FOOTBALL_CAPTURE_ENABLED=True)
def test_enabled_scheduler_wake_delegates_to_shared_service():
    capture_result = mock.Mock()
    capture_result.as_dict.return_value = {"status": "NO_WORK", "provider_attempts": 0}
    with mock.patch(
        "football.tasks.run_capture", return_value=capture_result
    ) as service:
        result = wake_capture_planner()
    service.assert_called_once_with(trigger=CaptureRun.Trigger.SCHEDULER)
    assert result == {"status": "NO_WORK", "provider_attempts": 0}


@override_settings(FOOTBALL_CAPTURE_ENABLED=True)
def test_scheduler_persists_failure_before_executor_audit_exists():
    with mock.patch(
        "football.tasks.run_capture", side_effect=ValueError("invalid capture config")
    ):
        result = wake_capture_planner()
    run = CaptureRun.objects.get()
    assert result["status"] == CaptureRun.Status.FAILED
    assert result["provider_attempts"] == 0
    assert run.error_class == "ValueError"
    assert run.error_message == "invalid capture config"


@override_settings(**CAPTURE_SETTINGS)
def test_command_dry_run_prints_structured_plan_without_writes():
    now = timezone.now().replace(microsecond=0)
    create_match(league_id=39, name="League", kickoff=now + timedelta(hours=1))
    output = StringIO()

    call_command(
        "run_football_capture",
        dry_run=True,
        at=now.isoformat(),
        stdout=output,
    )

    assert '"status": "DRY_RUN"' in output.getvalue()
    assert CaptureRun.objects.count() == 0
