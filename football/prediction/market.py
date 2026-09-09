import math
from dataclasses import dataclass

from penaltyblog.implied import calculate_implied

from football.market_identity import CANONICAL_1X2_CODE, MAPPING_VERSION
from football.models import OddsObservation, ReconciliationStatus

from .constants import MARKET_CONSENSUS_VERSION, OUTCOMES
from .contracts import ProbabilityResult, UnavailablePrediction


@dataclass(frozen=True)
class MarketQuote:
    observation: OddsObservation
    canonical_bookmaker: object
    prices: tuple
    fair_probabilities: tuple
    overround: float


@dataclass(frozen=True)
class MarketSelection:
    quotes: tuple[MarketQuote, ...]
    diagnostics: dict


def valid_prices(observation):
    prices = tuple(
        float(value) for value in (observation.home, observation.draw, observation.away)
    )
    if not all(math.isfinite(value) and value > 1 for value in prices):
        return None
    return prices


def _raw_identity(observation):
    return {
        "observation_id": observation.pk,
        "source": observation.source.code,
        "bookmaker_external_id": observation.bookmaker.external_id,
        "bookmaker_name": observation.bookmaker.name,
        "market_external_id": observation.market.external_id,
        "market_name": observation.market.name,
        "observed_at": observation.observed_at.isoformat(),
        "provider_updated_at": (
            observation.provider_updated_at.isoformat()
            if observation.provider_updated_at
            else None
        ),
    }


def market_selection_as_of(match, cutoff, *, not_before=None):
    queryset = OddsObservation.objects.filter(match=match, observed_at__lt=cutoff)
    if not_before is not None:
        queryset = queryset.filter(observed_at__gte=not_before)
    observations = queryset.select_related(
        "source",
        "bookmaker",
        "bookmaker__canonical_ref__canonical_bookmaker",
        "market",
        "market__canonical_ref__canonical_market",
    ).order_by(
        "-observed_at",
        "source__code",
        "bookmaker__external_id",
        "market__external_id",
        "id",
    )
    quotes = []
    selected_bookmakers = set()
    rejection_counts = {
        "unmapped_bookmaker": 0,
        "unmapped_market": 0,
        "non_1x2_market": 0,
        "invalid_prices": 0,
        "duplicate_canonical_vote": 0,
    }
    rejected = []
    for observation in observations:
        bookmaker_ref = getattr(observation.bookmaker, "canonical_ref", None)
        market_ref = getattr(observation.market, "canonical_ref", None)
        reason = ""
        if (
            bookmaker_ref is None
            or bookmaker_ref.reconciliation_status != ReconciliationStatus.RESOLVED
            or bookmaker_ref.canonical_bookmaker_id is None
        ):
            reason = "unmapped_bookmaker"
        elif (
            market_ref is None
            or market_ref.reconciliation_status != ReconciliationStatus.RESOLVED
            or market_ref.canonical_market_id is None
        ):
            reason = "unmapped_market"
        elif market_ref.canonical_market.code != CANONICAL_1X2_CODE:
            reason = "non_1x2_market"
        prices = valid_prices(observation) if not reason else None
        if not reason and prices is None:
            reason = "invalid_prices"
        canonical = (
            bookmaker_ref.canonical_bookmaker if bookmaker_ref is not None else None
        )
        if not reason and canonical.pk in selected_bookmakers:
            reason = "duplicate_canonical_vote"
        if reason:
            rejection_counts[reason] += 1
            if len(rejected) < 20:
                rejected.append(
                    {
                        **_raw_identity(observation),
                        "reason": reason.upper(),
                        "bookmaker_reconciliation_status": (
                            bookmaker_ref.reconciliation_status
                            if bookmaker_ref is not None
                            else "NO_REF"
                        ),
                        "bookmaker_reconciliation_reason": (
                            bookmaker_ref.reason
                            if bookmaker_ref is not None
                            else "NO_CANONICAL_REF"
                        ),
                        "market_reconciliation_status": (
                            market_ref.reconciliation_status
                            if market_ref is not None
                            else "NO_REF"
                        ),
                        "market_reconciliation_reason": (
                            market_ref.reason
                            if market_ref is not None
                            else "NO_CANONICAL_REF"
                        ),
                    }
                )
            continue
        implied = calculate_implied(list(prices), method="multiplicative")
        selected_bookmakers.add(canonical.pk)
        quotes.append(
            MarketQuote(
                observation=observation,
                canonical_bookmaker=canonical,
                prices=prices,
                fair_probabilities=tuple(map(float, implied.probabilities)),
                overround=float(implied.margin),
            )
        )
    provenance = [
        {
            "canonical_bookmaker_code": quote.canonical_bookmaker.code,
            "canonical_bookmaker_name": quote.canonical_bookmaker.name,
            **_raw_identity(quote.observation),
        }
        for quote in quotes
    ]
    ages = [
        (cutoff - quote.observation.observed_at).total_seconds() for quote in quotes
    ]
    diagnostics = {
        "canonical_identity_version": MAPPING_VERSION,
        "canonical_market": CANONICAL_1X2_CODE,
        "canonical_bookmaker_count": len(quotes),
        "book_count": len(quotes),
        "raw_observations_considered": len(observations),
        "rejection_counts": rejection_counts,
        "rejected_raw_provenance": rejected,
        "selected_raw_provenance": provenance,
        "sources": sorted({quote.observation.source.code for quote in quotes}),
        "minimum_age_seconds": min(ages) if ages else None,
        "maximum_age_seconds": max(ages) if ages else None,
        "strict_cutoff": cutoff.isoformat(),
        "evidence_not_before": not_before.isoformat() if not_before else None,
    }
    return MarketSelection(tuple(quotes), diagnostics)


def latest_observations_as_of(match, cutoff):
    return [quote.observation for quote in market_selection_as_of(match, cutoff).quotes]


def market_quotes_as_of(match, cutoff):
    return list(market_selection_as_of(match, cutoff).quotes)


class MarketConsensusAdapter:
    model_code = "MARKET_CONSENSUS"
    model_version = MARKET_CONSENSUS_VERSION
    config = {
        "de_vig_method": "multiplicative",
        "consensus_method": "equal_weight_arithmetic_mean",
        "canonical_identity_version": MAPPING_VERSION,
        "canonical_market": CANONICAL_1X2_CODE,
    }

    def predict(self, match, cutoff, *, not_before=None):
        selection = market_selection_as_of(match, cutoff, not_before=not_before)
        quotes = selection.quotes
        if not quotes:
            return UnavailablePrediction(
                "NO_VALID_CANONICAL_1X2_QUOTES", selection.diagnostics
            )
        means = [
            sum(quote.fair_probabilities[index] for quote in quotes) / len(quotes)
            for index in range(3)
        ]
        total = sum(means)
        probabilities = [value / total for value in means]
        overrounds = [quote.overround for quote in quotes]
        return ProbabilityResult(
            *probabilities,
            diagnostics={
                **selection.diagnostics,
                "de_vig_method": "multiplicative",
                "consensus_method": "equal_weight_arithmetic_mean",
                "consensus_evidence": (
                    "SINGLE_BOOKMAKER_TECHNICAL_ONLY"
                    if len(quotes) == 1
                    else "MULTI_BOOKMAKER_UNCALIBRATED"
                ),
                "mean_overround": sum(overrounds) / len(overrounds),
                "min_overround": min(overrounds),
                "max_overround": max(overrounds),
            },
        )


def best_prices_as_of(match, cutoff):
    quotes = market_quotes_as_of(match, cutoff)
    if not quotes:
        return {}
    best = {}
    for index, outcome in enumerate(OUTCOMES):
        quote = max(quotes, key=lambda candidate: candidate.prices[index])
        best[outcome] = (
            quote.observation,
            getattr(quote.observation, outcome.lower()),
        )
    return best
