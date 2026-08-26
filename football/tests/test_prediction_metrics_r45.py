from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from football.prediction.constants import LEGACY_R45_VERSION
from football.prediction.contracts import ProbabilityResult
from football.prediction.metrics import (
    calibration_data,
    multiclass_brier,
    policy_metrics,
    prediction_metrics,
)
from football.prediction.r45 import (
    LegacyCandidate,
    ModernizedR45Adapter,
    build_modernized_feature_rows,
    legacy_reject_reason,
    legacy_score,
    modernized_features,
    select_legacy_r45,
    select_modernized_config,
    shrunk_draw_rate,
)

from .prediction_helpers import create_synthetic_league, create_synthetic_odds


def test_prediction_metrics_known_values_and_calibration_shape():
    actual = ["HOME", "DRAW", "AWAY"]
    probabilities = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    metrics = prediction_metrics(actual, probabilities)

    assert metrics["sample_count"] == 3
    assert metrics["accuracy"] == 1
    assert metrics["multiclass_brier"] == 0
    assert metrics["confusion_matrix"] == [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    assert multiclass_brier(["HOME"], [[0.5, 0.25, 0.25]]) == pytest.approx(0.375)
    assert calibration_data(actual, probabilities)["DRAW"][-1]["count"] == 1


def test_policy_metrics_streaks_and_flat_unit_economics():
    rows = [
        {
            "action": "DRAW",
            "actual_outcome": "HOME",
            "selected_price": 3.0,
            "expected_value": 0.1,
        },
        {
            "action": "AWAY",
            "actual_outcome": "HOME",
            "selected_price": None,
            "expected_value": None,
        },
        {
            "action": "NO_BET",
            "actual_outcome": "DRAW",
            "selected_price": None,
            "expected_value": None,
        },
        {
            "action": "DRAW",
            "actual_outcome": "DRAW",
            "selected_price": 3.0,
            "expected_value": 0.2,
        },
    ]
    metrics = policy_metrics(rows)

    assert metrics["longest_losing_streak"] == 2
    assert metrics["losing_streak_distribution"] == {2: 1}
    assert metrics["flat_unit_pnl"] == 1
    assert metrics["roi"] == 0.5


def test_policy_metrics_reports_only_no_bet_reason_distribution():
    metrics = policy_metrics(
        [
            {
                "action": "NO_BET",
                "reason": "BELOW_CONFIDENCE_THRESHOLD",
                "actual_outcome": "HOME",
            },
            {
                "action": "NO_BET",
                "reason": "NO_VALID_MARKET",
                "actual_outcome": "DRAW",
            },
            {
                "action": "NO_BET",
                "reason": "NO_VALID_MARKET",
                "actual_outcome": "AWAY",
            },
            {
                "action": "HOME",
                "reason": "MODAL_OUTCOME",
                "actual_outcome": "HOME",
            },
        ]
    )

    assert metrics["no_bet_reasons"] == {
        "BELOW_CONFIDENCE_THRESHOLD": 1,
        "NO_VALID_MARKET": 2,
    }


def candidate(now, **changes):
    values = {
        "identity": "candidate",
        "kickoff": now + timedelta(minutes=20),
        "home_odd": 1.5,
        "draw_odd": 2.8,
        "away_odd": 4.5,
        "league_draw_percentage": 25,
    }
    values.update(changes)
    return LegacyCandidate(**values)


def test_legacy_r45_exact_boundaries_score_top_one_and_draw_semantics():
    now = timezone.make_aware(datetime(2026, 1, 1, 12))
    accepted = candidate(now)
    assert legacy_reject_reason(accepted, now=now) == ""
    assert legacy_reject_reason(candidate(now, away_odd=4.51), now=now)
    assert legacy_reject_reason(candidate(now, home_odd=1.49), now=now)
    assert legacy_reject_reason(candidate(now, away_odd=1.49), now=now)
    assert legacy_reject_reason(candidate(now, draw_odd=4.2), now=now) == ""
    assert legacy_reject_reason(candidate(now, draw_odd=4.21), now=now)
    assert legacy_reject_reason(candidate(now, league_draw_percentage=24.99), now=now)
    assert (
        legacy_reject_reason(
            candidate(now, kickoff=now + timedelta(minutes=5)), now=now
        )
        == ""
    )
    assert (
        legacy_reject_reason(
            candidate(now, kickoff=now + timedelta(minutes=35)), now=now
        )
        == ""
    )
    assert legacy_reject_reason(
        candidate(now, kickoff=now + timedelta(minutes=36)), now=now
    )
    assert legacy_score(accepted, max_league_draw_percentage=35) == pytest.approx(-0.4)

    better = candidate(now, identity="better", home_odd=2, away_odd=2, draw_odd=4)
    selected = select_legacy_r45(
        [accepted, better], now=now, max_league_draw_percentage=35
    )
    assert selected.identity == "better"
    assert not hasattr(selected, "p_draw")
    assert LEGACY_R45_VERSION == (
        "R45-refund-stop@ef861a4897e4bfdff938e8541e8185f731ddaa5c"
    )


@pytest.mark.parametrize("variant,length", [("M0", 1), ("M1", 2), ("M2", 2), ("M3", 3)])
def test_modernized_r45_variants_preserve_home_away_ratio(variant, length):
    market = ProbabilityResult(0.45, 0.30, 0.25)
    draw_rate = shrunk_draw_rate(5, 20, 0.25, 20)
    assert len(modernized_features(market, draw_rate, variant)) == length
    adapter = ModernizedR45Adapter(variant=variant, c=1.0, prior_strength=20)
    assert adapter.predict_from_market(market, draw_rate).reason == "MODEL_NOT_FITTED"
    training = []
    labels = []
    for index in range(12):
        sample = ProbabilityResult(0.40, 0.20 + index * 0.02, 0.40 - index * 0.02)
        training.append(modernized_features(sample, 0.2 + index * 0.01, variant))
        labels.append(index % 3 == 0)
    adapter.fit_features(training, labels)
    result = adapter.predict_from_market(market, draw_rate)

    assert abs(sum(result.as_tuple()) - 1) < 1e-9
    assert result.p_home / result.p_away == pytest.approx(market.p_home / market.p_away)


@pytest.mark.django_db
def test_modernized_feature_rows_freeze_daily_draw_rate_and_select_config():
    _, seasons, _ = create_synthetic_league()
    season_one = list(seasons[0].matches.order_by("kickoff", "id"))
    season_two = list(seasons[1].matches.order_by("kickoff", "id"))
    season_three = list(seasons[2].matches.order_by("kickoff", "id"))
    create_synthetic_odds([*season_two, *season_three])

    rows, unavailable = build_modernized_feature_rows(
        [*season_one, *season_two[:8]], variant="M3", prior_strength=20
    )
    prior_mean = sum(match.outcome == "DRAW" for match in season_one) / 56
    first_day = rows[:4]
    second_day = rows[4:8]

    assert unavailable["NO_PRIOR_SEASON_DRAW_RATE"] == 56
    assert all(row.draw_rate == pytest.approx(prior_mean) for row in first_day)
    expected_second = shrunk_draw_rate(
        sum(match.outcome == "DRAW" for match in season_two[:4]),
        4,
        prior_mean,
        20,
    )
    assert all(row.draw_rate == pytest.approx(expected_second) for row in second_day)

    selected = select_modernized_config(
        [*season_one, *season_two],
        season_three,
        configs=[{"variant": "M3", "c": 1.0, "prior_strength": 20}],
    )
    assert selected is not None
    assert selected[1] == {"variant": "M3", "c": 1.0, "prior_strength": 20}
