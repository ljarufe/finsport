import io
from datetime import UTC, date, datetime, timedelta
from unittest import mock
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from football.capital.policies import (
    FIXED_FRACTION_BANKROLL,
    FLAT_UNIT,
    LEGACY_RECOVERY,
)
from football.capital.runtime import (
    build_execution_candidate,
    place_candidate,
    provision_automatic_configs,
    reconcile_execution_events,
    refresh_open_result_debt,
    run_automatic_runtime,
    settle_observation,
)
from football.capture import run_capture
from football.capture.contracts import CaptureConfig
from football.capture.planner import CapturePlanner
from football.maintenance import (
    run_catalogue_maintenance,
    run_current_season_reconciliation,
)
from football.models import (
    CapitalExecutionState,
    CapitalPosition,
    CapitalRuntimeConfig,
    CaptureRun,
    CaptureWorkItem,
    Competition,
    CompetitionSourceRef,
    Decision,
    MaintenanceRun,
    Match,
    OddsObservation,
    PipelineRun,
    Prediction,
    PredictionExperiment,
    ProviderCallAudit,
    ReconciliationStatus,
    Season,
)
from football.pipeline import run_pipeline
from football.providers.api_football import (
    APIFootballClient,
    APIFootballRateLimitError,
)
from football.quota import (
    DIRECTED_RESULT_FALLBACK,
    dynamic_reserve,
    quota_state,
    quota_summary,
)
from football.sync import _fixture_outcome

from . import test_capital_runtime_v2 as capital_test
from .test_capital_runtime_v2 import (
    add_api_football_ref,
    make_capture,
    make_manual_config,
    make_match,
    observe_terminal_result,
)
from .test_capture import CAPTURE_SETTINGS, FakeCaptureClient
from .test_client import QueueOpener, Response, payload

pytestmark = pytest.mark.django_db


@pytest.fixture
def runtime_graph():
    return capital_test.runtime_graph.__wrapped__()


FS017_CAPTURE_SETTINGS = CAPTURE_SETTINGS | {
    "FOOTBALL_CAPTURE_DISCOVERY_ENABLED": True,
    "FOOTBALL_CAPTURE_DISCOVERY_DAYS_AHEAD": 1,
    "FOOTBALL_CAPTURE_RESULT_DELAY_MINUTES": 130,
    "FOOTBALL_CAPTURE_RESULT_CADENCE_MINUTES": 30,
}


@override_settings(**FS017_CAPTURE_SETTINGS)
def test_fixture_horizon_covers_today_tomorrow_and_is_persistently_idempotent():
    at = datetime(2026, 9, 16, 4, 55, tzinfo=UTC)  # 23:55 Lima
    FakeCaptureClient.responses = {"fixtures": []}

    with mock.patch("football.capture.executor.timezone.now", return_value=at):
        first = run_capture(
            at=at,
            purpose=CaptureWorkItem.Purpose.FIXTURE_REFRESH,
            client_factory=FakeCaptureClient,
        )
    with mock.patch(
        "football.capture.executor.timezone.now", return_value=at + timedelta(minutes=4)
    ):
        repeated = run_capture(
            at=at + timedelta(minutes=4),
            purpose=CaptureWorkItem.Purpose.FIXTURE_REFRESH,
            client_factory=FakeCaptureClient,
        )

    assert first.provider_attempts == 2
    assert {item[1]["date"] for item in FakeCaptureClient.instances[0].requests} == {
        "2026-09-15",
        "2026-09-16",
    }
    assert repeated.provider_attempts == 0


@override_settings(**FS017_CAPTURE_SETTINGS)
def test_integrated_empty_wake_has_no_duplicate_durable_capture_delta(runtime_graph):
    del runtime_graph
    at = timezone.now().replace(microsecond=0)
    ProviderCallAudit.objects.create(
        capability=ProviderCallAudit.Capability.OTHER_EXPLICIT_MAINTENANCE,
        logical_identity="empty-wake-seed-header",
        endpoint_family="fixtures",
        started_at=at - timedelta(seconds=1),
        completed_at=at - timedelta(seconds=1),
        outcome="SUCCESS",
        quota_limit=100,
        quota_remaining=90,
        quota_observed_at=at - timedelta(seconds=1),
    )
    opener = QueueOpener(
        Response(payload(), {"x-ratelimit-requests-remaining": "89"}),
        Response(payload(), {"x-ratelimit-requests-remaining": "88"}),
    )

    def client_factory(**kwargs):
        return APIFootballClient(
            api_key="fictional", opener=opener, minimum_interval=0, **kwargs
        )

    discovery = run_capture(
        at=at,
        purpose=CaptureWorkItem.Purpose.FIXTURE_REFRESH,
        client_factory=client_factory,
    )
    assert discovery.provider_attempts == 2
    assert len(discovery.completed_work) == 2
    assert CaptureWorkItem.objects.filter(run_id=discovery.run_id).count() == 2
    provision_automatic_configs()

    models = (
        CaptureRun,
        CaptureWorkItem,
        ProviderCallAudit,
        Match,
        OddsObservation,
        PredictionExperiment,
        Prediction,
        Decision,
        CapitalRuntimeConfig,
        CapitalExecutionState,
        CapitalPosition,
    )
    before = {model: model.objects.count() for model in models}
    with (
        mock.patch(
            "football.providers.api_football.APIFootballClient.get_page",
            side_effect=AssertionError("empty wake attempted provider HTTP"),
        ) as provider_page,
        mock.patch(
            "football.pipeline.service.predict_competition_day",
            side_effect=AssertionError("empty wake invoked heavy model work"),
        ) as predictor,
    ):
        result = run_pipeline(at=at + timedelta(minutes=1))

    assert result.status == PipelineRun.Status.NO_WORK
    assert provider_page.call_count == 0
    assert predictor.call_count == 0
    assert {model: model.objects.count() - before[model] for model in models} == {
        model: 0 for model in models
    }


@override_settings(**FS017_CAPTURE_SETTINGS)
def test_dynamic_reserve_protects_due_t30_from_optional_t60(runtime_graph):
    at = datetime(2026, 9, 14, 14, 30, tzinfo=UTC)
    match, _, _ = make_match(runtime_graph, 0, at=at)
    runtime_graph["season"].coverage = {"odds": True}
    runtime_graph["season"].save(update_fields=["coverage", "modified"])
    add_api_football_ref(runtime_graph, match)
    ProviderCallAudit.objects.create(
        capability=ProviderCallAudit.Capability.ODDS_T60,
        logical_identity="header-authority",
        endpoint_family="odds",
        started_at=at - timedelta(minutes=1),
        completed_at=at - timedelta(minutes=1),
        outcome="SUCCESS",
        quota_limit=100,
        quota_remaining=1,
        quota_observed_at=at - timedelta(minutes=1),
    )

    plan = CapturePlanner(config=CaptureConfig.from_settings()).plan(at=at)
    assert match.pk in plan.reserve["t30_match_ids"]
    assert plan.reserve["t30"] == 1
    assert any(
        item.intended_window != "market-t30m"
        and item.status == CaptureWorkItem.Status.QUOTA_RESERVE
        for item in plan.items
    )


@pytest.mark.parametrize(
    ("case", "expected_status"),
    [
        ("no_coverage", CaptureWorkItem.Status.ODDS_NOT_COVERED),
        ("no_ref", CaptureWorkItem.Status.UNRESOLVED_IDENTITY),
        ("unresolved_ref", CaptureWorkItem.Status.UNRESOLVED_IDENTITY),
        ("no_market", CaptureWorkItem.Status.UNRESOLVED_IDENTITY),
        ("eligible", CaptureWorkItem.Status.PLANNED),
    ],
)
@override_settings(FOOTBALL_CAPTURE_DISCOVERY_ENABLED=False)
def test_t30_reserve_and_planner_share_provider_prerequisites(
    runtime_graph, case, expected_status
):
    at = datetime(2026, 9, 14, 14, 30, tzinfo=UTC)
    match, _, _ = make_match(runtime_graph, 0, at=at)
    if case != "no_coverage":
        runtime_graph["season"].coverage = {"odds": True}
        runtime_graph["season"].save(update_fields=["coverage", "modified"])
    if case not in {"no_coverage", "no_ref"}:
        ref = add_api_football_ref(runtime_graph, match)
        if case == "unresolved_ref":
            ref.reconciliation_status = ReconciliationStatus.PENDING
            ref.save(update_fields=["reconciliation_status"])
    if case == "no_market":
        runtime_graph["market"].name = "Unsupported Market"
        runtime_graph["market"].save(update_fields=["name", "modified"])

    config = CaptureConfig.from_settings()
    reserve = dynamic_reserve(at, config)
    plan = CapturePlanner(config=config).plan(
        at=at,
        match_id=match.pk,
        purpose=CaptureWorkItem.Purpose.ODDS_CAPTURE,
        window="market-t30m",
        allow_bootstrap=True,
    )

    assert reserve["t30"] == int(case == "eligible")
    assert plan.reserve["t30"] == reserve["t30"]
    assert len(plan.items) == 1
    assert plan.items[0].status == expected_status


@override_settings(FOOTBALL_CAPTURE_DISCOVERY_ENABLED=False)
def test_t30_reserve_keeps_fulfilled_and_expired_temporal_rules(runtime_graph):
    at = datetime(2026, 9, 14, 14, 30, tzinfo=UTC)
    match, _, _ = make_match(runtime_graph, 0, at=at)
    runtime_graph["season"].coverage = {"odds": True}
    runtime_graph["season"].save(update_fields=["coverage", "modified"])
    add_api_football_ref(runtime_graph, match)
    config = CaptureConfig.from_settings()

    assert dynamic_reserve(at, config)["t30"] == 1
    assert dynamic_reserve(at + timedelta(minutes=14), config)["t30"] == 1
    assert dynamic_reserve(at + timedelta(minutes=16), config)["t30"] == 0

    make_capture(runtime_graph, [match], at=at)
    assert dynamic_reserve(at, config)["t30"] == 0


@override_settings(FOOTBALL_CAPTURE_DISCOVERY_ENABLED=False)
def test_open_reserve_counts_effective_wake_opportunities_not_only_dates(
    runtime_graph,
):
    at = datetime(2026, 9, 14, 18, tzinfo=UTC)
    first, _, _ = make_match(runtime_graph, 0, at=at - timedelta(hours=3))
    second, _, _ = make_match(runtime_graph, 1, at=at - timedelta(hours=3))
    _, work = make_capture(runtime_graph, [first, second], at=at - timedelta(hours=3))
    config = make_manual_config(
        policy_code=FLAT_UNIT, policy_config={"unit": "1"}, max_lanes=2
    )
    for item in work:
        place_candidate(config.pk, build_execution_candidate(item))
    positions = {
        row.match_id: row for row in CapitalPosition.objects.filter(config=config)
    }
    CapitalPosition.objects.filter(pk=positions[first.pk].pk).update(
        next_result_check_at=at + timedelta(minutes=11)
    )
    CapitalPosition.objects.filter(pk=positions[second.pk].pk).update(
        next_result_check_at=at + timedelta(minutes=12)
    )
    config_snapshot = CaptureConfig.from_settings()
    same_wake = dynamic_reserve(at, config_snapshot)
    assert same_wake["open_result"] == 1
    assert same_wake["open_result_sweep_opportunities"] == [
        {"date": "2026-09-14", "wake_at": "2026-09-14T18:15:00+00:00"}
    ]

    CapitalPosition.objects.filter(pk=positions[second.pk].pk).update(
        next_result_check_at=at + timedelta(minutes=90)
    )
    staggered = dynamic_reserve(at, config_snapshot)
    assert staggered["open_result"] == 2
    assert len(staggered["open_result_sweep_opportunities"]) == 2
    assert len(quota_summary(at=at)["backlog"]["open_result_sweep_opportunities"]) == 2

    CapitalPosition.objects.filter(pk=positions[second.pk].pk).update(
        result_refresh_error=DIRECTED_RESULT_FALLBACK
    )
    known_fallback = dynamic_reserve(at, config_snapshot)
    assert known_fallback["open_result"] == 2
    assert known_fallback["open_result_fallback_match_ids"] == [second.pk]
    assert len(known_fallback["open_result_sweep_opportunities"]) == 1


@override_settings(FOOTBALL_CAPTURE_DISCOVERY_ENABLED=False)
def test_open_result_opportunity_reserve_respects_utc_epoch_wake_boundary(
    runtime_graph,
):
    at = datetime(2026, 9, 14, 23, 50, tzinfo=UTC)
    match, _, _ = make_match(runtime_graph, 0, at=at - timedelta(hours=3))
    _, work = make_capture(runtime_graph, [match], at=at - timedelta(hours=3))
    config = make_manual_config(
        policy_code=FLAT_UNIT, policy_config={"unit": "1"}, max_lanes=1
    )
    place_candidate(config.pk, build_execution_candidate(work[0]))
    position = CapitalPosition.objects.get(config=config, match=match)
    position.next_result_check_at = at + timedelta(minutes=4)
    position.save(update_fields=["next_result_check_at"])
    assert dynamic_reserve(at, CaptureConfig.from_settings())["open_result"] == 1

    position.next_result_check_at = at + timedelta(minutes=8)
    position.save(update_fields=["next_result_check_at"])
    assert dynamic_reserve(at, CaptureConfig.from_settings())["open_result"] == 0


def test_provider_attempt_audit_and_429_has_no_immediate_retry():
    error = HTTPError(
        "https://provider.test/fixtures",
        429,
        "rate limited",
        {"Retry-After": "60", "x-ratelimit-requests-remaining": "3"},
        io.BytesIO(b"{}"),
    )
    client = APIFootballClient(
        api_key="fictional",
        opener=QueueOpener(error),
        minimum_interval=0,
        max_retries=1,
    )
    client.set_audit_context(
        ProviderCallAudit.Capability.OPEN_RESULT_BATCH,
        "open:date:one",
        request_metadata={"api_key": "fictional-secret", "reason": "due result"},
        represented_fixture_count=2,
    )

    with pytest.raises(APIFootballRateLimitError):
        client.get_all("fixtures", {"date": "2026-09-14", "timezone": "America/Lima"})

    audit = ProviderCallAudit.objects.get()
    assert client.calls == 1
    assert audit.capability == ProviderCallAudit.Capability.OPEN_RESULT_BATCH
    assert audit.fixture_count == 2
    assert audit.request_metadata["api_key"] == "<redacted>"
    assert audit.retry_number == 0
    assert audit.outcome == "RATE_LIMITED"


def test_old_header_does_not_synthesize_quota_reset(settings):
    settings.FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS = 1
    observed = datetime(2026, 9, 14, 23, 55, tzinfo=UTC)
    ProviderCallAudit.objects.create(
        capability=ProviderCallAudit.Capability.ODDS_T30,
        logical_identity="old-epoch",
        endpoint_family="odds",
        quota_limit=100,
        quota_remaining=7,
        quota_observed_at=observed,
        completed_at=observed,
        outcome="SUCCESS",
    )

    state = quota_state(observed + timedelta(minutes=10), CaptureConfig.from_settings())

    assert state["basis"] == "HEADER_STALE_EPOCH"
    assert state["remaining"] == 7


def test_legacy_header_counts_audited_and_unaudited_attempts_once():
    at = datetime(2026, 9, 14, 18, tzinfo=UTC)
    header = CaptureRun.objects.create(
        trigger=CaptureRun.Trigger.SCHEDULER,
        planning_at=at,
        started_at=at,
        quota_limit=100,
        quota_remaining_after=8,
        quota_observed_at=at,
    )
    audited_run = CaptureRun.objects.create(
        trigger=CaptureRun.Trigger.SCHEDULER,
        planning_at=at + timedelta(minutes=1),
        started_at=at + timedelta(minutes=1),
        provider_attempts=1,
    )
    ProviderCallAudit.objects.create(
        capability=ProviderCallAudit.Capability.ODDS_T30,
        logical_identity="audited-headerless-run",
        endpoint_family="odds",
        capture_run=audited_run,
        started_at=at + timedelta(minutes=1),
        completed_at=at + timedelta(minutes=1),
        outcome="SUCCESS",
    )
    config = CaptureConfig.from_settings()
    after_audited = quota_state(at + timedelta(minutes=2), config)
    legacy_run = MaintenanceRun.objects.create(
        capability=MaintenanceRun.Capability.CATALOGUE,
        logical_identity="old-headerless-maintenance",
        period_start=at.date(),
        started_at=at + timedelta(minutes=3),
        last_attempt_at=at + timedelta(minutes=3),
        provider_attempts=2,
    )
    after_legacy = quota_state(at + timedelta(minutes=4), config)

    assert header.quota_remaining_after == 8
    assert audited_run.provider_attempts == 1
    assert legacy_run.provider_attempts == 2
    assert after_audited["remaining"] == 7
    assert after_legacy["remaining"] == 5


def test_bounded_bootstrap_counts_audited_run_summary_once(settings):
    settings.FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS = 3
    at = datetime(2026, 9, 14, 18, tzinfo=UTC)
    run = CaptureRun.objects.create(
        trigger=CaptureRun.Trigger.SCHEDULER,
        planning_at=at,
        started_at=at,
        provider_attempts=1,
    )
    ProviderCallAudit.objects.create(
        capability=ProviderCallAudit.Capability.DAILY_FIXTURE_DISCOVERY,
        logical_identity="bootstrap-audited",
        endpoint_family="fixtures",
        capture_run=run,
        started_at=at,
        completed_at=at,
        outcome="SUCCESS",
    )

    state = quota_state(at + timedelta(minutes=1), CaptureConfig.from_settings())

    assert state["basis"] == "BOUNDED_BOOTSTRAP"
    assert state["remaining"] == 2


@override_settings(**FS017_CAPTURE_SETTINGS)
def test_first_due_critical_call_establishes_new_epoch_without_probe(runtime_graph):
    del runtime_graph
    observed = datetime(2026, 9, 14, 23, 55, tzinfo=UTC)
    at = observed + timedelta(minutes=10)
    ProviderCallAudit.objects.create(
        capability=ProviderCallAudit.Capability.ODDS_T30,
        logical_identity="exhausted-old-epoch",
        endpoint_family="odds",
        quota_limit=100,
        quota_remaining=0,
        quota_observed_at=observed,
        completed_at=observed,
        outcome="SUCCESS",
    )

    plan = CapturePlanner(config=CaptureConfig.from_settings()).plan(
        at=at,
        purpose=CaptureWorkItem.Purpose.FIXTURE_REFRESH,
    )
    admitted = [item for item in plan.items if item.status == "PLANNED"]

    assert plan.quota.basis == "HEADER_STALE_EPOCH"
    assert plan.quota.remaining == 0
    assert plan.quota.stale_establishing_attempt_available is True
    assert len(admitted) == 1
    assert admitted[0].purpose == CaptureWorkItem.Purpose.FIXTURE_REFRESH

    opener = QueueOpener(
        Response(
            payload(),
            {
                "x-ratelimit-requests-limit": "100",
                "x-ratelimit-requests-remaining": "99",
            },
        )
    )
    client = APIFootballClient(
        api_key="fictional",
        opener=opener,
        minimum_interval=0,
        max_retries=1,
    )
    client.set_audit_context(
        ProviderCallAudit.Capability.DAILY_FIXTURE_DISCOVERY,
        admitted[0].logical_identity,
    )
    with mock.patch("football.providers.api_football.timezone.now", return_value=at):
        client.get_all("fixtures", admitted[0].params)

    current = quota_state(at, CaptureConfig.from_settings())
    assert len(opener.requests) == 1
    assert current["basis"] == "HEADER_CURRENT_UTC_EPOCH"
    assert current["remaining"] == 99
    assert current["stale_establishing_attempt_available"] is False


@override_settings(**FS017_CAPTURE_SETTINGS)
def test_headerless_stale_capture_attempt_blocks_later_capture_and_open(
    runtime_graph, settings
):
    observed = datetime(2026, 9, 14, 23, 55, tzinfo=UTC)
    at = observed + timedelta(minutes=10)
    settings.FOOTBALL_CAPTURE_DISCOVERY_DAYS_AHEAD = 1
    runtime_graph["season"].coverage = {"odds": True}
    runtime_graph["season"].save(update_fields=["coverage", "modified"])
    base_at = observed - timedelta(hours=4)
    open_match, _, _ = make_match(runtime_graph, 0, at=base_at)
    _, open_work = make_capture(runtime_graph, [open_match], at=base_at)
    config = make_manual_config(
        policy_code=FLAT_UNIT, policy_config={"unit": "1"}, max_lanes=1
    )
    place_candidate(config.pk, build_execution_candidate(open_work[0]), at=base_at)
    add_api_football_ref(runtime_graph, open_match)
    optional_match, _, _ = make_match(runtime_graph, 1, at=at - timedelta(minutes=1))
    add_api_football_ref(runtime_graph, optional_match)
    ProviderCallAudit.objects.create(
        capability=ProviderCallAudit.Capability.ODDS_T30,
        logical_identity="prior-exhausted-header",
        endpoint_family="odds",
        started_at=observed,
        completed_at=observed,
        quota_limit=100,
        quota_remaining=0,
        quota_observed_at=observed,
        outcome="SUCCESS",
    )
    opener = QueueOpener(Response(payload(), {}))

    def client_factory(**kwargs):
        return APIFootballClient(
            api_key="fictional", opener=opener, minimum_interval=0, **kwargs
        )

    before_capture_open = refresh_open_result_debt(
        at=at,
        client_factory=lambda **kwargs: pytest.fail(
            "OPEN must wait for stale-epoch fixture priority"
        ),
    )
    with mock.patch("football.capture.executor.timezone.now", return_value=at):
        first = run_capture(
            at=at,
            purpose=CaptureWorkItem.Purpose.FIXTURE_REFRESH,
            client_factory=client_factory,
        )

    headerless = ProviderCallAudit.objects.filter(
        capability=ProviderCallAudit.Capability.DAILY_FIXTURE_DISCOVERY
    ).get()
    later_at = at + timedelta(minutes=5)
    state = quota_state(later_at, CaptureConfig.from_settings())
    later_fixture = CapturePlanner(config=CaptureConfig.from_settings()).plan(
        at=later_at, purpose=CaptureWorkItem.Purpose.FIXTURE_REFRESH
    )
    later_optional = CapturePlanner(config=CaptureConfig.from_settings()).plan(
        at=later_at,
        match_id=optional_match.pk,
        purpose=CaptureWorkItem.Purpose.ODDS_CAPTURE,
        window="market-t60m",
    )
    later_open = refresh_open_result_debt(
        at=later_at,
        client_factory=lambda **kwargs: pytest.fail("OPEN must not construct a client"),
    )
    later_maintenance = run_catalogue_maintenance(
        at=later_at,
        client_factory=lambda **kwargs: pytest.fail(
            "optional maintenance must not construct a client"
        ),
    )

    assert before_capture_open.provider_calls == 0
    assert first.provider_attempts == 1
    assert len(opener.requests) == 1
    assert headerless.quota_remaining is None
    assert headerless.quota_observed_at is None
    assert state["basis"] == "HEADER_STALE_EPOCH"
    assert state["stale_establishing_attempt_available"] is False
    assert not later_fixture.executable
    assert any(
        item.intended_window == "market-t60m"
        and item.status == CaptureWorkItem.Status.QUOTA_RESERVE
        for item in later_optional.items
    ), [
        (item.intended_window, item.status, item.reason)
        for item in later_optional.items
    ]
    assert later_open.provider_calls == 0
    assert later_maintenance["status"] == MaintenanceRun.Status.SKIPPED_QUOTA

    current_at = later_at + timedelta(minutes=5)
    ProviderCallAudit.objects.create(
        capability=ProviderCallAudit.Capability.OTHER_EXPLICIT_MAINTENANCE,
        logical_identity="later-observed-header",
        endpoint_family="fixtures",
        started_at=current_at,
        completed_at=current_at,
        quota_limit=100,
        quota_remaining=20,
        quota_observed_at=current_at,
        outcome="SUCCESS",
    )
    current = quota_state(current_at, CaptureConfig.from_settings())
    resumed = CapturePlanner(config=CaptureConfig.from_settings()).plan(
        at=current_at, purpose=CaptureWorkItem.Purpose.FIXTURE_REFRESH
    )
    assert current["basis"] == "HEADER_CURRENT_UTC_EPOCH"
    assert current["remaining"] == 20
    assert len(resumed.executable) == 1


def test_pending_capacity_uses_frozen_basis_and_actual_placement_state(runtime_graph):
    at = datetime(2026, 9, 14, 15, tzinfo=UTC)
    first, _, _ = make_match(runtime_graph, 0, at=at)
    pending, _, _ = make_match(runtime_graph, 1, at=at + timedelta(minutes=10))
    _, first_work = make_capture(runtime_graph, [first], at=at)
    _, pending_work = make_capture(
        runtime_graph, [pending], at=at + timedelta(minutes=10)
    )
    config = make_manual_config(
        policy_code=FIXED_FRACTION_BANKROLL,
        policy_config={"fraction": "0.05"},
        max_lanes=1,
    )

    assert (
        place_candidate(
            config.pk,
            build_execution_candidate(first_work[0]),
            at=at + timedelta(minutes=5),
        )
        == "PLACED"
    )
    assert (
        place_candidate(
            config.pk,
            build_execution_candidate(pending_work[0]),
            at=at + timedelta(minutes=16),
        )
        == "PENDING_CAPACITY"
    )
    state = CapitalExecutionState.objects.get(config=config, match=pending)
    frozen_basis_id = state.execution_basis_id
    assert not CapitalPosition.objects.filter(config=config, match=pending).exists()

    add_api_football_ref(runtime_graph, first)
    first.status_short = "FT"
    first.outcome = "HOME"
    first.save()
    observation, _ = observe_terminal_result(first, known_at=at + timedelta(minutes=17))
    settle_observation(observation, settled_at=at + timedelta(minutes=17))
    config.refresh_from_db()
    equity_at_placement = config.bankroll_equity

    placed_at = at + timedelta(minutes=18)
    assert (
        place_candidate(
            config.pk,
            build_execution_candidate(pending_work[0]),
            at=placed_at,
        )
        == "PLACED"
    )
    position = CapitalPosition.objects.get(config=config, match=pending)
    state.refresh_from_db()
    assert state.execution_basis_id == frozen_basis_id
    assert position.placed_at == placed_at
    assert float(position.applied_stake) == pytest.approx(
        float(equity_at_placement) * 0.05
    )
    assert position.execution_basis.evidence_not_before < position.placed_at


def test_pending_capacity_recomputes_sequential_recovery_state(runtime_graph):
    at = datetime(2026, 9, 14, 15, tzinfo=UTC)
    first, _, _ = make_match(runtime_graph, 0, at=at)
    pending, _, _ = make_match(runtime_graph, 1, at=at + timedelta(minutes=10))
    _, first_work = make_capture(runtime_graph, [first], at=at)
    _, pending_work = make_capture(
        runtime_graph, [pending], at=at + timedelta(minutes=10)
    )
    config = make_manual_config(
        policy_code=LEGACY_RECOVERY,
        policy_config={"initial_stake": "1"},
        policy_state={"target_profit": None, "accumulated_loss": "0", "step": 0},
        max_lanes=1,
    )

    place_candidate(config.pk, build_execution_candidate(first_work[0]), at=at)
    assert (
        place_candidate(
            config.pk,
            build_execution_candidate(pending_work[0]),
            at=at + timedelta(minutes=16),
        )
        == "PENDING_CAPACITY"
    )

    add_api_football_ref(runtime_graph, first)
    first.status_short = "FT"
    first.outcome = "AWAY"
    first.save(update_fields=["status_short", "outcome", "modified"])
    observation, _ = observe_terminal_result(first, known_at=at + timedelta(minutes=17))
    settle_observation(observation, settled_at=at + timedelta(minutes=17))

    assert (
        place_candidate(
            config.pk,
            build_execution_candidate(pending_work[0]),
            at=at + timedelta(minutes=18),
        )
        == "PLACED"
    )
    position = CapitalPosition.objects.get(config=config, match=pending)
    assert position.requested_stake == 2
    assert position.policy_state_before["step"] == 1


def test_pending_expires_at_kickoff(runtime_graph):
    at = datetime(2026, 9, 14, 15, tzinfo=UTC)
    first, _, _ = make_match(runtime_graph, 0, at=at)
    pending, _, _ = make_match(runtime_graph, 1, at=at)
    _, first_work = make_capture(runtime_graph, [first], at=at)
    _, pending_work = make_capture(runtime_graph, [pending], at=at)
    config = make_manual_config(
        policy_code=FLAT_UNIT, policy_config={"unit": "1"}, max_lanes=1
    )
    place_candidate(config.pk, build_execution_candidate(first_work[0]), at=at)
    place_candidate(config.pk, build_execution_candidate(pending_work[0]), at=at)

    outcome = place_candidate(
        config.pk,
        build_execution_candidate(pending_work[0]),
        at=pending.kickoff,
    )

    state = CapitalExecutionState.objects.get(config=config, match=pending)
    assert outcome == "NOT_PLACED"
    assert state.non_placement_reason == "EXPIRED_CAPACITY"
    assert not CapitalPosition.objects.filter(config=config, match=pending).exists()


def test_existing_pending_terminalizes_when_config_is_inactive(runtime_graph):
    at = datetime(2026, 9, 14, 15, tzinfo=UTC)
    first, _, _ = make_match(runtime_graph, 0, at=at)
    pending, _, _ = make_match(runtime_graph, 1, at=at)
    _, first_work = make_capture(runtime_graph, [first], at=at)
    _, pending_work = make_capture(runtime_graph, [pending], at=at)
    config = make_manual_config(
        policy_code=FLAT_UNIT, policy_config={"unit": "1"}, max_lanes=1
    )
    place_candidate(config.pk, build_execution_candidate(first_work[0]), at=at)
    assert (
        place_candidate(config.pk, build_execution_candidate(pending_work[0]), at=at)
        == "PENDING_CAPACITY"
    )
    state = CapitalExecutionState.objects.get(config=config, match=pending)
    state_id, basis_id = state.pk, state.execution_basis_id
    config.refresh_from_db()
    exposure_before = config.reserved_exposure
    config.status = CapitalRuntimeConfig.Status.TERMINATED
    config.save(update_fields=["status", "modified"])

    result = place_candidate(
        config.pk,
        build_execution_candidate(pending_work[0]),
        at=at + timedelta(minutes=1),
    )

    state.refresh_from_db()
    config.refresh_from_db()
    assert result == "NOT_PLACED"
    assert state.pk == state_id
    assert state.execution_basis_id == basis_id
    assert state.status == CapitalExecutionState.Status.NOT_PLACED
    assert state.non_placement_reason == "INELIGIBLE"
    assert state.terminal_at == at + timedelta(minutes=1)
    assert (
        CapitalExecutionState.objects.filter(config=config, match=pending).count() == 1
    )
    assert not CapitalPosition.objects.filter(config=config, match=pending).exists()
    assert config.reserved_exposure == exposure_before


def test_same_wake_settlement_releases_lane_for_pending(runtime_graph):
    at = datetime(2026, 9, 14, 15, tzinfo=UTC)
    first, _, _ = make_match(runtime_graph, 0, at=at)
    pending, _, _ = make_match(runtime_graph, 1, at=at)
    pending.kickoff = first.kickoff + timedelta(hours=3)
    pending.save(update_fields=["kickoff", "modified"])
    run, _ = make_capture(runtime_graph, [first, pending], at=at)
    initial = reconcile_execution_events(run.pk)
    assert initial.pending_capacity == 3
    add_api_football_ref(runtime_graph, first)
    first.status_short = "FT"
    first.outcome = "HOME"
    first.save()

    result = run_automatic_runtime(at=first.kickoff + timedelta(minutes=130))

    assert result.settled == 7
    assert result.placed == 3
    assert not CapitalExecutionState.objects.filter(
        match=pending,
        status=CapitalExecutionState.Status.PENDING_CAPACITY,
    ).exists()


@override_settings(FOOTBALL_CAPTURE_DISCOVERY_ENABLED=False)
def test_date_sweep_settlement_releases_pending_capacity_same_wake(
    runtime_graph, monkeypatch
):
    at = datetime(2026, 9, 14, 15, tzinfo=UTC)
    first, _, _ = make_match(runtime_graph, 0, at=at)
    pending, _, _ = make_match(runtime_graph, 1, at=at)
    pending.kickoff = first.kickoff + timedelta(hours=3)
    pending.save(update_fields=["kickoff", "modified"])
    run, _ = make_capture(runtime_graph, [first, pending], at=at)
    assert reconcile_execution_events(run.pk).pending_capacity == 3
    add_api_football_ref(runtime_graph, first, external_id="8300")
    CompetitionSourceRef.objects.create(
        source=runtime_graph["source"],
        competition=runtime_graph["competition"],
        external_id="99",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )

    class FakeClient:
        def __init__(self, **kwargs):
            del kwargs
            self.calls = 0

        def get_all(self, endpoint, params):
            assert (endpoint, params) == (
                "fixtures",
                {"date": "2026-09-14", "timezone": "America/Lima"},
            )
            self.calls += 1
            return [{"fixture": {"id": 8300}}]

    def sync_stub(items, competitions):
        assert [item["fixture"]["id"] for item in items] == [8300]
        assert set(competitions) == {"99"}
        Match.objects.filter(pk=first.pk).update(status_short="FT", outcome="HOME")
        return None, {"8300": first}

    monkeypatch.setattr("football.capital.runtime.sync_fixture_payloads", sync_stub)
    result = run_automatic_runtime(
        at=first.kickoff + timedelta(minutes=130), client_factory=FakeClient
    )
    assert result.provider_calls == 1
    assert result.settled == 7
    assert result.placed == 3
    assert not CapitalExecutionState.objects.filter(
        match=pending,
        status=CapitalExecutionState.Status.PENDING_CAPACITY,
    ).exists()


@pytest.mark.parametrize(
    ("provider_status", "retry_minutes"),
    [("1H", 30), ("FT", 30), ("SUSP", 60), ("PST", None)],
)
@override_settings(FOOTBALL_CAPTURE_DISCOVERY_ENABLED=False)
def test_open_result_t130_and_status_aware_retry(
    runtime_graph, monkeypatch, provider_status, retry_minutes
):
    at = datetime(2026, 9, 14, 15, tzinfo=UTC)
    match, _, _ = make_match(runtime_graph, 0, at=at)
    _, work = make_capture(runtime_graph, [match], at=at)
    config = make_manual_config(
        policy_code=FLAT_UNIT,
        policy_config={"unit": "1"},
        max_lanes=2,
    )
    place_candidate(config.pk, build_execution_candidate(work[0]), at=at)
    due_at = match.kickoff + timedelta(minutes=130)
    add_api_football_ref(runtime_graph, match, external_id="8001")
    CompetitionSourceRef.objects.create(
        source=runtime_graph["source"],
        competition=runtime_graph["competition"],
        external_id="99",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )

    class FakeClient:
        instances = []

        def __init__(self, **kwargs):
            del kwargs
            self.calls = 0
            self.daily_remaining = None
            self.attempt_guard = None
            self.__class__.instances.append(self)

        def get_all(self, endpoint, params):
            self.attempt_guard(self)
            self.calls += 1
            assert endpoint == "fixtures"
            assert params in (
                {"date": "2026-09-14", "timezone": "America/Lima"},
                {"id": "8001"},
            )
            return [{"fixture": {"id": 8001}}]

    def sync_stub(payloads, competitions):
        del payloads, competitions
        match.status_short = provider_status
        match.outcome = ""
        match.save(update_fields=["status_short", "outcome", "modified"])
        return None, {"8001": match}

    monkeypatch.setattr("football.capital.runtime.sync_fixture_payloads", sync_stub)

    before = refresh_open_result_debt(
        at=due_at - timedelta(seconds=1), client_factory=FakeClient
    )
    due = refresh_open_result_debt(at=due_at, client_factory=FakeClient)

    assert before.provider_calls == 0
    assert due.provider_calls == 1
    position = CapitalPosition.objects.get(config=config, match=match)
    if retry_minutes is None:
        assert position.next_result_check_at is None
        assert position.result_refresh_error == "WAITING_FOR_FIXTURE_RECONCILIATION"
    elif provider_status == "FT":
        assert position.next_result_check_at == due_at
        assert position.result_refresh_error.startswith(
            "DATE_SWEEP_EXPECTED_FIXTURE_MISSING"
        )
    else:
        assert position.next_result_check_at == due_at + timedelta(
            minutes=retry_minutes
        )


@pytest.mark.parametrize("incidental_status", ["FT", "1H"])
@override_settings(FOOTBALL_CAPTURE_DISCOVERY_ENABLED=False)
def test_date_sweep_filters_and_coalesces_incidental_open_debt(
    runtime_graph, monkeypatch, incidental_status
):
    at = datetime(2026, 9, 14, 20, tzinfo=UTC)
    first, _, _ = make_match(runtime_graph, 0)
    second, _, _ = make_match(runtime_graph, 1)
    _, work = make_capture(runtime_graph, [first, second])
    config = make_manual_config(
        policy_code=FLAT_UNIT, policy_config={"unit": "1"}, max_lanes=2
    )
    for item in work:
        place_candidate(config.pk, build_execution_candidate(item))
    for match, kickoff, next_check, external_id in (
        (first, at - timedelta(hours=3), at - timedelta(minutes=50), "8100"),
        (second, at - timedelta(hours=2), at + timedelta(minutes=10), "8101"),
    ):
        match.kickoff = kickoff
        match.save(update_fields=["kickoff", "modified"])
        CapitalPosition.objects.filter(config=config, match=match).update(
            next_result_check_at=next_check
        )
        add_api_football_ref(runtime_graph, match, external_id=external_id)
    CompetitionSourceRef.objects.create(
        source=runtime_graph["source"],
        competition=runtime_graph["competition"],
        external_id="99",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    before = dynamic_reserve(at, CaptureConfig.from_settings())
    assert before["open_result"] == 2

    opener = QueueOpener(
        Response(
            payload(
                [
                    {"fixture": {"id": 8100}},
                    {"fixture": {"id": 8101}},
                    {"fixture": {"id": 999999}},
                ]
            ),
            {},
        )
    )

    def client_factory(**kwargs):
        return APIFootballClient(
            api_key="fictional", opener=opener, minimum_interval=0, **kwargs
        )

    def sync_stub(items, competitions):
        assert set(competitions) == {"99"}
        assert {item["fixture"]["id"] for item in items} == {8100, 8101}
        Match.objects.filter(pk=first.pk).update(status_short="FT", outcome="HOME")
        Match.objects.filter(pk=second.pk).update(
            status_short=incidental_status,
            outcome="HOME" if incidental_status == "FT" else "",
        )
        return None, {"8100": first, "8101": second}

    monkeypatch.setattr("football.capital.runtime.sync_fixture_payloads", sync_stub)
    result = refresh_open_result_debt(at=at, client_factory=client_factory)
    assert result.provider_calls == 1
    assert not result.errors
    assert [
        parse_qs(urlsplit(request.full_url).query) for request, _ in opener.requests
    ] == [{"date": ["2026-09-14"], "timezone": ["America/Lima"]}]
    audit = ProviderCallAudit.objects.get(
        capability=ProviderCallAudit.Capability.OPEN_RESULT_BATCH
    )
    assert audit.fixture_count == 2
    assert audit.request_metadata["relevant_fixture_ids"] == ["8100", "8101"]
    second_position = CapitalPosition.objects.get(config=config, match=second)
    if incidental_status == "FT":
        assert result.settled == 2
        assert result.open_debt == 0
        assert second_position.status != CapitalPosition.Status.OPEN
        assert dynamic_reserve(at, CaptureConfig.from_settings())["open_result"] == 0
        assert quota_summary(at=at)["backlog"]["open_result_fixtures"] == 0
        later = refresh_open_result_debt(
            at=at + timedelta(minutes=10),
            client_factory=lambda **kwargs: pytest.fail("resolved debt was polled"),
        )
        assert later.provider_calls == 0
    else:
        assert result.settled == 1
        assert second_position.status == CapitalPosition.Status.OPEN
        assert second_position.next_result_check_at == at + timedelta(minutes=10)
        assert dynamic_reserve(at, CaptureConfig.from_settings())["open_result"] == 1


@override_settings(FOOTBALL_CAPTURE_DISCOVERY_ENABLED=False)
def test_missing_due_fixture_uses_one_audited_directed_id_fallback(
    runtime_graph, monkeypatch
):
    at = datetime(2026, 9, 14, 20, tzinfo=UTC)
    match, _, _ = make_match(runtime_graph, 0)
    _, work = make_capture(runtime_graph, [match])
    config = make_manual_config(
        policy_code=FLAT_UNIT, policy_config={"unit": "1"}, max_lanes=1
    )
    place_candidate(config.pk, build_execution_candidate(work[0]))
    match.kickoff = at - timedelta(hours=3)
    match.save(update_fields=["kickoff", "modified"])
    CapitalPosition.objects.filter(config=config, match=match).update(
        next_result_check_at=at
    )
    add_api_football_ref(runtime_graph, match, external_id="8200")
    CompetitionSourceRef.objects.create(
        source=runtime_graph["source"],
        competition=runtime_graph["competition"],
        external_id="99",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    ProviderCallAudit.objects.create(
        capability=ProviderCallAudit.Capability.ODDS_T30,
        logical_identity="fallback-header",
        endpoint_family="odds",
        started_at=at - timedelta(minutes=1),
        completed_at=at - timedelta(minutes=1),
        outcome="SUCCESS",
        quota_limit=100,
        quota_remaining=5,
        quota_observed_at=at - timedelta(minutes=1),
    )
    opener = QueueOpener(
        Response(payload([{"fixture": {"id": 999999}}]), {}),
        Response(
            payload([{"fixture": {"id": 8200}}]),
            {"x-ratelimit-requests-remaining": "3"},
        ),
    )

    def client_factory(**kwargs):
        return APIFootballClient(
            api_key="fictional", opener=opener, minimum_interval=0, **kwargs
        )

    def sync_stub(items, competitions):
        assert [item["fixture"]["id"] for item in items] == [8200]
        assert set(competitions) == {"99"}
        Match.objects.filter(pk=match.pk).update(status_short="FT", outcome="HOME")
        return None, {"8200": match}

    monkeypatch.setattr("football.capital.runtime.sync_fixture_payloads", sync_stub)
    result = refresh_open_result_debt(at=at, client_factory=client_factory)
    assert result.provider_calls == 2
    assert result.settled == 1
    assert result.open_debt == 0
    queries = [
        parse_qs(urlsplit(request.full_url).query) for request, _ in opener.requests
    ]
    assert queries == [
        {"date": ["2026-09-14"], "timezone": ["America/Lima"]},
        {"id": ["8200"]},
    ]
    audits = list(
        ProviderCallAudit.objects.filter(
            capability=ProviderCallAudit.Capability.OPEN_RESULT_BATCH
        ).order_by("id")
    )
    assert [row.request_metadata["acquisition"] for row in audits] == [
        "date_sweep",
        "directed_id_fallback",
    ]
    assert [row.outcome for row in audits] == ["SUCCESS", "SUCCESS"]
    assert [row.fixture_count for row in audits] == [1, 1]
    assert audits[1].quota_remaining == 3


@pytest.mark.parametrize(
    ("higher_priority", "remaining", "expected_batches"),
    [(0, 2, 2), (1, 3, 2), (1, 2, 1)],
)
def test_open_batch_consumes_its_full_reserve_after_higher_priority(
    runtime_graph, settings, monkeypatch, higher_priority, remaining, expected_batches
):
    base_at = datetime(2026, 9, 14, 15, tzinfo=UTC)
    due_at = base_at + timedelta(hours=4)
    settings.FOOTBALL_CAPTURE_DISCOVERY_ENABLED = bool(higher_priority)
    settings.FOOTBALL_CAPTURE_DISCOVERY_DAYS_AHEAD = 0
    settings.FOOTBALL_CAPTURE_MAX_PROVIDER_ATTEMPTS = 4
    config = make_manual_config(
        policy_code=FLAT_UNIT,
        policy_config={"unit": "1"},
        max_lanes=40,
    )
    for index in range(2):
        match, _, _ = make_match(
            runtime_graph, index % 4, at=base_at + timedelta(seconds=index)
        )
        _, work = make_capture(runtime_graph, [match], at=base_at)
        place_candidate(config.pk, build_execution_candidate(work[0]), at=base_at)
        add_api_football_ref(runtime_graph, match, external_id=str(8000 + index))
        match.kickoff = due_at - timedelta(days=index + 1)
        match.save(update_fields=["kickoff", "modified"])
        CapitalPosition.objects.filter(config=config, match=match).update(
            next_result_check_at=due_at
        )
    CompetitionSourceRef.objects.create(
        source=runtime_graph["source"],
        competition=runtime_graph["competition"],
        external_id="99",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    ProviderCallAudit.objects.create(
        capability=ProviderCallAudit.Capability.ODDS_T30,
        logical_identity="quota-for-open-batches",
        endpoint_family="odds",
        started_at=due_at - timedelta(minutes=1),
        completed_at=due_at - timedelta(minutes=1),
        outcome="SUCCESS",
        quota_limit=100,
        quota_remaining=remaining,
        quota_observed_at=due_at - timedelta(minutes=1),
    )
    reserve = dynamic_reserve(due_at, CaptureConfig.from_settings())
    requests = []

    class FakeClient:
        def __init__(self, **kwargs):
            del kwargs
            self.calls = 0
            self.daily_remaining = remaining
            self.attempt_guard = None

        def get_all(self, endpoint, params):
            self.attempt_guard(self)
            self.calls += 1
            self.daily_remaining -= 1
            requests.append((endpoint, params))
            return [
                {"fixture": {"id": 8000 if params["date"] == "2026-09-13" else 8001}}
            ]

    monkeypatch.setattr(
        "football.capital.runtime.sync_fixture_payloads",
        lambda payloads, competitions: (
            None,
            {
                str(item["fixture"]["id"]): Match.objects.get(
                    source_refs__external_id=str(item["fixture"]["id"])
                )
                for item in payloads
            },
        ),
    )
    result = refresh_open_result_debt(at=due_at, client_factory=FakeClient)

    assert reserve["fixture"] + reserve["t30"] == higher_priority
    assert reserve["open_result"] == 2
    assert result.provider_calls == expected_batches
    assert len(requests) == expected_batches
    assert all(
        endpoint == "fixtures"
        and params.get("timezone") == "America/Lima"
        and "ids" not in params
        for endpoint, params in requests
    )
    assert len({params["date"] for _, params in requests}) == expected_batches


@pytest.mark.parametrize(
    "response_pattern", ["normal", "first_retry", "after_header_retry"]
)
def test_headerless_open_attempts_preserve_higher_priority_reserve(
    runtime_graph, settings, response_pattern
):
    base_at = datetime(2026, 9, 14, 15, tzinfo=UTC)
    due_at = base_at + timedelta(hours=4)
    settings.FOOTBALL_CAPTURE_DISCOVERY_ENABLED = True
    settings.FOOTBALL_CAPTURE_DISCOVERY_DAYS_AHEAD = 0
    settings.FOOTBALL_CAPTURE_MAX_PROVIDER_ATTEMPTS = 4
    settings.API_FOOTBALL_MAX_RETRIES = 1
    config = make_manual_config(
        policy_code=FLAT_UNIT, policy_config={"unit": "1"}, max_lanes=40
    )
    for index in range(2):
        match, _, _ = make_match(
            runtime_graph, index % 4, at=base_at + timedelta(seconds=index)
        )
        _, work = make_capture(runtime_graph, [match], at=base_at)
        place_candidate(config.pk, build_execution_candidate(work[0]), at=base_at)
        add_api_football_ref(runtime_graph, match, external_id=str(9000 + index))
        match.kickoff = due_at - timedelta(days=index + 1)
        match.save(update_fields=["kickoff", "modified"])
        CapitalPosition.objects.filter(config=config, match=match).update(
            next_result_check_at=due_at
        )
    CompetitionSourceRef.objects.create(
        source=runtime_graph["source"],
        competition=runtime_graph["competition"],
        external_id="99",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    ProviderCallAudit.objects.create(
        capability=ProviderCallAudit.Capability.ODDS_T30,
        logical_identity="quota-for-headerless-open",
        endpoint_family="odds",
        started_at=due_at - timedelta(minutes=1),
        completed_at=due_at - timedelta(minutes=1),
        outcome="SUCCESS",
        quota_limit=100,
        quota_remaining=3,
        quota_observed_at=due_at - timedelta(minutes=1),
    )
    responses = [
        Response(payload([{"fixture": {"id": 9001}}]), {}),
        Response(payload([{"fixture": {"id": 9000}}]), {}),
    ]
    if response_pattern == "first_retry":
        responses.insert(
            0,
            HTTPError(
                "https://provider.test/fixtures",
                500,
                "transient",
                {},
                io.BytesIO(b"{}"),
            ),
        )
    elif response_pattern == "after_header_retry":
        responses = [
            Response(
                payload([{"fixture": {"id": 9001}}]),
                {"x-ratelimit-requests-remaining": "2"},
            ),
            HTTPError(
                "https://provider.test/fixtures",
                500,
                "transient",
                {},
                io.BytesIO(b"{}"),
            ),
        ]
    opener = QueueOpener(*responses)

    def client_factory(**kwargs):
        return APIFootballClient(
            api_key="fictional", opener=opener, minimum_interval=0, **kwargs
        )

    def sync_stub(items, competitions):
        del competitions
        return None, {
            str(item["fixture"]["id"]): Match.objects.get(
                source_refs__external_id=str(item["fixture"]["id"])
            )
            for item in items
        }

    with (
        mock.patch("football.capital.runtime.timezone.now", return_value=due_at),
        mock.patch(
            "football.capital.runtime.sync_fixture_payloads", side_effect=sync_stub
        ),
    ):
        result = refresh_open_result_debt(at=due_at, client_factory=client_factory)

    audits = list(
        ProviderCallAudit.objects.filter(
            capability=ProviderCallAudit.Capability.OPEN_RESULT_BATCH
        ).order_by("id")
    )
    state = quota_state(due_at, CaptureConfig.from_settings())
    assert dynamic_reserve(due_at, CaptureConfig.from_settings())["fixture"] == 1
    assert len(opener.requests) == 2
    assert result.provider_calls == 2
    assert len(audits) == 2
    assert state["remaining"] == 1
    if response_pattern == "first_retry":
        assert all(audit.quota_remaining is None for audit in audits)
        assert [audit.outcome for audit in audits] == ["TRANSIENT_RETRY", "SUCCESS"]
        assert audits[1].retry_number == 1
        assert result.errors
    elif response_pattern == "after_header_retry":
        assert audits[0].quota_remaining == 2
        assert audits[1].quota_remaining is None
        assert [audit.outcome for audit in audits] == ["SUCCESS", "TRANSIENT_RETRY"]
        assert result.errors
    else:
        assert all(audit.quota_remaining is None for audit in audits)
        assert [audit.outcome for audit in audits] == ["SUCCESS", "SUCCESS"]
        assert not result.errors


def test_pst_open_debt_moves_between_result_and_fixture_reserve(
    runtime_graph, settings
):
    settings.FOOTBALL_CAPTURE_DISCOVERY_ENABLED = True
    settings.FOOTBALL_CAPTURE_DISCOVERY_DAYS_AHEAD = 0
    at = datetime(2026, 9, 14, 15, tzinfo=UTC)
    match, _, _ = make_match(runtime_graph, 0, at=at)
    _, work = make_capture(runtime_graph, [match], at=at)
    config = make_manual_config(
        policy_code=FLAT_UNIT, policy_config={"unit": "1"}, max_lanes=1
    )
    place_candidate(config.pk, build_execution_candidate(work[0]), at=at)
    add_api_football_ref(runtime_graph, match)
    due_at = match.kickoff + timedelta(minutes=130)
    capture_config = CaptureConfig.from_settings()
    ordinary = dynamic_reserve(due_at, capture_config)

    match.status_short = "PST"
    match.save(update_fields=["status_short", "modified"])
    postponed = dynamic_reserve(due_at, capture_config)

    match.status_short = "1H"
    match.save(update_fields=["status_short", "modified"])
    resumed = dynamic_reserve(due_at, capture_config)

    assert (ordinary["fixture"], ordinary["open_result"]) == (1, 1)
    assert (postponed["fixture"], postponed["open_result"]) == (2, 0)
    assert (resumed["fixture"], resumed["open_result"]) == (1, 1)


@pytest.mark.parametrize(
    ("status", "fulltime", "goals", "expected"),
    [
        ("FT", (2, 1), (2, 1), "HOME"),
        ("AET", (1, 1), (2, 1), "DRAW"),
        ("PEN", (0, 0), (5, 4), "DRAW"),
        ("ET", (1, 1), (2, 1), "DRAW"),
        ("P", (1, 1), (4, 3), "DRAW"),
        ("AET", (None, None), (2, 1), ""),
    ],
)
def test_regulation_outcome_uses_fulltime_score(status, fulltime, goals, expected):
    item = {
        "score": {"fulltime": {"home": fulltime[0], "away": fulltime[1]}},
        "goals": {"home": goals[0], "away": goals[1]},
        "teams": {"home": {"winner": True}, "away": {"winner": False}},
    }
    assert _fixture_outcome(item, status) == expected


def test_current_season_cycle_is_due_once_and_api_football_free():
    competition = Competition.objects.create(
        name="Current League", competition_type="League", country="PE", enabled=True
    )
    season = Season.objects.create(
        competition=competition,
        year=2026,
        is_current=True,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    calls = []

    def runner(received_competition, received_season, *, apply):
        calls.append((received_competition.pk, received_season.pk, apply))
        return {
            "competition_id": received_competition.pk,
            "season_id": received_season.pk,
            "source_file_checksum": "same",
            "counts": {"PRESERVE_EXISTING_RESULT": 1},
        }

    at = datetime(2026, 9, 17, 11, 30, tzinfo=UTC)  # Thu 06:30 Lima
    first = run_current_season_reconciliation(at=at, runner=runner)
    repeated = run_current_season_reconciliation(at=at, runner=runner)

    assert first["status"] == MaintenanceRun.Status.NO_WORK
    assert repeated["status"] == "NOT_DUE"
    assert calls == [(competition.pk, season.pk, True)]
    assert ProviderCallAudit.objects.count() == 0


def test_quota_summary_and_command_are_provider_free(capsys):
    at = datetime(2026, 9, 15, 18, tzinfo=UTC)
    ProviderCallAudit.objects.create(
        capability=ProviderCallAudit.Capability.ODDS_T30,
        logical_identity="summary",
        endpoint_family="odds",
        quota_limit=100,
        quota_remaining=90,
        quota_observed_at=at,
        completed_at=at,
        outcome="SUCCESS",
    )
    before = ProviderCallAudit.objects.count()

    summary = quota_summary(at=at)
    call_command("football_quota_summary", at=at.isoformat())

    assert summary["quota"]["remaining"] == 90
    assert set(summary["reserve"]) == {
        "fixture",
        "t30",
        "open_result",
        "execution_quote",
        "total",
    }
    assert ProviderCallAudit.objects.count() == before
    assert "usage_by_capability" in capsys.readouterr().out
