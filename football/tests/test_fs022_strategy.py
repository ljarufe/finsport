"""Controlled prospective #209 conformance. No provider or bookmaker calls."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from django.db import close_old_connections

from football.capital.runtime import (
    build_execution_candidate,
    observe_terminal_result,
    place_candidate,
    provision_automatic_configs,
    run_automatic_runtime,
    settle_observation,
)
from football.market_identity import (
    reconcile_bookmaker_identity,
    reconcile_market_identity,
)
from football.models import (
    Bookmaker,
    CapitalDeployment,
    CapitalExecutionState,
    CapitalPosition,
    CapitalRuntimeConfig,
    CaptureRun,
    CaptureWorkItem,
    Competition,
    Decision,
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
from football.strategy.authority import BINDING_PATH, AuthorityError, resolve_authority
from football.strategy.deployment import provision, request_drain, update_depletion
from football.strategy.prospective import (
    evaluate_work,
    frozen_candidate,
    reconcile_global,
)
from football.tests.fs016_historical_runtime import provision_historical_configs

pytestmark = pytest.mark.django_db
AT = datetime(2026, 9, 27, 18, tzinfo=UTC)


@pytest.fixture(autouse=True)
def simulated_clock(monkeypatch):
    monkeypatch.setattr(
        "football.strategy.clock.effective_now",
        lambda *, planning_at=None: planning_at or AT,
    )


@pytest.fixture
def graph(monkeypatch):
    # An accidental provider read is a test failure, not a physical HTTP call.
    def forbidden(*args, **kwargs):
        raise AssertionError("EXTERNAL_PROVIDER_FORBIDDEN")

    monkeypatch.setattr(
        "football.providers.api_football.APIFootballClient.get_all", forbidden
    )
    source, _ = Source.objects.get_or_create(
        code="api_football",
        defaults=dict(name="API Football", base_url="https://example.test"),
    )
    market, _ = OddsMarket.objects.get_or_create(
        source=source, external_id="1", defaults=dict(name="Match Winner")
    )
    reconcile_market_identity(market)
    books = []
    for i, name in enumerate(("Pinnacle", "Bet365")):
        b, _ = Bookmaker.objects.get_or_create(
            source=source, external_id=str((4, 8)[i]), defaults=dict(name=name)
        )
        reconcile_bookmaker_identity(b)
        books.append(b)
    competition = Competition.objects.create(
        name="FS022 League", country="PE", competition_type="League", enabled=True
    )
    season = Season.objects.create(
        competition=competition,
        year=2026,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    return source, market, books, competition, season


def capture(
    graph,
    i=0,
    *,
    at=AT + timedelta(minutes=1),
    prices=(("1.5", "5", "8"), ("2.2", "4", "4")),
):
    source, market, books, competition, season = graph
    teams = [
        Team.objects.create(competition=competition, name=f"Team {i}-{side}")
        for side in (1, 2)
    ]
    match = Match.objects.create(
        season=season,
        home_team=teams[0],
        away_team=teams[1],
        kickoff=at + timedelta(minutes=30),
        status_short="NS",
    )
    MatchSourceRef.objects.create(
        source=source,
        match=match,
        external_id=f"fs022-{match.pk}",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    run = CaptureRun.objects.create(
        status="SUCCESS",
        planning_at=at,
        started_at=at,
        completed_at=at + timedelta(seconds=3),
    )
    work = CaptureWorkItem.objects.create(
        run=run,
        purpose="ODDS_CAPTURE",
        status="SUCCESS",
        source=source,
        market=market,
        match=match,
        logical_identity=f"fs022-test:{match.pk}",
        intended_window="market-t30m",
        target_at=at,
        not_before=at,
        not_after=at + timedelta(minutes=15),
        executed_at=at,
        completed_at=at + timedelta(seconds=2),
    )
    for b, p in zip(books, prices, strict=True):
        OddsObservation.objects.create(
            match=match,
            source=source,
            market=market,
            bookmaker=b,
            home=p[0],
            draw=p[1],
            away=p[2],
            observed_at=at + timedelta(seconds=1),
            provider_updated_at=at,
        )
    return work


def candidate(work):
    decision, reason = evaluate_work(work, at=work.run.completed_at)
    assert reason == ""
    return frozen_candidate(work, decision)


def terminal(position, *, won=True, at=AT + timedelta(minutes=180)):
    match = position.match
    match.status_short = "FT"
    match.outcome = position.execution_basis.action if won else "AWAY"
    match.save()
    observation, _ = observe_terminal_result(match, known_at=at)
    settle_observation(observation, settled_at=at)
    return observation


def test_material_authority_exact_and_original_preserved(tmp_path):
    from pathlib import Path

    from django.conf import settings

    root = Path(settings.BASE_DIR)
    old = (
        root
        / "docs/experiments/FS-021"
        / resolve_authority()["execution_id"]
        / "original_v1.json"
    )
    before = old.read_bytes()
    authority = resolve_authority()
    assert (
        authority["winner"] == 209 and authority["activation"]["real_betting"] is False
    )
    assert (
        authority["winner_candidate"]["prediction_decision"][
            "prediction_config_identity"
        ]
        == "c35e58fb446145fa698d4d122b1ddbb0e9e213dee4b1d04a756232979bb5ff7b"
    )
    assert old.read_bytes() == before and json.loads(before)["selection_index"] == 60
    p = tmp_path / BINDING_PATH
    p.parent.mkdir(parents=True)
    p.write_text("{}")
    with pytest.raises(AuthorityError, match="BINDING_INTEGRITY"):
        resolve_authority(base=tmp_path)
    with pytest.raises(AuthorityError, match="INACCESSIBLE"):
        resolve_authority(base=tmp_path / "missing")


def test_one_bank_ten_lanes_restart_retains_money_date_and_identity():
    (config,) = provision(at=AT)
    deployment = CapitalDeployment.objects.get()
    assert config.initial_bankroll == config.bankroll_equity == 100
    assert config.reserved_exposure == 0 and config.max_lanes == 10
    assert deployment.activated_at == AT and deployment.real_betting is False
    config.bankroll_equity = 112
    config.save()
    for _ in range(3):
        provision_automatic_configs()
    config.refresh_from_db()
    deployment.refresh_from_db()
    assert CapitalRuntimeConfig.objects.count() == 1
    assert config.bankroll_equity == 112 and deployment.activated_at == AT
    assert list(deployment.events.values_list("state", flat=True)) == [
        "DRAINING",
        "DRAINED",
        "ACTIVE",
    ]


def test_pipeline_prospective_complete_and_no_alternative_predictions(graph):
    provision(at=AT)
    work = capture(graph)
    result = run_automatic_runtime(capture_run_id=work.run_id, at=work.run.completed_at)
    assert result.placed == 1 and result.configs == 1
    assert list(Prediction.objects.values_list("model_code", flat=True)) == [
        "MARKET_CONSENSUS"
    ]
    assert list(Decision.objects.values_list("policy_variant", flat=True)) == ["0.45"]
    position = CapitalPosition.objects.get()
    basis = position.execution_basis
    assert (
        basis.selected_price == basis.selected_odds_observation.home == Decimal("2.2")
    )
    assert basis.originating_decision.selected_price == basis.selected_price
    assert (
        basis.evidence_not_before
        <= basis.selected_odds_observation.observed_at
        < basis.evidence_cutoff
        <= position.placed_at
        < position.match.kickoff
    )
    config = position.config
    assert (
        config.available_cash + config.reserved_exposure
        == config.bankroll_equity
        == 100
    )
    before = (config.bankroll_equity, config.reserved_exposure)
    assert (
        run_automatic_runtime(
            capture_run_id=work.run_id, at=work.run.completed_at
        ).placed
        == 0
    )
    config.refresh_from_db()
    assert before == (config.bankroll_equity, config.reserved_exposure)
    terminal(position)
    config.refresh_from_db()
    position.refresh_from_db()
    assert config.reserved_exposure == 0
    assert config.bankroll_equity == 100 + position.realized_pnl
    assert run_automatic_runtime(at=AT + timedelta(minutes=181)).settled == 0


@pytest.mark.parametrize(
    "fault",
    [
        "incomplete",
        "mixed_source",
        "future",
        "future_provider",
        "no_price",
        "lost_t30",
        "late_window",
        "post_kickoff",
        "pre_activation",
    ],
)
def test_price_input_gates_are_closed_and_classified(graph, fault):
    provision(at=AT)
    work = capture(graph)
    q = OddsObservation.objects.filter(match=work.match).first()
    if fault in {"incomplete", "mixed_source", "future", "future_provider"}:
        # One complete book is now valid; these failure cases have none.
        OddsObservation.objects.filter(match=work.match).exclude(pk=q.pk).delete()
    at = work.run.completed_at
    if fault == "incomplete":
        q.draw = 0
        q.save()
    elif fault == "mixed_source":
        q.bookmaker.source = Source.objects.create(
            code="other", name="Other", base_url="https://example.test"
        )
        q.bookmaker.save()
    elif fault == "future":
        q.observed_at = work.run.completed_at + timedelta(seconds=1)
        q.save()
    elif fault == "future_provider":
        q.provider_updated_at = work.run.completed_at + timedelta(seconds=1)
        q.save()
    elif fault == "no_price":
        OddsObservation.objects.filter(match=work.match).delete()
    elif fault == "lost_t30":
        work.status = "MISSED_WINDOW"
        work.executed_at = None
        work.save()
    elif fault == "late_window":
        work.executed_at = work.not_after + timedelta(seconds=1)
        work.save()
    elif fault == "post_kickoff":
        at = work.match.kickoff
    elif fault == "pre_activation":
        CapitalDeployment.objects.update(
            activated_at=work.executed_at + timedelta(seconds=1)
        )
    result = reconcile_global(work.run_id, at=at)
    assert result.placed == 0 and not CapitalPosition.objects.exists()
    assert CapitalExecutionState.objects.get().non_placement_reason != "NO_BET"


def test_policy_no_bet_is_economic_neutral(graph):
    (config,) = provision(at=AT)
    work = capture(graph, prices=(("3", "3", "3"), ("3", "3", "3")))
    assert reconcile_global(work.run_id, at=work.run.completed_at).not_placed == 1
    decision = Decision.objects.get()
    assert (
        decision.action == "NO_BET" and decision.reason == "BELOW_CONFIDENCE_THRESHOLD"
    )
    config.refresh_from_db()
    assert (
        config.bankroll_equity == 100
        and config.reserved_exposure == 0
        and not CapitalPosition.objects.exists()
    )


def test_injected_price_or_authority_cannot_bypass_admission(graph):
    (config,) = provision(at=AT)
    work = capture(graph)
    c = candidate(work)
    assert (
        place_candidate(
            config.pk,
            replace(c, selected_price=Decimal("99")),
            at=work.run.completed_at,
        )
        == "NOT_PLACED"
    )
    assert (
        CapitalExecutionState.objects.get().non_placement_reason
        == "EXECUTION_PRICE_MISMATCH"
    )
    assert not CapitalPosition.objects.exists()


def test_old_pending_cancelled_old_open_settles_after_restart_before_new_activation(
    graph,
):
    old = provision_historical_configs()
    work = capture(graph)
    # Produce historical DC/Modal fixture explicitly, before cutover.
    prediction = Prediction.objects.create(
        experiment=PredictionExperiment.objects.create(
            competition=work.match.competition,
            mode="PROSPECTIVE",
            period_start=date(2026, 9, 27),
            period_end=date(2026, 9, 27),
        ),
        match=work.match,
        model_code="DIXON_COLES",
        model_version="test",
        cutoff=work.run.completed_at,
        p_home=0.6,
        p_draw=0.2,
        p_away=0.2,
        predicted_outcome="HOME",
    )
    Decision.objects.create(
        experiment=prediction.experiment,
        match=work.match,
        prediction=prediction,
        policy_code="MODAL_ALL",
        policy_version="fs003-modal-all-v1",
        decision_time=work.run.completed_at,
        action="HOME",
        reason="MODAL_OUTCOME",
    )
    c = build_execution_candidate(work)
    assert place_candidate(old[0].pk, c, at=work.run.completed_at) == "PLACED"
    pending_work = capture(graph, 1)
    pending = CapitalExecutionState.objects.create(
        config=old[1], match=pending_work.match, status="PENDING"
    )
    before = {row.pk: row.bankroll_equity for row in old}
    assert provision(at=AT + timedelta(minutes=2)) == ()
    d = CapitalDeployment.objects.get()
    assert d.state == "DRAINING" and d.activated_at is None
    pending.refresh_from_db()
    assert (
        pending.non_placement_reason == "STRATEGY_DRAINING"
        and pending.position_id is None
    )
    assert place_candidate(old[2].pk, c, at=AT + timedelta(minutes=3)) == "NOT_PLACED"
    assert provision(at=AT + timedelta(minutes=4)) == ()
    position = CapitalPosition.objects.get()
    terminal(position, at=AT + timedelta(minutes=180))
    (new,) = provision(at=AT + timedelta(minutes=181))
    assert new.bankroll_equity == 100 and new.initial_bankroll == 100
    assert not CapitalRuntimeConfig.objects.filter(
        pk__in=[r.pk for r in old], entry_enabled=True
    ).exists()
    assert {
        r.pk: r.bankroll_equity
        for r in CapitalRuntimeConfig.objects.filter(
            pk__in=[x.pk for x in old]
        ).exclude(pk=position.config_id)
    } == {k: v for k, v in before.items() if k != position.config_id}
    assert CapitalPosition.objects.get().config_id == old[0].pk
    assert (
        len(provision_automatic_configs()) == 1
        and CapitalRuntimeConfig.objects.count() == 8
    )


def test_unresolved_debt_or_inconsistent_ledger_never_finishes_drain(graph):
    old = provision_historical_configs()
    old[0].reserved_exposure = 1
    old[0].save()
    with pytest.raises(RuntimeError, match="LEDGER_EXPOSURE_MISMATCH"):
        provision(at=AT)
    assert not CapitalRuntimeConfig.objects.filter(
        identity__startswith="fs022"
    ).exists()


@pytest.mark.parametrize(
    "equity,expected",
    [
        ("5", "OPERATIONAL_DEPLETION"),
        ("4.99999999", "OPERATIONAL_DEPLETION"),
        ("5.00000001", "ACTIVE"),
    ],
)
def test_exact_floor_and_not_available_cash(graph, equity, expected):
    (config,) = provision(at=AT)
    config.bankroll_equity = Decimal(equity)
    config.save()
    update_depletion(at=AT)
    assert CapitalDeployment.objects.get().depletion_state == expected
    work = capture(graph)
    result = reconcile_global(work.run_id, at=work.run.completed_at)
    assert result.placed == (expected == "ACTIVE")


def test_d05_sticky_three_open_3_6_9_and_fresh_only(graph):
    (config,) = provision(at=AT)
    works = [
        capture(graph, i, prices=(("1.5", "10", "10"), ("4", "7", "7")))
        for i in range(3)
    ]
    assert (
        sum(
            reconcile_global(work.run_id, at=work.run.completed_at).placed
            for work in works
        )
        == 3
    )
    positions = list(
        config.positions.select_related("match", "execution_basis").order_by("pk")
    )
    # Controlled money fixture: first loss reaches 3, subsequent wins each add 3.
    config.refresh_from_db()
    positions[0].applied_stake = 97
    positions[0].requested_stake = 97
    positions[0].save()
    for p in positions[1:]:
        p.applied_stake = Decimal("1")
        p.requested_stake = Decimal("1")
        p.save()
    config.bankroll_equity = 100
    config.reserved_exposure = 99
    config.save()
    terminal(positions[0], won=False, at=AT + timedelta(minutes=180))
    update_depletion(at=AT + timedelta(minutes=180))
    config.refresh_from_db()
    assert config.bankroll_equity == 3
    assert (
        CapitalDeployment.objects.get().depletion_state
        == "AWAITING_FINAL_OPEN_SETTLEMENT"
    )
    terminal(positions[1], at=AT + timedelta(minutes=190))
    update_depletion(at=AT + timedelta(minutes=190))
    config.refresh_from_db()
    assert config.bankroll_equity == 6
    assert (
        CapitalDeployment.objects.get().depletion_state
        == "AWAITING_FINAL_OPEN_SETTLEMENT"
    )
    blocked = capture(graph, 10, at=AT + timedelta(minutes=191))
    assert reconcile_global(blocked.run_id, at=blocked.run.completed_at).placed == 0
    terminal(positions[2], at=AT + timedelta(minutes=200))
    update_depletion(at=AT + timedelta(minutes=200))
    config.refresh_from_db()
    assert config.bankroll_equity == 9
    assert CapitalDeployment.objects.get().depletion_state == "ACTIVE"
    fresh = capture(graph, 11, at=AT + timedelta(minutes=201))
    assert reconcile_global(fresh.run_id, at=fresh.run.completed_at).placed == 1
    assert reconcile_global(blocked.run_id, at=AT + timedelta(minutes=202)).placed == 0


def test_simultaneous_known_settlements_complete_before_floor_gate(graph):
    (config,) = provision(at=AT)
    for i in range(2):
        work = capture(graph, i, prices=(("1.5", "10", "10"), ("4", "7", "7")))
        reconcile_global(work.run_id, at=work.run.completed_at)
    positions = list(config.positions.order_by("pk"))
    positions[0].applied_stake = 97
    positions[0].save()
    positions[1].applied_stake = Decimal("2")
    positions[1].save()
    config.reserved_exposure = 99
    config.save()
    for i, p in enumerate(positions):
        p.match.status_short = "FT"
        p.match.outcome = "AWAY" if i == 0 else "HOME"
        p.match.save()
    result = run_automatic_runtime(at=AT + timedelta(minutes=180))
    config.refresh_from_db()
    assert result.settled == 2 and config.bankroll_equity == 9
    assert CapitalDeployment.objects.get().depletion_state == "ACTIVE"
    assert (
        not CapitalDeployment.objects.get()
        .events.filter(state="AWAITING_FINAL_OPEN_SETTLEMENT")
        .exists()
    )


def test_ten_lanes_and_frozen_pending_then_kickoff_expiry(graph):
    (config,) = provision(at=AT)
    for i in range(11):
        work = capture(graph, i)
        reconcile_global(work.run_id, at=work.run.completed_at)
    assert config.positions.count() == 10
    state = config.execution_states.get(status="PENDING_CAPACITY")
    price = state.execution_basis.selected_price
    OddsObservation.objects.filter(match=state.match).update(home=99)
    assert reconcile_global(None, at=state.match.kickoff).placed == 0
    state.refresh_from_db()
    assert (
        state.non_placement_reason == "EXPIRED_CAPACITY"
        and state.execution_basis.selected_price == price
    )


def test_stopped_diagnostic_authority_does_not_reactivate_or_destroy_history(graph):
    provision(at=AT)
    work = capture(graph)
    reconcile_global(work.run_id, at=work.run.completed_at)
    request_drain(
        successor_mode="DIAGNOSTIC_ONLY__NO_NEW_STAKES", at=AT + timedelta(minutes=5)
    )
    assert len(provision(at=AT + timedelta(minutes=6))) == 1
    assert CapitalDeployment.objects.get().state == "DRAINING"
    terminal(CapitalPosition.objects.get())
    provision(at=AT + timedelta(minutes=181))
    d = CapitalDeployment.objects.get()
    assert d.state == "STOPPED" and not d.entry_enabled and d.activated_at == AT
    fresh = capture(graph, 2, at=AT + timedelta(minutes=182))
    assert reconcile_global(fresh.run_id, at=fresh.run.completed_at).placed == 0
    assert CapitalPosition.objects.count() == 1
    assert d.selection == resolve_authority()


@pytest.mark.django_db(transaction=True)
def test_two_first_wakes_create_one_deployment_and_one_bank():
    def wake():
        close_old_connections()
        try:
            return provision(at=AT)[0].pk
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: wake(), range(2)))
    assert len(set(ids)) == 1 and CapitalRuntimeConfig.objects.count() == 1
    assert CapitalDeployment.objects.count() == 1


def test_pending_reuses_exact_frozen_price_when_lane_frees_before_kickoff(graph):
    (config,) = provision(at=AT)
    for i in range(10):
        work = capture(graph, i)
        assert reconcile_global(work.run_id, at=work.run.completed_at).placed == 1
    later = capture(graph, 11, at=AT + timedelta(minutes=181))
    assert (
        reconcile_global(later.run_id, at=later.run.completed_at).pending_capacity == 1
    )
    state = config.execution_states.get(match=later.match)
    original_basis = state.execution_basis_id
    original_price = state.execution_basis.selected_price
    OddsObservation.objects.create(
        match=later.match,
        source=graph[0],
        market=graph[1],
        bookmaker=graph[2][0],
        home=99,
        draw=99,
        away=99,
        observed_at=AT + timedelta(minutes=183),
    )
    terminal(config.positions.order_by("pk").first(), at=AT + timedelta(minutes=184))
    assert reconcile_global(None, at=AT + timedelta(minutes=185)).placed == 1
    state.refresh_from_db()
    assert (
        state.execution_basis_id == original_basis
        and state.position.execution_basis.selected_price == original_price
    )
    assert state.position.placed_at == AT + timedelta(minutes=185)


def test_transient_cash_shortage_is_capacity_and_never_depletion(graph):
    (config,) = provision(at=AT)
    first = capture(graph, 0)
    assert reconcile_global(first.run_id, at=first.run.completed_at).placed == 1
    position = config.positions.get()
    position.applied_stake = Decimal("99")
    position.save()
    config.reserved_exposure = Decimal("99")
    config.save()
    update_depletion(at=AT)
    work = capture(graph, 1)
    assert reconcile_global(work.run_id, at=work.run.completed_at).pending_capacity == 1
    assert CapitalDeployment.objects.get().depletion_state == "ACTIVE"
    assert (
        config.execution_states.get(match=work.match).diagnostics["reason"]
        == "INSUFFICIENT_AVAILABLE_CASH"
    )


def test_authority_failure_does_not_interrupt_real_settlement(graph, monkeypatch):
    provision(at=AT)
    work = capture(graph)
    reconcile_global(work.run_id, at=work.run.completed_at)
    position = CapitalPosition.objects.get()
    position.match.status_short = "FT"
    position.match.outcome = "HOME"
    position.match.save()

    def missing():
        raise AuthorityError("FS022_AUTHORITY_INACCESSIBLE")

    monkeypatch.setattr("football.strategy.deployment.resolve_authority", missing)
    result = run_automatic_runtime(at=AT + timedelta(minutes=180))
    position.refresh_from_db()
    assert result.status == "DEGRADED" and result.settled == 1
    assert position.status == CapitalPosition.Status.SETTLED_WIN
    assert position.config.reserved_exposure == 0


@pytest.mark.django_db(transaction=True)
def test_two_wakes_cannot_duplicate_prospective_positions(graph):
    provision(at=AT)
    work = capture(graph)

    def wake():
        close_old_connections()
        try:
            return run_automatic_runtime(
                capture_run_id=work.run_id, at=work.run.completed_at
            ).placed
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(lambda _: wake(), range(2)))
    assert sorted(counts) == [0, 1]
    assert (
        CapitalPosition.objects.count() == 1
        and CapitalExecutionState.objects.count() == 1
    )


def test_complete_pipeline_reports_only_209_and_capture_continues_when_stopped(
    graph, monkeypatch
):
    from football.capture.contracts import CaptureResult
    from football.models import CaptureWorkItem
    from football.pipeline.service import run_pipeline

    monkeypatch.setattr("football.pipeline.service.timezone.now", lambda: AT)
    work = capture(graph)
    result = CaptureResult(
        run_id=work.run_id,
        status="SUCCESS",
        planning_at=AT,
        quota_before={},
        quota_after={},
    )
    called = []

    def retained_capture(**kwargs):
        called.append(kwargs)
        return result

    monkeypatch.setattr("football.pipeline.service.run_capture", retained_capture)
    first = run_pipeline(at=AT)
    assert first.phases["PREDICTION"]["state"] == "SUCCESS"
    assert first.report["prediction"]["created_count"] == 1
    assert first.phases["CAPITAL"]["details"]["runtime"]["placed"] == 1
    assert Prediction.objects.count() == Decision.objects.count() == 1
    request_drain(at=AT + timedelta(minutes=5))
    # Provider-free fake clock remains before result debt is due.
    second = run_pipeline(at=AT + timedelta(minutes=6))
    assert len(called) == 2 and second.phases["CAPTURE"]["state"] == "SUCCESS"
    assert CapitalPosition.objects.count() == 1
    assert CaptureWorkItem.objects.get(pk=work.pk).status == "SUCCESS"


@pytest.mark.parametrize(
    "fault", ["missing_index_key", "changed_index", "unsupported_version"]
)
def test_material_index_and_version_drift_fail_closed(tmp_path, monkeypatch, fault):
    from pathlib import Path

    from django.conf import settings

    from football.strategy.authority import EXECUTION_ID

    relative = Path("docs/experiments/FS-021") / EXECUTION_ID
    (tmp_path / relative).mkdir(parents=True)
    for name in (
        "prospective_binding_v1.json",
        "economic_v1_1.json",
        "original_v1.json",
    ):
        (tmp_path / relative / name).write_bytes(
            (Path(settings.BASE_DIR) / relative / name).read_bytes()
        )
    index_path = tmp_path / relative / "economic_v1_1.json"
    index = json.loads(index_path.read_text())
    if fault == "missing_index_key":
        del index["winner"]
    elif fault == "changed_index":
        index["winner"] = 60
    else:
        monkeypatch.setattr(
            "football.strategy.authority.MARKET_CONSENSUS_VERSION", "unsupported"
        )
    index_path.write_text(json.dumps(index))
    with pytest.raises(AuthorityError, match="CONTRACT_DRIFT"):
        resolve_authority(base=tmp_path)
    assert not CapitalRuntimeConfig.objects.exists()


def test_depletion_config_drift_blocks_entries_but_preserves_settlement(graph):
    provision(at=AT)
    work = capture(graph)
    reconcile_global(work.run_id, at=work.run.completed_at)
    position = CapitalPosition.objects.get()
    position.match.status_short = "FT"
    position.match.outcome = "HOME"
    position.match.save()
    CapitalDeployment.objects.update(depletion_floor=4)
    result = run_automatic_runtime(at=AT + timedelta(minutes=180))
    position.refresh_from_db()
    assert result.status == "DEGRADED" and result.settled == 1
    assert "DEPLETION_FLOOR_DRIFT" in result.errors[0]
    assert position.status == CapitalPosition.Status.SETTLED_WIN
    assert position.config.reserved_exposure == 0


def test_injected_action_cannot_override_frozen_decision(graph):
    from football.prediction.policies import PolicyResult

    (config,) = provision(at=AT)
    work = capture(graph)
    actual = candidate(work)
    assert actual.decision.action == "HOME"
    injected = replace(actual, result=PolicyResult("NO_BET", "INJECTED"))
    assert (
        place_candidate(config.pk, injected, at=work.run.completed_at) == "NOT_PLACED"
    )
    assert (
        CapitalExecutionState.objects.get().non_placement_reason
        == "AUTHORITY_EVIDENCE_MISMATCH"
    )
    assert not CapitalPosition.objects.exists()


def test_stale_planning_time_cannot_admit_after_real_kickoff(graph, monkeypatch):
    provision(at=AT)
    work = capture(graph)
    expired_at = work.match.kickoff + timedelta(seconds=1)
    monkeypatch.setattr(
        "football.strategy.clock.effective_now", lambda *, planning_at=None: expired_at
    )
    result = reconcile_global(work.run_id, at=work.run.completed_at)
    assert result.placed == 0
    assert not CapitalPosition.objects.exists()
    assert not PredictionExperiment.objects.exists()
    state = CapitalExecutionState.objects.get(match=work.match)
    assert state.non_placement_reason == "MISSED_EXECUTION_WINDOW"
    assert reconcile_global(work.run_id, at=work.run.completed_at).placed == 0
    assert CapitalExecutionState.objects.filter(match=work.match).count() == 1


def test_pending_capacity_expires_after_real_kickoff_even_with_freed_lanes(
    graph, monkeypatch
):
    (config,) = provision(at=AT)
    for i in range(10):
        work = capture(graph, i)
        assert reconcile_global(work.run_id, at=work.run.completed_at).placed == 1
    pending_work = capture(graph, 11, at=AT + timedelta(minutes=181))
    assert (
        reconcile_global(
            pending_work.run_id, at=pending_work.run.completed_at
        ).pending_capacity
        == 1
    )
    state = config.execution_states.get(match=pending_work.match)
    frozen_basis = state.execution_basis_id
    frozen_price = state.execution_basis.selected_price
    for position in list(config.positions.order_by("pk")[:2]):
        terminal(position, at=AT + timedelta(minutes=184))
    expired_at = pending_work.match.kickoff + timedelta(seconds=1)
    monkeypatch.setattr(
        "football.strategy.clock.effective_now", lambda *, planning_at=None: expired_at
    )
    assert reconcile_global(None, at=AT + timedelta(minutes=185)).placed == 0
    state.refresh_from_db()
    assert state.non_placement_reason == "EXPIRED_CAPACITY"
    assert state.execution_basis_id == frozen_basis
    assert state.execution_basis.selected_price == frozen_price
    assert not config.positions.filter(match=pending_work.match).exists()
    assert reconcile_global(None, at=AT + timedelta(minutes=185)).placed == 0
    assert config.execution_states.filter(match=pending_work.match).count() == 1


def test_prospective_period_uses_lima_kickoff_day(graph):
    provision(at=AT)
    work = capture(graph, at=datetime(2026, 9, 28, 0, 30, tzinfo=UTC))
    assert work.match.kickoff.date() == date(2026, 9, 28)
    result = reconcile_global(work.run_id, at=work.run.completed_at)
    assert result.placed == 1
    experiment = PredictionExperiment.objects.get()
    assert experiment.period_start == experiment.period_end == date(2026, 9, 27)
    assert experiment.logical_identity.endswith(work.logical_identity)


def test_new_activation_uses_effective_time_but_never_resets_it(monkeypatch):
    effective = AT + timedelta(hours=2)
    monkeypatch.setattr(
        "football.strategy.clock.effective_now", lambda *, planning_at=None: effective
    )
    (config,) = provision(at=AT)
    deployment = CapitalDeployment.objects.get()
    assert config.started_at == deployment.activated_at == effective
    later = effective + timedelta(days=1)
    monkeypatch.setattr(
        "football.strategy.clock.effective_now", lambda *, planning_at=None: later
    )
    provision(at=AT)
    deployment.refresh_from_db()
    assert deployment.activated_at == effective
    assert CapitalRuntimeConfig.objects.count() == 1
