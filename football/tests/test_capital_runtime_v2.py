from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from django.db import close_old_connections
from django.test import Client

from football.capital.contracts import RunUnavailable
from football.capital.policies import (
    FIXED_FRACTION_BANKROLL,
    FIXED_TARGET_PROFIT_NO_RECOVERY,
    FLAT_UNIT,
    FRACTIONAL_KELLY,
    LEGACY_CAPPED,
    LEGACY_PARTIAL,
    LEGACY_RECOVERY,
)
from football.capital.runtime import (
    AUTOMATIC_CONFIGS,
    EXECUTION_VERSION,
    RUNTIME_VERSION,
    build_execution_candidate,
    observe_terminal_result,
    place_candidate,
    provision_automatic_configs,
    reconcile_execution_events,
    refresh_open_result_debt,
    run_automatic_runtime,
    settle_locally_known_open_positions,
    settle_observation,
)
from football.capital.studies import run_persisted_v2_study
from football.capture.contracts import CaptureConfig
from football.capture.planner import CapturePlanner
from football.market_identity import (
    reconcile_bookmaker_identity,
    reconcile_market_identity,
)
from football.models import (
    Bookmaker,
    CapitalExecutionBasis,
    CapitalExecutionState,
    CapitalPosition,
    CapitalResultObservation,
    CapitalRuntimeConfig,
    CaptureRun,
    CaptureWorkItem,
    Competition,
    CompetitionSourceRef,
    Decision,
    HistoricalMarketEvidence,
    Match,
    MatchSourceRef,
    OddsMarket,
    OddsObservation,
    Prediction,
    PredictionExperiment,
    ReconciliationStatus,
    Season,
    Source,
    Team,
)
from football.providers.api_football import APIFootballQuotaReserveError
from football.reporting.selectors import _capital_v2_rows

pytestmark = pytest.mark.django_db


@pytest.fixture
def runtime_graph():
    source, _ = Source.objects.get_or_create(
        code="api_football",
        defaults={"name": "API-Football", "base_url": "https://example.test"},
    )
    bookmaker, _ = Bookmaker.objects.get_or_create(
        source=source, external_id="4", defaults={"name": "Pinnacle"}
    )
    market, _ = OddsMarket.objects.get_or_create(
        source=source, external_id="1", defaults={"name": "Match Winner"}
    )
    reconcile_bookmaker_identity(bookmaker)
    reconcile_market_identity(market)
    competition = Competition.objects.create(
        name="FS016 League", competition_type="League", country="PE", enabled=True
    )
    season = Season.objects.create(
        competition=competition,
        year=2026,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    teams = [
        Team.objects.create(competition=competition, name=f"Team {index}")
        for index in range(8)
    ]
    experiment = PredictionExperiment.objects.create(
        competition=competition,
        mode=PredictionExperiment.MODE_PROSPECTIVE,
        period_start=date(2026, 9, 14),
        period_end=date(2026, 9, 14),
    )
    return {
        "source": source,
        "bookmaker": bookmaker,
        "market": market,
        "competition": competition,
        "season": season,
        "teams": teams,
        "experiment": experiment,
    }


def make_match(graph, index, *, at=None, price="2.0000", action="HOME", eligible=True):
    at = at or datetime(2026, 9, 14, 15, tzinfo=timezone.utc)
    match = Match.objects.create(
        season=graph["season"],
        home_team=graph["teams"][index * 2],
        away_team=graph["teams"][index * 2 + 1],
        kickoff=at + timedelta(minutes=30 + index),
        status_short="NS",
        status_long="Not Started",
    )
    prediction = Prediction.objects.create(
        experiment=graph["experiment"],
        match=match,
        model_code=Prediction.DIXON_COLES,
        model_version="test-v1",
        model_config={},
        cutoff=match.kickoff - timedelta(microseconds=1),
        p_home=0.6,
        p_draw=0.25,
        p_away=0.15,
        predicted_outcome=Match.OUTCOME_HOME,
        bet_eligible=eligible,
    )
    decision = Decision.objects.create(
        experiment=graph["experiment"],
        match=match,
        prediction=prediction,
        policy_code="MODAL_ALL",
        policy_version="fs003-modal-all-v1",
        policy_config={},
        decision_time=prediction.cutoff,
        action=action,
        reason="MODAL_OUTCOME" if action != "NO_BET" else "READINESS_NOT_MET",
        model_probability=0.6 if action != "NO_BET" else None,
    )
    observation = None
    if price is not None:
        observation = OddsObservation.objects.create(
            match=match,
            source=graph["source"],
            bookmaker=graph["bookmaker"],
            market=graph["market"],
            home=Decimal(price),
            draw=Decimal("3.2000"),
            away=Decimal("5.0000"),
            observed_at=at + timedelta(minutes=1),
        )
    return match, decision, observation


def make_capture(graph, matches, *, at=None, statuses=None):
    at = at or datetime(2026, 9, 14, 15, tzinfo=timezone.utc)
    run = CaptureRun.objects.create(
        trigger=CaptureRun.Trigger.MANUAL,
        status=CaptureRun.Status.SUCCESS,
        planning_at=at,
        started_at=at,
        completed_at=at + timedelta(minutes=5),
        config_snapshot={},
    )
    rows = []
    for index, match in enumerate(matches):
        status = statuses[index] if statuses else CaptureWorkItem.Status.SUCCESS
        rows.append(
            CaptureWorkItem.objects.create(
                run=run,
                purpose=CaptureWorkItem.Purpose.ODDS_CAPTURE,
                status=status,
                source=graph["source"],
                match=match,
                market=graph["market"],
                logical_identity=f"t30:{run.pk}:{match.pk}:{status}",
                intended_window="market-t30m",
                target_at=at,
                not_before=at,
                not_after=at + timedelta(minutes=15),
                executed_at=(
                    at if status != CaptureWorkItem.Status.MISSED_WINDOW else None
                ),
                completed_at=at + timedelta(minutes=4),
            )
        )
    return run, rows


def add_api_football_ref(graph, match, *, external_id=None):
    return MatchSourceRef.objects.create(
        source=graph["source"],
        match=match,
        external_id=external_id or f"fixture-{match.pk}",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )


def make_manual_config(*, policy_code, policy_config, policy_state=None, max_lanes=1):
    return CapitalRuntimeConfig.objects.create(
        identity=f"manual:{policy_code}:{CapitalRuntimeConfig.objects.count()}",
        runtime_version=RUNTIME_VERSION,
        execution_version=EXECUTION_VERSION,
        mode=CapitalRuntimeConfig.Mode.CURRENT,
        source_model_code=Prediction.DIXON_COLES,
        decision_policy_code="MODAL_ALL",
        policy_code=policy_code,
        policy_version="manual-test-v1",
        policy_config=policy_config,
        max_lanes=max_lanes,
        initial_bankroll=Decimal("100"),
        bankroll_equity=Decimal("100"),
        policy_state=policy_state or {},
        peak_equity=Decimal("100"),
    )


def prepare_study_decision(match, decision, observation, *, status, outcome):
    decision.selected_odds_observation = observation
    decision.selected_price = observation.home
    decision.save()
    match.status_short = status
    match.outcome = outcome
    match.save()


def test_exact_automatic_provisioning_is_idempotent_and_independent():
    first = provision_automatic_configs()
    second = provision_automatic_configs()

    assert [row.pk for row in first] == [row.pk for row in second]
    assert CapitalRuntimeConfig.objects.count() == 7
    assert {(row.policy_code, row.max_lanes) for row in first} == {
        (code, lanes) for code, _, lanes in AUTOMATIC_CONFIGS
    }
    assert all(row.initial_bankroll == Decimal("100") for row in first)
    assert all(row.bankroll_equity == Decimal("100") for row in first)
    assert all(row.reserved_exposure == 0 for row in first)
    assert all(row.runtime_version == RUNTIME_VERSION for row in first)
    assert all(row.execution_version == EXECUTION_VERSION for row in first)


def test_final_t30_places_concurrent_policies_and_retains_pending_capacity(
    runtime_graph,
):
    high, _, _ = make_match(runtime_graph, 0, price="2.1000")
    low, _, _ = make_match(runtime_graph, 1, price="1.8000")
    run, _ = make_capture(runtime_graph, [low, high])

    result = reconcile_execution_events(run.pk)

    assert result.placed == 11
    assert result.not_placed == 0
    assert result.pending_capacity == 3
    for code in (
        FLAT_UNIT,
        FIXED_FRACTION_BANKROLL,
        FIXED_TARGET_PROFIT_NO_RECOVERY,
        FRACTIONAL_KELLY,
    ):
        config = CapitalRuntimeConfig.objects.get(policy_code=code, automatic=True)
        assert config.positions.filter(status=CapitalPosition.Status.OPEN).count() == 2
        assert config.bankroll_equity == Decimal("100")
        assert config.reserved_exposure > 0
        assert (
            config.available_cash == config.bankroll_equity - config.reserved_exposure
        )
    for code in (LEGACY_RECOVERY, LEGACY_CAPPED, LEGACY_PARTIAL):
        config = CapitalRuntimeConfig.objects.get(policy_code=code, automatic=True)
        assert config.positions.filter(status=CapitalPosition.Status.OPEN).count() == 1
        state = config.execution_states.get(match=low)
        assert state.status == CapitalExecutionState.Status.PENDING_CAPACITY
        assert state.position_id is None

    flat = CapitalRuntimeConfig.objects.get(policy_code=FLAT_UNIT, automatic=True)
    position = flat.positions.get(match=high)
    assert position.placed_at == run.work_items.get(match=high).completed_at
    assert position.execution_basis.selected_odds_observation.match == high
    assert (
        position.execution_basis.evidence_not_before
        <= (position.execution_basis.selected_odds_observation.observed_at)
        < position.execution_basis.evidence_cutoff
    )
    counts = (
        CapitalExecutionState.objects.count(),
        CapitalPosition.objects.count(),
        sum(row.reserved_exposure for row in CapitalRuntimeConfig.objects.all()),
    )
    assert reconcile_execution_events(run.pk).status == "NO_WORK"
    assert counts == (
        CapitalExecutionState.objects.count(),
        CapitalPosition.objects.count(),
        sum(row.reserved_exposure for row in CapitalRuntimeConfig.objects.all()),
    )


def test_no_t30_never_places_and_explicit_terminal_reasons_are_durable(runtime_graph):
    match, _, _ = make_match(runtime_graph, 0)
    early_run, _ = make_capture(runtime_graph, [match])
    early_run.work_items.update(intended_window="market-t60m")

    assert reconcile_execution_events(early_run.pk).placed == 0
    assert not CapitalPosition.objects.exists()

    missed_run, _ = make_capture(
        runtime_graph,
        [match],
        statuses=[CaptureWorkItem.Status.MISSED_WINDOW],
    )
    result = reconcile_execution_events(missed_run.pk)
    assert result.not_placed == 7
    assert set(
        CapitalExecutionState.objects.values_list("non_placement_reason", flat=True)
    ) == {"MISSED_EXECUTION_WINDOW"}
    assert reconcile_execution_events(missed_run.pk).status == "NO_WORK"


def test_execution_time_no_bet_is_terminal(runtime_graph):
    match, _, _ = make_match(runtime_graph, 0, action="NO_BET", eligible=False)
    run, _ = make_capture(runtime_graph, [match])

    result = reconcile_execution_events(run.pk)

    assert result.placed == 0
    assert result.not_placed == 7
    assert set(
        CapitalExecutionState.objects.values_list("non_placement_reason", flat=True)
    ) == {"NO_BET"}
    assert not CapitalPosition.objects.exists()


def test_value_is_revalidated_against_final_price_without_mixing(runtime_graph):
    at = datetime(2026, 9, 14, 15, tzinfo=timezone.utc)
    match, modal, _ = make_match(runtime_graph, 0, at=at, price=None)
    old_observation = OddsObservation.objects.create(
        match=match,
        source=runtime_graph["source"],
        bookmaker=runtime_graph["bookmaker"],
        market=runtime_graph["market"],
        home=Decimal("2.2000"),
        draw=Decimal("4.5000"),
        away=Decimal("8.0000"),
        observed_at=at - timedelta(hours=1),
    )
    value = Decision.objects.create(
        experiment=runtime_graph["experiment"],
        match=match,
        prediction=modal.prediction,
        policy_code="VALUE",
        policy_variant="0.00",
        policy_version="fs003-value-v1",
        policy_config={"minimum_ev": 0},
        decision_time=modal.decision_time,
        action="HOME",
        reason="VALUE_ABOVE_THRESHOLD",
        model_probability=0.6,
        selected_odds_observation=old_observation,
        selected_price=old_observation.home,
        expected_value=0.32,
    )
    final_observation = OddsObservation.objects.create(
        match=match,
        source=runtime_graph["source"],
        bookmaker=runtime_graph["bookmaker"],
        market=runtime_graph["market"],
        home=Decimal("1.2000"),
        draw=Decimal("1.2000"),
        away=Decimal("1.2000"),
        observed_at=at + timedelta(minutes=1),
    )
    run, work = make_capture(runtime_graph, [match], at=at)

    candidate = build_execution_candidate(
        work[0], policy_code="VALUE", policy_variant="0.00"
    )

    assert candidate.decision == value
    assert candidate.result.action == Decision.ACTION_NO_BET
    assert candidate.selected_price is None
    assert candidate.selected_observation_id is None
    assert final_observation.pk != old_observation.pk
    assert run.completed_at > final_observation.observed_at


@pytest.mark.parametrize(
    ("outcome", "expected_status", "expected_pnl"),
    (
        (Match.OUTCOME_HOME, CapitalPosition.Status.SETTLED_WIN, Decimal("1.1")),
        (Match.OUTCOME_AWAY, CapitalPosition.Status.SETTLED_LOSS, Decimal("-1")),
    ),
)
def test_win_and_loss_settle_exactly_once(
    runtime_graph, outcome, expected_status, expected_pnl
):
    match, _, _ = make_match(runtime_graph, 0, price="2.1000")
    run, _ = make_capture(runtime_graph, [match])
    reconcile_execution_events(run.pk)
    flat = CapitalRuntimeConfig.objects.get(policy_code=FLAT_UNIT, automatic=True)
    match.status_short = "FT"
    match.status_long = "Match Finished"
    match.outcome = outcome
    match.save()
    add_api_football_ref(runtime_graph, match)
    known_at = datetime(2026, 9, 14, 20, tzinfo=timezone.utc)

    observation, created = observe_terminal_result(match, known_at=known_at)
    assert created
    assert settle_observation(observation, settled_at=known_at) == 7
    assert settle_observation(observation, settled_at=known_at) == 0

    flat.refresh_from_db()
    position = flat.positions.get()
    assert position.status == expected_status
    assert position.realized_pnl == expected_pnl
    assert position.result_known_at == known_at
    assert flat.reserved_exposure == 0
    assert flat.bankroll_equity == Decimal("100") + expected_pnl
    assert CapitalResultObservation.objects.count() == 1


def test_void_releases_recovery_without_changing_state(runtime_graph):
    match, _, _ = make_match(runtime_graph, 0)
    run, _ = make_capture(runtime_graph, [match])
    reconcile_execution_events(run.pk)
    recovery = CapitalRuntimeConfig.objects.get(
        policy_code=LEGACY_RECOVERY, automatic=True
    )
    before = recovery.policy_state
    match.status_short = "CANC"
    match.status_long = "Cancelled"
    match.save()
    add_api_football_ref(runtime_graph, match)

    observation, _ = observe_terminal_result(match)
    settle_observation(observation)

    recovery.refresh_from_db()
    position = recovery.positions.get()
    assert position.status == CapitalPosition.Status.VOID
    assert position.realized_pnl == 0
    assert recovery.reserved_exposure == 0
    assert recovery.policy_state == before == position.policy_state_after


def test_blank_terminal_result_remains_visible_debt_and_provider_failure_is_soft(
    runtime_graph,
    settings,
):
    match, _, _ = make_match(runtime_graph, 0)
    run, _ = make_capture(runtime_graph, [match])
    reconcile_execution_events(run.pk)
    match.status_short = "FT"
    match.status_long = "Match Finished"
    match.outcome = ""
    match.kickoff = datetime(2026, 9, 14, 10, tzinfo=timezone.utc)
    match.save()
    MatchSourceRef.objects.create(
        source=runtime_graph["source"],
        match=match,
        external_id="2000",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    settings.FOOTBALL_CAPTURE_RESULT_DELAY_MINUTES = 0

    assert observe_terminal_result(match)[0] is None

    def unavailable(**kwargs):
        del kwargs
        raise APIFootballQuotaReserveError("quota reserved")

    result = refresh_open_result_debt(
        at=datetime(2026, 9, 14, 20, tzinfo=timezone.utc),
        client_factory=unavailable,
    )

    assert result.status == "DEGRADED"
    assert result.open_debt == 7
    assert (
        CapitalPosition.objects.filter(
            status=CapitalPosition.Status.OPEN,
            debt_status=CapitalPosition.DebtStatus.DEGRADED,
        ).count()
        == 7
    )
    assert result.errors == ("APIFootballQuotaReserveError:quota reserved",)
    assert all(
        row.config.reserved_exposure > 0 for row in CapitalPosition.objects.all()
    )


def test_zero_open_debt_never_constructs_provider_client():
    called = False

    def forbidden(**kwargs):
        nonlocal called
        called = True
        del kwargs

    result = refresh_open_result_debt(client_factory=forbidden)

    assert result.status == "NO_WORK"
    assert result.provider_calls == 0
    assert not called


def test_unavailable_price_cash_and_policy_ineligible_reasons_are_distinct(
    runtime_graph,
):
    unavailable, _, _ = make_match(runtime_graph, 0)
    Decision.objects.filter(match=unavailable).delete()
    unavailable_run, _ = make_capture(runtime_graph, [unavailable])
    reconcile_execution_events(unavailable_run.pk)
    assert set(
        CapitalExecutionState.objects.filter(match=unavailable).values_list(
            "non_placement_reason", flat=True
        )
    ) == {"UNAVAILABLE_NO_DECISION_AT_EXECUTION"}

    no_price, _, _ = make_match(runtime_graph, 1, price=None)
    no_price_run, _ = make_capture(runtime_graph, [no_price])
    reconcile_execution_events(no_price_run.pk)
    assert set(
        CapitalExecutionState.objects.filter(match=no_price).values_list(
            "non_placement_reason", flat=True
        )
    ) == {"NO_EXECUTION_PRICE"}

    cash, _, _ = make_match(runtime_graph, 2)
    flat = CapitalRuntimeConfig.objects.get(policy_code=FLAT_UNIT, automatic=True)
    flat.bankroll_equity = Decimal("0.5")
    flat.peak_equity = Decimal("100")
    flat.save()
    cash_run, _ = make_capture(runtime_graph, [cash])
    reconcile_execution_events(cash_run.pk)
    cash_state = CapitalExecutionState.objects.get(config=flat, match=cash)
    assert cash_state.status == CapitalExecutionState.Status.PENDING_CAPACITY
    assert cash_state.diagnostics["reason"] == "INSUFFICIENT_AVAILABLE_CASH"
    flat.refresh_from_db()
    assert flat.status == CapitalRuntimeConfig.Status.ACTIVE
    assert flat.practical_ruin is False

    ineligible, _, observation = make_match(runtime_graph, 3, price="1.2000")
    observation.draw = Decimal("1.2000")
    observation.away = Decimal("1.2000")
    observation.save()
    ineligible_run, _ = make_capture(runtime_graph, [ineligible])
    reconcile_execution_events(ineligible_run.pk)
    kelly = CapitalRuntimeConfig.objects.get(
        policy_code=FRACTIONAL_KELLY, automatic=True
    )
    assert (
        CapitalExecutionState.objects.get(
            config=kelly, match=ineligible
        ).non_placement_reason
        == "INELIGIBLE"
    )


def test_explicit_policy_termination_is_practical_ruin_without_position(runtime_graph):
    match, _, _ = make_match(runtime_graph, 0)
    run, work = make_capture(runtime_graph, [match])
    config = make_manual_config(
        policy_code=LEGACY_CAPPED,
        policy_config={"initial_stake": "1", "max_recovery_steps": 1},
        policy_state={"target_profit": "1", "accumulated_loss": "1", "step": 1},
    )

    outcome = place_candidate(config.pk, build_execution_candidate(work[0]))

    config.refresh_from_db()
    state = config.execution_states.get(match=match)
    assert outcome == "NOT_PLACED"
    assert config.status == CapitalRuntimeConfig.Status.TERMINATED
    assert config.practical_ruin is True
    assert config.termination_reason == "MAX_RECOVERY_STEPS"
    assert config.completed_at == work[0].completed_at
    assert state.non_placement_reason == "INELIGIBLE"
    assert state.diagnostics == {"policy_reason": "MAX_RECOVERY_STEPS"}
    assert not config.positions.exists()


def test_pipeline_semantic_clock_does_not_backdate_local_result_knowledge(
    runtime_graph, monkeypatch
):
    match, _, _ = make_match(runtime_graph, 0)
    run, _ = make_capture(runtime_graph, [match])
    reconcile_execution_events(run.pk)
    add_api_football_ref(runtime_graph, match)
    match.status_short = "FT"
    match.outcome = Match.OUTCOME_HOME
    match.save()
    semantic_at = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
    actual_knowledge_at = datetime(2026, 9, 14, 21, tzinfo=timezone.utc)
    monkeypatch.setattr(
        "football.capital.runtime.timezone.now", lambda: actual_knowledge_at
    )

    result = run_automatic_runtime(capture_run_id=None, at=semantic_at)

    observation = CapitalResultObservation.objects.get(match=match)
    assert result.settled == 7
    assert observation.result_known_at == actual_knowledge_at
    assert observation.result_known_at != semantic_at


def test_terminal_match_without_api_authority_stays_open_until_canonical_refresh(
    runtime_graph, settings, monkeypatch
):
    match, _, _ = make_match(runtime_graph, 0)
    run, _ = make_capture(runtime_graph, [match])
    reconcile_execution_events(run.pk)
    due_at = datetime(2026, 9, 14, 20, tzinfo=timezone.utc)
    knowledge_at = datetime(2026, 9, 14, 21, tzinfo=timezone.utc)
    match.kickoff = due_at - timedelta(hours=3)
    match.status_short = "FT"
    match.outcome = Match.OUTCOME_HOME
    match.save()

    assert settle_locally_known_open_positions(known_at=knowledge_at) == 0
    assert not CapitalResultObservation.objects.exists()
    assert (
        CapitalPosition.objects.filter(status=CapitalPosition.Status.OPEN).count() == 7
    )
    assert set(CapitalPosition.objects.values_list("debt_status", flat=True)) == {
        CapitalPosition.DebtStatus.DEGRADED
    }

    CompetitionSourceRef.objects.create(
        source=runtime_graph["source"],
        competition=runtime_graph["competition"],
        external_id="399",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    add_api_football_ref(runtime_graph, match, external_id="3000")
    settings.FOOTBALL_CAPTURE_RESULT_DELAY_MINUTES = 0

    class FakeClient:
        def __init__(self, **kwargs):
            del kwargs
            self.calls = 0

        def get_all(self, endpoint, params):
            assert endpoint == "fixtures"
            assert params == {"date": "2026-09-14", "timezone": "America/Lima"}
            self.calls += 1
            return [{"fixture": {"id": 3000}}]

    def canonical_sync(payloads, competitions):
        assert payloads == [{"fixture": {"id": 3000}}]
        assert set(competitions) == {"399"}
        Match.objects.filter(pk=match.pk).update(
            status_short="FT", outcome=Match.OUTCOME_HOME
        )
        return None, {"3000": match}

    monkeypatch.setattr(
        "football.capital.runtime.sync_fixture_payloads", canonical_sync
    )
    monkeypatch.setattr("football.capital.runtime.timezone.now", lambda: knowledge_at)

    result = refresh_open_result_debt(at=due_at, client_factory=FakeClient)

    observation = CapitalResultObservation.objects.get(match=match)
    assert result.settled == 7
    assert result.provider_calls == 1
    assert observation.source == runtime_graph["source"]
    assert observation.match_source_ref.external_id == "3000"
    assert observation.result_known_at == knowledge_at
    assert not CapitalPosition.objects.filter(
        status=CapitalPosition.Status.OPEN
    ).exists()


def test_recovery_continues_only_after_real_settlement(runtime_graph):
    first, _, _ = make_match(runtime_graph, 0)
    first_run, _ = make_capture(runtime_graph, [first])
    reconcile_execution_events(first_run.pk)
    recovery = CapitalRuntimeConfig.objects.get(
        policy_code=LEGACY_RECOVERY, automatic=True
    )
    first.status_short = "FT"
    first.outcome = Match.OUTCOME_AWAY
    first.save()
    add_api_football_ref(runtime_graph, first)
    observation, _ = observe_terminal_result(first)
    settle_observation(observation)
    recovery.refresh_from_db()
    assert recovery.policy_state["step"] == 1
    assert recovery.policy_state["accumulated_loss"] == "1.00000000"

    second, _, _ = make_match(runtime_graph, 1)
    second_run, _ = make_capture(runtime_graph, [second])
    reconcile_execution_events(second_run.pk)
    second_position = recovery.positions.get(match=second)
    assert second_position.status == CapitalPosition.Status.OPEN
    assert second_position.requested_stake == Decimal("2")
    assert second_position.policy_state_before["step"] == 1


def test_successful_t30_remains_valid_when_capital_reconciliation_is_delayed(
    runtime_graph,
):
    match, _, _ = make_match(runtime_graph, 0)
    run, work = make_capture(runtime_graph, [match])

    result = reconcile_execution_events(
        run.pk, at=work[0].not_after + timedelta(seconds=1)
    )

    assert result.placed == 7
    assert result.not_placed == 0
    assert not CapitalExecutionState.objects.filter(
        non_placement_reason="MISSED_EXECUTION_WINDOW"
    ).exists()


def test_partial_t30_processing_recovers_original_fulfilled_evidence(
    runtime_graph, monkeypatch
):
    match, original_decision, _ = make_match(runtime_graph, 0)
    original_run, original_work = make_capture(runtime_graph, [match])
    real_place_candidate = place_candidate
    calls = 0

    def interrupted_place(config_id, candidate):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise RuntimeError("simulated Capital interruption")
        return real_place_candidate(config_id, candidate)

    monkeypatch.setattr("football.capital.runtime.place_candidate", interrupted_place)
    with pytest.raises(RuntimeError, match="simulated Capital interruption"):
        reconcile_execution_events(original_run.pk)

    completed_before = {
        state.config_id: (
            state.pk,
            state.position_id,
            state.execution_basis_id,
        )
        for state in CapitalExecutionState.objects.all()
    }
    assert len(completed_before) == 3

    later_experiment = PredictionExperiment.objects.create(
        competition=runtime_graph["competition"],
        mode=PredictionExperiment.MODE_PROSPECTIVE,
        period_start=date(2026, 9, 15),
        period_end=date(2026, 9, 15),
    )
    later_prediction = Prediction.objects.create(
        experiment=later_experiment,
        match=match,
        model_code=Prediction.DIXON_COLES,
        model_version="later-v1",
        model_config={},
        cutoff=match.kickoff - timedelta(microseconds=1),
        p_home=0.1,
        p_draw=0.1,
        p_away=0.8,
        predicted_outcome=Match.OUTCOME_AWAY,
        bet_eligible=True,
    )
    Decision.objects.create(
        experiment=later_experiment,
        match=match,
        prediction=later_prediction,
        policy_code="MODAL_ALL",
        policy_version="later-modal-v1",
        policy_config={},
        decision_time=later_prediction.cutoff,
        action=Match.OUTCOME_AWAY,
        reason="MODAL_OUTCOME",
        model_probability=0.8,
    )
    retry_at = original_work[0].not_after + timedelta(hours=1)
    retry_run, retry_work = make_capture(
        runtime_graph,
        [match],
        at=retry_at,
        statuses=[CaptureWorkItem.Status.ALREADY_FULFILLED],
    )
    retry_work[0].logical_identity = original_work[0].logical_identity
    retry_work[0].save(update_fields=["logical_identity"])
    monkeypatch.setattr(
        "football.capital.runtime.place_candidate", real_place_candidate
    )

    recovered = reconcile_execution_events(retry_run.pk, at=retry_at)

    assert recovered.placed == 0
    assert recovered.not_placed == 4
    assert CapitalExecutionState.objects.count() == 7
    assert {
        state.config_id: (state.pk, state.position_id, state.execution_basis_id)
        for state in CapitalExecutionState.objects.filter(
            config_id__in=completed_before
        )
    } == completed_before
    assert set(
        CapitalExecutionBasis.objects.values_list("capture_work_item_id", flat=True)
    ) == {original_work[0].pk}
    assert set(
        CapitalExecutionBasis.objects.values_list("originating_decision_id", flat=True)
    ) == {original_decision.pk}
    assert set(CapitalExecutionBasis.objects.values_list("action", flat=True)) == {
        Match.OUTCOME_HOME
    }
    assert (
        CapitalExecutionState.objects.filter(
            non_placement_reason="EXPIRED_CAPACITY"
        ).count()
        == 4
    )
    assert reconcile_execution_events(retry_run.pk, at=retry_at).status == "NO_WORK"


def test_capacity_ranks_ev_before_probability(runtime_graph):
    high_probability, high_probability_decision, _ = make_match(
        runtime_graph, 0, price="1.5000"
    )
    high_probability_decision.prediction.p_home = 0.7
    high_probability_decision.prediction.p_draw = 0.2
    high_probability_decision.prediction.p_away = 0.1
    high_probability_decision.prediction.save()
    high_ev, high_ev_decision, _ = make_match(runtime_graph, 1, price="2.2000")
    high_ev_decision.prediction.p_home = 0.55
    high_ev_decision.prediction.p_draw = 0.3
    high_ev_decision.prediction.p_away = 0.15
    high_ev_decision.prediction.save()
    run, _ = make_capture(runtime_graph, [high_probability, high_ev])

    reconcile_execution_events(run.pk)

    recovery = CapitalRuntimeConfig.objects.get(
        policy_code=LEGACY_RECOVERY, automatic=True
    )
    assert recovery.positions.get().match == high_ev
    assert (
        recovery.execution_states.get(match=high_probability).status
        == CapitalExecutionState.Status.PENDING_CAPACITY
    )


def test_capacity_tie_breaks_by_kickoff_then_stable_match_identity(runtime_graph):
    later, _, _ = make_match(runtime_graph, 0, price="2.0000")
    earlier, _, _ = make_match(runtime_graph, 1, price="2.0000")
    earlier.kickoff = later.kickoff - timedelta(minutes=1)
    earlier.save()
    run, _ = make_capture(runtime_graph, [later, earlier])

    reconcile_execution_events(run.pk)

    recovery = CapitalRuntimeConfig.objects.get(
        policy_code=LEGACY_RECOVERY, automatic=True
    )
    assert recovery.positions.get().match == earlier

    # Equal kickoff and EV fall through to stable Match identity.
    recovery.positions.all().delete()
    CapitalExecutionState.objects.filter(config=recovery).delete()
    recovery.execution_bases.all().delete()
    recovery.reserved_exposure = 0
    recovery.save()
    later.kickoff = earlier.kickoff
    later.save()
    second_run, _ = make_capture(runtime_graph, [later, earlier])
    reconcile_execution_events(second_run.pk)
    assert recovery.positions.get().match_id == min(later.pk, earlier.pk)


@pytest.mark.django_db(transaction=True)
def test_concurrent_workers_cannot_double_place_same_config_match(runtime_graph):
    match, _, _ = make_match(runtime_graph, 0)
    run, work = make_capture(runtime_graph, [match])
    candidate = build_execution_candidate(work[0])
    flat = provision_automatic_configs()[0]

    def place():
        close_old_connections()
        try:
            return place_candidate(flat.pk, candidate)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(lambda _: place(), range(2)))

    assert outcomes == ["NO_WORK", "PLACED"]
    assert CapitalPosition.objects.filter(config=flat, match=match).count() == 1
    flat.refresh_from_db()
    assert flat.reserved_exposure == Decimal("1")


def test_unique_open_matches_use_one_date_sweep_provider_request(
    runtime_graph, settings, monkeypatch
):
    first, _, _ = make_match(runtime_graph, 0)
    second, _, _ = make_match(runtime_graph, 1)
    run, _ = make_capture(runtime_graph, [first, second])
    reconcile_execution_events(run.pk)
    due_at = datetime(2026, 9, 14, 20, tzinfo=timezone.utc)
    Match.objects.filter(pk__in=(first.pk, second.pk)).update(
        kickoff=due_at - timedelta(hours=3)
    )
    CompetitionSourceRef.objects.create(
        source=runtime_graph["source"],
        competition=runtime_graph["competition"],
        external_id="99",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    MatchSourceRef.objects.create(
        source=runtime_graph["source"],
        match=first,
        external_id="1000",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    MatchSourceRef.objects.create(
        source=runtime_graph["source"],
        match=second,
        external_id="1001",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    settings.FOOTBALL_CAPTURE_RESULT_DELAY_MINUTES = 0

    class FakeClient:
        instance = None

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.calls = 0
            self.requests = []
            type(self).instance = self

        def get_all(self, endpoint, params):
            self.calls += 1
            self.requests.append((endpoint, params))
            return [{"fixture": {"id": external_id}} for external_id in (1000, 1001)]

    def sync_stub(payloads, competitions):
        assert len(payloads) == 2
        assert set(competitions) == {"99"}
        Match.objects.filter(pk__in=(first.pk, second.pk)).update(
            status_short="FT", status_long="Match Finished", outcome="HOME"
        )
        return None, {"1000": first, "1001": second}

    monkeypatch.setattr("football.capital.runtime.sync_fixture_payloads", sync_stub)

    result = refresh_open_result_debt(at=due_at, client_factory=FakeClient)

    assert result.status == "PRODUCED"
    assert result.provider_calls == 1
    assert result.settled == 11
    assert result.open_debt == 0
    assert FakeClient.instance.requests == [
        ("fixtures", {"date": "2026-09-14", "timezone": "America/Lima"})
    ]
    assert CapitalResultObservation.objects.count() == 2


def test_result_debt_rotates_unattempted_then_least_recently_attempted_dates(
    runtime_graph, settings, monkeypatch
):
    base_at = datetime(2026, 9, 14, 15, tzinfo=timezone.utc)
    due_at = base_at + timedelta(hours=4)
    config = make_manual_config(
        policy_code=FLAT_UNIT,
        policy_config={"unit": "1"},
        max_lanes=100,
    )
    matches = []
    for index in range(2):
        match, _, _ = make_match(
            runtime_graph,
            index % 4,
            at=base_at + timedelta(seconds=index),
        )
        run, work = make_capture(runtime_graph, [match], at=base_at)
        assert (
            place_candidate(config.pk, build_execution_candidate(work[0])) == "PLACED"
        )
        external_id = str(9000 - index)
        add_api_football_ref(runtime_graph, match, external_id=external_id)
        match.kickoff = due_at - timedelta(days=index + 1)
        match.save(update_fields=["kickoff", "modified"])
        CapitalPosition.objects.filter(config=config, match=match).update(
            next_result_check_at=due_at
        )
        matches.append(match)
    CompetitionSourceRef.objects.create(
        source=runtime_graph["source"],
        competition=runtime_graph["competition"],
        external_id="499",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    settings.FOOTBALL_CAPTURE_RESULT_DELAY_MINUTES = 0
    settings.FOOTBALL_CAPTURE_MAX_PROVIDER_ATTEMPTS = 1
    requests = []

    class FakeClient:
        def __init__(self, **kwargs):
            del kwargs
            self.calls = 0

        def get_all(self, endpoint, params):
            assert endpoint == "fixtures"
            self.calls += 1
            requests.append(params)
            fixture_id = 9000 if params["date"] == "2026-09-13" else 8999
            return [{"fixture": {"id": fixture_id}}]

    monkeypatch.setattr(
        "football.capital.runtime.sync_fixture_payloads",
        lambda payloads, competitions: (
            None,
            {
                str(item["fixture"]["id"]): matches[
                    0 if item["fixture"]["id"] == 9000 else 1
                ]
                for item in payloads
            },
        ),
    )
    ordered = sorted(matches, key=lambda match: (match.kickoff, match.pk))

    first = refresh_open_result_debt(at=due_at, client_factory=FakeClient)

    assert first.provider_calls == 1
    assert requests[0] == {"date": "2026-09-12", "timezone": "America/Lima"}
    never_attempted = CapitalPosition.objects.get(config=config, match=ordered[1])
    assert never_attempted.result_refresh_attempted_at is None

    second_at = due_at + timedelta(minutes=1)
    second = refresh_open_result_debt(at=second_at, client_factory=FakeClient)

    assert second.provider_calls == 1
    assert requests[1] == {"date": "2026-09-13", "timezone": "America/Lima"}
    least_recent = CapitalPosition.objects.get(config=config, match=ordered[0])
    assert least_recent.result_refresh_attempted_at == due_at

    third = refresh_open_result_debt(
        at=due_at + timedelta(minutes=2), client_factory=FakeClient
    )

    assert third.provider_calls == 0
    fourth = refresh_open_result_debt(
        at=due_at + timedelta(minutes=30), client_factory=FakeClient
    )
    assert fourth.provider_calls == 1
    assert requests[2] == requests[0]
    assert (
        CapitalPosition.objects.filter(
            config=config, status=CapitalPosition.Status.OPEN
        ).count()
        == 2
    )


def test_generic_result_planner_defers_open_capital_debt_to_batch_owner(
    runtime_graph, settings
):
    match, _, _ = make_match(runtime_graph, 0)
    run, _ = make_capture(runtime_graph, [match])
    reconcile_execution_events(run.pk)
    at = datetime(2026, 9, 14, 20, tzinfo=timezone.utc)
    match.kickoff = at - timedelta(hours=3)
    match.save()
    settings.FOOTBALL_CAPTURE_RESULT_DELAY_MINUTES = 0

    plan = CapturePlanner(config=CaptureConfig.from_settings()).plan(
        at=at,
        match_id=match.pk,
        purpose=CaptureWorkItem.Purpose.RESULT_REFRESH,
    )

    assert plan.items == []


@pytest.mark.parametrize(
    "mode",
    (
        CapitalRuntimeConfig.Mode.REPLAY,
        CapitalRuntimeConfig.Mode.MONTE_CARLO,
        CapitalRuntimeConfig.Mode.STRESS,
    ),
)
def test_replay_monte_carlo_and_stress_persist_v2_chronology(runtime_graph, mode):
    first, first_decision, first_observation = make_match(runtime_graph, 0)
    second, second_decision, second_observation = make_match(runtime_graph, 1)
    for decision, observation in (
        (first_decision, first_observation),
        (second_decision, second_observation),
    ):
        decision.selected_odds_observation = observation
        decision.selected_price = observation.home
        decision.save()
    first.status_short = second.status_short = "FT"
    first.outcome = second.outcome = Match.OUTCOME_HOME
    first.save()
    second.save()

    config = run_persisted_v2_study(
        [first_decision, second_decision],
        policy_code=FLAT_UNIT,
        policy_config={"unit": "1"},
        mode=mode,
        seed=7,
        path_count=3 if mode != CapitalRuntimeConfig.Mode.REPLAY else 1,
        stress=(
            {"price_haircut": 0.05} if mode == CapitalRuntimeConfig.Mode.STRESS else {}
        ),
    )

    assert config.runtime_version == RUNTIME_VERSION
    assert config.status == CapitalRuntimeConfig.Status.COMPLETE
    assert config.metrics["chronology"] == "FS016_EVENT_TIME_V2"
    assert config.metrics["path_count"] == (
        1 if mode == CapitalRuntimeConfig.Mode.REPLAY else 3
    )
    assert config.positions.count() == 2
    assert all(position.settled_at for position in config.positions.all())
    assert config.metrics["no_winner_claim"] is True


def test_study_explicit_policy_termination_stops_later_capital_actions(runtime_graph):
    first, first_decision, first_observation = make_match(runtime_graph, 0)
    second, second_decision, second_observation = make_match(runtime_graph, 1)
    third, third_decision, third_observation = make_match(runtime_graph, 2)
    first_settlement = first.kickoff + timedelta(hours=2)
    second_observation.observed_at = first_settlement + timedelta(minutes=30)
    second_observation.save()
    second.kickoff = second_observation.observed_at + timedelta(minutes=30)
    second.save()
    third_observation.observed_at = second.kickoff + timedelta(hours=3)
    third_observation.save()
    third.kickoff = third_observation.observed_at + timedelta(minutes=30)
    third.save()
    prepare_study_decision(
        first,
        first_decision,
        first_observation,
        status="FT",
        outcome=Match.OUTCOME_AWAY,
    )
    prepare_study_decision(
        second,
        second_decision,
        second_observation,
        status="FT",
        outcome=Match.OUTCOME_HOME,
    )
    prepare_study_decision(
        third,
        third_decision,
        third_observation,
        status="FT",
        outcome=Match.OUTCOME_HOME,
    )

    config = run_persisted_v2_study(
        [first_decision, second_decision, third_decision],
        policy_code=LEGACY_CAPPED,
        policy_config={"initial_stake": "1", "max_recovery_steps": 1},
        mode=CapitalRuntimeConfig.Mode.REPLAY,
    )

    assert config.status == CapitalRuntimeConfig.Status.TERMINATED
    assert config.practical_ruin is True
    assert config.termination_reason == "MAX_RECOVERY_STEPS"
    assert config.positions.count() == 1
    assert config.positions.get().match == first
    second_state = config.execution_states.get(match=second)
    assert second_state.non_placement_reason == "INELIGIBLE"
    assert second_state.diagnostics == {"policy_reason": "MAX_RECOVERY_STEPS"}
    assert not config.execution_states.filter(match=third).exists()


def test_study_funded_bankroll_depletion_stops_later_capital_actions(runtime_graph):
    first, first_decision, first_observation = make_match(runtime_graph, 0)
    second, second_decision, second_observation = make_match(runtime_graph, 1)
    first_settlement = first.kickoff + timedelta(hours=2)
    second_observation.observed_at = first_settlement + timedelta(minutes=30)
    second_observation.save()
    second.kickoff = second_observation.observed_at + timedelta(minutes=30)
    second.save()
    prepare_study_decision(
        first,
        first_decision,
        first_observation,
        status="FT",
        outcome=Match.OUTCOME_AWAY,
    )
    prepare_study_decision(
        second,
        second_decision,
        second_observation,
        status="FT",
        outcome=Match.OUTCOME_HOME,
    )

    config = run_persisted_v2_study(
        [first_decision, second_decision],
        policy_code=FLAT_UNIT,
        policy_config={"unit": "100"},
        mode=CapitalRuntimeConfig.Mode.REPLAY,
    )

    position = config.positions.get()
    assert position.match == first
    assert position.status == CapitalPosition.Status.SETTLED_LOSS
    assert position.applied_stake == Decimal("100")
    assert position.realized_pnl == Decimal("-100")
    assert position.practical_ruin is True
    assert position.termination_reason == "BANKROLL_DEPLETED"
    assert config.bankroll_equity == 0
    assert config.status == CapitalRuntimeConfig.Status.TERMINATED
    assert config.practical_ruin is True
    assert config.termination_reason == "BANKROLL_DEPLETED"
    assert not config.execution_states.filter(match=second).exists()


def test_study_insufficient_available_cash_is_not_practical_ruin(runtime_graph):
    first, first_decision, first_observation = make_match(runtime_graph, 0)
    second, second_decision, second_observation = make_match(runtime_graph, 1)
    for match, decision, observation in (
        (first, first_decision, first_observation),
        (second, second_decision, second_observation),
    ):
        prepare_study_decision(
            match,
            decision,
            observation,
            status="FT",
            outcome=Match.OUTCOME_AWAY,
        )

    config = run_persisted_v2_study(
        [first_decision, second_decision],
        policy_code=FLAT_UNIT,
        policy_config={"unit": "200"},
        mode=CapitalRuntimeConfig.Mode.REPLAY,
    )

    assert config.status == CapitalRuntimeConfig.Status.COMPLETE
    assert config.practical_ruin is False
    assert config.termination_reason == ""
    assert not config.positions.exists()
    assert set(
        config.execution_states.values_list("non_placement_reason", flat=True)
    ) == {"INSUFFICIENT_AVAILABLE_CASH"}


@pytest.mark.parametrize(
    "mode",
    (
        CapitalRuntimeConfig.Mode.REPLAY,
        CapitalRuntimeConfig.Mode.MONTE_CARLO,
        CapitalRuntimeConfig.Mode.STRESS,
        CapitalRuntimeConfig.Mode.HISTORICAL,
    ),
)
def test_study_persists_peak_and_drawdown_from_full_settlement_trajectory(
    runtime_graph, mode
):
    first, first_decision, first_observation = make_match(
        runtime_graph, 0, price="2.0000"
    )
    second, second_decision, second_observation = make_match(
        runtime_graph, 1, price="1.6667"
    )
    first_settlement = first.kickoff + timedelta(hours=2)
    second_observation.observed_at = first_settlement + timedelta(minutes=30)
    second_observation.save()
    second.kickoff = second_observation.observed_at + timedelta(minutes=30)
    second.save()
    prepare_study_decision(
        first,
        first_decision,
        first_observation,
        status="FT",
        outcome=Match.OUTCOME_HOME,
    )
    prepare_study_decision(
        second,
        second_decision,
        second_observation,
        status="FT",
        outcome=Match.OUTCOME_AWAY,
    )
    first_decision.model_probability = 1
    first_decision.save(update_fields=["model_probability", "modified"])
    second_decision.model_probability = 0
    second_decision.save(update_fields=["model_probability", "modified"])
    if mode == CapitalRuntimeConfig.Mode.HISTORICAL:
        for match, home_price, row_identity in (
            (first, Decimal("2.0000"), "drawdown-first"),
            (second, Decimal("1.6667"), "drawdown-second"),
        ):
            HistoricalMarketEvidence.objects.create(
                match=match,
                source=runtime_graph["source"],
                home_price=home_price,
                draw_price=Decimal("3.0000"),
                away_price=Decimal("4.0000"),
                selected_group=(HistoricalMarketEvidence.PriceGroup.PINNACLE_CLOSING),
                time_semantics=HistoricalMarketEvidence.TimeSemantics.ASSUMED_T30M,
                source_competition="FS016 League",
                source_season="2026",
                source_file="drawdown.csv",
                source_file_checksum="c" * 64,
                source_row_identity=row_identity,
                provenance_version="fs015-football-data-v1",
            )

    config = run_persisted_v2_study(
        [first_decision, second_decision],
        policy_code=FIXED_TARGET_PROFIT_NO_RECOVERY,
        policy_config={"target_profit": "20"},
        mode=mode,
        seed=4,
    )
    config.refresh_from_db()

    assert config.peak_equity == Decimal("120")
    assert float(config.bankroll_equity) == pytest.approx(90.0015)
    assert float(config.maximum_drawdown) == pytest.approx(0.2499875, abs=1e-8)


def test_study_simple_loss_persists_ten_percent_drawdown(runtime_graph):
    match, decision, observation = make_match(runtime_graph, 0, price="2.0000")
    prepare_study_decision(
        match,
        decision,
        observation,
        status="FT",
        outcome=Match.OUTCOME_AWAY,
    )

    config = run_persisted_v2_study(
        [decision],
        policy_code=FLAT_UNIT,
        policy_config={"unit": "10"},
        mode=CapitalRuntimeConfig.Mode.REPLAY,
    )
    config.refresh_from_db()

    assert config.bankroll_equity == Decimal("90")
    assert config.peak_equity == Decimal("100")
    assert config.maximum_drawdown == Decimal("0.1")


def test_stress_forced_loss_interval_preserves_normal_outcomes_outside_it(
    runtime_graph,
):
    first, first_decision, first_observation = make_match(runtime_graph, 0)
    second, second_decision, second_observation = make_match(runtime_graph, 1)
    for match, decision, observation in (
        (first, first_decision, first_observation),
        (second, second_decision, second_observation),
    ):
        prepare_study_decision(
            match,
            decision,
            observation,
            status="FT",
            outcome=Match.OUTCOME_HOME,
        )

    config = run_persisted_v2_study(
        [first_decision, second_decision],
        policy_code=FLAT_UNIT,
        policy_config={"unit": "1"},
        mode=CapitalRuntimeConfig.Mode.STRESS,
        seed=4,
        stress={"forced_loss_start": 0, "forced_loss_length": 1},
    )

    assert (
        config.positions.get(match=first).status == CapitalPosition.Status.SETTLED_LOSS
    )
    assert (
        config.positions.get(match=second).status == CapitalPosition.Status.SETTLED_WIN
    )
    assert config.provenance["stress"] == {
        "probability_delta": 0.0,
        "price_haircut": 0.0,
        "forced_loss_start": 0,
        "forced_loss_length": 1,
    }


@pytest.mark.parametrize(
    ("status", "reason"),
    (
        ("NS", "UNSUPPORTED_CANONICAL_RESULT"),
        ("PST", "UNRESOLVED_CANONICAL_OUTCOME"),
        ("SUSP", "UNRESOLVED_CANONICAL_OUTCOME"),
        ("FT", "UNRESOLVED_CANONICAL_OUTCOME"),
    ),
)
def test_replay_unresolved_result_never_becomes_a_loss(runtime_graph, status, reason):
    match, decision, observation = make_match(runtime_graph, 0)
    prepare_study_decision(match, decision, observation, status=status, outcome="")

    with pytest.raises(RunUnavailable, match=reason):
        run_persisted_v2_study(
            [decision],
            policy_code=FLAT_UNIT,
            policy_config={"unit": "1"},
            mode=CapitalRuntimeConfig.Mode.REPLAY,
        )

    assert not CapitalRuntimeConfig.objects.exists()
    assert not CapitalPosition.objects.exists()


@pytest.mark.parametrize("status", ("CANC", "ABD"))
def test_deterministic_study_cancellation_or_abandonment_is_void(runtime_graph, status):
    match, decision, observation = make_match(runtime_graph, 0)
    prepare_study_decision(match, decision, observation, status=status, outcome="")

    config = run_persisted_v2_study(
        [decision],
        policy_code=LEGACY_RECOVERY,
        policy_config={"initial_stake": "1"},
        mode=CapitalRuntimeConfig.Mode.REPLAY,
    )

    position = config.positions.get()
    assert position.status == CapitalPosition.Status.VOID
    assert position.realized_pnl == 0
    assert position.policy_state_before == position.policy_state_after
    assert config.practical_ruin is False


def test_historical_blank_terminal_result_is_unavailable_not_loss(runtime_graph):
    match, decision, _ = make_match(runtime_graph, 0, price=None)
    match.status_short = "FT"
    match.outcome = ""
    match.save()
    HistoricalMarketEvidence.objects.create(
        match=match,
        source=runtime_graph["source"],
        home_price=Decimal("2.0000"),
        draw_price=Decimal("3.0000"),
        away_price=Decimal("4.0000"),
        selected_group=HistoricalMarketEvidence.PriceGroup.PINNACLE_CLOSING,
        time_semantics=HistoricalMarketEvidence.TimeSemantics.ASSUMED_T30M,
        source_competition="FS016 League",
        source_season="2026",
        source_file="unresolved.csv",
        source_file_checksum="b" * 64,
        source_row_identity="unresolved-row",
        provenance_version="fs015-football-data-v1",
    )

    with pytest.raises(RunUnavailable, match="UNRESOLVED_CANONICAL_OUTCOME"):
        run_persisted_v2_study(
            [decision],
            policy_code=FLAT_UNIT,
            policy_config={"unit": "1"},
            mode=CapitalRuntimeConfig.Mode.HISTORICAL,
        )

    assert not CapitalPosition.objects.exists()


def test_historical_study_preserves_fs015_synthetic_time_provenance(runtime_graph):
    match, decision, _ = make_match(runtime_graph, 0, price=None)
    match.status_short = "FT"
    match.outcome = Match.OUTCOME_HOME
    match.save()
    evidence = HistoricalMarketEvidence.objects.create(
        match=match,
        source=runtime_graph["source"],
        home_price=Decimal("2.0000"),
        draw_price=Decimal("3.0000"),
        away_price=Decimal("4.0000"),
        selected_group=HistoricalMarketEvidence.PriceGroup.PINNACLE_CLOSING,
        time_semantics=HistoricalMarketEvidence.TimeSemantics.ASSUMED_T30M,
        source_competition="FS016 League",
        source_season="2026",
        source_file="fixture.csv",
        source_file_checksum="a" * 64,
        source_row_identity="row-1",
        provenance_version="fs015-football-data-v1",
    )

    config = run_persisted_v2_study(
        [decision],
        policy_code=FLAT_UNIT,
        policy_config={"unit": "1"},
        mode=CapitalRuntimeConfig.Mode.HISTORICAL,
    )

    basis = config.execution_bases.get()
    assert basis.historical_market_evidence == evidence
    assert basis.evidence_class == "SYNTHETIC_TIME_RESEARCH_ONLY"
    assert basis.provenance["timestamp_is_imputed"] is True
    assert basis.provenance["time_semantics"] == "ASSUMED_T30M"
    assert basis.provenance["settlement_time"] == "SYNTHETIC_RESEARCH_ONLY"


def test_normal_reporting_surface_answers_current_capital_questions(runtime_graph):
    match, _, _ = make_match(runtime_graph, 0)
    run, _ = make_capture(runtime_graph, [match])
    reconcile_execution_events(run.pk)

    response = Client().get("/")
    content = response.content.decode()

    assert response.status_code == 200
    assert "Capital v2 CURRENT · event-time" in content
    assert "DIXON_COLES + MODAL_ALL" in content
    for value in (
        "FLAT_UNIT",
        "FIXED_FRACTION_BANKROLL",
        "FIXED_TARGET_PROFIT_NO_RECOVERY",
        "LEGACY_RECOVERY",
        "LEGACY_CAPPED",
        "LEGACY_PARTIAL",
        "FRACTIONAL_KELLY",
        "Reservado / disponible",
        "OPEN / capacidad",
        "PnL / ROI",
        "Ruina / terminación",
        "días",
        "Capital v1 legado / evidencia superseded (no CURRENT)",
    ):
        assert value in content


def test_current_realized_roi_uses_settled_stake_not_initial_bankroll(runtime_graph):
    match, _, _ = make_match(runtime_graph, 0, price="1.5000")
    run, _ = make_capture(runtime_graph, [match])
    reconcile_execution_events(run.pk)
    add_api_football_ref(runtime_graph, match)
    match.status_short = "FT"
    match.outcome = Match.OUTCOME_HOME
    match.save()
    observation, _ = observe_terminal_result(match)
    settle_observation(observation)

    row = next(
        item
        for item in _capital_v2_rows()
        if item["config"].policy_code == FIXED_TARGET_PROFIT_NO_RECOVERY
    )

    assert row["settled_stake"] == Decimal("2")
    assert row["realized_pnl"] == Decimal("1")
    assert row["realized_roi"] == Decimal("0.5")
