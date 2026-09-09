# Finsport — FS-013 MARKET_CONSENSUS — Final Integrated Research

**Status:** FINAL
**Artifact class:** REFERENCE ONLY
**Project:** Finsport
**Provisional planning identity:** FS-013 — `MARKET_CONSENSUS`
**Date:** 2026-09-08
**Research mode:** integrated pre-ticket research
**Deep Research:** NOT USED
**Provider calls:** NONE
**Implementation performed:** NONE
**Ticket created:** NO

---

# 1. Executive summary

The research is complete enough to define an implementation ticket for `MARKET_CONSENSUS`.

Final research status:

```text
RESEARCH STATUS
→ COMPLETE ENOUGH FOR TICKET

TICKET READINESS
→ READY_FOR_TICKET
```

The product decision is to enable `MARKET_CONSENSUS` now as a usable experimental/current research capability instead of waiting for enough future evidence to calibrate every advanced parameter.

The circular dependency is explicit:

```text
near-kickoff evidence is missing
because
the current capture lifecycle does not deliberately acquire it

therefore

requiring that evidence before implementing the acquisition mechanism
→ would make the research impossible to complete honestly
```

The usable baseline does **not** require learned bookmaker weighting.

The final default method is:

```text
latest real timestamp-valid 1X2 evidence
→ canonical bookmaker identity
→ canonical 1X2 market identity
→ one vote per canonical bookmaker
→ multiplicative de-vig
→ EQUAL_WEIGHT
→ HOME / DRAW / AWAY probabilities
```

`EQUAL_WEIGHT` is both:

```text
DEFAULT
+
UNCONDITIONAL STATISTICAL FALLBACK
```

Book-count semantics remain:

```text
0 valid canonical bookmaker quotes
→ UNAVAILABLE

>=1 valid canonical bookmaker quote
→ Prediction may be PRODUCED
```

with diagnostics exposing canonical bookmaker count and quote freshness.

This does **not** claim:

```text
1 bookmaker
→ mature market consensus
```

The distinction remains:

```text
technical producibility
!=
mature consensus/readiness
```

The ticket must also correct the current capture-timing defect by enabling bounded prospective evidence acquisition at:

```text
T-6h
T-60m
T-30m
```

No `T-15m`.

No continuous polling.

No preservation of `T-48h / T-24h / T-12h` merely by inertia for this Market Consensus evidence study.

Each completed real capture batch should be capable of producing one versioned `MARKET_CONSENSUS` Prediction for that batch/window after raw evidence is durably persisted.

Learned weighting methodology is also closed, but current evidence is insufficient to activate it. Therefore a legitimate initial state is:

```text
candidate/stored learned profile
→ INSUFFICIENT_EVIDENCE / INACTIVE

effective runtime
→ EQUAL_WEIGHT
```

Future empirical calibration is:

```text
POST-IMPLEMENTATION SCIENTIFIC EVIDENCE
→ NOT A TICKET BLOCKER
```

The former pre-ticket Phase 3 requirement is therefore reclassified:

```text
PRE-TICKET LOCAL EMPIRICAL PHASE
→ NOT REQUIRED
```

---

# 2. Purpose

This document integrates:

```text
Finsport_FS013_market_consensus_research_phase1_local_baseline.md
→ ACCEPTED

Finsport_FS013_market_consensus_research_phase2a_provider_capture.md
→ ACCEPTED

Finsport_FS013_market_consensus_research_phase2b_statistical_weighting.md
→ ACCEPTED
```

plus the final explicit product decision:

```text
enable safe/default MARKET_CONSENSUS now
+
automatically accumulate prospective evidence
+
keep evidence-dependent enhancements behind explicit fallback/readiness
```

The purpose is to provide F008 with a complete research contract for ticket definition.

This document does not create the ticket and does not perform implementation mapping.

---

# 3. Authority and source hierarchy

## 3.1 Finsport authority

Durable project authority remains:

```text
F000
F001
F002
F003
F004
F006
F008
F009
F010
```

`F005` remains:

```text
TEMPLATE / BOOTSTRAP
NOT USED IN FINSPORT
```

## 3.2 Accepted research artifacts

Research authority order for this topic:

```text
1. this final integrated artifact
2. accepted Phase 2B statistical-weighting artifact
3. accepted Phase 2A provider/capture artifact
4. accepted Phase 1 local-baseline artifact
5. MARKET_CONSENSUS applicability handoff
   → REFERENCE ONLY
```

Where the final product decision changes an earlier phase disposition, this final artifact is authoritative.

## 3.3 External-source hierarchy used

Provider research:

```text
official API-Football documentation
official API-Football / API-SPORTS current guidance
official pricing / quota material
```

Statistical research:

```text
peer-reviewed forecast-combination literature
original methodological papers
proper-scoring-rule literature
authoritative forecast-evaluation literature
```

No betting blogs, tipster content or ROI anecdotes were used as methodological authority.

---

# 4. Local findings carried forward

Phase 1 established the current local evidence state.

Independent resolved Matches with real timestamp-valid pre-kickoff market evidence:

```text
29
```

Temporal spread:

```text
dates
→ 5

season
→ 2026 only

competition coverage
→ uneven
```

Near-kickoff evidence:

```text
<=30m
→ 0 Matches

<=60m
→ 1 Match

<=180m
→ 2 Matches
```

Therefore:

```text
current evidence cannot empirically compare
T-60 / T-30 / T-15
```

This remains authoritative.

The current adapter baseline found in Phase 1 was:

```text
strict observed_at < cutoff
multiplicative de-vig
equal arithmetic mean
raw identity = source/bookmaker/market
no hard freshness gate inside adapter
```

The current schema/algorithm structurally permits duplicated economic-bookmaker votes if the same bookmaker appears through more than one source identity, even though the current real DB sample showed zero observed cross-source same-name collisions.

That structural issue becomes ticket scope.

---

# 5. Provider findings carried forward

Phase 2A closed enough of the current public provider contract to define bounded prospective capture.

Current documented pre-match football odds surface:

```text
GET /odds
```

Relevant public filtering includes:

```text
fixture
league + season
date
bookmaker
bet
```

The endpoint can return multiple bookmaker lines in one response and is paginated.

Therefore:

```text
one HTTP request
!=
one bookmaker quote
```

and:

```text
one fixture
!=
necessarily one request
```

because pagination may add requests.

Provider quota is request/page-oriented, not bookmaker-oriented.

Current public provider guidance established:

```text
pre-match /odds
→ nominal update every ~3h

pre-match odds availability
→ typically 1–14 days before fixture

provider pre-match odds history
→ last 7 days

coverage support
→ not a guarantee of odds for every Match/window
```

Exact provider refresh clock, per-bookmaker absence causes, per-market absence causes and provider cache internals remain undocumented.

Those are not ticket blockers.

---

# 6. The capture defect

The current research blocker is not merely lack of historical time.

Phase 1 directly observed that the existing lifecycle does not accumulate dense same-Match market states merely because the scheduler wakes frequently.

On 2026-09-06, when the stack ran through much of the day:

```text
CaptureRuns
→ 55

provider attempts
→ 49

market observations created
→ 43

Matches represented
→ 7

middle ALREADY_FULFILLED work items
→ 194
```

For every observed:

```text
match × source
```

there was only:

```text
1 distinct capture minute
```

and:

```text
0 match/source pairs
with 2+ distinct capture minutes
```

Therefore:

```text
scheduler wake ~15m
!=
new snapshot every 15m
```

and:

```text
keeping make up running
!=
prospective movement evidence accumulation
```

Once a planned capture identity/window is fulfilled, later wakes can correctly become `ALREADY_FULFILLED`.

That behavior is sensible for one-shot windows but insufficient when the research needs several deliberate time states for the same Match.

The problem must therefore be solved by **distinct planned capture windows**, not continuous polling.

---

# 7. Final capture acquisition configuration

The initial Market Consensus research/evidence acquisition configuration is frozen as:

```text
T-6h
T-60m
T-30m
```

These are deliberate independent acquisition opportunities for the same Match.

## T-6h

Purpose:

```text
same-day earlier state
movement comparator
incremental-information baseline
```

Rationale:

The provider documents a nominal ~3h pre-match odds update cadence.

`T-6h` is sufficiently separated from both near windows to create a reasonable chance of observing a different provider state while avoiding retention of the old `-12h/-24h/-48h` grid by inertia.

## T-60m

Purpose:

```text
first deliberate near state
better operational margin than T-30
fill the major Phase 1 evidence gap
```

## T-30m

Purpose:

```text
closer near state
create evidence needed to learn whether T-60 or T-30 can eventually be removed
```

## T-15m

Final disposition:

```text
EXCLUDED
```

Reason:

```text
only 15m after T-30
+
documented provider update cadence ~3h
+
full additional request/page cost
+
highest missed-window risk
```

## Continuous polling

```text
FORBIDDEN AS RESEARCH DESIGN
```

The evidence design is bounded.

## Permanence

The three-window set is not claimed to be permanent production timing.

Future evidence may justify:

```text
T-6h + T-60m
```

or:

```text
T-6h + T-30m
```

or another evidence-backed smaller subset.

But the ticket must initially make all three observable so that this question can become answerable.

---

# 8. Equal-weight usable baseline

## 8.1 Required default technique

The initial usable Market Consensus method is:

```text
real timestamp-valid raw odds
→ canonicalize bookmaker
→ canonicalize 1X2 market
→ select one usable quote per canonical bookmaker at cutoff/window
→ multiplicative de-vig
→ equal-weight arithmetic pool
→ HOME / DRAW / AWAY probabilities
```

If canonical bookmaker probabilities are:

\[
p_i =
[p_{i,H}, p_{i,D}, p_{i,A}]
\]

for available bookmaker set \(A\), then:

\[
p^{EQ}
=
\frac{1}{|A|}
\sum_{i\in A} p_i.
\]

Each \(p_i\) already sums to one after de-vig.

The equal arithmetic mean therefore also sums to one mathematically, aside from floating-point tolerance.

## 8.2 Equal weighting status

```text
EQUAL_WEIGHT
→ DEFAULT

EQUAL_WEIGHT
→ UNCONDITIONAL STATISTICAL FALLBACK
```

It does not require learned-weight readiness.

It may remain the effective method indefinitely if later evidence never establishes a robust weighting advantage.

---

# 9. Book-count behavior

Final usable semantics:

```text
0 valid canonical bookmaker quotes
→ UNAVAILABLE
```

and:

```text
>=1 valid canonical bookmaker quote
→ probability Prediction may be PRODUCED
```

No fixed minimum bookmaker threshold is research-justified.

Preserved:

```text
NO_FIXED_MIN_BOOKMAKERS_JUSTIFIED
```

Mandatory diagnostics should expose at least:

```text
canonical bookmaker count
source/provenance summary
freshness/window information
```

The final research makes no claim that:

```text
one bookmaker
→ mature consensus
```

Instead:

```text
technical producibility
!=
mature consensus/readiness
```

The product/runtime may produce a probability vector while separately exposing that the consensus evidence is thin.

No arbitrary bookmaker count may be invented solely to make this distinction convenient.

---

# 10. Canonical bookmaker and market requirement

FS-013 must close the statistical vote-identity problem.

Required conceptual identities:

```text
canonical bookmaker identity
+
canonical 1X2 market identity
```

Invariant:

```text
1 canonical bookmaker
×
1 canonical 1X2 market
×
1 cutoff
→ maximum one vote
```

This requirement serves both:

```text
equal-weight correctness
+
future learned-weight correctness
```

Without it, the same economic forecaster can be counted twice because of provider/source representation.

Raw evidence must remain:

```text
append-only
source-provenanced
auditable
```

Canonicalization changes the statistical voting unit, not the provenance authority.

Exact:

```text
ORM models
tables
migration shape
indexes
constraints
service placement
```

belong to:

```text
F009 preflight / implementation mapping
```

and are intentionally not designed here.

---

# 11. Learned-weight methodology

The learned challenger is closed methodologically but not active empirically.

## 11.1 Challenger

For statistical profile scope \(s\):

\[
w_{s,i}\ge0
\]

and:

\[
\sum_i w_{s,i}=1.
\]

For the current Match/window, only freshness-valid canonical bookmakers are in the available set:

\[
A_{m,h}.
\]

Effective available weight:

\[
\widetilde{w}_{s,i,m,h}
=
\frac{w_{s,i}}
{\sum_{j\in A_{m,h}} w_{s,j}}.
\]

Weighted pool:

\[
p^W_{m,h}
=
\sum_{i\in A_{m,h}}
\widetilde{w}_{s,i,m,h} p_{i,m,h}.
\]

No invented quote is introduced for missing bookmakers.

No intercept, negative weights, neural model, boosting stack or ROI-optimized weighting is part of the accepted challenger.

## 11.2 Fit objective

Primary fit objective:

```text
multiclass log-loss
```

For realized outcome \(y_m\):

\[
\ell_{\log}(m)
=
-\log p^W_m(y_m).
\]

Primary OOS comparison:

```text
log-loss
```

Secondary diagnostics:

```text
multiclass Brier
calibration/reliability
RPS supplementary only
accuracy descriptive only
```

ROI/profit/Capital:

```text
NOT A WEIGHT-FIT OBJECTIVE
```

## 11.3 Regularization

Primary estimator:

```text
L2 ridge toward equal/effective parent
```

Generic scope objective:

\[
J_s(w;\lambda)
=
\frac{1}{|T_s|}
\sum_{m\in T_s}
-\log p^W_m(y_m;w)
+
\lambda_s
\|w-a_s\|_2^2.
\]

Shrinkage target:

```text
GLOBAL
→ EQUAL

LEAGUE
→ effective GLOBAL/EQUAL parent

SEASON
→ effective LEAGUE/GLOBAL/EQUAL parent
```

No fixed \(\lambda\) is research-frozen.

When enough evidence exists:

```text
lambda
→ selected by chronological inner forward validation
```

If evidence does not support meaningful hyperparameter selection:

```text
profile remains INACTIVE
→ effective runtime falls back
```

## 11.4 Hierarchy

Accepted hierarchy:

```text
GLOBAL
→ LEAGUE
→ SEASON
```

A narrower profile borrows strength from the effective broader parent.

A new season is:

```text
new child evidence scope
```

not:

```text
hard reset of all historical bookmaker reliability
```

A child may be stored without becoming ACTIVE.

---

# 12. Missing-bookmaker semantics

Real bookmaker panels are incomplete.

Finsport must not assume bookmaker availability is missing-at-random.

Training and prediction use:

```text
actual available canonical bookmaker panel
```

Not:

```text
complete-case deletion
```

and not:

```text
imputed bookmaker quote
neutral synthetic forecast
zero forecast
```

At prediction time:

```text
take ACTIVE profile weights
→ restrict to currently available freshness-valid bookmakers
→ renormalize weight mass over the available subset
→ pool only real forecasts
```

If one bookmaker is available:

```text
weighted pool
=
equal pool
=
that bookmaker's probability vector
```

Such a Match is valid predictive evidence but contains no comparative information about bookmaker weighting.

If the selected learned profile has zero available weight mass:

```text
do not invent epsilon
→ fall back to effective parent
→ eventually EQUAL_WEIGHT
```

---

# 13. Reliability and freshness lifecycle

Historical reliability and current quote freshness are separate.

Required composition:

```text
current quote passes capture/freshness/inclusion rule
→ bookmaker enters usable panel

historical reliability profile
→ determines weight among usable bookmakers
```

Rejected:

```text
stale quote
→ merely receives a smaller historical reliability weight
```

A stale/non-usable quote is not in the current usable panel.

This preserves the separation between:

```text
capture/readiness evidence
and
bookmaker historical reliability
```

---

# 14. Evidence and readiness lifecycle

## 14.1 Base Market Consensus

Base equal-weight Market Consensus becomes usable once the ticket can correctly construct real canonical bookmaker evidence.

It is not waiting on learned-weight evidence.

## 14.2 Learned profile lifecycle

Required distinction:

```text
profile exists
!=
profile ACTIVE
```

A learned candidate may legitimately be:

```text
STORED
CANDIDATE
INSUFFICIENT_EVIDENCE
INACTIVE
UNSTABLE
```

while runtime remains:

```text
EQUAL_WEIGHT
```

## 14.3 Evidence-based activation

Activation is based on behavior, not an arbitrary universal sample count.

Preserved:

```text
NO_FIXED_THRESHOLD_JUSTIFIED
```

A candidate profile should become ACTIVE only when all relevant gates pass:

```text
canonical bookmaker identity valid

genuine chronological OOS evidence exists

paired OOS log-loss improves against effective fallback

uncertainty supports improvement

improvement is not a one-short-period artifact

scope-specific evidence supports child scope

bookmaker overlap is non-degenerate

weights are sufficiently stable

calibration does not materially deteriorate

missingness/coverage does not undermine interpretation
```

The Phase 2B conservative criterion:

```text
95% stationary-block-bootstrap CI
for mean paired loss difference
has upper endpoint < 0
```

is explicitly classified as:

```text
PROJECT METHODOLOGICAL DECISION
```

It is **not** a universal theorem or literature-mandated activation threshold.

If evidence is too thin for credible uncertainty estimation:

```text
INSUFFICIENT_EVIDENCE_FOR_WEIGHT_ACTIVATION
```

and runtime continues using the effective fallback.

## 14.4 Automatic resolution

Runtime resolution semantics must not require hidden manual preference selection.

Conceptually:

```text
if matching SEASON profile ACTIVE
→ SEASON

else if matching LEAGUE profile ACTIVE
→ LEAGUE

else if GLOBAL profile ACTIVE
→ GLOBAL

else
→ EQUAL_WEIGHT
```

A stored inactive profile is not runtime authority.

F008 should preserve auditable deterministic activation/resolution semantics.

Exact implementation mapping belongs to F009.

---

# 15. Chronological future evaluation methodology

Future learned-weight evaluation is frozen as:

```text
nested expanding-window forward evaluation
```

Independent target unit:

```text
Match
```

All snapshots/quotes belonging to one Match remain in the same target unit.

No random K-fold is primary.

Outer chronology:

```text
TRAIN
→ already-resolved earlier Matches only

TEST
→ next operational forecast block
```

Weights and hyperparameters are frozen before the outer test block.

Inner chronology:

```text
forward validation inside TRAIN
→ choose lambda
```

Outer outcomes never select their own hyperparameter.

Weighting is evaluated separately for:

```text
T-6h
T-60m
T-30m
```

because each represents a distinct information horizon.

---

# 16. Future uncertainty and stability methodology

## 16.1 Paired comparison

On the same resolved Matches:

\[
d_m
=
\ell_{\log,weighted}(m)
-
\ell_{\log,fallback}(m).
\]

Interpretation:

```text
d_m < 0
→ weighted better
```

Primary uncertainty procedure:

```text
stationary block bootstrap
over chronologically ordered operational-date / forecast-batch clusters
```

with data-driven block-length selection when the evidence supports it.

An iid Match bootstrap is not the primary method because it would ignore chronological dependence.

Optional sensitivity only:

```text
Diebold-Mariano style comparison
with serial-dependence-aware variance
```

## 16.2 Weight stability

Future evaluation should track at each forward fit:

```text
weight vector
successive total-variation distance
effective number of bookmakers
distance from shrinkage parent
```

No universal numerical instability cutoff is research-justified.

Therefore:

```text
numeric stability threshold
→ NOT FROZEN
```

If empirical trajectories are materially unstable/ambiguous:

```text
WEIGHTED_POOL_UNSTABLE
→ do not activate
```

This does not prevent the base Market Consensus technique from operating under equal weighting.

---

# 17. Future calibration boundary

The following are intentionally **not prerequisites** for FS-013 implementation:

```text
whether T-60 or T-30 eventually wins

whether T-6h ultimately adds useful movement information

which lambda future evidence selects

whether GLOBAL learned weights ever activate

whether LEAGUE learned weights ever activate

whether SEASON learned weights ever activate

whether EQUAL_WEIGHT remains permanently superior
```

These are scientific outcomes.

They require the prospective evidence generated by the ticket itself.

Therefore:

```text
future empirical calibration
!=
pre-ticket blocker
```

and:

```text
PRE-TICKET LOCAL EMPIRICAL PHASE
→ NOT REQUIRED
```

Post-implementation operation must accumulate the evidence automatically enough for later evaluation without requiring fabricated historical states.

---

# 18. Prediction and versioning semantics

The required conceptual lifecycle per planned capture batch is:

```text
planned capture batch
→ retrieve real provider evidence
→ persist all real raw observations
→ commit durable evidence
→ canonicalize/deduplicate for statistical voting
→ compute one Market Consensus probability vector
→ persist one versioned MARKET_CONSENSUS Prediction
```

Explicitly not:

```text
every raw OddsObservation insert
→ separate Prediction
```

Each completed planned batch/window may produce its own Prediction version:

```text
T-6h capture
→ Prediction version/state for T-6h cutoff

T-60m capture
→ new Prediction version/state for T-60m cutoff

T-30m capture
→ new Prediction version/state for T-30m cutoff
```

Subsequent real evidence:

```text
→ new Prediction version
```

Historical Predictions:

```text
→ immutable
```

No later market observation may rewrite an older Prediction as though that evidence had existed earlier.

No backdating.

No synthetic closing quote.

No "latest odds" substitution for missing historical evidence.

Exact versioning model/fields/identity belongs to F009 preflight.

---

# 19. Missing / unchanged observation semantics

The ticket/research operation must preserve conceptual distinctions between:

```text
PROVIDER_EMPTY_AT_WINDOW
→ request succeeded but no usable odds evidence returned

OBSERVED_UNCHANGED
→ later real retrieval occurred and returned same relevant prices

BOOKMAKER_MISSING_AT_WINDOW
→ response exists, bookmaker absent

MARKET_MISSING_AT_WINDOW
→ response exists, canonical 1X2 market absent

NOT_ATTEMPTED
→ Finsport made no provider attempt for that window

ATTEMPT_FAILED
→ provider state was not successfully observed

WINDOW_MISSED
→ planned temporal acquisition did not occur inside allowed window
```

Core rules:

```text
absence
!= zero

no attempt
!= provider empty

failed request
!= provider empty

same prices on a real later retrieval
!= no new observation
```

If Finsport really retrieves the same prices again at another planned window, that is real evidence of an unchanged market state and must remain auditable.

---

# 20. Quota/cost boundary

Provider request cost should be measured by actual pages/retries, not bookmaker count.

For eligible fixtures \(F\), window set \(W\), pages \(P(f,w)\) and executed additional retries \(R(f,w)\):

\[
Q_{attempts}(W)
=
\sum_{f\in F,w\in W}
[P(f,w)+R(f,w)].
\]

Current initial window set:

```text
W
=
{T-6h, T-60m, T-30m}
```

If each fixture/window fits on one page with no retry, the simple special case is:

```text
3 requests per fixture
```

but pagination/retries can increase that.

Actual quota deltas should be preferred where provider headers make them available.

Daily research cohort size must respect:

```text
account daily allowance
-
mandatory reserve
-
normal non-research provider budget
```

The user's exact current API-Football account allowance was not established in research and should be an operational/preflight input.

No password/token is required to resolve it.

This does not block ticket definition.

---

# 21. Safety and non-goals

Finsport remains:

```text
local-only
demo-only
research-oriented
```

Real betting is forbidden.

FS-013 must not add:

```text
bookmaker authentication
bookmaker account access
bet placement
financial transaction side effects
automatic real-money execution
```

This research does not authorize:

```text
real betting
ROI optimization
capital allocation based on live wagering
```

Other non-goals:

```text
reopen Dixon-Coles
reopen Independent Poisson
reopen Elo
reopen de-vig comparison
black-box ML weighting
neural stacking
continuous odds polling
synthetic historical odds reconstruction
```

---

# 22. Exact decisions now closed

## C1 — Base Market Consensus usability

```text
CLOSED

MARKET_CONSENSUS
→ may be enabled now with EQUAL_WEIGHT
```

No learned-weight activation required.

## C2 — Probability construction

```text
CLOSED

real timestamp-valid canonical 1X2 evidence
→ multiplicative de-vig
→ equal arithmetic pool
→ HOME/DRAW/AWAY probabilities
```

## C3 — Book-count producibility

```text
CLOSED

0 canonical quotes
→ UNAVAILABLE

>=1 canonical quote
→ Prediction may be PRODUCED

NO_FIXED_MIN_BOOKMAKERS_JUSTIFIED
```

## C4 — Canonical vote identity

```text
CLOSED AS REQUIREMENT

1 canonical bookmaker
×
1 canonical 1X2 market
×
1 cutoff
→ maximum one vote
```

Exact schema is not closed here.

## C5 — Capture configuration

```text
CLOSED FOR INITIAL RESEARCH OPERATION

T-6h
T-60m
T-30m
```

No `T-15m`.

No continuous polling.

## C6 — Prediction production granularity

```text
CLOSED

one completed real capture batch/window
→ at most one Market Consensus prediction version for that batch/cutoff

not
one raw quote insert → one Prediction
```

## C7 — Historical immutability

```text
CLOSED

new evidence
→ new version

old Prediction
→ immutable
```

## C8 — Learned challenger methodology

```text
CLOSED METHODOLOGICALLY

canonical bookmaker
availability-conditioned
nonnegative simplex linear pool

fit
→ log-loss

regularization
→ L2 toward equal/effective parent

hierarchy
→ GLOBAL → LEAGUE → SEASON
```

## C9 — Learned-weight activation

```text
CLOSED SEMANTICALLY
OPEN EMPIRICALLY

profile exists
!=
profile ACTIVE
```

No arbitrary sample-count threshold.

## C10 — Runtime fallback

```text
CLOSED

ACTIVE SEASON
→ ACTIVE LEAGUE
→ ACTIVE GLOBAL
→ EQUAL_WEIGHT
```

## C11 — Pre-ticket empirical phase

```text
CLOSED

PRE-TICKET PHASE 3
→ NOT REQUIRED
```

## C12 — Ticket readiness

```text
CLOSED

READY_FOR_TICKET
```

---

# 23. Implementation requirements recommended to F008

F008 should define the ticket around behavior/invariants, leaving exact implementation mapping to F009.

Required ticket outcomes should include:

## 23.1 Usable equal-weight Market Consensus

The technique must be usable with:

```text
real timestamp-valid canonical market evidence
multiplicative de-vig
equal weighting
HOME/DRAW/AWAY output
```

## 23.2 Canonical bookmaker identity

FS-013 must make bookmaker-specific statistical voting use one economic bookmaker identity across raw providers.

Raw source evidence remains preserved.

## 23.3 Canonical 1X2 market identity

Equivalent raw provider market identities must map to one statistical 1X2 voting identity.

## 23.4 One-vote invariant

```text
1 canonical bookmaker
×
1 canonical 1X2 market
×
1 cutoff
→ maximum one vote
```

## 23.5 Bounded capture evidence acquisition

FS-013 must permit distinct deliberate capture opportunities:

```text
T-6h
T-60m
T-30m
```

for eligible research Matches.

No continuous polling is required.

## 23.6 Real observation persistence

Every successful planned acquisition must preserve real raw observations with temporal provenance.

Repeated unchanged prices at a later real acquisition remain new observations.

## 23.7 Window/capture diagnostics

Evidence should remain auditable enough to distinguish at least:

```text
attempted/successful
empty
unchanged
bookmaker missing
market missing
failed
not attempted
window missed
freshness / observation age
canonical bookmaker count
```

Exact persistence fields belong to F009.

## 23.8 Versioned Prediction semantics

Each completed real capture batch should be capable of producing one new versioned `MARKET_CONSENSUS` Prediction for its own cutoff/window.

Old Predictions remain immutable.

## 23.9 Learned-profile lifecycle capability

To the extent F008 decides the weighting lifecycle belongs in the same ticket, the system should support:

```text
candidate/stored profile
ACTIVE state distinct from existence
hierarchical resolution
equal fallback
```

Initial legitimate runtime can have:

```text
no ACTIVE learned profile
→ EQUAL_WEIGHT effective
```

## 23.10 Automatic, auditable activation semantics

No hidden manual preference should silently decide which learned hierarchy level is used.

Resolution must be deterministic and auditable:

```text
ACTIVE SEASON
else ACTIVE LEAGUE
else ACTIVE GLOBAL
else EQUAL
```

The precise evaluator/job/profile persistence mapping is F009 work.

## 23.11 Evidence accumulation

Operation after FS-013 should automatically accumulate enough provenance for future scientific evaluation:

```text
capture horizon
actual observed_at
canonical bookmaker panel
probability vector
resolved outcome
profile/equal configuration
```

without fabricating missing history.

## 23.12 Quota safety

Research capture must remain bounded by:

```text
actual account quota
mandatory reserve
normal pipeline needs
```

and must not become continuous polling.

---

# 24. Empirical questions intentionally deferred

These remain scientific questions after implementation.

They do not prevent ticket creation.

## Capture questions

```text
Does T-30 add enough value beyond T-60 to justify keeping both?

Can T-60 eventually be removed?

Can T-30 eventually be removed?

Does T-6h provide useful movement/incremental-information evidence?

What is the minimum evidence-backed future window subset?
```

## Weighting questions

```text
Does the regularized weighted pool beat EQUAL_WEIGHT OOS?

Which lambda does future chronological evidence select?

Does a GLOBAL profile ever become ACTIVE?

Does any LEAGUE child provide additional OOS value?

Does any SEASON child provide additional OOS value?

Are learned weights stable through time?

Does linear weighting degrade calibration?

Does missing-bookmaker behavior undermine generalization?

Does EQUAL_WEIGHT remain permanently superior?
```

None is required to enable the base technique.

---

# 25. Falsification and null outcomes

Future evidence must be allowed to conclude:

```text
KEEP_EQUAL_WEIGHT
```

The challenger is not required to win.

Also valid:

```text
INSUFFICIENT_EVIDENCE_FOR_WEIGHT_ACTIVATION

WEIGHTED_POOL_NO_OOS_IMPROVEMENT

WEIGHTED_POOL_UNSTABLE

CHILD_PROFILE_INSUFFICIENT
→ fallback parent

CALIBRATION_DEGRADED
→ do not activate

NO_FIXED_THRESHOLD_JUSTIFIED
```

Capture research may also conclude that the initial three-window acquisition set can be reduced.

For example:

```text
T-6h + T-60m
```

or:

```text
T-6h + T-30m
```

if prospective evidence supports the simplification.

Failure of learned weighting to activate does **not** falsify Market Consensus itself.

It means:

```text
EQUAL_WEIGHT
→ remains effective method
```

---

# 26. Durable bibliography

## Provider / API-Football sources

### P1 — API-Football documentation

**Title:** API-Football - Documentation
**Version observed:** v3.9.3 (Current)
**Accessed:** 2026-09-08
**URL:** https://www.api-football.com/documentation-v3

### P2 — API-SPORTS provider guide

**Title:** How to Get Started with API-Football: The Complete Beginner's Guide
**Publisher:** API-SPORTS / API-Football
**Published:** 2026-03-13
**URL:** https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide

### P3 — API quota optimization

**Title:** How to Optimize API-SPORTS Calls and Quota Usage
**Publisher:** API-SPORTS
**Published:** 2026-07-27
**URL:** https://www.api-football.com/news/post/how-to-optimize-api-sports-calls-and-quota-usage

### P4 — API rate limits

**Title:** How Ratelimit Works
**Publisher:** API-SPORTS
**Published:** 2026-06-12
**URL:** https://www.api-football.com/news/post/how-ratelimit-works

### P5 — API-Football pricing

**Title:** API-Football Pricing
**Accessed:** 2026-09-08
**URL:** https://www.api-football.com/pricing

---

## Forecast pooling / statistical methodology

### S1

**Authors:** John Geweke; Gianni Amisano
**Title:** Optimal prediction pools
**Journal:** Journal of Econometrics, 164(1), 130–141
**Year:** 2011
**DOI:** https://doi.org/10.1016/j.jeconom.2011.02.017
**Publisher:** https://www.sciencedirect.com/science/article/pii/S0304407611000455

### S2

**Authors:** Francis X. Diebold; Minchul Shin; Boyuan Zhang
**Title:** On the aggregation of probability assessments: Regularized mixtures of predictive densities for Eurozone inflation and real interest rates
**Journal:** Journal of Econometrics, 237(2), 105321
**Year:** 2023
**DOI:** https://doi.org/10.1016/j.jeconom.2022.06.008
**Open manuscript:** https://arxiv.org/abs/2012.11649
**NBER:** https://www.nber.org/papers/w29635

### S3

**Authors:** Francis X. Diebold; Minchul Shin
**Title:** Machine learning for regularized survey forecast combination: Partially-egalitarian LASSO and its derivatives
**Journal:** International Journal of Forecasting, 35(4), 1679–1691
**Year:** 2019
**DOI:** https://doi.org/10.1016/j.ijforecast.2018.09.006
**NBER:** https://doi.org/10.3386/w24967

### S4

**Authors:** Tilmann Gneiting; Adrian E. Raftery
**Title:** Strictly Proper Scoring Rules, Prediction, and Estimation
**Journal:** Journal of the American Statistical Association, 102(477), 359–378
**Year:** 2007
**DOI:** https://doi.org/10.1198/016214506000001437

### S5

**Authors:** Roopesh Ranjan; Tilmann Gneiting
**Title:** Combining Probability Forecasts
**Journal:** Journal of the Royal Statistical Society: Series B, 72(1), 71–91
**Year:** 2010
**DOI:** https://doi.org/10.1111/j.1467-9868.2009.00726.x
**Publisher:** https://academic.oup.com/jrsssb/article/72/1/71/7076442

### S6

**Authors:** Véronique Genre; Geoff Kenny; Aidan Meyler; Allan Timmermann
**Title:** Combining expert forecasts: Can anything beat the simple average?
**Journal:** International Journal of Forecasting, 29(1), 108–121
**Year:** 2013
**DOI:** https://doi.org/10.1016/j.ijforecast.2012.06.004

### S7

**Authors:** Yuling Yao; Gregor Pirš; Aki Vehtari; Andrew Gelman
**Title:** Bayesian Hierarchical Stacking: Some Models Are (Somewhere) Useful
**Journal:** Bayesian Analysis, 17(4), 1043–1071
**Year:** 2022
**DOI:** https://doi.org/10.1214/21-BA1287
**Repository:** https://research.aalto.fi/en/publications/bayesian-hierarchical-stacking-some-models-are-somewhere-useful/

### S8

**Authors:** Kajal Lahiri; Huaming Peng; Yongchen Zhao
**Title:** Online learning and forecast combination in unbalanced panels
**Journal:** Econometric Reviews, 36(1–3), 257–288
**Year:** 2017
**DOI:** https://doi.org/10.1080/07474938.2015.1114550

### S9

**Authors:** Carlos Capistrán; Allan Timmermann
**Title:** Forecast Combination With Entry and Exit of Experts
**Journal:** Journal of Business & Economic Statistics, 27(4), 428–440
**Year:** 2009
**DOI:** https://doi.org/10.1198/jbes.2009.07211

### S10

**Authors:** Chris Fraley; Adrian E. Raftery; Tilmann Gneiting
**Title:** Calibrating Multimodel Forecast Ensembles with Exchangeable and Missing Members Using Bayesian Model Averaging
**Journal:** Monthly Weather Review, 138(1), 190–202
**Year:** 2010
**DOI:** https://doi.org/10.1175/2009MWR3046.1

### S11

**Author:** Leonard J. Tashman
**Title:** Out-of-sample tests of forecasting accuracy: an analysis and review
**Journal:** International Journal of Forecasting, 16(4), 437–450
**Year:** 2000
**DOI:** https://doi.org/10.1016/S0169-2070(00)00065-0

### S12

**Authors:** Dimitris N. Politis; Joseph P. Romano
**Title:** The Stationary Bootstrap
**Journal:** Journal of the American Statistical Association, 89(428), 1303–1313
**Year:** 1994
**DOI:** https://doi.org/10.1080/01621459.1994.10476870

### S13

**Authors:** Dimitris N. Politis; Halbert White
**Title:** Automatic Block-Length Selection for the Dependent Bootstrap
**Journal:** Econometric Reviews, 23(1), 53–70
**Year:** 2004
**DOI:** https://doi.org/10.1081/ETC-120028836

**Correction:** Andrew Patton; Dimitris N. Politis; Halbert White
**Title:** Correction to “Automatic Block-Length Selection for the Dependent Bootstrap” by D. Politis and H. White
**Journal:** Econometric Reviews, 28(4), 372–375
**Year:** 2009
**DOI:** https://doi.org/10.1080/07474930802459016

### S14

**Authors:** Francis X. Diebold; Roberto S. Mariano
**Title:** Comparing Predictive Accuracy
**Journal:** Journal of Business & Economic Statistics, 13(3), 253–263
**Year:** 1995
**DOI:** https://doi.org/10.1080/07350015.1995.10524599

### S15

**Author:** Edward Wheatcroft
**Title:** Evaluating probabilistic forecasts of football matches: the case against the Ranked Probability Score
**Journal:** Journal of Quantitative Analysis in Sports, 17(4), 273–287
**Year:** 2021
**DOI:** https://doi.org/10.1515/jqas-2019-0089
**Repository:** https://researchonline.lse.ac.uk/id/eprint/111494/

---

# 27. Research coverage matrix

| Area | Status | Final disposition |
|---|---|---|
| current local Market Consensus behavior | **CLOSED** | strict timestamp validity; multiplicative; equal-weight current baseline |
| historical/near evidence inventory | **CLOSED** | 29 independent resolved Matches; near evidence insufficient |
| capture defect | **CLOSED** | scheduler wake does not create repeated market states after fulfillment |
| provider pre-match odds contract | **CLOSED ENOUGH** | `/odds`, targeted retrieval, request/page accounting |
| provider refresh/availability | **CLOSED ENOUGH** | nominal ~3h update; 7-day history; missingness not guaranteed/explained |
| initial acquisition windows | **CLOSED** | T-6h / T-60m / T-30m |
| T-15m | **CLOSED** | excluded |
| continuous polling | **CLOSED** | not required / not recommended |
| base equal-weight usability | **CLOSED** | usable immediately once ticket invariants exist |
| fixed minimum bookmakers | **CLOSED** | no fixed minimum justified |
| canonical bookmaker identity | **CLOSED AS REQUIREMENT** | required in ticket; schema deferred to F009 |
| canonical 1X2 identity | **CLOSED AS REQUIREMENT** | required in ticket; schema deferred to F009 |
| Prediction per raw quote | **CLOSED** | rejected |
| Prediction per completed capture batch/window | **CLOSED** | required conceptual semantics |
| Prediction immutability/versioning | **CLOSED** | new evidence → new version; old immutable |
| weighting challenger | **CLOSED METHODOLOGICALLY** | availability-conditioned simplex pool |
| weighting objective | **CLOSED** | multiclass log-loss |
| weighting regularization | **CLOSED** | L2 toward equal/effective parent |
| weighting hierarchy | **CLOSED** | GLOBAL → LEAGUE → SEASON |
| missing bookmaker handling | **CLOSED** | real available panel; renormalize weights; no imputation |
| freshness vs reliability | **CLOSED** | freshness gate first; reliability second |
| chronological evaluation | **CLOSED** | nested expanding-window forward validation |
| uncertainty | **CLOSED METHODOLOGICALLY** | stationary block bootstrap paired loss differences |
| 95% bootstrap activation CI | **PROJECT METHODOLOGICAL DECISION** | upper endpoint < 0, not universal truth |
| universal match-count activation threshold | **REJECTED** | NO_FIXED_THRESHOLD_JUSTIFIED |
| universal bookmaker-count threshold | **REJECTED** | NO_FIXED_THRESHOLD_JUSTIFIED |
| numerical universal weight-instability cutoff | **NOT FROZEN** | empirical ambiguity blocks ACTIVE, not ticket |
| learned-weight activation now | **NOT JUSTIFIED** | equal fallback |
| future empirical calibration | **DEFERRED BY DESIGN** | post-implementation |
| pre-ticket Phase 3 | **NOT REQUIRED** | acquisition mechanism must exist first |
| ticket readiness | **READY** | READY_FOR_TICKET |

---

# 28. Ticket-readiness handoff

## Research status

```text
RESEARCH STATUS
→ COMPLETE ENOUGH FOR TICKET
```

## Required base capability

```text
MARKET_CONSENSUS usable now
→ YES
```

with:

```text
multiplicative de-vig
+
EQUAL_WEIGHT
```

## Evidence acquisition

Initial bounded configuration:

```text
T-6h
T-60m
T-30m
```

## Canonical identity

```text
REQUIRED IN FS-013
```

for both:

```text
canonical bookmaker
canonical 1X2 market
```

## Learned weighting

```text
methodology
→ CLOSED

current ACTIVE evidence
→ INSUFFICIENT

effective runtime
→ EQUAL_WEIGHT
```

## Future calibration

```text
POST-IMPLEMENTATION
NOT A TICKET BLOCKER
```

## Pre-ticket Phase 3

```text
NOT REQUIRED
```

## Ticket readiness

```text
READY_FOR_TICKET
```

Next process step:

```text
MAIN CHAT
→ F008 TICKET DEFINITION
→ then F009 preflight for exact implementation mapping
```

---

# 29. Integrity audit

## Research-process integrity

```text
Phase 1 accepted?
→ YES

Phase 2A accepted?
→ YES

Phase 2B accepted?
→ YES

Deep Research used?
→ NO

new web research performed in final integration?
→ NO

provider calls made?
→ NO

checkout re-inspected?
→ NO

DB re-inspected?
→ NO

local empirical Phase 3 executed?
→ NO

code modified?
→ NO

migration designed?
→ NO

ticket created?
→ NO

Planka created?
→ NO
```

## Evidence integrity

```text
missing odds synthesized?
→ NO

historical latest quote backdated?
→ NO

post-kickoff quote accepted as earlier evidence?
→ NO

same bookmaker allowed multiple statistical votes?
→ NO — final contract forbids it

same 1X2 market allowed multiple equivalent votes?
→ NO — final contract forbids it

same later price treated as "not observed"?
→ NO

one raw OddsObservation insert mapped conceptually to one Prediction?
→ NO
```

## Statistical integrity

```text
EQUAL_WEIGHT preserved as baseline?
→ YES

EQUAL_WEIGHT preserved as fallback?
→ YES

current 29 Matches used to activate learned weights?
→ NO

MIN_MATCHES invented?
→ NO

MIN_BOOKMAKERS invented?
→ NO

universal numeric stability threshold invented?
→ NO

ROI/profit used as fit objective?
→ NO

95% bootstrap activation criterion labelled project decision?
→ YES
```

## Product-decision integrity

```text
future calibration treated as pre-ticket blocker?
→ NO

pre-ticket Phase 3 required?
→ NO

capture mechanism required before evidence can accumulate?
→ YES

ticket readiness blocked by inactive learned weights?
→ NO
```

---

# 30. Final research disposition

```text
FS-013
→ MARKET_CONSENSUS

Research
→ COMPLETE

Default usable method
→ MULTIPLICATIVE + EQUAL_WEIGHT

Book-count rule
→ 0 canonical quotes = UNAVAILABLE
→ >=1 canonical quote may PRODUCE
→ no fixed minimum bookmaker threshold

Capture evidence configuration
→ T-6h / T-60m / T-30m

Canonical identity
→ REQUIRED IN TICKET

Prediction lifecycle
→ one version per completed real capture batch/window
→ old Predictions immutable

Learned weighting
→ methodology closed
→ current activation unsupported
→ equal fallback until/if evidence gates pass

Future calibration
→ POST-IMPLEMENTATION EMPIRICAL EVIDENCE
→ NOT TICKET BLOCKER

Pre-ticket Phase 3
→ NOT REQUIRED

Ticket readiness
→ READY_FOR_TICKET
```

**STOP — NEXT: MAIN CHAT / F008 TICKET DEFINITION.**
