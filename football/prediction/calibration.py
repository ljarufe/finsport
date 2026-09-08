"""DB-only season-block calibration promoted from reviewed FS-012 Phase A v2.

All development seasons supply expanding folds; four whole-day blocks per
validation season and outer season. Only development chooses config and gates.
No file cache, provider client, scheduler or persistence belongs to this module.
Unexpected model exceptions propagate to the operational lifecycle owner.
"""

import hashlib
import json
import math
from collections import Counter, defaultdict

import numpy as np
from sklearn.metrics import log_loss

from football.models import Match
from football.sync import FINISHED_STATUSES

from .constants import (
    ELO_K_GRID,
    ELO_MULTINOMIAL_LOGIT_VERSION,
    INDEPENDENT_POISSON_VERSION,
    LOGISTIC_C_GRID,
    OUTCOMES,
    XI_GRID,
)
from .contracts import FailedPrediction, UnavailablePrediction
from .datasets import local_day
from .elo import EloMultinomialAdapter
from .goal_models import IndependentPoissonAdapter

STRATEGY_VERSION = "fs012-phase-a-season-block-v2"
PROFILE_RULE_VERSION = "fs012-readiness-v1"
POISSON = "INDEPENDENT_POISSON"
ELO = "ELO_MULTINOMIAL_LOGIT"


def stable_json(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )


def season_matches(season):
    return list(
        Match.objects.filter(
            season=season,
            status_short__in=FINISHED_STATUSES,
            outcome__in=OUTCOMES,
            home_score__isnull=False,
            away_score__isnull=False,
        )
        .select_related("season", "home_team", "away_team")
        .order_by("kickoff", "id")
    )


def load_competition(competition):
    """
    Use only the canonical FS-011 completed-history window.

    Competition.seasons may contain older catalogued completed seasons that
    intentionally sit outside the source-supported HistoricalCoverage window.
    Phase A must calibrate from the current required/covered canonical window,
    not treat those catalogue-only seasons as missing evidence.
    """
    coverage = competition.historical_coverage
    required_years = sorted({int(year) for year in coverage.required_seasons or []})
    covered_years = sorted({int(year) for year in coverage.covered_seasons or []})
    if not required_years:
        raise RuntimeError(
            f"EMPTY_CANONICAL_HISTORICAL_WINDOW competition={competition.pk}"
        )
    if covered_years != required_years:
        raise RuntimeError(
            f"CANONICAL_HISTORICAL_WINDOW_NOT_FULLY_COVERED competition={competition.pk} required={required_years} covered={covered_years}"
        )
    seasons = list(
        competition.seasons.filter(is_current=False, year__in=required_years).order_by(
            "year", "id"
        )
    )
    actual_years = [season.year for season in seasons]
    if actual_years != required_years:
        raise RuntimeError(
            f"CANONICAL_SEASON_ROWS_MISSING competition={competition.pk} required={required_years} actual={actual_years}"
        )
    by_year = {season.year: season_matches(season) for season in seasons}
    return (seasons, by_year)


def sporting_basis_hash(competition, seasons, by_year):
    digest = hashlib.sha256()
    digest.update(
        stable_json(
            {
                "competition_id": competition.pk,
                "strategy": STRATEGY_VERSION,
                "seasons": [season.year for season in seasons],
            }
        ).encode()
    )
    for season in seasons:
        for match in by_year[season.year]:
            digest.update(
                stable_json(
                    {
                        "match": match.pk,
                        "season": season.year,
                        "kickoff": match.kickoff.isoformat(),
                        "home": match.home_team_id,
                        "away": match.away_team_id,
                        "home_score": match.home_score,
                        "away_score": match.away_score,
                        "outcome": match.outcome,
                    }
                ).encode()
            )
    return digest.hexdigest()


def team_counts(history):
    counts = Counter()
    for match in history:
        counts[match.home_team_id] += 1
        counts[match.away_team_id] += 1
    return counts


def graph_connected(history):
    graph = defaultdict(set)
    for match in history:
        home = match.home_team_id
        away = match.away_team_id
        graph[home].add(away)
        graph[away].add(home)
    if not graph:
        return False
    start = next(iter(graph))
    seen = {start}
    pending = [start]
    while pending:
        node = pending.pop()
        for neighbor in graph[node]:
            if neighbor not in seen:
                seen.add(neighbor)
                pending.append(neighbor)
    return len(seen) == len(graph)


def class_counts(history):
    counts = Counter((match.outcome for match in history))
    return {
        "HOME": counts.get("HOME", 0),
        "DRAW": counts.get("DRAW", 0),
        "AWAY": counts.get("AWAY", 0),
    }


def make_adapter(model, config):
    if model == POISSON:
        return IndependentPoissonAdapter(xi=float(config["xi"]))
    return EloMultinomialAdapter(k=int(config["k"]), c=float(config["C"]))


def complete_adapter_config(model, config):
    return make_adapter(model, config).config


def model_version(model):
    if model == POISSON:
        return INDEPENDENT_POISSON_VERSION
    return ELO_MULTINOMIAL_LOGIT_VERSION


def produced(rows):
    return [row for row in rows if row["status"] == "PRODUCED"]


def reliability(actual, probabilities, bins=10):
    result = {}
    for class_index, outcome in enumerate(OUTCOMES):
        entries = []
        for bin_index in range(bins):
            lower = bin_index / bins
            upper = (bin_index + 1) / bins
            indexes = []
            for index, vector in enumerate(probabilities):
                p = vector[class_index]
                if lower <= p < upper or (bin_index == bins - 1 and p == 1.0):
                    indexes.append(index)
            if not indexes:
                continue
            mean_probability = float(
                np.mean([probabilities[index][class_index] for index in indexes])
            )
            observed_rate = float(
                np.mean([actual[index] == outcome for index in indexes])
            )
            entries.append(
                {
                    "lower": lower,
                    "upper": upper,
                    "count": len(indexes),
                    "mean_probability": mean_probability,
                    "observed_rate": observed_rate,
                }
            )
        result[outcome] = entries
    return result


def calibration_ece(actual, probabilities, bins=10):
    if not actual:
        return None
    per_class = []
    for class_index, outcome in enumerate(OUTCOMES):
        error = 0.0
        for bin_index in range(bins):
            lower = bin_index / bins
            upper = (bin_index + 1) / bins
            indexes = []
            for index, vector in enumerate(probabilities):
                p = vector[class_index]
                if lower <= p < upper or (bin_index == bins - 1 and p == 1.0):
                    indexes.append(index)
            if not indexes:
                continue
            predicted = float(
                np.mean([probabilities[index][class_index] for index in indexes])
            )
            observed = float(np.mean([actual[index] == outcome for index in indexes]))
            error += len(indexes) / len(actual) * abs(predicted - observed)
        per_class.append(error)
    return float(np.mean(per_class))


def multiclass_brier(actual, probabilities):
    values = []
    for outcome, vector in zip(actual, probabilities, strict=True):
        expected = [1.0 if candidate == outcome else 0.0 for candidate in OUTCOMES]
        values.append(
            sum(((p - y) ** 2 for p, y in zip(vector, expected, strict=True)))
        )
    return float(np.mean(values))


def rps(actual, probabilities):
    values = []
    for outcome, vector in zip(actual, probabilities, strict=True):
        expected = [1.0 if candidate == outcome else 0.0 for candidate in OUTCOMES]
        predicted_cumulative = np.cumsum(vector)[:-1]
        actual_cumulative = np.cumsum(expected)[:-1]
        values.append(float(np.sum((predicted_cumulative - actual_cumulative) ** 2)))
    return float(np.mean(values))


def metrics(rows):
    valid = produced(rows)
    result = {
        "eligible_targets": len(rows),
        "produced": len(valid),
        "unavailable": sum((row["status"] == "UNAVAILABLE" for row in rows)),
        "failed": sum((row["status"] == "FAILED" for row in rows)),
        "coverage": len(valid) / len(rows) if rows else 0.0,
        "log_loss": None,
        "multiclass_brier": None,
        "calibration_ece": None,
        "rps": None,
        "accuracy": None,
        "calibration_json": "{}",
    }
    if not valid:
        return result
    actual = [row["actual"] for row in valid]
    probabilities = [[row["p_home"], row["p_draw"], row["p_away"]] for row in valid]
    encoded = [OUTCOMES.index(value) for value in actual]
    predictions = [OUTCOMES[int(np.argmax(vector))] for vector in probabilities]
    result.update(
        {
            "log_loss": float(log_loss(encoded, probabilities, labels=[0, 1, 2])),
            "multiclass_brier": multiclass_brier(actual, probabilities),
            "calibration_ece": calibration_ece(actual, probabilities),
            "rps": rps(actual, probabilities),
            "accuracy": float(
                np.mean(
                    [
                        predicted == observed
                        for predicted, observed in zip(predictions, actual, strict=True)
                    ]
                )
            ),
            "calibration_json": stable_json(reliability(actual, probabilities)),
        }
    )
    return result


def finite_loss(result):
    return result["log_loss"] is not None and math.isfinite(result["log_loss"])


def evaluate_block(competition, model, config, training, targets, *, phase, fold):
    targets = sorted(targets, key=lambda match: (match.kickoff, match.pk))
    if not targets:
        return []
    cutoff = targets[0].kickoff
    training = [
        match for match in training if local_day(match.kickoff) < local_day(cutoff)
    ]
    adapter = make_adapter(model, config)
    counts = team_counts(training)
    classes = class_counts(training)
    connected = graph_connected(training)
    fit_status = "PRODUCED"
    fit_reason = ""
    fitted = adapter.fit(training, cutoff)
    if isinstance(fitted, UnavailablePrediction):
        fit_status = "UNAVAILABLE"
        fit_reason = fitted.reason
    elif isinstance(fitted, FailedPrediction):
        raise RuntimeError(f"Calibration model fit failed: {fitted.reason}")
    rows = []
    for match in targets:
        home_history = counts[match.home_team_id]
        away_history = counts[match.away_team_id]
        row = {
            "model": model,
            "competition_id": competition.pk,
            "country": str(competition.country),
            "competition": competition.name,
            "phase": phase,
            "fold": fold,
            "season_year": match.season.year,
            "match_id": match.pk,
            "kickoff": match.kickoff.isoformat(),
            "home_team_id": match.home_team_id,
            "away_team_id": match.away_team_id,
            "actual": match.outcome,
            "training_matches": len(training),
            "home_team_history": home_history,
            "away_team_history": away_history,
            "team_history_min": min(home_history, away_history),
            "status": fit_status,
            "reason": fit_reason,
            "p_home": None,
            "p_draw": None,
            "p_away": None,
            "readiness_pass": None,
            "config_json": stable_json(config),
        }
        if model == POISSON:
            row.update({"xi": config["xi"], "history_connected": connected})
        else:
            row.update(
                {
                    "k": config["k"],
                    "C": config["C"],
                    "class_home": classes["HOME"],
                    "class_draw": classes["DRAW"],
                    "class_away": classes["AWAY"],
                    "class_support_min": min(classes.values()),
                    "home_pre_rating": None,
                    "away_pre_rating": None,
                    "home_rating_distance_1500": None,
                    "away_rating_distance_1500": None,
                }
            )
        if fit_status != "PRODUCED":
            rows.append(row)
            continue
        if model == ELO:
            home_rating = float(adapter.elo.get_team_rating(str(match.home_team_id)))
            away_rating = float(adapter.elo.get_team_rating(str(match.away_team_id)))
            row.update(
                {
                    "home_pre_rating": home_rating,
                    "away_pre_rating": away_rating,
                    "home_rating_distance_1500": abs(home_rating - 1500.0),
                    "away_rating_distance_1500": abs(away_rating - 1500.0),
                }
            )
        result = adapter.predict(match, match.kickoff)
        if isinstance(result, UnavailablePrediction):
            row["status"] = "UNAVAILABLE"
            row["reason"] = result.reason
        elif isinstance(result, FailedPrediction):
            raise RuntimeError(f"Calibration prediction failed: {result.reason}")
        else:
            probabilities = tuple((float(value) for value in result.as_tuple()))
            if len(probabilities) != 3 or not all(
                (math.isfinite(value) for value in probabilities)
            ):
                row["status"] = "FAILED"
                row["reason"] = "NON_FINITE_PROBABILITY_OUTPUT"
            else:
                row["p_home"], row["p_draw"], row["p_away"] = probabilities
        rows.append(row)
    return rows


def inner_fold_specs(development):
    if len(development) < 2:
        raise RuntimeError(
            "Need >= 2 development seasons for chronological expanding validation."
        )
    return tuple(
        (
            (f"INNER_{development[index].year}", index)
            for index in range(1, len(development))
        )
    )


def flatten_seasons(seasons, by_year):
    rows = []
    for season in seasons:
        rows.extend(by_year[season.year])
    return rows


def inner_candidate(competition, model, config, development, by_year):
    all_rows = []
    fold_metrics = {}
    for fold_name, validation_index in inner_fold_specs(development):
        history = flatten_seasons(development[:validation_index], by_year)
        validation = by_year[development[validation_index].year]
        blocks = split_outer_days(validation, blocks=4)
        fold_rows = []
        for block_index, block in enumerate(blocks, start=1):
            rows = evaluate_block(
                competition,
                model,
                config,
                history,
                block,
                phase="DEVELOPMENT",
                fold=fold_name,
            )
            fold_rows.extend(rows)
            history.extend(block)
        all_rows.extend(fold_rows)
        fold_metrics[fold_name] = metrics(fold_rows)
    aggregate = metrics(all_rows)
    valid = (
        aggregate["failed"] == 0
        and finite_loss(aggregate)
        and all(
            (
                result["failed"] == 0 and finite_loss(result)
                for result in fold_metrics.values()
            )
        )
    )
    return {
        "config": config,
        "valid": valid,
        "rows": all_rows,
        "aggregate": aggregate,
        "fold_metrics": fold_metrics,
    }


def candidate_grid(model):
    if model == POISSON:
        return [{"xi": float(xi)} for xi in XI_GRID]
    return [{"k": int(k), "C": float(c)} for k in ELO_K_GRID for c in LOGISTIC_C_GRID]


def select_hyperparameters(competition, model, development, by_year, metric_rows):
    candidates = []
    for config in candidate_grid(model):
        candidate = inner_candidate(competition, model, config, development, by_year)
        candidates.append(candidate)
        for fold, result in candidate["fold_metrics"].items():
            metric_rows.append(
                {
                    "model": model,
                    "competition_id": competition.pk,
                    "country": str(competition.country),
                    "competition": competition.name,
                    "stage": "HYPERPARAMETER_SELECTION",
                    "phase": "DEVELOPMENT",
                    "fold": fold,
                    "candidate_config": stable_json(config),
                    "group": "ALL",
                    **result,
                    "candidate_valid": candidate["valid"],
                }
            )
        metric_rows.append(
            {
                "model": model,
                "competition_id": competition.pk,
                "country": str(competition.country),
                "competition": competition.name,
                "stage": "HYPERPARAMETER_SELECTION",
                "phase": "DEVELOPMENT",
                "fold": "AGGREGATE",
                "candidate_config": stable_json(config),
                "group": "ALL",
                **candidate["aggregate"],
                "candidate_valid": candidate["valid"],
            }
        )
    valid = [candidate for candidate in candidates if candidate["valid"]]
    if not valid:
        return (None, candidates)
    if model == POISSON:
        winner = min(
            valid,
            key=lambda item: (item["aggregate"]["log_loss"], item["config"]["xi"]),
        )
    else:
        winner = min(
            valid,
            key=lambda item: (
                item["aggregate"]["log_loss"],
                item["config"]["k"],
                item["config"]["C"],
            ),
        )
    return (winner, candidates)


def split_outer_days(matches, blocks=3):
    grouped = defaultdict(list)
    for match in matches:
        grouped[local_day(match.kickoff)].append(match)
    days = sorted(grouped)
    if len(days) < blocks:
        return [[match for day in days for match in grouped[day]]]
    day_blocks = np.array_split(np.array(days, dtype=object), blocks)
    result = []
    for day_block in day_blocks:
        block_matches = []
        for day in day_block.tolist():
            block_matches.extend(grouped[day])
        result.append(
            sorted(block_matches, key=lambda match: (match.kickoff, match.pk))
        )
    return [block for block in result if block]


def evaluate_outer(competition, model, config, development, outer, by_year):
    history = flatten_seasons(development, by_year)
    blocks = split_outer_days(by_year[outer.year], blocks=4)
    all_rows = []
    block_metrics = {}
    for index, block in enumerate(blocks, start=1):
        fold = f"OUTER_BLOCK_{index}"
        rows = evaluate_block(
            competition, model, config, history, block, phase="OUTER", fold=fold
        )
        all_rows.extend(rows)
        block_metrics[fold] = metrics(rows)
        history.extend(block)
    return (all_rows, block_metrics)


def quantile_thresholds(rows, dimension):
    values = sorted(
        (
            int(row[dimension])
            for row in produced(rows)
            if row.get(dimension) is not None
        )
    )
    if len(set(values)) < 2:
        return []
    thresholds = set()
    for q in (0.25, 0.5, 0.75):
        threshold = int(np.quantile(values, q, method="nearest"))
        if threshold > min(values) and threshold <= max(values):
            thresholds.add(threshold)
    return sorted(thresholds)


def split_by_gate(rows, dimension, threshold):
    valid = produced(rows)
    blocked = [row for row in valid if int(row[dimension]) < threshold]
    passed = [row for row in valid if int(row[dimension]) >= threshold]
    return (blocked, passed)


def primary_improvement(blocked_metrics, passed_metrics):
    for key in ("log_loss", "multiclass_brier", "calibration_ece"):
        blocked = blocked_metrics[key]
        passed = passed_metrics[key]
        if (
            blocked is None
            or passed is None
            or (not math.isfinite(blocked))
            or (not math.isfinite(passed))
            or (blocked <= passed)
        ):
            return False
    return True


def fold_consistency(rows, dimension, threshold):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["fold"]].append(row)
    details = []
    comparable = 0
    positive = 0
    negative = 0
    for fold, fold_rows in sorted(grouped.items()):
        blocked, passed = split_by_gate(fold_rows, dimension, threshold)
        blocked_metrics = metrics(blocked)
        passed_metrics = metrics(passed)
        if (
            not blocked
            or not passed
            or (not finite_loss(blocked_metrics))
            or (not finite_loss(passed_metrics))
        ):
            details.append({"fold": fold, "comparable": False})
            continue
        comparable += 1
        delta = blocked_metrics["log_loss"] - passed_metrics["log_loss"]
        if delta > 0:
            positive += 1
        elif delta < 0:
            negative += 1
        details.append({"fold": fold, "comparable": True, "log_loss_delta": delta})
    return {
        "fold_count": len(grouped),
        "comparable_folds": comparable,
        "positive_folds": positive,
        "negative_folds": negative,
        "details": details,
    }


def readiness_dimensions(model):
    if model == POISSON:
        return ("team_history_min", "training_matches")
    return ("team_history_min", "class_support_min")


def choose_development_gate(competition, model, rows, metric_rows):
    candidates = []
    expected_folds = len({row["fold"] for row in rows})
    for dimension in readiness_dimensions(model):
        for threshold in quantile_thresholds(rows, dimension):
            blocked, passed = split_by_gate(rows, dimension, threshold)
            if not blocked or not passed:
                continue
            blocked_metrics = metrics(blocked)
            passed_metrics = metrics(passed)
            consistency = fold_consistency(rows, dimension, threshold)
            qualifies = (
                primary_improvement(blocked_metrics, passed_metrics)
                and consistency["comparable_folds"] == expected_folds
                and (consistency["positive_folds"] == expected_folds)
                and (consistency["negative_folds"] == 0)
            )
            delta = blocked_metrics["log_loss"] - passed_metrics["log_loss"]
            candidate = {
                "dimension": dimension,
                "threshold": threshold,
                "qualifies": qualifies,
                "development_log_loss_delta": delta,
                "blocked_metrics": blocked_metrics,
                "passed_metrics": passed_metrics,
                "fold_consistency": consistency,
            }
            candidates.append(candidate)
            for group, result in (
                ("BLOCKED", blocked_metrics),
                ("PASS", passed_metrics),
            ):
                metric_rows.append(
                    {
                        "model": model,
                        "competition_id": competition.pk,
                        "country": str(competition.country),
                        "competition": competition.name,
                        "stage": "READINESS_BAND",
                        "phase": "DEVELOPMENT",
                        "fold": "AGGREGATE",
                        "dimension": dimension,
                        "threshold": threshold,
                        "group": group,
                        **result,
                        "qualifies": qualifies,
                        "comparable_folds": consistency["comparable_folds"],
                        "positive_folds": consistency["positive_folds"],
                        "negative_folds": consistency["negative_folds"],
                    }
                )
    qualified = [candidate for candidate in candidates if candidate["qualifies"]]
    if not qualified:
        return (None, candidates)
    winner = max(
        qualified,
        key=lambda item: (item["development_log_loss_delta"], -item["threshold"]),
    )
    return (winner, candidates)


def requirements_for_gate(model, gate):
    if gate is None:
        return {}
    value = int(gate["threshold"])
    if gate["dimension"] == "team_history_min":
        return {"min_home_team_matches": value, "min_away_team_matches": value}
    if gate["dimension"] == "training_matches":
        return {"min_training_matches": value}
    if model == ELO and gate["dimension"] == "class_support_min":
        return {"min_class_support": value}
    raise AssertionError(f"unsupported gate {gate}")


def validate_gate_outer(gate, outer_rows):
    if gate is None:
        return {"status": "NO_DEVELOPMENT_GATE", "supported": None}
    dimension = gate["dimension"]
    threshold = gate["threshold"]
    blocked, passed = split_by_gate(outer_rows, dimension, threshold)
    if not passed:
        return {
            "status": "NO_OUTER_PASSING_TARGETS",
            "supported": False,
            "blocked_count": len(blocked),
            "pass_count": 0,
        }
    if not blocked:
        return {
            "status": "NOT_CONTRADICTED_NO_BLOCKED_OUTER",
            "supported": True,
            "blocked_count": 0,
            "pass_count": len(passed),
        }
    blocked_metrics = metrics(blocked)
    passed_metrics = metrics(passed)
    supported = primary_improvement(blocked_metrics, passed_metrics)
    return {
        "status": "SUPPORTED" if supported else "CONTRADICTED",
        "supported": supported,
        "blocked_count": len(blocked),
        "pass_count": len(passed),
        "blocked_metrics": blocked_metrics,
        "pass_metrics": passed_metrics,
        "block_consistency": fold_consistency(outer_rows, dimension, threshold),
    }


def apply_profile(rows, requirements, usable):
    for row in rows:
        if row["status"] != "PRODUCED":
            row["readiness_pass"] = False
            continue
        if not usable:
            row["readiness_pass"] = None
            continue
        passed = True
        if (
            "min_training_matches" in requirements
            and row["training_matches"] < requirements["min_training_matches"]
        ):
            passed = False
        if (
            "min_home_team_matches" in requirements
            and row["home_team_history"] < requirements["min_home_team_matches"]
        ):
            passed = False
        if (
            "min_away_team_matches" in requirements
            and row["away_team_history"] < requirements["min_away_team_matches"]
        ):
            passed = False
        if (
            "min_class_support" in requirements
            and row.get("class_support_min", 0) < requirements["min_class_support"]
        ):
            passed = False
        row["readiness_pass"] = passed


def run_model_competition(competition, model, seasons, by_year, basis_hash):
    development = seasons[:-1]
    outer = seasons[-1]
    metric_rows = []
    winner, candidates = select_hyperparameters(
        competition, model, development, by_year, metric_rows
    )
    candidate_summary = [
        {
            "config": candidate["config"],
            "valid": candidate["valid"],
            "aggregate_metrics": candidate["aggregate"],
            "fold_metrics": candidate["fold_metrics"],
        }
        for candidate in candidates
    ]
    if winner is None:
        profile = {
            "competition_id": competition.pk,
            "country": str(competition.country),
            "competition": competition.name,
            "model_code": model,
            "model_version": model_version(model),
            "calibration_strategy_version": STRATEGY_VERSION,
            "proposed_profile_version": f"fs012-{model.lower()}-{outer.year}-v1",
            "disposition": "EVIDENCE_INSUFFICIENT_TO_DEFINE_USABLE_PROFILE",
            "selected_model_config": None,
            "requirements": {},
            "selected_development_gate": None,
            "outer_gate_validation": {
                "status": "NO_FINITE_HYPERPARAMETER_WINNER",
                "supported": False,
            },
            "development_seasons": [season.year for season in development],
            "outer_season": outer.year,
            "sporting_basis_hash": basis_hash,
            "rationale": "NO_FINITE_HYPERPARAMETER_WINNER",
            "hyperparameter_candidates": candidate_summary,
            "provenance": {
                "provider_calls": 0,
                "odds_used": False,
                "db_writes": 0,
                "outer_retuned": False,
            },
        }
        result = {"profile": profile, "target_rows": [], "metric_rows": metric_rows}
        return (result, False)
    config = winner["config"]
    development_rows = winner["rows"]
    outer_rows, outer_block_metrics = evaluate_outer(
        competition, model, config, development, outer, by_year
    )
    development_metrics = metrics(development_rows)
    outer_metrics = metrics(outer_rows)
    for fold, result in outer_block_metrics.items():
        metric_rows.append(
            {
                "model": model,
                "competition_id": competition.pk,
                "country": str(competition.country),
                "competition": competition.name,
                "stage": "OUTER_VALIDATION",
                "phase": "OUTER",
                "fold": fold,
                "candidate_config": stable_json(config),
                "group": "ALL",
                **result,
            }
        )
    metric_rows.append(
        {
            "model": model,
            "competition_id": competition.pk,
            "country": str(competition.country),
            "competition": competition.name,
            "stage": "OUTER_VALIDATION",
            "phase": "OUTER",
            "fold": "AGGREGATE",
            "candidate_config": stable_json(config),
            "group": "ALL",
            **outer_metrics,
        }
    )
    gate, gate_candidates = choose_development_gate(
        competition, model, development_rows, metric_rows
    )
    outer_gate = validate_gate_outer(gate, outer_rows)
    if outer_metrics["produced"] == 0 or outer_metrics["failed"] > 0:
        disposition = "EVIDENCE_INSUFFICIENT_TO_DEFINE_USABLE_PROFILE"
        requirements = {}
        rationale = (
            "OUTER_HAS_NO_USABLE_PRODUCED_EVIDENCE"
            if outer_metrics["produced"] == 0
            else "OUTER_CONTAINS_FAILED_MODEL_EVIDENCE"
        )
    elif gate is None:
        disposition = "NO_ADDITIONAL_STATISTICAL_GATE_JUSTIFIED"
        requirements = {}
        rationale = "No data-derived readiness threshold improved log-loss, Brier and calibration consistently across both development folds."
    elif outer_gate["status"] == "NO_OUTER_PASSING_TARGETS":
        disposition = "EVIDENCE_INSUFFICIENT_TO_DEFINE_USABLE_PROFILE"
        requirements = {}
        rationale = "FROZEN_DEVELOPMENT_GATE_BLOCKS_ALL_OUTER_PRODUCED_TARGETS"
    elif outer_gate["supported"] is True:
        disposition = "ADDITIONAL_READINESS_GATE_JUSTIFIED"
        requirements = requirements_for_gate(model, gate)
        rationale = "The development-only data-derived gate improved all primary readiness metrics in both expanding folds and was not contradicted by untouched outer evidence."
    else:
        disposition = "NO_ADDITIONAL_STATISTICAL_GATE_JUSTIFIED"
        requirements = {}
        rationale = "The only qualifying development gate was contradicted by untouched outer evidence; no replacement was tuned on outer."
    usable = disposition != "EVIDENCE_INSUFFICIENT_TO_DEFINE_USABLE_PROFILE"
    apply_profile(development_rows, requirements, usable)
    apply_profile(outer_rows, requirements, usable)
    readiness_outer_pass = [
        row
        for row in outer_rows
        if row["status"] == "PRODUCED" and row["readiness_pass"] is True
    ]
    readiness_outer_blocked = [
        row
        for row in outer_rows
        if row["status"] == "PRODUCED" and row["readiness_pass"] is False
    ]
    profile = {
        "competition_id": competition.pk,
        "country": str(competition.country),
        "competition": competition.name,
        "model_code": model,
        "model_version": model_version(model),
        "calibration_strategy_version": STRATEGY_VERSION,
        "proposed_profile_version": f"fs012-{model.lower()}-{outer.year}-v1",
        "disposition": disposition,
        "selected_model_config": complete_adapter_config(model, config),
        "requirements": requirements,
        "selected_development_gate": gate,
        "outer_gate_validation": outer_gate,
        "development_seasons": [season.year for season in development],
        "outer_season": outer.year,
        "sporting_basis_hash": basis_hash,
        "development_metrics": development_metrics,
        "outer_metrics": outer_metrics,
        "outer_readiness_pass_metrics": metrics(readiness_outer_pass),
        "outer_readiness_blocked_metrics": metrics(readiness_outer_blocked),
        "hyperparameter_candidates": candidate_summary,
        "readiness_candidate_count": len(gate_candidates),
        "rationale": rationale,
        "provenance": {
            "sporting_history_only": True,
            "provider_calls": 0,
            "odds_used": False,
            "db_writes": 0,
            "inner_fold_count": len(inner_fold_specs(development)),
            "outer_block_count": len(outer_block_metrics),
            "outer_retuned": False,
            "same_block_results_revealed": False,
        },
    }
    result = {
        "profile": profile,
        "target_rows": development_rows + outer_rows,
        "metric_rows": metric_rows,
    }
    return (result, False)
