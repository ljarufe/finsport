from dataclasses import dataclass, field

from .constants import (
    MODAL_ALL_VERSION,
    OUTCOMES,
    SELECTIVE_CONFIDENCE_VERSION,
    VALUE_VERSION,
)


@dataclass(frozen=True)
class PolicyResult:
    action: str
    reason: str
    model_probability: float | None = None
    selected_observation: object | None = None
    selected_price: object | None = None
    expected_value: float | None = None
    config: dict = field(default_factory=dict)


def _market_fields(probability, outcome, best_prices):
    if not best_prices or outcome not in best_prices:
        return {}
    observation, price = best_prices[outcome]
    return {
        "selected_observation": observation,
        "selected_price": price,
        "expected_value": probability.probability_for(outcome) * float(price) - 1,
    }


def modal_all(probability, best_prices=None):
    outcome = probability.predicted_outcome
    return PolicyResult(
        action=outcome,
        reason="MODAL_OUTCOME",
        model_probability=probability.probability_for(outcome),
        **_market_fields(probability, outcome, best_prices),
    )


def selective_confidence(probability, threshold, best_prices=None):
    outcome = probability.predicted_outcome
    confidence = probability.probability_for(outcome)
    if confidence < threshold:
        return PolicyResult(
            action="NO_BET",
            reason="BELOW_CONFIDENCE_THRESHOLD",
            model_probability=confidence,
            config={"threshold": threshold},
        )
    return PolicyResult(
        action=outcome,
        reason="CONFIDENCE_THRESHOLD_MET",
        model_probability=confidence,
        config={"threshold": threshold},
        **_market_fields(probability, outcome, best_prices),
    )


def value_policy(probability, best_prices, minimum_ev):
    if any(outcome not in best_prices for outcome in OUTCOMES):
        return PolicyResult(
            action="NO_BET",
            reason="NO_VALID_MARKET",
            config={"minimum_ev": minimum_ev},
        )
    expected_values = {
        outcome: probability.probability_for(outcome) * float(best_prices[outcome][1])
        - 1
        for outcome in OUTCOMES
    }
    # max preserves OUTCOMES insertion order for deterministic ties.
    outcome = max(OUTCOMES, key=lambda candidate: expected_values[candidate])
    expected_value = expected_values[outcome]
    if expected_value <= minimum_ev:
        return PolicyResult(
            action="NO_BET",
            reason="NO_POSITIVE_VALUE_ABOVE_THRESHOLD",
            expected_value=expected_value,
            config={"minimum_ev": minimum_ev},
        )
    observation, price = best_prices[outcome]
    return PolicyResult(
        action=outcome,
        reason="VALUE_ABOVE_THRESHOLD",
        model_probability=probability.probability_for(outcome),
        selected_observation=observation,
        selected_price=price,
        expected_value=expected_value,
        config={"minimum_ev": minimum_ev},
    )


POLICY_VERSIONS = {
    "MODAL_ALL": MODAL_ALL_VERSION,
    "SELECTIVE_CONFIDENCE": SELECTIVE_CONFIDENCE_VERSION,
    "VALUE": VALUE_VERSION,
}
