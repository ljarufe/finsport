"""Validate manually frozen official MEF/SBS rates; never fetch external rates."""

from datetime import date
from decimal import Decimal, InvalidOperation


def _date(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError) as error:
        raise ValueError("FS023_BENCHMARK_DATE_INVALID") from error


def _rate(value):
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, TypeError) as error:
        raise ValueError("FS023_BENCHMARK_RATE_INVALID") from error
    if not rate.is_finite() or rate <= -1:
        raise ValueError("FS023_BENCHMARK_RATE_INVALID")
    return rate


def validate_benchmark(spec):
    if not isinstance(spec, dict) or spec.get("horizon_days") != 257:
        raise ValueError("FS023_BENCHMARK_HORIZON_INVALID")
    freeze = _date(spec.get("freeze_at"))
    primary = spec.get("primary")
    if not isinstance(primary, dict):
        raise ValueError("FS023_PRIMARY_BENCHMARK_REQUIRED")
    if primary.get("status") == "UNAVAILABLE":
        if any(
            primary.get(key)
            for key in ("annual_rate", "auction_date", "horizon_return")
        ):
            raise ValueError("FS023_UNAVAILABLE_BENCHMARK_HAS_INVENTED_RATE")
        validated_primary = {"status": "UNAVAILABLE", "source": "MEF_LETRAS_TESORO_PEN"}
    else:
        if (
            primary.get("status") != "AVAILABLE"
            or primary.get("source") != "MEF_LETRAS_TESORO_PEN"
            or primary.get("currency") != "PEN"
        ):
            raise ValueError("FS023_PRIMARY_BENCHMARK_SOURCE_INVALID")
        if primary.get("tenor_months") != 9:  # Nearest 3/6/9/12m to 257 days.
            raise ValueError("FS023_PRIMARY_BENCHMARK_TENOR_INVALID")
        if not primary.get("source_identifier") or not primary.get("source_locator"):
            raise ValueError("FS023_PRIMARY_BENCHMARK_PROVENANCE_REQUIRED")
        if _date(primary.get("auction_date")) > freeze:
            raise ValueError("FS023_BENCHMARK_AFTER_FREEZE")
        rate = _rate(primary.get("annual_rate"))
        validated_primary = dict(
            primary, horizon_return=str((1 + rate) ** (Decimal(257) / Decimal(365)) - 1)
        )
    secondary = spec.get("secondary")
    if secondary is not None:
        if not isinstance(secondary, dict) or secondary.get("status") not in {
            "AVAILABLE",
            "UNAVAILABLE",
        }:
            raise ValueError("FS023_SECONDARY_BENCHMARK_INVALID")
        if secondary["status"] == "AVAILABLE":
            if (
                secondary.get("source") != "SBS_BANKING_PEN_PERSONAL_TERM_DEPOSITS"
                or secondary.get("bucket") != "181-360"
                or not secondary.get("source_locator")
                or _date(secondary.get("observation_date")) > freeze
            ):
                raise ValueError("FS023_SECONDARY_BENCHMARK_CONTRACT_INVALID")
            _rate(secondary.get("annual_rate"))
    return {
        "horizon_days": 257,
        "freeze_at": freeze.isoformat(),
        "primary": validated_primary,
        "secondary": secondary,
    }
