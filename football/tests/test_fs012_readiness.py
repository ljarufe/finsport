"""FS-012 focused acceptance: real local models, isolated DB, no provider access."""

import copy
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from football.models import (
    Competition,
    HistoricalCoverage,
    Match,
    Prediction,
    ReadinessProfile,
    Team,
)
from football.pipeline.service import _dixon_coles_candidates, _sporting_candidates
from football.prediction import calibration, evaluation
from football.prediction import readiness_lifecycle as lifecycle
from football.prediction.contracts import (
    ProbabilityResult,
)
from football.prediction.elo import EloMultinomialAdapter, sequential_elo_features
from football.prediction.goal_models import DixonColesAdapter, IndependentPoissonAdapter
from football.prediction.readiness import active_profile
from football.prediction.service import predict_competition_day
from football.reporting.presentation import (
    DECISION_REASONS,
    decision_reason_presentations,
)

from .prediction_helpers import create_synthetic_league, create_synthetic_odds
from .test_fs011_dixon_coles import complete_coverage, future_target

POISSON, ELO = lifecycle.AUTOMATIC_MODELS


@pytest.fixture(autouse=True)
def no_providers(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("FS-012 must not call a provider")

    monkeypatch.setattr("requests.sessions.Session.request", forbidden)


def profile_fixture(competition, model, *, requirements=None):
    """Controlled explicit profile; empirical assertions use real calibration below."""
    adapter = (
        IndependentPoissonAdapter(xi=0.002)
        if model == POISSON
        else EloMultinomialAdapter(k=10, c=0.1)
    )
    identity, payload, _, _, reason = lifecycle.current_basis(competition, model)
    assert not reason
    return ReadinessProfile.objects.create(
        competition=competition,
        model_code=model,
        version="controlled-v1",
        model_version=adapter.model_version,
        model_config=adapter.config,
        approved=True,
        requirements=requirements or {},
        basis_identity=identity,
        evidence={"basis": payload},
        disposition="NO_ADDITIONAL_STATISTICAL_GATE_JUSTIFIED",
        calibration_strategy_version=calibration.STRATEGY_VERSION,
        profile_rule_version=calibration.PROFILE_RULE_VERSION,
    )


def test_independent_finite_selectors(monkeypatch):
    calls = []

    def loss(factory, config, *args):
        calls.append((factory, config))
        if factory is DixonColesAdapter:
            return 0 if config["xi"] == 0 else 2
        if factory is IndependentPoissonAdapter:
            return 0.5 if config["xi"] == 0.002 else float("nan")
        return 0.4 if config == {"k": 40, "c": 10.0} else float("inf")

    monkeypatch.setattr(evaluation, "_validation_loss", loss)
    selected = evaluation.select_hyperparameters([], [])
    assert selected["dixon_coles"]["xi"] == 0
    assert selected["independent_poisson"]["xi"] == 0.002
    assert selected["independent_poisson"]["selected_by"] == "independent_poisson"
    assert selected["elo_multinomial_logit"]["k"] == 40
    assert selected["elo_multinomial_logit"]["C"] == 10
    assert {c["xi"] for f, c in calls if f is IndependentPoissonAdapter} == {
        0,
        0.001,
        0.002,
    }


def test_all_nonfinite_no_fake_winner(monkeypatch):
    monkeypatch.setattr(evaluation, "_validation_loss", lambda *a: float("inf"))
    selected = evaluation.select_hyperparameters([], [])
    for name in ("independent_poisson", "elo_multinomial_logit"):
        assert selected[name]["status"] == "UNAVAILABLE"
        assert not {"xi", "k", "C"} & selected[name].keys()


@pytest.mark.django_db
def test_poisson_structural_guards_and_disconnected_diagnostic():
    competition, _, history = create_synthetic_league()
    model = IndependentPoissonAdapter(xi=0)
    assert model.fit([], timezone.now()).reason == "INSUFFICIENT_TRAINING_HISTORY"
    # Repeated disjoint fixture pairs are mechanically representable in pure Poisson.
    pairs = {
        (history[0].home_team_id, history[0].away_team_id),
        (history[1].home_team_id, history[1].away_team_id),
    }
    training = [m for m in history if (m.home_team_id, m.away_team_id) in pairs]
    assert model.fit(training, timezone.now()) is model
    assert isinstance(model.predict(history[0], timezone.now()), ProbabilityResult)
    target = copy.copy(history[0])
    target.home_team_id = 999999
    assert model.predict(target, timezone.now()).reason == "INSUFFICIENT_TEAM_HISTORY"


@pytest.mark.django_db
def test_elo_classes_new_team_and_same_day_freeze():
    competition, _, history = create_synthetic_league()
    model = EloMultinomialAdapter(k=20, c=0.1)
    assert (
        model.fit([m for m in history if m.outcome != "DRAW"]).reason
        == "INSUFFICIENT_OUTCOME_CLASSES"
    )
    assert model.fit(history) is model
    target = copy.copy(history[0])
    target.home_team_id = 999999
    result = model.predict(target)
    assert isinstance(result, ProbabilityResult)
    assert result.diagnostics["home_team_history"] == 0
    assert result.diagnostics["home_pre_rating"] == 1500
    a, b = copy.copy(history[0]), copy.copy(history[1])
    b.home_team_id = a.home_team_id
    b.kickoff = a.kickoff + timedelta(hours=1)
    features, _, _ = sequential_elo_features([a, b], k=20)
    assert features == [[0, 0], [0, 0]]


@pytest.mark.django_db
@pytest.mark.parametrize("model", [POISSON, ELO])
@pytest.mark.parametrize("blocked", [False, True])
def test_real_prospective_profile_and_decision_separation(model, blocked):
    competition, _, history = create_synthetic_league()
    complete_coverage(competition)
    target = future_target(competition, [history[0].home_team, history[0].away_team])
    profile = profile_fixture(
        competition,
        model,
        requirements={"min_home_team_matches": 10000} if blocked else {},
    )
    result = predict_competition_day(
        competition,
        calibration.local_day(target.kickoff),
        timezone.now(),
        model_codes=[model],
        match_ids=[target.pk],
    )
    prediction = result.experiment.predictions.get()
    assert prediction.readiness_profile == profile
    assert prediction.bet_eligible is not blocked
    assert prediction.evidence_identity
    assert prediction.model_config.items() >= profile.model_config.items()
    if blocked:
        assert prediction.readiness_reason == "HOME_TEAM_HISTORY_BELOW_PROFILE"
        assert set(prediction.decisions.values_list("action", flat=True)) == {"NO_BET"}
    else:
        assert prediction.readiness_reason == "APPROVED_READINESS_PROFILE_PASSED"
        assert (
            prediction.decisions.filter(policy_code="MODAL_ALL")
            .exclude(action="NO_BET")
            .exists()
        )


@pytest.mark.django_db
def test_elo_prior_only_profile_applies():
    competition, _, history = create_synthetic_league()
    complete_coverage(competition)
    newcomer = Team.objects.create(competition=competition, name="Prior only")
    target = future_target(competition, [newcomer, history[0].away_team])
    profile_fixture(competition, ELO, requirements={"min_home_team_matches": 1})
    result = predict_competition_day(
        competition,
        calibration.local_day(target.kickoff),
        timezone.now(),
        model_codes=[ELO],
    )
    prediction = result.experiment.predictions.get()
    assert prediction.diagnostics["home_pre_rating"] == 1500
    assert prediction.bet_eligible is False


@pytest.mark.django_db
def test_allinf_prospective_is_unavailable_without_prediction(monkeypatch):
    competition, _, history = create_synthetic_league()
    target = future_target(competition, [history[0].home_team, history[0].away_team])
    monkeypatch.setattr(
        "football.prediction.service.latest_selected_config",
        lambda _: (
            {
                "elo_multinomial_logit": {
                    "status": "UNAVAILABLE",
                    "reason": "NO_FINITE_ELO_HYPERPARAMETER_CANDIDATE",
                }
            },
            "controlled",
        ),
    )
    result = predict_competition_day(
        competition,
        calibration.local_day(target.kickoff),
        timezone.now(),
        model_codes=[ELO],
    )
    assert not result.experiment.predictions.exists()
    assert not result.experiment.decisions.exists()
    assert (
        result.experiment.summary["unavailable"][ELO]
        == "NO_FINITE_ELO_HYPERPARAMETER_CANDIDATE"
    )


@pytest.mark.django_db
def test_real_future_competition_calibration_and_no_work(monkeypatch):
    competition, _, _ = create_synthetic_league()
    complete_coverage(competition)
    result = lifecycle.run_readiness_maintenance()
    assert result["full_calibrations"] == 2
    assert {row["outcome"] for row in result["results"]} == {"CREATED"}
    profiles = list(ReadinessProfile.objects.filter(active=True))
    assert len(profiles) == 2 and all(p.approved for p in profiles)
    for profile in profiles:
        evidence = profile.evidence["calibration"]
        assert evidence["development_seasons"] == [2022, 2023]
        assert evidence["outer_season"] == 2024
        assert evidence["outer_metrics"]["produced"] > 0
        assert evidence["provenance"]["outer_retuned"] is False
    monkeypatch.setattr(
        calibration,
        "run_model_competition",
        Mock(side_effect=AssertionError("No recalibration")),
    )
    unchanged = lifecycle.run_readiness_maintenance()
    assert unchanged["full_calibrations"] == 0
    assert {row["outcome"] for row in unchanged["results"]} == {"NO_WORK"}


@pytest.mark.django_db
def test_initial_exact_twenty_frozen_configs_and_idempotency(monkeypatch):
    # Frozen data is real; tiny deterministic sporting basis replaces only DB history.
    frozen = lifecycle.frozen_profiles()
    expected_xi = {
        1270: 0.002,
        1272: 0.002,
        1273: 0.002,
        1274: 0.001,
        1275: 0.002,
        1276: 0.001,
        1277: 0.001,
        1278: 0.001,
        1325: 0.002,
        1459: 0,
    }
    for row in frozen[::2]:
        Competition.objects.create(
            pk=row["competition_id"],
            name=row["competition"],
            country=row["country"],
            competition_type="League",
            enabled=True,
        )

    def sporting_basis(comp):
        profile = next(p for p in frozen if p["competition_id"] == comp.pk)
        return lifecycle.SportingBasis(
            payload={"sporting_basis_hash": profile["sporting_basis_hash"]},
            seasons=(),
            by_year={},
            reason="",
        )

    monkeypatch.setattr(lifecycle, "build_sporting_basis", sporting_basis)
    monkeypatch.setattr(
        calibration,
        "run_model_competition",
        Mock(side_effect=AssertionError("Frozen must not recalibrate")),
    )
    result = lifecycle.run_readiness_maintenance()
    assert len(result["results"]) == 20
    assert result["full_calibrations"] == 0
    assert {row["outcome"] for row in result["results"]} == {"CREATED"}
    for profile in ReadinessProfile.objects.all():
        assert profile.approved and profile.active and profile.requirements == {}
        assert profile.disposition == "NO_ADDITIONAL_STATISTICAL_GATE_JUSTIFIED"
        assert profile.calibration_strategy_version == "fs012-phase-a-season-block-v2"
        if profile.model_code == POISSON:
            assert profile.model_config["xi"] == expected_xi[profile.competition_id]
            assert profile.version == "fs012-independent_poisson-2025-v1"
        else:
            assert profile.model_config["k"] == (
                10 if profile.competition_id == 1270 else 20
            )
            assert profile.model_config["C"] == 0.1
            assert profile.version == "fs012-elo_multinomial_logit-2025-v1"
    assert {r["outcome"] for r in lifecycle.run_readiness_maintenance()["results"]} == {
        "NO_WORK"
    }
    assert ReadinessProfile.objects.count() == 20


@pytest.mark.django_db
@pytest.mark.parametrize(
    "change", ["model", "strategy", "rule", "season", "sporting", "coverage"]
)
def test_material_changes_invalidate_currentness(change, monkeypatch):
    competition, seasons, history = create_synthetic_league()
    coverage = complete_coverage(competition)
    profile = profile_fixture(competition, POISSON)
    before = profile.basis_identity
    if change == "model":
        monkeypatch.setattr(calibration, "INDEPENDENT_POISSON_VERSION", "future-model")
    if change == "strategy":
        monkeypatch.setattr(calibration, "STRATEGY_VERSION", "future-strategy")
    if change == "rule":
        monkeypatch.setattr(calibration, "PROFILE_RULE_VERSION", "future-rule")
    if change == "season":
        seasons[-1].is_current = True
        seasons[-1].save()
    if change == "sporting":
        history[0].home_score += 1
        history[0].save()
    if change == "coverage":
        coverage.status = HistoricalCoverage.Status.PARTIAL
        coverage.save()
    assert lifecycle.current_basis(competition, POISSON)[0] != before
    assert not lifecycle.profile_is_current(competition, profile)


@pytest.mark.django_db
def test_price_only_no_work_and_sporting_pipeline_identity(monkeypatch):
    competition, _, history = create_synthetic_league()
    complete_coverage(competition)
    target = future_target(competition, [history[0].home_team, history[0].away_team])
    profile_fixture(competition, POISSON)
    profile_fixture(competition, ELO)
    at = timezone.now()
    before = {
        code: _sporting_candidates(at, model_code=code) for code in (POISSON, ELO)
    }
    assert all(before.values())
    create_synthetic_odds([target, history[0]])
    after = {code: _sporting_candidates(at, model_code=code) for code in (POISSON, ELO)}
    assert before == after
    monkeypatch.setattr(
        calibration,
        "run_model_competition",
        Mock(side_effect=AssertionError("Odds must not trigger calibration")),
    )
    assert {r["outcome"] for r in lifecycle.run_readiness_maintenance()["results"]} == {
        "NO_WORK"
    }
    candidate = before[ELO][0]
    kwargs = {k: v for k, v in candidate.items() if k not in {"competition_id", "day"}}
    first = predict_competition_day(competition, candidate["day"], **kwargs)
    second = predict_competition_day(competition, candidate["day"], **kwargs)
    assert first.created and not second.created
    assert (
        first.experiment.predictions.get().evidence_identity
        == candidate["evidence_identity"]
    )


@pytest.mark.django_db
def test_poisson_and_elo_candidates_survive_stale_coverage_but_dc_does_not():
    competition, _, history = create_synthetic_league()
    coverage = complete_coverage(competition)
    target = future_target(competition, [history[0].home_team, history[0].away_team])
    for model in (POISSON, ELO):
        profile_fixture(competition, model)
    coverage.status = HistoricalCoverage.Status.PARTIAL
    coverage.save(update_fields=["status", "modified"])

    at = timezone.now()
    assert _dixon_coles_candidates(at) == []
    for model in (POISSON, ELO):
        candidates = _sporting_candidates(at, model_code=model)
        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate["match_ids"] == [target.pk]
        kwargs = {
            key: value
            for key, value in candidate.items()
            if key not in {"competition_id", "day"}
        }
        result = predict_competition_day(competition, candidate["day"], **kwargs)
        prediction = result.experiment.predictions.get(model_code=model)
        assert prediction.bet_eligible is False
        assert prediction.readiness_reason == "READINESS_PROFILE_STALE"


@pytest.mark.django_db
def test_stale_revalidation_supersedes_auditable_profile(monkeypatch):
    competition, _, _ = create_synthetic_league()
    complete_coverage(competition)
    previous = profile_fixture(competition, ELO)
    monkeypatch.setattr(calibration, "ELO_MULTINOMIAL_LOGIT_VERSION", "new-model")
    result = lifecycle.provision_profile(competition, ELO)
    assert result["outcome"] == "UPDATED"
    current = active_profile(competition, model_code=ELO)
    assert current.supersedes == previous and current.model_version == "new-model"
    previous.refresh_from_db()
    assert not previous.active


@pytest.mark.django_db
def test_observability_unavailable_failed_traceback_and_success(monkeypatch):
    competition, _, _ = create_synthetic_league()
    events = []
    from football.observability.events import build_event

    monkeypatch.setattr(
        lifecycle, "emit_event", lambda **kwargs: events.append(build_event(**kwargs))
    )
    result = lifecycle.provision_profile(competition, ELO)
    assert result["outcome"] == "UNAVAILABLE"
    assert events[-1]["severity"] == "WARNING"
    complete_coverage(competition)

    def broken(*args):
        raise RuntimeError("calibration exploded")

    monkeypatch.setattr(calibration, "run_model_competition", broken)
    result = lifecycle.provision_profile(competition, ELO)
    assert result["outcome"] == "FAILED"
    assert "RuntimeError: calibration exploded" in events[-1]["stacktrace"]
    assert events[-1]["context"]["model"] == ELO
    assert events[-1]["context"]["evidence_identity"]
    assert events[-1]["competition_id"] == str(competition.pk)
    assert lifecycle.provision_profile(competition, ELO)["outcome"] == "NO_WORK"
    assert events[-1]["outcome"] == "NO_WORK"


@pytest.mark.django_db
def test_runtime_failure_persists_failed_classification(monkeypatch):
    competition, _, history = create_synthetic_league()
    target = future_target(competition, [history[0].home_team, history[0].away_team])
    monkeypatch.setattr(
        EloMultinomialAdapter, "fit", Mock(side_effect=RuntimeError("fit defect"))
    )
    events = []
    monkeypatch.setattr(
        "football.prediction.service.emit_event", lambda **kw: events.append(kw)
    )
    result = predict_competition_day(
        competition,
        calibration.local_day(target.kickoff),
        timezone.now(),
        model_codes=[ELO],
    )
    assert ELO in result.experiment.summary["failed"]
    assert not result.experiment.predictions.exists()
    assert isinstance(events[0]["exception"], RuntimeError)


@pytest.mark.django_db
def test_existing_weekly_owner_skips_readiness_before_interval(monkeypatch):
    from football import maintenance

    call = Mock(return_value={"full_calibrations": 0, "results": []})
    monkeypatch.setattr(lifecycle, "run_readiness_maintenance", call)
    monkeypatch.setattr(maintenance, "_weekly_due", lambda *a, **k: (False, None))
    result = maintenance.run_weekly_evaluation()
    call.assert_not_called()
    assert result["status"] == "NOT_DUE"
    assert "readiness" not in result


@pytest.mark.parametrize(
    "reason",
    [
        "APPROVED_READINESS_PROFILE_PASSED",
        "NO_APPROVED_READINESS_PROFILE",
        "READINESS_MODEL_VERSION_MISMATCH",
        "READINESS_MODEL_CONFIG_MISMATCH",
        "TRAINING_HISTORY_BELOW_PROFILE",
        "HOME_TEAM_HISTORY_BELOW_PROFILE",
        "AWAY_TEAM_HISTORY_BELOW_PROFILE",
        "TRAINING_GRAPH_NOT_CONNECTED",
        "CLASS_SUPPORT_BELOW_PROFILE",
        "READINESS_PROFILE_STALE",
    ],
)
def test_every_current_readiness_reason_has_spanish_mapping(reason):
    assert reason in DECISION_REASONS
    assert decision_reason_presentations(reason)[0]["label"] != "Motivo no clasificado"


def test_unknown_future_reason_has_deliberate_fallback():
    assert (
        decision_reason_presentations("FUTURE_UNKNOWN")[0]["label"]
        == "Motivo no clasificado"
    )


@pytest.mark.django_db
@pytest.mark.parametrize("model", [POISSON, ELO])
def test_daily_renders_readiness_for_both_models(model, client):
    competition, _, history = create_synthetic_league()
    complete_coverage(competition)
    target = future_target(competition, [history[0].home_team, history[0].away_team])
    profile_fixture(competition, model)
    day = calibration.local_day(target.kickoff)
    predict_competition_day(competition, day, timezone.now(), model_codes=[model])
    response = client.get("/daily/", {"date": day.isoformat()})
    assert response.status_code == 200
    content = response.content.decode()
    assert "Perfil de preparación aprobado y satisfecho" in content
    assert "APPROVED_READINESS_PROFILE_PASSED" in content
    assert "bet_eligible=true" in content


@pytest.mark.django_db
def test_budget_defers_full_calibration_without_hiding_due_work(monkeypatch):
    competition, _, _ = create_synthetic_league()
    complete_coverage(competition)
    monkeypatch.setattr(
        calibration, "run_model_competition", Mock(side_effect=AssertionError("budget"))
    )
    result = lifecycle.run_readiness_maintenance(maximum_calibrations=0)
    assert result["full_calibrations"] == 0
    assert {r["outcome"] for r in result["results"]} == {"DEFERRED"}
    assert not ReadinessProfile.objects.exists()


@pytest.mark.django_db
def test_precalibration_competition_failure_does_not_consume_budget(monkeypatch):
    failed_competition, _, _ = create_synthetic_league()
    failed_competition.name = "A Basis Failure League"
    failed_competition.country = "PE"
    failed_competition.save(update_fields=["name", "country", "modified"])
    complete_coverage(failed_competition)

    due_competition, _, _ = create_synthetic_league()
    due_competition.name = "B Due League"
    due_competition.country = "DE"
    due_competition.save(update_fields=["name", "country", "modified"])
    complete_coverage(due_competition)

    original_build = lifecycle.build_sporting_basis

    def build_or_fail(competition):
        if competition.pk == failed_competition.pk:
            raise RuntimeError("basis failure before calibration")
        return original_build(competition)

    calibrate = Mock(wraps=calibration.run_model_competition)
    monkeypatch.setattr(lifecycle, "build_sporting_basis", build_or_fail)
    monkeypatch.setattr(calibration, "run_model_competition", calibrate)

    result = lifecycle.run_readiness_maintenance(maximum_calibrations=2)

    failed_rows = [
        row
        for row in result["results"]
        if row["competition_id"] == failed_competition.pk
    ]
    due_rows = [
        row for row in result["results"] if row["competition_id"] == due_competition.pk
    ]
    assert {row["outcome"] for row in failed_rows} == {"FAILED"}
    assert not any(row["calibrated"] for row in failed_rows)
    assert {row["outcome"] for row in due_rows} == {"CREATED"}
    assert all(row["calibrated"] for row in due_rows)
    assert calibrate.call_count == 2
    assert {call.args[1] for call in calibrate.call_args_list} == {POISSON, ELO}
    assert all(
        call.args[0].pk == due_competition.pk for call in calibrate.call_args_list
    )
    assert result["full_calibrations"] == 2


@pytest.mark.django_db
def test_actual_failed_calibration_consumes_only_its_budget_unit(monkeypatch):
    competition, _, _ = create_synthetic_league()
    complete_coverage(competition)
    calibrate = Mock(side_effect=RuntimeError("calibration failed"))
    monkeypatch.setattr(calibration, "run_model_competition", calibrate)

    result = lifecycle.run_readiness_maintenance(maximum_calibrations=1)

    assert calibrate.call_count == 1
    assert result["full_calibrations"] == 1
    assert [row["outcome"] for row in result["results"]] == ["FAILED", "DEFERRED"]
    assert [row["calibrated"] for row in result["results"]] == [True, False]


@pytest.mark.django_db
def test_postcalibration_persistence_failure_preserves_exact_attempt_count(
    monkeypatch,
):
    competition, _, _ = create_synthetic_league()
    complete_coverage(competition)
    calibrate = Mock(wraps=calibration.run_model_competition)
    monkeypatch.setattr(calibration, "run_model_competition", calibrate)
    monkeypatch.setattr(
        ReadinessProfile,
        "save",
        Mock(side_effect=RuntimeError("profile persistence failed")),
    )

    result = lifecycle.run_readiness_maintenance(maximum_calibrations=2)

    assert calibrate.call_count == 1
    assert result["full_calibrations"] == 1
    assert [row["outcome"] for row in result["results"]] == ["FAILED", "FAILED"]
    assert [row["calibrated"] for row in result["results"]] == [True, False]


@pytest.mark.django_db
def test_failed_execution_retries_automatically_after_cooldown(monkeypatch):
    competition, _, _ = create_synthetic_league()
    complete_coverage(competition)
    original = calibration.run_model_competition
    monkeypatch.setattr(
        calibration,
        "run_model_competition",
        Mock(side_effect=RuntimeError("temporary failure")),
    )
    assert lifecycle.provision_profile(competition, ELO)["outcome"] == "FAILED"
    failed = active_profile(competition, model_code=ELO)
    failed.completed_at = timezone.now() - timedelta(days=8)
    failed.save()
    monkeypatch.setattr(calibration, "run_model_competition", original)
    assert lifecycle.provision_profile(competition, ELO)["outcome"] == "UPDATED"
    current = active_profile(competition, model_code=ELO)
    assert current.approved and current.supersedes == failed


@pytest.mark.django_db
def test_new_completed_season_automatically_revalidates():
    competition, seasons, history = create_synthetic_league()
    coverage = complete_coverage(competition)
    old = profile_fixture(competition, ELO)
    target = future_target(competition, [history[0].home_team, history[0].away_team])
    new = target.season
    new.is_current = False
    new.save()
    target.kickoff = history[-1].kickoff + timedelta(days=400)
    target.status_short = "FT"
    target.home_score = 1
    target.away_score = 0
    target.outcome = "HOME"
    target.save()
    coverage.required_seasons = [2022, 2023, 2024, 2026]
    coverage.covered_seasons = coverage.required_seasons
    coverage.save()
    result = lifecycle.provision_profile(competition, ELO)
    assert result["outcome"] == "UPDATED"
    current = active_profile(competition, model_code=ELO)
    assert current.supersedes == old
    assert current.evidence["calibration"]["outer_season"] == 2026
    assert current.evidence["calibration"]["development_seasons"] == [2022, 2023, 2024]


@pytest.mark.django_db
def test_normal_pipeline_consumes_profiles_without_market_or_provider(monkeypatch):
    from football.capture.contracts import CaptureResult
    from football.pipeline import run_pipeline

    competition, _, history = create_synthetic_league()
    complete_coverage(competition)
    target = future_target(competition, [history[0].home_team, history[0].away_team])
    for model in (POISSON, ELO):
        profile_fixture(competition, model)
    monkeypatch.setattr(
        "football.pipeline.service.run_capture",
        lambda **kw: CaptureResult(
            run_id=None,
            status="NO_WORK",
            planning_at=kw["at"],
            quota_before={},
            quota_after={},
            plan={"items": []},
        ),
    )
    at = timezone.now()
    run_pipeline(at=at)
    predictions = Prediction.objects.filter(match=target, model_code__in=(POISSON, ELO))
    assert predictions.count() == 2
    assert all(p.bet_eligible for p in predictions)
    identities = set(predictions.values_list("evidence_identity", flat=True))
    run_pipeline(at=at + timedelta(minutes=1))
    assert predictions.count() == 2
    assert set(predictions.values_list("evidence_identity", flat=True)) == identities


@pytest.mark.django_db
def test_success_event_identifies_created_config(monkeypatch):
    from football.observability.events import build_event

    competition, _, _ = create_synthetic_league()
    complete_coverage(competition)
    events = []
    monkeypatch.setattr(
        lifecycle, "emit_event", lambda **kw: events.append(build_event(**kw))
    )
    assert lifecycle.provision_profile(competition, ELO)["outcome"] == "CREATED"
    event = events[-1]
    assert event["severity"] == "INFO" and event["outcome"] == "CREATED"
    assert event["context"]["profile_version"]
    assert (
        event["context"]["calibration_strategy_version"] == calibration.STRATEGY_VERSION
    )
    assert "'k':" in event["context"]["selected_config"]


def test_development_only_bands_and_outer_no_retuning():
    rows = [{"status": "PRODUCED", "training_matches": n} for n in (3, 7, 11, 19, 27)]
    assert calibration.quantile_thresholds(rows, "training_matches") == [7, 11, 19]
    assert calibration.requirements_for_gate(
        ELO, {"dimension": "class_support_min", "threshold": 7}
    ) == {"min_class_support": 7}
    gate = {"dimension": "training_matches", "threshold": 19}
    before = copy.deepcopy(gate)
    assert (
        calibration.validate_gate_outer(gate, rows[:3])["status"]
        == "NO_OUTER_PASSING_TARGETS"
    )
    assert gate == before


@pytest.mark.django_db
def test_multitarget_prospective_reuses_one_expensive_sporting_basis(monkeypatch):
    competition, _, history = create_synthetic_league()
    complete_coverage(competition)
    first = future_target(competition, [history[0].home_team, history[0].away_team])
    second = Match.objects.create(
        season=first.season,
        home_team=history[1].home_team,
        away_team=history[1].away_team,
        kickoff=first.kickoff + timedelta(hours=2),
        status_short="NS",
        status_long="Not Started",
    )
    for model in (POISSON, ELO):
        profile_fixture(competition, model)

    from football.prediction import evidence

    basis_build = Mock(wraps=lifecycle.build_sporting_basis)
    sporting_hash = Mock(wraps=calibration.sporting_basis_hash)
    fallback_history_query = Mock(wraps=evidence.eligible_finished_matches)
    monkeypatch.setattr(lifecycle, "build_sporting_basis", basis_build)
    monkeypatch.setattr(calibration, "sporting_basis_hash", sporting_hash)
    monkeypatch.setattr(evidence, "eligible_finished_matches", fallback_history_query)

    result = predict_competition_day(
        competition,
        calibration.local_day(first.kickoff),
        timezone.now(),
        model_codes=[POISSON, ELO],
        match_ids=[first.pk, second.pk],
    )

    assert result.experiment.predictions.count() == 4
    assert basis_build.call_count == 1
    assert sporting_hash.call_count == 1
    assert fallback_history_query.call_count == 0
    identities = set(
        result.experiment.predictions.values_list("model_code", "evidence_identity")
    )
    assert len(identities) == 2
    assert all(
        prediction.bet_eligible for prediction in result.experiment.predictions.all()
    )


@pytest.mark.django_db
def test_maintenance_reuses_one_expensive_sporting_basis_for_both_models(
    monkeypatch,
):
    competition, _, _ = create_synthetic_league()
    complete_coverage(competition)
    for model in (POISSON, ELO):
        profile_fixture(competition, model)

    basis_build = Mock(wraps=lifecycle.build_sporting_basis)
    sporting_hash = Mock(wraps=calibration.sporting_basis_hash)
    monkeypatch.setattr(lifecycle, "build_sporting_basis", basis_build)
    monkeypatch.setattr(calibration, "sporting_basis_hash", sporting_hash)

    result = lifecycle.run_readiness_maintenance()

    assert basis_build.call_count == 1
    assert sporting_hash.call_count == 1
    assert {row["outcome"] for row in result["results"]} == {"NO_WORK"}
    assert result["full_calibrations"] == 0
