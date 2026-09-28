"""Retained Spanish reason labels for explicit research/readiness diagnostics."""

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
    "APPROVED_READINESS_PROFILE_PASSED": (
        "Perfil de preparación aprobado y satisfecho",
        "La predicción cumple los requisitos del perfil vigente de su modelo y competición.",
    ),
    "READINESS_PROFILE_STALE": (
        "Perfil de preparación pendiente de actualización",
        "La evidencia deportiva o las reglas cambiaron; el mantenimiento automático revalidará el perfil.",
    ),
    "CLASS_SUPPORT_BELOW_PROFILE": (
        "Evidencia de resultados por debajo del perfil",
        "La historia de resultados no alcanza el requisito versionado del perfil.",
    ),
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
        "El perfil activo no aprueba la versión del modelo utilizada.",
    ),
    "READINESS_MODEL_CONFIG_MISMATCH": (
        "Perfil no aplicable a esta configuración",
        "El perfil activo no aprueba la configuración del modelo utilizada.",
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
