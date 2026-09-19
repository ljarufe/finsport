# Finsport E0 / E0.1 — Experimental Methodology
## Final ticketization revision for FS-018

**Research ID:** `E0 / E0.1`
**Status:** `CLOSED`
**Date:** `2026-09-18`
**Project:** `Finsport`
**Artifact type:** `REFERENCE ONLY / maintainer-owned`
**Repository authority:** `ljarufe/finsport`
**Baseline checkout inspected by E0:** `master@11ee777a4bcb837ef76ac18c36bcb8488db6ec6a`
**Target durable path for FS-018:** `docs/research/FS-018_experiment_lab_global_prediction_research.md`

> This document supersedes the previous E0/E0.1 report only where ticketization corrections are
> explicitly stated below.
>
> It does **not** reopen the accepted methodology.
>
> The material correction is:
>
> ```text
> MARKET_CONSENSUS algorithm/version
> → remains fs013-market-consensus-v2
>
> historical experiment evidence
> → ODDSPAPI_RECONSTRUCTED_T30_V1
>
> no MARKET_CONSENSUS v3 is created merely because historical evidence comes from OddsPapi
> ```
>
> A second correction is operational:
>
> ```text
> proof that OddsPapi works
> → already sufficient
>
> full 10-league OddsPapi acquisition
> → FS-018 implementation/UAT responsibility
> → not another research gate
> ```
>
> A one-league end-to-end provider/reconstruction pilot is sufficient to validate the implemented
> acquisition path. FS-018 then runs a manually started, resumable Celery backfill across all ten
> enabled leagues and performs the full Prediction baseline after the available 2026 corpus reaches a
> terminal backfill state.

---

# 1. Executive conclusion

E0 and E0.1 are closed.

No further methodological research is required before F008 defines FS-018.

The next ticket is:

```text
FS-018 — Experiment Lab + Global Prediction Baseline
```

Its coherent outcome is:

```text
reusable Prediction Experiment Lab
+
historical research evidence needed by the four frozen candidates
+
full frozen Prediction baseline
+
one versioned GLOBAL_PREDICTION_V1
```

The four Prediction families remain:

```text
DIXON_COLES
→ fs011-dixon-coles-v2

INDEPENDENT_POISSON
→ fs003-independent-poisson-v1

ELO_MULTINOMIAL_LOGIT
→ fs003-elo-multinomial-logit-v1

MARKET_CONSENSUS
→ fs013-market-consensus-v2
```

`MARKET_CONSENSUS` is **not** upgraded to a new model version for historical replay.

The experiment uses a separate evidence profile:

```text
evidence_profile
→ ODDSPAPI_RECONSTRUCTED_T30_V1

evidence_class
→ HISTORICAL_RESEARCH
```

That profile reconstructs the inputs needed by the already-existing Market Consensus v2 algorithm:

```text
Pinnacle / Bet365 / Unibet historical 1X2
→ latest valid state at or before kickoff - 30m
→ complete H/D/A triplet per bookmaker
→ multiplicative de-vig per bookmaker
→ EQUAL_WEIGHT across usable bookmakers
→ P(H), P(D), P(A)
```

The experiment must never represent those historical rows as prospective `OddsObservation`.

The old FS-015 single-book proxy remains useful only as:

```text
MARKET_T30_PROXY
→ diagnostic
→ not eligible to represent Market Consensus v2 in the primary four-arm baseline
```

---

# 2. What remains frozen from E0

The following E0 conclusions remain accepted and are not reopened:

```text
Experiment Lab
→ football/experiments/ inside the football app

dedicated Django app
→ NOT_REQUIRED

dedicated experiment Compose/runtime
→ NOT_REQUIRED

execution runtime
→ finsport-dev

Beat
→ OFF

automatic providers
→ OFF

operational DB mutation
→ FORBIDDEN

enabled leagues
→ current 10

season completeness
→ NOT_REQUIRED

eligibility
→ per Match

COMMON
→ primary paired head-to-head cohort

NATURAL
→ secondary applicability/coverage cohort

Prediction replay
→ strict chronological / same-Lima-day frozen target batch

primary metric
→ COMMON log-loss

global aggregation
→ equal-league mean across eligible league strata

secondary
→ pooled log-loss, Brier, RPS, calibration, accuracy, coverage

uncertainty
→ paired Competition-stratified weekly block bootstrap

bootstrap replicates
→ 5,000

Prediction selection
→ one global baseline

per-league routing
→ OUT

Decision
→ OUT

Capital
→ OUT

MAGI
→ OUT

frontend
→ OUT

real betting
→ FORBIDDEN
```

The future process remains one-layer-at-a-time:

```text
Prediction
→ GLOBAL_PREDICTION_V1
→ freeze

Decision
→ later

Capital
→ later
```

No Prediction × Decision × Capital combinatorial search is authorized.

---

# 3. Historical sporting evidence

E0 measured a broad sporting replay basis:

```text
history before 2025  49,377 Matches
2025                  3,560 targets
2026 to E0 cutoff     1,052 targets
```

The historical sporting foundation is sufficient for FS-018.

No new sporting provider or additional league is needed for the first baseline.

A missing Match or missing evidence never invalidates a whole season:

```text
required evidence exists for Match
→ eligible

required evidence missing
→ exclude that Match from the affected arm/cohort
→ preserve reason
```

---

# 4. Current sporting candidate replay

The first baseline evaluates CURRENT configurations as frozen candidates.

No hyperparameter search is part of FS-018.

## Dixon-Coles

```text
model_version
→ fs011-dixon-coles-v2

history
→ expanding strict-prior

fit
→ once per Lima target day

xi
→ resolved CURRENT configuration

same-day target outcomes
→ unavailable until all predictions for that day are frozen
```

## Independent Poisson

```text
model_version
→ fs003-independent-poisson-v1

history
→ expanding strict-prior

fit
→ once per Lima target day

xi
→ resolved CURRENT configuration
```

## Elo Multinomial Logit

```text
model_version
→ fs003-elo-multinomial-logit-v1

k / C / HFA / solver / feature contract
→ resolved CURRENT configuration

state/training
→ strict-prior chronology
```

## Market Consensus

```text
model_version
→ fs013-market-consensus-v2

sporting fit
→ none

historical input profile
→ ODDSPAPI_RECONSTRUCTED_T30_V1
```

---

# 5. Why Market Consensus remains v2

A model version describes the statistical/model contract.

The following remain unchanged:

```text
1X2 probability output
canonical bookmaker identity
multiplicative de-vig
one probability vector per usable bookmaker
EQUAL_WEIGHT aggregation
```

Therefore:

```text
OddsPapi historical source
!= new model algorithm

historical replay profile
!= MARKET_CONSENSUS v3
```

FS-018 artifacts must make both identities visible:

```text
model_code
model_version
evidence_profile
evidence_class
bookmaker_universe
cutoff_rule
```

Recommended semantic identity:

```text
model_code
= MARKET_CONSENSUS

model_version
= fs013-market-consensus-v2

evidence_profile
= ODDSPAPI_RECONSTRUCTED_T30_V1
```

This keeps runtime and research provenance honest without creating fake model versions.

---

# 6. Market historical-fidelity conclusion

The original `HISTORICAL_T30_PROXY` used one historical closing 1X2 triplet.

E0.1 compared that proxy with actual prospective Market Consensus where overlap existed.

Observed local overlap:

```text
N
→ 36 Matches

leagues
→ 10

mean L1
→ ~0.0313

argmax agreement
→ ~94.4%

equal-league Δ log-loss
→ near zero
```

The sample was promising but too small/source-narrow to establish that the single-book proxy was
sufficiently faithful for baseline selection.

Therefore:

```text
HISTORICAL_T30_PROXY_AS_FULL_CANDIDATE
→ REJECTED

MARKET_T30_PROXY_DIAGNOSTIC
→ ALLOWED
```

This is no longer a blocker because OddsPapi physically demonstrated a stronger historical
reconstruction route.

---

# 7. OddsPapi external contract — accepted research conclusion

A bounded live smoke test already demonstrated the material historical contract on five major leagues.

The ticket does **not** require a new provider research pass.

Official contract as of 2026-09-18:

## Fixture discovery

```text
GET /v4/fixtures
```

Useful parameters include:

```text
tournamentId
from
to
statusId
hasOdds
bookmakers
```

Relevant returned fields include:

```text
fixtureId
tournamentId
seasonId
statusId
startTime
trueStartTime
participant1Id
participant2Id
participant1Name
participant2Name
tournamentName
categoryName
externalProviders
```

Official endpoint cooldown:

```text
2 seconds
```

Fixture calls are billable request-count calls.

## Historical odds

```text
GET /v4/historical-odds
```

Required request shape:

```text
fixtureId=<OddsPapi fixture id>
bookmakers=pinnacle,bet365,unibet
```

Maximum bookmakers per historical call:

```text
3
```

Relevant historical fields include:

```text
bookmakers
markets
outcomes
players["0"]
createdAt
price
active
```

Official historical endpoint cooldown:

```text
5 seconds
```

The endpoint exposes history from January 2026.

The endpoint itself is documented as free with respect to request-count consumption, but the overall
account request limit can still block service access if the plan limit has already been reached.

## 1X2 identity

```text
sportId
→ 10

marketId
→ 101
→ Full Time Result
→ fulltime
→ 1x2

outcomeId 101
→ HOME / "1"

outcomeId 102
→ DRAW / "X"

outcomeId 103
→ AWAY / "2"
```

No further methodology research is required around those IDs.

---

# 8. OddsPapi usage/retention boundary

Official OddsPapi documentation explicitly describes client-side caching of deterministic finished
fixture historical responses and ETag reuse.

Official Terms prohibit:

```text
reselling
repackaging
redistributing OddsPapi data as a standalone product
```

FS-018 therefore adopts a conservative local-research policy:

```text
raw provider payload
→ private local cache only
→ ignored by Git
→ never committed
→ never attached to ticket/handoff
→ never redistributed

derived experiment evidence
→ may store only what is necessary for reproducibility/audit
→ probabilities / selected prices / timestamps / ids / hashes / provenance
```

The ticket does not create a public historical OddsPapi dataset.

The local cache is an implementation aid, not canonical Finsport sporting/market truth.

If future work needs additional raw market families, reacquisition can be researched separately.

Extra O/U/AH/BTTS markets returned in a response do not expand FS-018 scope.

---

# 9. Backfill responsibility moves into FS-018

Full ten-league acquisition is **not** a prerequisite for ticket creation.

It is part of the FS-018 deliverable.

Correct boundary:

```text
research
→ provider capability proven
→ reconstruction semantics frozen

FS-018 implementation
→ build bounded acquisition/reconstruction path
→ validate it end-to-end on one league
→ start full resumable 10-league backfill
→ run final baseline after backfill reaches terminal state
```

One-league acquisition/reconstruction proof is sufficient for implementation correctness.

La Liga is the preferred deterministic pilot because earlier E0 replay work already used it and the
research smoke demonstrated the provider class.

The full experiment is still global across the ten enabled leagues.

---

# 10. Backfill execution contract

FS-018 may use Celery because the backfill is long-running research work.

It must **not** introduce a new periodic scheduler.

Required semantics:

```text
manual enqueue
→ one-shot research backfill

Celery Beat
→ no schedule

automatic production provider work
→ none

operational stack
→ untouched

execution environment
→ finsport-dev
```

The implementation must be:

```text
resumable
idempotent
checkpointed
serial for /historical-odds
safe after host/process restart
```

Historical provider calls must never exceed:

```text
1 /historical-odds request per 5 seconds
```

Do not parallelize historical calls across workers.

A duplicate manually-triggered backfill must fail closed or converge to the same cache/checkpoint
rather than doubling traffic.

A manually started task may continue unattended while the dev worker is running.

If interrupted:

```text
restart/resume
→ continue from durable/local checkpoint
→ do not reacquire completed fixtures unnecessarily
```

No artificial requirement exists that the maintainer keep an execution chat open while Celery works.

---

# 11. Full acquisition target

FS-018 attempts every current enabled Finsport league.

Historical acquisition window:

```text
2026-01-01
or earliest actual provider availability
→ frozen FS-018 data_cutoff
```

Initial bookmaker universe is frozen:

```text
pinnacle
bet365
unibet
```

No bookmaker may be swapped based on observed experiment scores.

Historical Market row eligibility:

```text
>=2 complete bookmakers
```

Preferred:

```text
3 complete bookmakers
```

For each usable bookmaker:

```text
select latest active valid HOME price at/before T-30
select latest active valid DRAW price at/before T-30
select latest active valid AWAY price at/before T-30

require complete triplet
de-vig multiplicatively
```

Then:

```text
equal arithmetic mean
→ reconstructed Market Consensus probability vector
```

No post-T30 observation may repair missing pre-T30 evidence.

---

# 12. Tournament/fixture mapping contract

Provider capability is closed.

Exact current tournament IDs for the ten leagues are implementation data and may be resolved in F009
preflight before Codex or discovered deterministically by the implemented provider catalog/discovery
path.

This is not a methodology choice.

Canonical reconciliation must use a fail-closed identity rule.

Preferred hierarchy:

```text
durable provider/external identity if available and verified
→ else deterministic canonical matching from:
   Competition mapping
   participant/team mapping
   scheduled kickoff within frozen tolerance
```

Outcomes:

```text
0 canonical candidates
→ UNMATCHED

1 canonical candidate
→ MATCHED

>1 canonical candidate
→ AMBIGUOUS
→ no guess
```

The exact helper/function/tolerance implementation is an F009 preflight/code fact.

The ambiguity policy is already closed and must not be invented by Codex.

---

# 13. Provider budget contract

Before starting the full backfill, F009/FS-018 checks:

```text
GET /v4/account
→ request_limit
→ request_count
```

`/v4/account` is documented as unmetered.

Fixture-discovery calls are billable.

Historical-odds calls do not increment request count, but service calls can still be blocked if the
account request limit has already been exhausted.

The implementation must minimize billable fixture discovery using filtered/batched fixture requests,
cache the resulting fixture mapping, and never repeatedly rediscover already-completed windows.

The physical acquisition report must record:

```text
fixture discovery calls
historical calls
HTTP status counts
429 count
retries
matched/unmatched/ambiguous fixtures
cached/skipped fixtures
complete-book counts
quote-age distribution
```

No quota should be intentionally exhausted for testing.

---

# 14. Experiment Lab contract

The minimum reusable implementation remains:

```text
football/experiments/
```

Conceptual responsibilities:

```text
ExperimentSpec
cohort/manifests
strict chronological replay
market historical evidence adapter
metrics
paired comparison/bootstrap
artifact generation
baseline promotion record
```

No generic experimentation platform is required.

The Prediction baseline is the proving use case for the lab.

---

# 15. ExperimentSpec

The full scored run freezes at least:

```text
experiment_id
experiment_spec_version
changed_layer = Prediction
candidate model codes/versions
resolved sporting configs
league set
data_cutoff
historical window
training/replay rules
COMMON definition
NATURAL definition
market evidence_profile
OddsPapi bookmaker universe
minimum complete-book rule
market cutoff rule
de-vig / consensus method
metrics
equal-league aggregation
bootstrap method
bootstrap replicate count
bootstrap seed
code Git SHA
artifact schema version
```

No candidate/config/bookmaker/cutoff change is permitted after inspecting the scored baseline output.

---

# 16. Experiment artifacts

Required run outputs:

```text
spec.json
manifest.json
summary.json
per_match.jsonl.gz
report.md
```

Raw OddsPapi payloads are not part of the durable report package.

Minimum per-Match/model evidence:

```text
Match id
Competition id
kickoff/local day
candidate model/version/config
p_home
p_draw
p_away
actual regulation outcome
log-loss
Brier
RPS
COMMON/NATURAL membership
unavailable/failure reason
evidence_profile
provider fixture id where applicable
bookmaker count where applicable
selected quote timestamps/ages where applicable
payload/cache hash where applicable
```

---

# 17. COMMON / NATURAL

Primary paired selection cohort:

```text
COMMON
```

A Match belongs to COMMON only if every candidate in that comparison has a legitimate probability
vector.

No missing output is imputed.

Secondary applicability cohort:

```text
NATURAL
```

NATURAL reports the Matches each family can honestly cover.

For Market Consensus:

```text
eligible historical probability
→ reconstructed OddsPapi T30 evidence

legacy MARKET_T30_PROXY
→ diagnostic only
→ does not make a Match eligible for the primary Market arm
```

---

# 18. Global selection metric

Primary:

```text
COMMON log-loss
```

Primary aggregation:

```text
equal-league mean
```

Conceptually:

```text
1/10 × sum(league COMMON mean log-loss)
```

when all ten leagues have a legitimate comparison stratum.

Secondary:

```text
pooled match-weighted log-loss
Brier
RPS
accuracy
calibration
coverage
failure/unavailability
per-league metrics
temporal stability
```

No arbitrary composite score.

---

# 19. Market eligibility if coverage is incomplete

FS-018 attempts all ten leagues.

The ticket does not fail merely because OddsPapi lacks legitimate reconstructed evidence in one or
more leagues.

Instead:

```text
Market evidence in all ten required league strata
→ Market eligible to become GLOBAL_PREDICTION_V1

Market evidence only in subset
→ report Market as partial challenger/diagnostic
→ Market cannot win ten-league global baseline

DC / Poisson / Elo
→ continue through frozen selection procedure
```

This keeps the ticket productive without disguising partial Market coverage as global evidence.

---

# 20. Uncertainty

For paired COMMON comparisons:

```text
delta_m(A,B)
= logloss_m(A) - logloss_m(B)
```

Frozen bootstrap:

```text
stratum
→ Competition

block
→ Competition × Lima calendar week

resampling
→ complete weekly blocks with replacement inside Competition

replicate score
→ mean delta per Competition
→ equal mean across leagues

replicates
→ 5,000

interval
→ percentile 95%
```

The bootstrap seed is frozen in the final ExperimentSpec before the scored run.

---

# 21. Selection / tie fallback

The lab must produce one product baseline without manufacturing scientific certainty.

Process:

```text
1. determine eligible global candidates
2. compare primary equal-league COMMON log-loss
3. inspect paired uncertainty
4. inspect coverage/stability/failure guardrails
5. select or apply deterministic fallback
```

If no clear superiority:

```text
scientific disposition
→ NO_CLEAR_SUPERIORITY
```

Deterministic fallback order:

```text
1. higher legitimate NATURAL coverage
2. better per-league/time stability
3. fewer systematic failures/evidence dependencies
4. lower measured runtime/resource burden
5. stable model-code/version ordering
```

The fallback chooses a usable baseline; it does not claim a statistical winner.

---

# 22. Baseline promotion record

FS-018 must leave a machine-readable immutable result for the next layer.

Required semantic output:

```text
GLOBAL_PREDICTION_V1
```

It must reference:

```text
selected model_code
selected model_version
resolved config identity
experiment spec identity
winner run identity
data_cutoff
cohort/manifest hash
selection disposition
research artifact
human report
```

Recommended durable path:

```text
docs/research/FS-018_global_prediction_v1.json
```

Human report:

```text
docs/research/FS-018_global_prediction_baseline_report.md
```

This record is the input authority for the subsequent Decision research/ticket.

It does not automatically reconfigure the operational Prediction runtime.

---

# 23. One-league technical pilot

Before the full backfill/baseline, FS-018 must validate the implemented path end-to-end on one
deterministic league.

Preferred:

```text
La Liga
```

Pilot checks:

```text
fixture discovery
canonical Match mapping
historical request
private cache/checkpoint
T-30 selection
complete-book rule
de-vig
EQUAL_WEIGHT
Market probability vector
ExperimentSpec integration
COMMON/NATURAL construction
artifact generation
rerun/idempotence
```

The pilot may not select `GLOBAL_PREDICTION_V1`.

After pilot PASS:

```text
enqueue full 10-league backfill
```

---

# 24. Full UAT sequence

Final ticket UAT occurs only after the backfill has reached a terminal state for the frozen scope.

Expected order:

```text
U1
→ deterministic one-league provider/reconstruction pilot

U2
→ manual enqueue full 10-league resumable backfill

U3
→ verify terminal acquisition report
→ coverage/mapping/errors explicit

U4
→ freeze final data_cutoff + ExperimentSpec + manifest

U5
→ run full eligible baseline

U6
→ validate metrics/bootstrap/per-league outputs

U7
→ validate GLOBAL_PREDICTION_V1 disposition/promotion record

U8
→ rerun artifact-only/analysis path from cached/derived evidence where applicable
→ no unnecessary provider reacquisition

U9
→ verify operational DB untouched
→ no historical data written as prospective OddsObservation
→ no Beat schedule created
```

The full baseline uses **all legitimate data acquired by the frozen cutoff**.

---

# 25. Resource conclusion

Sporting replay evidence measured by E0:

```text
~12.6 min
~300 MiB RSS
```

This remains acceptable.

OddsPapi historical acquisition is network-bound.

At roughly one historical request per matched fixture and a mandatory 5-second cooldown, a corpus of
about 1,000 fixtures has a protocol-level minimum order of magnitude around 5,000 seconds of
historical-request spacing, before fixture discovery/retries.

That is acceptable for a one-time resumable backfill and is precisely why Celery/checkpointing is
included.

No GPU, distributed executor or parallel historical endpoint use is required.

---

# 26. Future experiment procedure v0.1

After FS-018:

```text
1. define Prediction challenger
2. freeze candidate/version/config
3. freeze ExperimentSpec
4. obtain any required historical evidence under explicit provenance
5. build/hash cohort manifest
6. replay baseline + challenger under identical chronology
7. build COMMON/NATURAL
8. compute proper scores
9. compute paired uncertainty
10. inspect global/per-league/time stability + coverage
11. disposition:
    PROMOTE
    KEEP_BASELINE
    DROP
    INSUFFICIENT_EVIDENCE
12. if promoted:
    create immutable GLOBAL_PREDICTION_V(n+1)
13. old baseline/history remains unchanged
```

The inspected confirmation window becomes development evidence for subsequent challengers.

Future candidates require newer/later confirmation appropriate to their claim.

---

# 27. MAGI compatibility

MAGI remains future work.

FS-018 preserves, where already legitimate:

```text
per-model probability vectors
per-Match losses
Competition
time identity
historical market context
coverage/unavailability
model/config identity
```

No speculative MAGI features are added.

Future:

```text
MAGI / MODEL_CONSENSUS
→ contextual relevance of models
→ candidate vs GLOBAL_PREDICTION baseline
```

---

# 28. Explicit FS-018 non-goals

Not FS-018:

```text
Decision baseline
Capital baseline
MAGI
per-league production routing
new Prediction family
R45 reactivation
Inkabet reactivation
production OddsPapi integration
OddsPapi Beat schedule
production OddsPapi prospective capture
writing historical OddsPapi as OddsObservation
bookmaker-weight tuning
multi-market Prediction
O/U/AH/BTTS feature engineering
new leagues
frontend
Portfolio Kelly
dynamic lanes
real betting
```

---

# 29. Stop conditions

Execution must stop and return contradiction if:

```text
historical endpoint contract materially differs from verified shape
provider access no longer supports required historical call
T-30 selection cannot be reconstructed without post-cutoff evidence
canonical Match mapping is systematically ambiguous
current sporting adapter replay leaks future information
manifest/cohort construction is nondeterministic
raw provider evidence would need to be published/redistributed contrary to terms
```

Do not silently:

```text
fall back to MARKET_T30_PROXY
change bookmakers
change cutoff
change model configs
change eligibility
```

after seeing scores.

If Market reconstruction is merely incomplete by league, use the predefined partial-diagnostic
policy instead of stopping the entire ticket.

---

# 30. Ticket-readiness boundary

Closed by E0/E0.1/F008:

```text
product objective
methodology
candidate set
Market algorithm identity
historical evidence class
provider/source choice
external request contract
bookmaker policy
T-30 cutoff semantics
COMMON/NATURAL semantics
metrics
uncertainty
selection/fallback
one-league pilot concept
full 10-league acquisition responsibility
safety/provenance
scope/out-of-scope
```

May remain to F009 S1→S2 preflight because they are implementation facts:

```text
exact branch-local module/helper names
exact management-command/task names
exact current OddsPapi tournament IDs
exact local fixture/team mapping helpers available in checkout
exact artifact/cache directories consistent with .gitignore
exact bootstrap seed literal
exact deterministic pilot Match IDs
exact Celery queue/task wiring in current dev stack
exact current API-key configuration surface/presence
exact fixture discovery batching/window size under current quota
```

F009 must close all material preflight facts before Codex.

Codex must not research methodology/provider choice.

---

# 31. Final disposition

```text
E0
→ CLOSED

E0.1
→ CLOSED

METHODOLOGY
→ CLOSED

MARKET_HISTORICAL_FIDELITY
→ CLOSED

MARKET_MODEL_VERSION
→ fs013-market-consensus-v2

MARKET_HISTORICAL_EVIDENCE_PROFILE
→ ODDSPAPI_RECONSTRUCTED_T30_V1

LEGACY_MARKET_T30_PROXY
→ DIAGNOSTIC_ONLY

PROVIDER_RESEARCH
→ COMPLETE

FULL_10_LEAGUE_BACKFILL
→ FS-018 RESPONSIBILITY

ONE_LEAGUE_PROVIDER_PILOT
→ SUFFICIENT IMPLEMENTATION PROOF

10_LEAGUE_BASELINE_TARGET
→ YES

DEDICATED_DJANGO_APP
→ NOT_REQUIRED

DEDICATED_EXPERIMENT_RUNTIME
→ NOT_REQUIRED

FS_018
→ READY_FOR_TICKET

GLOBAL_PREDICTION_V1
→ NOT_SELECTED_IN_RESEARCH
```

---

# 32. Stable external references

Accessed 2026-09-18:

1. OddsPapi — GET historical odds
   `https://oddspapi.io/us/docs/get-historical-odds`
   Contract: `fixtureId`, max three bookmaker slugs, timestamped historical states, ETag/cache,
   5-second cooldown, historical data since January 2026.

2. OddsPapi — GET fixtures
   `https://oddspapi.io/en/docs/get-fixtures`
   Contract: tournament/date/status discovery, fixture/team/tournament identity, 2-second cooldown.

3. OddsPapi — GET markets
   `https://oddspapi.io/us/docs/get-markets`
   Contract: `marketId=101` Full Time Result, `101=1`, `102=X`, `103=2`.

4. OddsPapi — Requests & Quota
   `https://oddspapi.io/us/docs/requests-and-quota`
   Contract: fixtures are billable, historical-odds is free with respect to request count,
   `/account` unmetered.

5. OddsPapi — Terms
   `https://oddspapi.io/es/legal/terms`
   Relevant restriction: no resale/repackaging/redistribution as a standalone data product.

6. Gneiting & Raftery (2007), Strictly Proper Scoring Rules, Prediction, and Estimation.

7. Wheatcroft (2021), Evaluating probabilistic forecasts of football matches.

8. Hyndman & Athanasopoulos, Forecasting: Principles and Practice — time-series cross-validation.

9. Diebold & Mariano (1995), Comparing Predictive Accuracy.

10. Politis & Romano (1994), The Stationary Bootstrap.

11. White (2000), A Reality Check for Data Snooping.

---

# 33. E0/E0.1 handoff to F008/F009

```text
Research status
→ CLOSED

Next ticket
→ FS-018 Experiment Lab + Global Prediction Baseline

Research artifact
→ maintainer-owned / REFERENCE ONLY

Codex
→ consumes conclusions
→ does not recreate research

Experiment Lab
→ football/experiments/

Runtime
→ finsport-dev

Backfill
→ one-shot/resumable Celery research job
→ manually enqueued
→ no Beat
→ serial historical endpoint

Provider pilot
→ one league is sufficient

Full data acquisition
→ all 10 leagues attempted inside ticket

Market
→ same fs013-market-consensus-v2 algorithm
→ ODDSPAPI_RECONSTRUCTED_T30_V1 evidence profile

Final experiment
→ all legitimate acquired 2026 evidence at frozen cutoff

Ticket result
→ GLOBAL_PREDICTION_V1
```
