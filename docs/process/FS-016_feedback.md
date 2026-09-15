# FS-016 — Feedback de ejecución y handoff

**Ticket:** FS-016 — Capital Runtime / Event-Time v2
**Branch:** `FS-016-capital-runtime-event-time-v2`
**PR:** #22
**Fecha:** 2026-09-15
**Estado:** technical close local / PR-review corrections complete / cierre operacional pendiente post-merge

---

## 1. Resultado

FS-016 implementa Capital Runtime / Event-Time v2 como capacidad prospectiva automática, persistente y simulation-only.

El runtime automático queda fijado a:

```text
Prediction
→ DIXON_COLES

Decision
→ MODAL_ALL

Capital
→ 7 configuraciones CURRENT independientes
→ initial_bankroll = 100u por configuración
```

No existe un grid `policy × lane-count` y una lane no representa un bankroll independiente.

Cada configuración mantiene:

```text
bankroll_equity
reserved_exposure
available_cash
```

con:

```text
available_cash = bankroll_equity - reserved_exposure
```

---

## 2. Configuraciones automáticas

| Policy | Configuración | max_lanes |
|---|---|---:|
| `FLAT_UNIT` | `unit=1` | 10 |
| `FIXED_FRACTION_BANKROLL` | `fraction=0.05` | 10 |
| `FIXED_TARGET_PROFIT_NO_RECOVERY` | `target_profit=1` | 10 |
| `LEGACY_RECOVERY` | `initial_stake=1` | 1 |
| `LEGACY_CAPPED` | `initial_stake=1`, `max_absolute_stake=5` | 1 |
| `LEGACY_PARTIAL` | `target_profit=1`, `alpha=0.5` | 1 |
| `FRACTIONAL_KELLY` | `lambda=0.25` | 10 |

Concurrentes:

```text
FLAT_UNIT
FIXED_FRACTION_BANKROLL
FIXED_TARGET_PROFIT_NO_RECOVERY
FRACTIONAL_KELLY
```

Secuenciales:

```text
LEGACY_RECOVERY
LEGACY_CAPPED
LEGACY_PARTIAL
```

Las cuatro concurrentes pueden mantener varias posiciones OPEN simultáneamente usando un único bankroll compartido de la configuración.

Las recovery conservan una sola secuencia dependiente del resultado anterior. Si el evento final de una nueva oportunidad llega mientras la lane sigue ocupada:

```text
EXPIRED_CAPACITY
```

No se coloca más tarde con una cuota stale.

---

## 3. Lifecycle Capital v2

Lifecycle CURRENT:

```text
market-t30m real
→ revalidación Decision/precio
→ placement simulado
→ reserva de stake
→ Position OPEN
→ resultado canónico conocido
→ SETTLE / VOID
→ liberación de exposición
→ P&L realizado
```

El único evento de ejecución prospectivo es el `market-t30m` exitoso real.

No existe fallback operativo a:

```text
market-t60m
market-t6h
```

para sustituir un T-30 ausente.

El execution basis congela de manera coherente:

- Prediction;
- Decision;
- policy/config;
- action/reason;
- model probability;
- OddsObservation;
- selected price;
- expected value;
- CaptureWorkItem;
- CaptureRun;
- límites temporales de evidencia.

El precio usado para ranking, sizing y P&L queda ligado al mismo basis.

---

## 4. Estados de no colocación

Razones terminales persistentes y consultables:

```text
NO_BET
UNAVAILABLE_NO_DECISION_AT_EXECUTION
NO_EXECUTION_PRICE
MISSED_EXECUTION_WINDOW
EXPIRED_CAPACITY
INSUFFICIENT_AVAILABLE_CASH
INELIGIBLE
```

Un `NO_BET` anterior de research no termina Capital.

El `NO_BET` de ejecución T-30 sí termina:

```text
config + Match
```

con exposición cero.

---

## 5. Settlement y autoridad de resultado

Una posición OPEN sólo se liquida cuando existe conocimiento terminal canónico.

Se exige un:

```text
resolved API-Football MatchSourceRef
```

para crear `CapitalResultObservation`.

`result_known_at` representa cuándo Finsport realmente reconoció/persistió el resultado y no se backdatea.

Semántica:

```text
WIN
→ liberar stake
→ sumar realized P&L

LOSS
→ liberar stake
→ restar realized P&L

CANC / ABD
→ VOID
→ P&L = 0
→ liberar stake
→ recovery state preserva el pre-state
```

Estados como:

```text
FT / AET / PEN / AWD / WO
```

sin outcome canónico permanecen como deuda visible, no se convierten en pérdidas artificiales.

---

## 6. Result debt y recuperación tras interrupciones

Las posiciones OPEN vencidas se reconcilian en el pipeline normal.

El refresh:

- deduplica por Match;
- colapsa múltiples configuraciones sobre un mismo fixture;
- usa lotes máximos de 20 fixture IDs;
- respeta provider-attempt budget;
- deja posiciones OPEN si el provider falla;
- mantiene exposición reservada;
- expone DEGRADED/error;
- hace cero llamadas Capital-specific cuando no existe deuda OPEN.

Tras PR review se corrigió fairness del backlog:

```text
never attempted
→ first

then
→ least recently attempted

tie-break
→ kickoff + stable Match identity
```

Esto evita starvation de fixtures posteriores.

---

## 7. Recuperación de T-30 parcialmente procesado

PR review detectó:

```text
T-30 exitoso
→ algunas configs procesadas
→ excepción en Capital
→ siguiente wake
→ planner considera el capture original fulfilled
```

La implementación inicial podía dejar configs faltantes sin consumir el evento válido.

Corrección final:

- el T-30 exitoso original sigue siendo evidencia durable válida;
- configs ya completadas no cambian;
- sólo se completan `config + Match` faltantes;
- se reutilizan CaptureWorkItem, CaptureRun, Decision y precio originales;
- no se transforma esta recuperación en stale fallback;
- el siguiente retry es `NO_WORK`.

---

## 8. Estudios v2

Se adaptaron:

```text
REPLAY
MONTE_CARLO
STRESS
HISTORICAL
```

a la cronología:

```text
placement
→ OPEN
→ reserved exposure
→ settlement
```

Todos conservan:

```text
no_winner_claim = true
```

FS-016 no selecciona ninguna policy ganadora.

PR review detectó además que `peak_equity` y `maximum_drawdown` no consideraban toda la trayectoria.

Corrección final:

```text
100 → 120 → 90
peak_equity = 120
maximum_drawdown = 25%

100 → 90
maximum_drawdown = 10%
```

Las métricas se actualizan settlement por settlement y se persisten en la trayectoria representativa.

---

## 9. Histórico FS-015

HISTORICAL v2 conserva provenance:

```text
source_price_is_real = true
timestamp_is_imputed = true
time_semantics = ASSUMED_T30M
settlement_time = SYNTHETIC_RESEARCH_ONLY
```

No se reinterpreta esta evidencia como observación prospectiva real a T-30.

---

## 10. Persistencia y schema

Migration:

```text
football/migrations/0014_capitalexecutionbasis_capitalresultobservation_and_more.py
```

Representaciones v2 principales:

```text
CapitalRuntimeConfig
CapitalExecutionBasis
CapitalExecutionState
CapitalPosition
CapitalResultObservation
```

Versiones:

```text
runtime_version   = fs016-capital-runtime-v2
execution_version = fs016-market-t30m-v2
```

---

## 11. Reporting mínimo

La superficie CURRENT permite responder por configuración:

- policy/config;
- started_at/status;
- initial bankroll;
- current equity;
- realized P&L;
- realized ROI;
- reserved exposure;
- available cash;
- OPEN/max_lanes;
- W/L/VOID;
- maximum drawdown;
- practical ruin / termination;
- sample count;
- NO_BET;
- EXPIRED_CAPACITY;
- missing execution;
- degraded debt.

UAT mostró las siete configuraciones inicialmente en:

```text
equity = 100u
reserved = 0u
available = 100u
```

sin performance inventada.

---

## 12. Capital v1 retirement

Capital v1 deja de ser CURRENT.

Retirement elimina únicamente:

```text
CapitalLongitudinalSeries
CapitalExperiment
CapitalPolicyRun
CapitalLedgerEntry
```

y preserva:

```text
Match
OddsObservation
HistoricalMarketEvidence
PredictionExperiment
Prediction
Decision
CaptureRun
CaptureWorkItem
PipelineRun
```

UAT en `finsport-dev`:

```text
CapitalLongitudinalSeries = 1
CapitalExperiment         = 17
CapitalPolicyRun          = 23
CapitalLedgerEntry        = 41
upstream_selected         = 0
```

Apply exacto:

```text
v1 derived rows = 0
```

Los upstream counts permanecieron idénticos.

Capital v2 permaneció intacto con:

```text
7 automatic CURRENT configs
```

Segundo retirement:

```text
NO_WORK
```

El retirement operacional queda deliberadamente post-merge.

---

## 13. UAT

Resultado:

```text
UAT-1..UAT-19
→ PASS
```

Cubrió:

- siete configs;
- capital compartido;
- múltiples OPEN concurrentes;
- recovery secuencial;
- execution timing T-30;
- Decision/price atomicity;
- NO_BET;
- razones de no colocación;
- ranking EV;
- WIN/LOSS exactly-once;
- VOID;
- terminal-result debt;
- restart catch-up;
- batching;
- provider fail-soft;
- REPLAY;
- MONTE_CARLO;
- STRESS;
- HISTORICAL;
- browser CURRENT;
- retirement v1 dev;
- hotfix guards.

Un primer smoke de studies seleccionó dos Decisions del mismo Match y chocó contra la constraint `config + Match unique`.

Se clasificó correctamente como:

```text
HARNESS FINDING
```

El UAT repetido con Matches únicos pasó.

---

## 14. Gate general

Gate completo previo al PR:

```text
Black                        PASS
Ruff                         PASS
Django check                 PASS
migration drift              none
pip check                    PASS
pip-audit                    no known vulnerabilities
pytest                       575 passed
coverage                     84.50%
```

Pass 4 reran sólo invalidated evidence:

```text
football/tests/test_capital_runtime_v2.py
→ 45 passed

football/tests/test_pipeline.py
→ 14 passed

Ruff
→ PASS

Black
→ PASS

Django check
→ PASS

migration drift
→ none
```

No se repitieron UAT/retirement/full gate sin delta que los invalidara.

---

## 15. PR review

PR #22 produjo tres findings reales:

### P1 — partial T-30 processing could be lost after Capital failure

```text
FIXED
```

### P1 — study peak/drawdown ignored intermediate settlements

```text
FIXED
```

### P2 — bounded result-debt prefix could starve later fixtures

```text
FIXED
```

No se identificaron false positives.

El correction fue una única pasada consolidada de PR review.

---

## 16. Research integrity y defecto de proceso Git hooks

Research aprobado:

```text
bytes  = 45562
sha256 = 70d40f3b15605bb7d7391691ed1e232a974b98e8425b820e1e756f301d28605d
```

El archivo contiene cinco hard-breaks Markdown legítimos con dos espacios finales.

El hook `trailing-whitespace` los elimina y produce:

```text
45552 bytes
d8881cc7a5cdff315c119727528faa595041dabc5055ff8d73d3d2969b12af93
```

El problema se observó en dos momentos distintos del lifecycle:

1. al preparar/commitir el artifact, el formatter/hook podía dejar el archivo modificado fuera del commit;
2. incluso después de restaurar el artifact y commitirlo correctamente con `SKIP=trailing-whitespace`, el `git push` volvió a ejecutar el hook sin ese `SKIP`, modificó el worktree y abortó el push.

El comportamiento observado fue:

```text
commit
→ research correcto en HEAD
→ pre-push trailing-whitespace
→ modifica research en working tree
→ push aborta
→ branch queda ahead del origin
```

### Causa de orquestación

La variable:

```text
SKIP=trailing-whitespace
```

aplicada a `git commit` sólo existe para ese comando.

No se hereda por el `git push` posterior.

Por tanto, usar `SKIP` únicamente en el commit no resuelve un hook mutante que también se ejecute en pre-push.

### Lección durable

Un artifact maintainer-owned con identidad byte-exact no puede coexistir de manera implícita con hooks mutantes que normalicen su contenido.

El proceso debe asegurar explícitamente una de estas dos propiedades:

```text
exact-byte artifact
→ excluido de hooks mutantes

o

mutating hygiene hooks
→ sólo pre-commit y nunca pre-push
```

La protección debe ser estructural, no depender de recordar un `SKIP` puntual en cada commit/push.

También debe verificarse después de cualquier hook mutante:

```text
hook modifies file
→ inspect exact delta
→ stage deliberately
→ commit again
→ do not continue push as if HEAD/worktree still matched
```

Este finding pertenece a ejecución/proceso, no a producto FS-016.

---

## 17. Safety

Se preservan:

```text
FOOTBALL_MODERNIZED_R45_ENABLED=False
FOOTBALL_MODERNIZED_R45_CAPITAL_ENABLED=False
INKABET_AUTOMATIC_ENABLED=False
```

FS-016 sigue siendo:

```text
simulation-only
research-oriented
no real betting
```

No se agregó bookmaker auth/write ni financial mutation real.

---

## 18. New Work Discovered — reporting/frontend performance

Durante browser UAT se descubrió un problema preexistente/transversal.

Un `/` histórico sin rango puede materializar grandes poblaciones de:

```text
Prediction
Decision
```

Con la DB observada:

```text
Prediction ≈ 14.5k
Decision   ≈ 131k
```

se observó:

```text
Gunicorn worker
→ high memory
→ OOM / SIGKILL
→ Nginx 502
```

Una request dev con rango de un día respondió:

```text
HTTP 200
```

y mostró correctamente las siete configuraciones Capital v2.

Disposition:

```text
New Work Discovered
→ dedicated frontend/reporting performance work
```

FS-016 no absorbió un rediseño del frontend.

---

## 19. Observabilidad / audit impact

Nuevas señales:

```text
runtime status
placed
not_placed
settled
provider_calls
open_debt
errors
```

Estados:

```text
PRODUCED
NO_WORK
DEGRADED
```

Failure/state signals relevantes:

```text
MISSING_API_FOOTBALL_MATCH_REF
UNRESOLVED_CANONICAL_OUTCOME
MISSED_EXECUTION_WINDOW
EXPIRED_CAPACITY
INSUFFICIENT_AVAILABLE_CASH
automatic config drift
canonical result conflict
reserved exposure underflow
```

No todas son incidentes: algunas son estados terminales de dominio esperados.

---

## 20. Errores de orquestación y mejoras

### 20.1 Frontend operacional vs dev

Durante UAT se inspeccionó inicialmente el frontend operacional al intentar validar FS-016 dev.

Autoridad correcta:

```text
finsport-dev
→ :18001
```

Lección:

```text
browser UAT
→ confirmar URL/stack identity antes de interpretar evidencia
```

### 20.2 Harness de studies con Decisions duplicadas por Match

El primer selector eligió dos Decisions del mismo Match.

La DB rechazó correctamente el segundo basis.

Lección:

```text
UAT selector
→ respetar las mismas invariantes de identidad que product runtime
```

### 20.3 No absorber incidentalmente frontend OOM

El reporting OOM apareció durante FS-016, pero no justificaba convertir el ticket en un frontend redesign.

La decisión correcta fue:

```text
preserve finding
→ validate bounded FS-016 surface
→ defer reporting redesign
```

### 20.4 Exact-byte research vs hooks mutantes

Este ticket demostró una incompatibilidad real entre:

```text
maintainer-owned byte-exact artifact
```

y hooks genéricos que modifican whitespace.

Esto debe proyectarse a F009 / repo hook policy.

---

## 21. Trabajo no absorbido

FS-016 no implementa:

- rediseño general del frontend;
- selección de CapitalPolicy ganadora;
- Portfolio Kelly;
- recovery lanes paralelas;
- activación R45;
- activación automática Inkabet;
- apuestas reales;
- benchmark de costo de oportunidad;
- evaluador integrado Prediction/Decision/Capital;
- eliminación general de Predictions/Decisions históricas.

Prediction y Decision históricos se preservan como upstream.

La clasificación CURRENT / comparator / superseded deberá hacerse en trabajo posterior, no mediante borrado indiscriminado.

---

## 22. Estado antes del merge

```text
UAT-1..19
→ PASS

general gate
→ PASS

PR review findings
→ FIXED

development Capital v1 retirement
→ PASS

research artifact
→ must remain exact approved bytes/hash

operational DB
→ UNTOUCHED
```

Único paso deliberadamente pendiente:

```text
Capital v1 retirement operational
→ post-merge
```

---

## 23. Cierre operacional post-merge

Después del merge:

```bash
make dev-destroy

git switch master
git pull --ff-only origin master

make deploy-local
```

Luego verificar:

- `/healthz/`;
- normal pipeline owner;
- migration/schema v2;
- exactamente siete automatic CURRENT configs;
- minimal Capital v2 read model;
- R45 prospective OFF;
- R45 Capital OFF;
- Inkabet automatic OFF.

Sólo después:

```text
v1 retirement dry-run operational
→ inspect manifest/counts

apply exact manifest
→ delete only v1-derived Capital

verify
→ upstream unchanged
→ v2 unchanged

second run
→ NO_WORK
```

Nunca usar contra operacional:

```text
docker compose down -v
docker volume prune
docker system prune --volumes
```

El volumen:

```text
finsport_postgres_data
```

sigue protegido.

---

## 24. Handoff

FS-016 deja a Finsport con:

```text
Capital
→ persistent prospective runtime
→ multiple simultaneous OPEN positions
→ shared reserved exposure
→ settlement when result is actually known
→ restart catch-up
→ batched canonical result reconciliation
→ seven comparable automatic bankrolls
```

Esto permite empezar a acumular evidencia prospectiva real de comportamiento de Capital sin fingir settlement inmediato ni serializar artificialmente políticas naturalmente concurrentes.

No hay winner.

La evaluación futura debe seguir separando:

```text
Prediction quality
Decision selection quality
Capital allocation/risk
```

El finding de frontend/reporting performance y el finding de hooks/research exact-byte deben permanecer visibles al cerrar el ticket.
