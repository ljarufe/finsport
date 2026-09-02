from datetime import datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.staticfiles import finders
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from football.models import (
    Bookmaker,
    CapitalExperiment,
    CapitalPolicyRun,
    Competition,
    Decision,
    Match,
    OddsMarket,
    OddsObservation,
    Prediction,
    PredictionExperiment,
    Season,
    Source,
    Team,
)
from football.reporting.presentation import (
    decision_reason_presentations,
    reason_presentations,
)
from football.reporting.selectors import _decision_metrics, historical
from football.templatetags.reporting import as_percent, as_units, yes_no_unknown


@pytest.fixture
def graph(db):
    selected = timezone.localdate()
    competition = Competition.objects.create(
        name="Liga Informe", competition_type="League", country="ES", enabled=True
    )
    other_competition = Competition.objects.create(
        name="Liga Fuera", competition_type="League", country="PE", enabled=True
    )
    season = Season.objects.create(competition=competition, year=selected.year)
    home = Team.objects.create(competition=competition, name="Equipo Local")
    away = Team.objects.create(competition=competition, name="Equipo Visitante")
    kickoff = timezone.make_aware(
        datetime.combine(selected, time(15)), timezone.get_current_timezone()
    )
    match = Match.objects.create(
        season=season,
        home_team=home,
        away_team=away,
        kickoff=kickoff,
        status_short="FT",
        status_long="Match Finished",
        home_score=2,
        away_score=1,
        outcome=Match.OUTCOME_HOME,
    )
    return SimpleNamespace(
        selected=selected,
        competition=competition,
        other_competition=other_competition,
        season=season,
        home=home,
        away=away,
        match=match,
        kickoff=kickoff,
    )


def experiment(graph, *, mode="PROSPECTIVE", competition=None, summary=None):
    return PredictionExperiment.objects.create(
        competition=competition or graph.competition,
        mode=mode,
        period_start=graph.selected - timedelta(days=2),
        period_end=graph.selected + timedelta(days=2),
        summary=summary or {},
    )


def prediction(
    graph,
    exp,
    *,
    match=None,
    model_code=Prediction.DIXON_COLES,
    variant="base",
    config=None,
    predicted=Match.OUTCOME_HOME,
    actual=Match.OUTCOME_HOME,
):
    return Prediction.objects.create(
        experiment=exp,
        match=match or graph.match,
        model_code=model_code,
        variant=variant,
        model_version="v1",
        model_config=config or {},
        cutoff=graph.kickoff - timedelta(hours=1),
        p_home=0.5,
        p_draw=0.3,
        p_away=0.2,
        predicted_outcome=predicted,
        actual_outcome=actual,
    )


def decision(
    graph,
    exp,
    pred,
    *,
    match=None,
    policy="MODAL_ALL",
    variant="base",
    config=None,
    action=Match.OUTCOME_HOME,
    observation=None,
    reason=None,
):
    return Decision.objects.create(
        experiment=exp,
        match=match or graph.match,
        prediction=pred,
        policy_code=policy,
        policy_variant=variant,
        policy_version="v1",
        policy_config=config or {},
        decision_time=graph.kickoff - timedelta(hours=1),
        action=action,
        reason=reason
        or ("MODAL_OUTCOME" if action != Decision.ACTION_NO_BET else "NO_VALID_MARKET"),
        selected_odds_observation=observation,
        selected_price=(
            getattr(observation, action.lower())
            if observation and action != Decision.ACTION_NO_BET
            else None
        ),
    )


def observation(graph, observed_at):
    source, _ = Source.objects.get_or_create(
        code="reporting-test",
        defaults={"name": "Reporting", "base_url": "https://example.test/"},
    )
    bookmaker, _ = Bookmaker.objects.get_or_create(
        source=source, external_id="book", defaults={"name": "Book"}
    )
    market, _ = OddsMarket.objects.get_or_create(
        source=source, external_id="mw", defaults={"name": "1X2"}
    )
    return OddsObservation.objects.create(
        match=graph.match,
        source=source,
        bookmaker=bookmaker,
        market=market,
        home=Decimal("2.00"),
        draw=Decimal("3.00"),
        away=Decimal("4.00"),
        observed_at=observed_at,
    )


@pytest.mark.django_db
def test_routes_valid_invalid_and_empty_filters_are_safe(graph):
    client = Client()
    assert client.get("/").status_code == 200
    assert (
        client.get("/daily/", {"date": graph.selected.isoformat()}).status_code == 200
    )
    assert client.get("/admin/").status_code in {200, 302}
    valid = client.get(
        "/",
        {
            "competition": graph.competition.pk,
            "date_from": graph.selected.isoformat(),
            "date_to": graph.selected.isoformat(),
        },
    )
    assert valid.status_code == 200
    assert "No hay predicciones prospectivas" in valid.content.decode()
    invalid = client.get("/", {"competition": "bad", "date_from": "bad"})
    assert invalid.status_code == 200
    assert "No se aplicaron los filtros" in invalid.content.decode()


@pytest.mark.django_db
def test_unavailable_reason_shapes_and_zero_row_arms_never_crash(graph):
    shapes = {
        "SCALAR": "INSUFFICIENT_LEAK_SAFE_SELECTION_EVIDENCE",
        "LIST": ["NO_VALID_MARKET", "UNKNOWN_CODE"],
        "STRUCTURED": {"unexpected": "shape"},
    }
    experiment(graph, mode="BACKTEST", summary={"unavailable_arms": shapes})
    response = Client().get("/")
    content = response.content.decode()
    assert response.status_code == 200
    assert all(code in content for code in shapes)
    assert "UNKNOWN_CODE" in content
    assert "La forma persistida no es un código" in content
    assert len(reason_presentations(("NO_VALID_MARKET", "UNKNOWN"))) == 2
    assert (
        f"PredictionExperiment #{PredictionExperiment.objects.get(mode='BACKTEST').pk}"
        in content
    )


@pytest.mark.parametrize(
    ("code", "label"),
    (
        ("MODAL_OUTCOME", "Resultado modal seleccionado"),
        ("CONFIDENCE_THRESHOLD_MET", "Umbral de confianza alcanzado"),
        ("BELOW_CONFIDENCE_THRESHOLD", "Confianza por debajo del umbral"),
        ("VALUE_ABOVE_THRESHOLD", "Valor esperado por encima del umbral"),
        (
            "NO_POSITIVE_VALUE_ABOVE_THRESHOLD",
            "Sin valor positivo por encima del umbral",
        ),
        ("NO_VALID_MARKET", "Sin mercado válido"),
        ("EXACT_LEGACY_CONTEXT_UNAVAILABLE", "Contexto legacy exacto no disponible"),
        ("UNAVAILABLE_FOR_REPLAY", "No disponible para replay"),
    ),
)
def test_decision_reason_vocabulary_has_contextual_labels(code, label):
    assert decision_reason_presentations(code)[0]["label"] == label


def test_decision_unknown_reason_is_distinct_from_availability_fallback():
    assert (
        decision_reason_presentations("NEW_DECISION_REASON")[0]["label"]
        == "Motivo no clasificado"
    )
    assert reason_presentations("NEW_AVAILABILITY_REASON")[0]["label"].startswith(
        "No evaluable"
    )


@pytest.mark.django_db
def test_model_and_decision_groups_preserve_both_configs(graph):
    for value in (1, 2):
        exp = experiment(graph)
        pred = prediction(graph, exp, config={"strength": value})
        decision(graph, exp, pred, config={"threshold": value}, variant=str(value))
    context = historical({})
    assert len(context["prediction_rows"]) == 2
    assert len(context["decision_rows"]) == 2
    assert len(context["crosses"]) == 2
    content = Client().get("/").content.decode()
    assert "strength=1" in content and "strength=2" in content
    assert "threshold=1" in content and "threshold=2" in content


@pytest.mark.django_db
def test_prediction_detail_renders_semantic_confusion_and_calibration(graph):
    exp = experiment(graph)
    prediction(graph, exp, config={"xi": 0.01})
    content = Client().get("/").content.decode()
    assert "Matriz de confusión" in content
    assert "Real \\ Predicha" in content
    assert "Calibración" in content
    assert "Probabilidad media" in content
    assert "Frecuencia observada" in content
    assert "50.0%" in content
    assert "confusion_matrix" not in content


@pytest.mark.django_db
def test_decision_resolution_and_temporal_economics_are_separate(graph):
    exp = experiment(graph)
    resolved = prediction(graph, exp)
    unresolved_match = Match.objects.create(
        season=graph.season,
        home_team=graph.home,
        away_team=graph.away,
        kickoff=graph.kickoff + timedelta(hours=1),
        status_short="NS",
        status_long="No iniciado",
    )
    unresolved_exp = experiment(graph)
    unresolved = prediction(graph, unresolved_exp, match=unresolved_match, actual=None)
    rows = [
        decision(graph, unresolved_exp, unresolved, match=unresolved_match),
        decision(graph, exp, resolved, variant="no-bet", action=Decision.ACTION_NO_BET),
        decision(graph, exp, resolved, variant="hit"),
        decision(graph, exp, resolved, variant="loss", action=Match.OUTCOME_AWAY),
        decision(
            graph,
            exp,
            resolved,
            variant="late-price",
            observation=observation(graph, graph.kickoff),
        ),
        decision(
            graph,
            exp,
            resolved,
            variant="valid-price",
            observation=observation(graph, graph.kickoff - timedelta(hours=2)),
        ),
    ]
    metrics = _decision_metrics(rows)
    assert metrics["actionable"] == 5
    assert metrics["resolved_actionable"] == 4
    assert metrics["hits"] == 3
    assert metrics["losses"] == 1
    assert metrics["no_bet_count"] == 1
    assert metrics["economic_decisions"] == 1
    assert metrics["flat_unit_pnl"] == 1.0
    content = Client().get("/").content.decode()
    for heading in (
        "Evaluadas",
        "Accionables",
        "Cobertura",
        "NO_BET",
        "Accionables resueltas",
        "Aciertos",
        "Pérdidas",
        "N económico / Decisions con precio válido",
        "Cobertura económica sobre resueltas",
        "Hit rate",
        "PnL simulado (stake plano 1u)",
        "ROI simulado",
    ):
        assert heading in content
    assert ">1u<" in content
    assert ">100.0%<" in content
    context = historical({})
    assert any(
        row["metrics"]["economic_decisions"] == 0
        and row["metrics"]["flat_unit_pnl"] is None
        and row["metrics"]["roi"] is None
        for row in context["decision_rows"]
    )


@pytest.mark.django_db
def test_agreement_is_instance_bounded_and_not_self_paired(graph):
    for predicted_b in (Match.OUTCOME_HOME, Match.OUTCOME_AWAY):
        exp = experiment(graph)
        prediction(graph, exp, model_code=Prediction.DIXON_COLES)
        prediction(
            graph, exp, model_code=Prediction.INDEPENDENT_POISSON, predicted=predicted_b
        )
    agreements = historical({})["agreements"]
    assert len(agreements) == 1
    assert agreements[0]["n"] == 2
    assert agreements[0]["agreement"] == 1
    assert agreements[0]["disagreements"] == 1
    assert agreements[0]["agreement_rate"] == 0.5


@pytest.mark.django_db
def test_daily_is_prospective_spanish_and_uses_selected_action(graph):
    prospective = experiment(graph)
    prospective_prediction = prediction(
        graph, prospective, config={"xi": 0.01, "basis": "recent"}
    )
    selected_observation = observation(graph, graph.kickoff - timedelta(hours=2))
    decision(
        graph,
        prospective,
        prospective_prediction,
        policy="PROSPECTIVE_POLICY",
        config={"threshold": 0.4},
        observation=selected_observation,
    )
    backtest = experiment(graph, mode="BACKTEST")
    backtest_prediction = prediction(
        graph, backtest, model_code=Prediction.MARKET_CONSENSUS
    )
    decision(graph, backtest, backtest_prediction, policy="BACKTEST_POLICY")
    response = Client().get(
        "/daily/",
        {"date": graph.selected.isoformat(), "competition": graph.competition.pk},
    )
    content = response.content.decode()
    assert response.status_code == 200
    assert "PROSPECTIVE_POLICY" in content
    assert "BACKTEST_POLICY" not in content
    assert "DIXON_COLES · base · v1 · basis=recent · xi=0.01" in content
    assert "threshold=0.4" in content
    assert "Resultado modal seleccionado" in content
    assert "Acierto" in content
    assert "Equipo Local" in content and "Equipo Visitante" in content
    assert "Equipo Local (Liga Informe)" not in content
    assert "Finalizado" in content
    assert "Precio seleccionado" in content
    assert "Reporting" in content and "Book" in content
    assert "Observado" in content and "Decisión" in content
    assert (graph.selected - timedelta(days=1)).isoformat() in content
    assert (graph.selected + timedelta(days=1)).isoformat() in content
    assert "Calibración:" not in content


@pytest.mark.django_db
def test_capital_empty_metrics_do_not_crash_and_filters_do_not_leak(graph):
    visible_source = experiment(graph)
    hidden_source = experiment(graph, competition=graph.other_competition)
    for source, code in (
        (visible_source, "VISIBLE_POLICY"),
        (hidden_source, "HIDDEN_POLICY"),
    ):
        capital = CapitalExperiment.objects.create(
            source_experiment=source,
            source_model_code=Prediction.DIXON_COLES,
            decision_policy_code="MODAL_ALL",
            mode=CapitalExperiment.MODE_REPLAY,
            initial_bankroll=Decimal("100"),
            input_hash=code,
        )
        CapitalPolicyRun.objects.create(
            experiment=capital,
            policy_code=code,
            policy_version="v1",
            status=(
                CapitalPolicyRun.STATUS_PRODUCED
                if code == "VISIBLE_POLICY"
                else CapitalPolicyRun.STATUS_UNAVAILABLE
            ),
            metrics=(
                {
                    "terminal_bankroll": "0",
                    "total_pnl": "0",
                    "roi": "0",
                    "maximum_drawdown": "0",
                    "practical_ruin": False,
                    "max_stake_pre_bankroll_ratio": "0",
                    "stake_concentration": "0.25",
                }
                if code == "VISIBLE_POLICY"
                else {}
            ),
        )
        if code == "VISIBLE_POLICY":
            CapitalPolicyRun.objects.create(
                experiment=capital,
                policy_code="TRUE_RUIN_POLICY",
                policy_version="v1",
                status=CapitalPolicyRun.STATUS_FAILED,
                reason="INSUFFICIENT_CAPITAL",
                metrics={"practical_ruin": True},
            )
    response = Client().get("/", {"competition": graph.competition.pk})
    content = response.content.decode()
    assert response.status_code == 200
    assert "VISIBLE_POLICY" in content
    assert "HIDDEN_POLICY" not in content
    assert "CapitalExperiment #" in content
    assert "Producido" in content and "Fallido" in content
    assert "0u" in content
    assert ">No<" in content and ">Sí<" in content
    assert "Máx. stake / bankroll previo" in content
    assert "Concentración de stake" in content
    assert "25.0%" in content


@pytest.mark.django_db
def test_capital_reporting_uses_mode_specific_metric_contracts(graph):
    source = experiment(graph)

    def capital_run(mode, code, metrics, *, path_count=None):
        capital = CapitalExperiment.objects.create(
            source_experiment=source,
            source_model_code=Prediction.DIXON_COLES,
            decision_policy_code="MODAL_ALL",
            mode=mode,
            initial_bankroll=Decimal("100"),
            input_count=4,
            input_hash=code,
        )
        return CapitalPolicyRun.objects.create(
            experiment=capital,
            policy_code=code,
            policy_version="v1",
            status=CapitalPolicyRun.STATUS_PRODUCED,
            path_count=path_count,
            metrics=metrics,
        )

    replay = capital_run(
        CapitalExperiment.MODE_REPLAY,
        "REPLAY_POLICY",
        {
            "terminal_bankroll": "104",
            "total_pnl": "4",
            "roi": "0.04",
            "maximum_drawdown": "0.02",
            "practical_ruin": False,
            "max_stake_pre_bankroll_ratio": "0.01",
        },
    )
    stochastic_metrics = {
        "path_count": 500,
        "mean_terminal_bankroll": 112,
        "median_terminal_bankroll": 109,
        "terminal_bankroll_quantile_1": 70,
        "terminal_bankroll_quantile_5": 82,
        "mean_pnl": 12,
        "median_pnl": 9,
        "practical_ruin_probability": 0.03,
        "maximum_drawdown_distribution": {
            "mean": 0.12,
            "median": 0.10,
            "quantile_95": 0.30,
            "maximum": 0.50,
        },
        "max_stake_distribution": {
            "mean": 2,
            "median": 1.5,
            "quantile_95": 4,
            "maximum": 6,
        },
        "max_stake_pre_bankroll_ratio_distribution": {
            "mean": 0.02,
            "median": 0.015,
            "quantile_95": 0.04,
            "maximum": 0.06,
        },
        "stake_concentration": 0.025,
        "expected_shortfall": 75,
    }
    monte_carlo = capital_run(
        CapitalExperiment.MODE_MONTE_CARLO,
        "MONTE_CARLO_POLICY",
        stochastic_metrics,
        path_count=500,
    )
    stress_metrics = dict(stochastic_metrics)
    stress_metrics.update(mean_terminal_bankroll=95, mean_pnl=-5)
    stress = capital_run(
        CapitalExperiment.MODE_STRESS,
        "STRESS_POLICY",
        stress_metrics,
        path_count=500,
    )

    context = historical({})
    assert [run.pk for run in context["replay_capital_runs"]] == [replay.pk]
    assert {run.pk for run in context["stochastic_capital_runs"]} == {
        monte_carlo.pk,
        stress.pk,
    }
    assert not hasattr(context["stochastic_capital_runs"][0], "terminal_bankroll")
    assert context["stochastic_capital_runs"][0].mean_terminal_bankroll == 112

    content = Client().get("/").content.decode()
    stochastic_section = content.split("Simulación estocástica", 1)[1].split(
        "</section>", 1
    )[0]
    assert f"PredictionExperiment #{source.pk}" in stochastic_section
    assert Prediction.DIXON_COLES in stochastic_section
    assert "MODAL_ALL" in stochastic_section
    assert "REPLAY_POLICY" not in stochastic_section
    assert "MONTE_CARLO_POLICY" in stochastic_section
    assert "STRESS_POLICY" in stochastic_section
    assert "112u" in stochastic_section and "95u" in stochastic_section
    assert "3.0%" in stochastic_section
    assert "Shortfall esperado" in stochastic_section
    assert "ROI" not in stochastic_section
    assert "Bankroll final" not in stochastic_section


def test_ratio_formatter_converts_half_to_fifty_percent():
    assert as_percent(0.5) == "50.0%"
    assert as_percent(-0.335) == "-33.5%"
    assert as_percent(None) == "—"
    assert yes_no_unknown(False) == "No"
    assert yes_no_unknown(True) == "Sí"
    assert yes_no_unknown(None) == "—"
    assert as_units(Decimal("100.00000000")) == "100u"
    assert as_units(Decimal("99.3300")) == "99.33u"
    assert as_units(Decimal("-0.6700")) == "-0.67u"
    assert as_units(0) == "0u"
    assert as_units(None) == "—"


def test_reporting_static_assets_are_discoverable_by_collectstatic():
    assert finders.find("reporting/bootstrap.min.css")
    assert finders.find("reporting/finsport.css")


@pytest.mark.django_db
def test_default_scope_excludes_all_disabled_competition_evidence(graph):
    graph.other_competition.enabled = False
    graph.other_competition.save(update_fields=["enabled", "modified"])
    disabled_season = Season.objects.create(
        competition=graph.other_competition, year=graph.selected.year
    )
    disabled_home = Team.objects.create(
        competition=graph.other_competition, name="DISABLED_HOME"
    )
    disabled_away = Team.objects.create(
        competition=graph.other_competition, name="DISABLED_AWAY"
    )
    disabled_match = Match.objects.create(
        season=disabled_season,
        home_team=disabled_home,
        away_team=disabled_away,
        kickoff=graph.kickoff,
        status_short="FT",
        status_long="Match Finished",
        outcome=Match.OUTCOME_HOME,
    )

    enabled_exp = experiment(graph)
    enabled_prediction = prediction(graph, enabled_exp)
    decision(
        graph,
        enabled_exp,
        enabled_prediction,
        policy="ENABLED_DECISION",
    )
    enabled_backtest = experiment(
        graph,
        mode="BACKTEST",
        summary={"unavailable_arms": {"ENABLED_BACKTEST": "NO_VALID_MARKET"}},
    )
    assert enabled_backtest.pk

    disabled_exp = experiment(graph, competition=graph.other_competition)
    disabled_prediction = prediction(
        graph, disabled_exp, match=disabled_match, config={"scope": "DISABLED"}
    )
    decision(
        graph,
        disabled_exp,
        disabled_prediction,
        match=disabled_match,
        policy="DISABLED_DECISION",
    )
    experiment(
        graph,
        mode="BACKTEST",
        competition=graph.other_competition,
        summary={"unavailable_arms": {"DISABLED_BACKTEST": "NO_VALID_MARKET"}},
    )
    disabled_capital = CapitalExperiment.objects.create(
        source_experiment=disabled_exp,
        source_model_code=Prediction.DIXON_COLES,
        decision_policy_code="MODAL_ALL",
        mode=CapitalExperiment.MODE_REPLAY,
        initial_bankroll=Decimal("100"),
        input_hash="disabled-capital",
    )
    CapitalPolicyRun.objects.create(
        experiment=disabled_capital,
        policy_code="DISABLED_CAPITAL",
        policy_version="v1",
        status=CapitalPolicyRun.STATUS_UNAVAILABLE,
    )

    home = Client().get("/")
    home_content = home.content.decode()
    assert home.status_code == 200
    assert "ENABLED_DECISION" in home_content
    assert "ENABLED_BACKTEST" in home_content
    assert "DISABLED_DECISION" not in home_content
    assert "DISABLED_BACKTEST" not in home_content
    assert "DISABLED_CAPITAL" not in home_content

    daily = Client().get("/daily/", {"date": graph.selected.isoformat()})
    daily_content = daily.content.decode()
    assert daily.status_code == 200
    assert "Equipo Local" in daily_content
    assert "DISABLED_HOME" not in daily_content

    selected = Client().get("/", {"competition": graph.competition.pk})
    assert selected.status_code == 200
    assert "ENABLED_DECISION" in selected.content.decode()
    invalid_disabled = Client().get("/", {"competition": graph.other_competition.pk})
    assert invalid_disabled.status_code == 200
    assert "No se aplicaron los filtros" in invalid_disabled.content.decode()


@pytest.mark.django_db
def test_daily_query_count_is_bounded_as_rows_grow(graph):
    exp = experiment(graph)

    def add_evidence(index):
        match = Match.objects.create(
            season=graph.season,
            home_team=graph.home,
            away_team=graph.away,
            kickoff=graph.kickoff + timedelta(minutes=index),
            status_short="FT",
            status_long="Finalizado",
            outcome=Match.OUTCOME_HOME,
        )
        pred = prediction(graph, exp, match=match)
        decision(graph, exp, pred, match=match, variant=str(index))

    add_evidence(1)
    url = f"/daily/?date={graph.selected.isoformat()}"
    with CaptureQueriesContext(connection) as small:
        assert Client().get(url).status_code == 200
    for index in range(2, 7):
        add_evidence(index)
    with CaptureQueriesContext(connection) as large:
        assert Client().get(url).status_code == 200
    assert len(large) == len(small)


@pytest.mark.django_db
def test_reporting_gets_are_read_only_and_do_not_dispatch(graph):
    counts = (
        Prediction.objects.count(),
        Decision.objects.count(),
        CapitalExperiment.objects.count(),
    )
    with (
        patch("football.tasks.run_pipeline") as pipeline,
        patch("football.tasks.run_capture") as capture,
    ):
        assert Client().get("/").status_code == 200
        assert (
            Client().get("/daily/", {"date": graph.selected.isoformat()}).status_code
            == 200
        )
    assert not pipeline.called and not capture.called
    assert counts == (
        Prediction.objects.count(),
        Decision.objects.count(),
        CapitalExperiment.objects.count(),
    )
