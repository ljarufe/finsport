# FS-021 — Anexo de aprobación y cierre del preflight documental

**Fecha:** 2026-09-23. **Ámbito:** exclusivamente FS-021. **Autoridad:** ticket FS-021 aprobado y F008 v1.8; ejecución F009 v1.14. **Naturaleza:** anexo documental de acuerdos preexistentes, no reescritura del research.

## 1. Fuentes verificadas y ubicación aprobada

- `docs/research/FS-021_integrated_strategy_methodology_research.md`: documento de research aprobado, versionado en Git y editable normalmente. Las correcciones deben distinguirse de decisiones históricas ya tomadas.
- `~/Documents/finsport/FS-021/FS-021_ticket_approved.md`: ticket aprobado **fuera de Git**. No debe copiarse ni versionarse en `docs/`.
- `docs/research/FS-021_approved_scope_addendum.md`: este anexo, editable y sujeto a los hooks normales de Git.

## 2. Jerarquía de decisiones ya aprobadas

El encabezado original del research v2 contiene `RESEARCH_COMPLETE__PENDING_SOURCE_RECONCILIATION` y `NOT_YET_READY_FOR_CODEX`: son los estados históricos **al emitir la investigación**, no el estado actual de implementación. F008 v1.8 y la sección 13 del ticket aprobaron después `P6 READY` y el delta específico FS-021. El ticket prevalece únicamente donde declara expresamente una sustitución para FS-021; la historia de research/E2.3/FS-020 no se reescribe.

- **Depletion:** `FS021_OPERATIONAL_DEPLETION_5U_AFTER_ALL_OPEN_V2`, banca global única 100u por candidato, pausa reversible con OPEN vivas y terminación definitiva únicamente después de la última OPEN con equity <=5u. Ruina económica y policy termination continúan siendo motivos distintos.
- **Alcance de inferencia:** T+120, T+130 y T+150 solo para los 693 paths observados; bootstrap confirmatorio únicamente T+150, L=1,2,4, 5.000 réplicas paired por diseño, 231 candidatos íntegros y doce slices. `CROSS_LAG_INFERENCE=NOT_EVALUATED_BY_FS021_V1`.
- **Producto vs ciencia:** criterio práctico maximin sobre los tres lags con gates A/B/C, actividad ≥38 PLACED, ≥3 competiciones y ≥4 semanas por lag. Si ningún candidato es admisible, elegir exactamente un `DIAGNOSTIC_ONLY__NO_NEW_STAKES` (no una estrategia supuestamente segura). Scientific leader/disposition T+150 separado y ninguna activación operacional.
- **Errata D05:** ejecutar **TRES** posiciones OPEN iniciales y tres settlements sucesivos. La alusión histórica a dos OPEN es editorialmente incorrecta; conservarla como errata documentada, no adaptar la prueba al texto contradictorio.

## 3. Preferencias operacionales aceptadas durante ejecución

No modifican metodología ni resultados: progreso TTY breve con numerador que solo cuenta réplicas completas, checkpoints inmutables/reanudación por shard, monitor independiente, observación CPU/NVMe/RAM/disco y `PAUSE_RESOURCE`. Alarma probada con altavoces por el maintainer: 740 Hz ~0,22 s y 920 Hz ~0,28 s; silencio entre tonos ~0,06 s y final ~0,04 s; repetir aproximadamente cada 4 s hasta ACK explícito para PAUSE_RESOURCE, STOP_TECHNICAL, salida inesperada o COMPLETE. No alarmar por depletion individual ni checkpoints. ACK solo silencia, jamás reanuda automáticamente. La alarma no puede garantizar sonido durante una pérdida de energía.

Recursos observados antes del desarrollo: disco libre 191 GB; RAM disponible ~20 GiB; 24 CPUs lógicas; CPU package 48 °C y NVMe Composite 42 °C en reposo. Presupuesto preventivo inicial propuesto y configurable: cuatro workers; CPU ≥80 °C, NVMe Composite ≥70 °C, RAM disponible <4 GiB, libre <80 GiB, nuevos artifacts >50 GiB ⇒ PAUSE_RESOURCE. Los valores operacionales son límites de prevención, no resultados científicos ni certificación térmica.

## 4. Incidente del proceso — conservar en el handoff final

**Identificador:** `FS021_PROCESS_PRECODE_RESEARCH_COPY_OMITTED`.

**Hecho:** el primer prompt de Codex se generó tras el preflight de datos sin comprobar que el research aprobado estuviera en el checkout ni que el ticket íntegro estuviera accesible **fuera del repositorio**. Se detectó por observación del maintainer antes de continuar con la implementación. El archivo de research existía como adjunto de conversación, no como fuente versionada de ese checkout. No confundir con pérdida o corrupción de evidencia FS-018/019/020.

**Causa de proceso:** la preparación comprobó la integridad del material científico y el entorno, pero omitió el paso `maintainer-owned artifacts copied` de F009 entre creación de rama y preflight técnico. Se generó un prompt condicionado a documentos que Codex podría no tener disponibles localmente.

**Corrección:** conservar el research y el anexo en `docs/research/` y el ticket únicamente fuera de Git. La primera versión del helper colocaba indebidamente el ticket en `docs/development/`; el maintainer detectó y eliminó esa copia. Codex Pass 1 reprodujo el error, corregido manualmente.

**Prevención en el handoff:** introducir un check binario `APPROVED_RESEARCH_IN_CHECKOUT_AND_TICKET_ACCESSIBLE_OUTSIDE_GIT` en la preparación F009 cuando Codex deba consultar documentos adjuntos. No repetir todo el preflight ni abrir un pass Codex exclusivo para copiar archivos. Considerar una actualización dirigida de F009 solamente en el cierre, si el equipo decide que la regla durable necesita explicitación adicional.

## 5. Estado real de los gates

El preflight restauró FS-018/019/020 y el binding FS-019 de 33×1.877 = 61.941 filas; se conserva la copia durable FS-019 en `/home/ljarufe/Documents/finsport/research-evidence/FS-019/E2_phase3_fs019_binding_pack/`. Mantener `PRESERVE_ACTIVE` y los consumidores FS-021/FS-022. Pass 1 reportó PASS de conformance y equivalencia. Este correctivo requiere repetir los tres gates técnicos funcionales antes de la corrida económica; no se revalidan hashes de los documentos ni de archivos heredados. Este anexo no equivale a una UAT independiente.

El research permanece versionado y editable; no editar F001/F003/F006/F010 como condición previa porque F008 v1.8 cerró la supersesión específica FS-021.


## 6. Corrección de proceso — 2026-09-24 (sustituye los requisitos SHA anteriores)

Por decisión expresa del maintainer, los documentos de research/anexos y el
código son editables y se formatean con los hooks habituales. Se retiran los
`exclude` de pre-commit, los hashes fijos de paquetes/archivos heredados,
la comparación de bytes con workspace/index/HEAD y la invalidación automática
por modificaciones de código o documentación. Cualquier indicación de este
anexo sobre preservar hashes de documentos o recertificar SHA tras hooks queda
**supersedida**. No regenerar ni recuperar los SHA documentales anteriores.

FS-021 conserva únicamente comprobaciones funcionales del experimento:
33×1.877 observaciones, emparejamiento, coherencia Prediction/Decision/precio,
conformance CURRENT/V2R, equivalencia de runner y lectura segura de checkpoints.
Los fingerprints calculados automáticamente al ejecutar sirven solo para
identificar los **datos de esa corrida**, no para bloquear ediciones de archivos.
Si cambia la lógica económica durante una corrida, crear otra ejecución.

Incidente a registrar en el handoff: el exceso de pines de SHA introdujo
excepciones indebidas de pre-commit y retrabajo tras `make format`; el maintainer
las retiró manualmente. La preparación también intentó incorporar el ticket a
Git; el ticket permanece exclusivamente en su ubicación externa.
