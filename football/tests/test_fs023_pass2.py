"""Pass-2 integration boundaries: fake providers, no scientific U33/U34 run."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest
from django.test import override_settings

from football.capture.contracts import CaptureConfig, PlannedWork
from football.capture.executor import CaptureExecutor
from football.experiments.capital_runner import CANDIDATES
from football.experiments.economic_selector import select_economic_baseline
from football.experiments.fs023_runner import _stream
from football.experiments.integrated_events import run_integrated_path
from football.management.commands.verify_fs023_runtime import verify_effective_settings
from football.models import (
    BSDEventBinding,
    BSDTeamMapping,
    CompetitionResultRoute,
    CompetitionSourceRef,
    MatchSourceRef,
    ReconciliationStatus,
    ResultProviderObservation,
    StrategyBinding,
)
from football.providers.bsd import BSDClient
from football.providers.bsd_continuity import run_bsd_continuity
from football.result_provider import Result, record
from football.sync import get_api_football_source
from football.tests.helpers import fixture_payload
from football.tests.test_fs023_contracts import NOW, _match

pytestmark = pytest.mark.django_db


class Response:
    status_code = 200
    headers = {}

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class BSDSession:
    def __init__(self, event, *, ambiguous=False):
        self.event = event
        self.ambiguous = ambiguous
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if url.endswith("/events/"):
            rows = [self.event]
            if self.ambiguous:
                rows.append({**self.event, "id": self.event["id"] + 1})
            return Response({"results": rows, "next": None})
        assert url.endswith(f"/events/{self.event['id']}/")
        return Response(
            {**self.event, "status": "finished", "home_score": 2, "away_score": 1}
        )


def _bsd_graph(*, at=NOW, mapped=True):
    match = _match()
    match.kickoff = at + timedelta(days=10)
    match.save(update_fields=["kickoff", "modified"])
    route = CompetitionResultRoute.objects.create(
        competition=match.season.competition,
        api_football_league_id=1,
        bsd_league_ids=[1],
        bsd_state="BSD_SHADOW_VALIDATION",
        provenance={"bsd_season_ids": {"1": 2026}},
    )
    if mapped:
        for team, bsd_id in ((match.home_team, 11), (match.away_team, 12)):
            BSDTeamMapping.objects.create(
                route=route,
                canonical_team=team,
                bsd_league_id=1,
                bsd_team_id=bsd_id,
                approval="EXACT_UNIQUE",
            )
    event = {
        "id": 1001,
        "league_id": 1,
        "home_team_id": 11,
        "away_team_id": 12,
        "event_date": match.kickoff.isoformat(),
    }
    return match, route, event


def test_new_future_fixture_binds_once_then_shadow_observes_without_position():
    match, route, event = _bsd_graph()
    route.bsd_state = "BSD_BOOTSTRAP_PENDING"
    route.save(update_fields=["bsd_state"])
    session = BSDSession(event)

    def factory():
        return BSDClient(session=session, sleep=lambda _: None)

    with override_settings(BSD_API_TOKEN="fake-only"):
        first = run_bsd_continuity(at=NOW, client_factory=factory)
        second = run_bsd_continuity(at=NOW, client_factory=factory)
        assert first["bindings"] == 1 and second["bindings"] == 0
        route.refresh_from_db()
        assert route.bsd_state == "BSD_SHADOW_VALIDATION"
        assert len(session.calls) == 1
        assert BSDEventBinding.objects.filter(match=match).count() == 1
        later = match.kickoff + timedelta(hours=3)
        observed = run_bsd_continuity(at=later, client_factory=factory)
        assert observed["shadow_observations"] == 1
        assert run_bsd_continuity(at=later, client_factory=factory)["shadow_calls"] == 0
    bsd = ResultProviderObservation.objects.get(match=match, provider="BSD")
    assert not bsd.authoritative
    match.refresh_from_db()
    assert match.status_short == "NS" and match.outcome == ""
    assert not match.capital_positions.exists()

    source = get_api_football_source()
    CompetitionSourceRef.objects.create(
        source=source,
        competition=match.season.competition,
        external_id="1",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    MatchSourceRef.objects.create(
        source=source,
        match=match,
        external_id="501",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    payload = fixture_payload(
        fixture_id=501,
        league_id=1,
        year=2026,
        status_short="FT",
        home_score=2,
        away_score=1,
        kickoff=match.kickoff.isoformat(),
        home_name=match.home_team.name,
        away_name=match.away_team.name,
    )

    class APIClient:
        def get_all(self, endpoint, params):
            assert endpoint == "fixtures"
            return [payload]

    item = PlannedWork(
        purpose="RESULT_REFRESH",
        status="PLANNED",
        source=source,
        logical_identity="shadow-date-sweep",
        intended_window="bsd-shadow-sample",
        params={"date": match.kickoff.date().isoformat(), "timezone": "America/Lima"},
        target_external_ids=("501",),
    )
    CaptureExecutor._perform(APIClient(), item)
    assert (
        ResultProviderObservation.objects.filter(
            match=match,
            provider="API_FOOTBALL",
            conflict=False,
        ).count()
        == 1
    )
    route.refresh_from_db()
    assert route.bsd_state == "BSD_SHADOW_VALIDATION"


def test_ambiguous_or_unmapped_incremental_identity_never_binds():
    match, _, event = _bsd_graph()
    session = BSDSession(event, ambiguous=True)
    with override_settings(BSD_API_TOKEN="fake-only"):
        result = run_bsd_continuity(
            at=NOW,
            client_factory=lambda: BSDClient(session=session, sleep=lambda _: None),
        )
        assert result["bindings"] == 0
        run_bsd_continuity(
            at=NOW,
            client_factory=lambda: BSDClient(session=session, sleep=lambda _: None),
        )
    assert len(session.calls) == 1
    assert not BSDEventBinding.objects.filter(match=match).exists()
    other, _, _ = _bsd_graph(at=NOW + timedelta(days=1), mapped=False)
    with override_settings(BSD_API_TOKEN=""):
        assert run_bsd_continuity(at=NOW)["status"] == "BSD_NOT_CONFIGURED"
    assert not BSDEventBinding.objects.filter(match=other).exists()


def test_primary_ft_score_and_terminal_revisions_preserve_one_truth():
    from football.result_provider import shadow_gate

    match = _match()
    CompetitionResultRoute.objects.create(
        competition=match.season.competition,
        api_football_league_id=1,
        bsd_league_ids=[1],
        bsd_state="BSD_PRIMARY_VALIDATED",
    )
    _, state = record(
        match,
        Result("BSD", "900", "FT", 2, 1, "HOME", NOW, {}),
        authoritative=True,
    )
    assert state == "RECORDED"
    match.refresh_from_db()
    assert (match.home_score, match.away_score) == (2, 1)
    assert (match.fulltime_home_score, match.fulltime_away_score) == (2, 1)
    same, state = record(
        match,
        Result(
            "API_FOOTBALL", "501", "FT", 2, 1, "HOME", NOW + timedelta(minutes=1), {}
        ),
        authoritative=True,
    )
    assert state == "RECORDED" and same.authoritative
    assert (
        record(
            match,
            Result(
                "API_FOOTBALL",
                "501",
                "FT",
                2,
                1,
                "HOME",
                NOW + timedelta(minutes=1),
                {},
            ),
            authoritative=True,
        )[1]
        == "ALREADY_RECORDED"
    )
    revised, state = record(
        match,
        Result(
            "API_FOOTBALL", "501", "FT", 1, 2, "AWAY", NOW + timedelta(minutes=2), {}
        ),
        authoritative=True,
    )
    assert state == "RESULT_CONFLICT" and revised.conflict
    assert revised.provenance["same_provider_revision"] is True
    assert shadow_gate()["confirmed_conflicts"] == 1
    assert shadow_gate()["status"] == "FAIL"
    match.refresh_from_db()
    assert (match.outcome, match.home_score, match.away_score) == ("HOME", 2, 1)
    assert (
        not ResultProviderObservation.objects.filter(match=match)
        .exclude(provider="BSD")
        .filter(authoritative=True, conflict=True)
        .exists()
    )


def test_effective_runtime_preflight_rejects_stale_windows_and_unsafe_flags():
    assert verify_effective_settings()["windows"] == [
        CaptureConfig.from_settings().windows[0].snapshot()
    ]
    old = [
        {
            "name": "market-t30m",
            "offset_minutes": 30,
            "normal_tolerance_minutes": 10,
            "late_tolerance_minutes": 15,
        },
        {
            "name": "market-t60m",
            "offset_minutes": 60,
            "normal_tolerance_minutes": 10,
            "late_tolerance_minutes": 15,
        },
        {
            "name": "market-t6h",
            "offset_minutes": 360,
            "normal_tolerance_minutes": 10,
            "late_tolerance_minutes": 15,
        },
    ]
    with override_settings(FOOTBALL_MARKET_CONSENSUS_WINDOWS=old):
        with pytest.raises(ValueError, match="FS023_T10_EFFECTIVE_CONFIG_INVALID"):
            verify_effective_settings()
    with override_settings(FOOTBALL_CAPTURE_WAKE_SECONDS=300):
        with pytest.raises(ValueError, match="FS023_WAKE_MUST_BE_180_SECONDS"):
            verify_effective_settings()
    with override_settings(INKABET_AUTOMATIC_ENABLED=True):
        with pytest.raises(ValueError, match="FS023_UNSAFE_AUTOMATIC_FLAG"):
            verify_effective_settings()
    with override_settings(BSD_API_TOKEN=""):
        assert (
            verify_effective_settings()["bsd_effective_state"] == "BSD_NOT_CONFIGURED"
        )


def test_binding_rejects_candidate_and_name_contract_disagreement():
    with pytest.raises(Exception, match="candidate_id disagrees"):
        StrategyBinding.objects.create(
            name="T10",
            candidate_id=209,
            contract={"name": "T10", "candidate_id": 216, "real_betting": False},
            approved=True,
        )
    with pytest.raises(Exception, match="name disagrees"):
        StrategyBinding.objects.create(
            name="T10",
            candidate_id=209,
            contract={"name": "T30", "candidate_id": 209, "real_betting": False},
            approved=True,
        )


def _row(identity, kickoff, probabilities, prices, home, away):
    return {
        "fixture_id": identity,
        "country": "PE",
        "kickoff_utc": kickoff.isoformat(),
        "windows": {
            "T10": {
                "status": "PRODUCED",
                "book_count": 3,
                "cutoff": (kickoff - timedelta(minutes=10)).isoformat(),
                "probabilities": probabilities,
                "best_prices": prices,
            }
        },
        "result": {"home_score": home, "away_score": away},
    }


def test_real_policy_stream_and_integrated_capital_win_loss_no_bet():
    rows = [
        _row("win", NOW, [0.6, 0.2, 0.2], ["2.5", "4", "5"], 2, 1),
        _row("loss", NOW + timedelta(hours=4), [0.1, 0.2, 0.7], ["5", "4", "2"], 2, 1),
        _row(
            "pass", NOW + timedelta(hours=8), [0.36, 0.34, 0.3], ["3", "3", "3"], 1, 1
        ),
    ]
    opportunities = _stream(rows, 209)
    assert [
        (o.action, o.selected_outcome, o.actual_outcome) for o in opportunities
    ] == [
        ("BET", "HOME", "HOME"),
        ("BET", "AWAY", "HOME"),
        ("NO_BET", None, "DRAW"),
    ]
    result = run_integrated_path(opportunities, CANDIDATES[6], 150, trace=True)
    assert result["metrics"]["placements"] == 2
    kinds = [row["kind"] for row in result["ledger"]]
    assert "NO_BET" in kinds
    settlements = [row for row in result["ledger"] if row["kind"] == "SETTLEMENT"]
    assert [row["won"] for row in settlements] == [True, False]
    assert Decimal(settlements[0]["profit_loss"]) > 0
    assert Decimal(settlements[1]["profit_loss"]) < 0
    assert CANDIDATES[6].data()["max_lanes"] == 10


def test_real_selector_n3_uses_observed_activity_and_sparse_canonical_ids():
    ids = (209, 216, 223)
    observed = {
        str(lag): [
            {
                "structurally_complete": True,
                "total_return": "0.1",
                "maximum_drawdown": "0.1",
                "hard_risk": "PASS",
                "ever_nonpositive_equity": False,
                "operational_depletion": False,
                "economic_ruin": False,
                "policy_termination": "",
                "termination_reason": "",
                "placements": 52 if i == 216 else 53,
                "placed_competitions": list(range(5)),
                "placed_weeks": list(range(5)),
            }
            for i in ids
        ]
        for lag in (120, 130, 150)
    }
    payload = {
        "schema": "ECONOMIC_SELECTOR_INPUT_V1",
        "candidates": [{"integrated_index": i, "capital_index": 6} for i in ids],
        "candidate_ids": list(ids),
        "activity": {
            "placements": 53,
            "competitions": 5,
            "weeks": 5,
        },
        "benchmark": {"status": "UNAVAILABLE"},
        "observed": observed,
        "scores": {str(block): np.full((20, 3), 0.1) for block in (1, 2, 4)},
        "scientific_disposition": "RESTRICTED_PREREGISTERED_CHALLENGE",
    }
    selected = select_economic_baseline(payload)
    assert selected["candidate_ids"] == [209, 216, 223]
    by_id = {row["integrated_index"]: row for row in selected["rows"]}
    assert "120:PLACEMENTS_LT_53" in by_id[216]["activity_reasons"]
    assert not by_id[209]["activity_reasons"]
    assert selected["benchmark_primary"] is None


def _olv_work(match, at, *, attempts=1, usable=True, status="SUCCESS"):
    from football.models import CaptureRun, CaptureWorkItem

    source = get_api_football_source()
    run = CaptureRun.objects.create(
        status="SUCCESS",
        planning_at=at,
        started_at=at,
        completed_at=at + timedelta(hours=1),
    )
    return CaptureWorkItem.objects.create(
        run=run,
        purpose="ODDS_CAPTURE",
        status=status,
        source=source,
        match=match,
        logical_identity=f"olv:{match.pk}:{run.pk}",
        intended_window="market-t10m",
        executed_at=at,
        completed_at=at + timedelta(seconds=4),
        not_after=at + timedelta(minutes=8),
        actual_attempts=attempts,
        olv_usable=usable if attempts else None,
    )


def test_olv_uses_physical_work_completion_not_later_run_completion(monkeypatch):
    from types import SimpleNamespace

    from football.capture.olv import _usable

    match = _match()
    at = NOW - timedelta(minutes=10)
    work = _olv_work(match, at, usable=None)
    called = []
    monkeypatch.setattr(
        "football.prediction.market.market_selection_as_of",
        lambda match, cutoff, **kwargs: (
            called.append(cutoff) or SimpleNamespace(quotes=[1, 2])
        ),
    )
    assert work.run.completed_at > work.not_after
    assert _usable(work) is True
    assert called == [work.completed_at]
    work.refresh_from_db()
    assert work.olv_usable is True
    assert _usable(work) is True
    assert called == [work.completed_at]


def test_olv_attempts_season_weights_lima_day_and_constant_query_growth():
    from datetime import date

    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from football.capture.olv import competition_score, score
    from football.models import Match, Season

    match = _match()
    current_at = datetime(2026, 9, 30, 1, tzinfo=UTC)  # September 29 in Lima.
    _olv_work(match, current_at - timedelta(minutes=5), usable=True)
    _olv_work(
        match, current_at - timedelta(minutes=4), usable=False, status="FAILED_PROVIDER"
    )
    _olv_work(
        match,
        current_at - timedelta(minutes=3),
        attempts=0,
        usable=None,
        status="MISSED_STRATEGY_WINDOW",
    )
    previous_season = Season.objects.create(
        competition=match.season.competition,
        year=2025,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )
    previous = Match.objects.create(
        season=previous_season,
        home_team=match.home_team,
        away_team=match.away_team,
        kickoff=NOW - timedelta(days=365),
        status_short="NS",
    )
    _olv_work(previous, current_at - timedelta(days=365), usable=True)
    assert competition_score(match.season.competition_id, current_at) == pytest.approx(
        score(2, 1, 1, 1, 1)
    )
    with CaptureQueriesContext(connection) as initial:
        competition_score(match.season.competition_id, current_at)
    for i in range(100):
        _olv_work(match, current_at - timedelta(days=1, minutes=i + 1), usable=True)
    with CaptureQueriesContext(connection) as accumulated:
        competition_score(match.season.competition_id, current_at)
    assert len(accumulated) <= len(initial) + 1


def _epoch_graph():
    from football.models import CapitalDeployment, CapitalRuntimeConfig, StrategyEpoch
    from football.strategy.epochs import target_binding

    contract = {
        "schema": "FS023_STRATEGY_BINDING_V1",
        "name": "FS022_BINDING_209_T30_V1",
        "candidate_id": 209,
        "prediction": {"code": "MARKET_CONSENSUS", "version": "v1"},
        "decision": {"code": "D05", "variant": "default"},
        "capital": {
            "code": "FRACTIONAL_KELLY",
            "version": "v1",
            "config": {"lambda": "0.25"},
            "max_lanes": 10,
        },
        "capture_window": "market-t30m",
        "wake_seconds": 300,
        "required_capabilities": ["LIVE_MARKET_ODDS"],
        "provider_topology": "API_FOOTBALL_RESULT_PRIMARY",
        "real_betting": False,
    }
    source = StrategyBinding.objects.create(
        name=contract["name"],
        candidate_id=209,
        contract=contract,
        approved=True,
    )
    epoch = StrategyEpoch.objects.create(
        binding=source,
        state="ACTIVE",
        initial_bankroll=Decimal("100"),
        activated_at=NOW,
    )
    config = CapitalRuntimeConfig.objects.create(
        identity="pass2:source-epoch",
        strategy_epoch=epoch,
        runtime_version="test",
        execution_version="fs022-prospective-t30-v2",
        mode="CURRENT",
        automatic=True,
        current=True,
        entry_enabled=True,
        source_model_code="MARKET_CONSENSUS",
        decision_policy_code="D05",
        decision_policy_variant="default",
        policy_code="FRACTIONAL_KELLY",
        policy_version="v1",
        policy_config={"lambda": "0.25"},
        max_lanes=10,
        initial_bankroll=Decimal("100"),
        bankroll_equity=Decimal("75"),
        reserved_exposure=Decimal("1"),
        peak_equity=Decimal("100"),
        policy_state={},
        started_at=NOW,
    )
    deployment = CapitalDeployment.objects.create(
        pk=1,
        state="ACTIVE",
        active_epoch=epoch,
        config=config,
        activated_at=NOW,
        entry_enabled=True,
        selection={
            "prospective_prediction_effective_config": {"capture_window": "market-t30m"}
        },
    )
    return source, epoch, config, deployment, target_binding(source)


def test_nonempty_epoch_drain_settlement_retry_and_rollback_isolated_bankroll():
    from football.capital.runtime import observe_terminal_result, settle_observation
    from football.models import (
        CapitalDeployment,
        CapitalExecutionBasis,
        CapitalExecutionState,
        CapitalPosition,
        CapitalRuntimeConfig,
        CaptureRun,
        CaptureWorkItem,
        StrategyEpoch,
        StrategySwitch,
    )
    from football.strategy.deployment import admission_reason
    from football.strategy.epochs import advance, request_switch
    from football.strategy.prospective import capture_reason

    source, epoch, config, deployment, target = _epoch_graph()
    opened = _match()
    pending_match = _match()
    basis = CapitalExecutionBasis.objects.create(
        config=config,
        match=opened,
        decision_policy_code="D05",
        decision_policy_version="v1",
        action="HOME",
        reason="TEST_EVIDENCE",
        selected_price=Decimal("2"),
        execution_at=NOW,
        evidence_not_before=NOW,
        evidence_cutoff=NOW,
    )
    position = CapitalPosition.objects.create(
        config=config,
        match=opened,
        execution_basis=basis,
        status="OPEN",
        placed_at=NOW,
        requested_stake=Decimal("1"),
        applied_stake=Decimal("1"),
        placement_equity_before=Decimal("75"),
        placement_reserved_before=Decimal("0"),
        placement_available_before=Decimal("75"),
        placement_equity_after=Decimal("75"),
        placement_reserved_after=Decimal("1"),
        placement_available_after=Decimal("74"),
        policy_state_before={},
    )
    pending = CapitalExecutionState.objects.create(
        config=config,
        match=pending_match,
        status="PENDING_CAPACITY",
    )
    state, switch = request_switch(target, at=NOW + timedelta(minutes=1))
    assert state == "DRAINING" and switch.target_epoch_id is None
    pending.refresh_from_db()
    config.refresh_from_db()
    deployment.refresh_from_db()
    assert pending.status == "NOT_PLACED"
    assert pending.non_placement_reason == "STRATEGY_DRAINING"
    assert not pending.position_id and not config.entry_enabled
    assert admission_reason(deployment, config) == "STRATEGY_DRAINING"
    assert advance(at=NOW + timedelta(minutes=2)) == ()
    assert request_switch(target, at=NOW + timedelta(minutes=2))[1].pk == switch.pk
    assert StrategyEpoch.objects.count() == 1

    provider, _ = record(
        opened,
        Result("BSD", "900", "FT", 2, 1, "HOME", NOW + timedelta(minutes=3), {}),
        authoritative=True,
    )
    opened.refresh_from_db()
    observation, _ = observe_terminal_result(
        opened,
        known_at=NOW + timedelta(minutes=3),
        provider_result=provider,
    )
    assert settle_observation(observation, settled_at=NOW + timedelta(minutes=3)) == 1
    assert settle_observation(observation, settled_at=NOW + timedelta(minutes=4)) == 0
    position.refresh_from_db()
    config.refresh_from_db()
    assert position.status == "SETTLED_WIN" and config.bankroll_equity == Decimal("76")
    position.debt_status = "DEGRADED"
    position.save(update_fields=["debt_status"])
    assert advance(at=NOW + timedelta(minutes=4)) == ()
    position.debt_status = "RESOLVED"
    position.save(update_fields=["debt_status"])
    config.reserved_exposure = Decimal("1")
    config.save(update_fields=["reserved_exposure"])
    with pytest.raises(RuntimeError, match="LEDGER_EXPOSURE_MISMATCH"):
        advance(at=NOW + timedelta(minutes=4))
    config.reserved_exposure = Decimal("0")
    config.save(update_fields=["reserved_exposure"])
    (target_config,) = advance(at=NOW + timedelta(minutes=5))
    assert (
        target_config.bankroll_equity
        == target_config.initial_bankroll
        == Decimal("100")
    )
    assert target_config.reserved_exposure == 0
    assert target_config.pk != config.pk and target_config.strategy_epoch_id != epoch.pk
    assert advance(at=NOW + timedelta(minutes=6))[0].pk == target_config.pk
    assert StrategySwitch.objects.count() == 1 and StrategyEpoch.objects.count() == 2

    early = _match()
    early.kickoff = NOW + timedelta(minutes=14)
    early.save(update_fields=["kickoff", "modified"])
    executed = early.kickoff - timedelta(minutes=10)
    run = CaptureRun.objects.create(
        status="SUCCESS",
        planning_at=executed,
        started_at=executed,
        completed_at=executed + timedelta(seconds=3),
    )
    work = CaptureWorkItem.objects.create(
        run=run,
        purpose="ODDS_CAPTURE",
        status="SUCCESS",
        source=get_api_football_source(),
        match=early,
        logical_identity="preactivation-t10",
        intended_window="market-t10m",
        target_at=executed,
        not_before=executed,
        not_after=executed + timedelta(minutes=8),
        executed_at=executed,
        completed_at=executed + timedelta(seconds=2),
    )
    deployment = CapitalDeployment.objects.get(pk=1)
    assert capture_reason(work, deployment) == "PRE_GLOBAL"

    state, rollback = request_switch(source, at=NOW + timedelta(minutes=7))
    assert state == "DRAINING" and rollback.target_binding_id == source.pk
    (rollback_config,) = advance(at=NOW + timedelta(minutes=8))
    assert rollback_config.strategy_epoch_id not in {
        epoch.pk,
        target_config.strategy_epoch_id,
    }
    assert (
        rollback_config.initial_bankroll
        == rollback_config.bankroll_equity
        == Decimal("100")
    )
    assert request_switch(source, at=NOW + timedelta(minutes=9))[0] == "ALREADY_ACTIVE"
    assert StrategyEpoch.objects.count() == 3
    config.refresh_from_db()
    assert config.bankroll_equity == Decimal("76")
    assert CapitalRuntimeConfig.objects.count() == 3


def test_runner_structural_failure_and_missing_benchmark_prevent_publication(
    tmp_path, monkeypatch
):
    from football.experiments import fs023_runner
    from football.experiments.fs023_benchmark import validate_benchmark

    row = _row("bad-cutoff", NOW, [0.6, 0.2, 0.2], ["2", "4", "5"], 2, 1)
    row["windows"]["T10"]["cutoff"] = NOW.isoformat()
    monkeypatch.setattr(fs023_runner, "authenticated_rows", lambda durable: [row])
    spec = {
        "horizon_days": 257,
        "freeze_at": "2026-09-29",
        "primary": {"status": "UNAVAILABLE"},
    }
    with pytest.raises(ValueError, match="FS023_FROZEN_T10_CUTOFF_MISMATCH"):
        fs023_runner.run_subset(
            ids=(209,),
            benchmark=spec,
            durable=tmp_path,
            output_root=tmp_path,
            mode="evaluation-only",
        )
    assert not list(tmp_path.rglob("publication.json"))
    with pytest.raises(ValueError, match="FS023_PRIMARY_BENCHMARK_REQUIRED"):
        validate_benchmark({"horizon_days": 257, "freeze_at": "2026-09-29"})
    with pytest.raises(ValueError, match="FS023_PRIMARY_BENCHMARK_SOURCE_INVALID"):
        validate_benchmark(
            {
                "horizon_days": 257,
                "freeze_at": "2026-09-29",
                "primary": {
                    "status": "AVAILABLE",
                    "source": "INVENTED",
                    "currency": "PEN",
                },
            }
        )


def test_runtime_preflight_accepts_one_180_second_pipeline_owner():
    with override_settings(
        FOOTBALL_PIPELINE_ENABLED=True,
        CELERY_BEAT_SCHEDULE={
            "football-pipeline-wake": {
                "task": "football.pipeline.wake",
                "schedule": 180,
            }
        },
    ):
        assert verify_effective_settings(require_automatic=True)["beat_owner"] == (
            "football.pipeline.wake"
        )
    with override_settings(
        FOOTBALL_PIPELINE_ENABLED=True,
        CELERY_BEAT_SCHEDULE={
            "football-pipeline-wake": {
                "task": "football.pipeline.wake",
                "schedule": 180,
            },
            "other": {"task": "football.capture.wake", "schedule": 180},
        },
    ):
        with pytest.raises(ValueError, match="FS023_SINGLE_BEAT_OWNER_REQUIRED"):
            verify_effective_settings(require_automatic=True)


def test_olv_28_competitions_aggregate_queries_do_not_grow_with_history():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from football.capture.olv import competition_score

    matches = [_match() for _ in range(28)]
    at = NOW + timedelta(hours=1)
    for match in matches:
        _olv_work(match, NOW - timedelta(hours=1), usable=True)

    def wake_scores():
        return [competition_score(match.season.competition_id, at) for match in matches]

    with CaptureQueriesContext(connection) as small:
        first = wake_scores()
    for match in matches:
        for day in range(1, 11):
            _olv_work(match, NOW - timedelta(days=day, hours=1), usable=True)
    with CaptureQueriesContext(connection) as accumulated:
        second = wake_scores()
    assert len(first) == len(second) == 28
    assert len(accumulated) <= len(small) + 2
