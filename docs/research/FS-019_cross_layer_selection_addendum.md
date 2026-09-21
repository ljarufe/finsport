# FS-019 Addendum — Cumulative Cross-Layer Selection

## Status

This addendum supplements the original FS-019 Decision-layer election without invalidating its local authorities.

The following remain valid and frozen as layer-local results:

```text
GLOBAL_PREDICTION_V1
= MARKET_CONSENSUS / fs013-market-consensus-v2

GLOBAL_DECISION_V1
= MODAL_ALL / fs003-modal-all-v1
```

They answer the original sequential questions:

```text
best Prediction under the Prediction contract
+
best/fallback Decision conditional on that frozen Prediction
```

The addendum introduces a second, cumulative experimental question:

```text
among all eligible alternatives from every layer opened so far,
which integrated combination performs best?
```

## Durable program rule

From this ticket onward, every experimental phase produces two complementary outputs.

### 1. Layer-local / sequential result

The newly opened layer is evaluated conditional on the previously frozen sequential baseline.

This preserves attribution and allows Finsport to determine whether weakness originates in Prediction, Decision, Capital, or a later layer.

### 2. Cumulative cross-layer result

All eligible alternatives from every layer opened so far are evaluated jointly.

```text
Prediction phase
→ Prediction

Decision phase
→ Prediction × Decision

Capital phase
→ Prediction × Decision × Capital

future phase N
→ eligible Layer1 × Layer2 × ... × LayerN combinations
```

The cumulative tournament prevents Finsport from assuming:

```text
best component in isolation
=
component contained in the best integrated strategy
```

Layer-local authorities are never silently rewritten by a cumulative result.

## FS-019 cross-layer candidate matrix

Frozen confirmatory matrix:

```text
Prediction:
- DIXON_COLES / fs011-dixon-coles-v2
- INDEPENDENT_POISSON / fs003-independent-poisson-v1
- ELO_MULTINOMIAL_LOGIT / fs003-elo-multinomial-logit-v1
- MARKET_CONSENSUS / fs013-market-consensus-v2

Universal Decision:
- MODAL_ALL
- SELECTIVE_CONFIDENCE 0.40
- SELECTIVE_CONFIDENCE 0.45
- SELECTIVE_CONFIDENCE 0.50
- SELECTIVE_CONFIDENCE 0.55
- SELECTIVE_CONFIDENCE 0.60

Additional VALUE Decision:
- VALUE 0.00
- VALUE 0.02
- VALUE 0.05

VALUE is eligible only with:
- DIXON_COLES
- INDEPENDENT_POISSON
- ELO_MULTINOMIAL_LOGIT

MARKET_CONSENSUS × CURRENT VALUE
→ INELIGIBLE under the current circularity contract

Total:
33 Prediction × Decision candidates
```

No additional candidate or threshold may be introduced into this confirmatory result after observing its outcome.

## Primary common cohort

Primary confirmatory comparison:

```text
price evidence:
ODDSPAPI_RECONSTRUCTED_T30_V1

paired/common Matches:
1,877

competitions:
10

Competition × Lima ISO-week blocks:
229

bootstrap:
5,000 replicates
seed 18092026
paired block bootstrap
simultaneous max-centered adverse top-vs-all guard
```

## Observed cross-layer point leader

Observed highest GLOBAL_PPO:

```text
DIXON_COLES
+
VALUE 0.05
```

Results:

```text
GLOBAL_PPO
= +0.009653719670368769

BET
= 1,518

NO_BET
= 359

pooled fixed-unit P&L
= +38.584u

yield per BET
= +2.5417654808959158%

hit rate
= 30.10540184453228%
```

This was the only candidate in the exploratory 33-combination screen with positive equal-league GLOBAL_PPO.

It must not be described as proven superior.

## Confirmatory inference

Observed runner-up:

```text
ELO_MULTINOMIAL_LOGIT
+
SELECTIVE_CONFIDENCE 0.55

GLOBAL_PPO
= -0.0017117403132467686
```

Simultaneous inference:

```text
q95
= 0.0884080380133749

minimum simultaneous lower bound
= -0.07704257802975936

lower bound vs current integrated control
= -0.04927320613106208
```

Stability contained negative deltas:

```text
-0.006755455985283151
-0.002434358883453188
```

Therefore:

```text
cross-layer scientific disposition
= UNSTABLE

survivors
= 33 / 33
```

No candidate demonstrated simultaneous stable superiority.

## Integrated conservative baseline

The pre-addendum sequential integrated control was:

```text
MARKET_CONSENSUS
+
MODAL_ALL
```

Because it remained in the survivor set, the deterministic conservative fallback retains:

```text
GLOBAL integrated control
= MARKET_CONSENSUS + MODAL_ALL

selection basis
= CONSERVATIVE_FALLBACK

cross-layer disposition
= UNSTABLE
```

This does not erase the observed cross-layer point leader.

The following must be handed independently to Capital:

```text
SEQUENTIAL / INTEGRATED CONTROL
MARKET_CONSENSUS + MODAL_ALL

CROSS_LAYER_POINT_LEADER_V1
DIXON_COLES + VALUE 0.05
status = OBSERVED_TOP / UNSTABLE / NOT PROVEN SUPERIOR

FROZEN CROSS-LAYER MATRIX
33 eligible Prediction × Decision candidates
```

## Larger-universe robustness

A secondary diagnostic used persisted Football-Data `HistoricalMarketEvidence`.

Observed:

```text
historical evidence rows
= 2,422

selected groups:
BET365_CLOSING = 2,306
PINNACLE_CLOSING = 116

time semantics:
ASSUMED_T30M = 2,422
```

This is a separate historical/research price profile.

It must never be represented as prospectively observed or reconstructed OddsPapi T-30 evidence.

The larger-universe diagnostic does not replace the 1,877 paired primary election.

Its role is robustness/sensitivity only.

## Phase-3 contract

Capital must perform two related studies.

### Capital-local study

Hold the sequential Prediction × Decision control fixed:

```text
MARKET_CONSENSUS
+
MODAL_ALL
```

and compare eligible Capital policies/configurations.

This produces the layer-local Capital result.

### Cumulative integrated study

Evaluate the frozen eligible Prediction × Decision matrix against the eligible Capital matrix.

Conceptually:

```text
Prediction
×
Decision
×
Capital
```

The purpose is to identify the strongest integrated system rather than assume that the concatenation of isolated layer winners is globally optimal.

The current seven Capital configurations remain the initial Capital candidate set unless Capital research freezes a different eligibility matrix.

## Required Phase-3 outputs

Phase 3 must preserve both:

```text
GLOBAL_CAPITAL_V1
→ best/fallback Capital result conditional on the sequential control

GLOBAL_STRATEGY_V1
→ best/fallback integrated Prediction × Decision × Capital combination
```

and retain enough per-layer diagnostics to attribute failures or improvements to the correct layer.

## Cohort rule

Primary direct candidate elections use paired/common evidence.

Natural/model-specific larger universes remain robustness diagnostics unless a future methodology explicitly freezes a different election contract.

## Multiplicity rule

As cumulative candidate count grows, candidate matrices must be frozen before confirmatory inference.

Search and confirmation must remain distinct enough to prevent post-hoc candidate expansion from being treated as proof.

Multiplicity-aware simultaneous inference and stability testing remain mandatory for cumulative promotion.

## Retention consequence

The previous FS-018 private-evidence deletion condition is superseded by this addendum.

Because Phase 3 must evaluate Prediction alternatives that are not represented by the single promoted `GLOBAL_PREDICTION_V1` stream, the retained FS-018 multi-model evidence remains an active downstream dependency.

Therefore:

```text
FS-018 private multi-model evidence
→ PRESERVE_ACTIVE through cumulative Capital evaluation
```

It becomes deletion-eligible only after Phase 3 has durably absorbed/published everything required to reproduce the cumulative Prediction × Decision × Capital comparison without reopening that private evidence.

The selected FS-019 Decision stream remains the durable sequential handoff, but it is not a replacement for the alternative Prediction evidence required by the cumulative tournament.

## Cross-ticket artifact packaging rule

Cumulative tournaments may generate substantially larger intermediate evidence as the cross-layer candidate matrix grows.

Use the following boundary:

- Small / compact / downstream-authoritative artifacts:
  - tracked in the repository.

- Large replay rows / candidate matrices / raw experimental bundles:
  - stored under `/home/ljarufe/Documents/finsport/research-evidence/<producer-ticket>/`;
  - identified by SHA-256;
  - registered in `RETENTION_INDEX.tsv`;
  - restored into the consuming ticket's `tmp/` workspace when required.

Tracked artifacts should include only what a downstream consumer needs directly, such as:

- promotion authority;
- compact experiment result;
- candidate matrix/spec identity;
- selected stream when reasonably small;
- report / handoff;
- hashes and pointers to retained large evidence.

Large private evidence must not become an operational runtime dependency.

A consuming ticket must follow:

`resolve retained artifact -> verify SHA-256 -> restore/copy into tmp/ -> bind restored artifact identity into its experiment -> absorb/publish the durable evidence it needs`

Only after the downstream ticket no longer needs direct access may the upstream private bundle become deletion-eligible.

For the current FS-019 -> Capital handoff:

- compact cross-layer confirmation -> tracked;
- selected sequential Decision stream -> tracked;
- FS-018 multi-model raw/private evidence -> external `PRESERVE_ACTIVE`;
- future large Prediction x Decision x Capital replay evidence -> external retention when repository packaging limits or usefulness justify it.
