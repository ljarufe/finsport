# Finsport E1 — Global Decision Baseline Methodology

**Research ID:** `E1`
**Layer:** `Decision`
**Status:** `CLOSED`
**Latest corrective pass:** `E1.2 — Fallback Determinism Precision`
**FS-019 disposition:** `READY_FOR_TICKET`
**Date:** `2026-09-19`
**Durable target:** `docs/research/FS-019_global_decision_methodology_research.md`
**Upstream baseline:** `GLOBAL_PREDICTION_V1 = MARKET_CONSENSUS / fs013-market-consensus-v2`
**Important boundary:** this research does **not** select `GLOBAL_DECISION_V1`.

---

# PHASE 3 — FS-018 BINDING / FEASIBILITY

## A. Frozen upstream Prediction identity

Physical binding against the final FS-018 promotion JSON and final immutable run succeeded.

```text
master merge commit
→ 2291648cfe656aaa49157d1d5b7c3aef7312f97b

baseline
→ GLOBAL_PREDICTION_V1

model_code
→ MARKET_CONSENSUS

model_version
→ fs013-market-consensus-v2

config_identity
→ c35e58fb446145fa698d4d122b1ddbb0e9e213dee4b1d04a756232979bb5ff7b

selection disposition
→ CLEAR_SUPERIORITY

selection policy
→ PAIRED_COMMON_EQUAL_LEAGUE_LOG_LOSS_V1

selection basis
→ LOWEST_EQUAL_LEAGUE_COMMON_LOG_LOSS

experiment spec
→ de5dc600168fd249f93848e9ca3d550b0de05eed07824f9874bf5fec68d4f9d0

source acquisition
→ 55e2c9682f20d229b3ca67a102d4c084c581f33686fea094139333e041838b81

execution runtime identity
→ 7cbeae3db86c33001e5c82f8aa66d9619a54be247569ec5abddf465730e09cd3

analysis identity
→ 15f313269bf23ed189ff3e50599b0b30785c23b61a1c361a7a7816f691a8ccc8

final run
→ b41fd8a324f4fd0265c8a9d43a1308dc21f5b862d45f6583b3a75542df5c711b

manifest hash
→ 3339a7f8247feee99e232d94be109cb32424234661bf1a7c6c2179b4db82c61e

Prediction cohort hash
→ 08d8f7c2852444c2e66ed28c4075e2bc51708d3ac918cdb7cf75daf858ae2c1c

data cutoff
→ 2026-09-19T03:17:33.457781+00:00
```

The supplied Phase-3 bundle was SHA-256 verified file by file against its inventory. The run hash,
manifest hash, spec identity and promotion references also recompute correctly from the supplied bytes.
FS-019 therefore has an immutable upstream anchor and must consume it rather than re-running or
retuning Prediction.

## B. Frozen Decision candidate matrix

The conditional branch is resolved by the actual upstream winner.

```text
GLOBAL_PREDICTION_V1 == MARKET_CONSENSUS
```

Therefore the FS-019 matrix is exactly six candidates:

| # | Policy | Version | Variant |
|---:|---|---|---:|
| 1 | `MODAL_ALL` | `fs003-modal-all-v1` | — |
| 2 | `SELECTIVE_CONFIDENCE` | `fs003-selective-confidence-v1` | `0.40` |
| 3 | `SELECTIVE_CONFIDENCE` | `fs003-selective-confidence-v1` | `0.45` |
| 4 | `SELECTIVE_CONFIDENCE` | `fs003-selective-confidence-v1` | `0.50` |
| 5 | `SELECTIVE_CONFIDENCE` | `fs003-selective-confidence-v1` | `0.55` |
| 6 | `SELECTIVE_CONFIDENCE` | `fs003-selective-confidence-v1` | `0.60` |

The three `VALUE / fs003-value-v1` variants (`0.00`, `0.02`, `0.05`) are **INELIGIBLE** under the
CURRENT contract. FS-019 must not reintroduce them or create a replacement market-relative policy.

## C. Decision opportunity universe

FS-018 exposes 2,476 target rows for each model in the materialized per-Match view, of which 2,474 are
canonical eligible FT targets. The selected Market baseline has exactly:

```text
PREDICTION_NATURAL = 1,906
```

Every one of those 1,906 rows was physically validated to have:

- `status = PRODUCED`;
- valid `p_home/p_draw/p_away` summing to one;
- canonical regulation-time outcome `HOME/DRAW/AWAY`;
- at least two complete bookmakers;
- complete raw decimal `HOME/DRAW/AWAY` triplets with all prices `> 1`;
- selected quote timestamps at or before kickoff minus 30 minutes;
- provider fixture identity;
- non-empty FS-018 raw-cache hash;
- `ODDSPAPI_RECONSTRUCTED_T30_V1` evidence profile.

Therefore:

```text
DECISION_COMMON = 1,906
PREDICTION_NATURAL -> DECISION_COMMON exclusions = 0
price coverage inside DECISION_COMMON = 100%
```

Per-league counts are:

| Competition | Eligible FT targets | PREDICTION_NATURAL | DECISION_COMMON | Prediction→Decision excluded |
|---:|---:|---:|---:|---:|
| 1270 | 202 | 144 | 144 | 0 |
| 1272 | 273 | 160 | 160 | 0 |
| 1273 | 235 | 191 | 191 | 0 |
| 1274 | 204 | 177 | 177 | 0 |
| 1275 | 255 | 216 | 216 | 0 |
| 1276 | 209 | 188 | 188 | 0 |
| 1277 | 222 | 132 | 132 | 0 |
| 1278 | 269 | 241 | 241 | 0 |
| 1325 | 205 | 163 | 163 | 0 |
| 1459 | 400 | 294 | 294 | 0 |
| **Total** | **2,474** | **1,906** | **1,906** | **0** |

For context only, upstream Market unavailability among the 2,476 materialized targets is:

```text
NO_MAPPED_HISTORICAL_EVIDENCE   387
FEWER_THAN_TWO_COMPLETE_BOOKS   111
NOT_FOUND                        70
NOT_CANONICAL_FT_WITH_VALID_SCORE 2
```

These are upstream Prediction exclusions, not Decision `NO_BET` rows.

## D. Price evidence coverage

The Phase-3 bundle proves that FS-018 retained sufficient derived evidence; raw provider reacquisition
is not required.

Inside the 1,906 Decision-common opportunities:

```text
2 complete books → 299 matches  (15.69%)
3 complete books → 1,607 matches (84.31%)
```

The earlier checkpoint concern about one-book-only price evidence is now closed. The acquisition has
111 one-complete-book cases, but the selected Market Prediction requires `>=2` complete books, so all
111 are outside `PREDICTION_NATURAL` and therefore outside FS-019.

FS-018 retains per usable bookmaker:

```text
Pinnacle / Bet365 / Unibet
raw HOME/DRAW/AWAY decimal prices
selected quote timestamp for each leg
quote age / seconds before cutoff
bookmaker identity
provider fixture identity
evidence_id in acquisition/run evidence
raw_cache_hash in materialized per-Match evidence
```

For each Decision outcome FS-019 must derive:

```text
research execution price
= maximum raw decimal price among usable complete books
```

The payout price is never de-vigged.

Physical quote-age diagnostics over the selected Market natural corpus:

| Diagnostic | Value |
|---|---:|
| Underlying usable bookmaker/outcome legs | 16,257 |
| Underlying-leg median age | 2,800.606 s = 46.68 min |
| Underlying-leg p95 age | 477,330.689 s = 5.52 days |
| Underlying-leg maximum age | 1,439,966.198 s = 16.67 days |
| Best-price outcome legs | 5,718 |
| Best-price median age | 2,373.212 s = 39.55 min |
| Best-price p95 age | 481,233.941 s = 5.57 days |
| Best-price maximum age | 1,279,908.739 s = 14.81 days |

Best-price age buckets are diagnostic only:

```text
<= 60m      4,148 / 5,718 = 72.54%
60m–6h        728 / 5,718 = 12.73%
6h–24h        280 / 5,718 =  4.90%
1d–7d         358 / 5,718 =  6.26%
>7d           204 / 5,718 =  3.57%
```

The long tail does not violate the frozen contract: FS-018's rule is latest active valid state at or
before T-30 and E1 did not define a maximum quote-age freshness ceiling. FS-019 must nevertheless
report quote-age distribution so this limitation remains visible.

There are 294 outcome-level ties for the maximum raw price across books. They do not change price,
EV or fixed-unit reward. For deterministic provenance FS-019 should preserve the set of co-best books
and, where a single representative field is required, use the frozen bookmaker order
`pinnacle -> bet365 -> unibet`. This is a provenance rule, not a Decision-performance rule.

## E. MARKET_CONSENSUS × VALUE disposition

Closed definitively:

```text
MARKET_CONSENSUS × VALUE
→ CURRENT VALUE variants INELIGIBLE
```

No further circularity research is needed for FS-019. A future market-relative/value family with an
independent execution-price contract would be a new challenger and a new ticket/version.

## F. Metric/sample feasibility

The closed Phase-2 methodology is feasible on the actual corpus:

- 1,906 common economic opportunities globally;
- non-empty common stratum in all ten enabled leagues;
- 229 `Competition × Lima-week` blocks;
- per-league block counts between 20 and 27;
- equal-league aggregation is fully defined;
- all six candidates have `POLICY_NATURAL = 1,906` under the selected upstream model;
- every BET action can be assigned a raw pre-cutoff payout price;
- canonical regulation-time outcome is present for every common row.

Actual deterministic action counts, computed without calculating a final economic ranking:

| Candidate | BET N | BET rate | NO_BET N | HOME | DRAW | AWAY |
|---|---:|---:|---:|---:|---:|---:|
| `MODAL_ALL` | 1,906 | 100.00% | 0 | 1,295 | 23 | 588 |
| `SELECTIVE 0.40` | 1,507 | 79.07% | 399 | 1,084 | 2 | 421 |
| `SELECTIVE 0.45` | 1,141 | 59.86% | 765 | 823 | 0 | 318 |
| `SELECTIVE 0.50` | 862 | 45.23% | 1,044 | 624 | 0 | 238 |
| `SELECTIVE 0.55` | 650 | 34.10% | 1,256 | 472 | 0 | 178 |
| `SELECTIVE 0.60` | 450 | 23.61% | 1,456 | 337 | 0 | 113 |

All Selective `NO_BET` rows have the CURRENT reason `BELOW_CONFIDENCE_THRESHOLD`. There is no missing
price-induced Decision abstention in this six-candidate matrix because Decision-common price coverage
is complete.

## G. Pilot result

A bounded technical pilot was executed only to validate the replay contract; it did **not** execute or
report the final FS-019 policy tournament.

Validation performed:

```text
full deterministic action expansion
→ 1,906 opportunities × 6 candidates = 11,436 Decision rows
→ PASS

price selection
→ maximum raw outcome price among complete books
→ PASS

20-match stratified settlement slice
→ 2 matches from each of 10 competitions
→ 120 policy rows
→ BET rows resolved exactly as +(odds-1) / -1
→ NO_BET rows resolved as 0
→ PASS

full cohort bootstrap geometry
→ 10 Competition strata
→ 229 Competition×Lima-week blocks
→ 5,000 paired replicates
→ simultaneous top-vs-all machinery executed with zero/dummy reward vectors
→ PASS

leave-one-league geometry
→ every leave-one-out universe non-empty
→ PASS

chronological-half geometry
→ source rows = selected `MARKET_CONSENSUS` rows with `NATURAL = true`
→ sort key = `(kickoff_utc_instant ASC, match_id ASC)`
→ no local-day bucketing for this split
→ split index = `floor(1,906 / 2) = 953`
→ first half = positions `[0, 953)`
→ second half = positions `[953, 1,906)`
→ 953 / 953 opportunities
→ boundary observed in the Phase-3 pilot: `2026-04-17T18:45:00+00:00 / match 23490` then `2026-04-17T19:45:00+00:00 / match 38695`
→ PASS
```

FS-019 must reuse this exact chronological-half definition. All retained FS-018 kickoff values in the
1,906-row corpus are timezone-aware `+00:00`; implementation must nevertheless parse them as instants
and normalize to UTC before sorting. Equal kickoff instants are broken only by ascending canonical
`match_id`; a tied kickoff never causes a group-preserving shift of the split index.

No full actual reward bootstrap, primary policy ranking, simultaneous superiority result or
`GLOBAL_DECISION_V1` selection was produced in Phase 3.

## H. Resource estimate

FS-018's final full Prediction analysis recorded:

```text
analysis time    408.184 s
process RSS HWM  347.809 MiB
```

Most of that cost came from sporting-model replay:

```text
DIXON_COLES             162.272 s
INDEPENDENT_POISSON     203.063 s
ELO_MULTINOMIAL_LOGIT    36.731 s
MARKET_CONSENSUS           0.006 s
```

FS-019 must not rerun those Prediction models.

Measured Decision-only feasibility pilot in this research environment:

```text
load 1,906 selected per-match rows       ~0.089 s
action-expand 11,436 candidate rows      ~0.066 s
serialize representative gzip artifact   ~0.115 s
5,000-replicate full block geometry      ~0.059 s
whole pilot process wall time             ~0.89 s
process max RSS                           ~124.4 MiB
```

A representative intended per-policy artifact with upstream lineage and selected-price provenance
compressed to approximately `480,886 bytes` for all 11,436 rows before summaries/reports. The lighter
pilot schema compressed to approximately `237 KB`.

Engineering expectation for FS-019:

```text
Decision computation
→ seconds, not minutes

memory
→ comfortably below the FS-018 full Prediction replay high-water mark

new Decision artifacts
→ low single-digit MiB expected if upstream run data are referenced rather than duplicated
```

F009 preflight should measure actual dev-container values, but there is no resource reason to block the
ticket.

## I. Remaining blockers

```text
NONE MATERIAL
```

Implementation-only facts for FS-019 preflight remain:

1. verify the local final FS-018 run artifact is still readable;
2. verify its `run_id/spec_id/manifest_hash` against the committed promotion JSON before use;
3. freeze a Decision-layer input snapshot so later FS-018 tmp cleanup cannot alter the study;
4. implement deterministic co-best bookmaker provenance;
5. run normal repository/UAT resource measurement in the real `finsport-dev` environment.

These are ticket/preflight duties, not unresolved E1 research.

## J. FS-019 readiness

```text
Research E1
→ CLOSED

FS_019
→ READY_FOR_TICKET

GLOBAL_DECISION_V1
→ NOT_SELECTED_IN_E1
```

---

## 1. Executive conclusion

E1 is complete. FS-018 has frozen `GLOBAL_PREDICTION_V1` as
`MARKET_CONSENSUS / fs013-market-consensus-v2`, and the final run contains sufficient immutable
per-Match probability, settlement and historical bookmaker evidence to execute the Decision study
without new Prediction work or provider reacquisition.

The final FS-019 candidate set is six CURRENT policies: `MODAL_ALL` plus five
`SELECTIVE_CONFIDENCE` thresholds from 0.40 through 0.60. `VALUE` is ineligible because the upstream
Prediction is Market Consensus and CURRENT Finsport explicitly suppresses VALUE for that model.

The historical Decision opportunity universe is physically closed at 1,906 Matches. All 1,906 have
complete pre-T30 best-price vectors and canonical regulation-time outcomes, so
`DECISION_COMMON = PREDICTION_NATURAL = 1,906`, with non-empty support in every one of the ten enabled
leagues. No additional OddsPapi acquisition is needed.

FS-019 can therefore be ticketed as an Experiment Lab Decision extension. It should consume the
immutable FS-018 baseline, replay only the six Decision policies, calculate fixed-unit economic reward,
apply equal-league common-opportunity comparison with paired weekly bootstrap and simultaneous
selection guard, and then—only in FS-019—promote one `GLOBAL_DECISION_V1` when the frozen scientific
disposition permits promotion; `INSUFFICIENT_EVIDENCE` explicitly produces `NO_PROMOTION`.

## 2. Decision enabled

FS-019 is enabled to answer one question:

```text
Given the frozen GLOBAL_PREDICTION_V1 probability vector for each legitimate opportunity,
which existing CURRENT Decision policy should become the single global Decision baseline?
```

The changed layer is only `Decision`.

It may output:

```text
BET HOME
BET DRAW
BET AWAY
NO_BET
```

The neutral 1u normalization exists only to compare Decision quality. Stake optimization, bankroll,
capacity, lanes, Kelly/recovery and opportunity-cost benchmarking remain Capital concerns.

## 3. Frozen upstream GLOBAL_PREDICTION_V1

Machine authority:

```text
docs/research/FS-018_global_prediction_v1.json
```

Bound baseline:

```text
GLOBAL_PREDICTION_V1
→ MARKET_CONSENSUS
→ fs013-market-consensus-v2
→ CLEAR_SUPERIORITY
```

Effective Market config:

```text
bookmakers
→ pinnacle / bet365 / unibet

market
→ canonical Full Time Result / 1X2

de-vig
→ multiplicative per bookmaker

consensus
→ equal-weight arithmetic mean

historical cutoff
→ latest active valid quote state <= canonical kickoff - 30m

minimum complete books for legitimate selected Prediction
→ 2

evidence profile
→ ODDSPAPI_RECONSTRUCTED_T30_V1
```

FS-019 must not fit, re-run, retune, reweight or re-elect Prediction. Its Prediction adapter is an
immutable reader of the selected FS-018 per-Match evidence.

The exact input path should be resolved from the promotion record/run lineage, then verified before a
Decision input snapshot is frozen. The convenient FS-018 materialized view is `per_match.jsonl.gz`;
the full `run.json`/acquisition evidence remains the source for evidence IDs and integrity checks.

## 4. CURRENT Decision candidate inventory

Final eligible matrix:

```text
MODAL_ALL
→ fs003-modal-all-v1
→ one candidate

SELECTIVE_CONFIDENCE
→ fs003-selective-confidence-v1
→ thresholds 0.40 / 0.45 / 0.50 / 0.55 / 0.60
→ five candidates

TOTAL
→ 6 candidates
```

Explicitly ineligible:

```text
VALUE fs003-value-v1 0.00
VALUE fs003-value-v1 0.02
VALUE fs003-value-v1 0.05
```

No threshold interpolation, local tuning or league-specific variant is permitted.

## 5. Policy semantics

### MODAL_ALL

For a valid upstream probability vector:

```text
action = argmax(p_home, p_draw, p_away)
```

Tie priority inherited from `OUTCOMES = (HOME, DRAW, AWAY)`:

```text
HOME > DRAW > AWAY
```

It always BETs on `DECISION_COMMON`.

### SELECTIVE_CONFIDENCE

For threshold `t`:

```text
outcome = argmax probabilities
confidence = P(outcome)

if confidence < t:
    NO_BET / BELOW_CONFIDENCE_THRESHOLD
else:
    BET outcome / CONFIDENCE_THRESHOLD_MET
```

Equality passes:

```text
confidence == t → BET
```

The action decision is price-independent, but historical economic evaluation uses the best valid raw
price for the chosen outcome.

### VALUE

CURRENT semantics remain documented but the family is not eligible in FS-019:

```text
EV(outcome) = P(outcome) * raw offered decimal price(outcome) - 1
```

CURRENT integrated orchestration does not create VALUE Decisions when the Prediction model is
`MARKET_CONSENSUS`. FS-019 must preserve that contract.

## 6. Decision opportunity/cohort contract

Three cohorts remain defined.

### PREDICTION_NATURAL

Every Match for which the immutable selected `GLOBAL_PREDICTION_V1` emitted a legitimate probability
vector under the frozen FS-018 contract.

Measured:

```text
PREDICTION_NATURAL N = 1,906
```

### DECISION_COMMON

Primary comparison cohort. Requires:

```text
PREDICTION_NATURAL membership
+
canonical regulation-time settlement
+
complete pre-cutoff raw HOME/DRAW/AWAY best-price vector
```

Measured:

```text
DECISION_COMMON N = 1,906
```

A complete three-outcome price vector is required for the common economic cohort even though
MODAL/Selective choose their action without price. This prevents action-dependent evidence missingness.

### POLICY_NATURAL

Conceptual policy applicability under CURRENT semantics. For the final six candidates and selected
Market upstream:

```text
POLICY_NATURAL N = 1,906 for every candidate
```

No upstream Prediction failure becomes a Decision `NO_BET`.

## 7. Historical price/evidence contract

Freeze for FS-019:

```text
provider evidence
→ retained FS-018 OddsPapi historical evidence

evidence profile
→ ODDSPAPI_RECONSTRUCTED_T30_V1

bookmakers
→ pinnacle / bet365 / unibet

market
→ Full Time Result / canonical 1X2

cutoff
→ canonical kickoff - 30 minutes

per bookmaker usable quote
→ latest active valid HOME/DRAW/AWAY state at or before cutoff
→ complete triplet required

Decision outcome price
→ maximum raw decimal price among usable complete books

payout/EV price treatment
→ RAW DECIMAL
→ NEVER DE-VIG
```

For exact reproducibility store or derive for each selected outcome:

```text
selected raw price
co-best bookmaker set
representative bookmaker
quote timestamp
quote age
provider fixture id
FS-018 evidence_id
raw_cache_hash
```

No post-T30 quote may repair missing pre-T30 evidence. No later closing/current quote may be
retrospectively substituted.

## 8. OddsPapi / existing price evidence reuse

Disposition:

```text
FS018_PRICE_EVIDENCE_REUSE
→ SUFFICIENT
```

The final FS-018 run and backfill checkpoint physically contain the per-book triplets, timestamps,
book counts, evidence IDs and hashes needed by FS-019. The materialized per-Match view contains the
same selected prices/timestamps/ages and hashes; a full cross-check over all 1,906 Market NATURAL rows
found no mismatch with the acquisition evidence.

Therefore:

```text
new OddsPapi provider calls
→ NOT REQUIRED

raw private cache access
→ NOT REQUIRED for normal replay

provider reacquisition
→ FORBIDDEN BY DEFAULT
```

If the original ignored FS-018 run directory is later removed, FS-019 must restore/use a verified copy
of those immutable artifacts or another hash-identical source; it must not silently reacquire current
provider history and call it the same corpus.

The former one-book concern is retired:

```text
one complete book only
→ 111 historical cases
→ selected Market Prediction unavailable
→ outside PREDICTION_NATURAL
→ irrelevant to FS-019 Decision baseline
```

## 9. MARKET_CONSENSUS × VALUE circularity disposition

Final disposition:

```text
MARKET_CONSENSUS_VALUE_CIRCULARITY
→ CLOSED

CURRENT implementation consequence
→ VALUE INELIGIBLE
```

Cross-book consensus probability versus best individual quote can mathematically produce positive
`p*o-1`; therefore this is not a claim that such EV is algebraically impossible. The exclusion is a
CURRENT product/policy contract already encoded by Finsport. E1 does not replace it with a new family.

## 10. Fixed-unit Decision normalization

For research comparison only:

```text
BET    → stake 1u
NO_BET → stake 0u
```

No compounding, bankroll state, lane capacity, Kelly fraction, recovery sequence, target-profit logic
or capital opportunity-cost benchmark enters Decision scoring.

This normalization isolates the consequence of choosing `BET/NO_BET` and `HOME/DRAW/AWAY`.

## 11. Settlement contract

Historical outcome authority is canonical regulation-time FT score/outcome.

Reward per common opportunity:

```text
BET + correct outcome
→ +(selected_raw_odds - 1)u

BET + wrong outcome
→ -1u

NO_BET
→ 0u

VOID / refund
→ 0u
```

The actual 1,906-row common corpus consists entirely of canonical FT Matches with valid regulation-time
scores/outcomes:

```text
HOME = 808
DRAW = 508
AWAY = 590
```

Therefore no historical VOID/refund row exists in this exact cohort. The zero-return VOID/refund branch
remains a defensive settlement contract and must have an explicit unit test in FS-019; its absence from
this corpus is not a blocker.

A 20-Match stratified technical slice successfully applied the BET-win, BET-loss and NO_BET formulas
across 120 policy rows.

## 12. Primary Decision metrics

Primary selection statistic:

```text
PRIMARY_DECISION_METRIC
= equal-league mean fixed-unit profit per DECISION_COMMON opportunity
```

For candidate `k`, Match `i`:

```text
r_ki = odds - 1   if BET and correct
r_ki = -1         if BET and wrong
r_ki = 0          if NO_BET
r_ki = 0          if VOID/refund
```

Per league:

```text
PPO_kl = mean(r_ki over DECISION_COMMON in league l)
```

Global:

```text
GLOBAL_PPO_k = (1/10) * sum_l(PPO_kl)
```

Higher is better.

The denominator is common opportunities, not bets. This prevents a highly selective policy from
improving its primary denominator merely by acting on a tiny lucky subset.

## 13. Secondary diagnostics

Mandatory global and per-league diagnostics:

```text
DECISION_COMMON N
PREDICTION_NATURAL N
POLICY_NATURAL N
BET N / rate
NO_BET N / rate / reasons
HOME / DRAW / AWAY action distribution
hit rate
total fixed-unit P&L
yield / ROI per unit staked
mean / median selected raw odds
mean model probability on BET actions
price coverage
usable bookmaker-count distribution
quote-age distribution
failure / unavailable counts
monthly/time-slice P&L
selected-subset log-loss / Brier as diagnostics only
losing streak diagnostics
pooled match-weighted PPO as secondary only
```

For this six-candidate matrix there is no VALUE EV diagnostic because VALUE is ineligible. Current
MODAL/Selective may still retain `expected_value = p(action)*price-1` as audit metadata; it is not a
selection criterion.

If `BET_N = 0` in any slice:

```text
yield = UNDEFINED
```

not zero.

## 14. Coverage/selectivity/sample guardrails

No arbitrary universal `BET_N >= X` threshold is introduced.

Hard gates:

1. candidate semantics must be exactly CURRENT/frozen;
2. `DECISION_COMMON` must be non-empty in all ten leagues;
3. reward must not depend on post-cutoff evidence;
4. paired uncertainty must be estimable across more than one non-zero-difference
   `Competition × Lima-week` block for any claimed superiority;
5. the frozen stability rule below must be evaluable and must pass before `CLEAR_SUPERIORITY` can be
   claimed.

### 14.1 Frozen stability candidate pair

Let `T` be the **observed provisional top** on the full 1,906-row `DECISION_COMMON` corpus using the
primary `GLOBAL_PPO` score and the frozen candidate order only to break an exact numerical point-score
tie.

Let `R` be the **observed strongest alternative**, defined once from the full corpus as the highest
`GLOBAL_PPO` candidate among `candidate != T`, again using the frozen candidate order only for an exact
point-score tie. `R` is fixed before any sensitivity slice is evaluated; FS-019 must not choose a
different runner-up separately inside each leave-one-league-out or chronological-half slice.

The stability guard tests **only the predeclared pair `(T, R)`**. The separate simultaneous
top-vs-all guard in Section 16 remains responsible for all other competitors.

### 14.2 Leave-one-league-out stability

For each enabled league `l` in the frozen ten-league set, compute for candidate `c`:

```text
PPO_c,j = mean fixed-unit reward for candidate c on DECISION_COMMON opportunities in league j

GLOBAL_PPO_c^(-l)
= (1 / 9) * sum(PPO_c,j for every enabled league j != l)

DELTA_LOO_l
= GLOBAL_PPO_T^(-l) - GLOBAL_PPO_R^(-l)
```

Every retained league must have at least one `DECISION_COMMON` opportunity. If any required
leave-one-league-out score cannot be computed, scientific disposition is
`INSUFFICIENT_EVIDENCE`.

### 14.3 Chronological-half stability

Construct the chronological halves once from the entire 1,906-row Decision-common Match universe:

```text
rows = DECISION_COMMON Matches, one row per canonical Match
normalize kickoff to timezone-aware UTC instant
sort ascending by (kickoff_utc_instant, match_id)
N = 1,906
split_index = floor(N / 2) = 953
H1 = sorted rows[0:953]
H2 = sorted rows[953:1,906]
```

The Phase-3 pilot used exactly that algorithm and produced `953 / 953`. The split is global, not
per-league. `America/Lima` is **not** used for this split; Lima timezone remains relevant to the
weekly bootstrap block definition only. If two Matches have the same kickoff instant, ascending
`match_id` is the sole tie-break. Do not move same-kickoff Matches across the boundary as a group.

For `h in {H1, H2}` and each candidate `c`:

```text
PPO_c,l,h
= mean fixed-unit reward for candidate c on rows in half h and league l

GLOBAL_PPO_c^h
= (1 / 10) * sum(PPO_c,l,h over all ten enabled leagues)

DELTA_HALF_h
= GLOBAL_PPO_T^h - GLOBAL_PPO_R^h
```

A half must contain at least one `DECISION_COMMON` opportunity in every enabled league; otherwise
stability is not evaluable and scientific disposition is `INSUFFICIENT_EVIDENCE`. Phase 3 verified
that the current physical corpus satisfies this condition in both halves.

### 14.4 Exact stability disposition

Define the twelve sensitivity deltas:

```text
S = {DELTA_LOO_l for 10 leagues} union {DELTA_HALF_H1, DELTA_HALF_H2}
```

The word `materially` is removed. There is no tolerance, effect-size threshold, epsilon, rounding band
or practical-significance exception. Use full-precision computed deltas before report rounding.

```text
if any required sensitivity score is not computable:
    stability = INSUFFICIENT_EVIDENCE

elif any delta in S < 0:
    stability = UNSTABLE

elif any delta in S == 0:
    stability = NON_STRICT
    # scientific disposition cannot be CLEAR_SUPERIORITY; use NO_CLEAR_SUPERIORITY

else:  # every delta > 0
    stability = PASS
```

Thus **delta = 0 is not a reversal, but it is not a stability PASS**. It maps to
`NO_CLEAR_SUPERIORITY` provided no higher-precedence evidence failure exists. A strictly negative
delta maps to `UNSTABLE`.

Every yield/ROI presentation must carry:

```text
BET_N
BET_rate
DECISION_COMMON_N
league/time support
```

A sparse high-yield candidate cannot be presented as strong without its coverage denominator.

## 15. Global aggregation

Primary aggregation remains equal-league:

```text
GLOBAL_PPO = arithmetic mean of the ten league PPO values
```

Each enabled league receives equal weight regardless of Match count.

Pooled match-weighted metrics remain secondary diagnostics.

If a future run has zero common opportunities in any required league:

```text
global ten-league Decision comparison
→ INSUFFICIENT_EVIDENCE
```

Do not renormalize over nine leagues and label it global ten-league evidence.

The current physical corpus passes this gate.

## 16. Pairwise uncertainty and simultaneous top-vs-all guard

Reuse the FS-018 resampling geometry exactly:

```text
stratum
→ Competition

block
→ Competition × Lima ISO week

resampling
→ complete weekly blocks with replacement within Competition

replicates
→ 5,000

seed
→ literal integer 18092026

pairing
→ identical resampled Match opportunities and identical block draws for all six candidates
```

FS-019 must initialize the Decision bootstrap RNG as:

```python
rng = numpy.random.default_rng(18092026)
```

and must preserve the deterministic FS-018 iteration geometry: competitions in ascending numeric ID,
Lima ISO-week block IDs in ascending lexical order within each competition, and one draw matrix of
shape `(5000, number_of_blocks_in_that_competition)` shared by all candidates. The seed is part of the
frozen Decision `ExperimentSpec`; it is not derived from run IDs, wall-clock time or data hashes.

The current corpus has 229 blocks:

| Competition | Lima-week blocks |
|---:|---:|
| 1270 | 21 |
| 1272 | 24 |
| 1273 | 22 |
| 1274 | 20 |
| 1275 | 23 |
| 1276 | 22 |
| 1277 | 24 |
| 1278 | 24 |
| 1325 | 22 |
| 1459 | 27 |
| **Total** | **229** |

### 16.1 Observed scores and observed top

For candidate `c`, let:

```text
theta_c = observed GLOBAL_PPO_c
```

where `GLOBAL_PPO` is the equal-league primary metric defined in Section 15. Higher is better.

Define provisional top `T` as:

```text
T = argmax_c(theta_c)
```

with the frozen candidate order from Section 19 used only for an exact numerical tie in `theta`.
`T` is fixed from the observed corpus before bootstrap superiority is assessed.

For every competitor `c != T`, define the observed top-minus-competitor delta:

```text
d_c = theta_T - theta_c
```

### 16.2 Bootstrap replicate scores and deltas

For bootstrap replicate `b = 1..5000`, resample whole Lima-week blocks with replacement independently
inside each Competition, preserving the same sampled block indices for all six candidates. For each
candidate, league, and replicate:

```text
theta_c,l^(b)
= sum(reward for sampled blocks in league l)
  / sum(DECISION_COMMON opportunities for sampled blocks in league l)

theta_c^(b)
= (1 / 10) * sum(theta_c,l^(b) over the ten leagues)

delta_c^(b)
= theta_T^(b) - theta_c^(b)
```

A replicate with a zero denominator in any required league is invalid and must fail closed rather than
being silently dropped or renormalized. Under the frozen block design and current corpus every drawn
block contains at least one opportunity, so this is a structural assertion rather than an expected
normal path.

### 16.3 Centered adverse statistic

For each replicate and competitor define the unstudentized centered adverse error:

```text
a_b,c = d_c - delta_c^(b)
```

Positive `a_b,c` means the bootstrap replicate reduced the observed advantage of `T` over competitor
`c`. For each replicate take the worst competitor:

```text
M_b = max(a_b,c for every c != T)
```

This is the **maximum centered adverse deviation**. Do not studentize it, take absolute values, center
around the bootstrap mean, or recompute the top candidate inside a replicate.

### 16.4 Frozen 95% quantile convention

Sort the 5,000 values `M_b` ascending as zero-based array `M_sorted[0..4999]`. Use the same linear
quantile convention as `numpy.quantile(..., 0.95, method="linear")`:

```text
h = (B - 1) * 0.95
  = 4999 * 0.95
  = 4749.05

j = floor(h) = 4749
gamma = h - j = 0.05

q95 = (1 - gamma) * M_sorted[4749]
      + gamma * M_sorted[4750]
```

No nearest-rank, `higher`, `lower`, midpoint or alternative percentile convention is permitted for
this frozen Decision selection rule.

### 16.5 Simultaneous lower bounds

For each competitor `c != T`:

```text
SIMULTANEOUS_LB_c = d_c - q95
```

The simultaneous top-vs-all guard passes iff:

```text
SIMULTANEOUS_LB_c > 0
for every one of the five competitors c != T
```

`SIMULTANEOUS_LB_c == 0` does **not** pass. For fallback semantics, competitor `c` is **shown clearly
inferior to T** iff `SIMULTANEOUS_LB_c > 0`; it is **not shown clearly inferior** iff the bound is
`<= 0`.

### 16.6 Exact scientific disposition precedence

After the observed top and all required metrics are available:

```text
1. If a required cohort, league score, bootstrap quantity or stability quantity is not estimable, or a
   structural evidence defect exists:
       → INSUFFICIENT_EVIDENCE

2. Else if any frozen stability delta from Section 14 is < 0:
       → UNSTABLE

3. Else if every SIMULTANEOUS_LB_c > 0 AND every frozen stability delta > 0:
       → CLEAR_SUPERIORITY

4. Else:
       → NO_CLEAR_SUPERIORITY
```

This precedence means a zero stability delta or a zero simultaneous lower bound yields
`NO_CLEAR_SUPERIORITY`, while a genuine sign reversal in a stability slice yields `UNSTABLE`.

Phase 3 validated the full block/resampling geometry with dummy zero rewards only; no FS-019 economic
winner, observed `theta`, observed `d_c`, simultaneous lower bound or scientific disposition was
calculated.

## 17. Chronological evidence roles

The historical 2026 OddsPapi/FS-018 corpus has already participated in Prediction baseline selection.
FS-019 Decision results on the same period must therefore be labelled:

```text
BASELINE_ENGINEERING / DECISION_SELECTION_EVIDENCE
```

They are not untouched confirmatory evidence for the entire Prediction→Decision stack.

After `GLOBAL_DECISION_V1` is frozen, genuinely future Matches with pre-event evidence become the
prospective confirmation stream.

No retrospective odds repair or future-data leakage is permitted.

## 18. Multiple-threshold guard

Frozen grid:

```text
SELECTIVE_CONFIDENCE
→ 0.40 / 0.45 / 0.50 / 0.55 / 0.60
```

Rules:

```text
no interpolation
no second sweep around an apparent winner
no league-specific threshold
no threshold change after seeing FS-019 economics
no retuning and then calling the same historical corpus confirmation
```

All five thresholds are part of one predeclared six-candidate search and are covered by the
simultaneous bootstrap guard.

Any later threshold change creates a new Decision challenger/version and requires a new confirmation
window.

## 19. Global selection / tie / fallback rule

FS-019 must execute this sequence exactly.

### 19.1 Point estimate

Compute `GLOBAL_PPO` for all six eligible candidates on the identical `DECISION_COMMON` cohort.

Exact numerical ties use frozen order:

```text
1 MODAL_ALL
2 SELECTIVE_CONFIDENCE 0.40
3 SELECTIVE_CONFIDENCE 0.45
4 SELECTIVE_CONFIDENCE 0.50
5 SELECTIVE_CONFIDENCE 0.55
6 SELECTIVE_CONFIDENCE 0.60
```

### 19.2 Scientific disposition

```text
CLEAR_SUPERIORITY
```

only under the exact Section 16.6 precedence: every one of the five simultaneous lower bounds is
strictly `> 0`, every one of the twelve frozen stability deltas in Section 14 is strictly `> 0`, and
no structural/estimability defect exists.

Otherwise the scientific disposition is deterministically assigned by Section 16.6 as one of:

```text
NO_CLEAR_SUPERIORITY
UNSTABLE
INSUFFICIENT_EVIDENCE
```

### 19.3 Frozen survivor set

Let `T` be the observed provisional top already defined by Section 19.1: the candidate with highest
full-corpus `GLOBAL_PPO`, with exact numerical ties resolved by the frozen candidate order. Let `M` be
`MODAL_ALL`.

For every disposition in which the simultaneous quantities are estimable, define the survivor set
exactly as:

```text
S = {T} ∪ {c != T : SIMULTANEOUS_LB_c <= 0}
```

Therefore **`T` always belongs to `S` by definition**. No self-bound is computed for `T`. A competitor
with `SIMULTANEOUS_LB_c > 0` is excluded because it has been shown clearly inferior to `T` under the
frozen simultaneous guard. A competitor with bound `<= 0`, including an exact zero, survives.

For `MODAL_ALL` specifically:

```text
MODAL_SURVIVES = True                                  if T == M
MODAL_SURVIVES = (SIMULTANEOUS_LB_M <= 0)             if T != M
```

If a required bound is not estimable, Section 16.6 assigns `INSUFFICIENT_EVIDENCE`; the survivor set
is then not authoritative for promotion.

### 19.4 Scientific disposition versus permission to promote

The scientific label and engineering permission are separate and frozen as follows:

| Scientific disposition | Evidence interpretation | Fallback invoked? | Promotion permission |
|---|---|---:|---|
| `CLEAR_SUPERIORITY` | Full required evidence is estimable; `T` passes simultaneous and stability guards | No | **YES** — select/promote `T` directly |
| `NO_CLEAR_SUPERIORITY` | Full required evidence is estimable, but strict superiority is not demonstrated | Yes | **YES** — select one usable baseline by Section 19.5 |
| `UNSTABLE` | Full required evidence is estimable, but `T` reverses against the fixed runner-up in at least one frozen stability slice | Yes | **YES** — select one usable baseline by Section 19.5 while preserving the `UNSTABLE` scientific label |
| `INSUFFICIENT_EVIDENCE` | A required quantity/cohort is not estimable or a structural evidence defect exists | No | **NO** — `NO_PROMOTION`; do not create/update `GLOBAL_DECISION_V1` |

Thus lack of demonstrated superiority (`NO_CLEAR_SUPERIORITY`) or demonstrated instability with
otherwise complete evidence (`UNSTABLE`) may still yield a conservative usable baseline. Missing
required evidence, non-estimability or a structural evidence defect does **not**.

### 19.5 Deterministic usable-baseline fallback

Fallback is executed only for `NO_CLEAR_SUPERIORITY` or `UNSTABLE`. It uses no new fit, search,
threshold, metric or optimization criterion. It reuses only the already-computed full-corpus
`GLOBAL_PPO`, simultaneous bounds and frozen candidate order.

```text
INPUT:
    disposition
    observed GLOBAL_PPO for all six candidates
    T = observed top from Section 19.1
    simultaneous lower bounds for every c != T
    frozen candidate order

if disposition == CLEAR_SUPERIORITY:
    selected_usable_baseline = T
    promotion = YES

elif disposition == INSUFFICIENT_EVIDENCE:
    selected_usable_baseline = NONE
    promotion = NO_PROMOTION

else:  # disposition is NO_CLEAR_SUPERIORITY or UNSTABLE
    S = {T} union {c != T where SIMULTANEOUS_LB_c <= 0}

    if MODAL_ALL in S:
        selected_usable_baseline = MODAL_ALL
    else:
        selected_usable_baseline = argmax_{c in S}(GLOBAL_PPO_c)
        # exact numerical GLOBAL_PPO ties are resolved by frozen candidate order

    promotion = YES
```

Because `T` is the full-corpus `GLOBAL_PPO` argmax and `T ∈ S`, the second fallback branch is
deterministically equivalent, for the frozen six-candidate FS-019 matrix, to selecting `T` whenever
`MODAL_ALL` has been shown clearly inferior. Writing the `argmax` explicitly makes the rule complete
for every valid survivor set and removes any implementation discretion among multiple surviving
`SELECTIVE_CONFIDENCE` candidates with unequal point scores.

The fallback never changes the scientific disposition. A selected usable baseline under
`NO_CLEAR_SUPERIORITY` or `UNSTABLE` is an engineering baseline, not scientific proof that the
selected policy is superior.

### 19.6 Explicit truth table

Let `LB_M` mean `SIMULTANEOUS_LB_MODAL_ALL` when `T != MODAL_ALL`; when `T == MODAL_ALL`, `LB_M` is
`N/A` and `MODAL_ALL` survives by definition.

| Scientific disposition | `MODAL_ALL` condition | Survivor handling | Selected usable baseline | Promotion |
|---|---|---|---|---|
| `CLEAR_SUPERIORITY` | any / `N/A` | Not a fallback decision | `T` | YES |
| `NO_CLEAR_SUPERIORITY` | `T == MODAL_ALL` | `MODAL_ALL ∈ S` | `MODAL_ALL` | YES |
| `NO_CLEAR_SUPERIORITY` | `T != MODAL_ALL` and `LB_M <= 0` | `MODAL_ALL ∈ S` | `MODAL_ALL` | YES |
| `NO_CLEAR_SUPERIORITY` | `T != MODAL_ALL` and `LB_M > 0` | `S = {T} ∪ {c != T : LB_c <= 0}` | highest observed `GLOBAL_PPO` in `S`; frozen-order tie-break; therefore `T` | YES |
| `UNSTABLE` | `T == MODAL_ALL` | `MODAL_ALL ∈ S` | `MODAL_ALL` | YES |
| `UNSTABLE` | `T != MODAL_ALL` and `LB_M <= 0` | `MODAL_ALL ∈ S` | `MODAL_ALL` | YES |
| `UNSTABLE` | `T != MODAL_ALL` and `LB_M > 0` | `S = {T} ∪ {c != T : LB_c <= 0}` | highest observed `GLOBAL_PPO` in `S`; frozen-order tie-break; therefore `T` | YES |
| `INSUFFICIENT_EVIDENCE` | any, missing or non-estimable | Survivor set cannot authorize promotion | `NONE` | **NO_PROMOTION** |

There is no branch in which Codex may choose a different survivor for qualitative simplicity,
threshold conservatism or subjective preference.

## 20. Per-league reporting

FS-019 must publish, for every candidate and every competition:

```text
DECISION_COMMON N
BET / NO_BET counts and rates
NO_BET reasons
HOME / DRAW / AWAY counts
fixed-unit P&L
profit per opportunity
yield per unit staked
hit rate
selected-price distribution
bookmaker source distribution
quote-age distribution
time-slice diagnostics
```

Primary global selection remains one policy for all ten leagues. Per-league reports are evidence and
falsification diagnostics, not permission to route policies by league.

The physical Phase-3 cohort already satisfies non-empty support in all ten competitions.

## 21. Experiment Lab Decision extension

FS-019 must extend `football/experiments/`; do not create a second experimental framework.

Reuse unchanged concepts/machinery:

```text
ExperimentSpec / canonical identity hashing
immutable input snapshot
manifest/cohort identity
atomic artifact storage
execution-runtime provenance
COMMON/NATURAL cohort machinery
Competition × Lima-week blocking
paired bootstrap engine
lineage verification
materialized artifact/report machinery
promotion immutability pattern
```

The frozen Decision `ExperimentSpec` must include these selection-contract fields verbatim in
meaning (field names may follow repository schema conventions, but values/semantics may not change):

```text
bootstrap.replicates = 5000
bootstrap.seed = 18092026
bootstrap.rng = numpy.random.default_rng
bootstrap.stratum = Competition
bootstrap.block = Competition×Lima-ISO-week
bootstrap.quantile = 0.95
bootstrap.quantile_method = LINEAR_R7 / numpy.quantile(method="linear")
bootstrap.simultaneous_rule = MAX_CENTERED_ADVERSE_UNSTUDENTIZED_V1

stability.rule = STRICT_SIGN_TOP_VS_OBSERVED_RUNNER_UP_V1
stability.leave_one_league_out = all 10 omissions
stability.chronological_half.sort = kickoff_utc_instant ASC, match_id ASC
stability.chronological_half.split_index = floor(N / 2)
stability.zero_delta = NO_CLEAR_SUPERIORITY
stability.negative_delta = UNSTABLE

fallback.survivor_rule = T_ALWAYS_PLUS_COMPETITORS_WITH_SIMULTANEOUS_LB_LE_ZERO_V1
fallback.modal_rule = SELECT_MODAL_IF_SURVIVES
fallback.non_modal_rule = MAX_OBSERVED_GLOBAL_PPO_WITH_FROZEN_ORDER_TIEBREAK
fallback.allowed_dispositions = [NO_CLEAR_SUPERIORITY, UNSTABLE]
fallback.clear_superiority = SELECT_T_DIRECTLY
fallback.insufficient_evidence = NO_PROMOTION
```

These are frozen research inputs, not runtime defaults to be chosen by FS-019 implementation.

Add only Decision-specific pieces, conceptually:

```text
decision.py / policy runner
→ consumes immutable selected-Market per-Match rows
→ emits exact CURRENT policy action/reason

historical_prices.py / adapter
→ reads retained FS-018 evidence
→ verifies evidence_id/hash/profile/cutoff
→ constructs best raw outcome prices
→ retains co-best provenance

reward.py / metrics
→ fixed-unit per-opportunity reward
→ PPO / yield / selectivity diagnostics

comparison.py
→ equal-league Decision aggregation
→ paired reward bootstrap
→ simultaneous top-vs-all guard
→ stability/fallback disposition

artifacts/promotion extension
→ Decision run/report
→ GLOBAL_DECISION_V1 machine promotion
```

Recommended execution flow:

```text
1. Read committed FS-018 promotion JSON.
2. Resolve final upstream run and verify run/spec/manifest identities.
3. Freeze a Decision input snapshot containing only selected Market NATURAL rows plus required price
   evidence/provenance.
4. Hash that snapshot; all later FS-019 reruns use it.
5. Replay six policies only.
6. Calculate reward/metrics/uncertainty.
7. Produce immutable Decision run artifacts.
8. Promote GLOBAL_DECISION_V1 only after UAT/review.
```

The Decision input snapshot prevents later cleanup of FS-018 ignored `tmp/` evidence from changing an
already-started FS-019 run.

## 22. GLOBAL_DECISION lineage/version contract

FS-019's eventual machine promotion record should minimally bind:

```text
baseline = GLOBAL_DECISION_V1

upstream
→ GLOBAL_PREDICTION_V1
→ model_code/version/config identity
→ upstream experiment spec id
→ upstream run id
→ upstream manifest hash
→ upstream data cutoff

Decision
→ selected policy_code
→ policy_version
→ policy_variant
→ policy_config

Decision experiment
→ changed_layer = Decision
→ Decision spec id
→ Decision input snapshot hash
→ DECISION_COMMON cohort hash
→ Decision run id
→ execution-runtime identity
→ price evidence profile/contract identity
→ bootstrap/selection policy identity
→ selection disposition

references
→ E1 research artifact
→ FS-019 baseline report
```

A material change to policy semantics, threshold, price rule, cohort rule, settlement or selection rule
requires a new Decision version/spec/run and cannot overwrite the frozen baseline silently.

## 23. Prospective confirmation contract

After `GLOBAL_DECISION_V1` exists, preserve for each genuinely future Match:

```text
upstream Prediction model/version/config
prediction time and probability vector
Decision policy/version/config
decision time
action/reason
selected price evidence identity
bookmaker/co-best provenance
raw decimal odds
quote timestamp/age
model probability / expected-value audit field
canonical regulation-time outcome
fixed-unit research reward
missing/missed-evidence reason where applicable
```

Future confirmation uses evidence that actually existed before the Match. It must not reconstruct an
unplaced historical bet after downtime merely to make a prospective record look complete.

If Decision semantics are materially changed, subsequent data for the changed challenger starts a new
confirmation stream.

## 24. Capital handoff requirements

Decision hands Capital an immutable sequence of:

```text
Match
Decision action/reason
selected outcome
selected research/prospective price and provenance
Decision policy/version/config
upstream Prediction identity/probability
canonical result when known
```

Capital owns:

```text
stake sizing
bankroll evolution
lane/capacity policy
concurrency
Kelly/recovery variants
drawdown / ruin
capital utilization
opportunity-cost benchmark
execution-capacity effects
```

FS-019 must not use any Capital result to select the Decision baseline.

The later Capital experiment should consume `GLOBAL_PREDICTION_V1 + GLOBAL_DECISION_V1` as frozen
upstream inputs.

## 25. FS-019 scope

Expected ticket:

```text
FS-019 — Global Decision Baseline
```

Required scope:

1. verify/read `GLOBAL_PREDICTION_V1` machine authority;
2. verify/read the exact final FS-018 run/evidence;
3. create immutable Decision ExperimentSpec/input snapshot;
4. implement the historical best-price adapter over retained FS-018 evidence;
5. replay exactly six CURRENT Decision candidates;
6. materialize one Decision row per candidate/common Match;
7. calculate fixed-unit common-opportunity metrics;
8. report global/per-league/selectivity/price-age diagnostics;
9. execute paired 5,000-replicate weekly block bootstrap;
10. execute simultaneous top-vs-all and stability rules;
11. apply the frozen scientific disposition and fallback;
12. produce immutable run/report artifacts;
13. after independent UAT/review, promote exactly one `GLOBAL_DECISION_V1` machine record only when
    disposition is `CLEAR_SUPERIORITY`, `NO_CLEAR_SUPERIORITY` or `UNSTABLE`; for
    `INSUFFICIENT_EVIDENCE`, emit `NO_PROMOTION`;
14. make no provider call unless an unexpected physical artifact integrity failure is proven first.

FS-019 should require no new methodological research.

## 26. FS-019 explicit non-goals

FS-019 must not:

- re-select or retune Prediction;
- alter `GLOBAL_PREDICTION_V1`;
- add Decision families;
- add confidence thresholds;
- reintroduce VALUE under Market Consensus;
- optimize bookmaker weights;
- use post-T30 evidence;
- reacquire OddsPapi history by default;
- route policy by league;
- select or tune Capital;
- optimize stake size;
- simulate Kelly/recovery/lanes as Decision evidence;
- redesign frontend;
- add leagues;
- enable real betting;
- infer profitability from ROI alone;
- relabel historical evidence as prospective;
- run a second threshold sweep after seeing results.

## 27. Risks / falsification

The following remain visible and must stop/qualify FS-019 if encountered:

### Upstream artifact integrity

If the FS-018 run cannot be hash-verified against the committed promotion record, stop rather than
recompute Prediction silently.

### Price evidence integrity

If retained per-book evidence does not match the frozen T-30 profile/hash or cannot reconstruct the
same materialized prices, stop and classify the physical gap. Do not reacquire automatically.

### Quote staleness

The evidence has a material old-quote tail. This is not a contract violation, but FS-019 must expose
quote-age diagnostics and must not describe all T-30 evidence as freshly observed at T-30.

### Multiple-threshold/data-snooping risk

The five Selective thresholds are one frozen search. The simultaneous guard and future prospective
confirmation are required to avoid overstating a lucky historical optimum.

### Selectivity

A high yield on few bets can be unstable. Profit per common opportunity remains primary and every
conditional metric carries BET coverage.

### Market evidence dependence

Prediction and Decision price evidence come from the same historical bookmaker universe. This is an
accepted baseline-engineering design, not proof of independent live execution edge.

### Settlement scope

The common corpus has FT regulation-time outcomes only; VOID/refund remains a tested defensive branch,
not an empirically represented historical stratum here.

### Capital contamination

If an implementation requires bankroll/lane/capital state to define a Decision action, the layer
boundary has been violated and FS-019 must stop rather than absorb Capital logic.

## 28. Resource budget

Disposition:

```text
RESOURCE_BUDGET
→ ACCEPTABLE
```

Measured facts:

```text
FS-018 full Prediction analysis
→ 408.184 s, 347.809 MiB process HWM

FS-018 Market reconstruction use inside final analysis
→ ~0.006 s measured replay assembly

E1 Decision-only feasibility process
→ ~0.89 s wall including Python startup/loading
→ ~124.4 MiB process HWM in this environment

full deterministic policy expansion
→ 11,436 rows
→ ~0.066 s

full 5,000-replicate block-geometry benchmark
→ 229 blocks
→ ~0.059 s using dummy rewards

representative full Decision-row gzip
→ ~0.46 MiB before report/summary/bootstrap outputs
```

Practical FS-019 expectation:

```text
runtime
→ seconds to low tens of seconds in finsport-dev, not Prediction-scale minutes

memory
→ materially below FS-018 full Prediction replay; normal dev-container budget is sufficient

artifact size
→ low single-digit MiB if upstream evidence is referenced/snapshotted compactly rather than copying the
   complete 36.3 MiB Phase-3 evidence bundle into every run
```

Suggested implementation warning thresholds—not scientific selection rules—are to investigate if a
Decision-only run unexpectedly exceeds roughly one minute, 512 MiB RSS, or 10 MiB of newly generated
Decision artifacts. F009 preflight may adjust these only for demonstrated implementation overhead.

## 29. Open questions

No methodological blocker remains.

Preflight-only implementation questions:

1. What exact command/API shape will FS-019 use to point at the frozen upstream run/input snapshot?
2. Will the Decision adapter consume `run.json` directly or a one-time slim snapshot derived from it?
   E1 recommends the slim immutable snapshot after verification.
3. What exact filename/schema version will be used for Decision per-policy rows and promotion JSON?
4. What real dev-container runtime/RSS/artifact measurements result after implementation?
5. Does the repository need a helper to verify/restore the local FS-018 evidence bundle after future
   `tmp/` cleanup?

These are F008/F009 ticket-definition and preflight facts. None requires new external research.

### E1.1 — Decision Selection Contract Precision

The corrective E1.1 pass closes four implementation ambiguities without changing candidates, cohorts,
prices, rewards, primary metric, bootstrap replicate count, fallback philosophy or resource
disposition:

```text
stability
→ strict sign rule on fixed observed top vs fixed observed runner-up
→ 10 leave-one-league-out deltas + 2 chronological-half deltas
→ delta < 0 = UNSTABLE
→ delta = 0 = NO_CLEAR_SUPERIORITY
→ all deltas > 0 required for stability PASS

chronological half
→ UTC kickoff instant ASC, match_id ASC
→ global split at floor(N/2)
→ current corpus 953 / 953

simultaneous guard
→ observed top fixed before bootstrap
→ d_c = theta_T - theta_c
→ a_b,c = d_c - delta_c^(b)
→ M_b = max_c a_b,c
→ q95 = linear/R7 95th percentile of M
→ LB_c = d_c - q95
→ every LB_c > 0 required

bootstrap seed
→ literal 18092026
→ frozen in Decision ExperimentSpec
```

No Decision ranking or `GLOBAL_DECISION_V1` selection was performed in E1.1.

### E1.2 — Fallback Determinism Precision

The corrective E1.2 pass closes the remaining usable-baseline ambiguity without changing any E1.1
selection statistic or guard:

```text
survivors
→ S = {T} ∪ {c != T : SIMULTANEOUS_LB_c <= 0}
→ T always survives

CLEAR_SUPERIORITY
→ select T directly
→ promotion allowed

NO_CLEAR_SUPERIORITY / UNSTABLE
→ fallback allowed
→ if MODAL_ALL survives, select MODAL_ALL
→ otherwise select highest observed GLOBAL_PPO within S
→ exact score ties by frozen candidate order
→ because T is the global point-score top and T ∈ S, this non-MODAL branch resolves to T

INSUFFICIENT_EVIDENCE
→ fallback forbidden
→ NO_PROMOTION
```

No Decision ranking or `GLOBAL_DECISION_V1` selection was performed in E1.2.

## 30. Final disposition

```text
UPSTREAM_GLOBAL_PREDICTION_V1
→ BOUND

DECISION_CANDIDATE_SET
→ CLOSED

DECISION_POLICY_SEMANTICS
→ CLOSED

DECISION_OPPORTUNITY_COHORT
→ CLOSED

PRICE_EVIDENCE_CONTRACT
→ CLOSED

FS018_PRICE_EVIDENCE_REUSE
→ SUFFICIENT

MARKET_CONSENSUS_VALUE_CIRCULARITY
→ CLOSED
→ VALUE fs003-value-v1 variants are INELIGIBLE under MARKET_CONSENSUS upstream

FIXED_UNIT_NORMALIZATION
→ CLOSED

SETTLEMENT_CONTRACT
→ CLOSED

PRIMARY_DECISION_METRIC
→ CLOSED

COVERAGE_SAMPLE_GUARDRAILS
→ CLOSED

GLOBAL_AGGREGATION
→ CLOSED

PAIRED_UNCERTAINTY
→ CLOSED

GLOBAL_SELECTION_RULE
→ CLOSED

PER_LEAGUE_REPORTING
→ CLOSED

RESOURCE_BUDGET
→ ACCEPTABLE

Research E1
→ CLOSED

FS_019
→ READY_FOR_TICKET

GLOBAL_DECISION_V1
→ NOT_SELECTED_IN_E1
```

### E1 handoff to F008

```text
Research status:
→ CLOSED

Upstream GLOBAL_PREDICTION_V1:
→ MARKET_CONSENSUS / fs013-market-consensus-v2
→ run b41fd8a324f4fd0265c8a9d43a1308dc21f5b862d45f6583b3a75542df5c711b

Decision candidates:
→ MODAL_ALL
→ SELECTIVE_CONFIDENCE .40/.45/.50/.55/.60
→ 6 total

Decision opportunity cohort:
→ PREDICTION_NATURAL = 1,906
→ DECISION_COMMON = 1,906
→ all ten league strata non-empty

Price evidence:
→ retained FS-018 ODDSPAPI_RECONSTRUCTED_T30_V1
→ Pinnacle / Bet365 / Unibet
→ >=2 complete books inherited from selected Market Prediction
→ best raw decimal price per outcome
→ no de-vig payout

FS-018 evidence reuse:
→ SUFFICIENT
→ no provider reacquisition by default

MARKET_CONSENSUS × VALUE:
→ CLOSED
→ VALUE INELIGIBLE

Fixed-unit normalization:
→ BET 1u / NO_BET 0u
→ win +(odds-1), loss -1, void 0

Primary metric:
→ equal-league fixed-unit profit per DECISION_COMMON opportunity

Coverage/sample guardrails:
→ common ten-league cohort
→ explicit selectivity denominators
→ simultaneous top-vs-all guard
→ leave-one-league + chronological-half stability

Global aggregation:
→ equal-league primary

Uncertainty:
→ paired Competition×Lima-week block bootstrap
→ 5,000 replicates

Selection/tie/fallback:
→ observed GLOBAL_PPO leader T; frozen-order tie-break
→ CLEAR only with simultaneous guard + stability; select T directly
→ survivor set S = {T} ∪ competitors with simultaneous LB <= 0; T always survives
→ NO_CLEAR or UNSTABLE: if MODAL_ALL survives select MODAL_ALL, else max observed GLOBAL_PPO in S
→ INSUFFICIENT_EVIDENCE: NO_PROMOTION
→ fallback never changes the scientific disposition

Experiment Lab extension:
→ reuse existing framework
→ add Decision runner, historical best-price adapter, reward/metrics/comparison and promotion only

Capital handoff:
→ frozen Decision sequence only; stake/bankroll/lanes remain Capital

FS-019:
→ READY_FOR_TICKET

Preflight-only implementation facts:
→ upstream artifact path/restore
→ actual dev-container resource numbers
→ exact artifact/schema filenames

Open blockers:
→ NONE

Artifact:
→ docs/research/FS-019_global_decision_methodology_research.md
```

## 31. Stable references

### Finsport authority and artifacts

```text
docs/research/FS-018_global_prediction_v1.json
docs/research/FS-018_global_prediction_baseline_report.md
docs/process/FS-018_feedback.md
docs/research/FS-018_prediction_baseline_evidence/2026-09-19_b41fd8a324f4/

tmp/FS-018_experiments/15f313269bf23ed189ff3e50599b0b30785c23b61a1c361a7a7816f691a8ccc8/run.json
tmp/FS-018_experiments/15f313269bf23ed189ff3e50599b0b30785c23b61a1c361a7a7816f691a8ccc8/per_match.jsonl.gz
tmp/FS-018_experiments/15f313269bf23ed189ff3e50599b0b30785c23b61a1c361a7a7816f691a8ccc8/manifest.json
tmp/FS-018_experiments/55e2c9682f20d229b3ca67a102d4c084c581f33686fea094139333e041838b81/backfill.json
```

Phase-3 evidence bundle received for physical verification:

```text
FS-018_E1_phase3_evidence_b41fd8a324f4_20260919_171052.tar.gz
```

All bundle artifacts matched its SHA-256 inventory. Bundle machine-authority JSON SHA-256:

```text
f97dc5adec463c86fc0cbd9db82b0a2277d27ea1804b80dcc3a4a226c779e0a0
```

Final FS-018 merge on `master`:

```text
2291648cfe656aaa49157d1d5b7c3aef7312f97b
```

Relevant code contracts:

```text
football/prediction/constants.py
football/prediction/contracts.py
football/prediction/policies.py
football/prediction/market.py
football/prediction/evaluation.py
football/prediction/metrics.py
football/prediction/datasets.py
football/models.py

football/experiments/spec.py
football/experiments/market.py
football/experiments/runner.py
football/experiments/analysis.py
football/experiments/views.py
football/experiments/artifacts.py
football/experiments/storage.py
```

Process/product source authority remains the project bootstrap set `F000`–`F010`, with the active
execution/ticket authority resolved under F008/F009 at FS-019 ticket time.

### Methodological anchors retained from Phase 2

- Geifman, Y. & El-Yaniv, R. (2017), *Selective Classification for Deep Neural Networks*,
  arXiv:1705.08500 — risk/coverage framing.
- Hvattum, L. M. & Arntzen, H. (2010), *Using ELO ratings for match result prediction in association
  football*, International Journal of Forecasting 26(3), DOI `10.1016/j.ijforecast.2009.10.002` —
  unit betting/value evaluation and common-event comparability.
- Künsch, H. R. (1989), *The Jackknife and the Bootstrap for General Stationary Observations*, Annals
  of Statistics 17(3), DOI `10.1214/aos/1176347265` — block resampling under dependence.
- Politis, D. N. & Romano, J. P. (1994), *The Stationary Bootstrap*, JASA 89(428), DOI
  `10.1080/01621459.1994.10476870` — dependence-aware bootstrap principle.
- White, H. (2000), *A Reality Check for Data Snooping*, Econometrica 68(5), DOI
  `10.1111/1468-0262.00152` — multiple-rule/data-snooping guard.
- Štrumbelj, E. & Robnik Šikonja, M. (2010), *Online bookmakers' odds as forecasts: The case of
  European soccer leagues*, International Journal of Forecasting 26(3), DOI
  `10.1016/j.ijforecast.2009.10.005` — bookmaker odds as market forecasts and separation from
  executable quote choice.

---

# Final research boundary

E1 has frozen the Decision methodology, bound it to the actual immutable FS-018 winner and verified
that the physical historical evidence supports the complete Decision experiment without new provider
acquisition.

The next legitimate action is ticket definition/execution for:

```text
FS-019 — Global Decision Baseline
```

Only FS-019 may calculate the final economic tournament and select/promote:

```text
GLOBAL_DECISION_V1
```
