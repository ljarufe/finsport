from penaltyblog.models import (
    DixonColesGoalModel,
    PoissonGoalsModel,
    dixon_coles_weights,
)

from .constants import DIXON_COLES_VERSION, INDEPENDENT_POISSON_VERSION
from .contracts import ProbabilityResult, UnavailablePrediction
from .datasets import rows_from_matches


class GoalModelAdapter:
    model_class = None
    model_code = ""
    model_version = ""

    def __init__(self, *, xi):
        self.xi = float(xi)
        self.model = None
        self.known_teams = set()
        self.training_count = 0

    @property
    def config(self):
        return {
            "xi": self.xi,
            "max_history": None,
            "time_weighting": "dixon_coles_weights",
        }

    def fit(self, history, cutoff):
        rows = rows_from_matches(history)
        if not rows:
            return UnavailablePrediction("INSUFFICIENT_TRAINING_HISTORY")
        self.known_teams = {
            team for row in rows for team in (row.home_team, row.away_team)
        }
        self.training_count = len(rows)
        weights = dixon_coles_weights(
            [row.kickoff for row in rows], xi=self.xi, base_date=cutoff
        )
        self.model = self.model_class(
            [row.home_score for row in rows],
            [row.away_score for row in rows],
            [row.home_team for row in rows],
            [row.away_team for row in rows],
            weights=weights,
        )
        self.model.fit()
        return self

    def predict(self, match, cutoff):
        del cutoff
        teams = (str(match.home_team_id), str(match.away_team_id))
        if self.model is None:
            return UnavailablePrediction("MODEL_NOT_FITTED")
        if any(team not in self.known_teams for team in teams):
            return UnavailablePrediction(
                "INSUFFICIENT_TEAM_HISTORY",
                {
                    "unknown_team_ids": [
                        team for team in teams if team not in self.known_teams
                    ]
                },
            )
        probabilities = self.model.predict(*teams).home_draw_away
        return ProbabilityResult(
            *map(float, probabilities),
            diagnostics={"xi": self.xi, "training_matches": self.training_count},
        )


class DixonColesAdapter(GoalModelAdapter):
    model_class = DixonColesGoalModel
    model_code = "DIXON_COLES"
    model_version = DIXON_COLES_VERSION


class IndependentPoissonAdapter(GoalModelAdapter):
    model_class = PoissonGoalsModel
    model_code = "INDEPENDENT_POISSON"
    model_version = INDEPENDENT_POISSON_VERSION
