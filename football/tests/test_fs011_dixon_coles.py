from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from football.capital.contracts import CapitalInputError
from football.capital.service import select_decision_basis
from football.historical.contracts import HistoricalResult
from football.historical.service import STRATEGY_VERSION, process_historical_bootstrap
from football.models import (
    Bookmaker,
    DixonColesReadinessProfile,
    HistoricalCoverage,
    Match,
    OddsMarket,
    OddsObservation,
    Prediction,
    PredictionExperiment,
    Season,
    Source,
    Team,
)
from football.pipeline.service import _dixon_coles_candidates
from football.prediction import evaluation
from football.prediction.constants import DIXON_COLES_VERSION
from football.prediction.contracts import FailedPrediction, UnavailablePrediction
from football.prediction.goal_models import DixonColesAdapter
from football.prediction.readiness import ReadinessAssessment
from football.prediction.service import predict_competition_day

from .prediction_helpers import create_synthetic_league


def future_target(competition, teams, *, hours=12):
    kickoff = timezone.now() + timedelta(hours=hours)
    season = Season.objects.create(
        competition=competition,
        year=2026,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        is_current=True,
    )
    return Match.objects.create(
        season=season,
        home_team=teams[0],
        away_team=teams[1],
        kickoff=kickoff,
        status_short="NS",
        status_long="Not Started",
    )


def complete_coverage(competition):
    required = list(
        competition.seasons.filter(is_current=False)
        .order_by("year")
        .values_list("year", flat=True)
    )
    return HistoricalCoverage.objects.create(
        competition=competition,
        status=HistoricalCoverage.Status.COMPLETE,
        strategy_version=STRATEGY_VERSION,
        activation_requested=True,
        required_seasons=required,
        covered_seasons=required,
    )


@pytest.mark.django_db
def test_real_dixon_coles_prediction_persists_below_readiness_as_no_bet():
    competition, _, history = create_synthetic_league()
    teams = [history[0].home_team, history[0].away_team]
    target = future_target(competition, teams)
    cutoff = timezone.now()
    outcome = predict_competition_day(
        competition,
        target.kickoff.date(),
        cutoff,
        logical_identity="fs011-real-dc-exploratory",
        match_ids=[target.pk],
        model_codes=[Prediction.DIXON_COLES],
    )
    prediction = outcome.experiment.predictions.get(model_code=Prediction.DIXON_COLES)
    assert prediction.bet_eligible is False
    assert prediction.readiness_reason == "NO_APPROVED_READINESS_PROFILE"
    assert prediction.evidence_identity
    decisions = prediction.decisions.all()
    assert decisions.exists()
    assert set(decisions.values_list("action", flat=True)) == {"NO_BET"}
    assert set(decisions.values_list("reason", flat=True)) == {
        "NO_APPROVED_READINESS_PROFILE"
    }
    assert not decisions.exclude(selected_odds_observation=None).exists()
    assert not decisions.exclude(selected_price=None).exists()
    assert not decisions.exclude(expected_value=None).exists()
    with pytest.raises(CapitalInputError, match="matched no Decisions"):
        select_decision_basis(
            prediction_experiment=outcome.experiment,
            source_model_code=Prediction.DIXON_COLES,
            decision_policy_code="MODAL_ALL",
        )


@pytest.mark.django_db
def test_approved_versioned_profile_can_make_valid_dc_prediction_eligible():
    competition, _, history = create_synthetic_league()
    target = future_target(competition, [history[0].home_team, history[0].away_team])
    profile = DixonColesReadinessProfile.objects.create(
        competition=competition,
        version="local-approved-v1",
        model_version=DIXON_COLES_VERSION,
        model_config=DixonColesAdapter(xi=0.001).config,
        approved=True,
        requirements={
            "require_connected": True,
            "min_home_team_matches": 1,
            "min_away_team_matches": 1,
        },
        rationale="Deterministic test approval.",
    )
    outcome = predict_competition_day(
        competition,
        target.kickoff.date(),
        timezone.now(),
        logical_identity="fs011-real-dc-approved",
        match_ids=[target.pk],
        model_codes=[Prediction.DIXON_COLES],
    )
    prediction = outcome.experiment.predictions.get()
    assert prediction.bet_eligible is True
    assert prediction.readiness_profile == profile
    assert prediction.readiness_profile_version == "local-approved-v1"


@pytest.mark.django_db
def test_multi_target_unseen_team_does_not_suppress_mature_dc_prediction():
    competition, _, history = create_synthetic_league()
    mature = future_target(competition, [history[0].home_team, history[0].away_team])
    unseen = Team.objects.create(competition=competition, name="Promoted Unseen")
    below_readiness = Match.objects.create(
        season=mature.season,
        home_team=unseen,
        away_team=history[0].away_team,
        kickoff=mature.kickoff + timedelta(hours=1),
        status_short="NS",
        status_long="Not Started",
    )
    DixonColesReadinessProfile.objects.create(
        competition=competition,
        version="per-target-v1",
        model_version=DIXON_COLES_VERSION,
        model_config=DixonColesAdapter(xi=0.001).config,
        approved=True,
        requirements={
            "require_connected": True,
            "min_home_team_matches": 1,
            "min_away_team_matches": 1,
        },
    )

    outcome = predict_competition_day(
        competition,
        mature.kickoff.date(),
        timezone.now(),
        logical_identity="fs011-dc-mixed-target-readiness",
        match_ids=[mature.pk, below_readiness.pk],
        model_codes=[Prediction.DIXON_COLES],
    )

    prediction = outcome.experiment.predictions.get(match=mature)
    assert prediction.bet_eligible is True
    assert not outcome.experiment.predictions.filter(match=below_readiness).exists()
    assert (
        outcome.experiment.summary["unavailable"][f"DIXON_COLES:{below_readiness.pk}"]
        == "INSUFFICIENT_TEAM_HISTORY"
    )
    assert outcome.experiment.summary["dixon_coles"]["targets"] == {
        str(mature.pk): {"status": "PRODUCED", "reasons": []},
        str(below_readiness.pk): {
            "status": "UNAVAILABLE",
            "reasons": ["INSUFFICIENT_TEAM_HISTORY"],
        },
    }


@pytest.mark.django_db
def test_target_readiness_independently_classifies_invalid_dc_output(monkeypatch):
    competition, _, history = create_synthetic_league()
    mature = future_target(competition, [history[0].home_team, history[0].away_team])
    unseen = Team.objects.create(competition=competition, name="Unseen Runtime Team")
    below_readiness = Match.objects.create(
        season=mature.season,
        home_team=unseen,
        away_team=history[0].away_team,
        kickoff=mature.kickoff + timedelta(hours=1),
        status_short="NS",
        status_long="Not Started",
    )
    DixonColesReadinessProfile.objects.create(
        competition=competition,
        version="per-target-runtime-v1",
        model_version=DIXON_COLES_VERSION,
        model_config=DixonColesAdapter(xi=0.001).config,
        approved=True,
        requirements={
            "require_connected": True,
            "min_home_team_matches": 1,
            "min_away_team_matches": 1,
        },
    )

    class InvalidModel:
        class Result:
            home_draw_away = (float("nan"), 0.5, 0.5)

        def __init__(self, *args, **kwargs):
            del args, kwargs

        def fit(self):
            return None

        def predict(self, *args):
            del args
            return self.Result()

    monkeypatch.setattr(DixonColesAdapter, "model_class", InvalidModel)
    outcome = predict_competition_day(
        competition,
        mature.kickoff.date(),
        timezone.now(),
        logical_identity="fs011-dc-mixed-target-runtime",
        match_ids=[mature.pk, below_readiness.pk],
        model_codes=[Prediction.DIXON_COLES],
    )
    targets = outcome.experiment.summary["dixon_coles"]["targets"]
    assert targets[str(mature.pk)] == {
        "status": "FAILED",
        "reasons": ["INVALID_DIXON_COLES_PROBABILITY_OUTPUT"],
    }
    assert targets[str(below_readiness.pk)] == {
        "status": "UNAVAILABLE",
        "reasons": ["INSUFFICIENT_TEAM_HISTORY"],
    }
    assert outcome.experiment.summary["dixon_coles"]["status"] == "FAILED"


@pytest.mark.django_db
def test_approved_profile_for_different_config_stays_ineligible_and_no_bet():
    competition, _, history = create_synthetic_league()
    target = future_target(competition, [history[0].home_team, history[0].away_team])
    DixonColesReadinessProfile.objects.create(
        competition=competition,
        version="wrong-config-v1",
        model_version=DIXON_COLES_VERSION,
        model_config=DixonColesAdapter(xi=0.002).config,
        approved=True,
        requirements={"require_connected": True},
    )
    outcome = predict_competition_day(
        competition,
        target.kickoff.date(),
        timezone.now(),
        logical_identity="fs011-dc-config-mismatch",
        match_ids=[target.pk],
        model_codes=[Prediction.DIXON_COLES],
    )
    prediction = outcome.experiment.predictions.get()
    assert prediction.bet_eligible is False
    assert prediction.readiness_reason == "READINESS_MODEL_CONFIG_MISMATCH"
    assert set(prediction.decisions.values_list("action", flat=True)) == {"NO_BET"}
    assert not prediction.decisions.exclude(selected_odds_observation=None).exists()
    assert not prediction.decisions.exclude(selected_price=None).exists()


@pytest.mark.django_db
def test_price_change_does_not_change_dc_basis_but_new_ft_evidence_does():
    competition, seasons, history = create_synthetic_league()
    target = future_target(competition, [history[0].home_team, history[0].away_team])
    complete_coverage(competition)
    before = _dixon_coles_candidates(timezone.now())[0]
    first = predict_competition_day(
        competition,
        before["day"],
        before["cutoff"],
        logical_identity=before["logical_identity"],
        intended_window=before["intended_window"],
        match_ids=before["match_ids"],
        model_codes=before["model_codes"],
        evidence_identity=before["evidence_identity"],
    )
    assert first.created is True

    source = Source.objects.create(
        code="price-only", name="Price only", base_url="https://example.test/"
    )
    bookmaker = Bookmaker.objects.create(source=source, external_id="1", name="Book")
    market = OddsMarket.objects.create(source=source, external_id="1", name="Winner")
    OddsObservation.objects.create(
        match=target,
        source=source,
        bookmaker=bookmaker,
        market=market,
        home=Decimal("2.0"),
        draw=Decimal("3.0"),
        away=Decimal("4.0"),
        observed_at=timezone.now(),
    )
    after_price = _dixon_coles_candidates(timezone.now())[0]
    assert after_price["evidence_identity"] == before["evidence_identity"]
    repeated = predict_competition_day(
        competition,
        after_price["day"],
        after_price["cutoff"],
        logical_identity=after_price["logical_identity"],
        intended_window=after_price["intended_window"],
        match_ids=after_price["match_ids"],
        model_codes=after_price["model_codes"],
        evidence_identity=after_price["evidence_identity"],
    )
    assert repeated.created is False
    assert repeated.reason == "ALREADY_EXISTS"

    last = max(history, key=lambda match: match.kickoff)
    Match.objects.create(
        season=seasons[-1],
        home_team=last.away_team,
        away_team=last.home_team,
        kickoff=last.kickoff + timedelta(days=1),
        status_short="FT",
        status_long="Match Finished",
        home_score=1,
        away_score=1,
        outcome=Match.OUTCOME_DRAW,
    )
    after_football = _dixon_coles_candidates(timezone.now())[0]
    assert after_football["evidence_identity"] != before["evidence_identity"]
    second = predict_competition_day(
        competition,
        after_football["day"],
        after_football["cutoff"],
        logical_identity=after_football["logical_identity"],
        intended_window=after_football["intended_window"],
        match_ids=after_football["match_ids"],
        model_codes=after_football["model_codes"],
        evidence_identity=after_football["evidence_identity"],
    )
    assert second.created is True
    assert (
        Prediction.objects.filter(
            match=target, model_code=Prediction.DIXON_COLES
        ).count()
        == 2
    )


@pytest.mark.django_db
def test_relevant_model_config_change_changes_dc_evidence_identity():
    competition, _, history = create_synthetic_league()
    future_target(competition, [history[0].home_team, history[0].away_team])
    complete_coverage(competition)
    before = _dixon_coles_candidates(timezone.now())[0]
    PredictionExperiment.objects.create(
        competition=competition,
        mode=PredictionExperiment.MODE_BACKTEST,
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
        completed_at=timezone.now(),
        config={
            "selected_hyperparameters": {
                "dixon_coles": {"xi": 0.002},
                "independent_poisson": {"xi": 0.001},
                "elo_multinomial_logit": {"k": 20, "C": 1.0},
            }
        },
    )
    after = _dixon_coles_candidates(timezone.now())[0]
    assert after["evidence_identity"] != before["evidence_identity"]


@pytest.mark.django_db
def test_frozen_historical_bootstrap_creates_new_preserved_dc_version():
    competition, seasons, history = create_synthetic_league()
    target = future_target(competition, [history[0].home_team, history[0].away_team])
    coverage = complete_coverage(competition)
    before = _dixon_coles_candidates(timezone.now())[0]
    first = predict_competition_day(
        competition,
        before["day"],
        before["cutoff"],
        logical_identity=before["logical_identity"],
        intended_window=before["intended_window"],
        match_ids=before["match_ids"],
        model_codes=before["model_codes"],
        evidence_identity=before["evidence_identity"],
    )
    assert first.created is True

    def frozen_result(match, external_id):
        return HistoricalResult(
            source_code="football_data",
            competition_external_id="SYNTHETIC_TEST_LEAGUE",
            season_year=match.season.year,
            external_id=external_id,
            home_external_id=f"SYNTHETIC:{match.home_team.name}",
            home_name=match.home_team.name,
            away_external_id=f"SYNTHETIC:{match.away_team.name}",
            away_name=match.away_team.name,
            kickoff=match.kickoff,
            kickoff_precision="EXACT",
            home_score=match.home_score,
            away_score=match.away_score,
            provenance={"authority": "football-data.co.uk", "fixture": "frozen"},
        )

    records = {
        season.year: [
            frozen_result(match, f"existing:{match.pk}")
            for match in history
            if match.season_id == season.pk
        ]
        for season in seasons
    }
    last = max(history, key=lambda match: match.kickoff)
    inserted = Match(
        season=seasons[-1],
        home_team=last.away_team,
        away_team=last.home_team,
        kickoff=last.kickoff + timedelta(days=1),
        status_short="FT",
        status_long="Match Finished",
        home_score=1,
        away_score=1,
        outcome=Match.OUTCOME_DRAW,
    )
    records[seasons[-1].year].append(frozen_result(inserted, "new:frozen-result"))

    class FrozenHistoricalAdapter:
        external_competition = "SYNTHETIC_TEST_LEAGUE"

        def __init__(self):
            self.download_count = 0

        def records_for_season(self, season):
            self.download_count += 1
            return records[season.year]

    coverage.status = HistoricalCoverage.Status.NOT_ATTEMPTED
    coverage.save(update_fields=["status", "modified"])
    completed = process_historical_bootstrap(
        competition, adapter=FrozenHistoricalAdapter()
    )
    assert completed.status == HistoricalCoverage.Status.COMPLETE
    assert completed.rows_created == 1
    assert Match.objects.filter(
        season=seasons[-1], kickoff=inserted.kickoff, outcome=Match.OUTCOME_DRAW
    ).exists()

    after = _dixon_coles_candidates(timezone.now())[0]
    assert after["evidence_identity"] != before["evidence_identity"]
    second = predict_competition_day(
        competition,
        after["day"],
        after["cutoff"],
        logical_identity=after["logical_identity"],
        intended_window=after["intended_window"],
        match_ids=after["match_ids"],
        model_codes=after["model_codes"],
        evidence_identity=after["evidence_identity"],
    )
    assert second.created is True
    assert (
        Prediction.objects.filter(
            match=target, model_code=Prediction.DIXON_COLES
        ).count()
        == 2
    )


@pytest.mark.django_db
def test_disconnected_history_is_unavailable_before_real_library_fit():
    competition, seasons, history = create_synthetic_league()
    disconnected = [history[0]]
    other = history[-1]
    disconnected.append(other)
    adapter = DixonColesAdapter(xi=0.001)
    outcome = adapter.fit(disconnected, timezone.now())
    assert isinstance(outcome, UnavailablePrediction)
    assert outcome.reason == "DISCONNECTED_TRAINING_GRAPH"


@pytest.mark.django_db
def test_post_readiness_runtime_and_invalid_probability_are_failed():
    competition, _, history = create_synthetic_league()
    adapter = DixonColesAdapter(xi=0.001)
    fitted = adapter.fit(
        history,
        timezone.now(),
        readiness_assessor=lambda diagnostics: ReadinessAssessment(
            True, "TEST_READINESS_PASSED"
        ),
    )
    assert fitted is adapter

    class RuntimeFailure:
        def predict(self, *args):
            del args
            raise RuntimeError("controlled runtime failure")

    adapter.model = RuntimeFailure()
    failed = adapter.predict(history[0], timezone.now())
    assert isinstance(failed, FailedPrediction)
    assert failed.reason == "DIXON_COLES_PREDICTION_FAILED"

    class InvalidOutput:
        class Result:
            home_draw_away = (float("nan"), 0.5, 0.5)

        def predict(self, *args):
            del args
            return self.Result()

    adapter.model = InvalidOutput()
    invalid = adapter.predict(history[0], timezone.now())
    assert isinstance(invalid, FailedPrediction)
    assert invalid.reason == "INVALID_DIXON_COLES_PROBABILITY_OUTPUT"


@pytest.mark.django_db
def test_invalid_output_below_current_readiness_is_unavailable():
    _, _, history = create_synthetic_league()
    adapter = DixonColesAdapter(xi=0.001)
    fitted = adapter.fit(
        history,
        timezone.now(),
        readiness_assessor=lambda diagnostics: ReadinessAssessment(
            False, "TRAINING_HISTORY_BELOW_PROFILE"
        ),
    )
    assert fitted is adapter

    class InvalidOutput:
        class Result:
            home_draw_away = (float("nan"), 0.5, 0.5)

        def predict(self, *args):
            del args
            return self.Result()

    adapter.model = InvalidOutput()
    unavailable = adapter.predict(history[0], timezone.now())
    assert isinstance(unavailable, UnavailablePrediction)
    assert unavailable.reason == "STRUCTURALLY_UNSTABLE_EXPLORATORY_EVIDENCE"


@pytest.mark.django_db
def test_backtest_preserves_failed_counts_separately(monkeypatch):
    competition, seasons, _ = create_synthetic_league()

    class FailedAdapter:
        model_code = Prediction.DIXON_COLES

        def __init__(self, **kwargs):
            del kwargs

        def fit(self, history, cutoff):
            del history, cutoff
            return FailedPrediction("CONTROLLED_BACKTEST_FAILURE")

    monkeypatch.setattr(evaluation, "DixonColesAdapter", FailedAdapter)
    monkeypatch.setattr(
        evaluation,
        "select_hyperparameters",
        lambda *_: {
            "dixon_coles": {"xi": 0.001},
            "independent_poisson": {"xi": 0.001},
            "elo_multinomial_logit": {"k": 20, "C": 1.0},
        },
    )
    monkeypatch.setattr(evaluation, "select_modernized_config", lambda *_: None)
    experiment = evaluation.run_backtest(competition, seasons[-1])

    assert experiment.summary["failed_counts"][
        "DIXON_COLES:CONTROLLED_BACKTEST_FAILURE"
    ]
    assert not any(
        key.startswith("DIXON_COLES:CONTROLLED_BACKTEST_FAILURE")
        for key in experiment.summary["unavailable_counts"]
    )
