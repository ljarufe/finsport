import math

from penaltyblog.models import (
    DixonColesGoalModel,
    PoissonGoalsModel,
    dixon_coles_weights,
)

from .constants import DIXON_COLES_VERSION, INDEPENDENT_POISSON_VERSION
from .contracts import (
    FailedPrediction,
    ProbabilityContractError,
    ProbabilityResult,
    UnavailablePrediction,
)
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

    def __init__(self, *, xi):
        super().__init__(xi=xi)
        self.team_counts = {}
        self.component_count = 0
        self.readiness_assessor = None
        self.fit_error = None

    def fit_for_targets(
        self, history, cutoff, target_matches, *, readiness_assessor=None
    ):
        return self.fit(
            history,
            cutoff,
            target_matches=target_matches,
            readiness_assessor=readiness_assessor,
        )

    def fit(self, history, cutoff, *, target_matches=None, readiness_assessor=None):
        del target_matches
        self.readiness_assessor = readiness_assessor
        try:
            rows = rows_from_matches(history)
        except ValueError as error:
            return FailedPrediction(
                "CANONICAL_TRAINING_DATA_INTEGRITY_FAILURE",
                {"error": str(error)[:500]},
            )
        if not rows:
            return UnavailablePrediction("INSUFFICIENT_TRAINING_HISTORY")
        if not math.isfinite(self.xi) or self.xi < 0:
            return UnavailablePrediction("INVALID_TIME_WEIGHT_CONFIGURATION")
        graph = {}
        for row in rows:
            graph.setdefault(row.home_team, set()).add(row.away_team)
            graph.setdefault(row.away_team, set()).add(row.home_team)
            self.team_counts[row.home_team] = self.team_counts.get(row.home_team, 0) + 1
            self.team_counts[row.away_team] = self.team_counts.get(row.away_team, 0) + 1
        remaining = set(graph)
        components = []
        while remaining:
            pending = [remaining.pop()]
            component = set(pending)
            while pending:
                node = pending.pop()
                for neighbor in graph[node] & remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    pending.append(neighbor)
            components.append(component)
        self.component_count = len(components)
        diagnostics = {
            "training_matches": len(rows),
            "unique_teams": len(graph),
            "component_count": self.component_count,
            "connected": self.component_count == 1,
        }
        if self.component_count != 1:
            return UnavailablePrediction("DISCONNECTED_TRAINING_GRAPH", diagnostics)
        self.known_teams = set(graph)
        self.training_count = len(rows)
        try:
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
        except Exception as error:
            self.fit_error = error
        return self

    def predict(self, match, cutoff):
        del cutoff
        teams = (str(match.home_team_id), str(match.away_team_id))
        diagnostics = {
            "xi": self.xi,
            "training_matches": self.training_count,
            "unique_teams": len(self.known_teams),
            "component_count": self.component_count,
            "connected": self.component_count == 1,
            "home_team_history": self.team_counts.get(teams[0], 0),
            "away_team_history": self.team_counts.get(teams[1], 0),
        }
        unknown = [team for team in teams if team not in self.known_teams]
        if unknown:
            return UnavailablePrediction(
                "INSUFFICIENT_TEAM_HISTORY",
                {**diagnostics, "unknown_team_ids": unknown},
            )
        readiness_passed = False
        if self.readiness_assessor is not None:
            assessment = self.readiness_assessor(diagnostics)
            readiness_passed = assessment.eligible
            diagnostics["readiness_reason"] = assessment.reason
        if self.fit_error is not None:
            if not readiness_passed and "negative probabilities" in str(self.fit_error):
                return UnavailablePrediction(
                    "STRUCTURALLY_UNSTABLE_EXPLORATORY_EVIDENCE",
                    {**diagnostics, "error": str(self.fit_error)[:500]},
                )
            return FailedPrediction(
                "DIXON_COLES_FIT_FAILED",
                {
                    **diagnostics,
                    "error_class": type(self.fit_error).__name__,
                    "error": str(self.fit_error)[:500],
                },
            )
        if self.model is None:
            return UnavailablePrediction("MODEL_NOT_FITTED", diagnostics)
        try:
            probabilities = self.model.predict(*teams).home_draw_away
            return ProbabilityResult(
                *map(float, probabilities), diagnostics=diagnostics
            )
        except ProbabilityContractError as error:
            if not readiness_passed:
                return UnavailablePrediction(
                    "STRUCTURALLY_UNSTABLE_EXPLORATORY_EVIDENCE",
                    {**diagnostics, "error": str(error)[:500]},
                )
            return FailedPrediction(
                "INVALID_DIXON_COLES_PROBABILITY_OUTPUT",
                {**diagnostics, "error": str(error)[:500]},
            )
        except Exception as error:
            if not readiness_passed and "negative probabilities" in str(error):
                return UnavailablePrediction(
                    "STRUCTURALLY_UNSTABLE_EXPLORATORY_EVIDENCE",
                    {**diagnostics, "error": str(error)[:500]},
                )
            return FailedPrediction(
                "DIXON_COLES_PREDICTION_FAILED",
                {
                    **diagnostics,
                    "error_class": type(error).__name__,
                    "error": str(error)[:500],
                },
            )


class IndependentPoissonAdapter(GoalModelAdapter):
    model_class = PoissonGoalsModel
    model_code = "INDEPENDENT_POISSON"
    model_version = INDEPENDENT_POISSON_VERSION
