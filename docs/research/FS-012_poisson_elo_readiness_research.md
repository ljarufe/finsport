# Finsport — Independent Poisson + Elo Multinomial Logit readiness research

**Status:** REFERENCE ONLY
**Research completion:** COMPLETE FOR FS-012 DEFINITION
**Empirical calibration:** REQUIRED IN FS-012 BEFORE PRODUCT IMPLEMENTATION
**Project:** Finsport
**Date:** 2026-09-07
**Product mode:** local-only / demo-only / research-oriented
**Real betting:** FORBIDDEN
**Research process authority:** F010
**Planning authority:** F008

> This artifact consolidates the corrected final result of the pre-FS-012 research.
> It supersedes the intermediate Deep Research drafts for ticket-definition purposes.
>
> It deliberately does **not** fabricate local empirical results that were never run.
> On 2026-09-07 the maintainer closed the sequencing decision:
>
> ```text
> no dormant implementation
> → empirical readiness calibration is REQUIRED inside FS-012
> → product implementation may start only after that calibration closes
> → the ticket is DONE only when both arms are automatically usable
> ```
>
> Therefore the research is complete for Definition of Ready: the empirical method,
> admissible evidence, failure semantics and decision rules are closed. The numerical
> model×competition profiles are execution evidence that FS-012 must produce before
> product code is implemented.

---

## 1. Executive summary

FS-011 changed the readiness problem materially. Finsport now has a canonical historical
pool covering ten enabled first-division competitions and a demonstrated Dixon-Coles
readiness/profile lifecycle. Independent Poisson and Elo Multinomial Logit already consume
the same sporting history and can produce prospective probabilities, but neither arm has
a completed model-specific readiness calibration/lifecycle.

The research closes the following:

```text
INDEPENDENT_POISSON
→ pure Poisson baseline stays pure
→ no odds dependency
→ global connectivity is diagnostic, not a hard gate
→ mechanical fit with tiny N does not imply maturity
→ Poisson must select its own temporal-decay xi
→ current XI_GRID stays {0.0, 0.001, 0.002}
→ no universal readiness N is supported externally

ELO_MULTINOMIAL_LOGIT
→ dynamic Elo + multinomial LogisticRegression stays the arm
→ initial_rating=1500 and HFA=100 remain unchanged
→ K grid stays {10,20,40}
→ C grid stays {0.1,1.0,10.0}
→ fewer than 3 observed outcome classes in a training slice is mechanical UNAVAILABLE
→ prior-only/new-team Prediction may be valid but is not automatically mature
→ all non-finite K/C validation losses means no legitimate winner
→ Finsport semantic result = UNAVAILABLE

SHARED
→ chronological expanding validation
→ outer = last completed season per competition
→ development = all earlier completed seasons
→ inner chronological validation owns hyperparameter selection
→ multiclass log-loss is the primary hyperparameter-selection metric
→ Brier + calibration are primary evaluation evidence
→ RPS and accuracy are complementary
→ evidence bands are derived only from development data
→ no arbitrary threshold is allowed
→ NO_GLOBAL_THRESHOLD_JUSTIFIED remains a valid scientific result
```

A product constraint added by the maintainer changes the disposition of that last point:

```text
NO_GLOBAL_THRESHOLD_JUSTIFIED
!= leave arm dormant

NO_GLOBAL_THRESHOLD_JUSTIFIED
→ derive the simplest defensible competition-specific profile
  or demonstrate that no additional statistical gate beyond structural applicability
  is justified for that competition

if a current model×competition profile still cannot be justified
→ FS-012 is BLOCKED
→ obtain the missing evidence/source/research
→ do not merge a dormant arm
```

The current target is therefore:

```text
10 competitions
×
2 model arms
=
20 automatically provisioned/current readiness profiles
```

with no Admin approval, ad-hoc management command, or manual activation required after
deployment.

The reporting finding observed in the real FS-011 smoke is also coherent with this ticket:

```text
APPROVED_READINESS_PROFILE_PASSED
→ current /daily/
→ "Motivo no clasificado"
```

The semantic reason is valid evidence; the human mapping is incomplete. FS-012 should
make the current readiness reason vocabulary human-readable without redesigning reporting.

---

## 2. Scope and non-goals

### In research scope

- Independent Poisson structural applicability vs statistical maturity.
- Independent Poisson temporal-decay selection.
- Elo Multinomial Logit mechanical applicability.
- Elo prior/new-team maturity.
- Elo K/C all-invalid selection semantics.
- chronological empirical design;
- probabilistic metrics and calibration;
- readiness/profile lifecycle implications;
- bounded reporting-reason semantics;
- coherence of one combined FS-012 ticket.

### Explicit non-goals

- new historical provider discovery unless empirical acceptance exposes a concrete gap;
- routine historical polling;
- Dixon-Coles model redesign;
- bivariate/correlated/hierarchical Poisson;
- xG/player/coach/lineup features;
- Elo native-probability replacement;
- Elo season regression;
- special promoted-team prior;
- special K for new teams;
- HFA tuning;
- MARKET_CONSENSUS audit;
- MODERNIZED_R45 audit;
- Decision-policy redesign;
- Capital changes;
- integrated evaluator;
- general `/daily/` redesign;
- Grafana/runtime error remediation;
- orphan `PipelineRun` / `safe-down` remediation;
- real betting.

---

## 3. Post-FS-011 baseline

FS-011 closed the shared data/readiness foundation.

### Enabled pool

| ID | Competition | Historical status | Effective completed history / rows |
|---:|---|---|---|
| 1270 | France — Ligue 1 | COMPLETE/current | 5,757 rows |
| 1272 | Brazil — Serie A | COMPLETE/current | 2012–2025 effective window / 5,307 rows |
| 1273 | England — Premier League | COMPLETE/current | 6,080 rows |
| 1274 | Germany — Bundesliga | COMPLETE/current | 4,896 rows |
| 1275 | Italy — Serie A | COMPLETE/current | 6,080 rows |
| 1276 | Netherlands — Eredivisie | COMPLETE/current | 4,822 rows |
| 1277 | Portugal — Primeira Liga | COMPLETE/current | 4,632 rows |
| 1278 | Spain — La Liga | COMPLETE/current | 6,080 rows |
| 1325 | Türkiye — Süper Lig | COMPLETE/current | 4,924 rows |
| 1459 | Argentina — Liga Profesional Argentina | COMPLETE/current | 2015–2025 / 4,359 rows |

The exact HOME/DRAW/AWAY class counts and per-team maturity distributions are execution
facts for the empirical calibration and must be measured from the current DB; they are not
invented here.

Shared FS-011 behavior that FS-012 must reuse:

- canonical/provenanced stored historical results;
- no daily completed-season historical polling;
- model evidence separated from odds where the arm does not consume odds;
- `PRODUCED / UNAVAILABLE / FAILED` semantics;
- valid Prediction separated from betting eligibility;
- versioned Prediction evidence;
- readiness/profile concept demonstrated for Dixon-Coles;
- current 10-league historical foundation;
- scheduled/pipeline ownership rather than a second scheduler.

The final prospective FS-011 smoke demonstrated a real future Brazil Serie A fixture where
Dixon-Coles was `PRODUCED`, `bet_eligible=true`,
`APPROVED_READINESS_PROFILE_PASSED`, Decisions were persisted, and `/daily/` rendered the
evidence. The same page also exposed current Independent Poisson and Elo Multinomial Logit
prospective outputs.

---

## 4. Prior handoff decisions preserved

### 4.1 Independent Poisson

The applicability audit established:

- current arm uses `penaltyblog.models.PoissonGoalsModel`;
- inputs are sporting history only;
- odds are not an input;
- the same canonical historical pool as Dixon-Coles is sufficient;
- N=0 is structurally unavailable;
- controlled probes produced valid vectors with N=1 and disconnected training components;
- therefore mechanical fit with N=1 is not a maturity threshold;
- global connectivity must not be promoted to a hard gate by default;
- unseen target teams cannot honestly be inferred by the current pure goal-model arm;
- Poisson currently inherited/copied the Dixon-Coles `xi` winner in the audited baseline;
- this coupling is methodologically wrong even though the tested samples happened to select
  the same `xi`;
- `XI_GRID` expansion had no supporting evidence;
- the arm must remain pure Independent Poisson.

### 4.2 Elo Multinomial Logit

The applicability audit established:

- the arm is dynamic Elo + multinomial logistic regression, not direct Elo probabilities;
- no odds dependency;
- `initial_rating=1500`;
- `home_field_advantage=100`;
- current grids: `K=(10,20,40)`, `C=(0.1,1.0,10.0)`;
- same-day features are frozen before results are revealed/ratings updated;
- unseen teams receive the neutral prior and can receive a valid exploratory Prediction;
- prior-only does not imply maturity;
- fewer than three observed HOME/DRAW/AWAY classes is the mechanical classifier-fit gate;
- N=3 with one observation per class is not a readiness threshold;
- K/C selection is model-specific;
- an all-non-finite K/C validation case can appear to select a tuple unless guarded;
- HFA tuning, season regression and promoted-team transfer priors are not justified now.

---

## 5. Research questions R1–R9

| Question | Definition result | Execution input still required |
|---|---|---|
| R1 Poisson fit/readiness boundary | Structural fit and statistical maturity are distinct; no universal N; known-team/history guards remain; connectivity diagnostic | DB calibration determines whether an additional competition-specific statistical gate is justified |
| R2 Poisson bet eligibility | Must be empirically calibrated per competition; no arbitrary global threshold | Phase A calibration |
| R3 Poisson `xi` | ANSWERED: own chronological validation; current grid only; expansion DEFER | Phase A selects each competition's current value |
| R4 Elo mechanical applicability | ANSWERED: `<3` classes in each chronological training slice → UNAVAILABLE | implementation/preflight confirms exact current helper path |
| R5 Elo prior/readiness progression | Prior 1500 can produce; maturity depends on accumulated target-team evidence; no universal N | Phase A calibration |
| R6 Elo all-inf K/C | ANSWERED: no legitimate winner; Finsport result UNAVAILABLE | implementation guard/test |
| R7 empirical design | ANSWERED for execution | Phase A runs it |
| R8 reporting reason | Valid current readiness code renders through fallback; bounded mapping audit/fix required | preflight finds exact mapper/current vocabulary |
| R9 ticket coherence | COMBINED_TICKET_RECOMMENDED | none |

---

## 6. External / methodological evidence

### 6.1 No universal maturity threshold

Classical and later football-score modelling literature supports Poisson-family models as
useful predictive baselines but does not provide a universal number of prior matches that
turns a mechanically estimable football model into a statistically mature one.

The correct inference is:

```text
small-sample uncertainty exists
!=
a universal hard minimum exists
```

Therefore Finsport must derive any additional readiness condition from its own chronological
evidence, by competition, and remain willing to conclude that no extra threshold is
justified.

The same principle applies to Elo. The neutral rating prior is a modelling convention; its
influence declines as observed results update the rating, but the literature does not
provide a universal football-specific match count at which a target becomes mature.

### 6.2 Proper probabilistic scoring

For three-way probability forecasts, log-loss and Brier-style probability scores provide
principled evidence. RPS is useful because HOME/DRAW/AWAY is ordered, but it should not
dominate the decision by itself. Accuracy/top-pick hit rate is secondary because it throws
away probability quality.

Research disposition:

```text
hyperparameter selection
→ multiclass log-loss

readiness quality
→ log-loss
→ multiclass Brier
→ calibration/reliability
→ coverage/stability

complementary
→ RPS
→ accuracy
```

ROI, profit, Capital and post-selection economic outcomes are excluded from predictive
readiness.

### 6.3 Chronological evaluation

Random cross-validation is inappropriate for this evidence because it can leak future
football information into past predictions.

The closed design is:

```text
per competition:

outer
= last completed season

development
= all earlier completed seasons

inside development
= chronological expanding validation

hyperparameter selection
= inner chronological validation only

outer
= evaluation only
```

No outer target may choose:

- `xi`;
- K/C;
- quantile boundaries;
- readiness cut;
- calibration rule.

### 6.4 Independent Poisson temporal decay

Within Finsport, `xi` refers to the exponential temporal-decay weighting used by the current
goal-model adapter. It is not the Dixon-Coles low-score correlation parameter.

Closed disposition:

```text
current Finsport XI_GRID
= {0.0, 0.001, 0.002}

external evidence does not justify expansion now
→ XI_GRID expansion = DEFER

Independent Poisson
→ chooses its own xi
→ using its own chronological validation loss
```

### 6.5 Elo prior and K/C

No football-specific evidence justifies a special K for new teams. Preserve the current
arm:

```text
initial_rating = 1500
HFA = 100
K ∈ {10,20,40}
C ∈ {0.1,1.0,10.0}
```

Maturity must be represented through evidence/readiness progression, not by changing K for
novices.

### 6.6 All-invalid hyperparameter candidates

If every candidate validation loss is non-finite, there is no statistically legitimate
winner.

External methodology supports:

```text
no valid winner
```

The domain decision is Finsport-specific:

```text
no valid winner
→ UNAVAILABLE
→ stable machine-readable reason
```

not `FAILED`, unless an unexpected runtime defect occurred.

---

## 7. Exact local empirical design promoted into FS-012 Phase A

This is REQUIRED execution evidence, not an optional future evaluator.

### 7.1 Dataset

Use only canonical stored sporting history already available in the post-FS-011 DB.

No:

- HTTP;
- API-Football;
- Inkabet;
- historical download;
- bookmaker evidence;
- ROI/Capital.

### 7.2 Partitioning

For each of the ten competitions:

```text
outer
= latest completed season

development
= every completed season before outer
```

Within development, construct expanding season folds:

```text
season 1
→ validate season 2

season 1 + season 2
→ validate season 3

...

all development seasons except final dev validation block
→ validate next block
```

If the current canonical history for a competition cannot support the predefined design,
do not pool leagues or invent a replacement. Record an evidence gap and STOP before product
implementation.

### 7.3 Independent Poisson

For every eligible chronological target, record at minimum:

- competition;
- season;
- target cutoff;
- total prior training matches;
- home target-team prior same-league matches;
- away target-team prior same-league matches;
- effective weighted evidence if the current adapter exposes a defensible definition;
- selected `xi`;
- probabilities HOME/DRAW/AWAY;
- actual outcome;
- structural applicability;
- `PRODUCED / UNAVAILABLE / FAILED`.

Hyperparameter selection:

```text
xi ∈ {0.0, 0.001, 0.002}
→ inner chronological validation
→ choose minimum finite multiclass log-loss
```

The Independent Poisson selector must not read the Dixon-Coles winner.

### 7.4 Elo Multinomial Logit

For every chronological target, record at minimum:

- competition;
- season;
- cutoff;
- local-team prior matches before cutoff;
- away-team prior matches before cutoff;
- local pre-target rating;
- away pre-target rating;
- distance from neutral 1500 when reproducible;
- training-slice class support;
- selected K;
- selected C;
- probabilities;
- actual outcome;
- `PRODUCED / UNAVAILABLE / FAILED`.

Mechanical gate:

```text
training slice lacks HOME or DRAW or AWAY
→ UNAVAILABLE
```

Hyperparameter selection:

```text
K × C current grid
→ inner chronological validation
→ choose minimum finite multiclass log-loss

all losses non-finite
→ no winner
→ UNAVAILABLE
```

### 7.5 Evidence bands

No hard-coded bands are permitted.

Within development only:

```text
candidate evidence dimensions
→ derive quantile/data-driven bands
→ compare probabilistic quality and stability
```

Outer data cannot alter those bands.

Poisson primary maturity dimensions:

- home target-team prior same-league matches;
- away target-team prior same-league matches;
- total prior training history;
- effective weighted evidence only if already meaningful in the arm.

Elo primary maturity dimensions:

- local target-team prior matches;
- away target-team prior matches;
- rating progression from neutral prior as diagnostic;
- training class support.

Current-season-only counts are secondary because Elo ratings continue across seasons.

### 7.6 Metrics

Primary evaluation:

- multiclass log-loss;
- multiclass Brier;
- HOME/DRAW/AWAY calibration/reliability;
- coverage;
- probability/metric stability.

Complementary:

- RPS;
- accuracy.

Coverage means:

```text
valid Predictions / eligible evaluation targets
```

and is accompanied by separate counts of:

- PRODUCED;
- UNAVAILABLE;
- FAILED.

### 7.7 Uncertainty

Where sample size permits, use temporal-block/season-block uncertainty rather than iid
random resampling.

Confidence-interval overlap is not an automatic gate.

A readiness boundary is acceptable only if development shows a sustained and practically
meaningful change/stabilisation, the effect is not driven by one tiny slice, and the frozen
rule survives outer evaluation.

### 7.8 Result disposition

For each model×competition, Phase A must produce one of:

```text
A. ADDITIONAL_READINESS_GATE_JUSTIFIED
→ version the simplest evidence predicate supported by development
→ freeze it
→ validate it on outer

B. NO_ADDITIONAL_STATISTICAL_GATE_JUSTIFIED
→ structural applicability is sufficient for readiness profile
→ freeze that explicit conclusion/profile
→ validate on outer

C. EVIDENCE_INSUFFICIENT_TO_DEFINE_USABLE_PROFILE
→ STOP
→ FS-012 remains BLOCKED
→ obtain targeted missing evidence/source/research
→ rerun calibration
```

Option C is not a mergeable dormant implementation.

---

## 8. Empirical results

No local empirical calibration was executed during Deep Research.

That absence is intentional in this final artifact and must not be disguised with invented
numbers.

Maintainer disposition on 2026-09-07:

```text
the empirical study becomes mandatory FS-012 Phase A
→ no product-code Codex pass before results are returned and reviewed
→ numeric/model×competition readiness values become implementation inputs
```

Required Phase A output:

```text
20 current model×competition calibration dispositions
+
selected Poisson xi values
+
selected Elo K/C values
+
versioned readiness predicates/config
+
development/outer metrics
+
coverage/unavailable/failed evidence
```

FS-012 cannot be completed unless the ten current competitions are automatically usable by
both arms or a source/evidence gap is resolved within the ticket before implementation
continues.

---

## 9. Independent Poisson conclusions

### REQUIRED

- keep pure `PoissonGoalsModel`;
- use canonical sporting history only;
- no odds;
- known-team/history structural guards remain;
- connectivity diagnostic only;
- independently select `xi`;
- keep current grid only;
- produce/persist valid probabilities independently of downstream Decision;
- apply an automatically provisioned competition-specific readiness profile;
- profile may explicitly encode “no additional statistical gate beyond structural
  applicability” if that is what the calibration supports;
- no manual approval step.

### FORBIDDEN

- copying Dixon-Coles `xi`;
- N=1/N=8/any arbitrary magic threshold;
- bivariate/correlated upgrade under the same arm;
- market odds as predictive input;
- runtime provider calls for readiness.

---

## 10. Elo Multinomial Logit conclusions

### REQUIRED

- preserve dynamic Elo + multinomial logit;
- preserve prior 1500;
- preserve HFA 100;
- preserve current K/C grids;
- preserve same-day anti-leakage;
- `<3` classes in chronological training → UNAVAILABLE;
- all K/C non-finite → no winner → UNAVAILABLE;
- prior-only/new-team may be mechanically PRODUCED;
- readiness depends on automatically calibrated evidence, not a special K or manual
  approval;
- automatically provision a competition-specific profile.

### FORBIDDEN

- N=3 as maturity threshold;
- K=40-for-newcomers rule;
- season regression;
- promoted-team lower-division prior;
- HFA tuning in FS-012;
- native Elo probability replacement.

---

## 11. Reporting reason finding

Observed real `/daily/` evidence:

```text
readiness_reason = APPROVED_READINESS_PROFILE_PASSED
bet_eligible = true

rendered human text
= "Motivo no clasificado"
```

Research conclusion:

- persisted semantic reason is meaningful/current;
- reporting must not rename the persisted code to fit presentation;
- exact mapping owner/path is a local preflight fact;
- FS-012 should audit the current readiness reason vocabulary reachable by this reporting
  path and add explicit human-readable Spanish mappings for current known reasons;
- fallback remains for genuinely unknown future codes;
- no reporting redesign is justified.

---

## 12. Combined-ticket coherence

**Disposition: COMBINED_TICKET_RECOMMENDED**

Rationale:

```text
one shared FS-011 historical/readiness foundation
+
one shared empirical calibration lifecycle
+
Poisson-specific xi/readiness delta
+
Elo-specific K/C/prior-readiness delta
+
same automatic profile provisioning/currentness requirement
+
one bounded readiness-reason reporting fix
=
one coherent outcome
```

The ticket ends only when both arms are automatically usable; splitting calibration from
implementation would create the exact dormant state the maintainer forbids.

---

## 13. Contradictions and uncertainty

### Closed contradictions

- Mechanical production with tiny N does not establish maturity.
- Global Poisson connectivity is not justified as a hard readiness gate.
- The current Finsport xi grid is a project choice, not a literature standard.
- Elo prior 1500 does not justify a special new-team K.
- Global presence of three result classes does not eliminate per-slice mechanical class
  failure.
- Training loss is not the hyperparameter-selection contract; inner chronological
  validation is.
- `coverage` in this study means prediction coverage, not confidence-interval coverage.

### Remaining numerical uncertainty

Exact readiness predicates and selected configurations for each competition are intentionally
unknown until Phase A executes.

This does not reopen product strategy because the decision procedure and acceptable
outcomes are already frozen.

---

## 14. Falsification

### Poisson

Reconsider a candidate profile if:

- outer evaluation reverses the development maturity pattern;
- the apparent threshold is driven by one small temporal block;
- lower-evidence bands are not materially worse;
- connectivity unexpectedly explains a robust failure mode;
- independent `xi` selection repeatedly hits a grid boundary and external values become
  a justified future research question;
- current checkout already generalized the selector differently than the audit baseline.

### Elo

Reconsider a candidate profile if:

- prior-only/low-history targets are as stable and calibrated as established targets;
- target-team experience does not explain maturity;
- class support dominates all other effects;
- all-inf selection is already solved by a generic helper;
- current arm semantics changed after the audited baseline.

### Reporting

Reconsider the bounded mapping fix if the exact preflight shows the fallback originates
outside the readiness-reason mapping layer or the reason vocabulary has been redesigned.

---

## 15. Required / May / Out / Preflight-only

| Item | Disposition | Reason |
|---|---|---|
| Phase A local empirical calibration | REQUIRED | Numeric profiles cannot be guessed |
| 20 current model×competition usable profiles | REQUIRED | No dormant implementation |
| automatic profile provisioning/currentness | REQUIRED | No manual activation |
| Poisson own `xi` | REQUIRED | Audit finding IP-F01 |
| current XI_GRID only | REQUIRED | No expansion evidence |
| Elo all-inf guard | REQUIRED | Audit finding ELO-F01 |
| Elo prior maturity profile | REQUIRED | Valid Prediction != maturity |
| readiness reason human mapping | REQUIRED | Real smoke finding |
| generic finite-selector helper | MAY | Only if checkout supports clean reuse |
| extra diagnostics already cheap to compute | MAY | Helpful but not a new model |
| exact ORM/profile shape | PREFLIGHT-ONLY | Checkout fact |
| exact reporting mapper path | PREFLIGHT-ONLY | Checkout fact |
| exact maintenance hook | PREFLIGHT-ONLY | Checkout/runtime fact |
| Dixon-Coles redesign | OUT | Already closed |
| new predictive features | OUT | New challengers |
| ROI/Capital readiness | OUT | Wrong layer |
| Grafana/runtime repair | OUT | Separate future maintenance |
| real betting | OUT/FORBIDDEN | Product boundary |

---

## 16. New Work Discovered

1. **Post-FS-012 runtime/observability maintenance** remains separate:
   - stale/orphaned `PipelineRun` after DB failure;
   - `safe-down` quiescence blocked by durable RUNNING rows;
   - other Grafana errors accumulated during long-running operation.

2. **Readiness calibration performance/caching** may become a future finding if automatic
   revalidation is too expensive. FS-012 itself must ensure full walk-forward calibration is
   not run on every normal pipeline wake.

3. **Generic ignored reconciliation state** for reviewed non-one-to-one secondary refs
   remains separate.

None of these expands FS-012 automatically.

---

## 17. Durable bibliography

Primary/authoritative references preserved from the research and prior handoffs:

- Maher, M. J. (1982). *Modelling association football scores*. Statistica Neerlandica.
  DOI: https://doi.org/10.1111/j.1467-9574.1982.tb00782.x
- Dixon, M. J.; Coles, S. G. (1997). *Modelling association football scores and
  inefficiencies in the football betting market*. The Statistician 46(2), 265–280.
  DOI: https://doi.org/10.1111/1467-9876.00071
- Elo, A. E. (1978). *The Rating of Chessplayers, Past and Present*, 2nd ed.
  Arco Publishing.
- Brier, G. W. (1950). *Verification of forecasts expressed in terms of probability*.
  Monthly Weather Review 78(1), 1–3.
- Epstein, E. S. (1969). *A scoring system for probability forecasts of ranked
  categories*. Journal of Applied Meteorology 8(6), 985–987.
- Murphy, A. H. (1971). *A new vector partition of the probability score*.
  Journal of Applied Meteorology 10(2), 318–321.
- Gneiting, T.; Raftery, A. E. (2007). *Strictly Proper Scoring Rules, Prediction, and
  Estimation*. Journal of the American Statistical Association 102(477), 359–378.
  DOI: https://doi.org/10.1198/016214506000001437
- Hyndman, R. J.; Athanasopoulos, G. (2021). *Forecasting: Principles and Practice*,
  3rd ed. OTexts. https://otexts.com/fpp3/ — accessed 2026-09-07.

Finsport-specific evidence authorities:

- `Finsport_INDEPENDENT_POISSON_applicability_handoff_2026-09-03.md`
- `Finsport_ELO_MULTINOMIAL_LOGIT_applicability_handoff_2026-09-03.md`
- `FS-011_historical_ingestion_dixon_coles.md`
- `FS-011_handoff_final.md`
- corrected Deep Research outputs dated 2026-09-07
- `FS-011_daily_smoke_2026-09-07.html`

---

## 18. Exact handoff to F008

```text
RESEARCH OUTCOME

Facts established:
- FS-011 provides the shared 10-league historical/readiness foundation.
- Independent Poisson and Elo consume sporting history without odds.
- Poisson must select its own xi from the current grid.
- Elo keeps prior 1500, HFA 100 and current K/C grids.
- Elo <3 classes is a mechanical per-slice gate.
- all-invalid Elo K/C has no legitimate winner and maps to UNAVAILABLE in Finsport.
- no universal readiness N is externally justified.
- the /daily/ readiness-reason fallback is a real observed reporting defect.

Recommendations promoted:
- one combined FS-012.
- empirical calibration is a REQUIRED first execution phase.
- no product-code implementation before calibration results are reviewed.
- calibrate model-specific, competition-specific profiles.
- profile may explicitly encode no additional statistical gate when the evidence supports it.
- automatically provision/current profiles; no manual approval.
- current target is 20 usable profiles.
- if any current model×competition cannot be justified, FS-012 is BLOCKED until missing
  evidence/source/research is obtained.
- automatic revalidation must reuse the existing pipeline/maintenance owner and must not
  run full calibration on every wake.
- fix current readiness reason rendering in the same bounded ticket.

Can close now:
- R3, R4, R6, R7 and R9.
- implementation strategy for R1/R2/R5.
- R8 product/reporting behavior.

Must remain open only as execution evidence:
- exact per-competition readiness predicates.
- exact selected Poisson xi values.
- exact selected Elo K/C values.
- exact current checkout/profile/helper paths.

Pending inputs:
- none from Luis before ticket creation.

Preflight-only unknowns:
- exact ORM/profile generalization shape.
- exact maintenance hook/currentness basis.
- exact reporting mapper location.
- exact reusable backtest/calibration helper shape.

Implementation implications:
- Phase A DB-only calibration → STOP/review → Phase B product implementation.
- no Codex product-code pass before Phase A closes.
- all current arms must be automatically usable when ticket is DONE.

Non-goals preserved:
- provider/runtime historical polling redesign.
- new model families/features.
- Decision/Capital/evaluator redesign.
- Grafana/runtime maintenance.
- real betting.

Combined-ticket disposition:
- COMBINED_TICKET_RECOMMENDED

Artifact:
- Finsport_independent_poisson_elo_readiness_research_2026-09-07.md

Integrity audit:
- PASS FOR FS-012 DEFINITION
```

---

## 19. Integrity checklist

- [x] Local facts are distinguished from external methodology.
- [x] Intermediate Deep Research mistakes were not preserved as conclusions.
- [x] No arbitrary readiness N is promoted.
- [x] No empirical result is fabricated.
- [x] Hyperparameter tuning is chronological and outer-safe.
- [x] Poisson and Elo remain their current pure comparator arms.
- [x] ROI/Capital is excluded from predictive readiness.
- [x] Automatic usability requirement is explicit.
- [x] No manual approval/configuration is left as a product requirement.
- [x] Source/evidence gaps block completion rather than create dormant code.
- [x] Reporting finding is bounded.
- [x] Separate Grafana/runtime maintenance work remains separate.
- [x] Research remains REFERENCE ONLY and does not itself authorize implementation.
