"""FS-022 product UI: only the governed #209 simulation and bounded reads."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.staticfiles import finders
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext

from football.models import (
    CapitalEvaluation,
    CapitalExecutionState,
    CapitalPosition,
    CaptureWorkItem,
    Competition,
    Decision,
    Prediction,
    PredictionExperiment,
    Season,
)
from football.reporting.selectors import home, match_detail, matches_day
from football.strategy.deployment import provision
from football.strategy.prospective import reconcile_global
from football.tests.test_fs022_strategy import AT, capture
from football.tests.test_fs022_strategy import graph as graph

pytestmark = pytest.mark.django_db
NOW = datetime(2026, 9, 29, 3, tzinfo=UTC)  # 28 September, 22:00 in Lima.


@pytest.fixture(autouse=True)
def simulated_clock(monkeypatch):
    monkeypatch.setattr(
        "football.strategy.clock.effective_now",
        lambda *, planning_at=None: planning_at or AT,
    )


def ui_client():
    return Client(HTTP_HOST="localhost")


def set_status(position, status, pnl, settled_at):
    position.status = status
    position.realized_pnl = Decimal(str(pnl))
    position.settled_at = settled_at
    position.save(update_fields=["status", "realized_pnl", "settled_at"])


def test_empty_home_uses_one_bank_and_real_calendar(graph):
    (config,) = provision(at=AT)
    old = config.__class__.objects.create(
        identity="retired-comparator",
        runtime_version="fs016-capital-runtime-v2",
        execution_version="legacy",
        mode="CURRENT",
        automatic=True,
        current=False,
        entry_enabled=False,
        source_model_code="DIXON_COLES",
        decision_policy_code="MODAL_ALL",
        policy_code="FLAT_UNIT",
        policy_version="v1",
        policy_config={},
        max_lanes=1,
        initial_bankroll=Decimal("100"),
        bankroll_equity=Decimal("999"),
        peak_equity=Decimal("999"),
    )
    assert old.pk != config.pk
    context = home()
    assert context["capital"] == {
        "equity": Decimal("100"),
        "initial": Decimal("100"),
        "available": Decimal("100"),
        "reserved": Decimal("0"),
    }
    assert len(context["results"]) == 4
    assert all(row["pnl"] == 0 and row["rate"] is None for row in context["results"])
    assert context["chart"]["empty"] and context["activity"][0]["count"] == 0
    response = ui_client().get("/")
    text = response.content.decode()
    assert response.status_code == 200
    assert "100u" in text and "999u" not in text
    assert "Sin liquidaciones" in text
    assert "Dixon-Coles" not in text and "MARKET_CONSENSUS" not in text
    assert (
        "Inicio" in text
        and "Partidos" in text
        and "Admin" in text
        and "Grafana" in text
    )
    assert "FS022 League" in text


def test_home_ledger_periods_chart_activity_and_void(graph, monkeypatch):
    (config,) = provision(at=AT)
    positions = []
    for index in range(4):
        work = capture(graph, index, at=AT + timedelta(minutes=index + 1))
        assert reconcile_global(work.run_id, at=work.run.completed_at).placed == 1
        positions.append(CapitalPosition.objects.get(match=work.match))
    # Settlement day in Lima, rather than kickoff or UTC settlement date, owns P&L.
    set_status(positions[0], "SETTLED_WIN", "2", datetime(2026, 9, 28, 3, tzinfo=UTC))
    set_status(positions[1], "SETTLED_LOSS", "-1", datetime(2026, 9, 29, 2, tzinfo=UTC))
    set_status(positions[3], "VOID", "0", datetime(2026, 9, 29, 1, tzinfo=UTC))
    config.bankroll_equity = Decimal("101")
    config.reserved_exposure = positions[2].applied_stake
    config.save(update_fields=["bankroll_equity", "reserved_exposure", "modified"])
    monkeypatch.setattr("football.reporting.selectors.timezone.now", lambda: NOW)
    context = home()
    assert context["warnings"] == []
    assert context["capital"]["equity"] == 101
    assert context["capital"]["reserved"] == positions[2].applied_stake
    assert (
        context["capital"]["available"] + context["capital"]["reserved"]
        == context["capital"]["equity"]
    )
    today, week, month, total = context["results"]
    assert today["pnl"] == -1 and today["opening_equity"] == 102
    assert today["rate"] == Decimal("-1") / 102
    assert week["pnl"] == -1
    assert month["pnl"] == total["pnl"] == 1
    assert total["opening_equity"] == 100
    assert context["chart"]["points"][-1]["equity"] == 101
    assert len(context["chart"]["points"]) <= 90
    assert [item["count"] for item in context["activity"]] == [4, 4, 1, 1]
    text = ui_client().get("/").content.decode()
    assert "101u" in text and "102u" in text
    assert "Apostado actualmente" in text


def test_observed_counts_once_across_captures_and_excludes_no_bet_pnl(graph):
    provision(at=AT)
    work = capture(graph, 10, prices=(("3", "3", "3"), ("3", "3", "3")))
    assert reconcile_global(work.run_id, at=work.run.completed_at).placed == 0
    CaptureWorkItem.objects.create(
        run=work.run,
        purpose="ODDS_CAPTURE",
        status="SUCCESS",
        source=work.source,
        market=work.market,
        match=work.match,
        logical_identity="extra-capture",
        intended_window="market-t60m",
        target_at=work.target_at,
        executed_at=work.executed_at,
        completed_at=work.completed_at,
    )
    context = home()
    assert [item["count"] for item in context["activity"]] == [1, 0, 0, 0]
    assert context["results"][-1]["pnl"] == 0
    assert context["results"][-1]["rate"] is None
    assert (
        "No seleccionado"
        in ui_client().get("/partidos/?date=2026-09-27").content.decode()
    )


def test_league_current_next_and_missing_calendar(graph, monkeypatch):
    season = graph[-1]
    season.start_date = date(2026, 1, 1)
    season.end_date = date(2026, 9, 27)
    season.save()
    season.competition.seasons.create(
        year=2027, start_date=date(2027, 1, 1), end_date=date(2027, 12, 31)
    )
    Competition.objects.create(
        name="Sin fechas", country="AR", competition_type="League", enabled=True
    )
    monkeypatch.setattr(
        "football.reporting.selectors.timezone.now",
        lambda: datetime(2026, 9, 27, 19, tzinfo=UTC),
    )
    rows = home()["leagues"]
    assert (
        next(row for row in rows if row["name"] == graph[3].name)["status"]
        == "En curso"
    )
    monkeypatch.setattr("football.reporting.selectors.timezone.now", lambda: NOW)
    rows = home()["leagues"]
    assert (
        next(row for row in rows if row["name"] == graph[3].name)["season"].year == 2027
    )
    assert (
        next(row for row in rows if row["name"] == "Sin fechas")["status"]
        == "Sin calendario"
    )


def test_matches_lima_day_filters_groups_and_lazy_detail(graph):
    provision(at=AT)
    placed = capture(graph, 20, at=datetime(2026, 9, 28, 0, 30, tzinfo=UTC))
    assert reconcile_global(placed.run_id, at=placed.run.completed_at).placed == 1
    position = CapitalPosition.objects.get(match=placed.match)
    position.match.status_short = "FT"
    position.match.fulltime_home_score = 2
    position.match.fulltime_away_score = 1
    position.match.outcome = "HOME"
    position.match.save()
    set_status(position, "SETTLED_WIN", "1", NOW)
    no_bet = capture(
        graph,
        21,
        at=datetime(2026, 9, 28, 0, 31, tzinfo=UTC),
        prices=(("3", "3", "3"), ("3", "3", "3")),
    )
    reconcile_global(no_bet.run_id, at=no_bet.run.completed_at)
    no_bet.match.status_short = "FT"
    no_bet.match.outcome = "DRAW"
    no_bet.match.save()
    untouched = capture(graph, 22, at=datetime(2026, 9, 28, 0, 32, tzinfo=UTC))
    # A second league on the same Lima day verifies the competition filter.
    other = Competition.objects.create(
        name="Otra Liga", country="PE", competition_type="League", enabled=True
    )
    other_season = Season.objects.create(competition=other, year=2026)
    untouched.match.season = other_season
    untouched.match.save(update_fields=["season", "modified"])
    response = ui_client().get("/partidos/?date=2026-09-27")
    text = response.content.decode()
    assert response.status_code == 200
    assert "2–1" in text and "Apuesta ganada" in text
    assert "No seleccionado" in text and "Sin evaluación" in text
    assert "DIXON_COLES" not in text and "Probabilidad local" not in text
    assert "Más información" in text
    assert "Terminado" in text or "Terminados" in text
    filtered = (
        ui_client()
        .get(f"/partidos/?date=2026-09-27&competition={graph[3].pk}")
        .content.decode()
    )
    assert untouched.match.home_team.name not in filtered
    assert placed.match.home_team.name in filtered
    assert matches_day({"date": "2026-09-28"})["page"].paginator.count == 0
    detail = ui_client().get(f"/partidos/{placed.match.pk}/detalle/")
    assert detail.status_code == 200
    assert "Probabilidad local" in detail.content.decode()
    assert (
        "T−30 min" in detail.content.decode() and "Pinnacle" in detail.content.decode()
    )
    assert "MARKET_CONSENSUS" not in detail.content.decode()


def test_capacity_expiration_open_loss_and_void_statuses(graph):
    (config,) = provision(at=AT)
    open_work = capture(graph, 30)
    reconcile_global(open_work.run_id, at=open_work.run.completed_at)
    loss_work = capture(graph, 31)
    reconcile_global(loss_work.run_id, at=loss_work.run.completed_at)
    void_work = capture(graph, 32)
    reconcile_global(void_work.run_id, at=void_work.run.completed_at)
    for work, status, pnl in (
        (loss_work, "SETTLED_LOSS", "-1"),
        (void_work, "VOID", "0"),
    ):
        position = CapitalPosition.objects.get(match=work.match)
        set_status(position, status, pnl, NOW)
        work.match.status_short = "FT"
        work.match.save()
    pending = capture(graph, 33)
    CapitalExecutionState.objects.create(
        config=config, match=pending.match, status="PENDING_CAPACITY"
    )
    expired = capture(graph, 34)
    CapitalExecutionState.objects.create(
        config=config,
        match=expired.match,
        status="NOT_PLACED",
        non_placement_reason="EXPIRED_CAPACITY",
    )
    statuses = {
        row["match"].pk: row
        for _, rows in matches_day({"date": "2026-09-27"})["groups"]
        for row in rows
    }
    assert statuses[open_work.match_id]["label"] == "Apuesta pendiente"
    assert statuses[loss_work.match_id]["label"] == "Apuesta perdida"
    assert statuses[void_work.match_id]["label"] == "Apuesta anulada"
    assert statuses[pending.match_id]["label"] == "Esperando capacidad"
    assert (
        statuses[expired.match_id]["reason"]
        == "La capacidad se liberó después del inicio"
    )


def test_query_cost_does_not_grow_with_scientific_history(graph):
    provision(at=AT)
    work = capture(graph, 40)
    result = reconcile_global(work.run_id, at=work.run.completed_at)
    assert result.placed == 1
    client = ui_client()
    paths = ("/", "/partidos/?date=2026-09-27")

    def measure():
        counts = []
        for path in paths:
            with CaptureQueriesContext(connection) as queries:
                response = client.get(path)
            assert response.status_code == 200
            sql = [row["sql"].lower() for row in queries.captured_queries]
            assert not any('from "football_predictionexperiment"' in row for row in sql)
            counts.append(len(queries))
        return counts

    before = measure()
    PredictionExperiment.objects.bulk_create(
        [
            PredictionExperiment(
                competition=graph[3],
                mode="BACKTEST",
                period_start=date(2025, 1, 1),
                period_end=date(2025, 1, 1),
                logical_identity=f"old-science-{index}",
            )
            for index in range(150)
        ]
    )
    after = measure()
    assert after == before
    assert before[0] <= 20 and before[1] <= 15
    with CaptureQueriesContext(connection) as queries:
        response = client.get(f"/partidos/{work.match_id}/detalle/")
    assert response.status_code == 200
    assert any("football_oddsobservation" in row["sql"].lower() for row in queries)
    with CaptureQueriesContext(connection) as queries:
        client.get("/partidos/?date=2026-09-27")
    assert not any("football_oddsobservation" in row["sql"].lower() for row in queries)


def test_navigation_no_historical_route_and_read_only(graph):
    provision(at=AT)
    work = capture(graph, 50)
    before = (
        CapitalPosition.objects.count(),
        Prediction.objects.count(),
        Decision.objects.count(),
        CapitalEvaluation.objects.count(),
    )
    with patch(
        "football.providers.api_football.APIFootballClient.get_all",
        side_effect=AssertionError("provider called"),
    ):
        with override_settings(FINSPORT_GRAFANA_URL="https://grafana.example.invalid/"):
            home_response = ui_client().get("/")
            day_response = ui_client().get("/partidos/?date=2026-09-27")
    assert "https://grafana.example.invalid/" in home_response.content.decode()
    assert "/admin/" in day_response.content.decode()
    assert ui_client().get("/daily/").status_code == 404
    assert before == (
        CapitalPosition.objects.count(),
        Prediction.objects.count(),
        Decision.objects.count(),
        CapitalEvaluation.objects.count(),
    )
    assert finders.find("reporting/bootstrap.min.css")
    assert finders.find("reporting/finsport.css")
    assert finders.find("reporting/partidos.js")
    assert not finders.find("reporting/historical.css")
    assert match_detail(work.match_id)["decision"] is None


def test_no_calendar_verified_is_not_false_empty(graph):
    context = matches_day({"date": "2026-10-04"})
    assert (
        context["empty_calendar"] == "Aún no hay calendario verificado para esta fecha."
    )
    assert context["page"].paginator.count == 0


def test_persisted_capital_reasons_distinguish_no_edge_from_no_evaluation(graph):
    from football.models import CapitalDeployment
    from football.strategy.prospective import evaluate_work

    (config,) = provision(at=AT)
    no_bet = capture(graph, 61, prices=(("3", "3", "3"), ("3", "3", "3")))
    reconcile_global(no_bet.run_id, at=no_bet.run.completed_at)
    no_edge = capture(graph, 62)
    decision, reason = evaluate_work(no_edge, at=no_edge.run.completed_at)
    assert reason == "" and decision.action != "NO_BET"
    CapitalEvaluation.objects.create(
        deployment=CapitalDeployment.objects.get(pk=1),
        work=no_edge,
        experiment=decision.experiment,
        status="COMPLETED",
        reason=decision.reason,
        attempted_at=no_edge.run.completed_at,
    )
    CapitalExecutionState.objects.create(
        config=config,
        match=no_edge.match,
        status="NOT_PLACED",
        non_placement_reason="INELIGIBLE",
        diagnostics={"policy_reason": "NO_POSITIVE_KELLY_EDGE"},
    )
    open_work = capture(graph, 65)
    assert reconcile_global(open_work.run_id, at=open_work.run.completed_at).placed == 1
    settled_work = capture(graph, 66)
    assert (
        reconcile_global(settled_work.run_id, at=settled_work.run.completed_at).placed
        == 1
    )
    set_status(
        CapitalPosition.objects.get(match=settled_work.match), "SETTLED_WIN", "1", NOW
    )
    unseen = capture(graph, 60)
    pending = capture(graph, 63)
    CapitalExecutionState.objects.create(
        config=config, match=pending.match, status="PENDING_CAPACITY"
    )
    expired = capture(graph, 64)
    CapitalExecutionState.objects.create(
        config=config,
        match=expired.match,
        status="NOT_PLACED",
        non_placement_reason="EXPIRED_CAPACITY",
    )
    rows = {
        row["match"].pk: row
        for _, group in matches_day({"date": "2026-09-27"})["groups"]
        for row in group
    }
    assert rows[unseen.match_id]["label"] == "Sin evaluación"
    assert rows[no_bet.match_id]["label"] == "No seleccionado"
    assert rows[no_edge.match_id]["label"] == "Sin apuesta"
    assert rows[no_edge.match_id]["reason"] == "Sin valor económico positivo"
    assert rows[no_edge.match_id]["action"] == "Local"
    assert rows[pending.match_id]["label"] == "Esperando capacidad"
    assert (
        rows[expired.match_id]["reason"] == "La capacidad se liberó después del inicio"
    )
    assert rows[open_work.match_id]["label"] == "Apuesta pendiente"
    assert rows[settled_work.match_id]["label"] == "Apuesta ganada"
    page = ui_client().get("/partidos/?date=2026-09-27").content.decode()
    detail = ui_client().get(f"/partidos/{no_edge.match_id}/detalle/").content.decode()
    assert (
        "Sin valor económico positivo" in page
        and "Sin valor económico positivo" in detail
    )
    assert "Evaluación no disponible" not in page + detail
    assert "Selección: <strong>Local</strong>" in detail


def test_equity_chart_follows_each_settlement_and_stable_timestamp_ties(
    graph, monkeypatch
):
    (config,) = provision(at=AT)
    pnls = (
        Decimal("-3.92585100"),
        Decimal("7.27879589"),
        Decimal("8.94241438"),
        Decimal("-14.91216305"),
    )
    settled_at = (
        datetime(2026, 9, 27, 23, tzinfo=UTC),
        datetime(2026, 9, 28, 2, tzinfo=UTC),
        datetime(2026, 9, 28, 12, tzinfo=UTC),
        datetime(2026, 9, 28, 12, tzinfo=UTC),
    )
    for index, (pnl, at) in enumerate(zip(pnls, settled_at, strict=True)):
        work = capture(graph, 70 + index)
        assert reconcile_global(work.run_id, at=work.run.completed_at).placed == 1
        position = CapitalPosition.objects.get(match=work.match)
        set_status(position, "SETTLED_WIN" if pnl > 0 else "SETTLED_LOSS", pnl, at)
    config.bankroll_equity = Decimal("97.38319622")
    config.reserved_exposure = Decimal("0")
    config.save(update_fields=["bankroll_equity", "reserved_exposure", "modified"])
    monkeypatch.setattr("football.reporting.selectors.timezone.now", lambda: NOW)
    chart = home()["chart"]
    assert [point["kind"] for point in chart["points"]] == ["initial"] + [
        "settlement"
    ] * 4
    assert [point["pnl"] for point in chart["events"]] == list(pnls)
    assert [point["equity"] for point in chart["points"]] == [
        Decimal("100"),
        Decimal("96.07414900"),
        Decimal("103.35294489"),
        Decimal("112.29535927"),
        Decimal("97.38319622"),
    ]
    assert [point["day"] for point in chart["events"]] == [
        date(2026, 9, 27),
        date(2026, 9, 27),
        date(2026, 9, 28),
        date(2026, 9, 28),
    ]
    assert chart["events"][2]["at"] == chart["events"][3]["at"]
    page = ui_client().get("/").content.decode()
    assert "96.074149u" in page and "112.29535927u" in page
    assert "97.38319622u" in page and "-14.91216305u" in page
    assert page.count("<circle ") == 5
