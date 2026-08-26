from collections import defaultdict

from penaltyblog.ratings import Elo
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .constants import ELO_MULTINOMIAL_LOGIT_VERSION, OUTCOMES
from .contracts import ProbabilityResult, UnavailablePrediction
from .datasets import local_day, rows_from_matches

RESULT_CODES = {"HOME": 0, "DRAW": 1, "AWAY": 2}


def sequential_elo_features(matches, *, k):
    """Capture every day's features before revealing any result from that day."""
    elo = Elo(k=float(k), home_field_advantage=100.0)
    grouped = defaultdict(list)
    for row in rows_from_matches(matches):
        grouped[local_day(row.kickoff)].append(row)
    features = []
    labels = []
    for day in sorted(grouped):
        frozen = []
        for row in sorted(grouped[day], key=lambda item: (item.kickoff, item.match_id)):
            difference = elo.get_team_rating(row.home_team) - elo.get_team_rating(
                row.away_team
            )
            features.append([difference, abs(difference)])
            labels.append(row.outcome)
            frozen.append(row)
        for row in frozen:
            elo.update_ratings(row.home_team, row.away_team, RESULT_CODES[row.outcome])
    return features, labels, elo


class EloMultinomialAdapter:
    model_code = "ELO_MULTINOMIAL_LOGIT"
    model_version = ELO_MULTINOMIAL_LOGIT_VERSION

    def __init__(self, *, k, c):
        self.k = int(k)
        self.c = float(c)
        self.classifier = None
        self.elo = None

    @property
    def config(self):
        return {
            "k": self.k,
            "C": self.c,
            "initial_rating": 1500,
            "home_field_advantage": 100,
            "features": ["elo_diff", "abs_elo_diff"],
            "solver": "lbfgs",
            "max_iter": 1000,
        }

    def fit(self, history, cutoff=None):
        del cutoff
        features, labels, self.elo = sequential_elo_features(history, k=self.k)
        if len(set(labels)) < 3:
            return UnavailablePrediction("INSUFFICIENT_OUTCOME_CLASSES")
        self.classifier = Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(C=self.c, solver="lbfgs", max_iter=1000),
                ),
            ]
        )
        self.classifier.fit(features, labels)
        return self

    def predict(self, match, cutoff=None):
        del cutoff
        if self.classifier is None or self.elo is None:
            return UnavailablePrediction("MODEL_NOT_FITTED")
        home = str(match.home_team_id)
        away = str(match.away_team_id)
        difference = self.elo.get_team_rating(home) - self.elo.get_team_rating(away)
        raw = self.classifier.predict_proba([[difference, abs(difference)]])[0]
        classes = self.classifier.named_steps["classifier"].classes_
        by_class = {label: float(value) for label, value in zip(classes, raw)}
        return ProbabilityResult(
            *(by_class[outcome] for outcome in OUTCOMES),
            diagnostics={
                "k": self.k,
                "C": self.c,
                "elo_diff": difference,
                "classes": list(classes),
            },
        )
