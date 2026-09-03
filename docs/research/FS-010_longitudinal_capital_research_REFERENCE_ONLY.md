# FS-010 — Longitudinal CapitalPolicy research

**Status:** REFERENCE ONLY
**Project:** Finsport
**Date:** 2026-09-01
**Brief:** FS-010 capital longitudinal research brief
**Product mode:** local-only / demo-only / research-oriented
**Financial side effects:** none
**Research process:** F010_guia_investigacion_handoff_research_finsport_v1.1.md
**Reconciliation note:** final Main Chat consolidation of the Deep Research passes, corrected against durable Finsport domain/architecture sources and the implemented FS-004 contract. This report is evidence/recommendation, not an approved ticket or implementation plan.

---

## 1. Executive conclusion

The recommended FS-010 methodology is a **deterministic longitudinal REPLAY over one fixed prospective Decision stream**, with all requested CapitalPolicy arms consuming the **same canonical ordered input basis**.

The primary research comparator stream should be:

```text
Prediction model = DIXON_COLES
Decision policy = MODAL_ALL
evidence class = prospective/runtime
population = global multi-league
ordering = Decision.decision_time ASC
same decision_time = one batch
```

This stream is recommended as an **experimental control**, not because DIXON_COLES or MODAL_ALL is a product winner. It reuses the normalized comparator already used by the automatic Finsport capital baseline, provides model probabilities needed by Fractional Kelly, and avoids selecting a Decision policy for its observed profitability.

The longitudinal experiment should begin at a **fixed provenance-safe epoch** determined in preflight: the earliest prospective point from which the chosen comparator stream can be reconstructed honestly under the current temporal-price and canonical-outcome contract. Evidence before that epoch is outside the FS-010 primary stream by explicit design, not silently dropped.

At any point in time, the primary longitudinal input is the **maximum complete chronological batch prefix from the fixed epoch**, where every actionable Decision up to that watermark has a canonical resolved outcome and the timestamp-valid selected price/provenance required by the current Decision contract.

`NO_BET` remains in the input/audit stream with zero capital exposure. A later actionable gap is **not skipped**: it stops the watermark until it is legitimately resolvable. A price observed later in real time must never be backdated or substituted as the earlier Decision price.

`CANC` is not a synthetic zero-stake Decision. Existing Finsport cancellation hygiene removes invalid experimental/economic derivatives and invalidates affected frozen capital evidence. A corrected canonical basis therefore causes the longitudinal REPLAY to be recomputed from the fixed epoch.

The recommended state model is:

```text
canonical longitudinal basis
→ evidence identity/hash changes
→ recompute complete REPLAY from epoch to watermark
→ persist/audit one reproducible result snapshot
```

not a mutable bankroll that is incrementally patched forever.

The primary experiment uses a **global multi-league shared 100u research bankroll**. All same-time Decisions, including cross-league Decisions, retain existing FS-004 batch semantics and compete for the same pre-batch simulated bankroll. Per-league capital runs are not part of the automatic FS-010 baseline; they may be studied later as sensitivity/descriptive evidence.

FS-010 should automatically run **REPLAY only** for the growing real-evidence longitudinal experiment. Existing `MONTE_CARLO` and `STRESS` remain separate, manual/on-demand research capabilities. FS-010 should not invent a new stochastic cadence or redefine their engines.

For the seven CapitalPolicy arms, FS-010 should reuse the **existing FS-004 reference comparator configuration** as a fixed research-control configuration:

```text
initial_bankroll = 100u

FLAT_UNIT
  unit = 1

FIXED_FRACTION_BANKROLL
  fraction = 0.05

FIXED_TARGET_PROFIT_NO_RECOVERY
  target_profit = 1

LEGACY_RECOVERY
  initial_stake = 1

LEGACY_CAPPED
  initial_stake = 1
  max_absolute_stake = 5

LEGACY_PARTIAL
  target_profit = 1
  alpha = 0.5

FRACTIONAL_KELLY
  lambda = 0.25
```

These values are frozen **only as an inherited REFERENCE COMPARATOR CONFIG for FS-010**, because they already form the implemented seven-policy comparison fixture. They are not empirically optimal, are not production defaults, and must not be promoted as risk tolerance or product staking parameters. The FS-004 research explicitly found that policy parameters remain empirically unfrozen.

The primary longitudinal metrics should reuse deterministic FS-004 metrics rather than introduce Sharpe, VaR, a new score, or a new financial metric family. Return and risk remain side by side. `ROI` keeps the engine definition:

```text
ROI = total_pnl / total_staked
```

while:

```text
turnover = total_staked / initial_bankroll
```

For deterministic REPLAY, `practical_ruin` is a path state/boolean, not a probability.

FS-010 does **not** choose a winning CapitalPolicy. Integrated evidence sufficiency, statistical winner claims, PROMOTE/DROP, multiple testing, final policy selection, and cross-layer evaluation remain FS-011 responsibilities.

## 2. Question-coverage matrix

| Question | Status | Final research conclusion |
|---|---|---|
| Q1 — Primary Decision stream | ANSWERED | Fixed prospective `DIXON_COLES + MODAL_ALL` stream; one control stream for all CapitalPolicies. No automatic value/selective secondary stream in FS-010. |
| Q2 — Global multi-league vs per-league | ANSWERED | One primary global multi-league shared bankroll; preserve cross-league same-batch semantics. Per-league runs are secondary/later sensitivity only. |
| Q3 — Eligibility / missing evidence | ANSWERED | Use a fixed provenance-safe epoch plus the maximum complete chronological batch prefix. Never skip an incomplete actionable Decision. `NO_BET` stays with zero exposure. `CANC` is removed by canonical cancellation hygiene. |
| Q4 — Full replay vs incremental state | ANSWERED | Full deterministic replay from the fixed epoch whenever canonical input identity changes. Mutable bankroll state is not the source of truth. |
| Q5 — Checkpoint / cadence | ANSWERED | Recompute when the canonical longitudinal input signature changes after settlement/reconciliation; unchanged evidence is idempotent/NO_WORK. Exact scheduler/service wiring is preflight. |
| Q6 — Initial bankroll normalization | ANSWERED | 100u research normalization, inherited from existing Finsport capital comparator. Not a real/product bankroll. |
| Q7 — Policy-by-policy research config | ANSWERED FOR FS-010 CONTROL | Reuse the existing FS-004 seven-policy comparator config as `REFERENCE COMPARATOR CONFIG`; no optimization or sensitivity sweep is required by the automatic FS-010 path. |
| Q8 — Fractional Kelly fairness | ANSWERED | Same broad source Decisions as every other policy; existing Kelly formula may request zero exposure on non-positive edge. `lambda=0.25` is inherited comparator config, not a claim of optimal Kelly fraction. |
| Q9 — REPLAY vs MC/STRESS | ANSWERED | Automatic longitudinal mode = REPLAY only. Existing MONTE_CARLO/STRESS remain manual/on-demand, separate evidence classes. |
| Q10 — Comparability key | ANSWERED | Same evidence class, source stream identity, epoch/horizon/input manifest, population, mode, initial bankroll, price provenance, engine version; policy/config identifies the arm. Mismatch => `NO COMPARABLE`. |
| Q11 — Minimal metrics | ANSWERED | Reuse deterministic FS-004 return/risk/exposure/behavior metrics. No new composite score. Stochastic-only metrics stay stochastic-only. |
| Q12 — Bounded FS-009 frontend delta | ANSWERED | Extend existing Capital section with one row per longitudinal policy arm/config plus evidence horizon/comparability context; trajectory is optional, not required. |
| Q13 — FS-011 boundary | ANSWERED | Winner selection, statistical sufficiency, PROMOTE/DROP, integrated Prediction/Decision/Capital evaluation and policy optimization stay out of FS-010. |

## 3. Current Finsport Capital facts relevant to FS-010

### 3.1 Established project facts

The durable layer order is:

```text
Prediction
→ Decision
→ CapitalPolicy
```

Capital is implemented simulation/research capability, not a wallet, bookmaker account or real execution surface.

A CapitalExperiment conceptually freezes one Decision basis, one evaluation configuration, and one or more CapitalPolicy arms. All requested policy arms consume the **exact same Decision stream**. A policy may not remove Decisions from its own source sample merely because they are losing or inconvenient.

`NO_BET` is preserved in the Capital input/audit basis and creates zero exposure.

Capital input chronology is `decision_time ASC`; same `decision_time` means the same economic batch. Stable ID ordering may support manifest/hash ordering but does not create an economic sequence inside the batch.

Every request in one batch is computed from the same pre-batch bankroll and policy state. No same-batch result may finance another same-batch Decision.

If total requested exposure exceeds the pre-batch bankroll, current engine semantics produce practical ruin/termination with zero funding of the overcommitted batch rather than proportional scaling or arbitrary subset funding.

For recovery-family policies without a canonical independent sequence assignment:

```text
>1 actionable Decision in same batch
→ UNAVAILABLE_CONCURRENT_RECOVERY_STEP
```

The arm remains auditable as `UNAVAILABLE`; it does not disappear.

### 3.2 Implemented policy families

```text
FLAT_UNIT
FIXED_FRACTION_BANKROLL
FIXED_TARGET_PROFIT_NO_RECOVERY
LEGACY_RECOVERY
LEGACY_CAPPED
LEGACY_PARTIAL
FRACTIONAL_KELLY
```

Core formulas/config semantics already belong to FS-004:

```text
FLAT_UNIT
stake = unit

FIXED_FRACTION_BANKROLL
stake = fraction * pre_batch_bankroll

FIXED_TARGET_PROFIT_NO_RECOVERY
stake = target_profit / (price - 1)

LEGACY_RECOVERY
first request = initial_stake
target = initial_stake * (first_price - 1)
subsequent request = ceil((target + accumulated_loss) / (price - 1))

LEGACY_CAPPED
legacy recovery + explicit bound(s)
requested/applied/cap_hit/shortfall/termination remain separate

LEGACY_PARTIAL
stake request concept =
(target_profit + alpha * accumulated_loss) / (price - 1)

FRACTIONAL_KELLY
edge = p * o - 1
full_kelly = edge / (o - 1)
stake = lambda * full_kelly * bankroll when edge > 0
otherwise 0 exposure
```

### 3.3 Implemented modes

```text
REPLAY
→ deterministic chronological canonical outcome/price replay

MONTE_CARLO
→ parametric stochastic paths using Decision probability, Decision price, seed, path count

STRESS
→ explicit configured scenario perturbations such as probability deterioration,
   price deterioration, losing-streak injection, degraded-regime block
```

Monte Carlo does not replace canonical replay. Stress scenarios are scenario definitions, not empirical truth.

### 3.4 Current automatic baseline

The post-FS-006 automatic capital comparator is:

```text
REPLAY
100 initial research units
FLAT_UNIT = 1u
DIXON_COLES + MODAL_ALL basis
```

It is a normalized research comparator, not a selected production CapitalPolicy.

### 3.5 Cancellation semantics

Current domain semantics:

```text
CANC
→ remove invalid experimental/economic derivatives
→ invalidate whole affected frozen CapitalExperiments rather than mutate their frozen input

PST/SUSP/FT/ambiguous
→ preserve according to canonical settlement rules
```

Therefore a cancelled fixture is not converted into a synthetic `NO_BET` ledger row.

### 3.6 Reconciliation of previous research-pass errors

Earlier Deep Research passes proposed or implied several contracts that conflict with current Finsport authority. This final report rejects them explicitly:

```text
ROI = (terminal - initial) / initial
→ REJECTED
→ current engine ROI = total_pnl / total_staked

Monte Carlo = shuffle/omit trades
→ REJECTED
→ current engine is parametric using p, price, seed, path count

CANC = neutral zero-stake Decision
→ REJECTED
→ cancellation hygiene removes invalid derivatives / invalidates affected capital evidence

policy-specific UNAVAILABLE = remove policy/sample
→ REJECTED
→ required-arm status remains explicit against the same source Decision stream

arbitrary half-Kelly / 5% / custom sensitivity ranges as empirical defaults
→ REJECTED
→ FS-004 says empirical parameter freeze is not ready
```

## 4. Primary Decision-stream recommendation

### 4.1 Alternatives

| Candidate basis | Isolation of Capital | Price availability | Probability availability | Coverage | Confounding | Reproducibility | Recommendation |
|---|---|---|---|---|---|---|---|
| Broad fixed comparator: `DIXON_COLES + MODAL_ALL` | High | Conditional: every actionable Decision must retain valid temporal selected-price provenance; gaps stop the watermark | High: DIXON_COLES provides probability needed by Kelly | Broad among comparator Decisions | Low relative to changing Decision policy | High | **PRIMARY** |
| Fixed value/selective stream | High within stream | Conditional | Usually available for probabilistic source | Lower | Higher: results become conditioned on Decision selectivity/value threshold | High | **DEFER as secondary research; not automatic FS-010 baseline** |
| Multiple reference streams | High within each stream | Varies | Varies | Split across strata | Higher interpretation burden | High if identities frozen | **Not automatic in FS-010; possible FS-011 robustness input** |

### 4.2 Recommendation

The primary FS-010 stream is:

```text
evidence class = prospective/runtime
model = DIXON_COLES
Decision policy = MODAL_ALL
population = all reportable/enabled competitions included by the chosen longitudinal epoch
```

Why: it inherits the source identity already used by the normalized automatic capital baseline; supplies model probabilities needed by Fractional Kelly; does not choose a Decision policy because it had superior observed profitability; and gives every CapitalPolicy the same broad selected stream.

Fractional Kelly may legitimately request zero exposure on a Decision with non-positive modeled edge. That is the CapitalPolicy behavior being measured, not a reason to prefilter the upstream Decision sample.

## 5. Global multi-league vs per-league recommendation

Use one **global multi-league shared bankroll** for the primary longitudinal experiment.

Rationale:

```text
one comparator stream
→ one chronological capital process
→ same finite bankroll shared across all contemporaneous opportunities
→ current FS-004 same-batch semantics remain meaningful across leagues
```

If Decisions from different competitions share the same `decision_time`, they are in the same capital batch and all requests are computed from the same pre-batch bankroll/state before any result is revealed.

The justification is experimental coherence, **not** an assumption that diversification automatically improves performance.

Per-league capital runs may be useful later to inspect heterogeneity, but they represent different experiments with independent bankrolls and must not be merged into the primary result. FS-010 automatic baseline should remain one coherent global experiment.

## 6. Longitudinal eligibility / missing-evidence semantics

### 6.1 Fixed provenance-safe epoch

The longitudinal stream requires an explicit start boundary:

```text
longitudinal_epoch_start
```

Preflight must identify the earliest prospective point where the chosen `DIXON_COLES + MODAL_ALL` stream can be reconstructed honestly under the current Decision/provenance contract.

The epoch is selected from **data availability/provenance**, never from observed P&L. All earlier Decisions are explicitly outside the FS-010 primary experiment rather than silently removed from an allegedly complete all-time stream.

### 6.2 Complete-evidence watermark

At each evaluation time, define:

```text
watermark
=
end of the maximum chronological batch prefix
for which every actionable Decision is economically evaluable
under canonical evidence rules
```

A batch is complete for Capital when every actionable Decision in that batch has valid selected price/provenance and canonical resolved outcome, or has been removed from the experimental basis through canonical cancellation hygiene.

`NO_BET` does not need to block the Capital path because it has zero exposure; it remains in audit/input.

### 6.3 Mandatory missing-evidence table

| Source Decision state | Include now? | Preserve in basis? | Blocks checkpoint/watermark? | Reason/status | Future reevaluation |
|---|---|---|---|---|---|
| `NO_BET` | Yes, zero exposure | Yes | No | Valid Decision action; Capital exposure = 0 | No Capital P&L dependency; later result may enrich other reporting |
| Actionable + valid temporal selected price + canonical resolved outcome | Yes | Yes | No | Fully evaluable Capital input | Already evaluable |
| Actionable + unresolved outcome | No beyond incomplete batch | Yes | **Yes** | `UNRESOLVED_OUTCOME` or current equivalent | Canonical settlement may advance watermark; full replay follows |
| Actionable + missing timestamp-valid selected price | No | Yes | **Yes** | `MISSING_TIMESTAMP_VALID_PRICE` or current equivalent | Only if legitimate provenance-preserving reconciliation proves a price valid at Decision time. A later current quote does not qualify |
| `CANC` fixture | No Capital derivative in canonical basis | Domain record stays; invalid experimental/economic derivatives are removed | No after hygiene completes; affected frozen Capital evidence is invalidated | Canonical cancellation lifecycle, not `NO_BET` | Recompute corrected basis |
| Corrected canonical outcome inside prefix | Yes with corrected canonical truth | Yes | Input identity/hash changes | Canonical correction | Full REPLAY from epoch |
| CapitalPolicy arm cannot evaluate common batch, e.g. concurrent recovery | Common source Decisions unchanged | Yes | Does not allow arm-specific sample reduction | `UNAVAILABLE_CONCURRENT_RECOVERY_STEP` | Arm remains explicit `UNAVAILABLE` for that snapshot/config unless methodology changes later |
| Unknown/ambiguous evidence affecting actionable input | No fabricated evaluation | Yes for audit | Yes | explicit unknown/unavailable | Reevaluate only after canonical clarification |

### 6.4 No silent skip rule

Forbidden:

```text
Decision missing price/outcome
→ remove it
→ continue with later resolved Decisions
```

because it conditions the evaluated history on which rows happened to be convenient.

The watermark preserves an honest contiguous causal history.

## 7. Recompute-vs-incremental-state recommendation

### 7.1 Required comparison

| Strategy | Reproducibility | Correction handling | Cancellation handling | Idempotence | Storage | Complexity | Recommendation |
|---|---|---|---|---|---|---|---|
| Full deterministic REPLAY from fixed epoch to current watermark | High | Natural: corrected canonical basis is replayed from origin | Natural: cancellation hygiene changes basis, then replay | High | Can persist derived snapshots/ledgers while source remains canonical Decisions | Moderate O(N) per changed checkpoint | **PRIMARY FS-010** |
| Mutable incremental bankroll as source of truth | Lower unless every mutation/reversal is perfectly versioned | Complex rollback or partial rebuild | Complex invalidation/rollback | More fragile | Less compute per update but requires durable mutable-state history | High | **REJECT as primary truth model** |

### 7.2 Recommendation

Use:

```text
canonical source basis
→ deterministic full replay
```

as the source of truth.

A persisted terminal bankroll/result may exist as a **derived snapshot/cache/audit artifact**, but must never become an irreversible financial state whose history cannot be reconstructed.

The exact model/table lifecycle is a **preflight/implementation choice**. Research does not mandate whether implementation creates a new CapitalExperiment per hash, introduces a small longitudinal snapshot identity, or uses another compatible persistence shape.

## 8. Checkpoint/cadence recommendation

### 8.1 Semantic trigger

The longitudinal result should be reconsidered when the **canonical input identity changes**, including:

- the complete-evidence watermark advances after settlement/reconciliation;
- a canonical correction changes an already included outcome;
- cancellation hygiene removes affected experimental/economic evidence;
- a legitimate provenance correction changes the eligible input basis.

Conceptually:

```text
build canonical longitudinal manifest
→ compare input identity/hash with last completed snapshot
→ unchanged = NO_WORK
→ changed = recompute full REPLAY from epoch
```

### 8.2 No calendar truth

Research does **not** require a daily/monthly reset or one new 100u bankroll per calendar interval.

Exact pipeline hook/Celery/service ownership belongs to preflight. The implementation should reuse the existing single scheduler/maintenance ownership rather than create a second independent capital scheduler, but the exact wiring is not frozen here.

### 8.3 Audit identity concept

A reproducible longitudinal snapshot should conceptually identify:

```text
evidence_class
longitudinal_epoch_start
source model code/version/variant
Decision policy code/version/variant
competition population
ordered Decision manifest / hash
evidence watermark
mode
initial bankroll normalization
CapitalPolicy code/version/config
engine version
```

For stochastic modes, when manually run, seed/path-count/stress config also belong to reproducibility identity.

## 9. Initial bankroll normalization

### 9.1 Recommendation

Use:

```text
initial_bankroll = 100u
```

for the FS-010 reference experiment.

Classification:

```text
RECOMMENDATION
+
inheritance from existing normalized Finsport baseline
```

not:

```text
empirically optimal bankroll
real bankroll
product bankroll
risk tolerance
```

### 9.2 Why 100u is acceptable

100u is a dimensionless, readable research scale already present in the Finsport normalized baseline and FS-004 comparison fixtures.

It gives every arm the same finite starting resource and allows capital constraints/overcommit/ruin behavior to be observed under one common normalization.

It is **not true** that changing 100u to 200u necessarily leaves every policy identical up to a trivial scale factor. Policy families mix absolute-unit stakes, fraction-of-bankroll stakes, target-profit amounts and absolute caps. Therefore 100u is part of the **comparison configuration**, and direct comparison requires the same initial bankroll.

## 10. Policy-by-policy normalized research configuration

### 10.1 Disposition

FS-004 research found no empirical basis to declare universal optimal values for fixed fraction, target profit, Kelly fraction, recovery alpha, caps or risk tolerance.

FS-010 should not optimize those values on the same growing evidence it is meant to evaluate.

However, the implemented FS-004 test/comparison contract already contains one coherent seven-policy configuration. Reusing it gives FS-010 a deterministic control without inventing new numbers.

Name this explicitly:

```text
FS-004 REFERENCE COMPARATOR CONFIG
```

### 10.2 Required policy normalization table

| CapitalPolicy | Parameters required by current policy | Proposed FS-010 research baseline | Optional sensitivity values | Normalization rationale | Confounding risk | May freeze for FS-010? |
|---|---|---|---|---|---|---|
| `FLAT_UNIT` | `unit` | `unit="1"` | None automatic | Existing normalized baseline; transparent absolute reference | Low, but absolute unit interacts with finite 100u bankroll | **Yes — research comparator only** |
| `FIXED_FRACTION_BANKROLL` | `fraction`, `0<f<1` | `fraction="0.05"` | None automatic | Inherited FS-004 comparator fixture, not empirical optimum | Medium/high: changes compounding and drawdown materially | **Yes — comparator identity only; not product default** |
| `FIXED_TARGET_PROFIT_NO_RECOVERY` | `target_profit` | `target_profit="1"` | None automatic | Normalizes target to one research unit in existing comparator | Medium/high: price directly changes required stake | **Yes — comparator identity only** |
| `LEGACY_RECOVERY` | `initial_stake`; target derived from first price; exact legacy ceiling semantics | `initial_stake="1"` | None | Preserves exact legacy comparator identity; no free recovery factor | High: tail exposure depends on losing sequence/price | **Yes — exact comparator only** |
| `LEGACY_CAPPED` | legacy initial state + explicit bounds | `initial_stake="1"`, `max_absolute_stake="5"` | None automatic | Reuses implemented bounded challenger fixture | High: cap choice strongly shapes shortfall/termination | **Yes — comparator identity only** |
| `LEGACY_PARTIAL` | `target_profit`, `alpha` | `target_profit="1"`, `alpha="0.5"` | None automatic | Reuses implemented partial-recovery challenger fixture | High: alpha controls recovery amplification | **Yes — comparator identity only** |
| `FRACTIONAL_KELLY` | `lambda`, model probability, valid price | `lambda="0.25"` | None automatic | Reuses implemented fractional-Kelly comparator; keeps full Kelly out of baseline | High if misread as optimal lambda; sensitive to probability error | **Yes — comparator identity only; not optimality claim** |

### 10.3 What “freeze” means here

It means FS-010 may use these exact values to identify one stable comparison experiment.

It does **not** mean best/safe/real-world/product configuration. Any sensitivity grid or parameter optimization creates additional experimental questions and belongs to later research/evaluator work unless separately approved.

## 11. Fractional Kelly treatment

Fractional Kelly retains current engine semantics:

```text
edge = p * o - 1

edge <= 0
→ 0 exposure
→ Decision unchanged

edge > 0
→ stake = lambda * full_kelly * bankroll
```

### Fairness rule

Do not prefilter the source stream to only positive-edge Decisions for Kelly.

All CapitalPolicies receive the same `DIXON_COLES + MODAL_ALL` source Decision basis. Therefore Flat/fraction/target/recovery families may request positive exposure on a Decision while Kelly legitimately requests zero. That difference is the CapitalPolicy behavior being compared.

The existing comparator uses `lambda=0.25`. Literature supports fractional Kelly as exposure reduction under parameter uncertainty, but no universal lambda. `0.25` is accepted only as the inherited FS-004 comparator value; FS-010 does not optimize it or claim it is better than another fraction.

## 12. REPLAY vs MONTE_CARLO vs STRESS disposition

### 12.1 Required mode/cadence table

| Mode | Evidence class | Automatic in FS-010 longitudinal path? | Trigger | Relative cost | Main question | Direct-comparison constraints |
|---|---|---:|---|---|---|---|
| `REPLAY` | Deterministic real-outcome evidence | **Yes** | Canonical longitudinal input identity/hash changes | O(N) full replay at current horizon | How did each CapitalPolicy behave on the real canonical comparator stream? | Same stream, epoch/horizon, mode, bankroll, engine, price provenance; policy/config identifies arm |
| `MONTE_CARLO` | Parametric stochastic evidence from Decision probability + price | **No — manual/on-demand existing capability** | Explicit research request | Multi-path | If these probability assumptions held, what capital-path distribution would policy induce? | Same input/config assumptions and seed/path protocol; never merged with real REPLAY evidence |
| `STRESS` | Explicit scenario evidence | **No — manual/on-demand existing capability** | Explicit configured scenario | Scenario-dependent | How does the policy behave under this declared adverse perturbation? | Same stress scenario/config across compared arms; scenario is not empirical truth |

### 12.2 No mode redesign

FS-010 must not redefine Monte Carlo as shuffling/omitting trades or IID bootstrap. Current Finsport Monte Carlo is parametric.

FS-010 also does not invent a monthly stochastic cadence, automatic 1000-path rule or new stress taxonomy. Those remain explicit config/on-demand questions.

## 13. Comparability-key contract

### 13.1 Must match for direct comparison

Two longitudinal CapitalPolicy results are directly comparable only if they share:

```text
evidence class = prospective/runtime
primary source model identity/version/variant
Decision policy identity/version/variant
longitudinal epoch
competition population
ordered Decision basis / input manifest
evidence watermark / horizon
timestamp-valid price provenance contract
evaluation mode
initial bankroll
engine version/runtime contract relevant to deterministic semantics
```

For stochastic comparisons, also match the relevant seed/path protocol, stress scenario and tail/reporting config.

### 13.2 What identifies the arm

The intended varying dimension is:

```text
CapitalPolicy code/version/config
```

The FS-010 reference experiment deliberately compares different policy families/configs on the same source basis.

### 13.3 `NO COMPARABLE`

Display/record `NO COMPARABLE` when a result differs materially in source Decision stream, evidence class, epoch/horizon, competition population, mode, initial bankroll, provenance basis or engine semantics/version.

Do not sort those results into one leader table.

## 14. Minimal longitudinal metrics

### 14.1 Primary deterministic REPLAY metrics

Use existing engine metrics.

**Evidence/sample**

```text
input_decisions
actionable_capital_decisions
capital_actions
```

**Return**

```text
total_pnl
roi
terminal_bankroll
```

with current engine definition:

```text
roi = total_pnl / total_staked
```

**Risk/path**

```text
maximum_drawdown
drawdown_duration
practical_ruin
```

**Exposure**

```text
total_staked
turnover
max_single_stake
max_stake_pre_bankroll_ratio
```

with:

```text
turnover = total_staked / initial_bankroll
```

**Policy behavior/detail**

```text
cap_hits
incomplete_terminated_recovery_sequences
longest_losing_streak
sequence_length_distribution
wins
losses
```

### 14.2 Secondary deterministic detail

May also show maximum_drawdown_amount, original Decision hit-rate context and exact engine `stake_concentration` when already produced. Reporting must not silently recalculate an alternate definition.

### 14.3 Stochastic-only metrics

Only when a real `MONTE_CARLO` or multi-path `STRESS` run exists:

```text
mean/median terminal bankroll
terminal-bankroll quantiles
Expected Shortfall
practical_ruin_probability
MDD distributions / threshold probabilities
max-stake distributions
termination distributions
```

For deterministic REPLAY:

```text
practical_ruin
→ boolean/state

practical_ruin_probability
→ unavailable / not applicable
```

### 14.4 No new composite metric

FS-010 adds no Sharpe requirement, VaR requirement, weighted score or “capital quality score”. Existing metrics are sufficient for the descriptive longitudinal objective.

## 15. Pareto/descriptive comparison boundary

FS-004 already has a transparent Pareto comparator and explicitly rejects a hidden single best-policy score.

FS-010 should **preserve existing Pareto behavior**, not design another Pareto engine.

Important current limitation:
- the implemented Pareto dimension set includes stochastic/tail dimensions such as Expected Shortfall;
- deterministic REPLAY may therefore legitimately produce an `UNAVAILABLE` Pareto summary when a required dimension is absent.

FS-010 must not fabricate deterministic Expected Shortfall merely to make Pareto work, silently remove dimensions, define a new weighted score or call a non-dominated arm the final winner.

Rule:

```text
existing Pareto output available
→ display/audit it as descriptive non-dominated/dominated evidence

existing Pareto output UNAVAILABLE
→ preserve reason honestly

final selection
→ FS-011
```

## 16. Minimal FS-009 frontend delta

FS-010 should make a bounded extension to the Capital section created by FS-009.

### 16.1 One row represents

```text
one longitudinal CapitalPolicyRun
under the same comparability group / evidence snapshot
```

### 16.2 Minimum visible fields

- policy name/version/config;
- status: `PRODUCED | UNAVAILABLE | FAILED`;
- source comparator label: `DIXON_COLES + MODAL_ALL`;
- evidence horizon/watermark;
- input/actionable sample;
- terminal simulated bankroll;
- simulated PnL;
- simulated ROI;
- maximum drawdown;
- drawdown duration;
- practical ruin / termination status;
- max stake / pre-bankroll ratio;
- comparability-group identity or concise context.

### 16.3 Optional trajectory

A bankroll trajectory is **optional**, not required for FS-010 Definition of Done.

If the existing FS-009 server-rendered UI can expose it cheaply from deterministic ledger data, it may be a small detail view. FS-010 must not introduce a charting SPA, new frontend service, API/export solely for charts or heavy JS dependency.

### 16.4 Leader language

FS-009 safe language remains:

```text
Mejor resultado observado en esta métrica
Líder observado
```

only within a valid comparison group and always with evidence/sample/horizon context. No final winner claim.

## 17. FS-011 boundary

FS-010 generates and exposes longitudinal Capital evidence.

FS-011 retains:
- universal/minimum sample-sufficiency rules;
- hypothesis tests / confidence intervals for winner claims;
- multiple-testing governance across techniques/configs;
- cross-period/cross-league stability criteria for promotion;
- final CapitalPolicy selection;
- PROMOTE / DROP;
- integrated Prediction + Decision + Capital evaluation;
- model complementarity/ensemble questions;
- parameter optimization;
- automatic CapitalPolicy selection;
- real bankroll/stake/risk limits;
- any transition toward real betting.

FS-010 must not infer:

```text
more terminal bankroll today
→ choose this CapitalPolicy
```

It reports evidence and leaves the scientific decision layer later.

## 18. Falsification results

The following table evaluates the **actual 20 falsification criteria from the FS-010 brief** against this final recommended methodology.

| # | Brief criterion | Result | Evidence/reason | Required correction |
|---:|---|---|---|---|
| 1 | Uses non-canonical outcomes for primary REPLAY | PASS | Primary REPLAY requires canonical resolved Match outcome | None |
| 2 | Substitutes current/latest odds for timestamp-valid Decision price | PASS | Watermark requires timestamp-valid selected-price provenance; later current quote cannot unlock history | None |
| 3 | Silently drops actionable Decisions | PASS | Maximum complete chronological batch prefix stops at first incomplete actionable gap | None |
| 4 | Gives different CapitalPolicies different source streams in direct comparison | PASS | All arms use fixed `DIXON_COLES + MODAL_ALL` manifest | None |
| 5 | Mutates source Predictions/Decisions to improve Capital result | PASS | Source basis is frozen/audited; recompute derives results without source mutation | None |
| 6 | Chains independent daily 100u experiments as one bankroll | PASS | One fixed epoch + full replay to watermark; no daily bankroll reset/chaining | None |
| 7 | Fits parameters by maximizing PnL on the same evaluation history | PASS | FS-010 inherits pre-existing FS-004 reference comparator config; no optimization sweep | None |
| 8 | Calls arbitrary research parameters product defaults | PASS | Config explicitly labelled research comparator only | None |
| 9 | Assumes full Kelly | PASS | Comparator uses Fractional Kelly `lambda=0.25`; no optimality claim | None |
| 10 | Conflates Decision with CapitalPolicy | PASS | Source Decision selector and downstream CapitalPolicy arm remain separate identities | None |
| 11 | Lets Monte Carlo replace real REPLAY | PASS | Automatic longitudinal mode is REPLAY only | None |
| 12 | Compares REPLAY/MC/STRESS as same evidence class | PASS | Modes remain separate comparability classes | None |
| 13 | Ignores batch/concurrent capital constraints | PASS | Existing same-time pre-batch semantics retained globally across leagues | None |
| 14 | Hides ruin/termination/cap/shortfall behavior | PASS | Existing run status, ledger states and deterministic risk metrics remain visible | None |
| 15 | Collapses risk/return into hidden single score | PASS | No new score; return/risk stay side by side; existing Pareto only when valid | None |
| 16 | Declares final CapitalPolicy winner | PASS | Final selection deferred to FS-011 | None |
| 17 | Defines integrated sample sufficiency/PROMOTE/DROP rules for FS-011 | PASS | Explicitly deferred | None |
| 18 | Introduces real betting/bookmaker auth/financial side effects | PASS | Research-only local simulation; no external writes | None |
| 19 | Requires provider calls | PASS | Longitudinal Capital reads canonical persisted DB evidence only | None |
| 20 | Freezes ORM/migration/Celery implementation before preflight | PASS | Research freezes semantics only; persistence/scheduler wiring remains preflight | None |

**Falsification disposition:** PASS. No criterion remains violated by the final methodology contract.

## 19. Unresolved questions / preflight inputs

### 19.1 CLOSED BY RESEARCH

```text
primary stream = prospective DIXON_COLES + MODAL_ALL
primary population = global multi-league
same-time batches share one bankroll
start from fixed provenance-safe epoch
input horizon = maximum complete chronological batch prefix
NO_BET = input/audit + zero exposure
CANC = cancellation hygiene, not synthetic NO_BET
state model = full recompute from epoch
automatic mode = REPLAY only
initial bankroll = 100u research normalization
policy configs = inherited FS-004 REFERENCE COMPARATOR CONFIG
no parameter optimization in FS-010
no final winner
small FS-009 Capital delta
```

### 19.2 PREFLIGHT INPUT

Preflight must determine from the post-FS-009 checkout/database:

1. Exact durable selector across multiple prospective PredictionExperiments that yields the longitudinal `DIXON_COLES + MODAL_ALL` stream without mixing backtest/reselection evidence.
2. Exact `longitudinal_epoch_start` supported by honest temporal-price/canonical-outcome provenance.
3. Exact current reason/status codes for unresolved outcome, missing valid selected price, recovery concurrency, cancellation invalidation and other arm-level unavailable states.
4. Whether current `CapitalExperiment.source_experiment` singular identity can represent the longitudinal stream directly or whether a minimal longitudinal identity/persistence shape is required.
5. Exact way to build the canonical multi-experiment input manifest/hash while preserving source provenance.
6. Current engine/version fields that should participate in snapshot identity.
7. Measured runtime cost of full replay at current DB scale and the point at which performance would require reconsideration.
8. Exact integration point with the existing single scheduler/maintenance owner.
9. Exact FS-009 template/service extension point after FS-009 is merged.

### 19.3 OPEN AS LATER SENSITIVITY

Not required to close FS-010:
- per-league independent-bankroll experiments;
- VALUE/SELECTIVE_CONFIDENCE source streams;
- alternate fixed-fraction/target/alpha/cap/Kelly configs;
- Monte Carlo cadence/path-count policy;
- automatic Stress cadence;
- block bootstrap.

### 19.4 FS-011

- statistical evidence sufficiency;
- stability thresholds;
- multiple testing;
- model/policy promotion/drop;
- final CapitalPolicy recommendation.

## 20. New Research Questions / New Work Discovered

### A. Historical market-evidence enrichment

FS-008 identified that historical results and historical timestamp-valid odds are separate evidence layers. A future source-research task may identify lawful historical prematch 1X2/MW3W data with real provenance.

This does **not** block the primary FS-010 design because FS-010 is based on growing prospective real evidence from its provenance-safe epoch.

### B. Per-league capital sensitivity

```text
global stream mixes competitions
→ a policy result may hide league heterogeneity
→ FS-011 may evaluate league-stratified robustness if sample supports it
```

### C. Alternate Decision-stream sensitivity

```text
capital cannot create edge
→ Capital result is conditional on source Decision process
→ FS-011 should treat source-stream robustness as part of integrated evaluation
```

### D. Stochastic robustness

FS-004 already supports Monte Carlo and Stress. FS-010 does not automate them.

```text
longitudinal real REPLAY grows
→ eventually enough evidence may justify richer robustness cadence
→ research only when there is a concrete evaluator question / sufficient evidence
```

No automatic priority is assigned here.

## 21. Durable project references

The following project artifacts are the authoritative/internal basis of this final research.

1. **`FS-010_capital_longitudinal_research_brief.md`** — 2026-09-01.
   Role: Q1–Q13, required tables, falsification criteria, final report contract.

2. **`F010_guia_investigacion_handoff_research_finsport_v1.1.md`** — ACTIVE.
   Role: research/evidence/handoff discipline; research != product decision != preflight != implementation.

3. **`F002_contexto_dominio_reglas_privacidad_seguridad_finsport_v1.3.md`** (or latest reconciled F002 carrying the same post-FS-004/FS-006 semantics).
   Relevant durable concepts: anti-leakage, Decision→Capital ordering, same-stream comparison, practical ruin, required-arm unavailable, real-financial-write prohibition, cancellation invalidation.

4. **`F003_contexto_tecnico_arquitectura_finsport_v1.4.md`**.
   Relevant concepts: Capital input contract, batch/concurrency, policy formulas, REPLAY/MC/STRESS semantics, persistence/audit identity, metrics/Pareto.

5. **`FS-004_capital_management_research.md`** — REFERENCE ONLY research underlying FS-004.
   Role: Kelly/fractional-Kelly theory, progression-system limitations, risk/drawdown/tail evidence, no universal policy-parameter freeze.

6. **`FS-004.md`** and final FS-004 implementation evidence.
   Role: implemented seven-policy/mode/metric contract and required-arm semantics.

7. **FS-004 test/diff evidence for the seven-policy comparator configuration.**
   Reference comparator: `100u`, Flat 1u, Fixed Fraction .05, Target 1u, Legacy initial 1u, Capped initial 1u + absolute cap 5u, Partial target 1u + alpha .5, Fractional Kelly lambda .25.

8. **`F006_roadmap_backlog_finsport_v1.3.md`**.
   Role: FS-004/FS-006 outcomes, normalized automatic baseline, parameter freeze still open, cancellation hygiene, no current best policy.

9. **`FS-008_handoff_final.md`**.
   Role: current capability/evidence-generation baseline and future historical-evidence gaps.

10. **`FS-009_reporting_ui_research.md`**.
    Role: current honest Capital reporting boundary and bounded post-FS-010 frontend delta.

11. **Deep Research correction artifacts for FS-010.**
    Role: exploratory analysis only. Where they contradicted F002/F003/FS-004, this final report explicitly reconciles them to the durable project contract.

## 22. Durable external bibliography

These references are inherited from the already-audited FS-004 research where they support the limited theoretical claims still relevant to FS-010. FS-010 does not use them to declare one Finsport-specific numeric policy parameter optimal.

### Kelly / parameter uncertainty

**Kelly, J. L., Jr. (1956).** “A New Interpretation of Information Rate.” *Bell System Technical Journal*, 35(4), 917–926.
DOI: https://doi.org/10.1002/j.1538-7305.1956.tb03809.x
Use: foundational log-growth criterion under known probabilities.

**Breiman, Leo (1961).** “Optimal Gambling Systems for Favorable Games.” In *Proceedings of the Fourth Berkeley Symposium on Mathematical Statistics and Probability*, Vol. 1, 65–78.
Stable URL: https://digicoll.lib.berkeley.edu/record/112884
Use: long-run properties of favorable-game gambling systems.

**MacLean, Leonard C.; Thorp, Edward O.; Ziemba, William T. (2010).** “Long-Term Capital Growth: The Good and Bad Properties of the Kelly and Fractional Kelly Capital Growth Criteria.” *Quantitative Finance*, 10(7), 681–687.
DOI: https://doi.org/10.1080/14697688.2010.506108
Use: growth/risk trade-off and rationale for fractional rather than unquestioned full Kelly.

**Baker, Rose D.; McHale, Ian G. (2013).** “Optimal Betting Under Parameter Uncertainty: Improving the Kelly Criterion.” *Decision Analysis*, 10(3), 189–199.
DOI: https://doi.org/10.1287/deca.2013.0271
Use: probability-estimation uncertainty can justify reduced Kelly exposure; no universal lambda follows.

**Metel, Michael R. (2018).** “Kelly Betting on Horse Races with Uncertainty in Probability Estimates.” *Decision Analysis*, 15(1), 47–52.
DOI: https://doi.org/10.1287/deca.2017.0359
Use: Kelly behavior under estimated probabilities in a betting context.

**Sun, Qingyun; Boyd, Stephen (2018).** “Distributional Robust Kelly Gambling: Optimal Strategy under Uncertainty in the Long-Run.” arXiv:1812.10371.
Stable URL/DOI: https://doi.org/10.48550/arXiv.1812.10371
Use: robust Kelly is a distinct future methodology; not required by FS-010 baseline.

**Busseti, Enzo; Ryu, Ernest K.; Boyd, Stephen (2016).** “Risk-Constrained Kelly Gambling.” *The Journal of Investing*, 25(3), 118–134.
DOI: https://doi.org/10.3905/joi.2016.25.3.118
Use: growth and drawdown/risk can be separate objectives/constraints; supports avoiding a simplistic single-return objective.

### Progression systems / no edge creation

**Liu, Wen (1999).** “A Theorem on Gambling Systems for Arbitrary Sequences of Random Variables.” *Bulletin of the London Mathematical Society*, 31(5), 607–615.
DOI: https://doi.org/10.1112/S0024609399005913
Use: progression systems transform capital paths but do not create favorable expectation by themselves.

**Dimitrov, Valentin; Shafer, Glenn (2025).** “The Martingale Index: A Measure of Self-Deception in Betting and Finance.” *Judgment and Decision Making*, 20, e26.
DOI: https://doi.org/10.1017/jdm.2025.12
Use: progression/martingale-style behavior should not be confused with creation of favorable expectation.

### Dependence / future robustness methods

**Politis, Dimitris N.; Romano, Joseph P. (1994).** “The Stationary Bootstrap.” *Journal of the American Statistical Association*, 89(428), 1303–1313.
DOI: https://doi.org/10.1080/01621459.1994.10476870
Use: if future evidence becomes sufficient for bootstrap robustness, dependence-preserving block methods are preferable to IID wager shuffling. Not part of FS-010 automatic mode.

## 23. RECOMMENDED FS-010 PRODUCT/METHODOLOGY CONTRACT

This section is the research recommendation that Main Chat may promote into an FS-010 ticket after F008 audit. It is not itself an implementation mandate.

### Primary evidence stream

```text
evidence class:
prospective/runtime

source model:
DIXON_COLES

Decision policy:
MODAL_ALL

population:
global multi-league

start:
fixed provenance-safe longitudinal epoch determined in preflight

ordering:
decision_time ASC

same decision_time:
one economic batch
```

### Secondary / sensitivity streams

```text
none in the automatic FS-010 longitudinal baseline
```

Per-league independent-bankroll views and alternate Decision streams are deferred sensitivity/evaluator work unless separately approved.

### Eligibility rule

```text
input =
maximum complete chronological batch prefix
from longitudinal epoch

NO_BET
→ preserved
→ zero Capital exposure

actionable Decision
→ enters only when canonical outcome + timestamp-valid selected price are valid
```

### Missing-evidence rule

```text
first incomplete actionable batch
→ fixes current watermark
→ later batches are not silently skipped

legitimate settlement/provenance correction
→ watermark may advance
→ recompute from epoch

later current quote
→ never backdated/substituted

CANC
→ cancellation hygiene removes invalid experimental/economic derivatives
→ affected frozen capital evidence invalidated
→ recompute corrected basis
```

### Ordering / batch rule

Preserve current FS-004 semantics:

```text
same Decision.decision_time
→ same pre-batch bankroll/state
→ no same-batch result leakage

joint requested exposure > bankroll
→ practical ruin / termination according to current engine

recovery policy + >1 actionable same batch
→ explicit UNAVAILABLE when no canonical independent sequence exists
```

### Initial bankroll normalization

```text
100u
```

Research-only common finite resource. Not real/product bankroll.

### Policy arms / configs

Use the inherited **FS-004 REFERENCE COMPARATOR CONFIG**:

```text
FLAT_UNIT
{"unit":"1"}

FIXED_FRACTION_BANKROLL
{"fraction":"0.05"}

FIXED_TARGET_PROFIT_NO_RECOVERY
{"target_profit":"1"}

LEGACY_RECOVERY
{"initial_stake":"1"}

LEGACY_CAPPED
{"initial_stake":"1","max_absolute_stake":"5"}

LEGACY_PARTIAL
{"target_profit":"1","alpha":"0.5"}

FRACTIONAL_KELLY
{"lambda":"0.25"}
```

Meaning:

```text
stable research control
!= empirical optimum
!= production default
!= real risk tolerance
```

No automatic parameter grid or optimization in FS-010.

### Modes

```text
REPLAY
→ automatic longitudinal evidence

MONTE_CARLO
→ existing manual/on-demand complementary stochastic evidence

STRESS
→ existing manual/on-demand scenario evidence
```

No new stochastic cadence required.

### Checkpoint trigger

Semantics:

```text
canonical longitudinal input manifest/hash changes
→ recompute complete REPLAY epoch→watermark

unchanged input
→ NO_WORK / no duplicate semantic result
```

Exact scheduler/service wiring belongs to preflight.

### Recompute / state model

```text
canonical Decision basis
→ source of truth

full deterministic replay
→ derived longitudinal snapshot

mutable terminal bankroll
→ never irreversible source of truth
```

### Comparability key

Direct policy comparison requires same:

```text
prospective evidence class
DIXON_COLES source identity/version
MODAL_ALL identity/version
competition population
longitudinal epoch
Decision manifest/input hash
watermark/horizon
timestamp-valid price provenance
mode
initial bankroll
engine version
```

Arm identity varies by:

```text
CapitalPolicy code/version/config
```

Any material mismatch:

```text
NO COMPARABLE
```

### Required metrics

Primary REPLAY:

```text
input_decisions
actionable_capital_decisions
capital_actions

total_staked
total_pnl
roi = total_pnl / total_staked
terminal_bankroll

maximum_drawdown
drawdown_duration
practical_ruin

turnover = total_staked / initial_bankroll
max_single_stake
max_stake_pre_bankroll_ratio

cap_hits
incomplete_terminated_recovery_sequences
longest_losing_streak
```

Show stochastic distributions/probabilities only for actual stochastic runs. No new composite score.

### Audit / reproducibility identity

Must be sufficient to reconstruct:

```text
epoch
watermark
source Decision selector
ordered Decision IDs/manifest/hash
canonical outcome snapshot identity
selected price/provenance
source model/Decision policy versions
CapitalPolicy version/config
mode
initial bankroll
engine version
```

plus seed/path/scenario config when stochastic.

### Frontend delta

Extend FS-009 Capital reporting with one longitudinal row per policy arm/config and:

```text
status/reason
source comparator
evidence horizon
sample
terminal bankroll
PnL
ROI
maximum drawdown
drawdown duration
practical ruin / termination
peak relative exposure
comparability context
```

Trajectory optional. No frontend redesign/API/SPA/chart dependency required.

### Explicitly deferred work

```text
parameter optimization
alternative policy-config grids
per-league independent bankroll evaluation
VALUE/SELECTIVE source-stream sensitivity
automatic MONTE_CARLO/STRESS cadence
block bootstrap
integrated sample sufficiency
statistical winner tests
PROMOTE/DROP
final CapitalPolicy selection
integrated Prediction + Decision + Capital evaluator
real bankroll/risk limits
bookmaker authentication
real betting
```

### Research close disposition

```text
FS-010 methodology research
→ COMPLETE / INTEGRITY-READY FOR MAIN-CHAT PROMOTION

remaining unknowns
→ implementation/preflight facts, not research blockers
```
