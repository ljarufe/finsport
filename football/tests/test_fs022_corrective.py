"""Pass 2 regressions: live acquisition, crash recovery, short locks. No HTTP."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from importlib import import_module
from threading import Event
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import close_old_connections, connection, transaction

from football.capital.runtime import run_automatic_runtime
from football.capture.contracts import CaptureResult
from football.market_identity import reconcile_bookmaker_identity
from football.models import (
    Bookmaker,
    BookmakerCanonicalRef,
    CapitalDeployment,
    CapitalEvaluation,
    CapitalExecutionState,
    CapitalPosition,
    Match,
    OddsMarket,
    OddsMarketCanonicalRef,
    OddsObservation,
    Prediction,
    PredictionExperiment,
    Source,
)
from football.pipeline.service import run_pipeline
from football.prediction.market import MarketConsensusAdapter
from football.strategy.authority import AuthorityError, resolve_authority
from football.strategy.deployment import provision, request_drain
from football.strategy.prospective import (
    evaluate_work,
    live_selection,
    reconcile_global,
)
from football.tests.test_fs022_strategy import AT, capture
from football.tests.test_fs022_strategy import graph as graph

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def simulated_clock(monkeypatch):
    monkeypatch.setattr(
        "football.strategy.clock.effective_now",
        lambda *, planning_at=None: planning_at or AT,
    )


def add_book(work, external_id, prices, *, observed_at=None, name="Provider book"):
    book, _ = Bookmaker.objects.get_or_create(
        source=work.source, external_id=external_id, defaults={"name": name}
    )
    reconcile_bookmaker_identity(book)
    return OddsObservation.objects.create(
        match=work.match,
        source=work.source,
        bookmaker=book,
        market=work.market,
        home=prices[0],
        draw=prices[1],
        away=prices[2],
        observed_at=observed_at or work.executed_at + timedelta(seconds=1),
        provider_updated_at=work.executed_at,
    )


def pipeline_capture(monkeypatch, work, *, at=None, plan=None):
    monkeypatch.setattr("football.pipeline.service.timezone.now", lambda: AT)
    result = CaptureResult(
        run_id=work.run_id,
        status="SUCCESS",
        planning_at=at or AT,
        quota_before={},
        quota_after={},
        plan=plan or {},
    )
    monkeypatch.setattr(
        "football.pipeline.service.run_capture", lambda **kwargs: result
    )


def test_four_live_books_change_consensus_and_select_best_outside_historical_trio(
    graph,
):
    provision(at=AT)
    work = capture(graph)
    before = MarketConsensusAdapter().predict_selection(live_selection(work))
    add_book(work, "7", ("2.8", "12", "12"))
    best = add_book(work, "11", ("3.5", "20", "20"))
    result = reconcile_global(work.run_id, at=work.run.completed_at)
    prediction = Prediction.objects.get()
    position = CapitalPosition.objects.get()
    assert result.placed == 1 and prediction.p_home != pytest.approx(before.p_home)
    assert prediction.diagnostics["canonical_bookmaker_count"] == 4
    assert (
        prediction.diagnostics["consensus_evidence"] == "MULTI_BOOKMAKER_UNCALIBRATED"
    )
    assert position.execution_basis.selected_odds_observation_id == best.pk
    assert position.execution_basis.selected_price == Decimal("3.5")
    assert set(prediction.diagnostics["quote_ids"]) == {
        q.observation.pk for q in live_selection(work).quotes
    }
    assert (
        position.execution_basis.provenance["quote_ids"]
        == prediction.diagnostics["quote_ids"]
    )
    assert (
        prediction.model_config["prospective_config_identity"]
        != prediction.model_config["scientific_selection_config_identity"]
    )
    assert "bookmakers" not in prediction.model_config and "ODDSPAPI" not in str(
        prediction.model_config
    )
    assert prediction.model_config["source"] == "api_football"


@pytest.mark.parametrize("count", [1, 2, 3])
def test_one_two_three_complete_books_preserve_live_classification(graph, count):
    provision(at=AT)
    work = capture(graph)
    if count == 1:
        OddsObservation.objects.filter(match=work.match, bookmaker=graph[2][0]).delete()
    elif count == 3:
        add_book(work, "11", ("3.5", "20", "20"))
    result = reconcile_global(work.run_id, at=work.run.completed_at)
    prediction = Prediction.objects.get()
    assert result.placed == 1
    assert prediction.diagnostics["book_count"] == count
    assert prediction.diagnostics["consensus_evidence"] == (
        "SINGLE_BOOKMAKER_TECHNICAL_ONLY"
        if count == 1
        else "MULTI_BOOKMAKER_UNCALIBRATED"
    )


def test_duplicates_unknown_and_incomplete_books_do_not_create_extra_votes(graph):
    provision(at=AT)
    work = capture(graph)
    newer = add_book(
        work,
        "8",
        ("2.5", "9", "9"),
        observed_at=work.executed_at + timedelta(seconds=1.5),
    )
    unknown = add_book(work, "unknown-999", ("10", "20", "20"), name="Pinnacle")
    add_book(work, "7", ("9", "0", "20"))
    selection = live_selection(work)
    assert len(selection.quotes) == 2
    assert newer.pk in {q.observation.pk for q in selection.quotes}
    assert unknown.bookmaker.canonical_ref.reconciliation_status == "PENDING"
    assert selection.diagnostics["rejection_counts"]["duplicate_canonical_vote"] == 1
    assert selection.diagnostics["rejection_counts"]["unmapped_bookmaker"] == 1
    assert selection.diagnostics["rejection_counts"]["invalid_prices"] == 1


@pytest.mark.parametrize(
    "kind",
    ["other_source", "other_market", "future", "stale_capture", "future_provider"],
)
def test_incompatible_newer_rows_never_displace_original_api_football_votes(
    graph, kind
):
    provision(at=AT)
    work = capture(graph)
    original = list(live_selection(work).quotes)
    original_ids = [q.observation.pk for q in original]
    quote = original[0]
    fields = dict(
        match=work.match,
        source=work.source,
        bookmaker=quote.observation.bookmaker,
        market=work.market,
        home="50",
        draw="80",
        away="90",
        observed_at=work.executed_at + timedelta(seconds=1.5),
        provider_updated_at=work.executed_at,
    )
    if kind == "other_source":
        other = Source.objects.create(
            code="secondary", name="Secondary", base_url="https://example.test"
        )
        book = Bookmaker.objects.create(source=other, external_id="8", name="Secondary")
        BookmakerCanonicalRef.objects.create(
            bookmaker=book,
            canonical_bookmaker=quote.canonical_bookmaker,
            reconciliation_status="RESOLVED",
        )
        market = OddsMarket.objects.create(source=other, external_id="1", name="1X2")
        OddsMarketCanonicalRef.objects.create(
            market=market,
            canonical_market=work.market.canonical_ref.canonical_market,
            reconciliation_status="RESOLVED",
        )
        fields.update(source=other, bookmaker=book, market=market)
    elif kind == "other_market":
        market = OddsMarket.objects.create(
            source=work.source, external_id="other", name="Other"
        )
        OddsMarketCanonicalRef.objects.create(
            market=market,
            canonical_market=work.market.canonical_ref.canonical_market,
            reconciliation_status="RESOLVED",
        )
        fields["market"] = market
    elif kind == "future":
        fields["observed_at"] = work.completed_at + timedelta(microseconds=1)
    elif kind == "stale_capture":
        fields["observed_at"] = work.executed_at - timedelta(microseconds=1)
        fields["provider_updated_at"] = fields["observed_at"]
    else:
        fields["provider_updated_at"] = work.run.completed_at + timedelta(seconds=1)
    OddsObservation.objects.create(**fields)
    after = live_selection(work)
    assert [q.observation.pk for q in after.quotes] == original_ids
    decision, reason = evaluate_work(work, at=work.run.completed_at)
    assert reason == "" and decision.prediction.diagnostics["quote_ids"] == original_ids
    assert decision.selected_odds_observation_id in original_ids
    assert [q.observation.pk for q in live_selection(work).quotes] == original_ids


@pytest.mark.parametrize("late", [False, True])
def test_recovery_without_last_capture_id_before_and_after_kickoff(graph, late):
    provision(at=AT)
    work = capture(graph)
    at = work.match.kickoff if late else work.run.completed_at + timedelta(minutes=1)
    result = reconcile_global(None, at=at)
    assert result.placed == (0 if late else 1)
    assert CapitalEvaluation.objects.get().status == (
        "MISSED_WINDOW" if late else "COMPLETED"
    )
    assert CapitalEvaluation.objects.get().work_id == work.pk
    if late:
        assert not Prediction.objects.exists() and not CapitalPosition.objects.exists()
        assert (
            CapitalExecutionState.objects.get().non_placement_reason
            == "MISSED_EXECUTION_WINDOW"
        )
    else:
        assert Prediction.objects.get().cutoff == work.run.completed_at
    again = reconcile_global(None, at=at)
    repeated = reconcile_global(work.run_id, at=at)
    assert again.placed == repeated.placed == 0
    assert CapitalEvaluation.objects.count() == 1
    assert PredictionExperiment.objects.count() == (0 if late else 1)
    assert CapitalPosition.objects.count() == (0 if late else 1)


def test_recovery_is_bounded_and_respects_activation(graph, monkeypatch):
    provision(at=AT)
    works = [capture(graph, i) for i in range(3)]
    monkeypatch.setattr("football.strategy.recovery.RECOVERY_LIMIT", 2)
    result = reconcile_global(None, at=works[0].run.completed_at)
    assert result.placed == 2 and CapitalEvaluation.objects.count() == 2
    assert reconcile_global(None, at=works[0].run.completed_at).placed == 1
    old = capture(graph, 10, at=AT - timedelta(minutes=5))
    assert reconcile_global(None, at=AT + timedelta(minutes=2)).placed == 0
    assert not CapitalEvaluation.objects.filter(work=old).exists()


@pytest.mark.parametrize(
    "kind", ["no_bet", "no_quotes", "missed", "authority", "error"]
)
def test_prediction_phase_events_and_receipts_identify_actual_evaluation(
    graph, monkeypatch, kind
):
    provision(at=AT)
    work = capture(
        graph,
        prices=(
            (("3", "3", "3"), ("3", "3", "3"))
            if kind == "no_bet"
            else (("1.5", "5", "8"), ("2.2", "4", "4"))
        ),
    )
    pipeline_capture(monkeypatch, work)
    events = []
    monkeypatch.setattr(
        "football.strategy.recovery.emit_event", lambda **kw: events.append(kw)
    )
    if kind == "no_quotes":
        OddsObservation.objects.filter(match=work.match).delete()
    elif kind == "authority":

        def unavailable():
            raise AuthorityError("FS022_AUTHORITY_INACCESSIBLE")

        monkeypatch.setattr(
            "football.strategy.deployment.resolve_authority", unavailable
        )
    elif kind == "error":

        def broken(*args, **kwargs):
            raise RuntimeError("controlled evaluator failure")

        monkeypatch.setattr("football.strategy.prospective.evaluate_work", broken)
    result = run_pipeline(
        at=work.match.kickoff if kind == "missed" else work.run.completed_at
    )
    expected = {
        "no_bet": ("SUCCESS", "NO_BET"),
        "no_quotes": ("UNAVAILABLE", "UNAVAILABLE"),
        "missed": ("UNAVAILABLE", "MISSED_WINDOW"),
        "authority": ("UNAVAILABLE", "BLOCKED"),
        "error": ("FAILED", "FAILED"),
    }[kind]
    assert result.phases["PREDICTION"]["state"] == expected[0]
    assert CapitalEvaluation.objects.get().status == expected[1]
    assert (
        events[-1]["outcome"] == expected[1]
        and events[-1]["capture_run_id"] == work.run_id
    )
    assert not CapitalPosition.objects.exists()
    assert result.phases["CAPTURE"]["state"] == "SUCCESS"


def test_authority_repair_retries_original_quote_before_kickoff(graph, monkeypatch):
    provision(at=AT)
    work = capture(graph)
    authority = resolve_authority()

    def missing():
        raise AuthorityError("FS022_AUTHORITY_INACCESSIBLE")

    monkeypatch.setattr("football.strategy.deployment.resolve_authority", missing)
    assert (
        run_automatic_runtime(
            capture_run_id=work.run_id, at=work.run.completed_at
        ).placed
        == 0
    )
    assert CapitalEvaluation.objects.get().retryable
    monkeypatch.setattr(
        "football.strategy.deployment.resolve_authority", lambda: authority
    )
    assert (
        run_automatic_runtime(at=work.run.completed_at + timedelta(minutes=1)).placed
        == 1
    )
    assert CapitalEvaluation.objects.get().attempts == 2


def test_dry_run_inspects_retained_recovery_and_capture_plan_without_writes(
    graph, monkeypatch
):
    provision(at=AT)
    work = capture(graph)
    pipeline_capture(
        monkeypatch,
        work,
        plan={
            "items": [
                {
                    "purpose": "ODDS_CAPTURE",
                    "intended_window": "market-t30m",
                    "match_id": work.match_id,
                    "status": "PLANNED",
                }
            ]
        },
    )
    before = (
        Prediction.objects.count(),
        CapitalEvaluation.objects.count(),
        CapitalPosition.objects.count(),
        CapitalDeployment.objects.count(),
    )
    result = run_pipeline(at=work.run.completed_at + timedelta(minutes=1), dry_run=True)
    detail = result.phases["PREDICTION"]["details"]
    assert detail["inspected"] and detail["capture_plan_inspected"]
    assert detail["planned"][0]["work_id"] == work.pk
    assert detail["capture_planned"][0]["match_id"] == work.match_id
    assert before == (
        Prediction.objects.count(),
        CapitalEvaluation.objects.count(),
        CapitalPosition.objects.count(),
        CapitalDeployment.objects.count(),
    )


def old_binding():
    binding = resolve_authority()
    binding["schema"] = "FS022_PROSPECTIVE_BINDING_V1"
    binding["prediction_effective_config"] = binding.pop(
        "scientific_prediction_effective_config"
    )
    for key in (
        "selection_source",
        "prospective_prediction_config_identity",
        "prospective_prediction_effective_config",
    ):
        binding.pop(key)
    return binding


def test_binding_data_correction_preserves_bank_date_and_audits_pending(graph):
    (config,) = provision(at=AT)
    previous = old_binding()
    CapitalDeployment.objects.update(selection=previous)
    config.bankroll_equity = Decimal("112")
    config.execution_version = "fs022-prospective-t30-v1"
    config.provenance = {"selection": previous, "real_betting": False}
    config.save()
    work = capture(graph)
    pending = CapitalExecutionState.objects.create(
        config=config, match=work.match, status="PENDING"
    )
    module = import_module("football.migrations.0017_fs022_live_evaluation_recovery")
    with transaction.atomic():
        module.correct_prospective_binding(apps, SimpleNamespace(connection=connection))
        module.correct_prospective_binding(apps, SimpleNamespace(connection=connection))
    config.refresh_from_db()
    pending.refresh_from_db()
    deployment = CapitalDeployment.objects.get()
    assert (
        config.bankroll_equity == 112
        and config.initial_bankroll == 100
        and deployment.activated_at == AT
    )
    assert (
        deployment.selection == resolve_authority()
        and config.provenance["selection"] == resolve_authority()
    )
    assert (
        pending.status == "NOT_PLACED"
        and pending.non_placement_reason == "AUTHORITY_EVIDENCE_MISMATCH"
    )
    assert (
        deployment.events.filter(reason="PROSPECTIVE_CONFIG_CORRECTION_V2").count() == 1
    )
    assert (
        deployment.events.get(reason="PROSPECTIVE_CONFIG_CORRECTION_V2").evidence[
            "previous_selection"
        ]
        == previous
    )


@pytest.mark.django_db(transaction=True)
def test_two_wakes_recover_same_unprocessed_capture_once(graph):
    provision(at=AT)
    work = capture(graph)

    def wake():
        close_old_connections()
        try:
            return run_automatic_runtime(at=work.run.completed_at).placed
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(lambda _: wake(), range(2)))
    assert sorted(counts) == [0, 1]
    assert (
        CapitalEvaluation.objects.count()
        == CapitalPosition.objects.count()
        == PredictionExperiment.objects.count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("drain,timeout", [(False, False), (True, False), (True, True)])
def test_slow_provider_does_not_hold_admission_lock_or_lose_settlement(
    graph, monkeypatch, settings, drain, timeout
):
    settings.FOOTBALL_CAPTURE_DISCOVERY_ENABLED = False
    settings.FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS = 3
    provision(at=AT)
    old = capture(graph)
    reconcile_global(old.run_id, at=old.run.completed_at)
    old_position = CapitalPosition.objects.get()
    due = AT + timedelta(minutes=180)
    fresh = capture(graph, 1, at=due)
    started, release = Event(), Event()
    calls = []
    clock = [due]
    monkeypatch.setattr(
        "football.strategy.clock.effective_now",
        lambda *, planning_at=None: max(planning_at or AT, clock[0]),
    )
    external_id = f"fs022-{old.match_id}"

    class SlowClient:
        def __init__(self, **kwargs):
            self.calls = 0

        def get_all(self, endpoint, params):
            assert not connection.in_atomic_block
            self.calls += 1
            calls.append((endpoint, dict(params)))
            started.set()
            assert release.wait(5), "concurrent admission blocked behind HTTP"
            if timeout:
                raise TimeoutError("controlled network timeout")
            return [{"fixture": {"id": external_id}}]

    def sync_stub(items, competitions):
        Match.objects.filter(pk=old.match_id).update(
            status_short="FT",
            outcome="HOME",
            home_score=2,
            away_score=1,
            fulltime_home_score=2,
            fulltime_away_score=1,
        )
        return None, {external_id: old.match}

    monkeypatch.setattr("football.capital.runtime.sync_fixture_payloads", sync_stub)

    def slow_wake():
        close_old_connections()
        try:
            return run_automatic_runtime(at=due, client_factory=SlowClient)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        slow = pool.submit(slow_wake)
        try:
            assert started.wait(3)
            clock[0] = fresh.match.kickoff + timedelta(seconds=1)
            if drain:
                request_drain(at=due)
            fast = pool.submit(lambda: concurrent_capture(fresh))
            fast_result = fast.result(timeout=2)
            assert fast_result.placed == 0
        finally:
            release.set()
        result = slow.result(timeout=3)
    assert calls, "the simulated result HTTP callback must run"
    old_position.refresh_from_db()
    if timeout:
        assert result.status == "DEGRADED" and old_position.status == "OPEN"
        Match.objects.filter(pk=old.match_id).update(status_short="FT", outcome="HOME")
        assert run_automatic_runtime(at=due + timedelta(minutes=1)).settled == 1
    else:
        assert old_position.status == "SETTLED_WIN" and result.settled == 1
    assert CapitalPosition.objects.filter(match=fresh.match).count() == 0
    assert run_automatic_runtime(at=due + timedelta(minutes=2)).settled == 0
    if drain:
        assert not CapitalDeployment.objects.get().entry_enabled


def concurrent_capture(work):
    close_old_connections()
    try:
        return reconcile_global(work.run_id, at=work.run.completed_at)
    finally:
        close_old_connections()


def test_latest_invalid_row_does_not_hide_last_valid_and_tied_prices_are_deterministic(
    graph,
):
    provision(at=AT)
    work = capture(graph, prices=(("2", "8", "8"), ("2", "8", "8")))
    before = [q.observation.pk for q in live_selection(work).quotes]
    add_book(
        work,
        "8",
        ("99", "0", "20"),
        observed_at=work.executed_at + timedelta(seconds=1.5),
    )
    assert [q.observation.pk for q in live_selection(work).quotes] == before
    decision, reason = evaluate_work(work, at=work.run.completed_at)
    assert (
        reason == ""
        and decision.selected_odds_observation.bookmaker.canonical_ref.canonical_bookmaker.code
        == "bet365"
    )
    result = reconcile_global(work.run_id, at=work.run.completed_at)
    assert result.placed == 1 and not result.evaluations[0]["created_experiment"]
    assert (
        CapitalEvaluation.objects.get().details["selected_observation_id"]
        == decision.selected_odds_observation_id
    )


def test_network_timeout_preserves_previously_committed_local_settlement(
    graph, settings
):
    settings.FOOTBALL_CAPTURE_DISCOVERY_ENABLED = False
    provision(at=AT)
    works = [capture(graph, i) for i in range(2)]
    reconcile_global(None, at=works[0].run.completed_at)
    first = CapitalPosition.objects.get(match=works[0].match)
    Match.objects.filter(pk=first.match_id).update(status_short="FT", outcome="HOME")

    class TimeoutClient:
        def __init__(self, **kwargs):
            self.calls = 0

        def get_all(self, *args):
            self.calls += 1
            raise TimeoutError("controlled timeout after local settlement")

    result = run_automatic_runtime(
        at=AT + timedelta(minutes=180), client_factory=TimeoutClient
    )
    first.refresh_from_db()
    assert result.settled == 1 and result.status == "DEGRADED"
    assert first.status == "SETTLED_WIN"
    Match.objects.filter(pk=works[1].match_id).update(status_short="FT", outcome="HOME")
    assert run_automatic_runtime(at=AT + timedelta(minutes=181)).settled == 1
    assert run_automatic_runtime(at=AT + timedelta(minutes=182)).settled == 0


def test_dry_run_reports_authority_block_and_missing_quotes_honestly(
    graph, monkeypatch
):
    provision(at=AT)
    work = capture(graph)
    pipeline_capture(monkeypatch, work)
    OddsObservation.objects.filter(match=work.match).delete()
    first = run_pipeline(at=work.run.completed_at, dry_run=True)
    detail = first.phases["PREDICTION"]["details"]
    assert detail["planned"][0]["classification"] == "INPUT_QUOTES_MISSING"
    assert detail["eligible_prediction_work_count"] == 0

    def invalid():
        raise AuthorityError("FS022_BINDING_INTEGRITY")

    monkeypatch.setattr("football.strategy.authority.resolve_authority", invalid)
    second = run_pipeline(at=work.run.completed_at, dry_run=True)
    assert (
        second.phases["PREDICTION"]["details"]["admission_reason"]
        == "AUTHORITY_ADMISSION_BLOCKED"
    )
    assert not CapitalEvaluation.objects.exists()


def test_unrecognized_binding_never_upgrades_or_changes_money(graph):
    (config,) = provision(at=AT)
    previous = old_binding()
    previous["winner"] = 60
    CapitalDeployment.objects.update(selection=previous)
    module = import_module("football.migrations.0017_fs022_live_evaluation_recovery")
    with pytest.raises(RuntimeError, match="UNRECOGNIZED_BINDING"):
        with transaction.atomic():
            module.correct_prospective_binding(
                apps, SimpleNamespace(connection=connection)
            )
    config.refresh_from_db()
    assert (
        config.bankroll_equity == 100
        and CapitalDeployment.objects.get().selection == previous
    )


def test_empty_cycle_skips_historical_experiment_scan(graph, monkeypatch):
    from django.test.utils import CaptureQueriesContext

    monkeypatch.setattr(
        "football.pipeline.service.run_capture",
        lambda **kwargs: CaptureResult(
            run_id=None,
            status="NO_WORK",
            planning_at=AT,
            quota_before={},
            quota_after={},
            plan={"items": []},
        ),
    )
    with CaptureQueriesContext(connection) as queries:
        result = run_pipeline(at=AT, dry_run=True)
    sql = [row["sql"].lower() for row in queries.captured_queries]
    assert result.status == "NO_WORK"
    assert not any("football_decision" in row for row in sql)
    assert not any('from "football_predictionexperiment"' in row for row in sql)
    assert result.report["prediction"]["experiment_count"] == 0
    assert len(str(result.as_dict())) < 20000


@pytest.mark.django_db(transaction=True)
def test_expiring_t30_admitted_before_slow_result_http(graph, monkeypatch, settings):
    settings.FOOTBALL_CAPTURE_DISCOVERY_ENABLED = False
    settings.FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS = 3
    monkeypatch.setattr(
        "football.capital.runtime.quota_state",
        lambda *args: {"basis": "HEADER_FRESH", "remaining": 3},
    )
    monkeypatch.setattr(
        "football.capital.runtime.dynamic_reserve",
        lambda *args: {"fixture": 0, "t10": 0, "execution_quote": 0},
    )
    provision(at=AT)
    old = capture(graph)
    reconcile_global(old.run_id, at=old.run.completed_at)
    due = AT + timedelta(minutes=180)
    fresh = capture(graph, 1, at=due - timedelta(minutes=1))
    calls = []
    effective = [due]
    monkeypatch.setattr(
        "football.strategy.clock.effective_now",
        lambda *, planning_at=None: max(planning_at or AT, effective[0]),
    )
    external_id = f"fs022-{old.match_id}"

    class SlowClient:
        def __init__(self, **kwargs):
            self.calls = 0

        def get_all(self, endpoint, params):
            assert not connection.in_atomic_block
            calls.append(endpoint)
            assert CapitalPosition.objects.filter(match=fresh.match).count() == 1
            effective[0] = fresh.match.kickoff + timedelta(seconds=1)
            self.calls += 1
            return [{"fixture": {"id": external_id}}]

    def sync_stub(items, competitions):
        Match.objects.filter(pk=old.match_id).update(
            status_short="FT",
            outcome="HOME",
            home_score=2,
            away_score=1,
            fulltime_home_score=2,
            fulltime_away_score=1,
        )
        return None, {external_id: old.match}

    monkeypatch.setattr("football.capital.runtime.sync_fixture_payloads", sync_stub)
    result = run_automatic_runtime(
        capture_run_id=fresh.run_id, at=due, client_factory=SlowClient
    )
    assert calls and result.placed == 1 and result.settled == 1, (
        result.placed,
        result.settled,
        result.errors,
        result.evaluations,
    )
    position = CapitalPosition.objects.get(match=fresh.match)
    assert position.placed_at < fresh.match.kickoff
    assert CapitalPosition.objects.get(match=old.match).status == "SETTLED_WIN"
    assert run_automatic_runtime(at=due).placed == 0
    assert CapitalPosition.objects.filter(match=fresh.match).count() == 1


def test_automatic_empty_wake_has_only_operational_queries(graph, monkeypatch):
    from django.test.utils import CaptureQueriesContext

    monkeypatch.setattr(
        "football.pipeline.service.run_capture",
        lambda **kwargs: CaptureResult(
            run_id=None,
            status="NO_WORK",
            planning_at=AT,
            quota_before={},
            quota_after={},
            plan={"items": []},
        ),
    )
    with CaptureQueriesContext(connection) as queries:
        result = run_pipeline(at=AT)
    sql = [row["sql"].lower() for row in queries.captured_queries]
    assert result.status == "NO_WORK"
    assert not any('from "football_predictionexperiment"' in row for row in sql)
    assert not any('from "football_decision"' in row for row in sql)
    assert PredictionExperiment.objects.count() == 0
    assert Prediction.objects.count() == 0
    assert not CapitalPosition.objects.exists()
    assert len(str(result.as_dict())) < 20000
