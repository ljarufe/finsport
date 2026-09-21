"""Fixed-unit settlement and Decision diagnostics for FS-019."""

from collections import Counter, defaultdict
from statistics import mean

from .storage import instant


def fixed_unit_reward(action, selected_outcome, actual_outcome, selected_price=None):
    if actual_outcome in {"VOID", "REFUND"}:
        return 0.0
    if action == "NO_BET":
        return 0.0
    if action != "BET" or selected_outcome not in {"HOME", "DRAW", "AWAY"}:
        raise ValueError("INVALID_DECISION_ACTION")
    if actual_outcome not in {"HOME", "DRAW", "AWAY"}:
        raise ValueError("INVALID_SETTLEMENT_OUTCOME")
    if selected_price is None or float(selected_price) <= 1:
        raise ValueError("INVALID_SETTLEMENT_PRICE")
    return float(selected_price) - 1 if selected_outcome == actual_outcome else -1.0


def settle_rows(rows):
    result = []
    for row in rows:
        reward = fixed_unit_reward(
            row["action"],
            row["selected_outcome"],
            row["actual_regulation_outcome"],
            row.get("selected_price"),
        )
        result.append(
            {**row, "stake": 1.0 if row["action"] == "BET" else 0.0, "reward": reward}
        )
    return result


def _distribution(values):
    values = sorted(float(value) for value in values)
    if not values:
        return {"count": 0, "min": None, "median": None, "max": None}
    middle = len(values) // 2
    median = (
        values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
    )
    return {"count": len(values), "min": values[0], "median": median, "max": values[-1]}


def _losing_streak(rows):
    longest = current = 0
    for row in sorted(
        rows, key=lambda item: (instant(item["kickoff"]), item["match_id"])
    ):
        if row["action"] == "BET" and row["reward"] < 0:
            current += 1
            longest = max(longest, current)
        elif row["action"] == "BET":
            current = 0
    return longest


def candidate_metrics(rows):
    total = len(rows)
    bets = [row for row in rows if row["action"] == "BET"]
    profit = sum(float(row["reward"]) for row in rows)
    stake = sum(float(row["stake"]) for row in rows)
    wins = sum(row["reward"] > 0 for row in bets)
    reasons = Counter(row["reason"] for row in rows)
    no_bet_reasons = Counter(row["reason"] for row in rows if row["action"] == "NO_BET")
    outcomes = Counter(row["selected_outcome"] for row in bets)
    books = Counter(row["representative_bookmaker"] for row in bets)
    co_best = Counter("|".join(row["co_best_bookmakers"]) for row in bets)
    monthly = defaultdict(float)
    for row in rows:
        monthly[instant(row["kickoff"]).strftime("%Y-%m")] += row["reward"]
    return {
        "common_opportunities": total,
        "bet_count": len(bets),
        "no_bet_count": total - len(bets),
        "bet_rate": len(bets) / total if total else None,
        "no_bet_rate": (total - len(bets)) / total if total else None,
        "reasons": dict(sorted(reasons.items())),
        "no_bet_reasons": dict(sorted(no_bet_reasons.items())),
        "action_outcomes": {
            key: outcomes.get(key, 0) for key in ("HOME", "DRAW", "AWAY")
        },
        "fixed_unit_profit": profit,
        "ppo": profit / total if total else None,
        "staked_units": stake,
        "yield": profit / stake if stake else None,
        "hit_rate": wins / len(bets) if bets else None,
        "selected_raw_odds": _distribution(row["selected_price"] for row in bets),
        "representative_bookmakers": dict(sorted(books.items())),
        "co_best_bookmakers": dict(sorted(co_best.items())),
        "selected_quote_age_seconds": _distribution(
            row["selected_quote_age_seconds"] for row in bets
        ),
        "monthly_profit": dict(sorted(monthly.items())),
        "longest_losing_bet_streak": _losing_streak(rows),
    }


def summarize_decisions(rows, candidate_ids, competition_ids):
    by_candidate = defaultdict(list)
    for row in rows:
        by_candidate[row["candidate_id"]].append(row)
    reports = {}
    for candidate in candidate_ids:
        candidate_rows = by_candidate[candidate]
        per_league = {
            str(competition): candidate_metrics(
                [row for row in candidate_rows if row["competition_id"] == competition]
            )
            for competition in competition_ids
        }
        league_ppos = [
            per_league[str(competition)]["ppo"] for competition in competition_ids
        ]
        reports[candidate] = {
            **candidate_metrics(candidate_rows),
            "per_league": per_league,
            "global_ppo": (
                mean(league_ppos)
                if league_ppos and all(value is not None for value in league_ppos)
                else None
            ),
            "pooled_ppo_diagnostic": candidate_metrics(candidate_rows)["ppo"],
        }
    return reports
