# Finsport — Research previo a FS-016: Capital Runtime / Event-Time v2

**Nombre canónico:** `Finsport_FS016_capital_concurrency_settlement_research_handoff_FINAL.md`
**Fecha:** 2026-09-14
**Estado:** `FINAL — REFERENCE ONLY / PRE-TICKET RESEARCH HANDOFF`
**Baseline aceptado:** `Finsport_FS016_capital_concurrency_settlement_research_handoff.md`
**Objetivo posterior:** permitir definir `FS-016 → Capital Runtime / Event-Time v2` sin decisiones funcionales o metodológicas abiertas.
**No es:** ticket, implementation plan, selección de ganador, autorización de dinero real, activación de R45 ni activación de Inkabet.

---

# 1. Final executive contract

Esta pasada reemplaza únicamente las decisiones del handoff anterior que trataban
`max_lanes` como una matriz experimental y que permitían recovery lanes paralelas.

El contrato final para FS-016 es:

```text
one existing CapitalPolicy family
→ one approved research configuration
→ one fixed max_lanes
→ one independent initial bankroll = 100u
```

No existe:

```text
policy × lane-count grid
```

en el runtime automático.

Dentro de cada configuración:

```text
bankroll_equity
reserved_exposure
available_cash
```

son globales a esa configuración.

Nunca:

```text
100u per lane
```

Las siete configuraciones automáticas comparten el mismo stream de Decision para conservar
comparabilidad, pero **no comparten bankroll entre ellas**.

---

# 2. Authoritative fixed `max_lanes`

## 2.1. Final policy table

| CapitalPolicy | Fixed `max_lanes` | Concurrent? | Lane semantics | Stake state | Shared bankroll | v1 disposition |
|---|---:|---|---|---|---|---|
| `FLAT_UNIT` | **10** | Yes | exposure slots only | stateless; fixed `unit` | one 100u config bankroll | **SAFE TO DELETE AFTER V2 ACCEPTANCE** |
| `FIXED_FRACTION_BANKROLL` | **10** | Yes | exposure slots only | current realized equity × `fraction` | one 100u config bankroll | **SAFE TO DELETE AFTER V2 ACCEPTANCE** |
| `FIXED_TARGET_PROFIT_NO_RECOVERY` | **10** | Yes | exposure slots only | price + fixed target; no previous-result state | one 100u config bankroll | **SAFE TO DELETE AFTER V2 ACCEPTANCE** |
| `LEGACY_RECOVERY` | **1** | No | one sequential recovery chain | previous settled result → `target_profit`, `accumulated_loss`, `step` | one 100u config bankroll | **SAFE TO DELETE AFTER V2 ACCEPTANCE** |
| `LEGACY_CAPPED` | **1** | No | one sequential capped-recovery chain | previous settled result + cap/step state | one 100u config bankroll | **SAFE TO DELETE AFTER V2 ACCEPTANCE** |
| `LEGACY_PARTIAL` | **1** | No | one sequential partial-recovery chain | previous settled result + accumulated loss | one 100u config bankroll | **SAFE TO DELETE AFTER V2 ACCEPTANCE** |
| `FRACTIONAL_KELLY` | **10** | Yes | exposure slots only | current realized equity + p + price | one 100u config bankroll | **SAFE TO DELETE AFTER V2 ACCEPTANCE** |

The four `10` values are:

```text
FINSPORT OPERATIONAL MAX
```

based on:

```text
maximum simultaneous OPEN observed locally = 10
```

They are **not** theoretical maxima of those policies.

The three `1` values are methodological constraints of the existing recovery families, not
an optimization result.

---

# 3. Concurrency classification

| CapitalPolicy | Classification | Fixed `max_lanes` | Why | Literature / methodology status |
|---|---|---:|---|---|
| `FLAT_UNIT` | **B — NATURALLY CONCURRENT** | 10 | one wager does not change the next stake formula; only shared cash can bind | concurrency does not change the policy formula |
| `FIXED_FRACTION_BANKROLL` | **B — NATURALLY CONCURRENT** | 10 | stake depends on current realized equity, not an unresolved previous result | valid with shared-equity sizing + separate available-cash funding gate |
| `FIXED_TARGET_PROFIT_NO_RECOVERY` | **B — NATURALLY CONCURRENT** | 10 | each stake is computed from target profit and current execution price independently | no recovery sequence exists |
| `LEGACY_RECOVERY` | **A — STRICTLY SEQUENTIAL** | 1 | next stake depends on the loss/win of the previous settled step | existing code rejects concurrent recovery; recovery/loss-chasing methodology is sequential |
| `LEGACY_CAPPED` | **A — STRICTLY SEQUENTIAL** | 1 | cap is applied to a recovery step whose state depends on prior settled outcomes | parallel chains would be a new strategy variant |
| `LEGACY_PARTIAL` | **A — STRICTLY SEQUENTIAL** | 1 | accumulated loss is the state of one ordered recovery sequence | parallel chains would materially change sequence semantics |
| `FRACTIONAL_KELLY` | **B — NATURALLY CONCURRENT** | 10 | the existing policy is scalar fractional Kelly per candidate; unresolved positions can coexist subject to shared cash | valid as existing independent-bet Kelly, explicitly not Portfolio Kelly |

No current policy uses class C in FS-016.

---

# 4. Final recovery-concurrency decision

## 4.1. Parallel recovery lanes are removed from FS-016

The previous handoff proposed:

```text
lane A
→ recovery sequence A

lane B
→ recovery sequence B

...
```

That design is mathematically possible as a **new parallel-chain strategy**, but it is not
sufficiently equivalent to the existing recovery family to preserve the current policy identity.

The current formulas have one mutable ordered state:

```text
target_profit
accumulated_loss
step
```

and their next request is defined only after the previous recovery step has a real settled
outcome.

The current engine also deliberately returns:

```text
UNAVAILABLE_CONCURRENT_RECOVERY_STEP
```

when more than one actionable recovery Decision shares the same economic batch.

The final methodological check supports the conservative interpretation:

```text
existing recovery family
→ one ordered recovery chain
→ previous real result required
→ max_lanes = 1
```

Literature on loss chasing / martingale-like recovery likewise treats escalation as a
sequence conditioned on prior losses or consecutive losses. It does not establish that N
independent concurrent chains are the same strategy.

Therefore:

```text
parallel recovery lanes
→ NOT FS-016
```

If ever desired later:

```text
parallel recovery sequences
→ new explicit strategy/config research question
```

rather than silently changing `LEGACY_RECOVERY`, `LEGACY_CAPPED` or `LEGACY_PARTIAL`.

## 4.2. Continuous operation with `max_lanes=1`

`max_lanes=1` does **not** mean the policy stops after one bet.

Lifecycle:

```text
recovery lane FREE
→ candidate may become pending for its future execution event

position OPEN
→ recovery lane BUSY
→ unresolved result is never guessed

settlement LOSS
→ update the one recovery state
→ lane FREE

settlement WIN
→ reset recovery state
→ lane FREE

settlement VOID
→ preserve pre-position recovery state
→ lane FREE
```

Future opportunities remain pending until their own valid execution-price event.

If the recovery lane is free when that event arrives:

```text
best valid due candidate
→ may be admitted
```

If it is still occupied when the candidate's final valid execution event arrives:

```text
candidate
→ EXPIRED_CAPACITY
```

It must **not** be placed later using a stale market price merely because kickoff has not yet
occurred.

That refinement is required by the actual market-capture contract described below.

---

# 5. Shared bankroll contract

Every configuration has:

```text
initial_bankroll = 100u
```

Definitions:

```text
bankroll_equity
= initial_bankroll + cumulative realized P&L

reserved_exposure
= sum(applied_stake of OPEN positions)

available_cash
= bankroll_equity - reserved_exposure
```

Placement:

```text
bankroll_equity
→ unchanged

reserved_exposure
→ +applied_stake

available_cash
→ -applied_stake
```

Settlement WIN:

```text
reserved_exposure
→ -stake

bankroll_equity
→ +stake * (price - 1)
```

Settlement LOSS:

```text
reserved_exposure
→ -stake

bankroll_equity
→ -stake
```

Settlement VOID:

```text
reserved_exposure
→ -stake

bankroll_equity
→ unchanged
```

When a formula uses bankroll, its formula input is:

```text
bankroll_equity
```

not `available_cash`.

Funding is a separate condition:

```text
requested_stake <= available_cash
```

For naturally concurrent policies:

```text
open positions <= 10
```

and shared cash may produce an effective open count below 10.

For recovery:

```text
open positions <= 1
```

---

# 6. Current prospective market-capture contract

The current source authority and checkout confirm exactly three scheduled prospective market
windows:

```text
market-t6h
market-t60m
market-t30m
```

Current default parameters are:

```text
T-6h:
target = kickoff - 360m
normal through target + 10m
late through target + 15m

T-60m:
target = kickoff - 60m
normal through target + 10m
late through target + 15m

T-30m:
target = kickoff - 30m
normal through target + 10m
late through target + 15m
```

Therefore the **actual final scheduled market observation opportunity** is:

```text
target T-30
actual allowed capture interval:
[T-30, T-15]
```

depending on the scheduler wake and successful provider work.

Current pipeline wake default:

```text
900 seconds
= 15 minutes
```

Important:

```text
T-30
→ target name

actual OddsObservation
→ observed_at when Finsport really captured it
```

No CURRENT scheduled prospective market capture exists at:

```text
T-10
T-7
T-1
```

FS-016 must not invent those observations.

---

# 7. Decision time != execution price time

This distinction is mandatory.

A sporting model can produce a probability/action without market odds.

Capital cannot execute an economic position without a real timestamped price because:

```text
P&L needs price
```

and these policies also use price directly in sizing:

```text
FIXED_TARGET_PROFIT_NO_RECOVERY
LEGACY_RECOVERY
LEGACY_CAPPED
LEGACY_PARTIAL
FRACTIONAL_KELLY
```

Even:

```text
FLAT_UNIT
FIXED_FRACTION_BANKROLL
```

need price for the eventual WIN payoff.

Therefore:

```text
Prediction ready
!=
Decision logic known
!=
execution-price evidence ready
!=
Capital position placed
```

---

# 8. Current Prediction / Decision paths that can feed Capital

Operational exclusions for this research:

```text
R45
→ DISABLED

automatic Inkabet
→ DISABLED
```

Current active Prediction families relevant to Capital are:

```text
DIXON_COLES
INDEPENDENT_POISSON
ELO_MULTINOMIAL_LOGIT
MARKET_CONSENSUS
```

Current normal Decision families are:

```text
MODAL_ALL

SELECTIVE_CONFIDENCE
thresholds:
0.40
0.45
0.50
0.55
0.60

VALUE
minimum_ev:
0.00
0.02
0.05
```

Current code deliberately does **not** create `VALUE` Decisions for `MARKET_CONSENSUS`.

---

# 9. Exact current timing behavior

## 9.1. Sporting models

Current pipeline considers:

```text
DIXON_COLES
INDEPENDENT_POISSON
ELO_MULTINOMIAL_LOGIT
```

for pre-match `NS/TBD` Matches inside:

```text
FOOTBALL_CAPTURE_HORIZON_HOURS
```

whose current default is 168 hours.

The sporting candidate uses:

```text
cutoff =
earliest kickoff in that competition/day group
- 1 microsecond
```

and strict-prior sporting history.

Therefore the sporting probability can be **mechanically produced well before T-30**.

A crucial current detail is:

```text
Decision.decision_time
→ uses the prediction cutoff
```

rather than necessarily representing the wall-clock moment the row was first persisted.

FS-016 must not treat the existing sporting `decision_time` field as a real simulated
placement timestamp.

## 9.2. Current sporting Decision economics

`MODAL_ALL`:

```text
action
→ model modal outcome

price
→ attached if valid market evidence already exists
```

`SELECTIVE_CONFIDENCE`:

```text
action / NO_BET
→ probability threshold

price
→ attached if actionable and market evidence exists
```

`VALUE`:

```text
action / NO_BET
→ explicitly depends on valid prices and EV
```

A sporting PredictionExperiment is immutable by logical identity. Therefore a `VALUE`
Decision generated before later market snapshots is not automatically transformed into a later
VALUE Decision merely because a new price arrived.

That existing behavior is one reason FS-016 requires an explicit execution-time Decision
revalidation contract.

## 9.3. Market Consensus

`MARKET_CONSENSUS v2` is created only from a completed market capture batch.

Prospectively it can therefore produce separate Predictions at:

```text
T-6h batch
T-60m batch
T-30m batch
```

subject to actual capture execution inside each window.

For each Market Consensus batch, current code preserves a lower temporal bound:

```text
capture_work_item.executed_at
<= selected market observations
< capture-run cutoff
```

so an earlier window cannot leak into the later batch.

Its Decision time is tied to the completed capture batch.

The final meaningful CURRENT Market Consensus update is consequently:

```text
market-t30m completed batch
```

whose actual observation occurs no later than T-15 under the present capture contract.

---

# 10. Authoritative execution-timing table

| Prediction / Decision family | Earliest valid Decision | Market-dependent? | Execution moment | Required price provenance | Terminal `NO_BET` rule |
|---|---|---|---|---|---|
| Sporting (`DIXON_COLES` / Poisson / Elo) + `MODAL_ALL` | sporting Prediction can exist once valid sporting evidence/readiness is available; currently often days before kickoff | action: **No**; economic execution: **Yes** | **actual successful `market-t30m` capture event**, same pipeline cycle | exact selected OddsObservation from the `market-t30m` batch | earlier research Decisions do not terminate Capital; explicit execution-time `NO_BET` is terminal |
| Sporting + `SELECTIVE_CONFIDENCE` | same as sporting Prediction; threshold action can be known early | action: **No**; economic execution: **Yes** | same common `market-t30m` execution event | exact `market-t30m` batch quote for the selected action | execution-time threshold `NO_BET` is terminal |
| Sporting + `VALUE` | only meaningful economically once valid 1X2 price evidence exists; earliest scheduled evidence can be T-6h | **Yes** | re-evaluate at common `market-t30m` execution event | exact `market-t30m` batch; VALUE must be recalculated against that same price set | execution-time `NO_VALID_MARKET` / no EV above threshold → terminal `NO_BET` |
| `MARKET_CONSENSUS` + `MODAL_ALL` | after each completed market batch; earliest T-6h | Prediction: **Yes**; Decision action itself uses MC probability | use the **T-30 Market Consensus batch** as execution batch | same governed T-30 batch; selected quote must be inside its lower/upper evidence bounds | explicit T-30 Decision `NO_BET` is terminal |
| `MARKET_CONSENSUS` + `SELECTIVE_CONFIDENCE` | after each completed market batch; earliest T-6h | Prediction: **Yes** | use the **T-30 Market Consensus batch** as execution batch | same governed T-30 batch | explicit T-30 threshold `NO_BET` is terminal |

No `MARKET_CONSENSUS + VALUE` row exists because CURRENT code intentionally skips VALUE for
Market Consensus.

---

# 11. One deterministic placement contract

FS-016 must use **one common placement rule** for every Capital source:

```text
all Capital placements
→ wait for the Match's successful market-t30m capture
→ evaluate/revalidate the Decision for execution using that exact batch
→ place immediately in the same pipeline cycle if:
     action is BET
     execution quote exists
     lane available
     cash available
→ otherwise finish with the appropriate non-placement state
```

This supersedes the earlier broad concept:

```text
any time from T-30 to T-1
```

because CURRENT Finsport does not observe a new market price at T-10/T-1.

## 11.1. What “T-30 placement” means

It does **not** mean:

```text
hardcoded clock instant kickoff - 30m
```

It means:

```text
the actual successful market-t30m capture event
```

which may occur:

```text
T-30 ... T-15
```

under the current tolerances.

Use actual:

```text
OddsObservation.observed_at
CaptureWorkItem.executed_at
CaptureRun.completed_at
```

as appropriate for provenance.

Never backdate placement to the target.

## 11.2. No stale fallback

If the final `market-t30m` window is missed or produces no valid selected quote:

```text
no Capital placement
```

Do not silently fall back to:

```text
T-60
T-6h
```

as if that price were still executable at T-30/T-15.

Terminal evidence should distinguish:

```text
NO_EXECUTION_PRICE
MISSED_EXECUTION_WINDOW
```

from policy `NO_BET`.

---

# 12. Execution-time Decision revalidation

The execution layer must not silently combine:

```text
old Decision
+
new price
```

For each due Capital execution event, one atomic evidence contract must be created/reused.

It freezes:

```text
Prediction identity
Decision policy code/variant/config
Decision action
Decision reason
model probability
selected OddsObservation
selected price
expected value
execution decision time
market-t30m capture identity
```

Exact ORM representation is preflight/implementation detail.

Functional contract is not.

## 12.1. Sporting MODAL / confidence

Their action can be known earlier.

At execution:

```text
re-evaluate/materialize execution Decision
→ same sporting probability
→ exact T-30 market batch
→ attach exact selected execution quote
```

If sporting evidence/readiness changed legitimately before execution, use the latest eligible
pre-execution Prediction according to the existing currentness rules.

## 12.2. VALUE

At execution:

```text
VALUE
→ MUST be recomputed against the exact T-30 batch
```

A VALUE approval against price X cannot be executed at Y without revalidation.

If the T-30 price changes the winning action or turns it into `NO_BET`:

```text
execution Decision
→ reflects that new action
```

The older Decision remains immutable research evidence.

## 12.3. Market Consensus

For T-30 Market Consensus:

```text
Prediction market evidence
+
Decision selected-price evidence
→ same completed T-30 capture batch
```

Existing FS-013 lower-bound semantics should be preserved.

---

# 13. Price/provenance freeze

For one placed position:

```text
price used for candidate EV ranking
==
price used for policy stake request
==
price used for realized P&L
==
Decision.selected_price frozen at execution
```

and:

```text
selected_odds_observation
→ exact provenance of that selected price
```

No later quote substitution.

No settlement-time quote substitution.

No “best current price” rewrite after placement.

For a T-30 execution batch containing multiple canonical bookmakers, current governed market
semantics may select the best quote for the chosen outcome **among the valid latest quotes
inside that same T-30 batch**.

It must not choose an older T-60 quote merely because the historical number is better.

---

# 14. Candidate ranking at the common execution event

The accepted ranking remains:

```text
EV_unit =
model_probability * selected_price - 1
```

descending.

Tie-break:

```text
earliest kickoff
→ stable Match/Decision identity
```

All contenders in a capacity conflict are ranked using their exact T-30 execution evidence.

No policy-specific ranking is introduced.

No dynamic admission threshold is introduced.

For automatic FS-016 Capital, every policy sees the same ranked Decision stream.

---

# 15. Waiting semantics after the timing correction

With the final price contract, `WAITING` has a narrower precise meaning.

A future opportunity can wait while:

```text
its final T-30 execution-price event has not occurred yet
```

Example:

```text
recovery position A OPEN
future Match B already has sporting Prediction
→ B is pending

A settles
before B's T-30 capture
→ B can still be considered normally at B's execution event
```

At B's actual T-30 capture event:

```text
lane free
→ may place

lane busy
→ EXPIRED_CAPACITY
```

B does **not** remain economically executable until kickoff using the frozen T-30 quote.

This is the only temporally honest behavior without adding new market polling after T-30.

For naturally concurrent policies the same rule applies when all 10 slots are occupied.

---

# 16. `NO_BET` terminality

## Before the execution event

Earlier `NO_BET` rows are research evidence.

They are **not** automatically terminal for Capital because:

- later market evidence may change VALUE;
- Market Consensus probabilities change by scheduled capture window;
- an execution-time revalidation has not occurred yet.

Therefore:

```text
before final execution event
NO eligible execution Decision yet
→ PENDING
```

## At the execution event

At the actual successful T-30 batch:

```text
explicit eligible execution Decision = NO_BET
→ config+Match terminal NO_BET
→ zero exposure
→ do not keep recomputing operational Decisions hoping it flips
```

Distinguish:

```text
NO_BET
```

from:

```text
UNAVAILABLE_NO_DECISION
NO_EXECUTION_PRICE
MISSED_EXECUTION_WINDOW
EXPIRED_CAPACITY
INSUFFICIENT_AVAILABLE_CASH
```

No-bet and unavailability are different evidence.

## If no execution Decision exists

If no eligible execution Decision exists when a valid T-30 batch is ready:

```text
config+Match
→ UNAVAILABLE_NO_DECISION_AT_EXECUTION
```

Do not invent a Decision later against stale T-30 price.

If no T-30 batch ever arrives:

```text
→ MISSED_EXECUTION_WINDOW
```

---

# 17. Placement lock

Placement lock scope remains:

```text
Capital configuration/run + Match
```

not global Match.

After placement:

```text
same config + Match
→ no second position
→ later Prediction/Decision rows cannot mutate the OPEN position
```

Other Capital configurations remain independent and may also place on the same Match using
their own 100u bankroll.

For automatic FS-016 they all consume the same execution Decision evidence, so the comparison
remains controlled.

---

# 18. Insufficient capital and ruin

The accepted v2 distinction remains.

If:

```text
requested_stake > available_cash
```

because other positions are OPEN:

```text
temporary funding constraint
!= practical ruin
```

At the one final execution event there is no later quote to retry, so this candidate becomes:

```text
INSUFFICIENT_AVAILABLE_CASH
```

for that Match/config.

The configuration continues for future Matches.

Practical ruin / termination is reserved for:

```text
bankroll_equity <= 0
```

or an explicit policy terminal rule such as:

```text
LEGACY_CAPPED
→ MAX_RECOVERY_STEPS
```

No refill.

No hidden parameter change.

No recovery reset to make the next stake fit.

---

# 19. Settlement contract — retained

Accepted settlement research remains unchanged except where it now interacts with fixed lane
counts.

Authority:

```text
API-Football
→ canonical result provider
```

For OPEN positions:

```text
deduplicate by Match/API-Football fixture
→ batch refresh
→ terminal canonical result controls settlement
```

No second result provider is introduced.

No duration heuristic can settle a position.

`kickoff + expected duration` remains only a scheduling hint.

## 19.1. `result_known_at`

Required:

```text
result_known_at
= moment Finsport actually persisted/recognized terminal canonical information
```

If PC is off during the match:

```text
do not backdate result_known_at
```

On restart:

```text
overdue OPEN positions
→ immediate catch-up
→ canonical terminal result
→ result_known_at = catch-up observation time
→ settle
→ release capital/lane
```

---

# 20. Terminal-result debt repair — retained and closed

FS-016 must prevent:

```text
terminal-looking Match
+
outcome = ""
→ OPEN forever
```

Terminal football statuses currently relevant:

```text
FT
AET
PEN
AWD
WO
CANC
ABD
```

Final handling:

### `FT / AET / PEN / AWD / WO`

Expected:

```text
canonical HOME/DRAW/AWAY
```

If local status is terminal but outcome is blank:

```text
terminal-result debt
→ explicitly refresh/reconcile from API-Football
→ do not guess
→ keep position unresolved until canonical outcome is obtained
```

The current planner's existing “terminal local status + blank outcome → result refresh
ineligible” behavior must not be allowed to strand v2 positions.

### `CANC / ABD`

They are terminal-without-canonical-1X2 outcome.

For Capital simulation:

```text
position
→ VOID
→ reserved stake released
→ realized P&L = 0
```

No HOME/DRAW/AWAY is fabricated.

For recovery policies:

```text
VOID
→ recovery state exactly as before that position
```

### `PST / SUSP`

They are not generalized into terminal settlement.

```text
no result guessed
```

Their lifecycle continues according to canonical Match updates/rescheduling.

---

# 21. Capital v1 is not semantically equivalent to v2

There is **no** existing CapitalPolicy for which current v1 derived results can be presented as
equivalent CURRENT v2 evidence.

Reason applies even when v2 `max_lanes=1`.

v1 currently:

```text
ordered Decision batch
→ request stake
→ canonical outcome already known
→ immediate settlement
→ next batch sees updated bankroll/state
```

v2:

```text
execution event
→ persistent OPEN
→ exposure reserved
→ later positions compete with occupied capital/lanes
→ settlement only when Finsport actually learns canonical terminal result
```

Therefore:

```text
max_lanes=1
does not rescue v1 equivalence
```

For all seven policies:

```text
v1 derived Capital
→ LEGACY / SUPERSEDED
→ not CURRENT v2 evidence
```

---

# 22. V1 retirement decision

## 22.1. Always keep upstream evidence

Never delete as part of Capital retirement:

```text
Match
canonical result
OddsObservation
historical market evidence
PredictionExperiment
Prediction
Decision
readiness evidence
CaptureRun / CaptureWorkItem
PipelineRun operational audit
```

These are upstream evidence or runtime audit, not invalid Capital derivations.

## 22.2. Derived v1 data

Retire after v2 acceptance:

```text
CapitalLongitudinalSeries v1
CapitalExperiment v1
CapitalPolicyRun v1
CapitalLedgerEntry v1
legacy/current_snapshot pointers to v1
legacy Capital reporting derived from those rows
```

Final classification:

```text
SAFE TO DELETE AFTER V2 ACCEPTANCE
```

for all seven policies.

## 22.3. FK / reconstruction audit

Current schema shows:

```text
CapitalPolicyRun
→ CASCADE from CapitalExperiment

CapitalLedgerEntry
→ CASCADE from CapitalPolicyRun

CapitalLongitudinalSeries.current_snapshot
→ SET_NULL when its CapitalExperiment is removed

CapitalExperiment.longitudinal_series
→ PROTECTs deleting the series while snapshots remain

CapitalExperiment.source_experiment
→ PROTECT upstream PredictionExperiment from accidental deletion
```

No downstream product entity requires a v1 ledger row as canonical truth.

`PipelineRun` keeps Capital experiment IDs in JSON audit/report data rather than a foreign key.

The v1 engine/config/code history plus immutable upstream Decisions/Odds/Results are sufficient
to reconstruct old derived research if ever needed.

Therefore retaining every v1 ledger row in the active DB is not necessary for auditability.

## 22.4. Bounded retirement sequence

Do not clean before v2 acceptance.

Required order:

```text
1. implement v2
2. run v2 acceptance/UAT
3. prove v2 CURRENT reporting/evidence works
4. create bounded retirement manifest:
     v1 engine/version identities
     row counts
     experiment IDs / series IDs
     min/max timestamps
     config hashes / relevant identity
5. delete only v1-derived CapitalExperiment snapshots
     → cascades v1 PolicyRun/Ledger
6. delete superseded v1 CapitalLongitudinalSeries after snapshots are gone
7. ensure CURRENT reporting/evaluator selectors exclude legacy v1
8. preserve upstream evidence and historical PipelineRun audit
```

Exact live row counts / disk size are preflight facts.

They do **not** change the retirement decision.

The preferred cleanup is:

```text
small retirement audit record
+
full deletion of v1-derived Capital rows
```

not permanent detailed v1 ledgers in the active research surface.

---

# 23. MC / STRESS boundary

FS-016 **does include** adapting all three Capital modes to v2 semantics:

```text
REPLAY
MONTE_CARLO
STRESS
```

Reason:

Capital currently advertises all three modes as one engine capability.

Closing FS-016 with event-time semantics corrected only in REPLAY would leave two supported modes
with materially old capital/concurrency semantics.

Therefore acceptance must include:

```text
REPLAY
→ v2 shared-bankroll / OPEN / lane / event-time semantics

MONTE_CARLO
→ same fixed max_lanes and event chronology
→ stochastic outcomes
→ no immediate-settlement shortcut

STRESS
→ same v2 chronology/state
→ stress transforms remain mode-specific
```

Required persisted smoke after implementation:

```text
>= 1 real persisted MONTE_CARLO v2 run
>= 1 real persisted STRESS v2 run
```

No policy winner is selected from those smokes.

They prove engine-mode compatibility only.

---

# 24. Current automatic Prediction / Decision arm inventory

## 24.1. Engine-supported CURRENT predictive sources

Excluding disabled R45:

```text
4 Prediction source families

DIXON_COLES
INDEPENDENT_POISSON
ELO_MULTINOMIAL_LOGIT
MARKET_CONSENSUS
```

## 24.2. Decision variants

For each sporting model:

```text
MODAL_ALL
→ 1

SELECTIVE_CONFIDENCE
→ 5 thresholds

VALUE
→ 3 minimum-EV variants

total per sporting source
→ 9
```

Three sporting sources:

```text
3 × 9 = 27
```

Market Consensus:

```text
MODAL_ALL
→ 1

SELECTIVE_CONFIDENCE
→ 5

VALUE
→ intentionally absent

total
→ 6
```

Thus current source/policy variant classes are:

```text
27 + 6 = 33
```

before considering that Market Consensus can persist at multiple capture windows.

Across the full normal pre-match lifecycle, a fully produced Match can receive:

```text
sporting:
3 sources × 9 Decisions
= 27

Market Consensus:
3 scheduled market windows × 6 Decisions
= 18

total potential persisted current Decision rows
= 45
```

This inventory is **not** a request to multiply Capital by 45.

---

# 25. Automatic Capital configuration count after FS-016

## 25.1. Current longitudinal comparator authority

The CURRENT primary longitudinal Capital series uses:

```text
source_model = DIXON_COLES
decision_policy = MODAL_ALL
initial_bankroll = 100u
same manifest for seven CapitalPolicies
```

That is already the correct design principle for studying Capital itself:

```text
hold Prediction/Decision basis constant
→ compare staking/risk policies
```

## 25.2. Final automatic prospective set

FS-016 keeps exactly one automatic common Decision source:

```text
DIXON_COLES
+
MODAL_ALL
+
execution-time T-30 revalidation / price freeze
```

and exactly seven Capital configurations:

```text
1. FLAT_UNIT
   unit=1
   max_lanes=10

2. FIXED_FRACTION_BANKROLL
   fraction=0.05
   max_lanes=10

3. FIXED_TARGET_PROFIT_NO_RECOVERY
   target_profit=1
   max_lanes=10

4. LEGACY_RECOVERY
   initial_stake=1
   max_lanes=1

5. LEGACY_CAPPED
   initial_stake=1
   max_absolute_stake=5
   max_lanes=1

6. LEGACY_PARTIAL
   target_profit=1
   alpha=0.5
   max_lanes=1

7. FRACTIONAL_KELLY
   lambda=0.25
   max_lanes=10
```

Therefore:

```text
AUTOMATIC PROSPECTIVE CAPITAL CONFIGURATIONS
= 7
```

Not:

```text
7 × 4 lane counts
```

Not:

```text
7 × all Prediction sources × all Decision variants
```

The seven parameters remain:

```text
research comparator config
!= winner
!= production optimum
!= real-money risk recommendation
```

## 25.3. Per-PredictionExperiment v1 baseline

Current pipeline also creates a legacy normalized:

```text
DIXON_COLES + MODAL_ALL + FLAT_UNIT
```

per-PredictionExperiment REPLAY baseline.

FS-016 should **not** reproduce that as a second automatic Capital-v2 stream.

It is superseded by the single coherent longitudinal/event-time runtime.

This removes duplicate/noisy automatic Capital evidence.

---

# 26. Engine-supported vs automatic vs historical vs stochastic

| Surface | FS-016 disposition | Automatic recurring count |
|---|---|---:|
| **ENGINE SUPPORTED** | 7 CapitalPolicy families with their one fixed `max_lanes`; engine may consume any explicitly valid Decision basis | N/A |
| **AUTOMATIC PROSPECTIVE** | one common `DIXON_COLES + MODAL_ALL` execution stream → 7 independent 100u configurations | **7** |
| **HISTORICAL STUDY** | explicit research runs only; use the same seven fixed configurations; no lane-count matrix | **0 recurring** |
| **MONTE_CARLO STUDY** | explicit/on-demand; v2 semantics; at least one persisted acceptance smoke | **0 recurring** |
| **STRESS STUDY** | explicit/on-demand; v2 semantics; at least one persisted acceptance smoke | **0 recurring** |

A manual/historical study may later choose another Prediction/Decision source if its research
question requires it.

That does not expand the automatic runtime.

---

# 27. Historical simulation after the simplification

Historical study no longer compares lane-count grids.

It compares:

```text
the same seven policy configurations
with their approved fixed max_lanes
```

For FS-015 historical market evidence:

```text
real 1X2 price
+
imputed observation time
```

The cleanest v2 execution basis is the historical closing evidence whose time semantics are
already:

```text
ASSUMED_T30M
```

Do not present that timestamp as observed fact.

Keep accepted synthetic settlement-time semantics for historical event-time simulation.

Historical results remain:

```text
research-only
```

for timing claims.

Prospective v2:

```text
actual placed_at
actual result_known_at
actual settled_at
```

becomes authority for real event-time behavior.

---

# 28. Position lifecycle after all corrections

Candidate lifecycle:

```text
PENDING_EXECUTION_EVENT
→ T-30 batch arrives
→ execution Decision evaluated
```

Possible terminals without a position:

```text
NO_BET
UNAVAILABLE_NO_DECISION_AT_EXECUTION
NO_EXECUTION_PRICE
MISSED_EXECUTION_WINDOW
EXPIRED_CAPACITY
INSUFFICIENT_AVAILABLE_CASH
INELIGIBLE
```

Placed lifecycle:

```text
OPEN
→ SETTLED_WIN
→ SETTLED_LOSS
→ VOID
```

Run/config lifecycle:

```text
ACTIVE
→ TERMINATED
```

No second placement for the same config+Match.

No result-dependent policy-state transition while OPEN.

---

# 29. Core v2 metrics

Keep the accepted metric set, but remove N-grid comparison wording.

Per configuration:

```text
initial bankroll
current equity
ending equity

realized P&L
realized ROI
geometric/log growth

wins
losses
voids
open positions

turnover
max drawdown
drawdown duration
time to recovery

peak reserved exposure
average reserved exposure
capital utilization
peak open positions
lane utilization

candidates seen
placed
NO_BET
unavailable
expired capacity
insufficient available cash
missed execution window

practical ruin
termination reason

recovery sequence lengths
cap hits
shortfall
```

Do not select a policy from:

```text
more bets
more wins
one ending bankroll
```

alone.

---

# 30. Minimum Capital v2 human surface

FS-016 still needs only enough read-only UI to answer:

> ¿estamos ganando o perdiendo y cuánto capital está comprometido ahora?

Per automatic configuration:

```text
policy
params
max_lanes
started_at

initial bankroll
current equity
reserved exposure
available cash

realized P&L
realized ROI

wins
losses
voids
open positions

lanes used / max_lanes

max drawdown

terminated
practical ruin
termination reason

sample / elapsed period
```

Useful execution counters:

```text
NO_BET
expired capacity
missing execution price/window
```

Detailed position/audit exploration may remain in Django Admin.

General frontend cleanup remains later work.

---

# 31. What FS-016 must implement

One coherent outcome:

> Replace Capital v1's immediate-outcome replay semantics with one persistent event-time
> runtime whose seven approved policy configurations use fixed concurrency, one common
> T-30 execution evidence contract, shared per-config capital and canonical delayed
> settlement.

Required scope:

```text
one fixed max_lanes per seven policies

max_lanes=10:
FLAT_UNIT
FIXED_FRACTION_BANKROLL
FIXED_TARGET_PROFIT_NO_RECOVERY
FRACTIONAL_KELLY

max_lanes=1:
LEGACY_RECOVERY
LEGACY_CAPPED
LEGACY_PARTIAL

independent 100u per config
shared bankroll within config
bankroll_equity / reserved_exposure / available_cash

persistent OPEN positions
config+Match execution lock

common market-t30m execution event
execution-time Decision revalidation
exact T-30 price/provenance freeze
VALUE revalidation against execution price

terminal execution-time NO_BET
explicit non-placement reasons

EV ranking under capacity contention
no stale later placement

canonical API-Football settlement
batched OPEN result refresh
offline overdue catch-up
result_known_at

terminal-result debt recovery
FT/AET/PEN/AWD/WO
CANC/ABD VOID

recovery sequential state
no parallel recovery chains

v2 REPLAY
v2 MONTE_CARLO
v2 STRESS
persisted MC smoke
persisted STRESS smoke

automatic prospective config count = 7
one common DIXON_COLES + MODAL_ALL Capital source stream

historical v2 study support with explicit synthetic-time provenance

minimum Capital-v2 reporting

bounded v1 retirement after acceptance
```

---

# 32. Explicit non-goals

Keep deferred:

```text
optimal lane count after FS-016
multiple lane-count experiments
parallel recovery chains
Portfolio Kelly
dynamic admission thresholds
integrated evaluator
policy winner
Capital parameter winner
risk-free/bank opportunity-cost benchmark
general frontend redesign
low-power PC operation
general non-Capital catch-up
R45
Inkabet
alternative result provider
real betting
```

---

# 33. Acceptance implications for the later ticket

The ticket should prove at least:

## Fixed lane identities

```text
each of seven policies
→ exact approved max_lanes
```

No grid is provisioned.

## Independent bankroll

```text
7 automatic configs
→ 7 independent initial 100u bankrolls
```

No lane gets 100u.

## Natural concurrency

For each `max_lanes=10` policy:

```text
multiple positions can remain OPEN simultaneously
→ no policy-state corruption
→ shared cash enforced
```

## Recovery sequentiality

For all three recovery policies:

```text
at most one OPEN
next recovery stake
→ cannot be requested from unresolved prior result
```

After real settlement:

```text
chain continues
```

No automatic reset.

## Common execution timing

Prove no position can be placed from:

```text
T-6h
T-60
old T-30 observation at a later wall-clock time
post-T-15 without a valid T-30 capture
```

Execution must use the actual final capture batch.

## Decision-price atomicity

Construct a VALUE case where:

```text
price X
→ BET

price Y
→ NO_BET or different action
```

and prove Capital cannot execute the X Decision with Y price.

## NO_BET

At execution event:

```text
explicit NO_BET
→ terminal
```

No later operational Decision for that config+Match.

## Capacity

If all allowed slots are occupied at a candidate's execution event:

```text
→ EXPIRED_CAPACITY
```

No stale-price delayed placement.

## Settlement

Terminal canonical result:

```text
settles once
releases exposure once
updates recovery state once
```

## Terminal debt

```text
FT/AET/PEN/AWD/WO + blank outcome
→ recovery refresh path exists
→ not stranded forever
```

and:

```text
CANC/ABD
→ VOID
→ zero P&L
→ capital released
```

## Offline restart

Overdue OPEN positions:

```text
immediate catch-up
result_known_at = actual catch-up knowledge time
```

## V1 retirement

Before cleanup:

```text
v2 UAT passes
retirement manifest exists
```

After cleanup:

```text
no v1 Capital derived rows pollute current reporting
upstream evidence intact
```

## Modes

```text
REPLAY v2
→ pass

persisted MONTE_CARLO v2 smoke
→ pass

persisted STRESS v2 smoke
→ pass
```

No winner claim.

---

# 34. Implementation facts left to preflight

No product decision remains hidden in these items.

Preflight may determine:

```text
exact new ORM class/model names
Position/Lane persistence shape
whether pending candidates are rows or deterministic queries
migration number
DB indexes
select_for_update / transaction boundaries
idempotency constraints
exact pipeline function extraction
exact query batching implementation
exact live count/size of v1 Capital rows
exact effective operational env overrides
exact current provider quota at UAT
exact UI template placement
exact retirement SQL/ORM ordering after schema inspection
```

These facts may change implementation mechanics.

They must not reopen the product contract.

---

# 35. Evidence summary

## Local/current sources audited

Current permanent/product architecture confirms:

```text
Capital question
→ same Decision stream, compare policy risk/sizing

primary longitudinal stream
→ DIXON_COLES + MODAL_ALL
→ seven CapitalPolicy arms
→ initial_bankroll=100
```

Current checkout confirms:

- all seven exact policy formulas;
- recovery state is one sequential `target_profit / accumulated_loss / step` state;
- recovery concurrency is currently explicitly `UNAVAILABLE`;
- current Capital v1 settles immediately from already-known outcomes;
- no persistent OPEN/reserved-capital semantics exist;
- three prospective market windows are exactly T-6h/T-60/T-30;
- each window has +10m normal / +15m late tolerance;
- default pipeline wake is 900 seconds;
- sporting candidates are generated independently of the market capture windows;
- Market Consensus is capture-batch-bound;
- current standard Decision variants are 1 MODAL + 5 confidence + 3 VALUE;
- Market Consensus does not get VALUE;
- selected Decision price is tied to a specific protected OddsObservation;
- current `best_prices_as_of` can examine older price evidence unless a lower bound is supplied;
- Market Consensus already supplies the batch lower bound needed to prevent cross-window leakage;
- current longitudinal automatic Capital source is DIXON_COLES + MODAL_ALL;
- current v1 per-PredictionExperiment FLAT_UNIT baseline is separate/duplicative;
- current v1 Capital FK graph permits bounded derived-data retirement without deleting upstream Prediction/Decision evidence.

## Final methodological check for recovery

External methodological literature consistently describes recovery/loss-chasing as behavior
conditioned on previous or accumulated losses and sequential outcomes. The useful point for this
ticket is not whether recovery systems are advisable; it is that their next-step definition is
ordered by already-realized loss state.

Relevant examples:

- *Rational escalation of costs by playing a sequence of unfavorable gambles: the martingale*
  (Journal of Economic Behavior & Organization, 2003) treats martingale escalation as a sequence
  through consecutive losses.
- *Behavioural expressions of loss-chasing in gambling: A systematic scoping review* (2023)
  describes loss chasing in terms of continuing/intensifying after losses.
- 2026 work on loss-accumulation windows explicitly distinguishes immediate loss chasing based on
  the most recently settled bet from accumulated-loss variants.

No reviewed source establishes that multiple independent simultaneous recovery chains are
mathematically the same strategy as one existing recovery sequence.

Combined with the exact Finsport policy formulas and current concurrency guard, this is sufficient
to close:

```text
existing recovery families
→ strictly sequential
→ max_lanes=1
```

No provider call was required for this research pass.

---

# 36. Superseded decisions from the prior handoff

The following prior recommendation is superseded:

```text
max_lanes ∈ {1,2,4,10}
as an automatic experimental dimension
```

Replaced by:

```text
one fixed max_lanes per CapitalPolicy
```

The following prior recommendation is also superseded:

```text
parallel lane-local recovery chains inside existing LEGACY_* identities
```

Replaced by:

```text
LEGACY_RECOVERY max_lanes=1
LEGACY_CAPPED max_lanes=1
LEGACY_PARTIAL max_lanes=1
```

The prior generic execution concept:

```text
any time from T-30 to kickoff
```

is narrowed by current market evidence to:

```text
actual successful market-t30m capture event
→ T-30 target
→ no later than T-15 under current window
```

Everything else from the accepted baseline remains valid unless explicitly updated in this final
document.

---

# 37. Final disposition

```text
FS-016 PRODUCT DECISIONS
→ CLOSED

ONE FIXED MAX_LANES PER POLICY
→ CLOSED

POLICY CONCURRENCY CLASSIFICATION
→ CLOSED

RECOVERY CONCURRENCY
→ CLOSED

DECISION TIMING
→ CLOSED

EXECUTION TIMING
→ CLOSED

DECISION/PRICE CONTRACT
→ CLOSED

NO_BET TERMINALITY
→ CLOSED

V1 RETIREMENT
→ CLOSED

SETTLEMENT / RESULT_KNOWN_AT
→ CLOSED

TERMINAL RESULT DEBT
→ CLOSED

MC/STRESS BOUNDARY
→ CLOSED

AUTOMATIC ARM COUNT
→ CLOSED

IMPLEMENTATION FACTS
→ PRE-FLIGHT ONLY

RESEARCH REQUIRED BEFORE FS-016 TICKET
→ NONE
```

The empirical questions that remain are deliberately **post-FS-016** questions:

```text
which CapitalPolicy performs best?
are the comparator parameters good?
would a different operational max_lanes improve a naturally concurrent policy?
would a new parallel-recovery strategy deserve study?
```

They are not blockers to ticket definition.

---

# Safety boundary

Everything in this handoff remains:

```text
simulation
research
read-only sports/market evidence
```

It does not authorize:

```text
real bookmaker login
real bet placement
money transfer
real bankroll mutation
automatic financial action
```
