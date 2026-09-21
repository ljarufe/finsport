"""FS-019 adapter for retained FS-018 raw historical 1X2 prices."""

import math
import string
from datetime import timedelta

from .storage import instant

OUTCOME_IDS = {"HOME": "101", "DRAW": "102", "AWAY": "103"}
BOOKMAKER_ORDER = ("pinnacle", "bet365", "unibet")
EVIDENCE_PROFILE = "ODDSPAPI_RECONSTRUCTED_T30_V1"


def _sha256(value, label):
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in string.hexdigits for character in value)
    ):
        raise ValueError(f"INVALID_{label}")


def _number(value, label):
    if isinstance(value, bool):
        raise ValueError(f"INVALID_{label}")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"INVALID_{label}") from None
    if not math.isfinite(result):
        raise ValueError(f"INVALID_{label}")
    return result


def validate_price_evidence(row):
    """Validate complete retained books and reject any post-T30 substitution."""
    if row.get("evidence_profile") != EVIDENCE_PROFILE:
        raise ValueError("PRICE_EVIDENCE_PROFILE_MISMATCH")
    books = row.get("selected_prices")
    timestamps = row.get("selected_quote_timestamps")
    ages = row.get("quote_ages_seconds")
    if not all(isinstance(value, dict) for value in (books, timestamps, ages)):
        raise ValueError("PRICE_EVIDENCE_SHAPE_MISMATCH")
    if set(books) != set(timestamps) or set(books) != set(ages):
        raise ValueError("PRICE_BOOK_PROVENANCE_MISMATCH")
    if not 2 <= len(books) <= 3 or set(books) - set(BOOKMAKER_ORDER):
        raise ValueError("PRICE_COMPLETE_BOOK_COUNT_MISMATCH")
    if row.get("bookmaker_count") != len(books):
        raise ValueError("PRICE_BOOK_COUNT_MISMATCH")
    kickoff = instant(row["kickoff"])
    cutoff = kickoff - timedelta(minutes=30)
    for bookmaker in books:
        if (
            set(books[bookmaker]) != set(OUTCOME_IDS.values())
            or set(timestamps[bookmaker]) != set(OUTCOME_IDS.values())
            or set(ages[bookmaker]) != set(OUTCOME_IDS.values())
        ):
            raise ValueError("INCOMPLETE_1X2_BOOK")
        for outcome_id in OUTCOME_IDS.values():
            price = _number(books[bookmaker][outcome_id], "RAW_DECIMAL_PRICE")
            age = _number(ages[bookmaker][outcome_id], "QUOTE_AGE")
            quote = instant(timestamps[bookmaker][outcome_id])
            calculated_age = (kickoff - quote).total_seconds()
            if price <= 1:
                raise ValueError("INVALID_RAW_DECIMAL_PRICE")
            if quote > cutoff or age < 1800:
                raise ValueError("POST_T30_PRICE_FORBIDDEN")
            if not math.isclose(age, calculated_age, abs_tol=0.001):
                raise ValueError("QUOTE_AGE_TIMESTAMP_MISMATCH")
    if not row.get("provider_fixture_id"):
        raise ValueError("MISSING_PROVIDER_FIXTURE_ID")
    _sha256(row.get("fs018_evidence_id"), "FS018_EVIDENCE_ID")
    _sha256(row.get("raw_cache_hash"), "RAW_CACHE_HASH")
    return row


def best_price(row, outcome):
    """Select the maximum raw payout price and deterministic co-best provenance."""
    validate_price_evidence(row)
    try:
        outcome_id = OUTCOME_IDS[outcome]
    except KeyError:
        raise ValueError("UNKNOWN_OUTCOME") from None
    prices = {
        bookmaker: float(row["selected_prices"][bookmaker][outcome_id])
        for bookmaker in BOOKMAKER_ORDER
        if bookmaker in row["selected_prices"]
    }
    selected = max(prices.values())
    co_best = [
        bookmaker for bookmaker in BOOKMAKER_ORDER if prices.get(bookmaker) == selected
    ]
    representative = co_best[0]
    return {
        "selected_price": selected,
        "co_best_bookmakers": co_best,
        "representative_bookmaker": representative,
        "selected_quote_timestamp": row["selected_quote_timestamps"][representative][
            outcome_id
        ],
        "selected_quote_age_seconds": float(
            row["quote_ages_seconds"][representative][outcome_id]
        ),
        "provider_fixture_id": row["provider_fixture_id"],
        "fs018_evidence_id": row["fs018_evidence_id"],
        "raw_cache_hash": row["raw_cache_hash"],
    }
