import math
from collections import defaultdict
from dataclasses import dataclass

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

from .constants import (
    LOGISTIC_C_GRID,
    MODERNIZED_R45_VERSION,
    PRIOR_STRENGTH_GRID,
    R45_VARIANTS,
)
from .contracts import ProbabilityResult, UnavailablePrediction
from .datasets import daily_batches
from .market import MarketConsensusAdapter


def logit(probability, epsilon=1e-6):
    clipped = min(max(float(probability), epsilon), 1 - epsilon)
    return math.log(clipped / (1 - clipped))


def shrunk_draw_rate(draws, matches, prior_mean, prior_strength):
    alpha = prior_mean * prior_strength
    beta = (1 - prior_mean) * prior_strength
    return (draws + alpha) / (matches + alpha + beta)


def modernized_features(market, draw_rate, variant):
    if variant not in R45_VARIANTS:
        raise ValueError(f"Unknown Modernized R45 variant: {variant}")
    features = [logit(market.p_draw)]
    if variant in ("M1", "M3"):
        features.append(abs(market.p_home - market.p_away))
    if variant in ("M2", "M3"):
        features.append(draw_rate)
    return features


@dataclass(frozen=True)
class ModernizedFeatureRow:
    match: object
    features: list
    is_draw: int
    market: ProbabilityResult
    draw_rate: float


def build_modernized_feature_rows(matches, *, variant, prior_strength):
    """Build features using only market and results available before each day."""
    market_adapter = MarketConsensusAdapter()
    completed_by_season = defaultdict(lambda: [0, 0])
    rows = []
    unavailable = defaultdict(int)
    for _, batch in daily_batches(matches):
        season_year = batch[0].season.year
        prior_draws = sum(
            draws
            for year, (draws, _) in completed_by_season.items()
            if year < season_year
        )
        prior_matches = sum(
            count
            for year, (_, count) in completed_by_season.items()
            if year < season_year
        )
        if prior_matches or variant in ("M0", "M1"):
            current_draws, current_matches = completed_by_season[season_year]
            draw_rate = (
                shrunk_draw_rate(
                    current_draws,
                    current_matches,
                    prior_draws / prior_matches,
                    prior_strength,
                )
                if prior_matches
                else 0.0
            )
            for match in batch:
                market = market_adapter.predict(match, match.kickoff)
                if isinstance(market, UnavailablePrediction):
                    unavailable[market.reason] += 1
                    continue
                rows.append(
                    ModernizedFeatureRow(
                        match=match,
                        features=modernized_features(market, draw_rate, variant),
                        is_draw=int(match.home_score == match.away_score),
                        market=market,
                        draw_rate=draw_rate,
                    )
                )
        else:
            unavailable["NO_PRIOR_SEASON_DRAW_RATE"] += len(batch)
        # Freeze every feature in the batch before revealing any batch result.
        for match in batch:
            completed_by_season[season_year][0] += int(
                match.home_score == match.away_score
            )
            completed_by_season[season_year][1] += 1
    return rows, dict(unavailable)


class ModernizedR45Adapter:
    model_code = "MODERNIZED_R45"
    model_version = MODERNIZED_R45_VERSION

    def __init__(self, *, variant, c, prior_strength):
        self.variant = variant
        self.c = float(c)
        self.prior_strength = int(prior_strength)
        self.classifier = LogisticRegression(C=self.c, solver="lbfgs", max_iter=1000)
        self.fitted = False

    @property
    def config(self):
        return {
            "variant": self.variant,
            "C": self.c,
            "prior_strength": self.prior_strength,
            "epsilon": 1e-6,
            "solver": "lbfgs",
            "max_iter": 1000,
        }

    def fit_features(self, features, labels):
        if len(set(labels)) < 2:
            return UnavailablePrediction("INSUFFICIENT_OUTCOME_CLASSES")
        self.classifier.fit(features, labels)
        self.fitted = True
        return self

    def predict_from_market(self, market, draw_rate):
        if not self.fitted:
            return UnavailablePrediction("MODEL_NOT_FITTED")
        feature = modernized_features(market, draw_rate, self.variant)
        probabilities = self.classifier.predict_proba([feature])[0]
        by_class = dict(zip(self.classifier.classes_, probabilities))
        p_draw = float(by_class[1])
        non_draw = market.p_home + market.p_away
        if non_draw <= 0:
            return UnavailablePrediction("INVALID_MARKET_HOME_AWAY_MASS")
        p_home = (1 - p_draw) * market.p_home / non_draw
        p_away = (1 - p_draw) * market.p_away / non_draw
        return ProbabilityResult(
            p_home,
            p_draw,
            p_away,
            diagnostics={"variant": self.variant, "draw_rate": draw_rate},
        )


def select_modernized_config(training_matches, validation_matches, configs):
    """Select M0-M3/C/prior strength without inspecting later outcomes."""
    training_ids = {match.id for match in training_matches}
    validation_ids = {match.id for match in validation_matches}
    all_matches = sorted(
        [*training_matches, *validation_matches],
        key=lambda match: (match.kickoff, match.id),
    )
    results = []
    for config in configs:
        rows, _ = build_modernized_feature_rows(
            all_matches,
            variant=config["variant"],
            prior_strength=config["prior_strength"],
        )
        training = [row for row in rows if row.match.id in training_ids]
        validation = [row for row in rows if row.match.id in validation_ids]
        adapter = ModernizedR45Adapter(**config)
        fitted = adapter.fit_features(
            [row.features for row in training], [row.is_draw for row in training]
        )
        if isinstance(fitted, UnavailablePrediction):
            continue
        if not validation:
            continue
        probability = adapter.classifier.predict_proba(
            [row.features for row in validation]
        )
        draw_index = list(adapter.classifier.classes_).index(1)
        loss = log_loss(
            [row.is_draw for row in validation],
            probability[:, draw_index],
            labels=[0, 1],
        )
        results.append((loss, config))
    return (
        min(
            results,
            key=lambda item: (
                item[0],
                item[1]["variant"],
                item[1]["prior_strength"],
                item[1]["c"],
            ),
        )
        if results
        else None
    )


def modernized_config_grid():
    return [
        {"variant": variant, "c": c, "prior_strength": prior_strength}
        for variant in R45_VARIANTS
        for c in LOGISTIC_C_GRID
        for prior_strength in PRIOR_STRENGTH_GRID
    ]


def fit_modernized(history, cutoff, config):
    """Fit the selected arm from strictly prior resolved/market evidence."""
    if any(match.kickoff >= cutoff for match in history):
        raise ValueError("Modernized R45 history must be strictly before cutoff.")
    rows, unavailable = build_modernized_feature_rows(
        history,
        variant=config["variant"],
        prior_strength=config["prior_strength"],
    )
    adapter = ModernizedR45Adapter(
        variant=config["variant"],
        c=config["c"],
        prior_strength=config["prior_strength"],
    )
    fitted = adapter.fit_features(
        [row.features for row in rows], [row.is_draw for row in rows]
    )
    if isinstance(fitted, UnavailablePrediction):
        return fitted, unavailable
    return adapter, unavailable


def draw_rate_for_target(history, target, prior_strength):
    prior = [match for match in history if match.season.year < target.season.year]
    if not prior:
        return UnavailablePrediction("NO_PRIOR_SEASON_DRAW_RATE")
    current = [match for match in history if match.season.year == target.season.year]
    prior_draws = sum(match.home_score == match.away_score for match in prior)
    current_draws = sum(match.home_score == match.away_score for match in current)
    return shrunk_draw_rate(
        current_draws,
        len(current),
        prior_draws / len(prior),
        prior_strength,
    )


def predict_modernized(adapter, history, match, cutoff):
    if match.kickoff < cutoff:
        raise ValueError("Modernized R45 target cannot precede its cutoff.")
    market = MarketConsensusAdapter().predict(match, cutoff)
    if isinstance(market, UnavailablePrediction):
        return market
    draw_rate = draw_rate_for_target(history, match, adapter.prior_strength)
    if isinstance(draw_rate, UnavailablePrediction):
        if adapter.variant in ("M0", "M1"):
            draw_rate = 0.0
        else:
            return draw_rate
    result = adapter.predict_from_market(market, draw_rate)
    if isinstance(result, UnavailablePrediction):
        return result
    return ProbabilityResult(
        result.p_home,
        result.p_draw,
        result.p_away,
        diagnostics={
            **result.diagnostics,
            "market_cutoff": cutoff.isoformat(),
            "history_max_kickoff": (
                max((row.kickoff for row in history), default=None).isoformat()
                if history
                else None
            ),
        },
    )
