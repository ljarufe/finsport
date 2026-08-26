from datetime import timedelta
from decimal import Decimal

import pytest

from football.models import OddsObservation, OddsSnapshot
from football.prediction.contracts import ProbabilityResult, UnavailablePrediction
from football.prediction.market import (
    MarketConsensusAdapter,
    best_prices_as_of,
    latest_observations_as_of,
)
from football.prediction.policies import modal_all, selective_confidence, value_policy

from .prediction_helpers import create_synthetic_league, create_synthetic_odds

pytestmark = pytest.mark.django_db


def test_synthetic_odds_have_four_books_three_times_and_asof_is_strict():
    _, _, matches = create_synthetic_league()
    target = matches[-1]
    source, market, bookmakers, observations = create_synthetic_odds([target])
    late = OddsObservation.objects.create(
        match=target,
        source=source,
        bookmaker=bookmakers[0],
        market=market,
        home=Decimal("9"),
        draw=Decimal("9"),
        away=Decimal("9"),
        observed_at=target.kickoff + timedelta(minutes=1),
    )

    assert len(observations) == 12
    assert len(latest_observations_as_of(target, target.kickoff)) == 4
    assert late not in latest_observations_as_of(target, target.kickoff)
    assert sum(item.provider_updated_at is None for item in observations) == 3
    book_four = [item for item in observations if item.bookmaker == bookmakers[3]]
    assert len({(item.home, item.draw, item.away) for item in book_four}) == 1
    assert len({item.observed_at for item in book_four}) == 3


def test_market_consensus_and_best_prices_keep_fair_probability_separate():
    _, _, matches = create_synthetic_league()
    target = matches[-1]
    _, _, _, _ = create_synthetic_odds([target])
    result = MarketConsensusAdapter().predict(target, target.kickoff)
    prices = best_prices_as_of(target, target.kickoff)
    modal_with_market = modal_all(ProbabilityResult(0.30, 0.40, 0.30), prices)
    assert modal_with_market.selected_price == prices["DRAW"][1]

    assert isinstance(result, ProbabilityResult)
    assert result.diagnostics["book_count"] == 4
    assert result.diagnostics["de_vig_method"] == "multiplicative"
    assert abs(sum(result.as_tuple()) - 1) < 1e-9
    assert set(prices) == {"HOME", "DRAW", "AWAY"}
    assert all(observation.match_id == target.id for observation, _ in prices.values())
    assert [
        prices[outcome][0].bookmaker.name for outcome in ("HOME", "DRAW", "AWAY")
    ] == ["Book 4", "Book 3", "Book 1"]
    latest = latest_observations_as_of(target, target.kickoff)
    manual_vectors = []
    for observation in latest:
        inverse = [
            1 / float(value)
            for value in (observation.home, observation.draw, observation.away)
        ]
        total = sum(inverse)
        manual_vectors.append([value / total for value in inverse])
    manual_mean = [
        sum(vector[index] for vector in manual_vectors) / 4 for index in range(3)
    ]
    assert result.as_tuple() == pytest.approx(manual_mean)


def test_market_missing_or_invalid_is_explicit():
    _, _, matches = create_synthetic_league()
    target = matches[0]
    source, market, bookmakers, _ = create_synthetic_odds([matches[1]])
    OddsSnapshot.objects.create(
        match=target,
        source=source,
        bookmaker=bookmakers[0],
        market=market,
        home=2,
        draw=3,
        away=4,
        observed_at=target.kickoff - timedelta(hours=1),
    )
    assert isinstance(
        MarketConsensusAdapter().predict(target, target.kickoff),
        UnavailablePrediction,
    )


def test_modal_confidence_and_value_allow_draw_and_no_bet():
    draw_modal = ProbabilityResult(0.30, 0.40, 0.30)
    assert modal_all(draw_modal).action == "DRAW"
    assert selective_confidence(draw_modal, 0.45).reason == "BELOW_CONFIDENCE_THRESHOLD"

    _, _, matches = create_synthetic_league()
    target = matches[-1]
    create_synthetic_odds([target])
    prices = best_prices_as_of(target, target.kickoff)
    value = value_policy(ProbabilityResult(0.45, 0.40, 0.15), prices, 0)
    assert value.action == "DRAW"
    assert value.action != "HOME"
    no_bet = value_policy(ProbabilityResult(0.34, 0.33, 0.33), {}, 0)
    assert no_bet.reason == "NO_VALID_MARKET"
    weak = value_policy(
        ProbabilityResult(0.34, 0.33, 0.33),
        {outcome: (object(), Decimal("2")) for outcome in ("HOME", "DRAW", "AWAY")},
        0,
    )
    assert weak.reason == "NO_POSITIVE_VALUE_ABOVE_THRESHOLD"


@pytest.mark.parametrize("outcome", ["HOME", "DRAW", "AWAY"])
def test_value_policy_can_select_every_outcome(outcome):
    probabilities = {
        "HOME": ProbabilityResult(0.60, 0.20, 0.20),
        "DRAW": ProbabilityResult(0.20, 0.60, 0.20),
        "AWAY": ProbabilityResult(0.20, 0.20, 0.60),
    }[outcome]
    prices = {
        candidate: (object(), Decimal("2")) for candidate in ("HOME", "DRAW", "AWAY")
    }
    assert value_policy(probabilities, prices, 0).action == outcome
