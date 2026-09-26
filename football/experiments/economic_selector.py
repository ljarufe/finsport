"""Pure, versioned, simulation-only FS-021 economic selection."""

from decimal import Decimal

import numpy as np

from .integrated_inputs import require

METHOD_VERSION = "FS021_SINGLE_ECONOMIC_SELECTOR_V1"
INPUT_VERSION = "ECONOMIC_SELECTOR_INPUT_V1"
LAGS = (120, 130, 150)
BLOCKS = (1, 2, 4)
TOLERANCE = 1e-12


def selector_contract():
    """Explicit formula identity for auditable, independently versioned reports.

    The publication manifest also hashes this module's actual source bytes;
    changing executable rules requires a new approved method version.
    """
    return dict(
        method_version=METHOD_VERSION,
        input_version=INPUT_VERSION,
        observed_lags=list(LAGS),
        bootstrap_lengths=list(BLOCKS),
        benchmark_effective_annual="0.07",
        horizon_weeks=36,
        year_weeks=52,
        tail_fraction="0.05",
        cvar="mean_of_lowest_floor_5_percent_float64",
        bootstrap_median="numpy_median_float64_strictly_positive",
        minimum_activity=dict(placements=38, competitions=3, weeks=4),
        tier_priority="benchmark_then_clean_activity_bootstrap_then_positive_fallback",
        pareto_directions=dict(R="MAX", D="MIN", L="MIN"),
        robust_threshold="min_leave_one_out_median_of_frontier",
        fallback_scale="max(linear_IQR,MAD,1e-12)",
        risk_tolerance=TOLERANCE,
        winner_tiebreaks=["R_DESC", "L_ASC", "D_ASC", "PLACEMENTS_DESC", "INDEX_ASC"],
        no_positive_states=[
            "BREAKEVEN_SIMULATION_ONLY",
            "DIAGNOSTIC_ONLY__NO_NEW_STAKES",
        ],
        high_risk_warning=dict(drawdown_gte="0.5", tail_loss_gte="0.95"),
        operational_activation=False,
    )


def _median(values):
    return float(np.median(np.asarray(values, dtype=np.float64)))


def _threshold(values):
    if len(values) == 1:
        return values[0]
    return min(_median(values[:j] + values[j + 1 :]) for j in range(len(values)))


def _scale(values):
    q = np.percentile(values, [25, 75], method="linear")
    return max(
        float(q[1] - q[0]),
        _median([abs(v - _median(values)) for v in values]),
        TOLERANCE,
    )


def select_economic_baseline(payload):
    """Choose exactly one canonical candidate; never authorize operational routing."""
    require(payload["schema"] == INPUT_VERSION, "ECONOMIC_INPUT_VERSION")
    observed, scores, candidates = (
        payload["observed"],
        payload["scores"],
        payload["candidates"],
    )
    n = len(candidates)
    require(
        n > 0 and [c["integrated_index"] for c in candidates] == list(range(n)),
        "ECONOMIC_IDENTITIES",
    )
    require(
        set(observed) == {str(lag) for lag in LAGS}
        and all(len(observed[str(lag)]) == n for lag in LAGS),
        "ECONOMIC_OBSERVED",
    )
    require(set(scores) == {str(b) for b in BLOCKS}, "ECONOMIC_SCORES")
    matrices = {}
    for block in BLOCKS:
        matrix = np.asarray(scores[str(block)], dtype=np.float64)
        require(
            matrix.ndim == 2
            and matrix.shape[1] == n
            and matrix.shape[0] > 0
            and np.isfinite(matrix).all(),
            "ECONOMIC_SCORE_MATRIX",
        )
        matrices[block] = matrix
    require(len({matrices[b].shape[0] for b in BLOCKS}) == 1, "ECONOMIC_REPLICATES")
    benchmark = Decimal("1.07") ** (Decimal(36) / Decimal(52)) - 1
    rows = []
    for i in range(n):
        paths = [observed[str(lag)][i] for lag in LAGS]
        require(
            all(p["structurally_complete"] for p in paths), "ECONOMIC_PATH_INCOMPLETE"
        )
        returns = [Decimal(p["total_return"]) for p in paths]
        drawdowns = [Decimal(p["maximum_drawdown"]) for p in paths]
        tails = {}
        medians = {}
        terminal_proxy = {}
        for block, matrix in matrices.items():
            column = matrix[:, i]
            count = max(1, int(len(column) * 0.05))
            tails[str(block)] = float(
                np.mean(np.sort(column)[:count], dtype=np.float64)
            )
            medians[str(block)] = float(np.median(column))
            terminal_proxy[str(block)] = float(np.mean(column <= -0.95))
        clean_reasons, activity_reasons = [], []
        for lag, path in zip(LAGS, paths, strict=True):
            for key in (
                "ever_nonpositive_equity",
                "operational_depletion",
                "economic_ruin",
                "policy_termination",
                "termination_reason",
            ):
                if path.get(key):
                    clean_reasons.append(f"{lag}:{key}")
            if path.get("hard_risk") != "PASS":
                clean_reasons.append(f"{lag}:hard_risk")
            if path["placements"] < 38:
                activity_reasons.append(f"{lag}:PLACEMENTS_LT_38")
            if len(path["placed_competitions"]) < 3:
                activity_reasons.append(f"{lag}:COMPETITIONS_LT_3")
            if len(path["placed_weeks"]) < 4:
                activity_reasons.append(f"{lag}:WEEKS_LT_4")
        r, d, loss = min(returns), max(drawdowns), -min(tails.values())
        boot_positive = all(v > 0 for v in medians.values())
        tier = (
            1
            if r > benchmark
            and not clean_reasons
            and not activity_reasons
            and boot_positive
            else (
                2
                if r > 0
                and not clean_reasons
                and not activity_reasons
                and boot_positive
                else (
                    3
                    if r > 0 and not clean_reasons and not activity_reasons
                    else 4 if r > 0 and not clean_reasons else 5 if r > 0 else None
                )
            )
        )
        rows.append(
            dict(
                integrated_index=i,
                R=str(r),
                D=str(d),
                L=loss,
                tier=tier,
                clean_reasons=clean_reasons,
                activity_reasons=activity_reasons,
                bootstrap_medians=medians,
                bootstrap_cvar5=tails,
                terminal_equity_le_5_proxy=terminal_proxy,
                min_placements=min(p["placements"] for p in paths),
                returns_by_lag={
                    str(lag): str(v) for lag, v in zip(LAGS, returns, strict=True)
                },
                drawdowns_by_lag={
                    str(lag): str(v) for lag, v in zip(LAGS, drawdowns, strict=True)
                },
            )
        )
    positive = [r for r in rows if Decimal(r["R"]) > 0]
    frontier, survivors, thresholds, fallback = [], [], None, False
    if positive:
        tier = min(r["tier"] for r in positive)
        selected_tier = [r for r in positive if r["tier"] == tier]

        def dominates(a, b):
            weak = (
                Decimal(a["R"]) >= Decimal(b["R"])
                and Decimal(a["D"]) <= Decimal(b["D"])
                and a["L"] <= b["L"]
            )
            strict = (
                Decimal(a["R"]) > Decimal(b["R"])
                or Decimal(a["D"]) < Decimal(b["D"])
                or a["L"] < b["L"]
            )
            return weak and strict

        frontier = [
            r
            for r in selected_tier
            if not any(dominates(other, r) for other in selected_tier if other is not r)
        ]
        d_values = [float(r["D"]) for r in frontier]
        l_values = [r["L"] for r in frontier]
        thresholds = dict(D=_threshold(d_values), L=_threshold(l_values))
        survivors = [
            r
            for r in frontier
            if float(r["D"]) <= thresholds["D"] + TOLERANCE
            and r["L"] <= thresholds["L"] + TOLERANCE
        ]
        fallback = not survivors

        def preference(r):
            return (
                -Decimal(r["R"]),
                r["L"],
                Decimal(r["D"]),
                -r["min_placements"],
                r["integrated_index"],
            )

        if survivors:
            winner = min(survivors, key=preference)
        else:
            d_scale, l_scale = _scale(d_values), _scale(l_values)
            winner = min(
                frontier,
                key=lambda r: (
                    max(
                        0,
                        (float(r["D"]) - thresholds["D"]) / d_scale,
                        (r["L"] - thresholds["L"]) / l_scale,
                    ),
                    *preference(r),
                ),
            )
    else:
        tier = None
        zeros = [r for r in rows if Decimal(r["R"]) == 0]
        winner = (
            min(zeros, key=lambda r: (r["L"], Decimal(r["D"]), r["integrated_index"]))
            if zeros
            else min(
                rows,
                key=lambda r: (
                    -Decimal(r["R"]),
                    r["L"],
                    Decimal(r["D"]),
                    r["integrated_index"],
                ),
            )
        )
    warnings = []
    if fallback:
        warnings.append("ROBUST_RISK_BUDGET_FALLBACK")
    if winner["clean_reasons"]:
        warnings.extend(winner["clean_reasons"])
    if winner["activity_reasons"]:
        warnings.extend(winner["activity_reasons"])
    if Decimal(winner["D"]) >= Decimal("0.5"):
        warnings.append("OBSERVED_DRAWDOWN_GE_50_PERCENT")
    if winner["L"] >= 0.95:
        warnings.append("BOOTSTRAP_TAIL_LOSS_GE_95_PERCENT")
    mode = (
        (
            "PRACTICAL_BASELINE_SIMULATION_ONLY_HIGH_RISK"
            if warnings
            else "PRACTICAL_BASELINE_SIMULATION_ONLY"
        )
        if positive
        else (
            "BREAKEVEN_SIMULATION_ONLY"
            if Decimal(winner["R"]) == 0
            else "DIAGNOSTIC_ONLY__NO_NEW_STAKES"
        )
    )
    for row in rows:
        row["selection_reason"] = (
            "SELECTED"
            if row is winner
            else (
                "NON_POSITIVE_RETURN"
                if positive and Decimal(row["R"]) <= 0
                else (
                    "LOWER_PRIORITY_TIER"
                    if positive and row["tier"] != tier
                    else (
                        "PARETO_DOMINATED"
                        if positive and row not in frontier
                        else (
                            "ROBUST_RISK_BUDGET"
                            if positive and row not in survivors and not fallback
                            else "LOWER_SELECTION_RANK"
                        )
                    )
                )
            )
        )
    outcome = dict(
        method_version=METHOD_VERSION,
        schema="ECONOMIC_SELECTOR_RESULT_V1",
        mode=mode,
        winner=winner["integrated_index"],
        winner_candidate=candidates[winner["integrated_index"]],
        tier=tier,
        frontier=[r["integrated_index"] for r in frontier],
        survivors=[r["integrated_index"] for r in survivors],
        thresholds=thresholds,
        fallback=fallback,
        risk_warnings=warnings,
        rows=rows,
        benchmark_7pct_36_weeks=str(benchmark),
        scientific_disposition=payload["scientific_disposition"],
        selection_warning="POST_HOC_SAME_HISTORY_NOT_PROSPECTIVE_VALIDATION",
        activation=dict(automatic_operational_routing=False, real_betting=False),
    )
    if fallback:
        outcome["fallback_violations"] = dict(
            D_excess=max(0.0, float(winner["D"]) - thresholds["D"]),
            L_excess=max(0.0, winner["L"] - thresholds["L"]),
            D_normalized=max(0.0, (float(winner["D"]) - thresholds["D"]) / d_scale),
            L_normalized=max(0.0, (winner["L"] - thresholds["L"]) / l_scale),
        )
    return outcome
