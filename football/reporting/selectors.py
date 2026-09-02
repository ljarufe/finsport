import json
from collections import defaultdict
from datetime import datetime, time, timedelta
from itertools import combinations

from django.db.models import Prefetch
from django.utils import timezone

from football.models import (
    CapitalExperiment,
    CapitalPolicyRun,
    Competition,
    Decision,
    Match,
    Prediction,
    PredictionExperiment,
)
from football.prediction.metrics import prediction_metrics

from .presentation import (
    CAPITAL_STATUSES,
    capital_reason_presentations,
    compact_config,
    config_items,
    decision_reason_presentations,
    match_status,
    outcome_label,
    reason_presentations,
)


def _config(value):
    return json.dumps(value or {}, sort_keys=True, separators=(",", ":"), default=str)


def _model_key(row):
    return row.model_code, row.variant, row.model_version, _config(row.model_config)


def _model_name(row):
    base = " · ".join(part or "—" for part in _model_key(row)[:3])
    return f"{base} · {compact_config(row.model_config)}"


def _model_key_name(key):
    base = " · ".join(part or "—" for part in key[:3])
    return f"{base} · {compact_config(json.loads(key[3]))}"


def _decision_key(row):
    return (
        *(
            _model_key(row.prediction)
            if row.prediction_id
            else ("Sin modelo", "", "", "{}")
        ),
        row.policy_code,
        row.policy_variant,
        row.policy_version,
        _config(row.policy_config),
    )


def _decision_name(row):
    model = (
        _model_name(row.prediction)
        if row.prediction_id
        else "Sin modelo probabilístico"
    )
    policy = f"{row.policy_code} · {row.policy_variant or '—'} · {row.policy_version} · {compact_config(row.policy_config)}"
    return f"{model} / {policy}"


def filters(params):
    errors, competition = [], None
    if raw := params.get("competition", ""):
        try:
            competition = Competition.objects.get(pk=int(raw), enabled=True)
        except (Competition.DoesNotExist, ValueError, TypeError):
            errors.append("La liga seleccionada no está disponible para este informe.")
    dates = []
    for key in ("date_from", "date_to"):
        try:
            dates.append(
                datetime.strptime(params[key], "%Y-%m-%d").date()
                if params.get(key)
                else None
            )
        except ValueError:
            dates.append(None)
            errors.append("Las fechas deben usar el formato AAAA-MM-DD.")
    if all(dates) and dates[0] > dates[1]:
        errors.append("La fecha inicial no puede ser posterior a la fecha final.")
    return competition, *dates, errors


def _scope(queryset, competition, start, end):
    if competition:
        queryset = queryset.filter(experiment__competition=competition)
    if start:
        queryset = queryset.filter(match__kickoff__date__gte=start)
    if end:
        queryset = queryset.filter(match__kickoff__date__lte=end)
    return queryset


def _decision_metrics(rows):
    actionable = [r for r in rows if r.action != Decision.ACTION_NO_BET]

    def outcome(row):
        return row.prediction.actual_outcome if row.prediction_id else row.match.outcome

    resolved = [r for r in actionable if outcome(r)]
    economic = [
        r
        for r in resolved
        if r.selected_odds_observation_id
        and r.selected_odds_observation.observed_at < r.decision_time
        and r.selected_price is not None
    ]
    hits = sum(r.action == outcome(r) for r in resolved)
    total = len(rows)
    pnl = sum(
        float(r.selected_price) - 1 if r.action == outcome(r) else -1 for r in economic
    )
    return {
        "evaluated_fixtures": total,
        "actionable": len(actionable),
        "coverage": len(actionable) / total if total else 0,
        "no_bet_count": total - len(actionable),
        "no_bet_rate": (total - len(actionable)) / total if total else 0,
        "resolved_actionable": len(resolved),
        "hits": hits,
        "losses": len(resolved) - hits,
        "hit_rate": hits / len(resolved) if resolved else None,
        "economic_decisions": len(economic),
        "economic_coverage": len(economic) / len(resolved) if resolved else 0,
        "flat_unit_pnl": pnl if economic else None,
        "roi": pnl / len(economic) if economic else None,
    }


def historical(params):
    competition, start, end, errors = filters(params)
    pqs = Prediction.objects.filter(
        experiment__mode=PredictionExperiment.MODE_PROSPECTIVE,
        experiment__competition__enabled=True,
    ).select_related("experiment", "match__season__competition")
    dqs = Decision.objects.filter(
        experiment__mode=PredictionExperiment.MODE_PROSPECTIVE,
        experiment__competition__enabled=True,
    ).select_related(
        "experiment",
        "match__season__competition",
        "prediction",
        "selected_odds_observation",
    )
    predictions = list(_scope(pqs, competition, start, end)) if not errors else []
    decisions = list(_scope(dqs, competition, start, end)) if not errors else []
    pg, dg = defaultdict(list), defaultdict(list)
    for row in predictions:
        pg[_model_key(row)].append(row)
    for row in decisions:
        dg[_decision_key(row)].append(row)
    prediction_rows = []
    for rows in pg.values():
        evaluated = [r for r in rows if r.actual_outcome]
        metrics = prediction_metrics(
            [r.actual_outcome for r in evaluated],
            [[r.p_home, r.p_draw, r.p_away] for r in evaluated],
        )
        confusion_order = metrics.get("confusion_order", [])
        confusion_values = metrics.get("confusion_matrix", [])
        calibration = metrics.get("calibration", {})
        prediction_rows.append(
            {
                "identity": _model_name(rows[0]),
                "config": rows[0].model_config,
                "config_items": config_items(rows[0].model_config),
                "produced": len(rows),
                "metrics": metrics,
                "confusion_headers": [outcome_label(code) for code in confusion_order],
                "confusion_rows": [
                    {"actual": outcome_label(code), "values": values}
                    for code, values in zip(confusion_order, confusion_values)
                ],
                "calibration_rows": [
                    {
                        "outcome": outcome_label(code),
                        "bins": bins,
                    }
                    for code, bins in calibration.items()
                ],
            }
        )
    decision_rows = []
    for rows in dg.values():
        first = rows[0]
        decision_rows.append(
            {
                "identity": _decision_name(first),
                "source_model": (
                    _model_name(first.prediction)
                    if first.prediction_id
                    else "Sin modelo probabilístico"
                ),
                "model_config": (
                    first.prediction.model_config if first.prediction_id else {}
                ),
                "model_config_items": (
                    config_items(first.prediction.model_config)
                    if first.prediction_id
                    else []
                ),
                "policy": f"{first.policy_code} · {first.policy_variant or '—'} · {first.policy_version} · {compact_config(first.policy_config)}",
                "config": first.policy_config,
                "config_items": config_items(first.policy_config),
                "metrics": _decision_metrics(rows),
            }
        )
    crosses = []
    for rows in dg.values():
        counts = {
            k: 0
            for k in (
                "correct_actionable",
                "incorrect_actionable",
                "correct_no_bet",
                "incorrect_no_bet",
            )
        }
        for r in rows:
            if not r.prediction_id or not r.prediction.actual_outcome:
                continue
            counts[
                (
                    "correct"
                    if r.prediction.predicted_outcome == r.prediction.actual_outcome
                    else "incorrect"
                )
                + ("_no_bet" if r.action == Decision.ACTION_NO_BET else "_actionable")
            ] += 1
        if total := sum(counts.values()):
            crosses.append(
                {"identity": _decision_name(rows[0]), "counts": counts, "total": total}
            )
    instances, pairs = defaultdict(list), defaultdict(list)
    for r in predictions:
        if r.actual_outcome:
            instances[(r.experiment_id, r.match_id)].append(r)
    for rows in instances.values():
        unique = {_model_key(r): r for r in rows}
        for left, right in combinations(sorted(unique.values(), key=_model_key), 2):
            pairs[(_model_key(left), _model_key(right))].append((left, right))
    agreements = []
    for pair, rows in pairs.items():
        same = sum(a.predicted_outcome == b.predicted_outcome for a, b in rows)
        agreements.append(
            {
                "models": " / ".join(_model_key_name(key) for key in pair),
                "n": len(rows),
                "agreement": same,
                "agreement_rate": same / len(rows),
                "disagreements": len(rows) - same,
                "a_only": sum(
                    a.predicted_outcome == a.actual_outcome
                    and b.predicted_outcome != b.actual_outcome
                    for a, b in rows
                ),
                "b_only": sum(
                    b.predicted_outcome == b.actual_outcome
                    and a.predicted_outcome != a.actual_outcome
                    for a, b in rows
                ),
                "shared_errors": sum(
                    a.predicted_outcome != a.actual_outcome
                    and b.predicted_outcome != b.actual_outcome
                    for a, b in rows
                ),
            }
        )
    bqs = PredictionExperiment.objects.filter(
        mode=PredictionExperiment.MODE_BACKTEST,
        competition__enabled=True,
    ).select_related("competition")
    if competition:
        bqs = bqs.filter(competition=competition)
    if start:
        bqs = bqs.filter(period_end__gte=start)
    if end:
        bqs = bqs.filter(period_start__lte=end)
    backtests = []
    for backtest in bqs:
        arms = [
            {"code": code, "reasons": reason_presentations(reason)}
            for code, reason in (backtest.summary or {})
            .get("unavailable_arms", {})
            .items()
        ]
        if arms:
            backtests.append(
                {
                    "id": backtest.pk,
                    "competition": backtest.competition,
                    "period_start": backtest.period_start,
                    "period_end": backtest.period_end,
                    "completed_at": backtest.completed_at,
                    "engine_version": backtest.engine_version,
                    "arms": arms,
                }
            )
    capital_runs = CapitalPolicyRun.objects.select_related(
        "experiment__source_experiment__competition"
    ).filter(experiment__source_experiment__competition__enabled=True)
    if competition:
        capital_runs = capital_runs.filter(
            experiment__source_experiment__competition=competition
        )
    if start:
        capital_runs = capital_runs.filter(
            experiment__source_experiment__period_end__gte=start
        )
    if end:
        capital_runs = capital_runs.filter(
            experiment__source_experiment__period_start__lte=end
        )
    capital_runs = list(capital_runs)
    for run in capital_runs:
        run.status_label = CAPITAL_STATUSES.get(run.status, "Estado no clasificado")
        run.reason_items = capital_reason_presentations(run.reason)
        run.stake_concentration = run.metrics.get("stake_concentration")
        if run.experiment.mode == CapitalExperiment.MODE_REPLAY:
            run.terminal_bankroll = run.metrics.get("terminal_bankroll")
            run.total_pnl = run.metrics.get("total_pnl")
            run.roi = run.metrics.get("roi")
            run.maximum_drawdown = run.metrics.get("maximum_drawdown")
            run.practical_ruin = run.metrics.get("practical_ruin")
            run.max_stake_pre_bankroll_ratio = run.metrics.get(
                "max_stake_pre_bankroll_ratio"
            )
        else:
            run.reported_path_count = (
                run.path_count
                if run.path_count is not None
                else run.metrics.get("path_count")
            )
            run.mean_terminal_bankroll = run.metrics.get("mean_terminal_bankroll")
            run.median_terminal_bankroll = run.metrics.get("median_terminal_bankroll")
            run.mean_pnl = run.metrics.get("mean_pnl")
            run.median_pnl = run.metrics.get("median_pnl")
            run.practical_ruin_probability = run.metrics.get(
                "practical_ruin_probability"
            )
            run.expected_shortfall = run.metrics.get("expected_shortfall")
            run.terminal_bankroll_quantile_1 = run.metrics.get(
                "terminal_bankroll_quantile_1"
            )
            run.terminal_bankroll_quantile_5 = run.metrics.get(
                "terminal_bankroll_quantile_5"
            )
            run.maximum_drawdown_distribution = run.metrics.get(
                "maximum_drawdown_distribution", {}
            )
            run.max_stake_distribution = run.metrics.get("max_stake_distribution", {})
            run.max_stake_pre_bankroll_ratio_distribution = run.metrics.get(
                "max_stake_pre_bankroll_ratio_distribution", {}
            )
    return {
        "competitions": Competition.objects.filter(enabled=True),
        "competition": competition,
        "start": start,
        "end": end,
        "errors": errors,
        "prediction_rows": prediction_rows,
        "decision_rows": decision_rows,
        "crosses": crosses,
        "agreements": agreements,
        "backtests": backtests,
        "replay_capital_runs": [
            run
            for run in capital_runs
            if run.experiment.mode == CapitalExperiment.MODE_REPLAY
        ],
        "stochastic_capital_runs": [
            run
            for run in capital_runs
            if run.experiment.mode
            in (CapitalExperiment.MODE_MONTE_CARLO, CapitalExperiment.MODE_STRESS)
        ],
        "evidence": {"predictions": len(predictions), "decisions": len(decisions)},
    }


def daily(params):
    competition, _, _, errors = filters({"competition": params.get("competition", "")})
    try:
        selected = (
            datetime.strptime(params["date"], "%Y-%m-%d").date()
            if params.get("date")
            else timezone.localdate()
        )
    except ValueError:
        selected = timezone.localdate()
        errors.append("La fecha debe usar el formato AAAA-MM-DD.")
    start = timezone.make_aware(
        datetime.combine(selected, time.min), timezone.get_current_timezone()
    )
    end = start + timedelta(days=1)
    pqs = (
        Prediction.objects.filter(
            experiment__mode=PredictionExperiment.MODE_PROSPECTIVE,
            experiment__competition__enabled=True,
        )
        .select_related("experiment")
        .order_by("model_code", "variant")
    )
    dqs = (
        Decision.objects.filter(
            experiment__mode=PredictionExperiment.MODE_PROSPECTIVE,
            experiment__competition__enabled=True,
        )
        .select_related(
            "prediction",
            "selected_odds_observation__source",
            "selected_odds_observation__bookmaker",
            "selected_odds_observation__market",
        )
        .order_by("policy_code", "policy_variant")
    )
    matches = (
        Match.objects.filter(
            kickoff__gte=start,
            kickoff__lt=end,
            season__competition__enabled=True,
        )
        .select_related(
            "season__competition",
            "home_team__competition",
            "away_team__competition",
        )
        .prefetch_related(
            Prefetch("predictions", queryset=pqs), Prefetch("decisions", queryset=dqs)
        )
    )
    if competition:
        matches = matches.filter(season__competition=competition)
    for match in matches:
        match.outcome_label = outcome_label(match.outcome)
        match.status_presentation = match_status(match.status_short, match.status_long)
        for p in match.predictions.all():
            p.outcome_label, p.actual_label = outcome_label(
                p.predicted_outcome
            ), outcome_label(p.actual_outcome)
            p.identity_label = _model_name(p)
            p.config_label = compact_config(p.model_config)
            p.config_items = config_items(p.model_config)
        for d in match.decisions.all():
            outcome = d.prediction.actual_outcome if d.prediction_id else match.outcome
            d.action_label, d.actual_label, d.reason_items = (
                outcome_label(d.action),
                outcome_label(outcome),
                decision_reason_presentations(d.reason),
            )
            d.source_model_label = (
                _model_name(d.prediction)
                if d.prediction_id
                else "Sin modelo probabilístico"
            )
            d.source_model_config_items = (
                config_items(d.prediction.model_config) if d.prediction_id else []
            )
            d.policy_label = (
                f"{d.policy_code} · {d.policy_variant or '—'} · {d.policy_version}"
            )
            d.policy_config_label = compact_config(d.policy_config)
            d.policy_config_items = config_items(d.policy_config)
            d.valid_selected_price = bool(
                d.action != Decision.ACTION_NO_BET
                and outcome
                and d.selected_odds_observation_id
                and d.selected_odds_observation.observed_at < d.decision_time
                and d.selected_price is not None
            )
            d.hit, d.loss = bool(
                outcome and d.action != Decision.ACTION_NO_BET and d.action == outcome
            ), bool(
                outcome and d.action != Decision.ACTION_NO_BET and d.action != outcome
            )
            d.simulated_pnl = (
                float(d.selected_price) - 1
                if d.valid_selected_price and d.hit
                else (-1 if d.valid_selected_price else None)
            )
    return {
        "competitions": Competition.objects.filter(enabled=True),
        "competition": competition,
        "selected": selected,
        "previous": selected - timedelta(days=1),
        "next": selected + timedelta(days=1),
        "errors": errors,
        "matches": matches,
    }
