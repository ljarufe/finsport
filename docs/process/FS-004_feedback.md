# FS-004 — Feedback final reconciliado

**Ticket:** `FS-004 — Construir motor comparativo de capital y riesgo para políticas de staking`
**Branch:** `FS-004-capital-risk-simulator`
**Base:** `master` post-FS-003
**Fecha:** `2026-08-27`
**Producto:** `local-only / demo-only / research-oriented`
**Estado técnico local:** `PASS`
**Estado del feedback:** `FINAL RECONCILIADO`
**Cierre externo pendiente al momento de este archivo:** push del último fix + rerun de GitHub CI + resolución/reconciliación de los threads del review.

Este documento reemplaza la fotografía factual intermedia del implementation pass. Reúne implementación, correcciones pre-UAT, benchmark, UAT A–D, gates locales y los tres findings reales del review de GitHub. No es autoridad de producto ni de research y no declara una política de staking ganadora.

---

## 1. Outcome

FS-004 entrega un motor local, reproducible y auditable para comparar políticas de capital sobre el mismo stream cronológico de `Decision` producido por FS-003.

La nueva frontera es:

```text
PredictionExperiment
→ Prediction / comparator identity
→ Decision policy / variant
→ ordered Decision stream
→ CapitalExperiment
→ CapitalPolicyRun
→ deterministic CapitalLedgerEntry
→ metrics / stress / Pareto
```

El ticket demuestra infraestructura comparativa y semántica de riesgo. No demuestra rentabilidad real ni selecciona una política final.

La conclusión de research permanece intacta:

```text
staking
→ no fabrica edge

staking
→ redistribuye exposición, retorno y riesgo de cola
```

---

## 2. Research y precedencia

El research maintainer-owned queda versionado como:

```text
docs/research/FS-004_capital_management_research.md
```

Clasificación:

```text
REFERENCE ONLY
```

No se convirtió en product authority y no fue reescrito por Codex.

La implementación conserva las decisiones cerradas por el ticket:

- `FLAT_UNIT` como benchmark;
- `FIXED_FRACTION_BANKROLL`;
- `FIXED_TARGET_PROFIT_NO_RECOVERY`;
- `LEGACY_RECOVERY` exacto;
- `LEGACY_CAPPED`;
- `LEGACY_PARTIAL`;
- `FRACTIONAL_KELLY`;
- `Decimal` para replay determinista;
- NumPy `float64` para bulk stochastic simulation;
- Expected Shortfall, MDD, ruin y stake concentration como dimensiones explícitas;
- no policy winner;
- no bankroll/unit/lambda/alpha/cap productivos.

---

## 3. Preflight factual cerrado

### Runtime

```text
Python 3.13.15
NumPy 2.5.2
SciPy 1.18.1 disponible transitivamente
```

Como FS-004 importa NumPy directamente:

```text
requirements.txt
→ numpy==2.5.2
```

No se añadió:

- Numba;
- JAX;
- CuPy;
- CVXPY;
- `arch`;
- PyTorch;
- GPU stack.

### NumPy smoke

Dentro del runtime autoritativo `django-web`:

```text
RNG/vectorized float64 smoke                 PASS
Decimal↔NumPy controlled equivalence smoke   PASS
```

### DB inventory pre-implementation

Inventario persistido:

```text
Decisions total = 10,756
streams          = 95
```

Resultado material:

```text
historical/backtest
→ outcomes resueltos existen
→ selected historical prices / selected OddsObservation temporales no existen
→ economic replay histórico no puede reconstruirse honestamente

prospective
→ selected prices y timestamp-valid OddsObservation existen
→ sample actionable resuelto era todavía insuficiente
```

Concurrencia real:

```text
same decision_time batches
→ existen

historical max actionable batch
→ hasta 10

prospective
→ también existen batches >1
```

Por tanto la semántica de batch/concurrencia no fue hipotética.

---

## 4. Input selector y manifest

Un `CapitalExperiment` identifica exactamente:

```text
source PredictionExperiment
+
(
  model_code + model_variant
  OR
  explicit comparator_code
)
+
Decision.policy_code
+
Decision.policy_variant
+
ordered Decisions
```

Orden:

```text
decision_time ASC
id ASC únicamente para audit/hash estable dentro del batch
```

`id` no tiene semántica de settlement ni recovery sequence.

Todos los capital arms de un experimento reciben el mismo input basis.

No se permite:

- eliminar pérdidas;
- seleccionar subconjuntos favorables;
- cambiar `Prediction`;
- cambiar `Decision`;
- reinterpretar `NO_BET`.

`NO_BET` permanece en manifest/ledger con exposición cero.

El input persiste:

- count;
- SHA-256;
- manifest;
- selector completo;
- engine version.

---

## 5. Nueva arquitectura

Boundary:

```text
football/capital/
├── __init__.py
├── contracts.py
├── policies.py
├── replay.py
├── simulation.py
├── stress.py
├── metrics.py
└── service.py
```

Responsabilidades:

### `contracts.py`

- `ENGINE_VERSION = fs004-v1`;
- errores de capital;
- `CapitalDecision`;
- `StakeRequest`;
- replay ledger/result contracts;
- serialización decimal para audit.

### `policies.py`

Implementa fórmulas/config/state de las siete políticas.

### `replay.py`

Reference engine determinista con:

```text
Decimal
chronological batching
funding validation
settlement
ledger
ruin / termination
```

### `simulation.py`

NumPy `float64` con state vectors `O(paths)`.

No guarda una matriz completa:

```text
paths × time
```

### `stress.py`

Stress explícito:

- probability deterioration;
- price haircut;
- forced losing streak.

### `metrics.py`

Métricas deterministas/estocásticas y Pareto sin score oculto.

### `service.py`

- selector ORM;
- input manifest/hash;
- experiment orchestration;
- persistence;
- required-arm accounting.

---

## 6. Persistencia

Migration:

```text
football.0003_capitalexperiment_capitalpolicyrun_and_more
```

Es aditiva.

### `CapitalExperiment`

Persiste:

- source `PredictionExperiment`;
- model/comparator identity;
- Decision policy/variant;
- engine version;
- mode `REPLAY / MONTE_CARLO / STRESS`;
- initial bankroll;
- config;
- input count/hash/manifest;
- summary;
- completed_at.

Constraints:

```text
exactamente una source identity
initial_bankroll > 0
```

### `CapitalPolicyRun`

Persiste:

- policy code/version/config;
- `PRODUCED / UNAVAILABLE / FAILED`;
- reason;
- seed;
- path count;
- metrics.

### `CapitalLedgerEntry`

Sólo para deterministic replay.

Persiste:

- source `Decision`;
- batch time/index;
- recovery step;
- requested/applied stake;
- bankroll before/after;
- P&L;
- action/outcome/price snapshots;
- capital reason;
- policy state;
- cap hit;
- shortfall;
- practical ruin;
- termination reason.

Monte Carlo no persiste rows por path.

---

## 7. Policies y versiones

```text
FLAT_UNIT
→ fs004-flat-unit-v1

FIXED_FRACTION_BANKROLL
→ fs004-fixed-fraction-bankroll-v1

FIXED_TARGET_PROFIT_NO_RECOVERY
→ fs004-fixed-target-no-recovery-v1

LEGACY_RECOVERY
→ fs004-legacy-recovery-deviation-1-v1

LEGACY_CAPPED
→ fs004-legacy-capped-v1

LEGACY_PARTIAL
→ fs004-legacy-partial-v1

FRACTIONAL_KELLY
→ fs004-fractional-kelly-v1
```

---

## 8. Semántica de batching y capital

Todas las `Decision` con el mismo `decision_time` forman un batch.

Regla:

```text
pre_batch_bankroll/state
→ dimensionar TODAS las solicitudes
→ validar exposición conjunta
→ revelar outcomes
→ settle batch
→ actualizar state para la siguiente batch
```

No existe:

```text
bet A settles
→ modifica bankroll
→ bet B del mismo batch usa ese resultado
```

### Overcommit

Si:

```text
sum(requested_stake) > pre_batch_bankroll
```

entonces:

```text
practical ruin = true
termination    = true
applied stake  = 0 para el batch
reason         = INSUFFICIENT_CAPITAL
path/run       = inactive/terminated
```

No scaling proporcional y no subset arbitrario.

### Bankroll depletion

Una batch exactamente financiada puede settle legítimamente y dejar:

```text
bankroll_after <= 0
```

En ese caso:

```text
P&L real            = conservado
stake ejecutado     = conservado
practical ruin      = true
termination reason  = BANKROLL_DEPLETED
siguiente batch     = no se ejecuta
```

### Recovery concurrente

Sin sequence assignment canónico:

```text
>1 actionable Decision en el mismo batch
→ UNAVAILABLE_CONCURRENT_RECOVERY_STEP
```

No serialización por primary key.

---

## 9. Legacy exact y equivalencia Decimal/NumPy

Legacy:

```text
target =
initial_stake * (first_price - 1)
```

Primera acción:

```text
requested stake = initial_stake EXACTO
```

Acciones posteriores:

```text
next_stake =
ceil(
    (target + accumulated_loss)
    / (price - 1)
)
```

`DEVIATION=1`.

Deterministic reference:

```text
Decimal + ROUND_CEILING
```

Después del GitHub review se corrigió una divergencia NumPy:

antes:

```text
initial_stake fraccional
→ también podía pasar por np.ceil()
```

ahora:

```text
first request
→ initial_stake exacto

subsequent recovery
→ ceil(formula)
```

Caso de regresión:

```text
initial_stake = 1.25
first loss
next recovery stake = 3
terminal bankroll = 101.75
```

---

## 10. Capped y partial recovery

### `LEGACY_CAPPED`

Conserva por separado:

```text
requested
applied
cap_hit
shortfall
termination
```

No afirma full recovery cuando un cap la impide.

Bounds configurables:

- max stake fraction;
- max absolute stake;
- max recovery steps.

### `LEGACY_PARTIAL`

```text
stake =
(
  target_profit
  + alpha * accumulated_loss
)
/ (price - 1)
```

`alpha` es config explícita.

No existe valor universal/productivo.

---

## 11. Fractional Kelly

```text
full_kelly =
max(
  0,
  (p * o - 1)
  / (o - 1)
)

stake =
lambda * full_kelly * pre_batch_bankroll
```

`lambda` es explícita.

Si:

```text
p * o <= 1
```

entonces:

```text
stake = 0
reason = NO_POSITIVE_KELLY_EDGE
```

La `Decision.action` original no cambia.

---

## 12. Métricas

### Deterministic replay

Incluye:

- input Decisions;
- actionable capital Decisions;
- capital actions;
- wins/losses;
- original Decision hit rate;
- total staked;
- P&L;
- ROI;
- terminal bankroll;
- MDD;
- MDD amount;
- drawdown duration;
- turnover;
- max single stake;
- max stake / pre-bet bankroll;
- practical ruin;
- cap hits;
- incomplete/terminated recovery sequences;
- longest losing streak;
- sequence-length distribution.

Expected Shortfall NO se fabrica para un single realized path.

Por tanto replay determinista puede producir:

```text
Pareto
→ UNAVAILABLE
→ MISSING_PARETO_DIMENSION:expected_shortfall
```

Eso es evidencia honesta, no un error.

### Monte Carlo / stress

Incluye:

- seed;
- path count;
- mean/median terminal bankroll;
- 1% / 5% terminal quantiles;
- Expected Shortfall;
- ruin probability;
- MDD distribution;
- `P(MDD > threshold)`;
- absolute max-stake distribution;
- cap distribution;
- termination distribution;
- mean/median P&L;
- return.

### Stake concentration — definición final

Después del GitHub review:

```text
por path:
max(
  applied_stake_i
  / pre_batch_bankroll_i
)

stake_concentration:
mean de esos máximos per-path
```

Sólo acciones financiadas.

Se conserva además:

```text
max_stake_pre_bankroll_ratio_distribution
```

con mean/median/q95/max.

No se divide ya el max stake por el bankroll inicial.

---

## 13. Pareto

Cinco dimensiones:

```text
return                     maximizar
maximum drawdown           minimizar
Expected Shortfall         maximizar
practical ruin probability minimizar
stake concentration        minimizar
```

Devuelve:

- metrics used;
- non-dominated runs;
- dominated runs;
- dominators.

No:

- weighted score;
- ranking único oculto;
- policy ganadora automática.

---

## 14. Primary operator workflow

Command:

```text
python manage.py evaluate_capital_policies \
  --prediction-experiment <id> \
  (--model-code <code> | --comparator-code <code>) \
  [--model-variant <variant>] \
  --decision-policy <code> \
  [--decision-variant <variant>] \
  --config <inline-json-or-json-file>
```

Modos:

```text
REPLAY
MONTE_CARLO
STRESS
```

No hace provider calls.

El inventario de management commands fue actualizado para incluir este nuevo command.

---

## 15. Django Admin

Superficies:

- `CapitalExperiment`;
- `CapitalPolicyRun`;
- `CapitalLedgerEntry`.

Estado final:

```text
view-only audit
```

Los tres Admin y el inline:

```text
has_add_permission    = False
has_change_permission = False
has_delete_permission = False
```

Los concrete persisted fields son readonly.

`has_view_permission` permanece bajo la machinery normal de Django.

UAT manual confirmó:

- CapitalExperiment visible con selector/config/hash/manifest/summary/runs;
- PolicyRun visible con version/config/status/seed/path_count/metrics;
- Ledger visible con requested/applied stake, bankroll, P&L, snapshots y ruin/termination;
- no botones Guardar/Eliminar en las superficies de capital.

---

## 16. Benchmark / performance

### ORM input extraction

Controlled stream:

```text
rows      = 10
queries   = 1
SQL N+1   = PASS
```

### Deterministic replay

```text
Decisions             = 5,000
wall time             = 0.167253 s
tracemalloc peak      = 3.310 MiB
process RSS peak      = 86.324 MiB
```

### NumPy Monte Carlo — 1,000 paths

```text
Decisions             = 250
wall time             = 0.089520 s
tracemalloc peak      = 4.829 MiB
process RSS peak      = 91.309 MiB
persistent state floor= 0.064 MiB
```

### NumPy Monte Carlo — 10,000 paths

```text
Decisions             = 250
wall time             = 0.098326 s
tracemalloc peak      = 6.127 MiB
process RSS peak      = 92.809 MiB
persistent state floor= 0.639 MiB
```

Design:

```text
O(paths) state vectors
no paths_by_time matrix
```

No profiling evidence justificó aceleradores.

---

## 17. UAT

### UAT A — controlled deterministic replay

```text
PASS
```

Input:

```text
10 Decisions
7 capital policies
```

Todas:

```text
PRODUCED
```

Cada replay run persistió:

```text
10 ledger rows
```

Pareto deterministic:

```text
UNAVAILABLE
reason = MISSING_PARETO_DIMENSION:expected_shortfall
```

correctamente, porque no se fabrica ES.

### UAT B — Monte Carlo + stress

```text
PASS
```

Se verificó:

- fixed-seed reproducibility;
- nominal Monte Carlo;
- probability deterioration;
- price deterioration;
- forced losing streak;
- distributional risk metrics;
- five-dimensional stochastic Pareto.

Los stochastic runs no crean `CapitalLedgerEntry` por path.

### UAT C — real FS-003 stream

Stream congelado:

```text
PredictionExperiment = 2
model                = DIXON_COLES
model variant        = ""
Decision policy      = MODAL_ALL
Decision variant     = ""
```

Evidencia real:

```text
input Decisions                 = 2
timestamp-valid                 = 2
resolved timestamp-valid        = 0
```

Resultado:

```text
run status = UNAVAILABLE

reason =
UNAVAILABLE_INSUFFICIENT_RESOLVED_TIMESTAMP_VALID_DECISIONS

ledger count = 0
```

```text
UAT C = PASS
```

No se backfilleó historia ni se inventaron outcomes/precios.

### UAT D — Admin

```text
PASS
```

Inspección manual de:

- CapitalExperiment;
- CapitalPolicyRun;
- CapitalLedgerEntry.

Todas las superficies de capital fueron confirmadas view-only.

---

## 18. Correcciones pre-UAT

### 18.1. Post-settlement bankroll depletion

Problema:

```text
funded batch
→ bankroll_after = 0
```

no marcaba practical ruin.

Fix:

```text
BANKROLL_DEPLETED
→ practical ruin
→ termination
→ no siguiente batch
```

Replay y NumPy cubiertos.

### 18.2. Admin realmente inmutable

Primera corrección:

```text
all fields readonly
add/delete disabled
```

Revisión posterior detectó que:

```text
readonly fields
!=
no change permission
```

Fix final:

```text
has_change_permission = False
```

manteniendo view permission normal.

### 18.3. Expected Shortfall determinista ficticio

Problema:

```text
single-path terminal bankroll
→ se había etiquetado como Expected Shortfall
```

Fix:

```text
deterministic replay
→ no ES ficticio

deterministic Pareto
→ explicit UNAVAILABLE por missing ES
```

Monte Carlo/stress conserva ES real.

---

## 19. Gate general y pequeña corrección de inventario

Primer final gate detectó un único failure:

```text
supported football command inventory
→ no incluía evaluate_capital_policies
```

El command es requerido por FS-004.

Fix:

```text
football/tests/test_cleanup_and_inspector.py
→ añadir evaluate_capital_policies a supported commands
```

Focused:

```text
3 passed
```

Gate corregido:

```text
git diff --check PASS
make check       PASS
163 passed
```

Posteriormente, después de los fixes del review de GitHub, el gate final fue invalidado y reejecutado.

---

## 20. GitHub PR review — findings reales

El review encontró tres defects reales.

### 20.1. Overcommit no contaba como termination

Antes:

```text
overcommitted
→ ruined
→ inactive
```

pero `terminated` podía permanecer `False`.

Eso podía producir:

```text
ruin probability = 1
termination probability = 0
```

Fix final:

```text
overcommitted
→ ruined = true
→ terminated = true
→ inactive
```

Regresión:

```text
bankroll = 100
FLAT_UNIT = 101

ruin probability        = 1
termination probability = 1
funded max stake        = 0
```

### 20.2. Stake concentration usaba initial bankroll

Antes:

```text
mean(max_absolute_stake) / initial_bankroll
```

Fix:

```text
max(applied_stake / pre_batch_bankroll) por path
→ mean de máximos per-path
```

Test:

```text
FIXED_FRACTION_BANKROLL = 0.20
bankroll variable
→ stake concentration ≈ 0.20
```

### 20.3. Legacy initial fractional stake era ceiled en NumPy

Antes:

```text
LEGACY_RECOVERY
initial_stake = 1.25
→ podía convertirse en 2
```

Fix:

```text
first request exact = 1.25
subsequent recovery uses ceil
```

Test:

```text
1.25 loss
→ recovery 3
→ terminal 101.75
```

---

## 21. Evidencia post-review fix

Focused:

```text
football/tests/test_capital_simulation.py
→ 10 passed in 0.12s
```

Changed-file quality:

```text
Ruff
→ PASS

Black
→ 3 files unchanged
```

Final local gate:

```text
git diff --check
→ exit 0

make check
→ exit 0

Black global
→ 76 files unchanged

Ruff global
→ PASS

Django check
→ 0 issues

pytest
→ 166 passed, 6 warnings in 4.00s
```

Warnings:

```text
penaltyblog
+
NumPy 2.5
+
deprecated ndarray .shape mutation
```

Son `DeprecationWarning`, no failures funcionales.

Disposición:

```text
DEFER
→ dependency maintenance / upstream compatibility
```

No justificar un cambio global de dependencias dentro de FS-004.

---

## 22. Complete diff review final

El complete diff artifact fue regenerado después del PR-review fix.

La revisión final del correction delta confirma:

```text
Finding 1 — overcommit termination
→ FIXED correctamente

Finding 2 — stake concentration
→ FIXED correctamente

Finding 3 — fractional legacy initial stake
→ FIXED correctamente
```

No apareció una contradicción nueva.

El artifact conserva:

```text
committed PR baseline
+
current correction worktree
+
relevant untracked feedback
```

sin staging necesario para revisión.

Estado:

```text
corrected complete diff review
→ PASS
```

---

## 23. Acceptance final local

Los 33 criterios técnicos de FS-004 quedan satisfechos localmente.

Estado:

```text
research/reference             PASS
selector/manifest              PASS
Prediction/Decision immutable  PASS
Decimal replay                 PASS
NumPy direct pin               PASS
O(paths) simulation            PASS
7 required policies            PASS
batch semantics                PASS
recovery concurrency           PASS
practical ruin                 PASS
distributional metrics         PASS
Pareto                         PASS
required-arm accounting        PASS
real evidence provenance       PASS
persistence/Admin              PASS
performance                    PASS
focused tests                  PASS
UAT A                          PASS
UAT B                          PASS
UAT C                          PASS
UAT D                          PASS
migration drift                PASS
complete diff review           PASS
git diff --check               PASS
make check                     PASS
financial side effects         NONE
```

Technical local disposition:

```text
PASS
```

External closure still required after the final commit:

```text
push correction + feedback
→ GitHub CI reruns
→ confirm green
→ resolve/reconcile review threads
→ merge
```

Este documento no inventa un post-fix CI result antes de ese push.

---

## 24. Safety boundary

FS-004 no:

- autentica bookmakers;
- coloca apuestas;
- transfiere capital;
- ejecuta Selenium;
- muta providers;
- llama provider APIs desde el evaluator;
- modifica source `Prediction` / `Decision`;
- habilita una ruta financiera.

Todo sigue:

```text
local
demo
simulation
research
```

---

## 25. Datos/evidencia todavía indisponibles

### Historical 2024 economic replay

```text
UNAVAILABLE
```

Porque no existen selected prices / timestamp-valid `OddsObservation` históricas suficientes para reconstruir honestamente la economía de las Decisions.

### Real prospective resolved sample

En UAT C:

```text
2 timestamp-valid Decisions
0 resolved
```

Por tanto:

```text
UNAVAILABLE_INSUFFICIENT_RESOLVED_TIMESTAMP_VALID_DECISIONS
```

es el resultado correcto.

No se sustituye con:

- current snapshot;
- fake odds;
- legacy WON/LOST;
- synthetic history.

---

## 26. Parámetros intencionalmente abiertos

FS-004 NO congela:

- bankroll real;
- unit;
- fixed fraction productiva;
- target profit;
- max stake;
- max recovery steps;
- alpha;
- lambda;
- minimum edge;
- drawdown tolerance;
- ruin tolerance;
- policy final;
- number of concurrent recovery sequences.

La infraestructura permite medirlos posteriormente cuando exista evidencia real suficiente.

---

## 27. Deferred / out of scope

```text
parameter selection
→ DEFER

correlation/regime richer model
→ DEFER

block bootstrap
→ DEFER / sufficient real sample first

vector Kelly / risk-constrained Kelly
→ DEFER

Numba/JAX/CuPy/GPU
→ DEFER / profiling-first

odds cadence/quota
→ OUT, separate work

policy winner declaration
→ OUT

real betting
→ PROHIBITED / OUT
```

---

## 28. New Work Discovered — legacy Bet domain removal

Durante FS-004 se cerró una decisión nueva del maintainer:

```text
BetTable / BetRow
y toda su superficie exclusivamente relacionada
→ REMOVE
```

FS-004 NO absorbe ese cleanup porque introduciría un segundo boundary y posibles migraciones destructivas.

El chat principal debe crear/disponer un ticket separado para inventariar y retirar completamente:

- `BetTable`;
- `BetRow`;
- `BetRowManager`;
- Admin legacy asociado;
- serializers asociados;
- `BetTableView` / `ModelViewSet`;
- `/bet/` URLs/endpoints;
- tests exclusivamente ligados a ese dominio;
- imports/referencias;
- migrations/runtime residual cuando corresponda;
- configuración/app registration si el app `bet` queda vacío;
- dependencias que queden exclusivamente asociadas a ese dominio;
- documentación que aún presente ese runtime como vigente.

Motivación:

```text
FS-003
→ Prediction / Decision

FS-004
→ CapitalExperiment / CapitalPolicyRun / CapitalLedgerEntry
```

ya proporcionan la arquitectura moderna necesaria para prediction/decision/capital simulation.

Mantener `BetTable`/`BetRow` como una segunda representación write-capable genera ambigüedad y deuda.

El cleanup debe preservar únicamente evidencia histórica que todavía tenga valor de research; no debe reactivar ninguna semántica financiera real.

---

## 29. Source reconciliation requerida

El chat principal debe reconciliar al menos:

### F001

Actualizar la disposición histórica:

```text
BetTable/BetRow
→ ya no "design revisable"
→ SUPERSEDE / REMOVE por ticket separado
```

Mantener:

```text
demo/simulation
no real betting
```

### F002

Registrar:

- `Decision` como selección fuente;
- capital policies como simulación posterior a Decision;
- practical ruin / concurrency / evidence-unavailable semantics;
- BetTable/BetRow superseded;
- no financial side effects.

### F003

Registrar arquitectura durable:

```text
football/capital/
CapitalExperiment
CapitalPolicyRun
CapitalLedgerEntry
evaluate_capital_policies
Decimal deterministic
NumPy stochastic
```

y retirar de la descripción durable la idea de `BetTable`/`BetRow` como estructura futura vigente.

### F004

Registrar:

- NumPy application-runtime smoke dentro de `django-web`;
- capital evaluator es DB-only/no-provider;
- benchmark local aceptable;
- warning `penaltyblog`/NumPy a vigilar sin maintenance global todavía.

### F006

- marcar FS-004 COMPLETED después del merge;
- mantener parameter freeze `NOT READY`;
- registrar ticket nuevo de legacy Bet domain removal;
- continuar odds cadence/quota como candidate/enabler separado;
- no seleccionar capital policy por UAT controlada.

### F008 / F009

Reconciliar los problemas de proceso detallados en el handoff de FS-004.

---

## 30. Implicaciones para trabajo siguiente

FS-004 desbloquea:

```text
Decision stream
→ reproducible capital experiment
→ risk distribution
→ stress
→ Pareto
```

Pero NO desbloquea todavía:

```text
production stake
production bankroll
preferred capital policy
real betting
```

El blocker empírico sigue siendo:

```text
sufficient resolved timestamp-valid prospective market sample
```

Por tanto cualquier ticket que elija parámetros debe esperar evidencia adicional o definir explícitamente que sigue siendo synthetic/controlled research.

---

## 31. Cierre Git esperado

Este feedback debe reemplazar:

```text
docs/process/FS-004_feedback.md
```

y entrar en el mismo último commit que los tres PR-review fixes.

No crear un commit exclusivamente documental posterior.

Después:

```text
push
→ CI
→ review reconciliation
→ merge
→ cleanup
→ Planka Done
→ handoff principal
```

No repetir UAT/benchmark/make-check local tras merge por ceremonia.

---

## 32. Declaración final

FS-004 cumple su objetivo:

> Dado un stream cronológico y reproducible de Decisions, Finsport puede aplicar varias políticas de capital bajo reglas explícitas de concurrencia, reproducir deterministicamente el settlement con Decimal, simular distribuciones con NumPy, stress-testear deterioro y rachas, medir retorno/riesgo de cola/ruina/exposición y comparar arms mediante Pareto sin convertir staking en una fuente ficticia de edge.

Resultado:

```text
FS-004 TECHNICAL LOCAL ACCEPTANCE
→ PASS
```

Pendiente únicamente del cierre externo normal del último push:

```text
GitHub CI
→ review threads
→ merge
```
