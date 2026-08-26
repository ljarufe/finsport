import math
from dataclasses import dataclass

from django.db.models import Q
from penaltyblog.implied import calculate_implied

from football.models import OddsObservation

from .constants import MARKET_CONSENSUS_VERSION, OUTCOMES
from .contracts import ProbabilityResult, UnavailablePrediction


@dataclass(frozen=True)
class MarketQuote:
    observation: OddsObservation
    prices: tuple
    fair_probabilities: tuple
    overround: float


def valid_prices(observation):
    prices = tuple(
        float(value) for value in (observation.home, observation.draw, observation.away)
    )
    if not all(math.isfinite(value) and value > 1 for value in prices):
        return None
    return prices


def latest_observations_as_of(match, cutoff):
    observations = (
        OddsObservation.objects.filter(match=match, observed_at__lt=cutoff)
        .filter(Q(market__name__iexact="Match Winner") | Q(market__name__iexact="1X2"))
        .select_related("source", "bookmaker", "market")
        .order_by("source_id", "bookmaker_id", "market_id", "-observed_at", "-id")
    )
    latest = []
    identities = set()
    for observation in observations:
        identity = (
            observation.source_id,
            observation.bookmaker_id,
            observation.market_id,
        )
        if identity not in identities:
            identities.add(identity)
            latest.append(observation)
    return latest


def market_quotes_as_of(match, cutoff):
    quotes = []
    for observation in latest_observations_as_of(match, cutoff):
        prices = valid_prices(observation)
        if prices is None:
            continue
        implied = calculate_implied(list(prices), method="multiplicative")
        quotes.append(
            MarketQuote(
                observation=observation,
                prices=prices,
                fair_probabilities=tuple(map(float, implied.probabilities)),
                overround=float(implied.margin),
            )
        )
    return quotes


class MarketConsensusAdapter:
    model_code = "MARKET_CONSENSUS"
    model_version = MARKET_CONSENSUS_VERSION
    config = {
        "de_vig_method": "multiplicative",
        "consensus_method": "mean",
    }

    def predict(self, match, cutoff):
        quotes = market_quotes_as_of(match, cutoff)
        if not quotes:
            return UnavailablePrediction("NO_VALID_MARKET")
        means = [
            sum(quote.fair_probabilities[index] for quote in quotes) / len(quotes)
            for index in range(3)
        ]
        total = sum(means)
        probabilities = [value / total for value in means]
        sources = sorted({quote.observation.source.code for quote in quotes})
        names_by_source = {}
        for quote in quotes:
            key = quote.observation.bookmaker.name.casefold()
            names_by_source.setdefault(key, set()).add(quote.observation.source.code)
        overlaps = sorted(
            name
            for name, quote_sources in names_by_source.items()
            if len(quote_sources) > 1
        )
        overrounds = [quote.overround for quote in quotes]
        ages = [
            (cutoff - quote.observation.observed_at).total_seconds() for quote in quotes
        ]
        return ProbabilityResult(
            *probabilities,
            diagnostics={
                "book_count": len(quotes),
                "sources": sources,
                "possible_cross_source_name_overlaps": overlaps,
                "de_vig_method": "multiplicative",
                "consensus_method": "mean",
                "mean_overround": sum(overrounds) / len(overrounds),
                "min_overround": min(overrounds),
                "max_overround": max(overrounds),
                "minimum_age_seconds": min(ages),
                "maximum_age_seconds": max(ages),
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
