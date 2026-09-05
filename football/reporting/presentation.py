"""Spanish presentation helpers; persisted values are never rewritten or inferred."""

import json

AVAILABILITY_REASONS = {
    "INSUFFICIENT_LEAK_SAFE_SELECTION_EVIDENCE": (
        "Historia insuficiente",
        "No hubo evidencia histórica suficiente con selección segura.",
    ),
    "INSUFFICIENT_HISTORICAL_MARKET_OBSERVATIONS": (
        "Sin evidencia de mercado válida",
        "No hay observaciones históricas de mercado suficientes.",
    ),
    "NO_VALID_MARKET": (
        "Sin evidencia de mercado válida",
        "No se conservó un precio de mercado válido para esta evaluación.",
    ),
    "NO_ELIGIBLE_TARGETS": (
        "Sin trabajo elegible",
        "No hubo partidos elegibles para procesar.",
    ),
    "UNAVAILABLE_INSUFFICIENT_RESOLVED_TIMESTAMP_VALID_DECISIONS": (
        "Sin decisiones con precio válido",
        "No hay decisiones resueltas con precio conservado antes del corte.",
    ),
    "INSUFFICIENT_CAPITAL": (
        "Capital insuficiente",
        "La simulación no pudo continuar con el capital disponible.",
    ),
}

DECISION_REASONS = {
    "MODAL_OUTCOME": (
        "Resultado modal seleccionado",
        "Se seleccionó el resultado con mayor probabilidad.",
    ),
    "CONFIDENCE_THRESHOLD_MET": (
        "Umbral de confianza alcanzado",
        "La probabilidad alcanzó el umbral configurado.",
    ),
    "BELOW_CONFIDENCE_THRESHOLD": (
        "Confianza por debajo del umbral",
        "La probabilidad no alcanzó el umbral configurado.",
    ),
    "VALUE_ABOVE_THRESHOLD": (
        "Valor esperado por encima del umbral",
        "El valor esperado superó el umbral configurado.",
    ),
    "NO_POSITIVE_VALUE_ABOVE_THRESHOLD": (
        "Sin valor positivo por encima del umbral",
        "Ninguna selección superó el umbral de valor esperado.",
    ),
    "NO_VALID_MARKET": (
        "Sin mercado válido",
        "No había un precio temporalmente válido para evaluar la selección.",
    ),
    "EXACT_LEGACY_CONTEXT_UNAVAILABLE": (
        "Contexto legacy exacto no disponible",
        "No estaba disponible el contexto exacto requerido por la política legacy.",
    ),
    "UNAVAILABLE_FOR_REPLAY": (
        "No disponible para replay",
        "La decisión no es utilizable por el replay conservado.",
    ),
    "NO_APPROVED_READINESS_PROFILE": (
        "Sin perfil de readiness aprobado",
        "La predicción existe como evidencia exploratoria, pero no es elegible para apuesta.",
    ),
    "READINESS_MODEL_VERSION_MISMATCH": (
        "Perfil no aplicable a esta versión",
        "El perfil activo no aprueba la versión Dixon-Coles utilizada.",
    ),
    "READINESS_MODEL_CONFIG_MISMATCH": (
        "Perfil no aplicable a esta configuración",
        "El perfil activo no aprueba la configuración Dixon-Coles utilizada.",
    ),
    "TRAINING_HISTORY_BELOW_PROFILE": (
        "Historia por debajo del perfil",
        "La evidencia actual no alcanza el requisito versionado del perfil.",
    ),
    "HOME_TEAM_HISTORY_BELOW_PROFILE": (
        "Historia local por debajo del perfil",
        "El equipo local no alcanza el requisito versionado del perfil.",
    ),
    "AWAY_TEAM_HISTORY_BELOW_PROFILE": (
        "Historia visitante por debajo del perfil",
        "El equipo visitante no alcanza el requisito versionado del perfil.",
    ),
    "TRAINING_GRAPH_NOT_CONNECTED": (
        "Grafo histórico no conectado",
        "La evidencia actual no satisface la conectividad exigida por el perfil.",
    ),
}

CAPITAL_STATUSES = {
    "PRODUCED": "Producido",
    "UNAVAILABLE": "No evaluable",
    "FAILED": "Fallido",
}

MATCH_STATUSES = {
    "FT": "Finalizado",
    "Match Finished": "Finalizado",
    "Finalizado": "Finalizado",
    "NS": "No iniciado",
    "Not Started": "No iniciado",
    "TBD": "Horario por confirmar",
    "Time To Be Defined": "Horario por confirmar",
    "PST": "Pospuesto",
    "Match Postponed": "Pospuesto",
    "CANC": "Cancelado",
    "Match Cancelled": "Cancelado",
    "SUSP": "Suspendido",
    "Match Suspended": "Suspendido",
    "1H": "Primer tiempo",
    "HT": "Entretiempo",
    "2H": "Segundo tiempo",
    "ET": "Tiempo extra",
    "P": "Penales",
}


def _present_reasons(value, mapping, unknown_label, unknown_explanation):
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [
            item
            for code in value
            for item in _present_reasons(
                code, mapping, unknown_label, unknown_explanation
            )
        ]
    if not isinstance(value, str):
        return [
            {
                "code": repr(value),
                "label": unknown_label,
                "explanation": "La forma persistida no es un código de motivo reconocible.",
            }
        ]
    label, explanation = mapping.get(value, (unknown_label, unknown_explanation))
    return [{"code": value, "label": label, "explanation": explanation}]


def reason_presentations(value):
    return _present_reasons(
        value,
        AVAILABILITY_REASONS,
        "No evaluable — motivo no clasificado",
        "El código persistido no tiene una explicación de disponibilidad verificada.",
    )


def decision_reason_presentations(value):
    return _present_reasons(
        value,
        DECISION_REASONS,
        "Motivo no clasificado",
        "El código persistido no tiene una explicación de decisión verificada.",
    )


def capital_reason_presentations(value):
    return _present_reasons(
        value,
        AVAILABILITY_REASONS,
        "Motivo de capital no clasificado",
        "El código persistido no tiene una explicación de capital verificada.",
    )


def outcome_label(value):
    return {
        "HOME": "Local",
        "DRAW": "Empate",
        "AWAY": "Visitante",
        "NO_BET": "No seleccionar (NO_BET)",
    }.get(value, value or "—")


def compact_config(config):
    if not config:
        return "configuración predeterminada"
    items = config_items(config)
    visible = [f"{item['key']}={item['value']}" for item in items[:3]]
    if len(items) > 3:
        visible.append(f"+{len(items) - 3}")
    return " · ".join(visible)


def config_items(config):
    if not isinstance(config, dict):
        return [{"key": "valor", "value": _display_value(config)}]
    return [
        {"key": str(key), "value": _display_value(value)}
        for key, value in sorted(config.items(), key=lambda item: str(item[0]))
    ]


def _display_value(value):
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
    if isinstance(value, bool):
        return "sí" if value else "no"
    if value is None:
        return "—"
    return str(value)


def match_status(status_short, status_long):
    label = MATCH_STATUSES.get(status_short) or MATCH_STATUSES.get(status_long)
    if label:
        return {"label": label, "technical": ""}
    technical = status_long or status_short or "sin estado"
    return {"label": "Estado no clasificado", "technical": technical}
