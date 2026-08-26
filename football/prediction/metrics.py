from collections import Counter

from sklearn.metrics import accuracy_score, confusion_matrix, log_loss

from .constants import OUTCOMES


def multiclass_brier(actual, probabilities):
    total = 0.0
    for label, vector in zip(actual, probabilities):
        total += sum(
            (value - (1.0 if outcome == label else 0.0)) ** 2
            for outcome, value in zip(OUTCOMES, vector)
        )
    return total / len(actual) if actual else None


def ranked_probability_score(actual, probabilities):
    if not actual:
        return None
    total = 0.0
    for label, vector in zip(actual, probabilities):
        observed = [1.0 if outcome == label else 0.0 for outcome in OUTCOMES]
        total += (
            sum((sum(vector[:index]) - sum(observed[:index])) ** 2 for index in (1, 2))
            / 2
        )
    return total / len(actual)


def calibration_data(actual, probabilities, bins=10):
    result = {}
    for outcome_index, outcome in enumerate(OUTCOMES):
        rows = []
        for bin_index in range(bins):
            lower = bin_index / bins
            upper = (bin_index + 1) / bins
            members = [
                (label, vector[outcome_index])
                for label, vector in zip(actual, probabilities)
                if lower <= vector[outcome_index] < upper
                or (bin_index == bins - 1 and vector[outcome_index] == 1)
            ]
            if members:
                rows.append(
                    {
                        "lower": lower,
                        "upper": upper,
                        "count": len(members),
                        "mean_predicted": sum(item[1] for item in members)
                        / len(members),
                        "empirical_rate": sum(item[0] == outcome for item in members)
                        / len(members),
                    }
                )
        result[outcome] = rows
    return result


def prediction_metrics(actual, probabilities):
    if not actual:
        return {"sample_count": 0}
    predicted = [OUTCOMES[vector.index(max(vector))] for vector in probabilities]
    return {
        "sample_count": len(actual),
        "log_loss": log_loss(
            [OUTCOMES.index(label) for label in actual],
            probabilities,
            labels=[0, 1, 2],
        ),
        "multiclass_brier": multiclass_brier(actual, probabilities),
        "rps": ranked_probability_score(actual, probabilities),
        "accuracy": accuracy_score(actual, predicted),
        "confusion_matrix": confusion_matrix(
            actual, predicted, labels=list(OUTCOMES)
        ).tolist(),
        "confusion_order": list(OUTCOMES),
        "calibration": calibration_data(actual, probabilities),
    }


def losing_streaks(decisions):
    streaks = []
    current = 0
    for decision in decisions:
        if decision["action"] == "NO_BET":
            if current:
                streaks.append(current)
                current = 0
        elif decision["action"] == decision["actual_outcome"]:
            if current:
                streaks.append(current)
                current = 0
        else:
            current += 1
    if current:
        streaks.append(current)
    return streaks


def policy_metrics(decisions):
    evaluated = len(decisions)
    bets = [decision for decision in decisions if decision["action"] != "NO_BET"]
    hits = sum(item["action"] == item["actual_outcome"] for item in bets)
    streaks = losing_streaks(decisions)
    economics = [item for item in bets if item.get("selected_price") is not None]
    pnl = sum(
        (
            float(item["selected_price"]) - 1
            if item["action"] == item["actual_outcome"]
            else -1
        )
        for item in economics
    )
    action_mix = Counter(item["action"] for item in bets)
    no_bet_reasons = Counter(
        item["reason"]
        for item in decisions
        if item["action"] == "NO_BET" and item.get("reason")
    )
    return {
        "evaluated_fixtures": evaluated,
        "decisions": len(bets),
        "coverage": len(bets) / evaluated if evaluated else 0,
        "no_bet_count": evaluated - len(bets),
        "no_bet_rate": (evaluated - len(bets)) / evaluated if evaluated else 0,
        "no_bet_reasons": dict(no_bet_reasons),
        "action_mix": {outcome: action_mix[outcome] for outcome in OUTCOMES},
        "hits": hits,
        "losses": len(bets) - hits,
        "hit_rate": hits / len(bets) if bets else None,
        "longest_losing_streak": max(streaks, default=0),
        "losing_streak_distribution": dict(Counter(streaks)),
        "economic_decisions": len(economics),
        "flat_unit_pnl": pnl if economics else None,
        "roi": pnl / len(economics) if economics else None,
        "mean_selected_odd": (
            sum(float(item["selected_price"]) for item in economics) / len(economics)
            if economics
            else None
        ),
        "mean_predicted_ev": (
            sum(
                item["expected_value"]
                for item in economics
                if item.get("expected_value") is not None
            )
            / sum(item.get("expected_value") is not None for item in economics)
            if any(item.get("expected_value") is not None for item in economics)
            else None
        ),
    }
