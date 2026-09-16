from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import mock

import pytest
from django.test import override_settings

from football.capture.contracts import CaptureConfig
from football.maintenance import (
    _bounded_client,
    maintenance_status,
    run_catalogue_maintenance,
    run_season_maintenance,
    run_weekly_evaluation,
)
from football.models import MaintenanceRun, Match, ProviderCallAudit
from football.providers.api_football import (
    APIFootballClient,
    APIFootballOperationBudgetError,
    APIFootballQuotaReserveError,
)
from football.quota import quota_state

from .helpers import catalog_season, competition, fixture_payload, league_payload
from .prediction_helpers import create_synthetic_league, create_synthetic_odds
from .test_client import QueueOpener, Response, payload

pytestmark = pytest.mark.django_db

MAINTENANCE_SETTINGS = {
    "FOOTBALL_CAPTURE_MANDATORY_RESERVE": 0,
    "FOOTBALL_CAPTURE_DISCOVERY_ENABLED": False,
    "FOOTBALL_MAINTENANCE_BOOTSTRAP_MAX_ATTEMPTS": 3,
    "FOOTBALL_MAINTENANCE_CATALOGUE_MAX_ATTEMPTS": 2,
    "FOOTBALL_MAINTENANCE_CATALOGUE_MAX_PAGES": 1,
    "FOOTBALL_MAINTENANCE_SEASON_MAX_ATTEMPTS": 1,
    "FOOTBALL_MAINTENANCE_SEASON_MAX_PAGES": 1,
    "FOOTBALL_MAINTENANCE_DAILY_MAX_ATTEMPTS": 2,
    "FOOTBALL_MAINTENANCE_QUOTA_RETRY_HOURS": 4,
    "FOOTBALL_MAINTENANCE_MAX_SEASONS_PER_DAY": 1,
    "FOOTBALL_MAINTENANCE_WEEKLY_INTERVAL_DAYS": 7,
}


class FakeMaintenanceClient:
    instances = []
    responses = {}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = 0
        self.pages = 0
        self.retries = 0
        self.daily_limit = 100
        self.daily_remaining = 100
        self.quota_observed_at = None
        self.attempt_guard = None
        self.requests = []
        self.__class__.instances.append(self)

    def get_all(self, endpoint, params=None):
        self.attempt_guard(self)
        self.calls += 1
        self.pages += 1
        self.daily_remaining -= 1
        self.requests.append((endpoint, params or {}))
        response = self.__class__.responses.get(endpoint, [])
        return response(params or {}) if callable(response) else response


@pytest.fixture(autouse=True)
def reset_maintenance_client(monkeypatch):
    FakeMaintenanceClient.instances = []
    FakeMaintenanceClient.responses = {}
    monkeypatch.setattr("football.maintenance.emit_event", lambda **kwargs: kwargs)


@override_settings(**MAINTENANCE_SETTINGS)
def test_catalogue_runs_once_per_local_day_and_persists_audit():
    at = datetime(2026, 8, 31, 15, tzinfo=UTC)
    FakeMaintenanceClient.responses = {
        "leagues": [league_payload()],
        "odds/bets": [{"id": 1, "name": "Match Winner"}],
    }

    first = run_catalogue_maintenance(at=at, client_factory=FakeMaintenanceClient)
    second = run_catalogue_maintenance(at=at, client_factory=FakeMaintenanceClient)

    assert first["status"] == MaintenanceRun.Status.SUCCESS
    assert second == {
        "run_id": first["run_id"],
        "capability": MaintenanceRun.Capability.CATALOGUE,
        "status": "NOT_DUE",
        "due": False,
        "reason": "DAILY_IDENTITY_ALREADY_TERMINAL",
        "last_status": MaintenanceRun.Status.SUCCESS,
    }
    assert FakeMaintenanceClient.instances[0].requests == [
        ("leagues", {}),
        ("odds/bets", {}),
    ]
    assert len(FakeMaintenanceClient.instances) == 1
    run = MaintenanceRun.objects.get(pk=first["run_id"])
    assert run.provider_attempts == 2
    assert run.summary["market_id"]


@override_settings(
    **(
        MAINTENANCE_SETTINGS
        | {
            "FOOTBALL_CAPTURE_MANDATORY_RESERVE": 10,
            "FOOTBALL_MAINTENANCE_BOOTSTRAP_MAX_ATTEMPTS": 2,
            "FOOTBALL_MAINTENANCE_CATALOGUE_MAX_ATTEMPTS": 2,
        }
    )
)
def test_catalogue_bounded_bootstrap_waives_unknown_reserve():
    at = datetime(2026, 8, 31, 15, tzinfo=UTC)
    FakeMaintenanceClient.responses = {
        "leagues": [league_payload()],
        "odds/bets": [{"id": 1, "name": "Match Winner"}],
    }

    result = run_catalogue_maintenance(
        at=at,
        client_factory=FakeMaintenanceClient,
    )

    assert result["status"] == MaintenanceRun.Status.SUCCESS
    assert result["summary"]["provider_attempts"] == 2
    assert FakeMaintenanceClient.instances[0].kwargs["daily_reserve"] == 0
    assert FakeMaintenanceClient.instances[0].requests == [
        ("leagues", {}),
        ("odds/bets", {}),
    ]


def _maintenance_header(at, remaining):
    return ProviderCallAudit.objects.create(
        capability=ProviderCallAudit.Capability.OTHER_EXPLICIT_MAINTENANCE,
        logical_identity="prior-header",
        endpoint_family="fixtures",
        started_at=at - timedelta(minutes=1),
        completed_at=at - timedelta(minutes=1),
        outcome="SUCCESS",
        quota_limit=100,
        quota_remaining=remaining,
        quota_observed_at=at - timedelta(minutes=1),
    )


def _real_maintenance_client(opener):
    def factory(**kwargs):
        return APIFootballClient(
            api_key="fictional", opener=opener, minimum_interval=0, **kwargs
        )

    return factory


@pytest.mark.parametrize("component", ["fixture", "t30", "open_result"])
@override_settings(**MAINTENANCE_SETTINGS)
def test_maintenance_rechecks_each_critical_reserve_component_after_lower_header(
    component, monkeypatch
):
    at = datetime(2026, 9, 16, 18, tzinfo=UTC)
    _maintenance_header(at, 3)
    opener = QueueOpener(
        Response(
            payload([]),
            {
                "x-ratelimit-requests-limit": "100",
                "x-ratelimit-requests-remaining": "1",
            },
        ),
        Response(payload([{"id": 1, "name": "Match Winner"}])),
    )
    reserve = {"fixture": 0, "t30": 0, "open_result": 0, "total": 1}
    reserve[component] = 1
    monkeypatch.setattr("football.maintenance.dynamic_reserve", lambda *_: reserve)

    with mock.patch("football.maintenance.timezone.now", return_value=at):
        result = run_catalogue_maintenance(
            at=at, client_factory=_real_maintenance_client(opener)
        )

    assert result["status"] == MaintenanceRun.Status.SKIPPED_QUOTA
    assert len(opener.requests) == 1
    run = MaintenanceRun.objects.get(pk=result["run_id"])
    assert run.provider_attempts == 1
    audit = ProviderCallAudit.objects.get(maintenance_run=run)
    assert audit.quota_remaining == 1
    assert quota_state(at, CaptureConfig.from_settings())["remaining"] == 1


@override_settings(**MAINTENANCE_SETTINGS)
def test_maintenance_second_call_uses_post_header_surplus_and_audits_once(monkeypatch):
    at = datetime(2026, 9, 16, 18, tzinfo=UTC)
    _maintenance_header(at, 4)
    opener = QueueOpener(
        Response(
            payload([]),
            {
                "x-ratelimit-requests-limit": "100",
                "x-ratelimit-requests-remaining": "3",
            },
        ),
        Response(payload([{"id": 1, "name": "Match Winner"}])),
    )
    monkeypatch.setattr("football.maintenance.dynamic_reserve", lambda *_: {"total": 1})

    with mock.patch("football.maintenance.timezone.now", return_value=at):
        result = run_catalogue_maintenance(
            at=at, client_factory=_real_maintenance_client(opener)
        )

    assert result["status"] == MaintenanceRun.Status.SUCCESS
    assert len(opener.requests) == 2
    run = MaintenanceRun.objects.get(pk=result["run_id"])
    assert run.provider_attempts == 2
    audits = list(ProviderCallAudit.objects.filter(maintenance_run=run).order_by("id"))
    assert [row.endpoint_family for row in audits] == ["leagues", "odds/bets"]
    assert [row.quota_remaining for row in audits] == [3, None]
    assert quota_state(at, CaptureConfig.from_settings())["remaining"] == 2


@override_settings(**MAINTENANCE_SETTINGS)
def test_maintenance_attempt_bound_and_stale_header_remain_fail_closed():
    at = datetime(2026, 9, 16, 18, tzinfo=UTC)
    _maintenance_header(at, 4)
    opener = QueueOpener(
        Response(payload([], current=1, total=2)),
        Response(payload([], current=2, total=2)),
    )
    with mock.patch("football.maintenance.timezone.now", return_value=at):
        client = _bounded_client(
            _real_maintenance_client(opener),
            at=at,
            maximum_attempts=1,
            maximum_pages=2,
        )
        with pytest.raises(APIFootballOperationBudgetError):
            client.get_all("leagues")
    assert len(opener.requests) == 1
    assert ProviderCallAudit.objects.filter(logical_identity="maintenance").count() == 1

    later = at + timedelta(days=1)
    with pytest.raises(APIFootballQuotaReserveError):
        _bounded_client(
            _real_maintenance_client(QueueOpener()),
            at=later,
            maximum_attempts=1,
            maximum_pages=1,
        )


@override_settings(**MAINTENANCE_SETTINGS)
def test_daily_season_detection_bootstraps_once_and_does_not_repeat():
    at = datetime(2026, 8, 31, 15, tzinfo=UTC)
    tracked = competition()
    season = catalog_season(tracked)
    FakeMaintenanceClient.responses = {"fixtures": [fixture_payload(year=season.year)]}

    first = run_season_maintenance(at=at, client_factory=FakeMaintenanceClient)
    second = run_season_maintenance(at=at, client_factory=FakeMaintenanceClient)

    assert first["status"] == MaintenanceRun.Status.SUCCESS
    assert first["summary"]["candidate_season_ids"] == [season.pk]
    assert first["summary"]["results"][0]["status"] == (MaintenanceRun.Status.SUCCESS)
    assert second["status"] == "NOT_DUE"
    assert FakeMaintenanceClient.instances[0].requests == [
        (
            "fixtures",
            {
                "league": "39",
                "season": season.year,
                "timezone": "America/Lima",
            },
        )
    ]
    assert Match.objects.filter(season=season).exists()

    next_day = run_season_maintenance(
        at=at + timedelta(days=1), client_factory=FakeMaintenanceClient
    )
    assert next_day["status"] == MaintenanceRun.Status.NO_WORK
    assert next_day["summary"]["candidate_season_ids"] == []
    assert len(FakeMaintenanceClient.instances) == 1


@override_settings(**MAINTENANCE_SETTINGS)
def test_weekly_evaluation_is_due_once_and_skips_unchanged_evidence():
    at = datetime(2026, 8, 31, 15, tzinfo=UTC)
    competition_row, _, matches = create_synthetic_league()
    calls = []

    def fake_backtest(target_competition, season):
        calls.append((target_competition.pk, season.pk))
        return SimpleNamespace(
            pk=99,
            config={"selected_hyperparameters": {"modernized_r45": {"variant": "M0"}}},
        )

    first = run_weekly_evaluation(at=at, backtest_runner=fake_backtest)
    repeated = run_weekly_evaluation(at=at, backtest_runner=fake_backtest)
    unchanged = run_weekly_evaluation(
        at=at + timedelta(days=8), backtest_runner=fake_backtest
    )

    assert first["status"] == MaintenanceRun.Status.SUCCESS
    assert first["summary"]["experiments"][0]["competition_id"] == (competition_row.pk)
    assert repeated["status"] == "NOT_DUE"
    assert unchanged["status"] == MaintenanceRun.Status.NO_WORK
    assert unchanged["summary"]["reason"] == "NO_NEW_RESOLVED_EVIDENCE"
    assert len(calls) == 1

    status = maintenance_status(at=at + timedelta(days=8))
    assert status["weekly_evaluation"]["due"] is False
    assert status["weekly_evaluation"]["last_status"] == (MaintenanceRun.Status.NO_WORK)

    create_synthetic_odds([matches[0]])
    changed_market_evidence = run_weekly_evaluation(
        at=at + timedelta(days=16),
        backtest_runner=fake_backtest,
    )

    assert changed_market_evidence["status"] == MaintenanceRun.Status.SUCCESS
    assert (
        changed_market_evidence["summary"]["evidence_signature"][
            "odds_observation_count"
        ]
        > 0
    )
    assert len(calls) == 2
