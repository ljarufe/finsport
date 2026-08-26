import math
from datetime import timedelta

import pytest

from football.prediction.constants import OUTCOMES
from football.prediction.contracts import (
    ProbabilityContractError,
    ProbabilityResult,
)
from football.prediction.datasets import (
    daily_batches,
    eligible_finished_matches,
    history_before_local_day,
    local_day,
    upcoming_matches_for_day,
)
from football.prediction.elo import EloMultinomialAdapter, sequential_elo_features
from football.prediction.goal_models import (
    DixonColesAdapter,
    IndependentPoissonAdapter,
)

from .prediction_helpers import create_synthetic_league

pytestmark = pytest.mark.django_db


def test_synthetic_dataset_is_three_double_round_robin_seasons_with_promotion():
    competition, seasons, matches = create_synthetic_league()

    assert len(seasons) == 3
    assert len(matches) == 168
    assert [season.matches.count() for season in seasons] == [56, 56, 56]
    assert competition.teams.count() == 10
    assert (
        len(
            set(seasons[2].matches.values_list("home_team_id", flat=True))
            | set(seasons[2].matches.values_list("away_team_id", flat=True))
        )
        == 8
    )
    assert {match.outcome for match in matches} == set(OUTCOMES)
    assert any(match.home_score == match.away_score == 0 for match in matches)
    assert any(match.home_score == match.away_score == 1 for match in matches)


def test_probability_contract_and_tie_break():
    result = ProbabilityResult(0.4, 0.4, 0.2)
    assert result.predicted_outcome == "HOME"
    assert all(math.isfinite(value) for value in result.as_tuple())
    with pytest.raises(ProbabilityContractError):
        ProbabilityResult(float("nan"), 0.5, 0.5)
    with pytest.raises(ProbabilityContractError):
        ProbabilityResult(0.2, 0.2, 0.2)


@pytest.mark.parametrize(
    "adapter_class",
    [DixonColesAdapter, IndependentPoissonAdapter],
)
def test_penaltyblog_goal_model_adapters_fit_predict_and_reject_unseen_team(
    adapter_class,
):
    _, seasons, matches = create_synthetic_league()
    training = list(seasons[0].matches.order_by("kickoff", "id"))
    known_target = seasons[1].matches.order_by("kickoff", "id").first()
    unseen_target = seasons[2].matches.filter(home_team__name__startswith="New").first()
    adapter = adapter_class(xi=0.001)
    adapter.fit(training, known_target.kickoff)

    result = adapter.predict(known_target, known_target.kickoff)
    assert isinstance(result, ProbabilityResult)
    assert result.predicted_outcome in OUTCOMES
    assert abs(sum(result.as_tuple()) - 1) < 1e-9
    unavailable = adapter.predict(unseen_target, unseen_target.kickoff)
    assert unavailable.reason == "INSUFFICIENT_TEAM_HISTORY"
    assert adapter.model.__class__.__name__ in {
        "DixonColesGoalModel",
        "PoissonGoalsModel",
    }


def test_elo_features_are_frozen_before_same_day_updates_and_column_mapping_is_explicit():
    _, seasons, _ = create_synthetic_league()
    history = list(seasons[0].matches.order_by("kickoff", "id"))
    features, labels, _ = sequential_elo_features(history, k=20)
    first_batch = daily_batches(history)[0][1]

    assert len(features) == len(labels) == 56
    assert features[: len(first_batch)] == [[0.0, 0.0]] * len(first_batch)

    target = seasons[1].matches.order_by("kickoff", "id").first()
    adapter = EloMultinomialAdapter(k=20, c=1.0)
    adapter.fit(history, target.kickoff)
    result = adapter.predict(target, target.kickoff)
    classes = list(adapter.classifier.named_steps["classifier"].classes_)

    assert isinstance(result, ProbabilityResult)
    assert result.diagnostics["classes"] == classes
    assert set(classes) == set(OUTCOMES)


def test_training_dataset_excludes_target_future_non_ft_and_non_regulation_statuses():
    competition, seasons, _ = create_synthetic_league()
    targets = list(seasons[1].matches.order_by("kickoff", "id")[:4])
    target_day = local_day(targets[0].kickoff)
    history = list(eligible_finished_matches(competition, before=targets[0].kickoff))

    assert all(match.kickoff < targets[0].kickoff for match in history)
    assert not {match.id for match in targets} & {match.id for match in history}
    assert not history_before_local_day(targets, target_day)
    assert not upcoming_matches_for_day(
        competition, target_day, targets[0].kickoff - timedelta(days=1)
    ).exists()

    excluded_statuses = ("AET", "PEN", "AWD", "WO", "NS")
    for match, status in zip(
        seasons[2].matches.order_by("kickoff", "id")[:5], excluded_statuses
    ):
        match.status_short = status
        match.save(update_fields=["status_short"])
    assert (
        not eligible_finished_matches(competition)
        .filter(status_short__in=excluded_statuses)
        .exists()
    )
