"""Independent practical selection and conditional T+150 scientific inference."""

from decimal import Decimal

import numpy as np

from .capital_analysis import interval, paired_max_t
from .integrated_inputs import require


def practical_selection(observed, matrix):
    require(
        set(observed) == {"120", "130", "150"} and len(matrix) == 231,
        "SELECTION_FAMILY",
    )
    require(all(len(v) == 231 for v in observed.values()), "SELECTION_CARDINALITY")
    ranking = []
    for i in range(231):
        paths = [observed[str(lag)][i] for lag in (120, 130, 150)]
        require(
            all(p["structurally_complete"] and p["input_count"] == 1877 for p in paths),
            "SELECTION_GATE_A",
        )
        reasons = []
        for lag, p in zip((120, 130, 150), paths, strict=True):
            for key in (
                "ever_nonpositive_equity",
                "policy_termination",
                "operational_depletion",
            ):
                if p[key]:
                    reasons.append(f"{lag}:{key}")
            if p["placements"] < 38:
                reasons.append(f"{lag}:PLACEMENTS_LT_38")
            if len(p["placed_competitions"]) < 3:
                reasons.append(f"{lag}:COMPETITIONS_LT_3")
            if len(p["placed_weeks"]) < 4:
                reasons.append(f"{lag}:WEEKS_LT_4")
        ranking.append(
            dict(
                integrated_index=i,
                eligible=not reasons,
                reasons=reasons,
                min_return=str(min(Decimal(p["total_return"]) for p in paths)),
                return150=paths[2]["total_return"],
                worst_drawdown=str(max(Decimal(p["maximum_drawdown"]) for p in paths)),
                min_placed=min(p["placements"] for p in paths),
                worst_exposure=str(
                    max(Decimal(p["peak_reserved_exposure"]) for p in paths)
                ),
            )
        )
    ranking.sort(
        key=lambda r: (
            -Decimal(r["min_return"]),
            -Decimal(r["return150"]),
            Decimal(r["worst_drawdown"]),
            -r["min_placed"],
            Decimal(r["worst_exposure"]),
            r["integrated_index"],
        )
    )
    eligible = [r for r in ranking if r["eligible"]]
    selected = (eligible or ranking)[0]
    return dict(
        mode=(
            "PRACTICAL_BASELINE_SIMULATION_ONLY"
            if eligible
            else "DIAGNOSTIC_ONLY__NO_NEW_STAKES"
        ),
        selected=matrix[selected["integrated_index"]],
        ranking=ranking,
        historical_loss_making=Decimal(selected["min_return"]) < 0,
    )


def scientific_evidence(observed, scores, slices):
    require(
        len(observed) == 231 and set(scores) == {"1", "2", "4"}, "SCIENTIFIC_FAMILY"
    )
    require(
        len(slices) == 12 and all(len(s["scores"]) == 231 for s in slices),
        "SCIENTIFIC_SLICES",
    )
    order = sorted(range(231), key=lambda i: (-Decimal(observed[i]["total_return"]), i))
    top = order[0]
    point = [float(p["total_return"]) for p in observed]
    families, strict = {}, {}
    for length in (2, 1, 4):
        matrix = np.asarray(scores[str(length)], dtype=np.float64)
        require(
            matrix.shape == (5000, 231) and np.isfinite(matrix).all(), "SCORE_MATRIX"
        )
        family = paired_max_t(point, matrix.T)
        families[str(length)] = family
        strict[str(length)] = family["status"] == "ESTIMABLE" and all(
            interval(family, top, i)[0] > 0 for i in range(231) if i != top
        )
    stability = []
    for s in slices:
        delta = min(
            Decimal(s["scores"][top]) - Decimal(s["scores"][i])
            for i in range(231)
            if i != top
        )
        stability.append(
            dict(
                slice=s["slice"],
                status=(
                    "UNSTABLE" if delta < 0 else "NON_STRICT" if delta == 0 else "PASS"
                ),
                minimum_delta=str(delta),
            )
        )
    unique = Decimal(observed[top]["total_return"]) > Decimal(
        observed[order[1]]["total_return"]
    )
    if any(f["status"] != "ESTIMABLE" for f in families.values()):
        disposition = "INSUFFICIENT_EVIDENCE"
    elif any(s["status"] == "UNSTABLE" for s in stability):
        disposition = "UNSTABLE"
    elif (
        unique
        and all(s["status"] == "PASS" for s in stability)
        and all(strict.values())
    ):
        disposition = "CLEAR_SUPERIORITY_150M_CONDITIONAL"
    else:
        disposition = "NO_CLEAR_SUPERIORITY"
    return dict(
        observed_leader=top,
        unique_leader=unique,
        disposition=disposition,
        stability=stability,
        strict_top_vs_all=strict,
        families=families,
        CROSS_LAG_INFERENCE="NOT_EVALUATED_BY_FS021_V1",
    )
