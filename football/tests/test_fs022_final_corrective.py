"""Post-UAT correction: normal OPEN result debt versus a durable incident."""

from datetime import timedelta

import pytest
from django.test import override_settings

from football.capital.runtime import run_automatic_runtime
from football.capture.contracts import CaptureResult
from football.models import (
    CapitalPosition,
    CompetitionSourceRef,
    Match,
    PipelineRun,
    ReconciliationStatus,
)
from football.pipeline.service import run_pipeline
from football.providers.api_football import APIFootballError
from football.strategy.deployment import provision
from football.strategy.prospective import reconcile_global
from football.tests.test_fs022_strategy import AT, capture
from football.tests.test_fs022_strategy import graph as graph

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def simulated_clock(monkeypatch):
    monkeypatch.setattr(
        "football.strategy.clock.effective_now",
        lambda *, planning_at=None: planning_at or AT,
    )


def setup_open_result_cycle(graph, monkeypatch, *, provider_error=False):
    provision(at=AT)
    work = capture(graph, 80)
    assert reconcile_global(work.run_id, at=work.run.completed_at).placed == 1
    match = work.match
    position = CapitalPosition.objects.get(match=match)
    CompetitionSourceRef.objects.create(
        source=graph[0],
        competition=graph[3],
        external_id="501",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    external_id = f"fs022-{match.pk}"
    stage = {"terminal": False}

    class FakeClient:
        def __init__(self, **kwargs):
            del kwargs
            self.calls = 0
            self.daily_remaining = 99
            self.quota_observed_calls = 0
            self.attempt_guard = None

        def get_all(self, endpoint, params):
            assert endpoint == "fixtures"
            assert params in (
                {"date": "2026-09-27", "timezone": "America/Lima"},
                {"id": external_id},
            )
            self.attempt_guard(self)
            self.calls += 1
            if provider_error:
                raise APIFootballError("controlled result failure")
            return [{"fixture": {"id": external_id}}]

    def sync_stub(payloads, competitions):
        assert payloads == [{"fixture": {"id": external_id}}]
        assert set(competitions) == {"501"}
        if stage["terminal"]:
            Match.objects.filter(pk=match.pk).update(
                status_short="FT",
                outcome="HOME",
                fulltime_home_score=2,
                fulltime_away_score=1,
            )
        else:
            Match.objects.filter(pk=match.pk).update(status_short="NS", outcome="")
        return None, {external_id: Match.objects.get(pk=match.pk)}

    monkeypatch.setattr("football.capital.runtime.sync_fixture_payloads", sync_stub)
    monkeypatch.setattr(
        "football.pipeline.service.run_capture",
        lambda **kwargs: CaptureResult(
            run_id=None,
            status="NO_WORK",
            planning_at=kwargs["at"],
            quota_before={},
            quota_after={},
        ),
    )
    monkeypatch.setattr(
        "football.pipeline.service.run_automatic_runtime",
        lambda **kwargs: run_automatic_runtime(**kwargs, client_factory=FakeClient),
    )
    return match, position, stage


@override_settings(FOOTBALL_CAPTURE_DISCOVERY_ENABLED=False)
def test_normal_nonterminal_poll_is_expected_debt_then_terminal_settlement(
    graph, monkeypatch
):
    match, position, stage = setup_open_result_cycle(graph, monkeypatch)
    due = match.kickoff + timedelta(minutes=130)
    first = run_pipeline(at=due)
    assert first.status != PipelineRun.Status.DEGRADED
    assert first.phases["CAPITAL"]["state"] != "DEGRADED"
    assert first.phases["CAPITAL"]["reason"] == "OPEN_RESULT_NOT_DUE"
    assert first.phases["CAPITAL"]["details"]["runtime"]["errors"] == []
    assert first.phases["CAPITAL"]["details"]["runtime"]["provider_calls"] == 1
    position.refresh_from_db()
    assert position.status == CapitalPosition.Status.OPEN
    assert position.next_result_check_at == due + timedelta(minutes=30)
    assert position.result_refresh_error == ""
    assert position.config.reserved_exposure > 0
    assert (
        PipelineRun.objects.get(pk=first.run_id).phase_states["CAPITAL"]["reason"]
        == "OPEN_RESULT_NOT_DUE"
    )

    stage["terminal"] = True
    second = run_pipeline(at=due + timedelta(minutes=30))
    position.refresh_from_db()
    assert second.status != PipelineRun.Status.DEGRADED
    assert second.phases["CAPITAL"]["details"]["runtime"]["settled"] == 1
    assert position.status == CapitalPosition.Status.SETTLED_WIN
    assert position.debt_status == CapitalPosition.DebtStatus.RESOLVED
    assert position.config.reserved_exposure == 0
    assert not CapitalPosition.objects.filter(
        status=CapitalPosition.Status.OPEN
    ).exists()


@override_settings(FOOTBALL_CAPTURE_DISCOVERY_ENABLED=False)
def test_provider_failure_stays_degraded_with_durable_reason(graph, monkeypatch):
    match, position, _ = setup_open_result_cycle(
        graph, monkeypatch, provider_error=True
    )
    due = match.kickoff + timedelta(minutes=130)
    result = run_pipeline(at=due)
    assert result.status == PipelineRun.Status.DEGRADED
    capital = result.phases["CAPITAL"]
    assert capital["state"] == "DEGRADED"
    assert "controlled result failure" in capital["reason"]
    assert capital["details"]["runtime"]["errors"]
    saved = PipelineRun.objects.get(pk=result.run_id)
    assert saved.phase_states["CAPITAL"]["reason"] == capital["reason"]
    position.refresh_from_db()
    assert position.status == CapitalPosition.Status.OPEN
    assert position.debt_status == CapitalPosition.DebtStatus.DEGRADED
    assert "controlled result failure" in position.result_refresh_error
