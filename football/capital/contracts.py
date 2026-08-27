from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

ENGINE_VERSION = "fs004-v1"
ZERO = Decimal("0")


class CapitalError(Exception):
    """Base error for the local capital evaluator."""


class CapitalInputError(CapitalError):
    """The Decision selector or experiment config is ambiguous or invalid."""


class PolicyConfigError(CapitalError):
    """A capital policy config is invalid."""


class RunUnavailable(CapitalError):
    """The requested run cannot be honestly produced from its input evidence."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class CapitalDecision:
    source_id: int
    decision_time: datetime
    action: str
    outcome: str
    price: Decimal | None
    probability: Decimal | None
    observation_id: int | None = None
    observation_time: datetime | None = None

    @property
    def actionable(self):
        return self.action != "NO_BET"


@dataclass(frozen=True)
class StakeRequest:
    requested: Decimal
    applied: Decimal
    reason: str = ""
    cap_hit: bool = False
    shortfall: Decimal = ZERO
    termination_reason: str = ""
    step: int | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ReplayLedgerRow:
    source_id: int
    batch_time: datetime
    batch_index: int
    step: int | None
    requested_stake: Decimal
    applied_stake: Decimal
    bankroll_before: Decimal
    bankroll_after: Decimal
    profit_loss: Decimal
    action: str
    outcome: str
    price: Decimal | None
    capital_reason: str
    policy_state: dict
    cap_hit: bool
    shortfall: Decimal
    practical_ruin: bool
    termination_reason: str


@dataclass(frozen=True)
class ReplayResult:
    metrics: dict
    ledger: tuple[ReplayLedgerRow, ...]


def json_decimal(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: json_decimal(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_decimal(item) for item in value]
    return value
