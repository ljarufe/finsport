# E2 — Global Capital Baseline Methodology
## Corrected self-contained research authority — E2.4 targeted semantic-conformance correction

**Project:** Finsport
**Canonical research artifact:** `docs/research/FS-020_global_capital_methodology_research.md`
**Artifact status:** `E2.4 RECONCILED VIA VERSIONED V2R — READY FOR UAT-4`
**Date:** 2026-09-23
**Economic Capital tournament:** NOT EXECUTED
**GLOBAL_CAPITAL_V1:** NOT SELECTED
**GLOBAL_STRATEGY_V1:** NOT SELECTED
**Automatic operational routing:** UNCHANGED
**Real betting:** FORBIDDEN

---

# 1. Research outcome

E2 Phase 1, Phase 2, E2.1, E2.2 and E2.3 remain closed and are **not reopened**.

E2.4 is a targeted correction to the Phase-3 technical reference and the transport precision of two already-frozen inference rules. The incident does not change the seven CURRENT Capital candidates, 100u, max_lanes, TOTAL_RETURN, settlement lags, bootstrap geometry/RNG, all-pairs family, stability, risk, fallback, cumulative candidate family, opportunity-cost role, operational routing or real-betting prohibition.

The original Phase-3 artifact passed cryptographic identity/exactness against itself but failed semantic conformance to CURRENT lane-first placement semantics. Its old feasibility numbers remain historical incident evidence. The published V2 executable identified by `f4afcf3dde508f4f460eff7e58e716c54ea7fd4e99183b402b30d84cd601917a` was not recovered and is not authenticated.

The 2026-09-23 reconciliation accepts a distinct reconstructed and versioned reference, `E2_PHASE3_EVENT_TIME_REFERENCE_V2R_LANE_FIRST`, SHA-256 `fa55e297ec2b334b6b8cf2aa70bd62974f98f1994a951446d59d9047c1e8e833`. V2R is not represented as the missing published V2. Its integrity, independent C01-C12 semantic conformance, implementation equivalence and bounded host/restart evidence satisfy the three-gate substitution rule for FS-020 pre-UAT-4.

Current E2.4 state in this artifact:

```text
upstream binding
→ remains CLOSED

methodology outside targeted scope
→ remains FROZEN

reconstructed V2R reference
→ ARTIFACT_INTEGRITY PASS
→ SEMANTIC_CONFORMANCE 12/12 PASS independently
→ IMPLEMENTATION_EQUIVALENCE 21/21 PASS

bounded V2R CPU feasibility
→ PASS WITH DECLARED LIMITS

FS-020
→ READY_FOR_UAT4
```

No economic Capital election was run.

---

# 2. Immutable upstream authorities

Local/sequential authority:

```text
GLOBAL_PREDICTION_V1
→ MARKET_CONSENSUS
→ fs013-market-consensus-v2

GLOBAL_DECISION_V1
→ MODAL_ALL
→ fs003-modal-all-v1
```

FS-019 local Decision disposition:

```text
UNSTABLE
```

Local/sequential control remains:

```text
MARKET_CONSENSUS + MODAL_ALL
```

Accepted FS-019 cumulative cross-layer result:

```text
33 eligible P×D candidates

DIXON_COLES + VALUE 0.05
→ OBSERVED_TOP
→ UNSTABLE
→ NOT PROVEN SUPERIOR
→ NOT PROMOTED
```

E2 does not reinterpret or overwrite these authorities.

---

# 3. Local vs cumulative questions

## 3.1 LOCAL CAPITAL ELECTION

Question:

```text
GLOBAL_PREDICTION_V1
+
GLOBAL_DECISION_V1
×
7 CURRENT Capital configs
```

Output authority:

```text
GLOBAL_CAPITAL_V1
or
NO_PROMOTION
```

`GLOBAL_CAPITAL_V1` is local/sequential Capital authority only.

## 3.2 CUMULATIVE INTEGRATED ELECTION

Question:

```text
33 frozen eligible P×D candidates
×
7 CURRENT Capital configs
=
231 conceptual integrated candidates
```

Output authority:

```text
GLOBAL_STRATEGY_V1
or
NO_PROMOTION
```

Do not assume:

```text
GLOBAL_PREDICTION_V1
+
GLOBAL_DECISION_V1
+
GLOBAL_CAPITAL_V1

=

GLOBAL_STRATEGY_V1
```

Local authorities remain durable and auditable even if a cumulative integrated strategy later uses different components.

---

# 4. Exact seven CURRENT Capital configurations

Frozen order:

| # | Capital config | Version | Config | max_lanes |
|---:|---|---|---|---:|
| 1 | FLAT_UNIT | fs004-flat-unit-v1 | `{"unit":"1"}` | 10 |
| 2 | FIXED_FRACTION_BANKROLL | fs004-fixed-fraction-bankroll-v1 | `{"fraction":"0.05"}` | 10 |
| 3 | FIXED_TARGET_PROFIT_NO_RECOVERY | fs004-fixed-target-no-recovery-v1 | `{"target_profit":"1"}` | 10 |
| 4 | LEGACY_RECOVERY | fs004-legacy-recovery-deviation-1-v1 | `{"initial_stake":"1"}` | 1 |
| 5 | LEGACY_CAPPED | fs004-legacy-capped-v1 | `{"initial_stake":"1","max_absolute_stake":"5"}` | 1 |
| 6 | LEGACY_PARTIAL | fs004-legacy-partial-v1 | `{"target_profit":"1","alpha":"0.5"}` | 1 |
| 7 | FRACTIONAL_KELLY | fs004-fractional-kelly-v1 | `{"lambda":"0.25"}` | 10 |

Common:

```text
initial bankroll
→ 100u independently per candidate
```

No policy, lane-grid, Kelly-lambda or recovery sweep is allowed in the first election.

---

# 5. Local Capital primary election contract

Primary metric:

```text
TOTAL_RETURN
=
(W_T - 100u) / 100u

direction
→ higher is better
```

Capital is one global multi-league bankroll per candidate.

Do not replace primary selection with:

```text
ROI / total_staked
Sharpe
log-wealth
Kelly utility
```

Risk, capacity and opportunity-cost quantities remain separate from the primary ranking metric.

---

# 6. Exact Event-Time contract — E2.4 corrected placement precedence

The governing authority is CURRENT Capital Event-Time plus F002/F003 domain/architecture semantics.

At each event instant `t`:

```text
A. SETTLEMENT / RESOURCE RELEASE
1. settle every due OPEN position with settlement_at <= t
2. release reserved exposure and lane
3. update bankroll equity and versioned policy state

B. PENDING EXPIRY
4. terminalize PENDING opportunities whose kickoff <= t
   → EXPIRED_CAPACITY / NOT_PLACED
   → never in-play

C. OPPORTUNITY SET
5. add newly executable actionable opportunities at t
6. merge still-valid PENDING + new opportunities
7. deduplicate by frozen opportunity identity
8. rank exactly:
      EV_unit DESC
      kickoff ASC
      stable identity

D. SERIAL PLACEMENT ATTEMPT FOR EACH RANKED OPPORTUNITY
9. verify opportunity is still strictly pre-kickoff
10. verify lane availability BEFORE any stake request

11. if open_count >= max_lanes:
      → PENDING_CAPACITY
      → policy.request MUST NOT be invoked for this attempt
      → no Position
      → no stake reservation
      → no lane consumption
      → retain frozen T-30 economic basis
      → retry only at a later resource/event wake while now < kickoff

12. if a lane exists:
      construct/reconstruct CapitalDecision from the frozen basis
      call policy.request exactly once for this attempt
      recompute stake from CURRENT bankroll/policy state

13. after policy.request, preserve CURRENT runtime branch order:
      a. non-empty termination_reason
         → explicit policy termination
      b. requested <= 0 or applied <= 0
         → typed terminal zero-stake / ineligible Capital outcome
         → Kelly NO_POSITIVE_KELLY_EDGE is not practical ruin
      c. requested_stake > available_cash
         → PENDING_CAPACITY
         → no Position / no reservation
         → retry later pre-kickoff and recompute request from then-CURRENT state
      d. otherwise
         → reserve applied stake
         → create OPEN Position
         → consume one lane
```

Invariant at every resource-changing point:

```text
available_cash = bankroll_equity - reserved_exposure
```

Same-timestamp precedence is contract:

```text
settlement
→ reserved exposure / lane release
→ policy state + bankroll update
→ pending expiry
→ pending/new merge and ranking
→ retry / fresh placement
```

Therefore a due settlement may make a pending opportunity executable **in the same wake**.

### E2.4 adversarial incident

Exact counterexample:

```text
10/10 FRACTIONAL_KELLY lanes occupied
+
11th valid opportunity
+
edge <= 0
```

Old `E2_PHASE3_EVENT_TIME_REFERENCE_V1`:

```text
policy.request first
→ NO_POSITIVE_KELLY_EDGE
→ ZERO_STAKE
```

Governing CURRENT / corrected V2:

```text
lane check first
→ PENDING_CAPACITY
→ policy.request invocation count = 0 for blocked attempt
```

If a lane is released before kickoff:

```text
retry
→ policy.request is invoked then
→ stake is recomputed from CURRENT state
→ ZERO_STAKE may occur at retry if edge is still non-positive
```

If no lane is released before kickoff:

```text
→ EXPIRED_CAPACITY
```

The existing `football/capital/studies.py::_run_path` remains non-authoritative because it does not reproduce the full CURRENT pending lifecycle.

### Post-request ordering note

The E2.4 incident concerns lane-before-request ordering. CURRENT `place_candidate` orders the post-request branches as:

```text
termination_reason
→ zero/applied<=0
→ insufficient available_cash
→ placement
```

That CURRENT order is preserved. A brief-level pseudocode that listed cash/zero/termination differently is not allowed to silently replace CURRENT; no methodology expansion is introduced in E2.4.

---

# 7. Executable risk semantics

Economic ruin:

```text
bankroll_equity <= 0
or
termination_reason == BANKROLL_DEPLETED
```

Explicit policy termination:

```text
versioned Capital policy emits non-empty termination_reason
```

These are promotion vetoes.

Not practical ruin by themselves:

```text
requested_stake > available_cash because capital is reserved
PENDING_CAPACITY
EXPIRED_CAPACITY
capacity non-placement
cap hit / shortfall without termination
Kelly NO_POSITIVE_KELLY_EDGE zero stake
```

Integrity/runtime invariant failure:

```text
scientific disposition
→ INSUFFICIENT_EVIDENCE
promotion
→ NO_PROMOTION
```

No arbitrary maximum-drawdown promotion threshold was invented.

---

# 8. Historical settlement-time and cross-lag contract — complete executable form

Historical research settlement timing remains unchanged:

```text
PRIMARY     → kickoff +150m
SENSITIVITY → kickoff +120m
SENSITIVITY → kickoff +130m
```

These are synthetic research times and do not claim historical `result_known_at`.

For each independent lag `x ∈ {120m,130m,150m}`, compute only lag-local evidence first:

```text
OBSERVED_LEADER_x
OBSERVED_RUNNER_UP_x
UNIQUE_OBSERVED_LEADER_x
WITHIN_LAG_STRUCTURAL_GATE_x
WITHIN_LAG_STABILITY_x
ALL_PAIRS_1W_x
ALL_PAIRS_2W_x
ALL_PAIRS_4W_x
```

Structural/estimability failure includes any required common input/candidate/path/stability/bootstrap/all-pairs evidence being unavailable, all required pair SEs degenerating to zero in a required design, or a material integrity/lineage defect.

Then exactly:

```text
if WITHIN_LAG_STRUCTURAL_GATE_x == FAIL:
    WITHIN_LAG_DISPOSITION_x = INSUFFICIENT_EVIDENCE

elif WITHIN_LAG_STABILITY_x == UNSTABLE:
    WITHIN_LAG_DISPOSITION_x = UNSTABLE

elif UNIQUE_OBSERVED_LEADER_x == True
 and WITHIN_LAG_STABILITY_x == PASS
 and STRICT_TOP_VS_ALL_2W_x == PASS
 and STRICT_TOP_VS_ALL_1W_x == PASS
 and STRICT_TOP_VS_ALL_4W_x == PASS:
    WITHIN_LAG_DISPOSITION_x = CLEAR_SUPERIORITY

else:
    WITHIN_LAG_DISPOSITION_x = NO_CLEAR_SUPERIORITY
```

For each block design independently:

```text
STRICT_TOP_VS_ALL_LW_x == PASS
iff
LB_x,LW(OBSERVED_LEADER_x - c) > 0
for every other candidate c
```

`LB == 0` fails strict superiority.

Within-lag fallback remains:

```text
if WITHIN_LAG_DISPOSITION_x != NO_CLEAR_SUPERIORITY:
    WITHIN_LAG_FALLBACK_x = NOT_APPLICABLE
else:
    T_x = OBSERVED_LEADER_x
    if FLAT_UNIT structurally complete
       and HARD_RISK_x(FLAT_UNIT) == PASS
       and (T_x == FLAT_UNIT or LB_2W_x(T_x - FLAT_UNIT) <= 0):
        WITHIN_LAG_FALLBACK_x = FLAT_UNIT
    else:
        WITHIN_LAG_FALLBACK_x = NO_PROMOTION
```

Within-lag promotion is exactly:

```text
CLEAR_SUPERIORITY + leader hard-risk PASS
→ WITHIN_LAG_PROMOTION_x = PROMOTE:<OBSERVED_LEADER_x>

CLEAR_SUPERIORITY + leader hard-risk FAIL
→ WITHIN_LAG_PROMOTION_x = NO_PROMOTION_RISK_GATE

NO_CLEAR_SUPERIORITY + fallback FLAT_UNIT
→ WITHIN_LAG_PROMOTION_x = PROMOTE:FLAT_UNIT

NO_CLEAR_SUPERIORITY + no fallback
→ WITHIN_LAG_PROMOTION_x = NO_PROMOTION

UNSTABLE / INSUFFICIENT_EVIDENCE
→ WITHIN_LAG_PROMOTION_x = NO_PROMOTION
```

No within-lag object may consult another settlement lag.

## Exact `SETTLEMENT_SIGNATURE_x`

Define once, after the independent 150m observed path exists:

```text
PRIMARY_150M_LEADER = OBSERVED_LEADER_150m
```

For every computable lag `x`, persist exactly this ordered tuple:

```text
SETTLEMENT_SIGNATURE_x = (
    OBSERVED_LEADER_x,
    WITHIN_LAG_DISPOSITION_x,
    WITHIN_LAG_PROMOTION_x,
    HARD_RISK_x(OBSERVED_LEADER_x),
    HARD_RISK_x(PRIMARY_150M_LEADER),
    HARD_RISK_x(FLAT_UNIT),
    WITHIN_LAG_FALLBACK_x,
)
```

Tuple field order is contract. Candidate identities use canonical Capital policy codes; disposition/promotion/risk/fallback values use canonical normalized enum/string values. Equality is exact field-for-field after normalization.

No signature field may depend on:

```text
settlement_time_stability
FINAL_CAPITAL_SCIENTIFIC_DISPOSITION
FINAL_PROMOTION_PERMISSION
FINAL_PROMOTION_TARGET
```

Cross-lag comparison occurs **only after all three independent lag-local signatures exist**.

Final precedence:

```text
if any required lag cannot be computed
 or any WITHIN_LAG_DISPOSITION_x == INSUFFICIENT_EVIDENCE:

    settlement_time_stability = NOT_ESTIMABLE
    FINAL_CAPITAL_SCIENTIFIC_DISPOSITION = INSUFFICIENT_EVIDENCE
    FINAL_PROMOTION_PERMISSION = NO_PROMOTION
    FINAL_PROMOTION_TARGET = None

elif SETTLEMENT_SIGNATURE_120m != SETTLEMENT_SIGNATURE_150m
  or SETTLEMENT_SIGNATURE_130m != SETTLEMENT_SIGNATURE_150m:

    settlement_time_stability = UNSTABLE
    FINAL_CAPITAL_SCIENTIFIC_DISPOSITION = UNSTABLE
    FINAL_PROMOTION_PERMISSION = NO_PROMOTION
    FINAL_PROMOTION_TARGET = None

else:
    settlement_time_stability = PASS
    FINAL_CAPITAL_SCIENTIFIC_DISPOSITION = WITHIN_LAG_DISPOSITION_150m

    if WITHIN_LAG_PROMOTION_150m starts with "PROMOTE:":
        FINAL_PROMOTION_PERMISSION = PROMOTE
        FINAL_PROMOTION_TARGET = candidate after "PROMOTE:"
    elif WITHIN_LAG_PROMOTION_150m == NO_PROMOTION_RISK_GATE:
        FINAL_PROMOTION_PERMISSION = NO_PROMOTION_RISK_GATE
        FINAL_PROMOTION_TARGET = None
    else:
        FINAL_PROMOTION_PERMISSION = NO_PROMOTION
        FINAL_PROMOTION_TARGET = None
```

If all three signatures agree on `UNSTABLE`, then `settlement_time_stability = PASS` because the lags agree with each other, while the final scientific disposition remains `UNSTABLE` and promotion remains `NO_PROMOTION`.

---

# 9. Bootstrap / uncertainty contract

Timezone:

```text
America/Lima
```

Continuous calendar-week universe:

```text
Monday 00:00 local
→ next Monday
```

Opportunity membership is assigned by:

```text
synthetic execution_at
=
kickoff - 30m
```

Frozen resampling:

```text
1w blocks
2w blocks → PRIMARY
4w blocks

replicates
→ 5000

generator
→ numpy PCG64

seed sequence for block length L
→ SeedSequence([21092026, L])
```

Resampling is:

```text
global
paired
stateful
moving-block
```

Every replicate:

```text
starts Capital once at 100u
reconstructs full Event-Time state
carries state continuously through synthetic concatenated blocks
uses identical sampled block sequence across all candidates
```

Do not bootstrap realized Capital P&L rows.

---

# 10. Physically bound bootstrap universe

Phase 3 measured:

```text
first synthetic execution
→ 2026-01-13T17:00:00+00:00

last synthetic execution
→ 2026-09-18T18:30:00+00:00

continuous Lima calendar weeks W
→ 36

first week
→ 2026-01-12

last week
→ 2026-09-14

empty weeks
→ 6
→ 2026-06-01
→ 2026-06-08
→ 2026-06-15
→ 2026-06-22
→ 2026-06-29
→ 2026-07-06
```

Frozen RNG matrix identities:

```text
1w
→ e631dccb1c9cec30ddb6531a83a6b242856001703bfe4a6fde46f35b746761bb

2w
→ 1bbed9db7c98fcc36403dec74f265260fdf3e414723e1d300d80466ccc6ef2e0

4w
→ d069403cecf99c572c936699c6f01b88dea11b76951c3628decafbdc6c941835
```

---

# 11. Simultaneous all-pairs inference — complete executable convention

For `M` eligible conceptual candidates, use all unordered pairs in frozen candidate order:

```text
(i,j) for every i < j
pair_count = M(M-1)/2
```

Local seven-arm family:

```text
M=7 → 21 pairs
```

Cumulative upper bound remains:

```text
M=231 → 26,565 pairs
```

For canonical pair `(i,j)` under the same lag/design:

```text
theta_i = observed TOTAL_RETURN_i
theta_j = observed TOTAL_RETURN_j

d_ij = theta_i - theta_j

d_ij^(b) = theta_i^(b) - theta_j^(b)
```

Bootstrap deltas remain in replicate order and are converted to `numpy.float64`. They are **not** recentered on the bootstrap mean. The observed `d_ij` is the center of the max statistic.

Sample SE is exactly:

```python
se_ij = numpy.std(delta_bootstrap_ij, ddof=1)
```

The zero test is exact `numpy.float64 == 0.0`; no tolerance is selected post hoc.

## 11.1 `se_ij > 0`

For every replicate `b`:

```text
z_b,ij = abs(d_ij^(b) - d_ij) / se_ij
```

For every replicate:

```text
M_b = max(z_b,ij over all canonical pairs with se_ij > 0)
```

If at least one canonical pair has positive SE:

```python
q95 = numpy.quantile(
    numpy.asarray(M, dtype=numpy.float64),
    0.95,
    method="linear",
)
```

Then for every positive-SE pair:

```text
LB_ij = d_ij - q95 * se_ij
UB_ij = d_ij + q95 * se_ij
```

## 11.2 Exact `se_ij == 0.0` convention

A zero-SE pair:

```text
studentized statistic
→ NOT FORMED / not divided by zero

contribution to M_b
→ NONE / excluded from max-statistic family calculation

simultaneous interval
→ [d_ij, d_ij]

deterministic_se_zero
→ true
```

This rule is used even if the constant bootstrap delta is numerically different from the observed `d_ij`; the frozen E2.1 convention does not invent an alternate pseudo-SE or tolerance. The reported simultaneous interval remains the point interval centered at the observed `d_ij`.

A zero-SE pair remains available as a deterministic point comparison **when at least one other required pair has positive SE**, so the family max statistic and `q95` are estimable from the positive-SE pairs.

If **all required canonical pairs in a required design** have `se_ij == 0.0`:

```text
q95 = 0.0  # stored only for deterministic completeness
simultaneous_inference_status = DEGENERATE_ALL_SE_ZERO
required design = NOT ESTIMABLE for superiority
WITHIN_LAG_DISPOSITION_x = INSUFFICIENT_EVIDENCE
```

For the local seven-arm family this means all 21 pairs are zero-SE. For a larger preregistered family the same rule applies to all required canonical pairs in that family.

A completely degenerate resampling family may never support `CLEAR_SUPERIORITY`.

## 11.3 Orientation reversal for `T - c`

If `index(T) < index(c)`, canonical storage already represents `T-c`:

```text
LB(T-c) = LB_Tc
UB(T-c) = UB_Tc
```

If `index(c) < index(T)`, canonical storage represents `c-T` with interval `[LB_cT, UB_cT]`. Reverse exactly:

```text
interval(T-c) = [-UB_cT, -LB_cT]
LB(T-c) = -UB_cT
UB(T-c) = -LB_cT
```

For a deterministic zero-SE stored interval `[d,d]`, reversal is the deterministic point interval `[-d,-d]`.

Strict superiority is always:

```text
LB(T-c) > 0
```

`LB == 0` fails. No `>= 0` substitution is permitted.

Family-wise target remains 95%; E2.4 does not change multiplicity methodology.

---

# 12. Scientific dispositions

Allowed:

```text
CLEAR_SUPERIORITY
NO_CLEAR_SUPERIORITY
UNSTABLE
INSUFFICIENT_EVIDENCE
```

Within a lag:

```text
unestimable required evidence
→ INSUFFICIENT_EVIDENCE

negative required stability delta
→ UNSTABLE

unique observed leader
+ within-lag stability PASS
+ 2w strict simultaneous top-vs-all PASS
+ 1w strict sensitivity PASS
+ 4w strict sensitivity PASS
→ CLEAR_SUPERIORITY

otherwise
→ NO_CLEAR_SUPERIORITY
```

Scientific disposition remains separate from product fallback and risk veto.

---

# 13. Local stability / falsification

Chronological halves:

```text
same continuous Lima week universe
empty weeks retained
H1 = floor(W/2)
H2 gets extra week if W is odd
fresh 100u per half
```

Leave-one-competition-out:

```text
remove one competition's opportunities
rerun full remaining Event-Time path from fresh 100u
```

Full-path top `T` and runner-up `R` remain fixed for local checks.

No subtraction of already-realized league P&L.

---

# 14. Cumulative stability / falsification

For each settlement lag `x`:

```text
T_x
→ full observed cumulative leader under x
```

In every required half and leave-one-competition-out slice:

```text
rerun the full integrated Capital path
from fresh 100u

compare T_x against every other eligible integrated candidate
```

Disposition:

```text
any required slice unestimable
→ INSUFFICIENT_EVIDENCE

any T_x - c < 0
→ UNSTABLE

any T_x - c == 0
→ NON_STRICT

otherwise
→ PASS
```

Cross-lag E2.2 precedence is then applied.

---

# 15. Local fallback

If:

```text
NO_CLEAR_SUPERIORITY
```

then:

```text
FLAT_UNIT
```

may be the usable local baseline only if:

```text
structurally complete
hard-risk PASS
not shown clearly inferior to provisional top
under the same simultaneous family
```

Otherwise:

```text
NO_PROMOTION
```

For:

```text
UNSTABLE
INSUFFICIENT_EVIDENCE
```

always:

```text
NO_PROMOTION
```

No "next best" post-hoc fallback.

---

# 16. Integrated fallback

Frozen cumulative control:

```text
CUMULATIVE_CONTROL_V1
=
MARKET_CONSENSUS
+
MODAL_ALL
+
FLAT_UNIT
```

This is preregistered before cumulative Capital scores.

Rules:

```text
CLEAR_SUPERIORITY
+ integrated top hard-risk PASS
→ PROMOTE:<integrated top>

CLEAR_SUPERIORITY
+ integrated top hard-risk FAIL
→ NO_PROMOTION_RISK_GATE

NO_CLEAR_SUPERIORITY
+ control structurally complete
+ control hard-risk PASS
+ control not clearly inferior to provisional top
+ settlement-time contract PASS
→ PROMOTE:CUMULATIVE_CONTROL_V1
  while scientific disposition remains NO_CLEAR_SUPERIORITY

otherwise
→ NO_PROMOTION
```

`DIXON_COLES + VALUE 0.05` has no fallback privilege.

---

# 17. Exact cumulative candidate binding

Phase 3 physically bound:

```text
FS-019 PAIRED_COMMON
→ 1,877 exact Matches
→ 10 competitions

P×D candidates
→ 33

rows
→ 1,877 × 33
→ 61,941

unique Capital-relevant P×D stream hashes
→ 33 / 33

behavioral-equivalence compression
→ NONE
```

Exact identities:

```text
repo master
→ e480c2c4d58c76bb834a5f0234f758fb51737e0f

common cohort canonical identity
→ 6b73234190eabfc77c0b597090576c52e798bbe8c902098c965215d38e89c131

common cohort semantic sha256
→ b7f002e826fe6fb7dcc59ad34c4ccb82a2b9966fd50aada58482a6a9e527d216

common cohort gzip sha256
→ 0c51f03fa6a7312b9e4147f8f85185c9dcadefec846b4921b733915c5090521a

upstream Prediction cohort hash
→ 08d8f7c2852444c2e66ed28c4075e2bc51708d3ac918cdb7cf75daf858ae2c1c

P×D matrix identity
→ 05ac15800a11ca887d3b1802ae3cdace0a85aa11e7e5d942be88805f51c23006

P×D combined semantic sha256
→ 4b30e4b38fa422d3118f1550f65e16cf8bab04d9f3b068c0234692f2bee34f36

P×D combined gzip sha256
→ eba4ea7a5c54d03e92a715a0706890b8325c676623adc414b9e400353637aa7d

integrated 231-candidate family semantic sha256
→ 279c2bde5e164be9d30bc5e42502dfcedf1fcdb938abfd123bef58d8b439286c
```

All 231 conceptual arms are structurally input-eligible.

No DB cross-check was required because retained artifacts were sufficient.

---

# 18. Artifact retention / restore

Large retained upstream evidence:

```text
key
→ FS018_E1_PHASE3

status
→ PRESERVE_ACTIVE

producer
→ FS-018

consumer
→ CAPITAL_CUMULATIVE_PHASE
```

Retained archive SHA-256:

```text
8776ff4e91bdbc93d5e3f7826e9b6b28a1128b65220f2dbdaf0475992c577db6
```

Consumer contract:

```text
verify retained archive SHA
→ restore to tmp workspace
→ verify root authority/run/spec/manifest/backfill
→ regenerate scientifically material derived views
→ exact/hash-bind regenerated views
→ materialize frozen alternative streams
→ bind exact common cohort
→ only then execute downstream experiment
```

`tmp/` is not durable authority.

Do not delete the retained FS-018 evidence until the cumulative P×D×Capital evaluation is closed, durable downstream evidence is preserved/verified, and no declared consumer remains.

---

# 19. Opportunity cost

Local seven-config election:

```text
opportunity cost
→ DIAGNOSTIC ONLY
```

Cumulative candidate ordering:

```text
opportunity cost
→ NOT a candidate-ranking metric
```

After integrated selection/fallback:

```text
opportunity-cost comparison
→ REQUIRED DIAGNOSTIC
```

Because research capital remains:

```text
100u
→ no currency bound
```

numeric real-world benchmark remains:

```text
UNAVAILABLE_CURRENCY_NOT_BOUND
```

No claim may be made that an integrated strategy beats a low-risk alternative until same-currency, same-horizon evidence is bound.

---

# 20. Phase-3 reference incident and E2.4 correction

## 20.1 Original reference preserved as incident evidence

Original reference:

```text
reference_id
→ E2_PHASE3_EVENT_TIME_REFERENCE_V1

reference_sha256
→ 59f488a83af6f3e42c679825d6614c8ae83daf6b7883ee779987720a61ce676a

original bundle sha256
→ 15ca6e477017cff8dc0e77d5eaca4bf18e167d19a4de53f6fc5da378dad3675b

original bundle internal SHA256SUMS
→ PASS 11/11
```

Historical statement retained exactly:

```text
V1 was cryptographically intact
V1 was deterministic/exact relative to itself
V1 parallel/shard outputs matched V1 scalar
```

But:

```text
V1 semantic conformance to CURRENT
→ FAIL
```

Therefore the original V1 exactness/throughput/thermal bundle is **not** an authoritative FS-020 implementation reference. It is preserved and never patched in place.

## 20.2 Corrected reference identity

Corrected reference:

```text
reference_id
→ E2_PHASE3_EVENT_TIME_REFERENCE_V2_LANE_FIRST

reference_sha256
→ f4afcf3dde508f4f460eff7e58e716c54ea7fd4e99183b402b30d84cd601917a
```

This identity is retained as historical fact only. The corresponding executable was not recovered or authenticated. It must not be conflated with the accepted reconstruction below.

Reconstructed reference accepted by the 2026-09-23 addendum:

```text
reference_id
→ E2_PHASE3_EVENT_TIME_REFERENCE_V2R_LANE_FIRST

reference_sha256
→ fa55e297ec2b334b6b8cf2aa70bd62974f98f1994a951446d59d9047c1e8e833

relationship to published V2
→ NEW VERSIONED RECONSTRUCTION
→ NOT THE PUBLISHED V2 FILE
```

Only the affected semantic boundary changes:

```text
V1
→ policy.request before lane capacity

V2
→ lane capacity before policy.request
```

V2 also records `POLICY_REQUEST` transitions so fixtures can assert invocation behavior directly.

All unaffected methodology remains frozen.

## 20.3 Semantic-conformance matrix

Bounded deterministic conformance fixtures specified for the corrected semantics (independently executed against V2R in the reconciliation addendum):

```text
C01 lane full + positive stake
→ PENDING_CAPACITY
→ policy.request not invoked for blocked opportunity

C02 lane full + Kelly edge <= 0
→ PENDING_CAPACITY
→ policy.request not invoked
→ no ZERO_STAKE at first blocked attempt
→ old V1 reproduces ZERO_STAKE divergence

C03 lane released before kickoff
→ PENDING retry
→ policy.request invoked at retry
→ stake recomputed
→ Kelly zero-stake may then terminalize

C04 lane never released before kickoff
→ EXPIRED_CAPACITY
→ no policy.request while lane-blocked

C05 lane available + requested > available_cash
→ PENDING_CAPACITY
→ request was invoked because lane existed

C06 cash later available pre-kickoff
→ retry
→ request recomputed
→ placement if now feasible

C07 same-wake settlement/release/state-update/retry
→ SETTLEMENT
→ PENDING_RETRY
→ POLICY_REQUEST
→ PLACEMENT
→ recovery request observes updated policy state

C08 at/after kickoff
→ never place
→ policy.request not invoked

C09 zero stake with lane available
→ policy.request invoked
→ typed ZERO_STAKE

C10 explicit policy termination with lane available
→ policy.request invoked
→ terminal policy outcome

C11 contention
→ EV_unit DESC
→ kickoff ASC
→ stable identity
→ lane-blocked followers do not invoke policy.request

C12 deterministic sharding/restart
→ full == shards
→ recomputed shard == scalar reference
```

Reconciled V2R conformance result:

```text
12 / 12 PASS
SEMANTIC_CONFORMANCE = PASS
PRODUCT_RUNNER_USED_AS_ORACLE = NO
```

This is the acceptance oracle for V2R ordering. It does not authenticate the missing published V2.

## 20.4 Independent acceptance gates

Freeze the reusable distinction:

```text
GATE A — ARTIFACT_INTEGRITY
→ authority/schema/path
→ producer/run/spec lineage
→ hashes/manifest
→ byte identity where required

GATE B — SEMANTIC_CONFORMANCE
→ executable reference behavior
→ adversarial fixtures against governing CURRENT/domain/research contract

GATE C — IMPLEMENTATION_EQUIVALENCE
→ production/Codex implementation
→ accepted semantically conformant reference/oracle
```

Rules:

```text
A PASS + B FAIL
→ authentic but semantically invalid
→ STOP

A FAIL
→ STOP

A PASS + B PASS
→ reference may constrain implementation

C is evaluated only after A+B establish an accepted reference/oracle
```

Canonical lesson:

```text
CRYPTOGRAPHIC_INTEGRITY != SEMANTIC_CONFORMANCE
```

## 20.5 Process escape — HIGH severity

The failure traversed four stages before detection:

```text
Research / original Phase 3
→ authenticated and benchmarked V1 against itself
→ semantic lane-first adversarial oracle missing

F008 / Definition of Ready
→ accepted the package without a separate semantic-conformance gate

F009 / preflight
→ authenticated schema/lineage/path/row counts/hashes/derived views
→ did not independently prove executable reference vs CURRENT semantics

Codex Pass 1
→ detected lane-first contradiction before implementation proceeded
```

Economic evidence invalidated:

```text
NONE
```

because no economic Capital tournament had been executed.

Runtime/application behavior changed before discovery:

```text
NONE
```

Operational routing remains unchanged.

# 21. Corrected technical exactness rerun boundary

E2.4 deliberately does **not** execute the cumulative 231 family and does not perform any economic scoring.

A bounded local seven-config smoke using the frozen `MARKET_CONSENSUS + MODAL_ALL` technical stream and synthetic outcomes revalidated V2R logic:

```text
7 scalar paths at 120m
→ PASS
→ invariant failures 0

7 scalar paths at 130m
→ PASS
→ invariant failures 0

7 scalar paths at 150m
→ PASS
→ invariant failures 0

scalar repeat
→ exact

parallel digest equality in local harness
→ PASS

shard concatenation
→ scalar exact

middle-shard recompute
→ scalar exact
```

This local rerun proves V2R control flow and determinism. The full-corpus 21/21 equivalence and bounded resampled-block host gate are separate evidence recorded in section 35.

# 22. Reconciled V2R host feasibility status

The original V1 host measurements remain historical incident evidence only. No V1 number is relabeled as V2 or V2R evidence. The published V2 executable remains unauthenticated and was not benchmarked.

A bounded host gate executed under the distinct V2R identity established:

```text
serial/parallel exactness
→ PASS 126/126

workers verified
→ 4

shard equivalence/readback/recompute
→ PASS / PASS / PASS

sampled block paths
→ 2 per block length

serial wall / parallel wall
→ 9.866s / 2.600s for the bounded gate

arithmetic projected CPU seconds for 315000 paths
→ 24647.5
→ PROJECTION ONLY; NOT ETA OR SUSTAINED THROUGHPUT GUARANTEE

process max RSS observed
→ 60796 KiB
→ NOT GLOBAL MAXIMUM ACROSS WORKERS

CPU temperature snapshots
→ 50C before / 46C after
→ NOT SUSTAINED THERMAL OR NO-THROTTLING EVIDENCE

GPU benchmark
→ NOT PERFORMED

bounded CPU feasibility for FS-020 UAT-4
→ SUFFICIENT_WITH_DECLARED_LIMITS
```

This evidence closes the bounded CPU feasibility gate for V2R only. It does not authenticate the original V2, promise UAT-4 duration, establish sustained thermal behavior or compare CPU with GPU.

# 23. Corrected reference execution scope

The executed V2R host gate was restricted to:

```text
local MARKET_CONSENSUS + MODAL_ALL technical stream
× exact seven CURRENT Capital configs
× synthetic candidate-independent outcomes
```

It executed only:

```text
scalar exactness
invariants
120m / 130m / 150m technical smoke
parallel exactness
shard equivalence
shard restart/recompute
bounded throughput
bounded process RSS and CPU temperature snapshots
arithmetic full-workload projection
```

It explicitly does **not** execute:

```text
cumulative 231 paths as an election family
economic TOTAL_RETURN comparison
bootstrap economic tournament
provider calls
DB reads/writes
GLOBAL_CAPITAL_V1 selection
GLOBAL_STRATEGY_V1 selection
GPU comparison
```

# 24. Original host evidence retained, not authoritative

Original host facts remain useful as historical context only:

```text
CPU → Intel i9-12900KF
RAM → ~31 GiB
GPU → RTX 4080 SUPER class
V1 thermal throttling observed → NO
```

They do not close V2 feasibility.

# 25. Reconciled feasibility classification

The V2R substitution is accepted for FS-020 because artifact integrity, independent semantic conformance, implementation equivalence, scalar/lag exactness, invariants, parallel exactness, shard equivalence and restart/recompute all pass. Thermal and resource evidence is explicitly bounded rather than overstated.

```text
classification
→ SUFFICIENT_WITH_DECLARED_LIMITS

original published V2
→ NOT AUTHENTICATED

sustained thermal behavior
→ NOT ESTABLISHED

aggregate worker memory maximum
→ NOT ESTABLISHED

GPU comparison
→ NOT PERFORMED

UAT-4 duration
→ NOT PROMISED
```

---

---

# 26. Storage strategy

Candidate×replicate scores:

```text
one design × one lag float64
→ 9.24 MB

nine design-lag cells
→ 83.16 MB
```

Do not materialize:

```text
pair × replicate tensor
```

Use:

```text
candidate×replicate score matrix
+
chunked/streamed pairwise differences
+
compact pairwise summaries
```

Storage and RAM are not current blockers.

---

# 27. Candidate reduction

No economic score-based reduction is permitted.

Allowed only:

```text
semantic incompatibility
irrecoverable structural input failure
exact behavioral equivalence
predeclared scientific-design exclusion
```

Phase 3 found:

```text
33 unique P×D Capital-input streams
```

Therefore:

```text
no behavioral compression
```

If implementation later becomes physically infeasible despite principled optimization:

```text
BLOCK / DEFER
```

not top-N pruning.

---

# 28. Exploratory / confirmatory boundary

A future implementation ticket may calculate descriptive observed scores, but those scores may not change:

```text
candidate family
eligibility
Capital configs
common cohort
metric
multiplicity
stability
fallback
settlement-lag contract
bootstrap geometry
```

The confirmatory family remains preregistered.

---

# 29. Output authorities

Local output:

```text
GLOBAL_CAPITAL_V1
or
NO_PROMOTION
```

Cumulative output:

```text
GLOBAL_STRATEGY_V1
or
NO_PROMOTION
```

Both outputs must preserve:

```text
scientific disposition
product fallback disposition
risk gate
lineage/spec/run/cohort/input hashes
settlement signatures
bootstrap/inference identities
```

Integrated promotion must not rewrite local Prediction/Decision/Capital authorities.

---

# 30. Packaging recommendation to F008

E2 research recommendation:

```text
separate, explicitly linked implementation/election tickets
```

Conceptual package A:

```text
Capital-local
→ implements authoritative Event-Time Experiment Lab runner
→ executes local 7-arm election
→ GLOBAL_CAPITAL_V1 or NO_PROMOTION
```

Conceptual package B:

```text
cumulative Strategy
→ reuses the same exact runner
→ restores/authenticates FS-018 retained alternatives
→ binds 33 P×D streams
→ executes 231-arm cumulative election
→ GLOBAL_STRATEGY_V1 or NO_PROMOTION
```

Package B must not restrict Capital to `GLOBAL_CAPITAL_V1`.

Final split/merge decision belongs to F008.

No ticket ID is assigned by E2.

---

# 31. Automatic-usability implication

No result from E2 changes live operational routing.

Any eventual baseline promotion is a research authority artifact.

Automatic runtime activation, if ever desired, requires a separate approved product/runtime contract.

Real betting remains forbidden.

---

# 32. Null / negative findings

```text
current studies._run_path
→ insufficient for authoritative E2 Event-Time election

behavioral equivalence compression across 33 P×D
→ none

GPU acceleration
→ historical V1 finding only
→ V2R GPU benchmark not performed

DB
→ not required for upstream binding

provider reacquisition
→ not required

economic Capital tournament
→ not run in research

GLOBAL_CAPITAL_V1
→ not selected

GLOBAL_STRATEGY_V1
→ not selected
```

---

# 33. F010 / F008 handoff after E2.4 targeted correction

```text
RESEARCH OUTCOME

Unchanged/frozen:
- seven CURRENT Capital configs / parameters / max_lanes
- 100u
- TOTAL_RETURN
- risk semantics
- 120m / 130m / 150m settlement contract
- 1w / 2w / 4w bootstrap
- 5000 replicates / PCG64 seeds
- all-pairs max-t family
- chronological halves
- leave-one-competition-out
- FLAT_UNIT fallback philosophy
- local vs cumulative authority separation
- 33×7 cumulative conceptual family
- candidate-reduction rules
- opportunity-cost role

Corrected:
- Event-Time reference lane-before-policy.request precedence
- semantic-conformance acceptance gate
- final research transport of complete se==0 rule
- final research transport of complete SETTLEMENT_SIGNATURE_x and cross-lag precedence

Original reference:
- preserved as HIGH-severity incident evidence
- cryptographically intact
- semantically nonconformant
- not authoritative

Published V2:
- E2_PHASE3_EVENT_TIME_REFERENCE_V2_LANE_FIRST
- declared SHA preserved
- executable not recovered/authenticated

Accepted reconstructed reference:
- E2_PHASE3_EVENT_TIME_REFERENCE_V2R_LANE_FIRST
- distinct SHA and durable manifest
- gates A/B/C PASS
- bounded parallel/shard/restart gate PASS
- CPU feasibility SUFFICIENT_WITH_DECLARED_LIMITS

Still required:
- independent pre-UAT review
- UAT-4 economic election once, after a new spec binds the final research hash
- no claim that the missing V2 executable was verified

Ticket state:
→ READY_FOR_UAT4

F008 must rerun DoR after corrected final evidence is supplied.
F009 preflight must separately record INPUT/ARTIFACT_INTEGRITY_PASS and SEMANTIC_CONFORMANCE_PASS.
Codex must not be constrained by an executable reference unless both gates passed.
```

Process lesson to project sources after this targeted research closes:

```text
F010
→ reference artifact identity does not establish correctness
→ final research must transport implementation-critical executable rules in full

F008
→ DoR for executable reference packages requires provenance + semantic oracle/fixtures + complete rule transport

F009
→ preflight separates artifact integrity from semantic conformance
```

---

# 34. Final reconciled E2.4 status

```text
E2 Phase 1/2 and E2.1/E2.2/E2.3
→ CLOSED

E2.4 targeted semantic correction
→ CLOSED VIA V2R RECONCILIATION

upstream binding
→ CLOSED

old Phase-3 V1 reference
→ PRESERVED
→ SEMANTICALLY_INVALID_AS_AUTHORITY

published V2 reference
→ E2_PHASE3_EVENT_TIME_REFERENCE_V2_LANE_FIRST
→ DECLARED SHA PRESERVED
→ EXECUTABLE NOT RECOVERED OR AUTHENTICATED

accepted reconstructed reference
→ E2_PHASE3_EVENT_TIME_REFERENCE_V2R_LANE_FIRST
→ ARTIFACT_INTEGRITY PASS
→ SEMANTIC_CONFORMANCE 12/12 PASS
→ IMPLEMENTATION_EQUIVALENCE 21/21 PASS

bounded V2R CPU feasibility
→ SUFFICIENT_WITH_DECLARED_LIMITS

FS-020
→ READY_FOR_UAT4

GLOBAL_CAPITAL_V1
→ NOT_SELECTED

GLOBAL_STRATEGY_V1
→ NOT_SELECTED

economic Capital tournament
→ NOT EXECUTED
```

V2R is an accepted, distinctly versioned reconstruction for FS-020; it is not the unrecovered V2 executable. UAT-4 must freeze a new spec only after this document is final and must bind the resulting byte SHA-256.

---

# 35. E2.4 V2R reconciliation addendum — 2026-09-23

This addendum supersedes earlier pending-host wording in sections 21–25 and 33 without changing the frozen methodology. It does not rewrite the historical V1 or published V2 identities.

Three independent gates were verified:

```text
GATE A — ARTIFACT_INTEGRITY
→ V1 exact SHA verified and preserved as incident evidence
→ V2 declared SHA preserved; executable NOT AUTHENTICATED
→ V2R exact SHA verified under a new reference identity
→ FS-019 gzip SHA and 1906-row binding verified
→ host manifest and two-shard cache SHA/dimensions cross-verified

GATE B — SEMANTIC_CONFORMANCE
→ independent V2R harness
→ C01–C12 = 12/12 PASS
→ product runner was not used as the V2R oracle

GATE C — IMPLEMENTATION_EQUIVALENCE
→ V2R versus FS-020 implementation
→ full authenticated FS-019 corpus with candidate-independent synthetic outcomes
→ 7 configs × 3 lags = 21/21 PASS
```

The bounded resampled-block host gate is a fourth, separate diagnostic: 126/126 serial/parallel exact tasks with four workers; two shards of 63 tasks; shard readback and recomputation PASS; two samples per block length; 36 continuous Lima weeks with six empty weeks; frozen PCG64. It used no real outcomes and produced no economic selection.

The measured 9.866s serial and 2.600s parallel wall times apply only to that bounded gate. The 24647.5 CPU-second figure is arithmetic projection for 315000 paths, not an ETA or sustained-throughput guarantee. The 60796 KiB figure is process RSS, not aggregate worker maximum. Temperatures are two snapshots only. No GPU benchmark was performed.

Durable reference contract:

```text
external retention root
→ /home/ljarufe/Documents/finsport/FS-020_e2_4_v2r/

repo contract
→ docs/research/FS-020_e2_4_v2r_reconciliation.json

producer
→ FS-020 E2.4 V2R reconciliation pass

consumer
→ FS-020 local Capital UAT-4 and final audit

deletion condition
→ only after FS-020 closes, durable final authority is verified, and no declared audit consumer remains
```

No existing FS-020 spec was found. Because `CapitalSpec` binds the byte SHA of this document, UAT-4 must create a new immutable spec after this addendum and must never reuse a spec tied to the pre-addendum SHA `d9a5179a011f4a8cfbc3330829f70c36230b0677c9259789575ca2ecd82e6c48`. No spec, run or promotion was created during reconciliation.

Safety result:

```text
provider calls → 0
DB reads/writes → 0
real outcomes in technical gates → 0
economic election → NOT EXECUTED
automatic routing → UNCHANGED
```
