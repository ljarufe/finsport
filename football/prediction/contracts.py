import math
from dataclasses import dataclass, field

from .constants import OUTCOMES


class ProbabilityContractError(ValueError):
    pass


@dataclass(frozen=True)
class ProbabilityResult:
    p_home: float
    p_draw: float
    p_away: float
    diagnostics: dict = field(default_factory=dict)

    def __post_init__(self):
        values = self.as_tuple()
        if not all(math.isfinite(value) and 0 <= value <= 1 for value in values):
            raise ProbabilityContractError(
                "Probabilities must be finite and between zero and one."
            )
        if abs(sum(values) - 1) > 1e-6:
            raise ProbabilityContractError("Probabilities must sum to one.")

    def as_tuple(self):
        return (float(self.p_home), float(self.p_draw), float(self.p_away))

    @property
    def predicted_outcome(self):
        # tuple.index gives the required HOME, DRAW, AWAY deterministic tie-break.
        return OUTCOMES[self.as_tuple().index(max(self.as_tuple()))]

    def probability_for(self, outcome):
        return self.as_tuple()[OUTCOMES.index(outcome)]


@dataclass(frozen=True)
class UnavailablePrediction:
    reason: str
    diagnostics: dict = field(default_factory=dict)
