# FS-005 — Feedback final reconciliado

**Estado del documento:** `FINAL RECONCILED FEEDBACK`

## Identidad y outcome

- Ticket: `FS-005 — Implementar captura temporal de odds quota-aware`.
- Branch: `FS-005-odds-capture-planner`.
- Base de inicio: `master` post-FS-004, SHA de preflight `1e93e97c81888c688f0955927f3ea43dc818286c`.
- Modo: `local-only / demo-only / research-oriented`.
- Research durable: `docs/research/FS-005_odds_cadence_quota_research.md` — `REFERENCE ONLY`.
- Side effects financieros: ninguno.

Outcome entregado:

```text
scheduler/manual wake
→ planner DB-only
→ deterministic due work
→ bounded executor
→ API-Football GET-only
→ OddsObservation append-only
→ OddsSnapshot latest projection
→ canonical result refresh
→ CaptureRun/CaptureWorkItem audit
```

Automatic capture queda `default OFF`; el camino manual permanece disponible.

## Arquitectura implementada

Nuevo boundary reusable:

```text
football/capture/
├── contracts.py
├── planner.py
├── executor.py
├── locks.py
├── service.py
└── __init__.py
```

Servicio compartido:

```python
from football.capture import run_capture
```

Entry points:

- management command `run_football_capture`;
- Celery task `football.capture.wake`;
- conditional Beat schedule;
- Django Admin para `CaptureRun` y `CaptureWorkItem`.

Persistencia:

- `CaptureRun`: una invocación real manual/scheduler con resumen, quota y efectos;
- `CaptureWorkItem`: unidad lógica de trabajo/ventana/target con estado, attempts, quota evidence y efectos.

Dry-run:

```text
provider calls = 0
CaptureRun writes = 0
CaptureWorkItem writes = 0
OddsObservation writes = 0
external effects = 0
```

## Semántica temporal, quota e idempotencia

Se mantienen separados:

```text
target_at
not_before
not_after
executed_at
observed_at
lateness
```

No backdating.

FS-005 usa provider headers como autoridad cuando son utilizables, epoch/reset UTC, accounting conservador de attempts, mandatory reserve, re-gate por page/retry y bounded bootstrap.

Optional odds sobre `BOUNDED_BOOTSTRAP` requieren opt-in explícito.

Prioridad final bajo presión de cuota:

```text
mandatory result debt
→ due odds
→ discovery due
```

Single-flight:

```text
PostgreSQL advisory lock
finsport:fs005:api_football
```

La identidad lógica de odds es:

```text
provider + fixture + market + intended window + target_at
```

Una intended window fulfilled no se reejecuta; una ventana posterior legítima sí.

Después de cualquier provider attempt real, una identidad no fulfilled no vuelve a autoejecutarse silenciosamente.

## Result refresh

El refresh:

- reutiliza `sync_fixture_payloads`;
- conserva `Match.outcome` como autoridad canónica;
- está protegido por reserve;
- es bounded;
- no hace polling infinito de terminal no-outcome;
- actualiza postponement/reschedule y timing cuando corresponde.

Corrección final de PR review:

`FOOTBALL_CAPTURE_HORIZON_HOURS` es horizonte de elegibilidad **futura** para captura, no TTL retrospectivo de result debt.

Contrato final:

```text
unresolved nonterminal result debt
→ no expira sólo por edad

terminal no-outcome
→ explicit stopping semantics
```

Se añadió regresión focalizada.

## Findings corregidos

### Pass 2

1. Optional odds bootstrap ahora exige opt-in explícito independientemente del reserve.
2. Discovery dejó de preemptar due odds: `result debt → due odds → discovery`.
3. Cualquier `actual_attempts > 0` no fulfilled protege la same identity contra retry automático silencioso.
4. Competition/day stratum usa `America/Lima`; kickoff absoluto y quota epoch continúan UTC.

### PR review

5. Un unresolved result debt podía desaparecer al superar `FOOTBALL_CAPTURE_HORIZON_HOURS`.

Fix directo y localizado: se retiró ese lower bound retrospectivo y se añadió regresión.

## Evidencia automatizada

Pass 2 consolidado:

- Black/Ruff: PASS.
- focused FS-005 evidence: 90 tests PASS.
- API-Football/Inkabet regression: 45 tests PASS.
- `make check`: PASS.
- repository tests: 197 PASS.
- Django check: PASS.
- migration drift: `No changes detected`.
- `git diff --check`: PASS.
- complete relevant diff review: PASS.
- seis warnings deprecados externos de `penaltyblog`, no pertenecientes a FS-005.

Después del fix de PR review se ejecutó evidencia focalizada sobre result semantics; GitHub CI/review final quedó verde según reporte del maintainer.

No se repitió UAT live ni el general gate por ceremonia porque el fix era focalizado y no invalidaba provider transport, quota accounting, persistence ni scheduler lifecycle.

## UAT final

### UAT A — dry-run

Match `1158`, API fixture `1570362`, Sevilla – Atletico Madrid:

- `DRY_RUN`;
- 0 provider attempts/pages/retries;
- 0 DB writes;
- bounded bootstrap plan explícito.

### UAT B — real odds capture

Mismo fixture:

- `SUCCESS`;
- 1 provider attempt;
- 1 page;
- 0 retries;
- 13 `OddsObservation`;
- 13 `OddsSnapshot` cambiados/creados;
- `run_id=1`;
- quota remaining: `97`.

`observed_at` fue real, no backdateado.

### UAT C — same-window idempotency

Misma logical identity:

```text
api_football:odds:1570362:1:middle:2026-08-28T17:30:00+00:00
```

Resultado:

- `NO_WORK`;
- `ALREADY_FULFILLED`;
- 0 provider calls;
- 0 new observations;
- quota intacta en `97`.

### UAT D — bounded result refresh

Match `1142`, API fixture `1570336`, Celta Vigo – Osasuna:

- `SUCCESS`;
- 1 provider attempt;
- 1 page;
- `fixtures_changed=1`;
- `matches_resolved=1`;
- canonical outcome `AWAY`;
- `FT`, 1–2;
- quota remaining `96`;
- `run_id=3`.

### UAT E/F — scheduler + Admin/DB audit

Se validó:

```text
default disabled
→ no FS-005 Beat schedule

enabled safe override
→ scheduler wake

restart enabled
→ scheduler wake vuelve a aparecer

restore normal
→ default OFF restaurado
```

Scheduler runs post-baseline:

- IDs `15` y `16`;
- 2 runs;
- 0 provider attempts;
- 0 failures;
- skips explícitos `MISSED_WINDOW` / `NOT_DUE`.

Admin fue inspeccionado manualmente.

Audit DB read-only confirmó:

- 3 manual runs;
- 2 scheduler runs post-baseline;
- 13 OddsObservation;
- 13 OddsSnapshot;
- scheduler attempts = 0;
- scheduler failures = 0;
- match 1142 resuelto `AWAY`, `FT`, 1–2.

## Provider-call accounting del UAT

```text
odds capture → 1
result refresh → 1
total → 2
```

No hubo:

- live 429/timeout/5xx probes;
- failed-call accounting probe;
- Inkabet calls desde FS-005;
- bookmaker auth;
- betting;
- Selenium betting;
- financial writes.

## Acceptance final

```text
47 PASS
0 PENDING
3 N/A
```

N/A:

- live 429/timeout/5xx triggering;
- failed-call quota probe `NOT PLANNED`;
- real betting/bookmaker auth/Selenium/financial mutation.

A48 queda PASS con este `FINAL RECONCILED FEEDBACK`.

## Pass budget

- Pass 1 — implementation.
- Closure continuation documental para completar factual snapshot omitido; no correction pass.
- Pass 2 — única corrección consolidada pre-UAT.
- No Pass 3 de UAT.
- Finding de PR review corregido directamente por ser pequeño/localizado; no nueva pasada Codex.

## Warning/deferred

- Seis warnings `penaltyblog`: externos/no FS-005.
- Automatic capture permanece default OFF.
- Temporal history no acumula autónomamente hasta habilitación/configuración explícita.
- Shipped offsets no son una política óptima congelada.
- No email/Slack/dashboard de observabilidad.
- No real betting.

## New Work Discovered — lifecycle de partidos cancelados/no realizados

Nueva decisión del maintainer:

> Cuando un partido quede definitivamente cancelado/no realizado y deje de ser relevante para experimentación, no interesa conservar datos dependientes inútiles asociados, incluidas odds, predicciones y demás evidencia derivada.

No se absorbe en FS-005 después de review estable.

Debe volver a F006/F008 para disposición y definición.

El siguiente diseño debe cerrar:

- qué estado significa cancelación definitiva/no realización;
- cómo distinguirlo de postponement/reschedule, que no debe limpiarse prematuramente;
- tratamiento de `OddsObservation` / `OddsSnapshot`;
- `Prediction` / `Decision`;
- source refs;
- `CaptureWorkItem` y audit;
- capital/evaluation rows derivadas;
- experiments/agregados multi-match que quedarían stale;
- si `Match` permanece como tombstone/status o también se elimina;
- orden/cascade;
- idempotencia;
- audit del cleanup;
- guardas contra borrar evidencia de partidos válidos.

Disposición recomendada para F008:

```text
candidate ABSORB into FS-006 post-match lifecycle
```

si sigue siendo un outcome coherente. Si el riesgo destructivo/provenance exige boundary independiente, F008 debe dividirlo deliberadamente.

## Process learnings

1. En tickets materiales/multi-boundary, el factual implementation snapshot de Pass 1 debe pedirse explícitamente en kickoff.
2. Una closure continuation exclusivamente documental no consume correction pass si no cambia lógica.
3. Execution chat posee el `FINAL RECONCILED FEEDBACK`.
4. No usar Codex sólo para wording final.
5. Findings de review pequeños/localizados pueden corregirse directamente con evidence-by-delta.
6. Un scripted lifecycle UAT no debe asumir que `make up` devuelve el prompt; usar Compose detached o dos terminales cuando se necesita continuar automáticamente.
7. Evidence-by-delta evitó repetir provider UAT y suites completas tras el fix de review.

## Source projection requerida

No regenerar F001–F010 en bloque.

- `F001`: FS-005 pasa de `IN DEVELOPMENT` a capability actual; automatic capture sigue default OFF.
- `F002`: proyectar sólo semánticas durables; incorporar cleanup de cancelados cuando F008 cierre el contrato exacto.
- `F003`: añadir capture package, audit models, `run_capture`, advisory lock, command y Celery wake.
- `F004`: añadir operación/config de capture, reserve/bootstrap, Admin audit y default-off lifecycle.
- `F006`: marcar FS-005 `COMPLETED`, reconciliar FS-006 y registrar finding de cancelados.
- `F009`: evaluar promoción de los process learnings anteriores.
- `F000`: actualizar sólo si cambian catálogo/estado/versiones activas.
- `F005`: sin cambio, `NOT USED`.
- `F007`: sin cambio feature-specific.
- `F008`: la guía no cambia; debe ingerir/disponer el new finding.
- `F010`: sin cambio.

## Estado de cierre

```text
READY FOR FINAL DOCUMENTATION COMMIT
→ SQUASH MERGE
→ MASTER SYNC / CLEANUP
→ PLANKA DONE
→ MAIN-CHAT HANDOFF
```
