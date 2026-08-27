from decimal import ROUND_CEILING, Decimal

from .contracts import ZERO, PolicyConfigError, StakeRequest

FLAT_UNIT = "FLAT_UNIT"
FIXED_FRACTION_BANKROLL = "FIXED_FRACTION_BANKROLL"
FIXED_TARGET_PROFIT_NO_RECOVERY = "FIXED_TARGET_PROFIT_NO_RECOVERY"
LEGACY_RECOVERY = "LEGACY_RECOVERY"
LEGACY_CAPPED = "LEGACY_CAPPED"
LEGACY_PARTIAL = "LEGACY_PARTIAL"
FRACTIONAL_KELLY = "FRACTIONAL_KELLY"

POLICY_VERSIONS = {
    FLAT_UNIT: "fs004-flat-unit-v1",
    FIXED_FRACTION_BANKROLL: "fs004-fixed-fraction-bankroll-v1",
    FIXED_TARGET_PROFIT_NO_RECOVERY: "fs004-fixed-target-no-recovery-v1",
    LEGACY_RECOVERY: "fs004-legacy-recovery-deviation-1-v1",
    LEGACY_CAPPED: "fs004-legacy-capped-v1",
    LEGACY_PARTIAL: "fs004-legacy-partial-v1",
    FRACTIONAL_KELLY: "fs004-fractional-kelly-v1",
}

RECOVERY_CODES = {LEGACY_RECOVERY, LEGACY_CAPPED, LEGACY_PARTIAL}


def _decimal(config, key, *, minimum=None, maximum=None, strict_minimum=False):
    try:
        raw = config[key]
    except KeyError as error:
        raise PolicyConfigError(f"MISSING_POLICY_CONFIG:{key}") from error
    if isinstance(raw, float):
        raise PolicyConfigError(f"BINARY_FLOAT_POLICY_CONFIG_NOT_ALLOWED:{key}")
    try:
        value = raw if isinstance(raw, Decimal) else Decimal(str(raw))
    except Exception as error:
        raise PolicyConfigError(f"INVALID_DECIMAL_POLICY_CONFIG:{key}") from error
    if not value.is_finite():
        raise PolicyConfigError(f"NON_FINITE_POLICY_CONFIG:{key}")
    if minimum is not None:
        invalid = value <= minimum if strict_minimum else value < minimum
        if invalid:
            raise PolicyConfigError(f"POLICY_CONFIG_BELOW_MINIMUM:{key}")
    if maximum is not None and value > maximum:
        raise PolicyConfigError(f"POLICY_CONFIG_ABOVE_MAXIMUM:{key}")
    return value


class CapitalPolicy:
    requires_probability = False
    is_recovery = False

    def __init__(self, config):
        self.config = config

    @property
    def version(self):
        return POLICY_VERSIONS[self.code]

    def initial_state(self):
        return {}

    def settle(self, state, request, won):
        del request, won
        return state, None


class FlatUnitPolicy(CapitalPolicy):
    code = FLAT_UNIT

    def __init__(self, config):
        super().__init__(config)
        self.unit = _decimal(config, "unit", minimum=ZERO, strict_minimum=True)

    def request(self, decision, bankroll, state):
        del decision, bankroll, state
        return StakeRequest(self.unit, self.unit)


class FixedFractionPolicy(CapitalPolicy):
    code = FIXED_FRACTION_BANKROLL

    def __init__(self, config):
        super().__init__(config)
        self.fraction = _decimal(
            config, "fraction", minimum=ZERO, maximum=Decimal("1"), strict_minimum=True
        )
        if self.fraction == 1:
            raise PolicyConfigError("POLICY_CONFIG_MUST_BE_LESS_THAN_ONE:fraction")

    def request(self, decision, bankroll, state):
        del decision, state
        stake = self.fraction * bankroll
        return StakeRequest(stake, stake)


class FixedTargetPolicy(CapitalPolicy):
    code = FIXED_TARGET_PROFIT_NO_RECOVERY

    def __init__(self, config):
        super().__init__(config)
        self.target = _decimal(
            config, "target_profit", minimum=ZERO, strict_minimum=True
        )

    def request(self, decision, bankroll, state):
        del bankroll, state
        stake = self.target / (decision.price - 1)
        return StakeRequest(stake, stake)


class RecoveryPolicy(CapitalPolicy):
    is_recovery = True

    def initial_state(self):
        return {"target_profit": None, "accumulated_loss": ZERO, "step": 0}

    def settle(self, state, request, won):
        target = state["target_profit"]
        if target is None:
            target = request.metadata["target_profit"]
        if won:
            return self.initial_state(), request.step
        return {
            "target_profit": target,
            "accumulated_loss": state["accumulated_loss"] + request.applied,
            "step": request.step,
        }, None


class LegacyRecoveryPolicy(RecoveryPolicy):
    code = LEGACY_RECOVERY

    def __init__(self, config):
        super().__init__(config)
        self.initial_stake = _decimal(
            config, "initial_stake", minimum=ZERO, strict_minimum=True
        )

    def request(self, decision, bankroll, state):
        del bankroll
        step = state["step"] + 1
        if state["target_profit"] is None:
            target = self.initial_stake * (decision.price - 1)
            return StakeRequest(
                self.initial_stake,
                self.initial_stake,
                step=step,
                metadata={"target_profit": target},
            )
        requested = (
            (state["target_profit"] + state["accumulated_loss"]) / (decision.price - 1)
        ).to_integral_value(rounding=ROUND_CEILING)
        return StakeRequest(
            requested,
            requested,
            step=step,
            metadata={"target_profit": state["target_profit"]},
        )


class LegacyCappedPolicy(RecoveryPolicy):
    code = LEGACY_CAPPED

    def __init__(self, config):
        super().__init__(config)
        self.initial_stake = _decimal(
            config, "initial_stake", minimum=ZERO, strict_minimum=True
        )
        self.max_stake_fraction = None
        self.max_absolute_stake = None
        self.max_recovery_steps = config.get("max_recovery_steps")
        if "max_stake_fraction" in config:
            self.max_stake_fraction = _decimal(
                config,
                "max_stake_fraction",
                minimum=ZERO,
                maximum=Decimal("1"),
                strict_minimum=True,
            )
        if "max_absolute_stake" in config:
            self.max_absolute_stake = _decimal(
                config, "max_absolute_stake", minimum=ZERO, strict_minimum=True
            )
        if self.max_recovery_steps is not None:
            if (
                not isinstance(self.max_recovery_steps, int)
                or self.max_recovery_steps < 1
            ):
                raise PolicyConfigError("INVALID_POLICY_CONFIG:max_recovery_steps")
        if (
            self.max_stake_fraction is None
            and self.max_absolute_stake is None
            and self.max_recovery_steps is None
        ):
            raise PolicyConfigError("LEGACY_CAPPED_REQUIRES_EXPLICIT_BOUND")

    def request(self, decision, bankroll, state):
        step = state["step"] + 1
        if state["target_profit"] is None:
            target = self.initial_stake * (decision.price - 1)
            requested = self.initial_stake
        else:
            target = state["target_profit"]
            requested = (target + state["accumulated_loss"]) / (decision.price - 1)
        if self.max_recovery_steps is not None and step > self.max_recovery_steps:
            return StakeRequest(
                requested,
                ZERO,
                reason="MAX_RECOVERY_STEPS",
                cap_hit=True,
                shortfall=requested,
                termination_reason="MAX_RECOVERY_STEPS",
                step=step,
                metadata={"target_profit": target},
            )
        cap = requested
        if self.max_stake_fraction is not None:
            cap = min(cap, self.max_stake_fraction * bankroll)
        if self.max_absolute_stake is not None:
            cap = min(cap, self.max_absolute_stake)
        cap_hit = cap < requested
        return StakeRequest(
            requested,
            cap,
            reason="CAPPED_RECOVERY_SHORTFALL" if cap_hit else "",
            cap_hit=cap_hit,
            shortfall=requested - cap,
            step=step,
            metadata={"target_profit": target},
        )


class LegacyPartialPolicy(RecoveryPolicy):
    code = LEGACY_PARTIAL

    def __init__(self, config):
        super().__init__(config)
        self.target = _decimal(
            config, "target_profit", minimum=ZERO, strict_minimum=True
        )
        self.alpha = _decimal(config, "alpha", minimum=ZERO, maximum=Decimal("1"))

    def request(self, decision, bankroll, state):
        del bankroll
        step = state["step"] + 1
        requested = (self.target + self.alpha * state["accumulated_loss"]) / (
            decision.price - 1
        )
        return StakeRequest(
            requested,
            requested,
            step=step,
            metadata={"target_profit": self.target},
        )


class FractionalKellyPolicy(CapitalPolicy):
    code = FRACTIONAL_KELLY
    requires_probability = True

    def __init__(self, config):
        super().__init__(config)
        self.lambda_fraction = _decimal(
            config, "lambda", minimum=ZERO, maximum=Decimal("1"), strict_minimum=True
        )

    def request(self, decision, bankroll, state):
        del state
        edge = decision.probability * decision.price - 1
        if edge <= 0:
            return StakeRequest(ZERO, ZERO, reason="NO_POSITIVE_KELLY_EDGE")
        full_kelly = edge / (decision.price - 1)
        stake = self.lambda_fraction * full_kelly * bankroll
        return StakeRequest(stake, stake)


POLICY_CLASSES = {
    FLAT_UNIT: FlatUnitPolicy,
    FIXED_FRACTION_BANKROLL: FixedFractionPolicy,
    FIXED_TARGET_PROFIT_NO_RECOVERY: FixedTargetPolicy,
    LEGACY_RECOVERY: LegacyRecoveryPolicy,
    LEGACY_CAPPED: LegacyCappedPolicy,
    LEGACY_PARTIAL: LegacyPartialPolicy,
    FRACTIONAL_KELLY: FractionalKellyPolicy,
}


def make_policy(code, config):
    try:
        policy_class = POLICY_CLASSES[code]
    except KeyError as error:
        raise PolicyConfigError(f"UNKNOWN_CAPITAL_POLICY:{code}") from error
    return policy_class(config)
