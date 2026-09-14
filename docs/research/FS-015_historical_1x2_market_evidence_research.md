# Finsport — Capital Layer Audit + Research Handoff (Consolidado Final)

**Fecha:** 2026-09-11
**Estado:** RESEARCH CLOSED / READY FOR MAIN-CHAT PLANNING
**Scope:** capa `CapitalPolicy` actual de Finsport, excluyendo `MODERNIZED_R45` como predictor/Decision arm.
**Objetivo:** entregar al chat principal una base única para definir el trabajo real de Capital sin crear tickets por ceremonia.

---

## 1. Decisión ejecutiva

La auditoría concluye que:

```text
Capital engine
→ existe
→ tiene 7 policy families
→ soporta REPLAY / MONTE_CARLO / STRESS

pero

Capital runtime/longitudinal actual
→ NO representa correctamente el lifecycle real de apuestas solapadas
→ puede quedar bloqueado por gaps permanentes de precio
→ no mantiene una semántica explícita de posiciones OPEN
→ no reserva capital mientras espera resultados
→ todavía no tiene un estudio real persistido de MC/STRESS
```

Por tanto:

```text
Capital implementation audit
→ NO CLOSED AS SUFFICIENT

real implementation work
→ JUSTIFIED

new ticket(s)
→ todavía deben definirse por outcome coherente
→ finding != ticket
```

No se requiere más research exploratorio previo antes de devolver esto al chat principal.

---

# 2. Objetivo de producto final de Capital

La capa Capital debe ser una simulación operacional de bankroll/exposición.

Lifecycle deseado:

```text
Prediction
→ puede existir sin odds

Decision / candidate action
→ puede existir antes del mercado final

target execution window
→ market-t30m

si no existe snapshot exacto T-30
→ usar la última cuota pre-match válida conocida
→ registrar age/fallback/provenance

si jamás existe una cuota pre-match válida
→ NO_EXECUTABLE_PRICE
→ exposición 0
→ reason explícito
→ el stream CONTINÚA

si existe action + price
→ CapitalPolicy calcula stake
→ stake queda reservado
→ posición OPEN

resultado canónico conocido
→ posición SETTLED
→ WIN / LOSS
→ P&L
→ bankroll actualizado
→ drawdown / recovery state / termination actualizados
```

Regla fundamental:

```text
future result
→ cannot finance a later position
before that result is actually known
```

---

# 3. “Precio ejecutable” — definición consolidada

No significa “hay dinero disponible”.

Significa:

```text
price decimal > 1
+
outcome compatible
+
price known pre-match
+
valid provenance
```

Regla prospectiva:

```text
TARGET
→ T-30

FALLBACK
→ most recent valid pre-match quote before T-30/cutoff

ONLY IF NONE EXISTS
→ NO_EXECUTABLE_PRICE
```

Por tanto, si falta T-30 pero existe T-60 o T-6h:

```text
use latest known pre-match price
→ mark fallback
→ preserve quote age
```

No se debe impedir Capital por exigir una captura exactamente T-30.

---

# 4. Qué hacer con un gap permanente

El comportamiento actual de FS-010:

```text
first actionable gap
→ stop maximum complete chronological prefix
```

puede congelar la serie para siempre.

Caso real:

```text
decision_id=117077
competition=Eredivisie
action=AWAY
outcome=AWAY
selected_price=None
selected_odds_observation=None

RAW_ODDS_BEFORE_DECISION=0
RAW_ODDS_AFTER_DECISION=0
```

Ese gap ya no puede repararse con datos locales.

Nueva semántica requerida:

```text
PENDING
→ puede resolverse luego
→ puede esperar temporalmente

PERMANENTLY_UNAVAILABLE
→ no existe price ejecutable
→ exposure=0
→ auditable exclusion
→ MUST NOT deadlock later evidence

CANCELLED / VOID
→ no position / exposure=0
→ stream continues

VALID
→ can place/settle
```

No borrar el partido.

Persistir algo equivalente a:

```text
CAPITAL_NOT_EXECUTABLE
reason=MISSING_PREMATCH_PRICE
excluded_from_policy_performance=true
```

y continuar.

---

# 5. Estado real del longitudinal principal

Serie actual:

```text
fs010-primary-prospective-dixon-coles-modal-all
```

Audit real:

```text
current_snapshot=None
input_count=0
watermark=None
```

El snapshot saludable anterior tenía 6 Decisions, pero sus Predictions antiguas quedaron luego:

```text
bet_eligible=False
readiness_reason=LEGACY_UNVERSIONED_READINESS
```

y salieron del selector vigente.

El primer row current eligible no tiene market evidence.

Resultado:

```text
old healthy prefix disappears
+
first current eligible row has no market
→ basis=0
→ current_snapshot=None
```

Esto no es un bug del puntero.

Sí es un problema operativo para el objetivo actual.

---

# 6. Siete CapitalPolicy families actuales

Policies:

```text
FLAT_UNIT
FIXED_FRACTION_BANKROLL
FIXED_TARGET_PROFIT_NO_RECOVERY
LEGACY_RECOVERY
LEGACY_CAPPED
LEGACY_PARTIAL
FRACTIONAL_KELLY
```

Configs de referencia actuales:

```text
FLAT_UNIT
unit=1

FIXED_FRACTION_BANKROLL
fraction=0.05

FIXED_TARGET_PROFIT_NO_RECOVERY
target_profit=1

LEGACY_RECOVERY
initial_stake=1

LEGACY_CAPPED
initial_stake=1
max_absolute_stake=5

LEGACY_PARTIAL
target_profit=1
alpha=0.5

FRACTIONAL_KELLY
lambda=0.25
```

Son configs de investigación/comparación.

No son parámetros óptimos/productivos.

---

# 7. Recovery policies y concurrencia

El replay actual considera recovery incompatible cuando hay:

```text
>1 actionable Decision
with exact same decision_time
```

y devuelve:

```text
UNAVAILABLE_CONCURRENT_RECOVERY_STEP
```

Eso evita una secuencia falsa, pero el problema real es más amplio.

---

# 8. Concurrencia real medida con placement T-30

Probe real sobre Dixon-Coles prospectivo resuelto:

```text
UNIQUE_RESOLVED_MATCHES=32

MAX_SIMULTANEOUS_OPEN=10

PLACEMENTS_WITH_EXISTING_OPEN=29

OPEN_COUNT_AT_PLACEMENT:
0 open  → 3 placements
1 open  → 2
2 open  → 3
3 open  → 3
4 open  → 2
5 open  → 3
6 open  → 4
7 open  → 2
8 open  → 6
9 open  → 4
```

Conclusión:

```text
overlap
→ structural
→ NOT edge case
```

29/32 placements ocurrieron mientras ya existía al menos otra posición abierta.

Máximo observado:

```text
10 simultaneous OPEN positions
```

Por tanto, el modelo:

```text
bet
→ settle
→ next bet
```

no representa el runtime real.

---

# 9. Event-time lifecycle requerido

El replay actual debe evolucionar a eventos explícitos:

```text
PLACE
→ at T-30 target / latest pre-match fallback
→ compute stake
→ reserve capital
→ OPEN position

SETTLE
→ only after result becomes known
→ release reserved exposure
→ apply P&L
→ update policy state
→ update bankroll
```

Separar:

```text
bankroll_equity
reserved_exposure
available_cash
```

Regla:

```text
new stake <= available_cash
```

Una posición OPEN no puede aportar ganancia futura al bankroll disponible.

---

# 10. Ruina / insuficiencia de capital

Distinguir:

```text
NO_EXECUTABLE_PRICE
→ market evidence problem

INSUFFICIENT_CAPITAL
→ CapitalPolicy/bankroll problem
```

Cuando una policy/config se queda sin capital:

```text
do NOT silently refill
do NOT silently reset
do NOT silently change params
```

Persistir la terminación y alertar.

Requisito de observabilidad:

```text
CAPITAL_POLICY_TERMINATED
CAPITAL_PRACTICAL_RUIN
```

Con contexto:

```text
policy code/version/config
source stream
bankroll before
requested stake
available cash
Decision/Position
reason
timestamp
```

Después:

```text
new params
→ new version / new experiment
```

Si múltiples runs/cohorts muestran ruina:

```text
evaluator
→ LOWER_PRIORITY
→ DROP
→ or research stricter config
```

---

# 11. Historical Capital evidence — estado actual

Audit real:

```text
BACKTEST_DC_PREDICTIONS=4365

BACKTEST_MODAL_TOTAL=4365
BACKTEST_MODAL_ACTIONABLE=780
BACKTEST_MODAL_RESOLVED=780

BACKTEST_MODAL_PRICED=8
BACKTEST_MODAL_TIMESTAMP_VALID=8
```

Odds locales vinculadas a esos matches:

```text
379 OddsObservations
30 matches
all in 2026
```

Conclusión:

```text
sporting history
→ large

economic/Capital history
→ severely underfed
```

Historical odds backfill está justificado.

---

# 12. Historical odds — fuente aprobada

## PRIMARY SOURCE: Football-Data.co.uk

TheStatsAPI queda descartado.

Razones:

```text
trial/API
→ 403 despite validated key

and

Football-Data
→ already gives complete bulk coverage
→ no need for secondary provider now
```

No tratar TheStatsAPI como blocker ni requirement.

---

# 13. Football-Data real probe — Eredivisie 2024/25

Archivo real:

```text
https://football-data.co.uk/mmz4281/2425/N1.csv
```

Resultado:

```text
HTTP=200
ROWS=306
HEADER_COUNT=119
```

Cobertura completa 1X2:

```text
B365_CLOSING
→ 306/306
→ 100%

PINNACLE_CLOSING
→ 306/306
→ 100%

AVG_CLOSING
→ 306/306
→ 100%

MAX_CLOSING
→ 306/306
→ 100%

B365_PRE
→ 306/306
→ 100%

PINNACLE_PRE
→ 306/306
→ 100%

AVG_PRE
→ 306/306
→ 100%

MAX_PRE
→ 306/306
→ 100%
```

Conclusión:

```text
Football-Data
→ sufficient primary source for historical Capital 1X2
```

---

# 14. Football-Data mapping / reconciliation

Direct normalized reconciliation actual:

```text
182 / 306
```

No es un problema de odds.

Ejemplos no reconciliados:

```text
Nijmegen
Waalwijk
For Sittard
Zwolle
PSV Eindhoven
```

Esto apunta a aliases/canonical naming.

El historical importer debe reutilizar el lifecycle de reconciliación de Finsport y NO depender sólo de string equality.

Objetivo:

```text
Football-Data row
→ canonical Competition
→ canonical Season
→ canonical HomeTeam
→ canonical AwayTeam
→ canonical Match
```

Ambiguity/conflict:

```text
→ explicit
→ no silent guess
```

---

# 15. ¿Cuántas odds históricas por match?

Minimum historical market unit:

```text
one complete 1X2 triplet
```

Es decir:

```text
HOME
DRAW
AWAY
```

No importar sólo el outcome que posteriormente seleccionó la Decision.

Eso evita selection bias y permite reutilizar la evidencia.

Para el primer study no se necesitan múltiples snapshots reales por match.

---

# 16. Historical temporal semantics

Luis autorizó timestamps sintéticos únicamente para research histórico cuando el precio es real pero la hora exacta no está disponible.

Mapping aprobado:

```text
opening / pre-closing
→ ASSUMED_T6H

closing / last_seen equivalent
→ ASSUMED_T30M
```

Persistir explícitamente:

```text
source_price_is_real=true
timestamp_is_imputed=true
time_semantics=ASSUMED_T6H | ASSUMED_T30M
evidence_class=SYNTHETIC_TIME_RESEARCH_ONLY
```

Nunca afirmar que el precio fue observado exactamente a ese instante.

No usar esa evidencia para:

```text
prospective freshness claims
MARKET_CONSENSUS current temporal validation
CLV claims requiring true timestamps
```

Sí puede usarse para:

```text
historical Capital replay
drawdown
ruin
recovery study
policy comparison
```

---

# 17. Historical source priority within Football-Data

Primer baseline:

```text
closing complete triplet
```

Jerarquía recomendada:

```text
1. Pinnacle closing complete 1X2
2. Bet365 closing complete 1X2
3. Avg closing complete 1X2
4. Max closing complete 1X2

then fallback:

5. Pinnacle pre
6. Bet365 pre
7. Avg pre
8. Max pre
```

La decisión exacta de bookmaker baseline puede quedar documentada/versionada.

No mezclar H/D/A de semantics distintas.

---

# 18. Historical ingestion lifecycle

No hacerlo diariamente.

```text
when Competition enabled
→ one-shot historical sporting ingestion
→ one-shot historical market 1X2 ingestion
→ coverage persisted
→ stop

existing enabled leagues
→ exceptional one-time bulk backfill now
```

Normal runtime:

```text
no historical provider polling
```

---

# 19. Simultaneous CapitalPolicy research

El problema de múltiples apuestas simultáneas tiene literatura específica.

Principal reference:

```text
Whitrow (2007)
Algorithms for optimal allocation of bets on many simultaneous events
JRSS Series C
```

Concepto:

```text
simultaneous portfolio allocation
→ maximize expected log wealth
→ Kelly-family generalization
```

No resolver concurrencia mediante orden arbitrario.

---

# 20. Candidate concurrency techniques

No elegir winner todavía.

## A. POOLED RESERVED CAPITAL

Para policies no-recovery:

```text
FLAT_UNIT
FIXED_FRACTION
FIXED_TARGET
FRACTIONAL_KELLY
```

Permitir múltiples OPEN positions sujetas a:

```text
available_cash
per-position cap
joint exposure cap
```

---

## B. RECOVERY_LANES

Inspirado en múltiples tablas independientes.

```text
total capital
→ N lanes

each lane
→ own recovery state
→ max one unresolved recovery position per lane
```

Research params:

```text
lane_count
initial allocation
assignment rule
rebalance rule
lane caps
all-lanes-busy rule
```

No fijar N=2.

---

## C. SELECT_ONE

Si existen varias oportunidades concurrentes:

```text
fund one
skip the rest for that policy
```

Ranking recomendado:

```text
economic edge / EV
not raw probability alone
```

Persistir:

```text
candidate set
selected
score
skipped + reasons
```

---

## D. PORTFOLIO_KELLY / SIMULTANEOUS_KELLY

Research-backed challenger.

```text
choose stake vector
→ optimize expected log wealth
subject to exposure constraints
```

Existing OPEN positions:

```text
fixed/reserved
```

Optimizer:

```text
allocates only remaining available capital
```

---

# 21. MONTE_CARLO / STRESS — real status

Real DB inventory:

```text
REPLAY=15
MONTE_CARLO=0
STRESS=0
```

Therefore:

```text
MC/STRESS
→ implemented/tested
→ NOT yet run as real persisted studies
```

Do not claim otherwise.

Do not run final comparative MC/STRESS until event-time/open-position semantics are corrected.

---

# 22. Stochastic checkpoint rule

Once runtime v2 is correct:

```text
initial real MC + Stress
→ required smoke/evaluation
```

Then rerun when:

```text
1. material policy/config/semantics change
OR
2. resolved executable sample >= 2 × last stochastic sample
OR
3. season/evidence cohort closes
OR
4. canonical correction changes previous basis
```

This is a compute/research cadence.

It is NOT a statistical sufficiency threshold.

Every checkpoint may return:

```text
INSUFFICIENT_EVIDENCE
```

Future integrated evaluator should own the trigger.

Until then, handoffs/tickets should carry:

```text
last_stochastic_sample
next_trigger
last_config_identity
```

---

# 23. Implementation closure criteria

Capital implementation audit may close when ALL are true:

```text
1. T-30-target execution path exists
2. older valid pre-match price can be explicit fallback
3. position OPEN state exists
4. stake is reserved at placement
5. open exposure reduces available cash
6. future winnings cannot fund earlier placements
7. settlement only after result known
8. permanent missing-price rows do not deadlock stream
9. missing price remains auditable
10. all seven current policy families remain executable/auditable
11. concurrency semantics are deterministic
12. recovery has at least one explicit supported concurrency challenger
13. ruin/termination emits alert
14. REPLAY remains reproducible
15. one real MC run passes
16. one real Stress run passes
17. Football-Data one-season historical ingestion is proven
18. human-readable Capital evidence is persisted/derivable
19. normal prospective Capital lifecycle needs no manual activation
```

---

# 24. Policy-selection closure criteria

Separate from implementation closure.

Do NOT use one universal arbitrary N.

Stages:

```text
A. mechanical validation
→ one populated league-season
→ REPLAY + MC + Stress
→ event-time correct

B. historical comparative study
→ multiple league-season blocks
→ real sourced 1X2

C. prospective confirmation
→ automatic T-30/fallback evidence
→ stochastic geometric checkpoints
```

A policy disposition can stabilize when:

```text
- not driven by one league-season
- survives at least two successive evidence checkpoints
- REPLAY and stochastic/stress evidence are not materially contradictory
- no hidden implementation/provenance blocker
- parameter neighborhood is not catastrophically unstable
- risk is not dominated without compensating benefit
```

Allowed conclusions:

```text
KEEP
PROMOTE
LOWER_PRIORITY
DROP
RESEARCH
INSUFFICIENT_EVIDENCE
```

Do not force one winner.

---

# 25. Human-readable Capital evidence requirement

For every settled simulated position, product should be able to derive something equivalent to:

```text
model: DIXON_COLES
decision: VALUE 0.02
capital_policy: FRACTIONAL_KELLY lambda=0.25

action: AWAY
price: 2.10
price_source: ...
price_age: ...

bankroll_equity_before: 100u
reserved_before: 12u
available_cash_before: 88u

requested_stake: 1.8u
applied_stake: 1.8u

status: SETTLED
result: LOSS
P&L: -1.8u

bankroll_equity_after: 98.2u
reserved_after: ...
drawdown: ...
termination: none
```

Frontend presentation remains deferred.

Persistence semantics first.

---

# 26. Findings classification

## CONFIRMED IMPLEMENTATION GAP

```text
permanent early price gap can deadlock all later longitudinal evidence
```

## CONFIRMED MODELING GAP

```text
no explicit OPEN-position / settlement-time / reserved-capital lifecycle
```

## CONFIRMED CONCURRENCY REQUIREMENT

```text
29/32 placements had another position already open
max simultaneous open = 10
```

## CONFIRMED EVIDENCE GAP

```text
4365 historical DC Predictions
but only 8 price-valid historical MODAL rows
```

## CONFIRMED HISTORICAL SOURCE

```text
Football-Data
→ Eredivisie 2024/25
→ 306/306 complete 1X2
→ pre + closing
```

## CONFIRMED RECONCILIATION WORK

```text
direct normalized mapping = 182/306
→ aliases/canonical reconciliation required
```

## CONFIRMED STOCHASTIC GAP

```text
real MC runs = 0
real Stress runs = 0
```

## DISCARDED SOURCE

```text
TheStatsAPI
→ 403 with validated key
→ unnecessary because Football-Data is sufficient
→ do not make it a blocker
```

---

# 27. Likely ticket boundaries — for F008, not automatic

Most coherent current split:

## Ticket candidate A — Historical Market Evidence

Outcome:

```text
Football-Data historical 1X2 ingestion
+
canonical reconciliation
+
one-shot activation lifecycle
+
historical temporal provenance/imputation
+
coverage state
```

This is independent infrastructure useful for Capital research and future enabled leagues.

---

## Ticket candidate B — Capital Runtime / Event-Time v2

Outcome:

```text
T-30 target / pre-match fallback
+
OPEN positions
+
reserved exposure
+
available cash
+
result-time settlement
+
permanent-gap progression
+
overlap semantics
+
ruin alerts
+
human-readable ledger
+
longitudinal automatic progression
+
MC/Stress checkpoint metadata
```

Recovery-lane/portfolio variants should be included only if research/acceptance can stay bounded.

Otherwise:

```text
concurrency architecture
→ runtime v2 base

new CapitalPolicy challenger
→ later research ticket
```

Do not create one ticket per finding.

---

# 28. Durable rules for main chat

```text
CAPITAL-01
Prediction may exist without odds.

CAPITAL-02
Execution targets T-30.

CAPITAL-03
If no exact T-30 price exists, use latest valid pre-match quote as explicit fallback.

CAPITAL-04
Only no pre-match quote at all means NO_EXECUTABLE_PRICE.

CAPITAL-05
Stake is allocated/reserved at placement.

CAPITAL-06
P&L is applied only when the result is known.

CAPITAL-07
OPEN positions reduce available cash.

CAPITAL-08
Future winnings cannot finance later positions before settlement.

CAPITAL-09
Permanent missing-data candidates must remain auditable but cannot deadlock later Capital evidence.

CAPITAL-10
Historical price may be real with imputed timestamp; provenance must say so.

CAPITAL-11
Historical opening/pre-closing maps to ASSUMED_T6H for research.

CAPITAL-12
Historical closing maps to ASSUMED_T30M for research.

CAPITAL-13
Historical odds ingestion is one-shot on league enablement, not daily.

CAPITAL-14
Football-Data is the current primary historical odds source.

CAPITAL-15
TheStatsAPI is discarded and not a blocker.

CAPITAL-16
Multiple overlapping positions are a normal case, not an edge case.

CAPITAL-17
Recovery lanes are a challenger; lane count is not fixed.

CAPITAL-18
SELECT_ONE should rank by economic edge/value, not pmax alone.

CAPITAL-19
Simultaneous/portfolio Kelly is a research-backed challenger.

CAPITAL-20
A ruined/terminated policy is never silently reset.

CAPITAL-21
Ruin/termination must emit an explicit operational alert.

CAPITAL-22
New parameters after ruin imply a new version/run.

CAPITAL-23
REPLAY remains automatic/current evidence mode.

CAPITAL-24
MC/STRESS run after runtime semantics are corrected.

CAPITAL-25
MC/STRESS rerun on material change, sample doubling, season close, or basis correction.

CAPITAL-26
Stochastic checkpoint != promotion gate.

CAPITAL-27
No policy winner is forced.

CAPITAL-28
Real-money execution remains absent/forbidden.

CAPITAL-29
Frontend/reporting work waits until persistence/lifecycle semantics are correct.
```

---

# 29. Recommended next action for main chat

Research phase is sufficiently closed.

Next:

```text
1. Use F008 to decide ticket boundaries.
2. Do not reopen broad Capital research.
3. Define acceptance criteria from this handoff.
4. Implement only concrete missing outcomes.
5. Backfill one Football-Data league-season first.
6. Validate runtime v2 event-time semantics locally.
7. Then run first real REPLAY + MONTE_CARLO + STRESS study.
8. Only afterward begin CapitalPolicy selection/evaluator work.
```

---

# 30. Final state

```text
CAPITAL AUDIT
→ CLOSED AS RESEARCH
→ NOT CLOSED AS IMPLEMENTATION

CAPITAL ENGINE
→ EXISTS

CURRENT LONGITUDINAL OPERATION
→ NOT SUFFICIENT

HISTORICAL ODDS SOURCE
→ FOOTBALL-DATA APPROVED AS PRIMARY

THESTATSAPI
→ DISCARDED

CONCURRENCY
→ MATERIAL / STRUCTURAL
→ MAX OBSERVED OPEN = 10

EVENT-TIME / RESERVED CAPITAL
→ REQUIRED

RUIN ALERTING
→ REQUIRED

MONTE_CARLO / STRESS
→ implemented
→ real study pending runtime-v2 semantics

NEXT
→ MAIN CHAT / F008 TICKET DEFINITION
