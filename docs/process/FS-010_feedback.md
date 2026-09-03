# FS-010 — IMPLEMENTATION SNAPSHOT — MAY BECOME STALE

Status: IMPLEMENTATION SNAPSHOT — MAY BECOME STALE / PASS 2 PRE-UAT / UAT PENDING
Ticket: FS-010 — Construir evidencia longitudinal comparable de CapitalPolicies con resultados reales
Branch: `FS-010-longitudinal-capital`

## Resultado

FS-010 añade una serie longitudinal primaria persistente para comparar las siete
familias `CapitalPolicy` sobre un único prefijo cronológico prospectivo de
`DIXON_COLES + MODAL_ALL`.

La implementación conserva la separación:

```text
Prediction != Decision != CapitalPolicy != real bet
```

No selecciona ganador, no modifica fórmulas predictivas/de decisión/capital, no
añade scheduler y no realiza llamadas de provider ni escrituras financieras.

## Correcciones consolidadas de Pass 2

- La higiene CANC reconoce dependencias longitudinales tanto en el prefijo
  `decision_ids` como en `first_gap.decision_id` y
  `first_gap.batch_decision_ids`. No considera Decisions posteriores arbitrarias.
- La home ya no renderiza la lista completa de Decision IDs. Muestra snapshot,
  muestra, hash del manifest, engine, comparador, cohorte, epoch/watermark y el
  contrato de provenance temporal; el manifest persistido conserva todos los IDs.
- Inicialización y construcción de basis están dentro del límite estructurado de
  error de Capital. Si no puede verificarse currentness, el puntero vigente se
  limpia conservadoramente y el snapshot histórico se conserva.
- Cuando Capital ya emitió la causa primaria, el pipeline conserva su evento
  terminal de liveness pero no duplica el traceback causal.
- Reporting tiene evidencia directa de `FAILED + diagnostic` con `metrics = {}` y
  representa todos los valores ausentes mediante guiones neutrales.

## Persistencia y migración

La migración aditiva `0008`:

- crea `CapitalLongitudinalSeries` con identidad, evidence class, comparador,
  cohorte congelada/hash, epoch, modo, bankroll, configuración exacta y puntero
  one-to-one al snapshot vigente;
- vuelve nullable `CapitalExperiment.source_experiment`;
- añade `CapitalExperiment.longitudinal_series`;
- exige por constraint que cada `CapitalExperiment` tenga exactamente un owner;
- no reescribe ni elimina evidencia Capital existente.

La migración sólo fue ejercitada en bases aisladas de test. No se aplicó sobre la
base PostgreSQL local del maintainer.

## Construcción de basis y currentness

La inicialización primaria captura una sola vez las `Competition.enabled` y
persiste el epoch cerrado `2026-08-26T21:34:33.795715Z`. Recomputes posteriores
usan exclusivamente esa cohorte congelada.

El builder DB-only:

- selecciona `PROSPECTIVE / DIXON_COLES / MODAL_ALL` desde el epoch;
- ordena por `decision_time`, usando `id` sólo para auditoría estable dentro del
  lote;
- trata tiempos iguales como un único lote económico;
- conserva `NO_BET` con exposición cero;
- valida outcome y provenance exacto del precio seleccionado;
- detiene el watermark en el primer lote con gap accionable y no salta evidencia
  posterior;
- persiste por Decision la identidad/config real de Prediction y Decision;
- genera manifiesto/hash determinista con cohorte, epoch, watermark, lotes,
  diagnóstico del primer gap y snapshots canónicos.

Ante un cambio semántico, el puntero vigente se limpia antes de ejecutar el nuevo
replay. El replay siempre reconstruye desde el epoch. Un hash/config idéntico
retorna `NO_WORK`; un snapshot histórico idéntico se reutiliza; una corrección
genera un snapshot nuevo. Snapshots anteriores pueden permanecer auditables, pero
el reporting sólo consume el puntero vigente.

## Motor y siete brazos

`run_capital_experiment()` permanece como wrapper compatible y delega, junto con
la ruta longitudinal, en un runner de basis preparado compartido. Replay,
policies, ledgers y métricas continúan perteneciendo al motor FS-004.

Los siete brazos usan exactamente la configuración de referencia FS-010. Cada
uno persiste `PRODUCED`, `UNAVAILABLE + reason` o `FAILED + reason`. La
concurrencia de recovery en un lote simultáneo permanece `UNAVAILABLE`; no se
serializa ni reduce el stream. Kelly conserva Decisions con edge no positivo y
aplica exposición cero.

## Integraciones

- El pipeline ejecuta un único recompute longitudinal DB-only dentro de la fase
  `CAPITAL`, después de higiene/settlement y además del baseline independiente.
- No depende de que el ciclo haya creado un `PredictionExperiment`.
- Higiene CANC elimina snapshots afectados por el prefijo o primer gap y
  `SET_NULL` limpia el puntero vigente.
- El comando `recompute_longitudinal_capital` ofrece el entry point manual JSON.
- Reporting histórico separa Capital longitudinal vigente de los experimentos
  independientes REPLAY/MONTE_CARLO/STRESS y presenta estados/métricas en español
  sin ranking ni métricas inventadas.
- Fallas inesperadas emiten un único traceback primario en Capital, correlacionado
  con `PipelineRun`; gap, `NO_WORK` y `UNAVAILABLE` de dominio no generan incidentes.

## Evidencia automatizada

- Suite focal corregida de Pass 2: `100 passed`.
- Suite longitudinal FS-010: `17 passed`.
- Suite completa: `313 passed`.
- Cobertura total: `86.78%` (mínimo requerido: `80%`).
- `make check`: PASS.
- `git diff --check`: PASS.
- `makemigrations --check --dry-run`: sin cambios.
- `pip check`: sin dependencias rotas.
- `pip-audit --local`: sin vulnerabilidades conocidas.

## UAT y validación diferida

PENDING:

- aplicar `0008` mediante el flujo autorizado por el maintainer;
- ejecutar el comando contra la DB real y confirmar el cohort/hash, el prefijo de
  seis Decisions, watermark cerrado y gap de Decision 10903;
- UAT visual/browser del bloque longitudinal.

No se inventaron resultados UAT.

## New Work Discovered

Ninguno.
