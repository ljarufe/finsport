"""Frozen E2.4 stateful resampling, simultaneous inference and dispositions."""

import hashlib
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from itertools import combinations
from zoneinfo import ZoneInfo

import numpy as np

from .capital_events import run_event_path

LIMA = ZoneInfo("America/Lima")
LAGS = (120, 130, 150)
BLOCKS = (1, 2, 4)
REPLICATES = 5000
SEED = 21092026


def week_start(at):
    local = at.astimezone(LIMA)
    return (local - timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def calendar_weeks(opportunities):
    if not opportunities:
        raise ValueError("EMPTY_CAPITAL_CALENDAR")
    first = min(week_start(o.execution_at) for o in opportunities)
    last = max(week_start(o.execution_at) for o in opportunities)
    return tuple(
        first + timedelta(weeks=i) for i in range((last - first).days // 7 + 1)
    )


def block_draws(weeks, length, *, replicates=REPLICATES):
    if length not in BLOCKS or weeks < length or replicates < 2:
        raise ValueError("UNESTIMABLE_BLOCK_DESIGN")
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([SEED, length])))
    return rng.integers(
        0,
        weeks - length + 1,
        size=(replicates, (weeks + length - 1) // length),
        dtype=np.int64,
    )


def array_hash(array):
    """Explicit little-endian bytes, independent of host byte order."""
    return hashlib.sha256(
        np.asarray(array, dtype=array.dtype.newbyteorder("<")).tobytes(order="C")
    ).hexdigest()


def sampled_path(opportunities, weeks, starts, length):
    """Translate whole weeks; retain T-30 offsets and settle across block seams.

    Moving blocks are non-circular. Concatenate then truncate to W weeks. The
    runner starts once, so neither bankroll nor recovery state resets at seams.
    """
    buckets = {week: [] for week in weeks}
    for opportunity in opportunities:
        buckets[week_start(opportunity.execution_at)].append(opportunity)
    source_weeks = [
        int(start) + offset for start in starts for offset in range(length)
    ][: len(weeks)]
    result = []
    for destination, source in enumerate(source_weeks):
        shift = weeks[destination] - weeks[source]
        for opportunity in buckets[weeks[source]]:
            result.append(
                replace(
                    opportunity,
                    identity=f"{destination:06d}:{opportunity.identity}",
                    execution_at=opportunity.execution_at + shift,
                    kickoff=opportunity.kickoff + shift,
                )
            )
    return tuple(result)


def bootstrap_scores(
    opportunities, candidates, lag, length, start, stop, *, replicates=REPLICATES
):
    """Shard by absolute replicate index, never by slices of a stateful path."""
    weeks = calendar_weeks(opportunities)
    draws = block_draws(len(weeks), length, replicates=replicates)
    if not 0 <= start < stop <= replicates:
        raise ValueError("INVALID_REPLICATE_SHARD")
    scores = np.empty((len(candidates), stop - start), dtype=np.float64)
    for column, index in enumerate(range(start, stop)):
        replay = sampled_path(opportunities, weeks, draws[index], length)
        for row, candidate in enumerate(candidates):
            result = run_event_path(replay, candidate, lag)
            if not result["metrics"]["structurally_complete"]:
                raise ValueError("INCOMPLETE_BOOTSTRAP_PATH")
            scores[row, column] = float(result["metrics"]["total_return"])
    if not np.isfinite(scores).all():
        raise ValueError("NON_FINITE_BOOTSTRAP_SCORE")
    return scores


def paired_max_t(observed, scores):
    observed = np.asarray(observed, dtype=np.float64)
    scores = np.asarray(scores, dtype=np.float64)
    if (
        scores.ndim != 2
        or scores.shape[0] != len(observed)
        or len(observed) < 2
        or scores.shape[1] < 2
        or not np.isfinite(observed).all()
        or not np.isfinite(scores).all()
    ):
        raise ValueError("UNESTIMABLE_ALL_PAIRS")
    maximum = np.zeros(scores.shape[1], dtype=np.float64)
    pairs = []
    positive = False
    # Only one replicate vector per pair. Never allocate pair x replicate.
    for i, j in combinations(range(len(observed)), 2):
        delta = scores[i] - scores[j]
        d = observed[i] - observed[j]
        se = np.std(delta, ddof=1)
        if not np.isfinite(se):
            raise ValueError("NON_FINITE_PAIR_SE")
        zero = se == 0.0
        if not zero:
            positive = True
            maximum = np.maximum(maximum, np.abs(delta - d) / se)
        pairs.append(
            dict(
                i=i, j=j, delta=float(d), se=float(se), deterministic_se_zero=bool(zero)
            )
        )
    q = float(np.quantile(maximum, 0.95, method="linear")) if positive else 0.0
    if not np.isfinite(q):
        raise ValueError("NON_FINITE_MAX_T")
    for pair in pairs:
        width = q * pair["se"]
        pair.update(lower=pair["delta"] - width, upper=pair["delta"] + width)
    return dict(
        status="ESTIMABLE" if positive else "DEGENERATE_ALL_SE_ZERO", q95=q, pairs=pairs
    )


def interval(family, top, other):
    if top == other:
        return (0.0, 0.0)
    i, j = sorted((top, other))
    pair = next(p for p in family["pairs"] if (p["i"], p["j"]) == (i, j))
    return (
        (pair["lower"], pair["upper"])
        if top < other
        else (-pair["upper"], -pair["lower"])
    )


def observed_order(metrics):
    return sorted(
        range(len(metrics)), key=lambda i: (-Decimal(metrics[i]["total_return"]), i)
    )


def stability_checks(opportunities, candidates, lag, top, runner_up):
    weeks = calendar_weeks(opportunities)
    midpoint = len(weeks) // 2
    halves = (set(weeks[:midpoint]), set(weeks[midpoint:]))
    slices = [
        (
            f"H{i+1}",
            tuple(o for o in opportunities if week_start(o.execution_at) in half),
        )
        for i, half in enumerate(halves)
    ]
    slices += [
        (
            f"WITHOUT:{competition}",
            tuple(o for o in opportunities if o.competition_id != competition),
        )
        for competition in sorted({o.competition_id for o in opportunities})
    ]
    results = []
    for name, subset in slices:
        if not subset:
            results.append(dict(slice=name, status="NOT_ESTIMABLE", count=0))
            continue
        paths = [
            run_event_path(subset, candidates[i], lag)["metrics"]
            for i in (top, runner_up)
        ]
        delta = Decimal(paths[0]["total_return"]) - Decimal(paths[1]["total_return"])
        results.append(
            dict(
                slice=name,
                count=len(subset),
                delta=str(delta),
                scores=[p["total_return"] for p in paths],
                status=(
                    "UNSTABLE" if delta < 0 else "NON_STRICT" if delta == 0 else "PASS"
                ),
            )
        )
    statuses = {row["status"] for row in results}
    status = next(
        (s for s in ("NOT_ESTIMABLE", "UNSTABLE", "NON_STRICT") if s in statuses),
        "PASS",
    )
    return dict(status=status, top=top, runner_up=runner_up, slices=results)


def within_lag(candidates, metrics, families, stability):
    order = observed_order(metrics)
    top, second = order[:2]
    codes = [c.code for c in candidates]
    risk = {c.code: m["hard_risk"] for c, m in zip(candidates, metrics, strict=True)}
    structural = (
        all(m["structurally_complete"] for m in metrics)
        and stability["status"] != "NOT_ESTIMABLE"
        and set(families) == {"1", "2", "4"}
        and all(f["status"] == "ESTIMABLE" for f in families.values())
    )
    strict = {
        length: all(
            interval(family, top, i)[0] > 0 for i in range(len(candidates)) if i != top
        )
        for length, family in families.items()
    }
    unique = Decimal(metrics[top]["total_return"]) > Decimal(
        metrics[second]["total_return"]
    )
    if not structural:
        disposition = "INSUFFICIENT_EVIDENCE"
    elif stability["status"] == "UNSTABLE":
        disposition = "UNSTABLE"
    elif unique and stability["status"] == "PASS" and all(strict.values()):
        disposition = "CLEAR_SUPERIORITY"
    else:
        disposition = "NO_CLEAR_SUPERIORITY"
    fallback, promotion = "NOT_APPLICABLE", "NO_PROMOTION"
    if disposition == "CLEAR_SUPERIORITY":
        promotion = (
            f"PROMOTE:{codes[top]}"
            if risk[codes[top]] == "PASS"
            else "NO_PROMOTION_RISK_GATE"
        )
    elif disposition == "NO_CLEAR_SUPERIORITY":
        flat = codes.index("FLAT_UNIT")
        eligible = (
            metrics[flat]["structurally_complete"]
            and risk["FLAT_UNIT"] == "PASS"
            and (top == flat or interval(families["2"], top, flat)[0] <= 0)
        )
        fallback = "FLAT_UNIT" if eligible else "NO_PROMOTION"
        if eligible:
            promotion = "PROMOTE:FLAT_UNIT"
    return dict(
        observed_leader=codes[top],
        observed_runner_up=codes[second],
        unique_leader=unique,
        structural_gate="PASS" if structural else "FAIL",
        disposition=disposition,
        fallback=fallback,
        promotion=promotion,
        hard_risk=risk,
        strict_top_vs_all=strict,
        stability=stability,
        families=families,
        observed=dict(zip(codes, metrics, strict=True)),
    )


def finalize_lags(lags):
    """Independent local results in; exactly seven signature fields out."""
    result = dict(
        settlement_time_stability="NOT_ESTIMABLE",
        disposition="INSUFFICIENT_EVIDENCE",
        promotion="NO_PROMOTION",
        selected=None,
        signatures={},
    )
    primary = lags.get("150", {}).get("observed_leader")
    signatures = {}
    if primary is not None:
        for key, lag in lags.items():
            if "observed_leader" in lag:
                signatures[key] = [
                    lag["observed_leader"],
                    lag["disposition"],
                    lag["promotion"],
                    lag["hard_risk"][lag["observed_leader"]],
                    lag["hard_risk"][primary],
                    lag["hard_risk"]["FLAT_UNIT"],
                    lag["fallback"],
                ]
    result["signatures"] = signatures
    if set(lags) != {"120", "130", "150"} or any(
        lag["disposition"] == "INSUFFICIENT_EVIDENCE" for lag in lags.values()
    ):
        return result
    if any(signatures[key] != signatures["150"] for key in ("120", "130")):
        result.update(settlement_time_stability="UNSTABLE", disposition="UNSTABLE")
        return result
    promotion = lags["150"]["promotion"]
    result.update(
        settlement_time_stability="PASS",
        disposition=lags["150"]["disposition"],
        promotion="PROMOTE" if promotion.startswith("PROMOTE:") else promotion,
        selected=(
            promotion.split(":", 1)[1] if promotion.startswith("PROMOTE:") else None
        ),
    )
    return result
