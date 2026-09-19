"""Historical evidence reconstruction; never creates prospective observations."""

import math
from datetime import timedelta

from football.prediction.contracts import ProbabilityResult
from football.prediction.market import equal_weight_consensus, multiplicative_fair

from .spec import BOOKMAKERS, MODELS, PROFILE
from .storage import identity, instant


def reconstruct(payload, *, fixture_id, match_id, kickoff):
    if payload.get("fixtureId") != fixture_id or not isinstance(
        payload.get("bookmakers"), dict
    ):
        raise ValueError("HISTORICAL_SHAPE_MISMATCH")
    cutoff = kickoff - timedelta(minutes=30)
    books, excluded = {}, {}
    for book in BOOKMAKERS:
        outcomes = (
            payload["bookmakers"]
            .get(book, {})
            .get("markets", {})
            .get("101", {})
            .get("outcomes", {})
        )
        legs = []
        for outcome in ("101", "102", "103"):
            series = outcomes.get(outcome, {}).get("players", {}).get("0", [])
            if not isinstance(series, list):
                raise ValueError("HISTORICAL_SERIES_SHAPE_MISMATCH")
            valid = []
            for state in series:
                try:
                    timestamp = instant(state["createdAt"])
                    price = float(state["price"])
                    if (
                        state["active"] is True
                        and timestamp <= cutoff
                        and math.isfinite(price)
                        and price > 1
                    ):
                        valid.append((timestamp, price))
                except (KeyError, ValueError, TypeError, AttributeError):
                    continue
            if not valid:
                break
            timestamp = max(item[0] for item in valid)
            prices = {p for t, p in valid if t == timestamp}
            if len(prices) != 1:
                break  # conflicting simultaneous states are not guessable
            legs.append(
                {
                    "outcome_id": outcome,
                    "created_at": timestamp.isoformat(),
                    "price": prices.pop(),
                    "quote_age_seconds": (kickoff - timestamp).total_seconds(),
                    "seconds_before_cutoff": (cutoff - timestamp).total_seconds(),
                }
            )
        if len(legs) == 3:
            fair, margin = multiplicative_fair([leg["price"] for leg in legs])
            books[book] = {"legs": legs, "fair": list(fair), "overround": margin}
        else:
            excluded[book] = "INCOMPLETE_VALID_T30_TRIPLET"
    result = {
        "fixture_id": fixture_id,
        "match_id": match_id,
        "kickoff": kickoff.isoformat(),
        "cutoff": cutoff.isoformat(),
        "model_code": "MARKET_CONSENSUS",
        "model_version": MODELS["MARKET_CONSENSUS"],
        "evidence_profile": PROFILE,
        "evidence_class": "HISTORICAL_RESEARCH",
        "books": books,
        "book_count": len(books),
        "excluded_books": excluded,
        "de_vig_method": "multiplicative",
        "consensus_method": "equal_weight_arithmetic_mean",
        "raw_hash": identity(payload),
        "status": "UNAVAILABLE",
        "reason": "FEWER_THAN_TWO_COMPLETE_BOOKS",
    }
    if len(books) >= 2:
        probabilities = equal_weight_consensus([b["fair"] for b in books.values()])
        ProbabilityResult(*probabilities)
        result.update(status="PRODUCED", reason="", probabilities=list(probabilities))
    result["evidence_id"] = identity(result)
    return result
