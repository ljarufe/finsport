import json
import logging
import sys
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from types import SimpleNamespace
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone

from football.api_football import APIFootballClient, APIFootballResponseError
from football.management.commands.observe_pipeline import Command as WatchdogCommand
from football.models import (
    Competition,
    CompetitionSourceRef,
    Match,
    MatchSourceRef,
    PipelineRun,
    ReconciliationStatus,
    Season,
    Source,
    Team,
    TeamSourceRef,
)
from football.observability import events
from football.observability.liveness import evaluate_liveness
from football.observability.pipeline import emit_pipeline_terminal, exception_diagnostic
from football.observability.reconciliation import emit_reconciliation_pending
from football.observability.runtime import OperationalErrorHandler
from football.pipeline.contracts import PhaseResult, PhaseState
from football.pipeline.service import _phase_status
from football.tasks import wake_pipeline

pytestmark = pytest.mark.django_db


def pipeline_run(*, status, trigger, completed_at):
    return PipelineRun.objects.create(
        trigger=trigger,
        status=status,
        planning_at=completed_at,
        local_day=completed_at.date(),
        completed_at=completed_at,
    )


def base_event(**overrides):
    values = {
        "event_code": "TEST_FAILED",
        "severity": "ERROR",
        "component": "test",
        "operation": "exercise_contract",
        "outcome": "FAILED",
        "failure_kind": "test_failure",
        "human_summary": "Controlled failure.",
    }
    values.update(overrides)
    return events.build_event(**values)


def test_event_contract_is_bounded_allowlisted_and_valid_json():
    event = base_event(
        human_summary="s" * 5000,
        pipeline_run_id="run-123",
        task_id="task-456",
        traceback_text="trace" * 10000,
        context={
            "json_path": "$.response" * 500,
            "diagnostic_excerpt": "x" * 5000,
            "not_allowed": "must disappear",
        },
    )
    serialized = json.dumps(event)

    assert len(event["human_summary"]) == events.SUMMARY_LIMIT
    assert len(event.get("stacktrace", "")) <= events.TRACEBACK_LIMIT
    assert "not_allowed" not in event.get("context", {})
    assert event["pipeline_run_id"] == "run-123"
    assert event["task_id"] == "task-456"
    assert len(serialized.encode()) <= events.EVENT_SIZE_LIMIT
    assert json.loads(serialized)["schema"] == "finsport.observability.v1"


@pytest.mark.parametrize(
    "key",
    [
        "authorization",
        "cookie",
        "api_key",
        "apikey",
        "token",
        "access_token",
        "password",
        "passwd",
        "secret",
        "database_url",
        "dsn",
    ],
)
def test_secret_canary_is_absent_from_all_supported_fields(monkeypatch, key):
    canary = f"canary-{key}-value"
    monkeypatch.setenv(key.upper(), canary)
    error = RuntimeError(f"{key}={canary}")
    try:
        raise error
    except RuntimeError as captured:
        event = base_event(
            human_summary=f"failure {key}={canary}",
            exception=captured,
            context={
                "diagnostic_excerpt": f"https://example.test/?{key}={canary}",
                key: canary,
            },
        )

    serialized = json.dumps(event)
    assert canary not in serialized
    assert key not in event.get("context", {})
    assert "[REDACTED]" in serialized


def test_incident_fingerprint_is_stable_and_excludes_occurrence_ids():
    first = base_event(pipeline_run_id="1", task_id="a")
    second = base_event(pipeline_run_id="2", task_id="b")
    changed = base_event(operation="different_operation")

    assert first["incident_fingerprint"] == second["incident_fingerprint"]
    assert first["incident_fingerprint"] != changed["incident_fingerprint"]


def test_redaction_handles_headers_quoted_values_and_secret_urls():
    canary = "opaque-canary-not-in-settings"
    text = (
        f"Authorization: Bearer {canary}\n"
        f"Cookie: session={canary}; preference=x\n"
        f'{{"api_key": "{canary} with spaces"}}\n'
        f"https://example.test/path?token={canary}&safe=1"
    )

    sanitized = events.sanitize_text(text, 4096)

    assert canary not in sanitized
    assert "with spaces" not in sanitized
    assert sanitized.count("[REDACTED]") >= 4


def test_event_spool_rotates_at_a_bounded_size(tmp_path, settings, monkeypatch):
    settings.OBSERVABILITY_EVENTS_ENABLED = True
    settings.OBSERVABILITY_EVENT_DIR = str(tmp_path)
    monkeypatch.setattr(events, "EVENT_FILE_SIZE_LIMIT", 800)
    monkeypatch.setattr(events, "EVENT_FILE_BACKUPS", 2)

    for index in range(12):
        events.emit_event(
            **{
                "event_code": "ROTATION_TEST",
                "severity": "INFO",
                "component": "test",
                "operation": "rotate",
                "outcome": "SUCCESS",
                "human_summary": f"event {index} " + "x" * 200,
            }
        )

    files = list(tmp_path.glob("django-web.jsonl*"))
    data_files = [path for path in files if not path.name.endswith(".lock")]
    assert len(data_files) <= 3
    assert all(path.stat().st_size <= 800 for path in data_files)
    for path in data_files:
        for line in path.read_text().splitlines():
            assert json.loads(line)["event_code"] == "ROTATION_TEST"


@pytest.mark.parametrize(
    "status",
    [
        PipelineRun.Status.SUCCESS,
        PipelineRun.Status.DEGRADED,
        PipelineRun.Status.FAILED,
        PipelineRun.Status.NO_WORK,
    ],
)
def test_scheduler_terminal_statuses_all_suppress_overdue(status):
    now = timezone.now()
    pipeline_run(
        status=status,
        trigger=PipelineRun.Trigger.SCHEDULER,
        completed_at=now - timedelta(seconds=1799),
    )
    state = evaluate_liveness(
        now=now,
        enabled=True,
        cadence_seconds=900,
        grace_seconds=900,
        monitoring_since=now - timedelta(days=1),
    )

    assert state.overdue is False
    assert state.last_scheduler_activity.status == status
    if status == PipelineRun.Status.NO_WORK:
        assert state.last_attempted is None
    else:
        assert state.last_attempted.status == status


@pytest.mark.parametrize(
    "status",
    [
        PipelineRun.Status.SUCCESS,
        PipelineRun.Status.DEGRADED,
        PipelineRun.Status.FAILED,
        PipelineRun.Status.NO_WORK,
    ],
)
def test_historical_scheduler_activity_does_not_precede_new_monitoring_episode(status):
    now = timezone.now()
    historical = pipeline_run(
        status=status,
        trigger=PipelineRun.Trigger.SCHEDULER,
        completed_at=now - timedelta(days=3),
    )

    state = evaluate_liveness(
        now=now,
        enabled=True,
        cadence_seconds=900,
        grace_seconds=900,
        monitoring_since=now,
    )

    assert state.overdue is False
    assert state.reference_at == now
    assert state.last_scheduler_activity == historical


def test_scheduler_activity_after_enablement_becomes_liveness_reference():
    monitoring_since = timezone.now() - timedelta(minutes=10)
    activity_at = monitoring_since + timedelta(minutes=2)
    activity = pipeline_run(
        status=PipelineRun.Status.SUCCESS,
        trigger=PipelineRun.Trigger.SCHEDULER,
        completed_at=activity_at,
    )

    state = evaluate_liveness(
        now=activity_at + timedelta(seconds=1800),
        enabled=True,
        cadence_seconds=900,
        grace_seconds=900,
        monitoring_since=monitoring_since,
    )

    assert state.overdue is False
    assert state.reference_at == activity_at
    assert state.last_scheduler_activity == activity


def test_new_monitoring_episode_uses_threshold_when_scheduler_history_is_older():
    monitoring_since = timezone.now() - timedelta(hours=1)
    pipeline_run(
        status=PipelineRun.Status.SUCCESS,
        trigger=PipelineRun.Trigger.SCHEDULER,
        completed_at=monitoring_since - timedelta(days=3),
    )

    exact_boundary = evaluate_liveness(
        now=monitoring_since + timedelta(seconds=1800),
        enabled=True,
        cadence_seconds=900,
        grace_seconds=900,
        monitoring_since=monitoring_since,
    )
    overdue = evaluate_liveness(
        now=monitoring_since + timedelta(seconds=1801),
        enabled=True,
        cadence_seconds=900,
        grace_seconds=900,
        monitoring_since=monitoring_since,
    )

    assert exact_boundary.overdue is False
    assert exact_boundary.reference_at == monitoring_since
    assert overdue.overdue is True
    assert overdue.reference_at == monitoring_since


def test_liveness_boundary_disabled_and_manual_run_semantics():
    now = timezone.now()
    monitoring_since = now - timedelta(seconds=1801)
    manual = pipeline_run(
        status=PipelineRun.Status.SUCCESS,
        trigger=PipelineRun.Trigger.MANUAL,
        completed_at=now,
    )
    disabled = evaluate_liveness(
        now=now,
        enabled=False,
        cadence_seconds=900,
        grace_seconds=900,
        monitoring_since=monitoring_since,
    )
    exact_boundary = evaluate_liveness(
        now=now,
        enabled=True,
        cadence_seconds=900,
        grace_seconds=900,
        monitoring_since=now - timedelta(seconds=1800),
    )
    overdue = evaluate_liveness(
        now=now,
        enabled=True,
        cadence_seconds=900,
        grace_seconds=900,
        monitoring_since=monitoring_since,
    )

    assert disabled.overdue is False
    assert exact_boundary.overdue is False
    assert overdue.overdue is True
    assert overdue.last_attempted == manual
    assert overdue.last_scheduler_activity is None
    assert overdue.threshold_seconds == 1800


@pytest.mark.parametrize(
    ("status", "event_code", "severity"),
    [
        (PipelineRun.Status.SUCCESS, "PIPELINE_SUCCEEDED", "INFO"),
        (PipelineRun.Status.DEGRADED, "PIPELINE_DEGRADED", "WARNING"),
        (PipelineRun.Status.FAILED, "PIPELINE_FAILED", "ERROR"),
    ],
)
def test_pipeline_terminal_status_emits_exactly_one_event(status, event_code, severity):
    run = SimpleNamespace(
        status=status,
        pk=7,
        capture_run_ids=[],
        prediction_experiment_ids=[],
        capital_experiment_ids=[],
    )
    with mock.patch("football.observability.pipeline.emit_event") as emitter:
        emit_pipeline_terminal(run)

    emitter.assert_called_once()
    assert emitter.call_args.kwargs["event_code"] == event_code
    assert emitter.call_args.kwargs["severity"] == severity


def test_no_work_skipped_and_unavailable_create_no_false_incident():
    phases = {
        "CAPTURE": PhaseResult(PhaseState.SKIPPED),
        "PREDICTION": PhaseResult(PhaseState.UNAVAILABLE),
        "RESULT_SETTLEMENT": PhaseResult(PhaseState.NO_WORK),
        "CAPITAL": PhaseResult(PhaseState.UNAVAILABLE),
    }
    status = _phase_status(phases)
    run = SimpleNamespace(
        status=status,
        pk=8,
        capture_run_ids=[],
        prediction_experiment_ids=[],
        capital_experiment_ids=[],
    )
    with mock.patch("football.observability.pipeline.emit_event") as emitter:
        result = emit_pipeline_terminal(run)

    assert status == PipelineRun.Status.NO_WORK
    assert result is None
    emitter.assert_not_called()


def test_unexpected_exception_has_one_sanitized_traceback(monkeypatch):
    canary = "exception-secret-canary"
    monkeypatch.setenv("ACCESS_TOKEN", canary)
    try:
        raise RuntimeError(f"access_token={canary}")
    except RuntimeError as error:
        cause = exception_diagnostic(error)
    run = SimpleNamespace(
        status=PipelineRun.Status.FAILED,
        pk=9,
        capture_run_ids=[],
        prediction_experiment_ids=[],
        capital_experiment_ids=[],
    )

    with mock.patch(
        "football.observability.pipeline.emit_event", wraps=events.emit_event
    ) as emitter:
        event = emit_pipeline_terminal(run, causes=[cause])

    emitter.assert_called_once()
    assert event["stacktrace"].count("Traceback (most recent call last)") == 1
    assert canary not in json.dumps(event)


class ProviderResponse:
    status = 200
    headers = {"content-type": "application/json", "x-request-id": "request-7"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"unexpected":{"private_payload":"must-not-be-copied"}}'


def test_http_200_provider_schema_drift_has_safe_shape_metadata_only():
    client = APIFootballClient(
        api_key="fictional",
        opener=lambda request, timeout: ProviderResponse(),
        minimum_interval=0,
        max_retries=0,
    )
    with pytest.raises(APIFootballResponseError) as captured:
        client.get_page("fixtures")

    error = captured.value
    assert error.failure_kind == "provider_schema_drift"
    assert error.diagnostic_context == {
        "endpoint_family": "fixtures",
        "http_status": 200,
        "content_type": "application/json",
        "response_size": 55,
        "provider_request_id": "request-7",
        "expected_category": "object with response array",
        "actual_category": "dict",
        "json_path": "$.response",
        "top_level_keys": ["unexpected"],
    }
    assert "must-not-be-copied" not in json.dumps(error.diagnostic_context)
    run = SimpleNamespace(
        status=PipelineRun.Status.FAILED,
        pk=12,
        capture_run_ids=[],
        prediction_experiment_ids=[],
        capital_experiment_ids=[],
    )
    event = emit_pipeline_terminal(run, causes=[exception_diagnostic(error)])
    serialized = json.dumps(event)
    assert event["failure_kind"] == "provider_schema_drift"
    assert event["provider"] == "API-Football"
    assert event["context"]["json_path"] == "$.response"
    assert event["provider_request_id"] == "request-7"
    assert "must-not-be-copied" not in serialized


def test_provider_application_error_is_secret_safe_in_event_and_jsonl(
    tmp_path, settings
):
    canary = "provider-event-secret-canary"

    class ProviderErrorResponse:
        status = 200
        headers = {
            "content-type": "application/json",
            "x-request-id": "request-provider-event",
        }

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "errors": {
                        "fixture": "Invalid fixture parameter 1550103",
                        "token": canary,
                    },
                    "response": [],
                    "full_payload": "must-not-be-copied",
                }
            ).encode()

    client = APIFootballClient(
        api_key="fictional",
        opener=lambda request, timeout: ProviderErrorResponse(),
        minimum_interval=0,
        max_retries=0,
    )
    with pytest.raises(APIFootballResponseError) as captured:
        client.get_page("odds")
    error = captured.value
    cause = {
        **exception_diagnostic(error),
        "component": "capture",
        "operation": "odds_capture",
    }
    cause["context"]["attempts"] = 1
    run = SimpleNamespace(
        status=PipelineRun.Status.DEGRADED,
        pk=15,
        capture_run_ids=[38],
        prediction_experiment_ids=[],
        capital_experiment_ids=[],
    )
    settings.OBSERVABILITY_EVENTS_ENABLED = True
    settings.OBSERVABILITY_EVENT_DIR = str(tmp_path)

    event = emit_pipeline_terminal(run, causes=[cause])
    serialized = json.dumps(event)
    persisted = (tmp_path / "django-web.jsonl").read_text()

    assert event["pipeline_run_id"] == "15"
    assert event["capture_run_id"] == "38"
    assert event["provider"] == "API-Football"
    assert event["failure_kind"] == "provider_application_error"
    assert event["operation"] == "odds_capture"
    assert event["provider_request_id"] == "request-provider-event"
    assert event["context"]["attempts"] == 1
    assert "Invalid fixture parameter 1550103" in (
        event["context"]["provider_error_summary"]
    )
    assert event["stacktrace"].count("Traceback (most recent call last)") == 1
    assert canary not in str(error)
    assert canary not in serialized
    assert canary not in persisted
    assert "must-not-be-copied" not in serialized
    assert "must-not-be-copied" not in persisted


def test_watchdog_emits_once_per_overdue_episode(tmp_path, settings):
    now = datetime(2026, 8, 30, 12, tzinfo=dt_timezone.utc)
    settings.FOOTBALL_PIPELINE_ENABLED = True
    settings.FOOTBALL_CAPTURE_WAKE_SECONDS = 900
    settings.OBSERVABILITY_PIPELINE_GRACE_SECONDS = 900
    settings.OBSERVABILITY_WATCHDOG_STATE_FILE = str(tmp_path / "state.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "monitoring_started_at": (now - timedelta(seconds=1801)).isoformat(),
                "overdue": False,
            }
        )
    )

    with mock.patch(
        "football.management.commands.observe_pipeline.emit_event"
    ) as emitter:
        call_command("observe_pipeline", once=True, at=now.isoformat())
        call_command("observe_pipeline", once=True, at=now.isoformat())

    emitter.assert_called_once()
    assert emitter.call_args.kwargs["event_code"] == "PIPELINE_OVERDUE"


def test_watchdog_disabled_never_emits_overdue(tmp_path, settings):
    settings.FOOTBALL_PIPELINE_ENABLED = False
    settings.OBSERVABILITY_WATCHDOG_STATE_FILE = str(tmp_path / "state.json")

    with mock.patch(
        "football.management.commands.observe_pipeline.emit_event"
    ) as emitter:
        call_command(
            "observe_pipeline",
            once=True,
            at="2026-08-30T12:00:00+00:00",
        )

    emitter.assert_not_called()


def test_watchdog_database_failure_is_one_bounded_incident(tmp_path, settings):
    settings.FOOTBALL_PIPELINE_ENABLED = True
    settings.OBSERVABILITY_WATCHDOG_STATE_FILE = str(tmp_path / "state.json")

    with (
        mock.patch(
            "football.management.commands.observe_pipeline.evaluate_liveness",
            side_effect=RuntimeError("database unavailable"),
        ),
        mock.patch(
            "football.management.commands.observe_pipeline.emit_event"
        ) as emitter,
    ):
        call_command("observe_pipeline", once=True, at="2026-08-30T12:00:00+00:00")
        call_command("observe_pipeline", once=True, at="2026-08-30T12:00:01+00:00")

    emitter.assert_called_once()
    assert emitter.call_args.kwargs["event_code"] == "OBSERVABILITY_WATCHDOG_FAILED"


def test_watchdog_discards_failed_connection_and_recovers_without_restart(
    tmp_path, settings
):
    settings.FOOTBALL_PIPELINE_ENABLED = True
    settings.OBSERVABILITY_WATCHDOG_STATE_FILE = str(tmp_path / "state.json")
    recovered = SimpleNamespace(overdue=False)
    database_connection = mock.Mock()

    with (
        mock.patch(
            "football.management.commands.observe_pipeline.evaluate_liveness",
            side_effect=[
                RuntimeError("database unavailable"),
                RuntimeError("database still unavailable"),
                recovered,
            ],
        ),
        mock.patch(
            "football.management.commands.observe_pipeline.connections",
            {"default": database_connection},
        ),
        mock.patch(
            "football.management.commands.observe_pipeline.close_old_connections"
        ) as close_old,
        mock.patch(
            "football.management.commands.observe_pipeline.emit_event"
        ) as emitter,
    ):
        call_command("observe_pipeline", once=True, at="2026-08-30T12:00:00+00:00")
        call_command("observe_pipeline", once=True, at="2026-08-30T12:00:01+00:00")
        call_command("observe_pipeline", once=True, at="2026-08-30T12:00:02+00:00")

    emitter.assert_called_once()
    assert database_connection.close.call_count == 2
    close_old.assert_not_called()
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["check_failed"] is False
    assert state["last_checked_at"] == "2026-08-30T12:00:02+00:00"


def test_watchdog_long_running_iteration_refreshes_old_connections(tmp_path, settings):
    now = datetime(2026, 8, 30, 12, tzinfo=dt_timezone.utc)
    settings.FOOTBALL_PIPELINE_ENABLED = True
    settings.OBSERVABILITY_WATCHDOG_STATE_FILE = str(tmp_path / "state.json")

    with (
        mock.patch(
            "football.management.commands.observe_pipeline.evaluate_liveness",
            return_value=SimpleNamespace(overdue=False),
        ),
        mock.patch(
            "football.management.commands.observe_pipeline.close_old_connections"
        ) as close_old,
    ):
        WatchdogCommand()._check(now, prepare_connection=True)

    close_old.assert_called_once_with()


def test_celery_pipeline_boundary_emits_once_and_reraises(settings):
    settings.FOOTBALL_PIPELINE_ENABLED = True
    with (
        mock.patch(
            "football.tasks.run_pipeline", side_effect=RuntimeError("task failure")
        ),
        mock.patch("football.tasks.emit_event") as emitter,
        pytest.raises(RuntimeError, match="task failure"),
    ):
        wake_pipeline()

    emitter.assert_called_once()
    assert emitter.call_args.kwargs["event_code"] == "PIPELINE_TASK_FAILED"


def test_celery_pipeline_boundary_preserves_provider_diagnostic(settings):
    settings.FOOTBALL_PIPELINE_ENABLED = True
    error = APIFootballResponseError(
        "API-Football reported: access denied",
        failure_kind="provider_access_denied",
        diagnostic_context={
            "endpoint_family": "odds",
            "provider_error_summary": "plan: access denied",
        },
    )
    with (
        mock.patch("football.tasks.run_pipeline", side_effect=error),
        mock.patch("football.tasks.emit_event") as emitter,
        pytest.raises(APIFootballResponseError),
    ):
        wake_pipeline()

    emitter.assert_called_once()
    event = emitter.call_args.kwargs
    assert event["provider"] == "API-Football"
    assert event["failure_kind"] == "provider_access_denied"
    assert event["context"]["endpoint_family"] == "odds"
    assert event["context"]["provider_error_summary"] == "plan: access denied"
    assert event["traceback_text"].count("Traceback (most recent call last)") == 1


def test_django_runtime_handler_captures_only_error_boundary():
    handler = OperationalErrorHandler()
    try:
        raise RuntimeError("request failure")
    except RuntimeError:
        record = logging.LogRecord(
            name="django.request",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="request failed",
            args=(),
            exc_info=sys.exc_info(),
        )

    with mock.patch("football.observability.runtime.emit_event") as emitter:
        handler.emit(record)

    emitter.assert_called_once()
    assert emitter.call_args.kwargs["event_code"] == "DJANGO_RUNTIME_FAILED"


def test_reconciliation_is_one_aggregate_event_per_source():
    now = datetime(2026, 8, 30, 12, tzinfo=dt_timezone.utc)
    source = Source.objects.create(code="provider", name="Provider")
    competition = Competition.objects.create(
        name="League", country="PE", competition_type="League"
    )
    season = Season.objects.create(
        competition=competition,
        year=2026,
        start_date=now.date(),
        end_date=now.date(),
    )
    home = Team.objects.create(competition=competition, name="Home")
    away = Team.objects.create(competition=competition, name="Away")
    match = Match.objects.create(
        season=season,
        home_team=home,
        away_team=away,
        kickoff=now,
        status_short="NS",
    )
    first_seen = now - timedelta(hours=2)
    CompetitionSourceRef.objects.create(
        source=source,
        external_id="c1",
        first_seen_at=first_seen,
        reconciliation_status=ReconciliationStatus.PENDING,
    )
    TeamSourceRef.objects.create(
        source=source,
        competition=competition,
        external_id="t1",
        first_seen_at=now - timedelta(hours=1),
        reconciliation_status=ReconciliationStatus.PENDING,
    )
    MatchSourceRef.objects.create(
        source=source,
        external_id="m1",
        proposed_match=match,
        first_seen_at=now - timedelta(minutes=30),
        reconciliation_status=ReconciliationStatus.PENDING,
    )

    with mock.patch("football.observability.reconciliation.emit_event") as emitter:
        emitted = emit_reconciliation_pending(
            pipeline_run_id=10, capture_run_id=11, now=now
        )

    assert len(emitted) == 1
    emitter.assert_called_once()
    call = emitter.call_args.kwargs
    assert call["event_code"] == "RECONCILIATION_PENDING"
    assert call["context"] == {
        "competition_pending": 1,
        "team_pending": 1,
        "match_pending": 1,
        "oldest_pending_age_seconds": 7200,
    }
