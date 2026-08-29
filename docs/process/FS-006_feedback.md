# FS-006 — FINAL RECONCILED FEEDBACK

**Ticket:** FS-006 — Automatizar pipeline prospectivo end-to-end multi-liga
**Branch:** `FS-006-prospective-pipeline`
**Fecha de cierre:** 2026-08-28
**Estado:** TECHNICALLY COMPLETE / READY TO MERGE
**Runtime boundary:** local-only / demo-only / research-oriented
**Financial side effects:** none

## Outcome

FS-006 implementó y validó un pipeline prospectivo reutilizable que compone:

Capture
→ Prediction
→ Decision
→ canonical settlement
→ normalized research Capital
→ cancellation hygiene
→ persisted report

El pipeline quedó demostrado con datos reales de múltiples ligas, provider real, odds reales, scheduler Celery Beat y estados negativos/degradados explícitos.

Se preserva el invariant:

Prediction != Decision != CapitalPolicy != real bet

No se añadió ni ejecutó ninguna capacidad de apuesta real.

## Arquitectura implementada

`football.pipeline.run_pipeline` es el boundary reusable principal.

El pipeline delega a servicios existentes o especializados y no shell-out a management commands desde Python.

Las fases son:

- CAPTURE
- PREDICTION
- RESULT_SETTLEMENT
- CAPITAL
- REPORT

Cada fase expone estados explícitos como:

SUCCESS
NO_WORK
SKIPPED
UNAVAILABLE
DEGRADED
FAILED

`PipelineRun` persiste:

- cycle UUID;
- cutoff/planning time;
- estados de fases;
- CaptureRun IDs;
- PredictionExperiment IDs;
- CapitalExperiment IDs;
- warnings/errors;
- config snapshot;
- `fs006-report-v1`.

## Scheduler

Se añadió:

`FOOTBALL_PIPELINE_ENABLED=False`

por defecto.

Cuando pipeline automation está habilitado:

`football.pipeline.wake`

es el único owner automático que puede entrar al capture path.

Si simultáneamente:

FOOTBALL_PIPELINE_ENABLED=True
FOOTBALL_CAPTURE_ENABLED=True

Beat registra únicamente:

`football-pipeline-wake`

y no registra el standalone:

`football-capture-wake`

El comando manual `run_football_capture` y la task callable `football.capture.wake` permanecen disponibles.

## Prospective Prediction identity

La identidad persistente final es:

competition
+ America/Lima local day
+ FS-005 intended_window
+ target_at

La DB protege la unicidad de esa identidad para PredictionExperiment prospectivos.

Además, cada experimento congela en config:

`target_match_ids`

con el lote exacto de fixtures elegibles correspondiente a esa identidad temporal.

### Pre-UAT correction

El review de Pass 1 detectó que el pipeline calculaba correctamente el lote de `match_ids`, pero `predict_competition_day()` volvía a consultar todos los fixtures elegibles de la competición/día.

Eso permitía que un fixture cuya propia ventana FS-005 todavía no había llegado apareciera prematuramente en el experimento de otro fixture.

La corrección final:

- añadió `match_ids=None` al boundary reusable;
- preservó el comportamiento histórico cuando no se suministran IDs;
- normalizó sorted/unique IDs;
- intersectó el lote explícito con la elegibilidad prospectiva real;
- pasó el lote exacto desde el pipeline;
- congeló `target_match_ids`;
- añadió una regresión con same competition/day, shared target y later target.

La identidad temporal original no cambió.

## Settlement

El settlement prospectivo es DB-only y canónico.

Sólo resuelve Predictions cuando:

- Match.status_short pertenece a FINISHED_STATUSES;
- Match.outcome es HOME/DRAW/AWAY.

Actualiza:

- Prediction.actual_outcome;
- Prediction.evaluated_at;
- summary del PredictionExperiment.

No reescribe:

- Decision.action;
- Decision.reason;
- Decision.selected_price;
- Decision.selected_odds_observation.

La segunda ejecución es idempotente y devuelve NO_WORK cuando no queda nada nuevo por resolver.

## Capital baseline

FS-006 utiliza exclusivamente el comparator de investigación normalizado:

mode = REPLAY
initial_bankroll = 100
policy = FLAT_UNIT
unit = 1

Basis:

DIXON_COLES / MODAL_ALL

Es una base de medición de research, no una selección de modelo/policy productiva.

Cuando la evidencia es insuficiente:

UNAVAILABLE

se conserva como resultado válido y no se fabrica un CapitalExperiment.

Las ejecuciones equivalentes son idempotentes mediante identidad derivada del experimento fuente, input hash y configuración congelada.

## Cancellation hygiene

El único trigger destructivo es exactamente:

Match.status_short == "CANC"

Se preservan:

- Match;
- MatchSourceRef;
- canonical CANC state;
- CaptureRun;
- CaptureWorkItem.

Se eliminan los derivados inválidos:

- OddsSnapshot;
- OddsObservation;
- Prediction;
- Decision.

Antes de eliminar Decisions se inspeccionan todos los:

CapitalExperiment.input_manifest.decision_ids

y se invalida/elimina el CapitalExperiment completo cuando depende de una Decision afectada.

Esto incluye experimentos estocásticos sin ledger.

Los summaries de PredictionExperiment afectados se recomputan.

PST, SUSP, FT y estados ambiguos no son triggers destructivos.

La limpieza es transaccional, dry-runnable e idempotente.

## Multi-league operation

El pipeline no hardcodea ligas y trabaja desde:

Competition.enabled

Durante UAT se amplió deliberadamente el pilot operacional a:

- Premier League / API-Football 39
- Bundesliga / API-Football 78
- Serie A / API-Football 135
- La Liga / API-Football 140

Las ligas son configuración/datos operacionales, no constantes del pipeline.

API-Football permanece como autoridad canónica.

Inkabet permanece como fuente secundaria read-only de market evidence.

## Automated evidence

Antes de UAT:

- FS-006 focused suite: 16 passed.
- Prediction regression directamente afectada: 25 passed.
- `make check`: PASS.
- Repository suite pre-review: 214 passed.
- Black: PASS.
- Ruff: PASS.
- Django system check: PASS.
- Migration drift: `No changes detected`.
- `git diff --check`: PASS.
- Acceptance ledger A01–A47: 47 PASS / 0 PENDING / 0 N/A.

Después de los findings tardíos, los tests focalizados afectados y `make check` completo volvieron a pasar.

Se mantienen seis warnings existentes de compatibilidad Penaltyblog/NumPy.

## UAT real

### A — persistent migration + dry-run

Se aplicó `football.0005_pipeline_run_and_prospective_identities`.

Dry-run real:

- provider attempts = 0;
- capture state = SKIPPED;
- zero pipeline/domain writes;
- planner encontró trabajo debido de forma read-only.

PASS.

### B — bounded provider execution

Se ejecutó un RESULT_REFRESH real con API-Football.

Resultado:

- provider attempts = 1;
- provider pages = 1;
- retries = 0;
- quota 96 → 95;
- capture = SUCCESS;
- settlement = SUCCESS;
- capital unavailable cuando correspondía.

PASS.

### Bootstrap multiliga

Se refrescó catálogo y se habilitaron las competiciones del pilot.

`sync_football_day --with-odds` produjo datos reales multi-liga y market evidence:

- API-Football;
- Inkabet fail-soft/read-only.

No se realizó ninguna acción financiera.

### C — real multi-league prospective pipeline

PipelineRun real `id=2`:

- pipeline status = DEGRADED;
- capture = SUCCESS;
- prediction = SUCCESS;
- settlement = SUCCESS;
- capital = DEGRADED;
- cuatro PredictionExperiments creados;
- tres competiciones reales representadas.

Competitions con experimentos:

- Premier League;
- Bundesliga;
- La Liga.

La degradación fue honesta: capital produjo resultados para algunos streams y dejó otros UNAVAILABLE.

Se produjeron dos normalized capital baselines reales.

PASS.

### D — controlled settlement + capital

Test DB aislada:

- unresolved → NO_WORK;
- canonical final → settlement;
- Decision frozen;
- exact 100u / FLAT_UNIT 1u;
- idempotency;
- unavailable creates no invalid experiment.

3 focused cases passed.

PASS.

### E — synthetic CANC lifecycle

Test DB aislada:

- dry-run;
- execute;
- Match/ref/capture audit preserved;
- odds/prediction/decision derivatives removed;
- deterministic capital invalidated;
- stochastic no-ledger dependency invalidated;
- summary recomputed;
- rerun NO_WORK;
- PST/FT/SUSP/UNKNOWN untouched.

5 cases passed.

PASS.

### F — scheduler lifecycle

Se verificó:

default:
FOOTBALL_PIPELINE_ENABLED=False
CELERY_BEAT_SCHEDULE={}

enabled with both automation flags:
only `football-pipeline-wake`

Se arrancó Celery Beat realmente dos veces mediante procesos UAT desechables.

Ambos boots pasaron.

La configuración normal final volvió a:

FOOTBALL_PIPELINE_ENABLED=False
CELERY_BEAT_SCHEDULE={}

PASS.

### G — persisted report

`PipelineRun.report` persistió correctamente:

schema_version = fs006-report-v1

Incluye:

- phases;
- competitions;
- sample sizes;
- capture/provider evidence;
- prediction experiments;
- settlement;
- capital;
- cancellation summary;
- versions/config;
- warnings.

No se detectaron secret-like keys.

PASS.

## Git / hook findings

### UTC quota test flake

Durante el pre-push hook apareció un failure en:

`test_current_utc_header_and_later_attempts_form_conservative_quota_state`

La implementación productiva era correcta.

La fixture usaba:

`timezone.now() - 10 minutes`

y el push se ejecutó pocos minutos después de las 00:00 UTC.

La supuesta observación "current UTC epoch" quedó accidentalmente en el día UTC anterior, por lo que el sistema correctamente eligió `BOUNDED_BOOTSTRAP`.

El test fue corregido para usar un instante aware determinista.

Aprendizaje:

tests cuyo contrato depende de day/epoch/reset boundaries no deben depender del wall clock real.

Usar:

- aware fixed datetime para escenarios simples;
- time freezing cuando múltiples capas consultan el reloj o se necesita avanzar el tiempo.

### PR review finding

GitHub/Codex review encontró un finding P2 válido en `_phase_status`.

La implementación trataba:

FAILED + NO_WORK

como recuperación parcial y clasificaba el pipeline `DEGRADED`.

Semántica corregida:

FAILED + only NO_WORK
→ FAILED

FAILED + actual SUCCESS
→ DEGRADED

Se añadió regresión focalizada y el gate final volvió a pasar.

## Runtime / environment finding

Al arrancar el stack después de la implementación, el worker Celery existente falló durante autodiscovery:

`ModuleNotFoundError: No module named 'numpy'`

El nuevo import graph:

football.tasks
→ football.pipeline
→ football.capital
→ metrics
→ numpy

hizo visible que la imagen local persistente estaba stale.

`make build` seguido de `make up` resolvió el runtime.

Los boots posteriores de Celery Beat pasaron.

Aprendizaje durable para UAT/handoff:

cuando el delta cambia dependencies, Docker image contents, schema o el import graph de servicios persistentes, la preparación operacional necesaria debe indicarse explícitamente.

Patrón esperado cuando aplique:

make build
→ migrate
→ make up
→ smoke de procesos persistentes

No asumir que un contenedor previamente construido representa el checkout actual.

## Reconciliation observation

Después de incorporar Inkabet aparecieron cuatro CompetitionSourceRef PENDING.

No se habían creado nuevas Competition desde Inkabet:

- `competition` era null;
- sólo existía `proposed_competition`.

Tres referencias revisadas por el maintainer fueron reconciliadas manualmente.

Una propuesta incorrecta `Serie C → Serie A` fue eliminada.

No se cambia FS-006 para este caso.

## New Work Discovered

### NWD-1 — durable maintainer-ignore state

El reconciliador secundario necesita eventualmente un estado durable equivalente a:

IGNORED_BY_MAINTAINER

para una entidad externa ya revisada y deliberadamente fuera de scope.

Objetivo:

- conservar external identity/evidence;
- no convertirla de nuevo en PENDING;
- no generar reconciliation noise repetidamente;
- permitir una futura reapertura explícita.

No crear este ticket automáticamente.

### NWD-2 — shared quota state/provenance

Durante bootstrap/UAT se observaron snapshots de cuota inconsistentes entre manual sync y capture planning.

Ejemplos observados incluyeron un `daily_remaining` reportado por sync diferente del quota snapshot leído posteriormente por capture, hasta recibir un nuevo header real del proveedor.

No se produjo sobreconsumo y el provider response posterior volvió a dar evidencia real de cuota.

Investigar en trabajo futuro:

- provenance del quota snapshot;
- manual sync entry points;
- capture entry point;
- epoch/reset semantics;
- necesidad de una fuente compartida de quota state.

No asumir todavía una causa concreta.

### NWD-3 — Penaltyblog / NumPy compatibility

La suite verde mantiene seis DeprecationWarnings procedentes de Penaltyblog bajo NumPy 2.5.

Actualmente no son failures.

Investigar separadamente:

- upgrade compatible de Penaltyblog;
- upstream fix;
- dependency pin sólo si fuera necesario.

No silenciar warnings como solución.

## Safety / exclusions

Confirmado durante implementación y UAT:

- no real betting;
- no bookmaker authentication;
- no cookies de bookmaker;
- no Selenium betting;
- no external financial write;
- no CapitalPolicy promotion;
- no winner selection;
- no generic observability platform;
- no generic provider framework;
- no destructive PostgreSQL reset;
- no Redis purge.

El pipeline permanece research-oriented.

## Source reconciliation required after merge

El chat principal debe proyectar selectivamente los hechos durables.

F003:
- PipelineRun;
- pipeline orchestration boundary;
- prospective identity;
- settlement/capital/hygiene boundaries;
- single automatic scheduler ownership.

F004:
- operator pipeline command;
- `FOOTBALL_PIPELINE_ENABLED`;
- build/migrate/start/smoke requirement when runtime image/import graph/schema changes;
- multi-league operational bootstrap boundary;
- quota-state observation as open operational work.

F006:
- FS-006 → COMPLETED;
- real multi-league pipeline demonstrated;
- register/defer NWD maintainer-ignore;
- register/defer shared quota state;
- retain dependency compatibility work.

F009:
- consider promoting explicit runtime-preparation instructions after dependency/import/schema deltas;
- promote deterministic clock policy for tests involving temporal reset boundaries if considered generally durable;
- preserve low-noise handling of pre-commit staged/unstaged auto-fixes.

No product/domain source change is required solely from FS-006.

## Final state

FS-006 satisfies its approved functional and safety outcome.

All material implementation, UAT, hook and review findings were resolved or explicitly deferred as New Work Discovered.

The ticket is ready for squash merge.
