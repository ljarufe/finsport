import numpy as np

from .contracts import CapitalInputError


def stress_parameters(config):
    probability_delta = float(config.get("probability_delta", 0.0))
    price_haircut = float(config.get("price_haircut", 0.0))
    forced_loss_start = int(config.get("forced_loss_start", 0))
    forced_loss_length = int(config.get("forced_loss_length", 0))
    if not 0 <= probability_delta <= 1:
        raise CapitalInputError("probability_delta must be between zero and one")
    if not 0 <= price_haircut < 1:
        raise CapitalInputError("price_haircut must be at least zero and below one")
    if forced_loss_start < 0 or forced_loss_length < 0:
        raise CapitalInputError("forced loss positions must be non-negative")
    return {
        "probability_delta": probability_delta,
        "price_haircut": price_haircut,
        "forced_loss_start": forced_loss_start,
        "forced_loss_length": forced_loss_length,
    }


def deteriorate_probability(probability, delta):
    return float(np.clip(probability - delta, 0.0, 1.0))


def deteriorate_price(price, haircut):
    return 1.0 + (price - 1.0) * (1.0 - haircut)


def is_forced_loss(action_index, *, start, length):
    return start <= action_index < start + length
