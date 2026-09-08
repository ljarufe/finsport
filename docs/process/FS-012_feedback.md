# FS-012 — Final reconciled feedback

**Ticket:** FS-012 — Automatic readiness calibration and lifecycle for Independent Poisson + Elo Multinomial Logit
**Final technical disposition:** PASS
**Acceptance:** 30 PASS · 0 PENDING · 0 BLOCKED
**Normal Codex passes used:** 3/4
**Pass 4:** not required

## 1. Outcome

FS-012 extends the readiness lifecycle so that Independent Poisson and Elo Multinomial Logit can participate automatically in the normal prospective Prediction lifecycle across the 10 current enabled competitions.

The final flow is:

canonical sporting history
→ model-specific readiness/configuration
→ automatically provisioned/current readiness profile
→ prospective Prediction
→ automatic `bet_eligible` assessment
→ normal Decision lifecycle
→ `/daily/` human-readable reporting

Prediction, Decision and Capital remain separate layers.

## 2. Phase A methodology and frozen result

Authoritative empirical strategy:

`fs012-phase-a-season-block-v2`

Final empirical result:

- 20/20 model×competition readiness profiles usable;
- 20 `NO_ADDITIONAL_STATISTICAL_GATE_JUSTIFIED`;
- 0 additional statistical gates;
- 0 evidence-insufficient final profiles;
- `requirements={}` for all 20 current Poisson/Elo profiles;
- no odds used for readiness calibration;
- no provider calls used for readiness calibration;
- no product DB writes during Phase A.

Frozen profile artifact SHA-256:

`c9add18eca6c18f038e4262fd3174ac8ebe84ae252fdaf27cc9463af1114adde`

### Independent Poisson frozen configs

- 1270 FR Ligue 1 → `xi=0.002`
- 1272 BR Serie A → `xi=0.002`
- 1273 EN Premier League → `xi=0.002`
- 1274 DE Bundesliga → `xi=0.001`
- 1275 IT Serie A → `xi=0.002`
- 1276 NL Eredivisie → `xi=0.001`
- 1277 PT Primeira Liga → `xi=0.001`
- 1278 ES La Liga → `xi=0.001`
- 1325 TR Süper Lig → `xi=0.002`
- 1459 AR Liga Profesional Argentina → `xi=0.0`

### Elo frozen configs

- 1270 FR Ligue 1 → `K=10`, `C=0.1`
- all other current competitions → `K=20`, `C=0.1`

## 3. Implemented capability

FS-012 adds or finalizes:

- shared/versioned readiness lifecycle for Poisson and Elo while preserving Dixon-Coles behavior;
- automatic provisioning of the 20 current Poisson/Elo readiness profiles;
- idempotent `NO_WORK` behavior when the sporting/model/profile basis is unchanged;
- automatic revalidation on material sporting/model/profile-basis change;
- currentness independent of odds-only changes for Poisson/Elo;
- Independent Poisson hyperparameter selection independent of Dixon-Coles;
- Elo finite-only hyperparameter selection;
- explicit Elo all-nonfinite outcome:
  `UNAVAILABLE:NO_FINITE_ELO_HYPERPARAMETER_CANDIDATE`;
- structural model guards remain authoritative even though no additional empirical N gate was justified;
- low-evidence mechanically producible Prediction can persist while remaining `bet_eligible=false`;
- normal Decision lifecycle remains downstream from Prediction;
- human-readable `/daily/` readiness rendering;
- migration `football.0011_shared_model_readiness`.

## 4. Pass 2 — performance finding resolved

A material performance finding was found during execution-chat diff review:

readiness/currentness could rebuild/hash canonical sporting history repeatedly for multiple Predictions in the same operation.

The correction introduced an ephemeral competition/operation-scoped `SportingBasis` and model-specific `ReadinessCurrentness`.

Measured behavior changed from:

- prospective 2 targets × 2 readiness models: 4 sporting-basis builds → 1;
- readiness maintenance Poisson + Elo: 2 sporting-basis builds → 1.

No global cache, Redis cache or persistent stale cache was introduced.

## 5. Pass 3 — PR review corrections

The first Codex PR review produced two material findings. Both were reproduced conceptually, fixed and regression-tested.

### P2 — Poisson/Elo disappearing when HistoricalCoverage is not current

**Problem**

`_sporting_candidates()` applied the Dixon-Coles `HistoricalCoverage COMPLETE/current` gate to all sporting models.

That could silently remove Independent Poisson and Elo from a normal pipeline run even when sufficient locally stored sporting history existed to mechanically produce probabilities.

**Final behavior**

- Dixon-Coles keeps its FS-011 `HistoricalCoverage COMPLETE/current` gate.
- Independent Poisson and Elo remain eligible sporting candidates from locally stored sporting history.
- Missing/stale/incomplete HistoricalCoverage does not silently remove those experimental arms.
- readiness/currentness determines later whether the resulting Prediction is `bet_eligible`.
- a stale readiness profile therefore remains auditable as a persisted Prediction with an explicit readiness reason rather than disappearing.

Regression:

`test_poisson_and_elo_candidates_survive_stale_coverage_but_dc_does_not`

**Disposition:** RESOLVED.

### P1 — unattempted models incorrectly consuming calibration budget

**Problem**

An exception outside the inner calibration catcher could fabricate two `calibrated=True` FAILED results, including for a model never attempted.

With the normal budget of two full calibrations per wake, a persistent failure in an early competition could starve later due competitions.

**Final behavior**

`CalibrationBudget` records `(competition_id, model)` immediately before each real full-calibration invocation.

Accounting semantics:

- failure before any model calibration → consumes 0;
- one calibration actually started → consumes exactly 1;
- failure during or after that attempted calibration preserves that one consumed unit;
- an unattempted sibling model consumes 0;
- two actual calibration attempts consume 2;
- frozen Phase-A provisioning consumes 0.

Regressions:

- `test_precalibration_competition_failure_does_not_consume_budget`
- `test_actual_failed_calibration_consumes_only_its_budget_unit`
- `test_postcalibration_persistence_failure_preserves_exact_attempt_count`

**Disposition:** RESOLVED.

## 6. Final automated evidence

Pass 3 final local evidence:

- focused FS-012 regressions: **83 passed in 15.59s**;
- `make check`: **430 passed in 37.58s**;
- coverage: **87.17%**;
- formatter/lint/Django/migration/dependency/security gates: PASS;
- `git diff --check`: PASS;
- frozen 20-profile config SHA unchanged;
- material findings remaining: none.

Acceptance ledger final state:

- PASS: 30
- PENDING: 0
- BLOCKED: 0

## 7. Persistent migration and UAT

Before persistent migration:

`tmp/FS-012_pre_uat.dump`

Migration:

`football.0011_shared_model_readiness` → PASS

Persistent DB/UAT evidence:

- 20/20 Poisson/Elo profiles active/current;
- exact frozen configurations verified;
- initial full calibrations = 0;
- unchanged maintenance = 20 `NO_WORK`;
- unchanged full calibrations = 0;
- controlled Elo all-inf → correct UNAVAILABLE;
- controlled low-evidence → producible but not bet-eligible;
- 10 approved Dixon-Coles profiles remain active.

### Real prospective UAT target

Stored target:

- match 53550
- NL Eredivisie
- Twente vs Telstar
- 2026-09-09

Provider-free readiness UAT result:

- Independent Poisson: `PRODUCED`, passing readiness;
- Elo Multinomial Logit: `PRODUCED`, passing readiness;
- Dixon-Coles regression: PASS;
- `provider_calls=0`;
- `manual_profile_activation=none`.

The fixtures/odds used to make a real future stored target available were obtained separately through an explicitly authorized normal capture operation. That capture is not part of readiness calibration/revalidation.

### Browser UAT

`/daily/` visually confirmed for Twente–Telstar:

- Dixon-Coles rendered normally;
- Elo Multinomial Logit rendered normally;
- Independent Poisson rendered normally;
- `bet_eligible=true` where expected;
- technical reason:
  `APPROVED_READINESS_PROFILE_PASSED`;
- human reason:
  `Perfil de preparación aprobado y satisfecho`;
- no unknown-reason fallback;
- normal downstream Decision lifecycle still visible.

Browser UAT: PASS.

## 8. Observability / audit impact

Readiness lifecycle terminal states remain auditable through readiness events and persisted profile provenance.

Relevant terminal outcomes include:

- CREATED;
- UPDATED;
- NO_WORK;
- UNAVAILABLE;
- FAILED;
- DEFERRED.

The final calibration-budget correction improves audit semantics because reported full-calibration consumption now corresponds to actual calibration attempts.

The stale/incomplete coverage correction improves auditability because Poisson/Elo Predictions are no longer silently absent solely due to the Dixon-Coles coverage gate; when mechanically producible, they can persist and carry explicit readiness eligibility state.

Unexpected runtime failures retain traceback/error observability; expected unavailable/readiness states remain classified rather than converted into exceptions.

## 9. Safety / exclusions

FS-012 does not add:

- real wager placement;
- bookmaker authentication/write;
- a second scheduler;
- readiness provider calls;
- odds as Poisson/Elo readiness evidence;
- mixing of Prediction and Decision semantics;
- mixing of Decision and Capital semantics.

## 10. New work discovered — future only

### Historical BACKTEST display in `/daily/` for Predictions only

During testing we verified that chronological BACKTEST Predictions are persisted and can be used to inspect historical model behavior.

A future reporting enhancement may expose those historical Predictions in `/daily/`, clearly separated from PROSPECTIVE evidence.

Allowed future scope:

- model / variant;
- home/draw/away probabilities;
- predicted outcome;
- actual outcome;
- explicit BACKTEST/replay label.

Explicitly out of scope for that enhancement:

- Decisions;
- betting policies;
- selected odds;
- VALUE;
- ROI;
- P&L;
- Capital.

The purpose is historical Prediction inspection/testing only. It must not be presented as prospective evidence and must not be mixed with economic decisions.

This future work is **not part of FS-012 acceptance**.

## 11. Final disposition

FS-012 technical acceptance is complete.

- implementation: PASS;
- Phase A empirical calibration: PASS;
- migration: PASS;
- automated gates: PASS;
- persistent UAT: PASS;
- browser UAT: PASS;
- PR review findings P1/P2: corrected and regression-tested;
- acceptance ledger: 30/30;
- remaining material product findings: none;
- Codex Pass 4: not justified.

This document is the **FINAL RECONCILED FEEDBACK** for FS-012.
