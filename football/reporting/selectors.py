"""Bounded, read-only selectors for the single #209 simulation UI."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Prefetch, Q, Sum
from django.http import Http404
from django.utils import timezone

from football.models import (
    CapitalDeployment,
    CapitalEvaluation,
    CapitalExecutionState,
    CapitalPosition,
    CaptureWorkItem,
    Competition,
    Decision,
    Match,
    Prediction,
    Season,
)
from football.prediction.market import market_selection_as_of
from football.strategy.deployment import CONFIG_IDENTITY
from football.sync import FINISHED_STATUSES

LOCAL_ZONE = ZoneInfo("America/Lima")
ZERO = Decimal("0")
PAGE_SIZE = 40
CHART_EVENTS = 90
CAPTURE_STATUSES = ("SUCCESS", "SUCCESS_EMPTY", "LATE_CAPTURE")
SETTLED_STATUSES = (
    CapitalPosition.Status.SETTLED_WIN,
    CapitalPosition.Status.SETTLED_LOSS,
    CapitalPosition.Status.VOID,
)
GROUPS = (
    ("settled_bet", "Terminados · apostados"),
    ("open_bet", "Próximos o en curso · apostados"),
    ("finished_unbet", "Terminados · no apostados"),
    ("upcoming_unbet", "Próximos · no apostados"),
)
OUTCOMES = {"HOME": "Local", "DRAW": "Empate", "AWAY": "Visitante"}
MATCH_STATES = {
    "NS": "Próximo",
    "TBD": "Por confirmar",
    "1H": "En curso",
    "HT": "Descanso",
    "2H": "En curso",
    "FT": "Finalizado",
    "ET": "Finalizado",
    "AET": "Finalizado",
    "P": "Finalizado",
    "PEN": "Finalizado",
    "AWD": "Finalizado",
    "WO": "Finalizado",
    "PST": "Pospuesto",
    "SUSP": "Suspendido",
    "CANC": "Cancelado",
}
REASONS = {
    "NO_BET": "No alcanzó el criterio de selección",
    "INPUT_QUOTES_MISSING": "Sin cuotas completas admisibles",
    "NO_EXECUTION_PRICE": "Sin precio de ejecución válido",
    "INELEGIBLE_EXECUTION_QUOTE": "Cuota fuera de la ventana válida",
    "MISSED_EXECUTION_WINDOW": "Ventana de evaluación vencida",
    "EXPIRED_CAPACITY": "La capacidad se liberó después del inicio",
    "INSUFFICIENT_AVAILABLE_CASH": "Capital disponible temporalmente insuficiente",
    "STRATEGY_DRAINING": "Estrategia en pausa por drenaje",
    "STRATEGY_STOPPED": "Estrategia detenida",
    "OPERATIONAL_DEPLETION": "Banca detenida por agotamiento",
    "AWAITING_FINAL_OPEN_SETTLEMENT": "Esperando liquidación pendiente",
    "PRE_GLOBAL": "Anterior a la activación",
    "AUTHORITY_EVIDENCE_MISMATCH": "Evidencia no conciliada",
    "EXECUTION_PRICE_MISMATCH": "Precio no conciliado",
    "EVALUATION_ERROR": "Error al evaluar",
    "NO_VALID_CANONICAL_1X2_QUOTES": "Sin cuotas completas admisibles",
    "UNAVAILABLE_NO_DECISION_AT_EXECUTION": "Sin decisión admisible al ejecutar",
    "INELIGIBLE": "La política de capital no autorizó la apuesta",
}


def _deployment():
    deployment = CapitalDeployment.objects.select_related("config").filter(pk=1).first()
    if not deployment or not deployment.config_id:
        return None, None
    config = deployment.config
    if (
        deployment.selection.get("winner") != 209
        or deployment.real_betting
        or not config.automatic
    ):
        return None, None
    if deployment.active_epoch_id:
        from football.strategy.deployment import verify_config

        if config.strategy_epoch_id != deployment.active_epoch_id:
            return None, None
        try:
            verify_config(deployment)
        except RuntimeError:
            return None, None
    elif config.identity != CONFIG_IDENTITY:
        return None, None
    return deployment, config


def _bounds(day):
    start = datetime.combine(day, time.min, tzinfo=LOCAL_ZONE)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=LOCAL_ZONE)
    return start, end


def _settled(config, now):
    return CapitalPosition.objects.filter(
        config=config,
        status__in=SETTLED_STATUSES,
        settled_at__isnull=False,
        settled_at__lte=now,
    )


def _periods(config, deployment, now):
    today = now.astimezone(LOCAL_ZONE).date()
    starts = (
        ("Hoy", today),
        ("Semana", today - timedelta(days=today.weekday())),
        ("Mes", today.replace(day=1)),
        ("Total", None),
    )
    settled = _settled(config, now)
    rows = []
    for label, day in starts:
        scope = (
            settled.filter(
                settled_at__gte=max(_bounds(day)[0], deployment.activated_at)
            )
            if day
            else settled.filter(settled_at__gte=deployment.activated_at)
        )
        aggregate = scope.aggregate(count=Count("pk"), pnl=Sum("realized_pnl"))
        pnl = aggregate["pnl"] or ZERO
        opening_equity = (
            config.bankroll_equity - pnl if day else config.initial_bankroll
        )
        rows.append(
            {
                "label": label,
                "pnl": pnl,
                "count": aggregate["count"],
                "opening_equity": opening_equity,
                "rate": (
                    pnl / opening_equity
                    if aggregate["count"] and opening_equity > 0
                    else None
                ),
            }
        )
    return rows


def _chart(config, deployment, now, settled_count):
    """Initial equity, then at most 90 real settlements in (time, PK) order.

    Older events are one labelled prior-ledger anchor, never synthetic trades.
    """
    if not settled_count:
        return {"points": [], "initial": config.initial_bankroll, "empty": True}
    settled = _settled(config, now)
    rows = list(
        settled.order_by("-settled_at", "-pk").values(
            "pk", "settled_at", "realized_pnl"
        )[:CHART_EVENTS]
    )
    rows.reverse()
    older_count = settled_count - len(rows)
    prior_pnl = ZERO
    if older_count:
        first = rows[0]
        prior_pnl = (
            settled.filter(
                Q(settled_at__lt=first["settled_at"])
                | Q(settled_at=first["settled_at"], pk__lt=first["pk"])
            ).aggregate(value=Sum("realized_pnl"))["value"]
            or ZERO
        )
    points = [
        {
            "kind": "initial",
            "at": deployment.activated_at,
            "day": deployment.activated_at.astimezone(LOCAL_ZONE).date(),
            "pnl": ZERO,
            "equity": config.initial_bankroll,
        }
    ]
    equity = config.initial_bankroll + prior_pnl
    if older_count:
        points.append(
            {
                "kind": "prior",
                "at": rows[0]["settled_at"],
                "day": rows[0]["settled_at"].astimezone(LOCAL_ZONE).date(),
                "pnl": prior_pnl,
                "equity": equity,
                "count": older_count,
            }
        )
    for row in rows:
        equity += row["realized_pnl"]
        points.append(
            {
                "kind": "settlement",
                "at": row["settled_at"],
                "day": row["settled_at"].astimezone(LOCAL_ZONE).date(),
                "pnl": row["realized_pnl"],
                "equity": equity,
            }
        )
    if equity != config.bankroll_equity:
        return {
            "points": [],
            "initial": config.initial_bankroll,
            "empty": True,
            "inconsistent": True,
        }
    values = [float(point["equity"]) for point in points]
    low, high = min(values), max(values)
    spread = max(high - low, 1.0)
    denominator = max(len(points) - 1, 1)
    for index, point in enumerate(points):
        point["x"] = round(20 + 600 * index / denominator, 1)
        point["y"] = round(175 - 130 * (values[index] - low) / spread, 1)
    return {
        "points": points,
        "events": points[1:],
        "path": " ".join(f"{point['x']},{point['y']}" for point in points),
        "initial": config.initial_bankroll,
        "empty": False,
        "older_count": older_count,
        "settlement_count": settled_count,
    }


def _activity(config, deployment):
    activated = deployment.activated_at
    captured = CaptureWorkItem.objects.filter(
        match_id=OuterRef("pk"),
        source__code="api_football",
        executed_at__gte=activated,
        status__in=CAPTURE_STATUSES,
    )
    observed = (
        Match.objects.filter(
            season__competition__enabled=True,
            season__competition__competition_type="League",
            season__competition__country__gt="",
            kickoff__gte=activated,
        )
        .alias(captured_since_activation=Exists(captured))
        .filter(Q(observed_at__gte=activated) | Q(captured_since_activation=True))
        .count()
    )
    counts = CapitalPosition.objects.filter(config=config).aggregate(
        bet=Count("match_id", distinct=True),
        won=Count(
            "match_id",
            filter=Q(status=CapitalPosition.Status.SETTLED_WIN),
            distinct=True,
        ),
        lost=Count(
            "match_id",
            filter=Q(status=CapitalPosition.Status.SETTLED_LOSS),
            distinct=True,
        ),
    )
    return [
        {
            "label": "Observados",
            "count": observed,
            "rate": Decimal(1) if observed else None,
        },
        {
            "label": "Apostados",
            "count": counts["bet"],
            "rate": Decimal(counts["bet"]) / observed if observed else None,
        },
        {
            "label": "Ganados",
            "count": counts["won"],
            "rate": Decimal(counts["won"]) / observed if observed else None,
        },
        {
            "label": "Perdidos",
            "count": counts["lost"],
            "rate": Decimal(counts["lost"]) / observed if observed else None,
        },
    ]


def _competitions(today):
    rows = (
        Competition.objects.filter(
            enabled=True, competition_type="League", country__gt=""
        )
        .prefetch_related(
            Prefetch(
                "seasons",
                queryset=Season.objects.filter(
                    start_date__isnull=False, end_date__gte=today
                ).order_by("start_date", "pk"),
                to_attr="dated_seasons",
            )
        )
        .order_by("country", "name", "pk")
    )
    result = []
    for competition in rows:
        current = next(
            (
                s
                for s in competition.dated_seasons
                if s.start_date <= today <= s.end_date
            ),
            None,
        )
        upcoming = next(
            (s for s in competition.dated_seasons if s.start_date > today), None
        )
        season = current or upcoming
        result.append(
            {
                "name": competition.name,
                "country": str(competition.country),
                "season": season,
                "status": (
                    "En curso"
                    if current
                    else "Próxima temporada" if upcoming else "Sin calendario"
                ),
                "tone": (
                    "success" if current else "warning" if upcoming else "secondary"
                ),
            }
        )
    return result


def home():
    """Read current bank, bounded settlements and enabled league calendar only."""
    now = timezone.now()
    deployment, config = _deployment()
    leagues = _competitions(now.astimezone(LOCAL_ZONE).date())
    context = {
        "leagues": leagues,
        "league_count": len(leagues),
        "deployment": deployment,
        "config": config,
        "warnings": [],
    }
    if config is None or deployment.activated_at is None:
        return context
    open_exposure = (
        CapitalPosition.objects.filter(
            config=config, status=CapitalPosition.Status.OPEN
        ).aggregate(value=Sum("applied_stake"))["value"]
        or ZERO
    )
    if open_exposure != config.reserved_exposure:
        context["warnings"].append("La exposición abierta no concilia con la banca.")
    settled = _settled(config, now)
    ledger = settled.aggregate(count=Count("pk"), pnl=Sum("realized_pnl"))
    if (ledger["pnl"] or ZERO) != config.realized_pnl:
        context["warnings"].append("El rendimiento realizado no concilia con la banca.")
    context.update(
        {
            "capital": {
                "equity": config.bankroll_equity,
                "initial": config.initial_bankroll,
                "available": config.available_cash,
                "reserved": config.reserved_exposure,
            },
            "results": _periods(config, deployment, now),
            "chart": _chart(config, deployment, now, ledger["count"]),
            "activity": _activity(config, deployment),
        }
    )
    return context


def _selection_params(params):
    errors = []
    today = timezone.now().astimezone(LOCAL_ZONE).date()
    try:
        selected = date.fromisoformat(params.get("date") or today.isoformat())
    except ValueError:
        selected = today
        errors.append("La fecha no es válida; se muestra hoy.")
    competition = None
    raw = params.get("competition")
    if raw:
        try:
            competition = Competition.objects.get(
                pk=int(raw), enabled=True, competition_type="League", country__gt=""
            )
        except (ValueError, Competition.DoesNotExist):
            errors.append("La liga indicada no está disponible.")
    return selected, competition, errors, today


def _empty_calendar(day):
    discovery = (
        CaptureWorkItem.objects.filter(
            purpose=CaptureWorkItem.Purpose.FIXTURE_REFRESH,
            intended_window="fixture-discovery",
            logical_identity__endswith=day.isoformat(),
        )
        .order_by("-pk")
        .values_list("status", flat=True)
        .first()
    )
    if discovery in CAPTURE_STATUSES:
        return "No se registraron partidos para esta fecha."
    if discovery == CaptureWorkItem.Status.FAILED_PROVIDER:
        return "No se pudo actualizar el calendario de esta fecha."
    return "Aún no hay calendario verificado para esta fecha."


def _reason_label(reason, diagnostics=None):
    if (
        reason == "INELIGIBLE"
        and (diagnostics or {}).get("policy_reason") == "NO_POSITIVE_KELLY_EDGE"
    ):
        return "Sin valor económico positivo"
    return REASONS.get(reason, "Motivo operativo registrado")


def _match_status(match, position, state, evaluation):
    if position:
        label = {
            CapitalPosition.Status.OPEN: "Apuesta pendiente",
            CapitalPosition.Status.SETTLED_WIN: "Apuesta ganada",
            CapitalPosition.Status.SETTLED_LOSS: "Apuesta perdida",
            CapitalPosition.Status.VOID: "Apuesta anulada",
        }.get(position["status"], "Apostado")
        tone = (
            "warning"
            if position["status"] == CapitalPosition.Status.OPEN
            else (
                "success"
                if position["status"] == CapitalPosition.Status.SETTLED_WIN
                else (
                    "danger"
                    if position["status"] == CapitalPosition.Status.SETTLED_LOSS
                    else "secondary"
                )
            )
        )
        return label, tone, ""
    if state and state["status"] == CapitalExecutionState.Status.PENDING_CAPACITY:
        return "Esperando capacidad", "warning", "Sin lane disponible por ahora"
    reason = (
        (state or {}).get("non_placement_reason")
        or (evaluation or {}).get("reason")
        or ""
    )
    if reason == "NO_BET" or (evaluation and evaluation["status"] == "NO_BET"):
        return "No seleccionado", "secondary", _reason_label("NO_BET")
    if reason:
        return (
            "Sin apuesta",
            (
                "warning"
                if reason
                in {
                    "INPUT_QUOTES_MISSING",
                    "MISSED_EXECUTION_WINDOW",
                    "EXPIRED_CAPACITY",
                }
                else "secondary"
            ),
            _reason_label(reason, (state or {}).get("diagnostics")),
        )
    if state:
        if state["status"] == CapitalExecutionState.Status.NOT_PLACED:
            return "Sin apuesta", "secondary", "Capital no colocó una posición"
        if state["status"] == CapitalExecutionState.Status.PLACED:
            return (
                "Estado por conciliar",
                "warning",
                "Posición financiera no disponible",
            )
        return (
            "Evaluación de capital pendiente",
            "secondary",
            "Esperando decisión de capital",
        )
    if evaluation:
        if evaluation["status"] == "FAILED":
            return "Evaluación fallida", "warning", "La evaluación no pudo completarse"
        return "Evaluado", "secondary", "Ejecución de capital aún sin estado"
    return "Sin evaluación", "secondary", "Aún no hay evaluación de esta oportunidad"


def matches_day(params):
    selected, competition, errors, today = _selection_params(params)
    start, end = _bounds(selected)
    qs = (
        Match.objects.filter(
            kickoff__gte=start,
            kickoff__lt=end,
            season__competition__enabled=True,
            season__competition__competition_type="League",
            season__competition__country__gt="",
        )
        .select_related("season__competition", "home_team", "away_team")
        .order_by("kickoff", "pk")
    )
    if competition:
        qs = qs.filter(season__competition=competition)
    page = Paginator(qs, PAGE_SIZE).get_page(params.get("page"))
    matches = list(page.object_list)
    deployment, config = _deployment()
    ids = [match.pk for match in matches]
    positions = (
        {
            row["match_id"]: row
            for row in CapitalPosition.objects.filter(
                config=config, match_id__in=ids
            ).values(
                "match_id",
                "status",
                "applied_stake",
                "realized_pnl",
                "settled_at",
                "execution_basis__action",
                "execution_basis__selected_price",
            )
        }
        if config and ids
        else {}
    )
    states = (
        {
            row["match_id"]: row
            for row in CapitalExecutionState.objects.filter(
                config=config, match_id__in=ids
            ).values(
                "match_id",
                "status",
                "non_placement_reason",
                "diagnostics",
                "execution_basis__action",
            )
        }
        if config and ids
        else {}
    )
    evaluations = {}
    if deployment and ids:
        for row in (
            CapitalEvaluation.objects.filter(
                deployment=deployment, work__match_id__in=ids
            )
            .order_by("work__match_id", "-attempted_at", "-pk")
            .distinct("work__match_id")
            .values("work__match_id", "status", "reason", "experiment_id")
        ):
            evaluations.setdefault(row["work__match_id"], row)
    experiment_ids = [
        row["experiment_id"] for row in evaluations.values() if row["experiment_id"]
    ]
    decisions = (
        {
            row["experiment_id"]: row
            for row in Decision.objects.filter(
                experiment_id__in=experiment_ids,
                policy_code="SELECTIVE_CONFIDENCE",
                policy_variant="0.45",
                prediction__model_code=Prediction.MARKET_CONSENSUS,
            ).values("experiment_id", "action")
        }
        if experiment_ids
        else {}
    )
    groups = {key: [] for key, _ in GROUPS}
    for match in matches:
        position, state, evaluation = (
            positions.get(match.pk),
            states.get(match.pk),
            evaluations.get(match.pk),
        )
        finished = (
            match.status_short in FINISHED_STATUSES
            or match.status_short == "CANC"
            or bool(position and position["status"] in SETTLED_STATUSES)
        )
        group = (
            "settled_bet"
            if finished and position
            else (
                "open_bet"
                if position
                else "finished_unbet" if finished else "upcoming_unbet"
            )
        )
        label, tone, reason = _match_status(match, position, state, evaluation)
        if (
            deployment
            and deployment.activated_at
            and match.kickoff < deployment.activated_at
            and not position
        ):
            label, tone, reason = (
                "Anterior a la activación",
                "secondary",
                "Este partido no pertenece a la estrategia actual",
            )
        action = (
            (position or {}).get("execution_basis__action")
            or (state or {}).get("execution_basis__action")
            or (decisions.get((evaluation or {}).get("experiment_id")) or {}).get(
                "action"
            )
        )
        home_score, away_score = match.fulltime_home_score, match.fulltime_away_score
        if match.status_short == "FT" and home_score is None and away_score is None:
            home_score, away_score = match.home_score, match.away_score
        groups[group].append(
            {
                "match": match,
                "label": label,
                "tone": tone,
                "reason": reason,
                "position": position,
                "action": OUTCOMES.get(action),
                "score": (
                    f"{home_score}–{away_score}"
                    if home_score is not None and away_score is not None
                    else None
                ),
                "outcome": OUTCOMES.get(match.outcome) if finished else None,
                "match_state": MATCH_STATES.get(
                    match.status_short, "Estado por confirmar"
                ),
            }
        )
    leagues = Competition.objects.filter(
        enabled=True, competition_type="League", country__gt=""
    ).order_by("country", "name", "pk")
    return {
        "selected": selected,
        "today": today,
        "yesterday": today - timedelta(days=1),
        "tomorrow": today + timedelta(days=1),
        "previous": selected - timedelta(days=1),
        "next": selected + timedelta(days=1),
        "competition": competition,
        "competitions": leagues,
        "errors": errors,
        "page": page,
        "groups": [(label, groups[key]) for key, label in GROUPS],
        "empty_calendar": _empty_calendar(selected) if not page.paginator.count else "",
    }


def match_detail(match_id):
    """One requested match only; never prefetch these relations for the day list."""
    match = (
        Match.objects.select_related("season__competition", "home_team", "away_team")
        .filter(pk=match_id, season__competition__enabled=True)
        .first()
    )
    if match is None:
        raise Http404("Partido no disponible")
    deployment, config = _deployment()
    position = (
        CapitalPosition.objects.filter(config=config, match=match)
        .select_related("execution_basis")
        .first()
        if config
        else None
    )
    state = (
        CapitalExecutionState.objects.filter(config=config, match=match).first()
        if config
        else None
    )
    evaluation = (
        CapitalEvaluation.objects.filter(deployment=deployment, work__match=match)
        .order_by("-attempted_at", "-pk")
        .first()
        if deployment
        else None
    )
    decision = None
    if evaluation and evaluation.experiment_id:
        decision = (
            Decision.objects.filter(
                experiment_id=evaluation.experiment_id,
                match=match,
                policy_code="SELECTIVE_CONFIDENCE",
                policy_variant="0.45",
                prediction__model_code=Prediction.MARKET_CONSENSUS,
            )
            .select_related(
                "prediction",
                "selected_odds_observation__bookmaker__canonical_ref__canonical_bookmaker",
            )
            .first()
        )
    capture_rows = []
    works = (
        CaptureWorkItem.objects.filter(
            match=match,
            purpose=CaptureWorkItem.Purpose.ODDS_CAPTURE,
            status__in=CAPTURE_STATUSES,
            source__code="api_football",
            executed_at__gte=deployment.activated_at,
            intended_window__in=(
                "market-t6h",
                "market-t60m",
                "market-t30m",
                "market-t10m",
            ),
            executed_at__isnull=False,
            completed_at__isnull=False,
            run__completed_at__isnull=False,
        )
        .select_related("run", "source")
        .order_by("-executed_at", "-pk")[:12]
        if deployment
        and deployment.activated_at
        and match.kickoff >= deployment.activated_at
        else []
    )
    for work in works:
        selection = market_selection_as_of(
            match, work.run.completed_at, not_before=work.executed_at, capture_work=work
        )
        capture_rows.append(
            {
                "window": {
                    "market-t6h": "T−6 h",
                    "market-t60m": "T−60 min",
                    "market-t30m": "T−30 min",
                    "market-t10m": "T−10 min",
                }[work.intended_window],
                "at": work.executed_at,
                "quotes": [
                    {
                        "bookmaker": quote.canonical_bookmaker.name,
                        "source": quote.observation.source.name,
                        "at": quote.observation.observed_at,
                        "home": quote.observation.home,
                        "draw": quote.observation.draw,
                        "away": quote.observation.away,
                    }
                    for quote in selection.quotes
                ],
            }
        )
    selected_bookmaker = None
    if decision and decision.selected_odds_observation_id:
        ref = getattr(
            decision.selected_odds_observation.bookmaker, "canonical_ref", None
        )
        selected_bookmaker = (
            ref.canonical_bookmaker.name if ref and ref.canonical_bookmaker_id else None
        )
    return {
        "match": match,
        "position": position,
        "state": state,
        "evaluation": evaluation,
        "decision": decision,
        "selected_bookmaker": selected_bookmaker,
        "action": OUTCOMES.get(decision.action) if decision else None,
        "prediction_outcome": (
            OUTCOMES.get(decision.prediction.predicted_outcome)
            if decision and decision.prediction_id
            else None
        ),
        "prediction_hit": (
            (decision.prediction.predicted_outcome == match.outcome)
            if decision
            and decision.prediction_id
            and match.outcome
            and match.status_short in FINISHED_STATUSES
            else None
        ),
        "decision_reason": REASONS.get(decision.reason, "") if decision else "",
        "state_reason": (
            _reason_label(state.non_placement_reason, state.diagnostics)
            if state and state.non_placement_reason
            else (
                "Capital no colocó una posición"
                if state and state.status == CapitalExecutionState.Status.NOT_PLACED
                else ""
            )
        ),
        "captures": capture_rows,
    }
