# Finsport — MVP post-downtime reconciliation & quota research handoff

**Artifact:** `Finsport_MVP_post_downtime_reconciliation_quota_research_handoff.md`
**Research date:** 2026-09-15
**Project:** Finsport
**Stage:** Operational MVP Closure / Experimental Readiness
**Baseline audited:** `master` @ `4d009136921a1526b3440a40c70a5d0a1cd4f7f1`
**Baseline audit timestamp:** `2026-09-15T13:05:15-05:00`
**Research mode:** local checkout + local persisted DB/runtime evidence + bounded empirical probes + targeted official web research
**Deep Research:** not used
**Product code modified during research:** no
**Permanent project sources modified during research:** no
**Real betting:** prohibited / out of scope

## Research authority and evidence

This handoff is the product/research contract for the next implementation ticket. It must be read together with the current durable Finsport sources, especially F001/F002/F003/F004/F006/F009/F010 and the FS-016 final handoff. Where this handoff defines a deliberate product delta from the post-FS-016 runtime, that delta is intentional and must be implemented rather than silently reconciled back to the old behavior.

The local audit covered, at minimum:

- `football/capture/planner.py`
- `football/capture/executor.py`
- `football/capture/contracts.py`
- `football/pipeline/service.py`
- `football/capital/runtime.py`
- `football/prediction/service.py`
- `football/prediction/settlement.py`
- `football/sync.py`
- `football/maintenance.py`
- `football/models.py`
- current-season historical-market recovery paths and commands
- scheduler/settings defaults
- relevant tests and runtime audit entities

Empirical artifacts used:

- `MVP_post_downtime_local_empirical_audit.txt`
- `MVP_post_downtime_phase2_targeted_audit.txt`
- `MVP_post_downtime_phase2_code_slices.txt`
- `MVP_post_downtime_phase3_timing_audit.txt`
- `MVP_post_downtime_phase3_capital_planner_contract.txt`
- `MVP_post_downtime_weekend_12_13_audit.txt`
- `MVP_recent_wake_efficiency_14_15.txt`
- `MVP_recent_wake_code_paths.txt`
- `MVP_api_football_real_batch_probe.txt`

No additional product question, local diagnostic, or provider call is required before opening the implementation ticket. One bounded live batch probe was attempted during research; it made exactly one API-Football call with zero retry, but the selected historical fixture IDs were denied under the current plan. Therefore successful `ids<=20` behavior remains an implementation/UAT acceptance item using current-plan-accessible fixtures, not an unresolved product decision.

---

# 1. Executive disposition

The research finds a **real implementation gap**, but the product contract is now closed.

The current runtime has the right durable building blocks — single scheduler ownership, temporal odds evidence, Prediction/Decision provenance, Capital-v2 OPEN positions, result-known chronology, historical-market evidence, current-season recovery, and quota headers — but several policies are still inherited from a generic capture planner and do not match the actual Finsport MVP workflow.

The key mismatch is that the current capture layer treats many provider operations as if every item might consume the same large worst-case request budget. At the same time, generic result refresh spends scarce API-Football quota pursuing outcomes for all past matches, even though only **OPEN Capital positions** require urgent result knowledge. This creates artificial starvation (`INSUFFICIENT_WORST_CASE_BUDGET`), delays protected odds windows, delays results, and makes the fixed `12`-attempt ceiling influence admission far beyond its legitimate role as a safety circuit breaker.

The desired MVP operational flow is instead:

```text
first operational opportunity of local day
→ discover/ensure today's fixtures once
→ persist fixture IDs + kickoff times
→ derive all due windows locally

new sporting evidence / new target Match
→ run only sporting model work whose evidence identity changed

T-6h / T-60m
→ capture if quota surplus allows
→ useful research evidence, not quota-protected ahead of critical work

T-30
→ protected capture
→ Prediction / Decision
→ Capital execution decision

Decision BET + capacity available
→ place simulated Position
→ Position OPEN

Decision BET + no lane/cash at T-30
→ persist pending pre-match opportunity
→ wait for capacity until strictly before kickoff
→ retry placement on later wakes without occupying a lane while pending
→ if capacity becomes available, place using valid T-30 evidence for the current MVP
→ if kickoff arrives first, expire without placement

Position OPEN
→ first result check at T+130
→ batch due OPEN fixture IDs, up to 20/request
→ canonical result/status drives SETTLED/VOID
→ release lane/capital
→ if host was off, overdue OPEN debt is due on first wake after restart

Match with no Position OPEN
→ no urgent per-match result polling
→ recover result later from API-Football surplus batch and/or
   twice-weekly Football-Data current-season reconciliation

provider quota
→ observe response headers
→ calculate protected reserve dynamically from actual critical work still pending
→ reserve generally decreases as critical work completes
→ only surplus quota may be spent on optional/deferrable work
```

The recommended scheduler target after due/event-driven gating is **5 minutes**. Current post-hotfix evidence shows no-work wakes are already cheap enough to make this practical, but the ticket must first prevent unchanged expensive/model/provider work from being repeated merely because Beat fired.

The result finish hint is frozen at **kickoff + 130 minutes** for urgent OPEN-position result debt. This is a scheduling hint only. It never asserts that a match is finished. Canonical provider state remains authoritative.

The current pre-match placement deadline is **kickoff**. Finsport must not let a delayed pre-match candidate turn accidentally into an in-play strategy. Betting after kickoff is a separate future research domain.

The current MVP execution-price fallback is the persisted **T-30 quote** if capacity becomes available later in the T-30→kickoff window. A future execution-quote capability should investigate API-Football `/odds/live` and/or reactivated Inkabet to obtain a fresher quote near actual placement. That future enhancement is not required to close this MVP ticket.

The implementation should be **one cohesive ticket**, because scheduler frequency, event/due gating, pending Capital capacity, OPEN result settlement, dynamic quota reserve, call attribution, and historical reconciliation are all parts of one operational lifecycle. Splitting them would preserve contradictory intermediate states.

---

# 2. Current local lifecycle map

## 2.1 CURRENT scheduler ownership

There is exactly one automatic scheduler owner:

```text
Celery Beat
→ football.pipeline.wake
→ run_pipeline()
→ capture
→ Prediction/Decision
→ result evaluation
→ Capital-v2 runtime
→ periodic maintenance
```

There must remain exactly one owner. The ticket must not add a second odds scheduler, result scheduler, Inkabet scheduler, Capital scheduler, readiness scheduler, or reconciliation scheduler.

## 2.2 CURRENT prospective capture

The current planner creates work for:

```text
RESULT_REFRESH
FIXTURE_REFRESH
ODDS_CAPTURE market-t6h
ODDS_CAPTURE market-t60m
ODDS_CAPTURE market-t30m
```

It also creates many durable non-executed work items such as `NOT_DUE`, `ALREADY_FULFILLED`, `MISSED_WINDOW`, `QUOTA_RESERVE`, and `INSUFFICIENT_WORST_CASE_BUDGET`.

The current fixture-discovery path is cadence-slot based and may rediscover dates more than once per local day. This is broader than the MVP needs. Once the day’s fixtures and kickoffs are known, T-6h/T-60/T-30 can be scheduled from PostgreSQL without repeatedly asking the provider what matches exist.

## 2.3 CURRENT Prediction path

Market Consensus candidates are already sensibly tied to completed durable capture batches. Sporting candidates are less efficient: every pipeline wake reconstructs Dixon-Coles, Independent Poisson and Elo candidate sets over upcoming Matches and recomputes evidence identity/basis before `predict_competition_day()` can deduplicate/reuse an existing experiment.

Product target:

```text
sporting models
→ only when target Match/evidence basis/readiness semantics changed

Market Consensus
→ only on new qualifying odds capture evidence

Prediction settlement/evaluation
→ only when new canonical result appears
```

A frequent scheduler wake must not itself be interpreted as new evidence.

## 2.4 CURRENT Capital path

Post-FS-016 CURRENT behavior is:

```text
successful final market-t30m capture
→ DIXON_COLES + MODAL_ALL execution basis
→ capacity/funding gate
→ OPEN or terminal non-placement
→ later canonical result debt
→ result_known_at
→ SETTLED / VOID
```

Important current mismatch: when a T-30 candidate cannot be placed because capacity is unavailable, the current architecture terminalizes that event (`EXPIRED_CAPACITY`). The new product contract requires a **pending pre-match opportunity** until kickoff.

Another current ordering issue is:

```text
reconcile_execution_events
→ settle_locally_known_open_positions
→ refresh_open_result_debt
```

With pending T-30 candidates, this can require two wakes: one wake obtains/settles the old OPEN position after placement reconciliation has already happened, and only the next wake can use the freed lane. The ticket must ensure that due settlement/result recovery can release lane/cash before pending placement reconciliation in the same wake.

## 2.5 CURRENT quota/admission path

Current defaults include:

```text
FOOTBALL_CAPTURE_MANDATORY_RESERVE = 10
FOOTBALL_CAPTURE_MAX_PROVIDER_ATTEMPTS = 12
API_FOOTBALL_MAX_RETRIES = 2
FOOTBALL_CAPTURE_WAKE_SECONDS = 900
FOOTBALL_CAPTURE_RESULT_DELAY_MINUTES = 120
FOOTBALL_CAPTURE_RESULT_CADENCE_MINUTES = 360
```

`worst_operation_cost` is derived from a generic combination of maximum pages, retries and provider-attempt ceiling. Every PLANNED item can receive this same large `estimated_max_cost`. This is the root of many false admission blocks.

The ticket must replace that admission principle with a dynamic calculation based on finite critical obligations actually remaining in the current provider quota epoch.

---

# 3. Post-downtime Match/result findings

## 3.1 OPEN Capital positions are already durable debt

FS-016 correctly established:

```text
Position already OPEN
+ host shuts down
+ match finishes while host is down
→ Position remains durable
→ restart makes overdue result debt eligible
→ canonical result is learned now, never backdated
→ result_known_at = actual recovery knowledge time
→ settlement releases lane/capital
```

This behavior is mandatory permanently. It remains mandatory if Finsport later moves from simulation to real betting because committed money/exposure already exists.

## 3.2 No bet was placed: do not reconstruct an economic action

For a Match where Finsport never placed a Position:

```text
host downtime
→ match may finish
→ result may be missing locally
→ recover/store result later
→ evaluate pre-existing prospective Prediction/Decision evidence when possible
→ DO NOT create a retroactive placement
```

This remains true even if, after the match, historical sources show that the hypothetical bet would have won.

## 3.3 Generic result refresh has a terminal+blank gap

Outside the special Capital OPEN path, CURRENT planner/executor behavior can strand:

```text
FT / AET / PEN / AWD / WO
+
outcome=""
```

because the Match is first selected as unresolved debt but then marked `STATUS_INELIGIBLE` because its local status is terminal. This is a real correctness gap.

The ticket must make terminal-looking + blank-outcome state explicitly recoverable/reconcilable rather than permanently ineligible.

## 3.4 Missing/unresolved API-Football identity

Generic API-Football refresh currently requires a resolved API-Football `MatchSourceRef`. Local audit found many current-season/completed rows without API-Football refs, but those rows were explained by Football-Data historical/current-season provenance; current future NS Matches had API-Football refs.

Desired behavior is source-aware:

```text
OPEN Position
→ API-Football canonical identity/result path is required
→ unresolved identity is visible debt, not silently replaced

no OPEN Position / historical completeness
→ Football-Data current-season reconciliation may supply historical result provenance
→ no need to spend urgent API-Football quota merely to repair every old non-bet row
```

## 3.5 Status contract

The operational contract is:

| Provider/local status | Finsport action |
|---|---|
| `NS` overdue | If OPEN Position: due result/status recovery at result schedule. If no Position: can wait for batch/historical reconciliation. |
| `1H`, `HT`, `2H`, other live | Never guess result; OPEN debt retries on schedule. |
| `FT` | Settle 1X2 from regulation-time score. |
| `ET` / `P` | Extra-time/penalty phase is not part of Finsport pre-match 90-minute 1X2. If regulation `score.fulltime` is available and contractually usable, the 90-minute outcome is already determinable; implementation must not use extra-time winner. |
| `AET` / `PEN` | Canonical Finsport H/D/A must be derived from regulation `score.fulltime`, not `teams.winner` or aggregate final goals. |
| `AWD` / `WO` | Use explicit provider-supported canonical H/D/A only when reliable; blank remains debt. Never infer. |
| `CANC` / `ABD` | No H/D/A fabrication. OPEN Capital Position becomes VOID, stake released, P&L 0. |
| `PST` | Not settled. Stop high-frequency result polling; wait for updated kickoff/daily reconciliation. |
| `SUSP` | Not settled. Preserve OPEN debt; slower status-aware retry. |

## 3.6 Regulation-time outcome bug

CURRENT `_fixture_outcome()` checks `teams.*.winner` and then top-level `goals`. For `AET`/`PEN`, that can encode the knockout winner rather than the regulation-time 1X2 outcome. Yet the Match model already persists separate `fulltime`, `extratime`, and `penalty` scores.

The implementation must align canonical Finsport H/D/A with the product definition:

```text
HOME / DRAW / AWAY
= result after two 45-minute halves + stoppage
!= extra-time winner
!= penalty-shootout winner
```

IFAB Law 7 defines two equal 45-minute halves and stoppage; IFAB Law 10 treats extra time/penalties as separate winner-determination procedures when a competition requires a winner.

## 3.7 First wake after downtime

Desired first-wake contract:

```text
restart
→ recover/ensure current local-day fixtures if today's discovery missing/stale
→ recompute dynamic protected reserve
→ identify overdue OPEN result debt
→ fetch/settle overdue OPEN debt subject to fixture/T30 critical deadlines
→ evaluate newly-known results
→ reconcile pending pre-kickoff placement opportunities still before kickoff
→ schedule only future due odds work
→ do not replay missed prospective windows as if observed on time
```

If a prospective T-30 window was completely missed while the host was off, it stays prospectively lost.

---

# 4. Prediction/Decision evaluation catch-up

## 4.1 Already-created prospective Predictions

CURRENT `settle_prospective_predictions` provides the correct basic behavior:

```text
Prediction MODE_PROSPECTIVE exists
+ actual_outcome is null
+ Match later obtains canonical outcome
→ settle/evaluate Prediction later
→ actual_outcome + evaluated_at persisted
```

Local audit found no past unresolved prospective evaluation debt at the research snapshot, which supports that this downstream catch-up works in practice once `Match.outcome` exists.

## 4.2 Decisions

Decision rows do not require a second provider call or a separate canonical result source. Their eventual correctness/economic evaluation is derived from persisted Decision/Prediction plus canonical Match outcome. The implementation must not invent a second “Decision result provider” lifecycle.

## 4.3 Automatic late computation is not prospective recovery

Two cases must remain distinct:

```text
A) Prediction/Decision existed before kickoff
→ late result evaluation is honest prospective evaluation

B) Prediction/Decision never existed before kickoff
→ normal automatic downtime recovery must NOT create it as prospective
```

For research, an explicit offline job may compute a missed model/policy result after the fact **only when every required input was genuinely persisted with valid pre-kickoff chronology**. Such output must be unmistakably classified as `BACKTEST`, `LATE_RESEARCH`, or an equivalent non-prospective mode.

It must never:

- become CURRENT prospective evidence;
- create an `OddsObservation` that did not exist;
- create a retroactive Capital execution;
- alter the historical fact that the production runtime missed the opportunity.

Before real betting is ever enabled, any automatic late-runtime research computation must be removed/disabled from the real execution path. Explicit offline backtesting may remain.

---

# 5. Recoverable vs irrecoverable evidence matrix

| Missing / delayed item | Recoverable canonically later? | Recoverable as historical/research evidence? | Can count as prospective? | Contract |
|---|---:|---:|---:|---|
| Match result | Yes | Yes | N/A | OPEN Position: urgent API-Football debt. Non-bet: batch/surplus or Football-Data historical reconciliation. |
| Match status after downtime | Yes | Yes | N/A | Recover current truth; never backdate when Finsport learned it. |
| Sporting Prediction that already existed | N/A | N/A | Yes | It remains prospective; evaluate later when result arrives. |
| Sporting Prediction never computed, but all strict-prior sporting inputs existed | No as missed prospective event | Yes | No | Explicit `LATE_RESEARCH/BACKTEST` only. |
| Market Consensus Prediction already existed | N/A | N/A | Yes | Evaluate later normally. |
| Market Consensus Prediction never computed but required prospective OddsObservations existed before kickoff | No as missed prospective computation | Yes | No | Explicit late research may reuse genuine timestamped observations. |
| Market Consensus Prediction with missing required prospective odds | No | Historical proxy may exist | No | Do not repair prospectively. |
| Decision already persisted | N/A | N/A | Yes | Evaluate/derive outcome later from canonical Match result. |
| Decision never computed but all required pre-kickoff evidence existed | No as missed prospective event | Yes | No | Explicit offline late research only. |
| T-30 OddsObservation missed because host was off | No | Historical price may later exist with imputed time | No | Irrecoverable prospective evidence. |
| T-60 / T-6h missed | No | Historical/research source may partially substitute | No | Record missed/unavailable honestly. |
| Historical real 1X2 price | Yes if source later supplies it | Yes | No | `HistoricalMarketEvidence`, real price + imputed time provenance. |
| Capital placement never made | No | Hypothetical backtest may model it | No | Never create retroactive runtime Position. |
| OPEN Capital result | Yes | Yes | N/A | Mandatory restart catch-up until SETTLED/VOID. |
| Prediction evaluation | Yes | Yes | Evaluation of existing prospective row remains prospective evaluation | Runs after canonical result recovery. |
| Decision evaluation | Yes | Yes | Same provenance as original Decision | Derived from persisted Decision/Prediction + canonical result. |
| `result_known_at` during downtime | No, original knowledge event did not occur | N/A | N/A | Persist actual later recovery time; never backdate. |

The central invariant is:

```text
recover truth when it becomes known
!=
pretend Finsport knew it earlier
```


---

# 6. Weekly current-season reconciliation design

## 6.1 Decision D5: yes, periodic current-season reconciliation is required

The research confirms an implementation gap in current-season historical completeness.

At the audited snapshot:

```text
current-season completed Matches        = 1017
HistoricalMarketEvidence present        = 900
explicit historical unavailable         = 0
historical-market evidence missing      = 117
current-season HistoricalMarketCoverage = no durable coverage rows found
```

The 117 gaps were concentrated in newly completed current-season Matches after the last Football-Data recovery. This is exactly the class of gap a periodic lifecycle should close.

## 6.2 Cadence: twice weekly, source-aligned

The original candidate was weekly. Official Football-Data documentation states that its files are updated **at least twice weekly, Sunday nights and Wednesday nights**. Therefore the better product contract is:

```text
Football-Data current-season reconciliation
→ due after expected Sunday update
→ due after expected Wednesday update
→ one existing scheduler owner
→ idempotent/coverage-driven
```

Implementation does not need a second Beat schedule. `football.pipeline.wake` / existing maintenance ownership should detect whether this capability is due.

Exact clock-hour selection is technical/operational preflight. Product semantics are source-aligned twice-weekly checks, not daily scraping.

## 6.3 Scope per enabled Competition/current Season

Each reconciliation cycle should account for:

```text
completed Matches
→ historical result completeness

historical 1X2 source rows
→ matched evidence or explicit unavailable

source rows
→ consumed / unmatched / ambiguous / conflicting visibility

historical-market coverage
→ current snapshot + counts + source provenance
```

Same unchanged source content should converge to `NO_WORK` or an equivalent idempotent no-delta result.

## 6.4 What this reconciliation is not

It is not:

- a substitute for prospective T-30 capture;
- a way to fabricate `OddsObservation` timestamps;
- a way to create missed Capital positions;
- an urgent settlement path for an OPEN position;
- a second current/live provider scheduler;
- a reason to consume API-Football quota merely because Football-Data was updated.

## 6.5 API-Football interaction

The normal twice-weekly Football-Data import should consume **zero API-Football quota** unless a specific conflict/identity condition requires canonical clarification under a bounded technical path.

Historical 1X2 completion should never call prospective `/odds` to repair history.

## 6.6 Historical/current canonical result semantics

The product authority contract is intentionally asymmetric:

```text
API-Football
→ primary current/live identity and result authority
→ mandatory authority for OPEN Capital settlement chronology

Football-Data
→ authorized secondary historical/current-season recovery source
→ may complete non-bet historical Match/result evidence
→ preserves explicit source provenance
→ must fail closed on identity/result conflict
→ never backdates Capital result knowledge
```

This makes the user's operational requirement possible: if no money/Position was committed, a result missed during downtime may be recovered during the Sunday/Wednesday historical update instead of burning scarce live API quota.

If Football-Data conflicts materially with an existing API-Football canonical result, the reconciliation must expose the conflict rather than silently overwrite the primary source.

---

# 7. Historical odds/result authority contract

## 7.1 Prospective market evidence

Prospective market truth remains:

```text
OddsObservation
→ actually observed by Finsport at that time
→ temporal evidence
→ eligible for prospective MARKET_CONSENSUS / Decision / Capital as governed
```

A missed observation remains missed.

## 7.2 Historical market evidence

When Football-Data later provides real market prices for a Match whose prospective capture was missed:

```text
HistoricalMarketEvidence
source_price_is_real = true
timestamp_is_imputed = true
time_semantics = ASSUMED_...
evidence_class = research/historical only
```

This is scientifically useful historical evidence, but it does not prove Finsport observed that price prospectively.

Therefore prohibited:

```text
HistoricalMarketEvidence
→ fake OddsObservation
→ fake prospective Market Consensus
→ fake Decision time
→ fake Capital placement
```

## 7.3 Result authority and chronology

For an actual OPEN Position:

```text
result must be learned through the current canonical runtime path
→ persist actual result_known_at
→ settle only from canonical evidence
```

For a Match with no OPEN Position:

```text
API-Football same-day batch if surplus quota
OR
Football-Data twice-weekly historical reconciliation
```

Both can result in canonical historical completeness, but only the real-time/restart Capital path carries settlement chronology.

## 7.4 Normal-time 1X2 contract

Finsport's H/D/A market means:

```text
90 minutes
+ referee-added stoppage time
```

It excludes:

```text
extra time
penalty shoot-out
```

For API-Football responses whose match proceeds to `ET`, `P`, `AET` or `PEN`, implementation must consume the regulation/full-time score component appropriate to this 90-minute market and must not use the final knockout winner as 1X2 outcome.

---

# 8. Current result-delay implementation

## 8.1 Generic Match result refresh CURRENT

Current configured defaults:

```text
first eligibility = kickoff + 120 minutes
logical result cadence = 360 minutes
scheduler wake = 15 minutes
```

The planner currently considers every enabled Match with blank outcome after the delay, excluding OPEN Capital positions. Each Match becomes an individual `RESULT_REFRESH` item. The logical identity is cadence-slot based.

The generic path has three important problems:

1. it spends quota on non-bet Matches that do not need urgent knowledge;
2. its admission is distorted by the fixed worst-case request cost;
3. terminal status + blank outcome may be marked ineligible forever.

## 8.2 Capital OPEN result debt CURRENT

FS-016 has a separate path for OPEN positions. It:

- selects OPEN Positions whose result debt is due;
- requires resolved API-Football fixture identity;
- orders/fairly admits debt;
- groups fixture IDs in chunks of up to 20;
- calls `/fixtures?ids=...`;
- synchronizes canonical Match state;
- persists `CapitalResultObservation` / `result_known_at`;
- settles affected Capital configs;
- catches overdue OPEN debt after restart.

This is the right structural basis for urgent result work and should become the primary live result lifecycle.

## 8.3 Restart CURRENT

The OPEN path already supports restart catch-up. The generic path can also see old overdue NS rows, but its cadence/admission/status rules can delay or strand them. The new product design intentionally removes the need for urgent generic per-Match recovery when no Position exists.

## 8.4 Current safety budgets

Current settings:

```text
mandatory reserve        = 10
max provider attempts    = 12
max retries              = 2
```

These settings must not survive as the primary admission model. A fixed hard circuit breaker may remain, but it must be secondary to a dynamic finite-work budget.

---

# 9. Empirical finish-delay evidence

## 9.1 What could and could not be measured

`Match.observed_at` is not a faithful timestamp for first terminal knowledge across imported/current rows, so it must not be used to fabricate a match-duration distribution.

The reliable empirical quantity available from Capture/WorkItem audit is:

```text
kickoff
→ when Finsport actually made its first result provider attempt
→ when that attempt resolved canonical result
```

This is an operational acquisition delay, not the physical duration of the football match.

## 9.2 Broad 14-day decomposition

For 157 resolved result-refresh cases:

```text
due at T+120 → first planned/seen
median  = 9.63 min
p90     = 717.98 min
p95     = 1513.99 min
max     = 2127.35 min

first seen → actual provider attempt
median  = 15.14 min
p90     = 197.74 min
p95     = 255.00 min
max     = 1205.70 min

actual provider attempt → resolution
median  = 0 min
p90     = 0 min
p95     = 0 min
max     = 195 min
```

The long first two tails are contaminated by host downtime and planner/quota admission. They do **not** show that the provider normally takes many hours to publish a result.

Empirical classification found:

```text
likely host/pipeline gap >30m       = 21
planner/quota wait >30m after seen = 62
```

The first-item result status distribution included:

```text
INSUFFICIENT_WORST_CASE_BUDGET = 93
SUCCESS                        = 50
QUOTA_RESERVE                  = 13
FAILED_PROVIDER                = 1
```

This is direct evidence that the admission model, not only external data availability, caused result delay.

## 9.3 Weekend September 12–13

Provider quota evidence:

```text
2026-09-12 UTC
attempts_total = 55
last observed remaining = 45/100

2026-09-13 UTC
attempts_total = 76
last observed remaining = 24/100
```

On September 13 there was a stored header transition from remaining `44` at 00:01 UTC to `98` at 00:16 UTC. Runtime must therefore treat observed provider headers as truth and must not manufacture a reset merely because the local clock crossed an assumed boundary.

The Saturday workload was heavily affected by known bugs/performance issues and conservative admission. The Sunday continuous-operation sample is more informative. Excluding late fixtures whose due/result acquisition fell after the user shut down the host, most first successful result acquisitions occurred roughly in the T+121 to T+166 range; the clean operational median was around T+136.

Again, this means:

```text
at first actual query in that range
→ provider usually already had a resolvable result
```

It does not mean the football match itself lasted 136 minutes.

## 9.4 Why T+130 is selected

A T+130 first check:

- avoids clearly premature checks for ordinary regulation matches;
- adds buffer for halftime + stoppage + operational scheduling jitter;
- is supported by the Sunday sample where many first calls at ~T+121–T+140 resolved immediately;
- remains early enough to release Capital lanes/cash without the multi-hour delay caused by the old admission queue;
- avoids building a competition-format duration engine.

IFAB's Laws establish 2×45-minute halves, halftime no longer than 15 minutes, and added time. Extra time/penalties are separate procedures when competition rules require a winner. Therefore T+130 is a conservative *query hint*, not a football-rule assertion.

---

# 10. Recommended finish-hint/retry contract

## 10.1 First urgent result check

For each unique fixture with at least one OPEN Capital Position:

```text
first_result_check_at = kickoff + 130 minutes
```

If the host starts after that time:

```text
OPEN debt overdue
→ eligible on first pipeline wake after restart
```

No additional T+130 waiting is introduced after restart.

## 10.2 Batch shape

Every due cycle:

```text
unique due OPEN fixture IDs
→ chunk <=20
→ one /fixtures?ids=... request per chunk
```

Multiple configs/positions on the same Match must not multiply provider calls.

API-Football officially documents up to 20 fixture IDs in one `ids` query. Current Capital code already follows this shape. The attempted live probe made exactly one request and zero retries but failed due to current-plan access for the selected old fixture set; successful current-plan batching must be proven in ticket UAT.

## 10.3 Retry cadence

Retry timing is time-based, not Beat-count based. This makes scheduler frequency independently tunable.

Frozen contract:

```text
normal unresolved/live OPEN debt
→ next provider check no earlier than +30 minutes

SUSP
→ next provider check no earlier than +60 minutes

PST
→ stop ordinary 30-minute result polling
→ await updated kickoff/status through fixture reconciliation

provider transient failure
→ at most one immediate bounded retry only when dynamic quota reserve still remains protected
→ otherwise defer to next scheduled +30-minute result opportunity

deterministic 4xx / plan / invalid request
→ no immediate retry loop
→ persist degraded/error state
```

A frequent 5-minute Beat therefore checks eligibility cheaply but does not call API-Football every five minutes for a result.

## 10.4 Terminal behavior

```text
FT
→ derive regulation 1X2
→ SETTLE

ET / P
→ if regulation/fulltime score is validly available, regulation 1X2 is determinable
→ do not wait for knockout winner merely to settle a 90-minute market
→ implementation must validate exact provider score semantics in tests/fixtures

AET / PEN
→ regulation 1X2 from fulltime/regulation component
→ never from final knockout winner

AWD / WO
→ settle only from explicit canonical result semantics
→ blank remains debt

CANC / ABD
→ VOID

PST / SUSP
→ remain unresolved as described above
```

## 10.5 Non-bet result cadence

There is no T+130 per-Match polling requirement for Matches without an OPEN Position.

Their results are filled via:

```text
surplus API-Football quota
→ batched non-bet result reconciliation

and/or

Football-Data Sunday/Wednesday current-season reconciliation
```

If there is no urgent economic exposure, completeness can be delayed without corrupting the experiment.

## 10.6 Pre-match placement deadline

A pending T-30 candidate may only become a Position while:

```text
now < kickoff
```

At or after kickoff:

```text
pending pre-match opportunity
→ EXPIRED / NOT_PLACED
```

Finsport must not use a late Capital lane as an accidental entry into in-play betting.


---

# 11. Current quota accounting

## 11.1 Provider authority

Quota authority is the provider response header state observed on normal API-Football calls:

```text
x-ratelimit-requests-limit
x-ratelimit-requests-remaining
X-RateLimit-Limit
X-RateLimit-Remaining
```

API-FOOTBALL/API-SPORTS explicitly recommends reading these headers and using remaining quota as an operational management signal. No extra provider call should be made merely to ask “how much quota remains?”.

Current Finsport already persists useful quota fields on `CaptureRun` and `MaintenanceRun`:

```text
quota_basis
quota_limit
quota_remaining_before
quota_remaining_after
quota_observed_at
provider_attempts
provider_pages
provider_retries
```

This foundation should be reused.

## 11.2 Current gap: not all API-Football calls share one durable accounting path

Capital OPEN result refresh can instantiate/use API-Football directly from `football/capital/runtime.py`. Current `quota_state()` reconstructs its view primarily from CaptureRun/MaintenanceRun persisted state. Therefore the next implementation must ensure **every API-Football attempt**, including Capital result batches and future protected capabilities, updates the same durable quota/accounting authority.

There must be no hidden provider consumer whose calls are absent from daily attribution.

## 11.3 Header freshness and reset

The daily quota should be understood as a provider quota epoch, not as a synthetic Finsport local-calendar counter.

Official API-SPORTS family guidance documents a daily reset at 00:00 UTC, while API-Football exposes the current-day remaining value through headers. Local evidence showed a remaining jump shortly after 00:00 UTC rather than exactly on the first stored request after midnight.

Therefore:

```text
provider header observed
→ authoritative remaining

clock says reset should have happened
but no new header proves it
→ do not synthetically reset remaining to full allocation
```

For Peru (`UTC-5`), a 00:00 UTC provider reset corresponds to 19:00 local. Dynamic reserve calculations must protect obligations only until the end of the **current provider quota epoch**; after an observed reset, recalculate against the new epoch. This avoids protecting calls with today’s quota that cannot actually be used until after that quota expires.

## 11.4 Attempt count vs observed quota delta

Persist both concepts:

```text
attempt count
→ what Finsport tried to send

header-observed remaining delta
→ what provider says remains
```

They need not always be identical due to failed requests, proxies, delayed/reset observations, pagination, or calls from another process sharing the same API account/IP context.

The header remains external truth; local attempt accounting remains indispensable for attribution and anomaly diagnosis.

---

# 12. Daily quota attribution

## 12.1 Required capability categories

Every API-Football attempt must be attributable to one of a small stable set of product purposes:

```text
DAILY_FIXTURE_DISCOVERY
ODDS_T30
ODDS_T60
ODDS_T6H
OPEN_RESULT_BATCH
NONBET_RESULT_BATCH
CATALOGUE_OR_SEASON_MAINTENANCE
OTHER_EXPLICIT_MAINTENANCE
FUTURE_EXECUTION_QUOTE   # inactive in current MVP
```

Retry and pagination are dimensions of the parent purpose, not separate opaque consumers.

## 12.2 Minimum per-call/per-operation audit

Persist or expose enough durable information to reconstruct:

```text
provider
quota epoch / observed header timestamp
capability
logical operation identity
endpoint / safe parameter shape
fixture count represented by call
attempt number
page number when relevant
retry number/reason
started/completed time
HTTP/provider outcome class
quota limit header if observed
quota remaining header if observed
CaptureRun / MaintenanceRun / Capital runtime linkage
```

Secrets/API keys must never be included.

## 12.3 Empirical recent consumption

The bounded 14-day attribution found actual provider attempts approximately:

```text
FIXTURE_REFRESH / discovery = 35
ODDS_T30                    = 15
ODDS_T60                    = 30
ODDS_T6H                    = 25
RESULT_REFRESH              = 162
CATALOGUE                   = 22
SEASON_BOOTSTRAP            = 2
```

The outsized generic result-refresh count is not the desired future baseline. Most of those calls were pursuing non-bet results individually. The new lifecycle removes that urgent per-Match polling obligation.

## 12.4 Why daily attribution is a product requirement

The operator must be able to answer:

```text
Did we spend quota on critical work or optional work?
Did a retry loop consume requests?
Did T-30 miss because quota was genuinely insufficient or because admission reserved an exaggerated worst case?
Did Capital result settlement consume hidden calls?
How much protected work remains before provider reset?
How much quota is genuinely free?
```

Without capability attribution, a remaining header alone cannot answer those questions.

---

# 13. Quota priority/reserve recommendation

## 13.1 Decision D12: fixed reserve is rejected

The current pattern:

```text
mandatory reserve = fixed 10
+
worst operation cost may reach 12
```

is not an acceptable product model.

The reserve must be **dynamic and derived from actual critical work still required before the next provider quota reset**.

It is not “keep 10 requests just in case”. It is:

```text
how many minimum provider calls do we still need
so that the rest of today's critical prospective/financial flow cannot be starved?
```

## 13.2 Protected critical work hierarchy

Among due/pending work, protected priority is:

```text
P1  ensure today's fixtures are known
P2  preserve remaining T-30 observations
P3  settle/reconcile due OPEN Capital result debt
P4  all other work from surplus only
```

P4 includes:

```text
T-60
T-6h
non-bet result completion
catalogue/season work not required to discover today's slate
historical/current-season gaps
optional maintenance/research calls
```

A dependency required to make P1 possible is part of P1; routine catalogue maintenance is not.

## 13.3 Dynamic reserve formula

At any planning instant `t`, define:

```text
R(t) = R_fixture(t)
     + R_t30(t)
     + R_open_result(t)
     + R_execution_quote(t)
```

For the current MVP:

```text
R_execution_quote(t) = 0
```

because the MVP uses persisted T-30 evidence for a later pre-kickoff placement. If a future API-Football live execution-quote capability is enabled, its real outstanding calls must be incorporated at that time.

### `R_fixture(t)`

Minimum number of API-Football physical calls/pages still required to finish the current local day’s mandatory fixture discovery **before the current provider quota epoch ends**.

Rules:

- if today's fixture discovery is already complete and canonical: `0`;
- if discovery has not happened: reserve its minimum known call/page cost;
- do not reserve repeated 12-hour rediscovery;
- a recovery rediscovery caused by a proven gap/identity contradiction is added only when the recovery obligation actually exists.

### `R_t30(t)`

Minimum physical calls/pages still required for **unsatisfied protected T-30 windows whose deadlines occur before the next provider reset**.

Rules:

- count only Matches that still need a T-30 API-Football capture in the current quota epoch;
- a fulfilled T-30 immediately drops out of reserve;
- a definitively missed/expired T-30 drops out; it is recorded as lost rather than reserving forever;
- T-60/T-6h do not inflate protected reserve;
- if the endpoint/query can legitimately serve multiple needed fixtures in one physical request, reserve the actual minimal batched/page cost rather than one artificial unit per Match.

### `R_open_result(t)`

Minimum next-check calls required for unique OPEN fixtures whose next result-attempt deadline falls before provider reset.

With `/fixtures?ids=` batching:

```text
R_open_result(t)
= ceil(unique_due_open_fixture_ids / 20)
```

for a single due result-attempt cycle, adjusted if plan/coverage constraints prove a smaller valid batch.

Do not multiply reserve by:

- number of Capital configs on the same Match;
- number of positions sharing the same fixture result;
- hypothetical repeated retries not yet due.

A newly placed Position may cause `R(t)` to increase because a new real financial/result obligation now exists. Therefore the reserve is expected to trend downward through the day but is not mathematically required to be monotonic at every instant.

## 13.4 Reserve horizon is provider-epoch bounded

Only calls whose critical deadlines occur before the next provider quota reset belong in the current reserve.

Example in Lima when API quota resets at 19:00 local:

```text
18:30 local
Match A T-30 due at 18:45
Match B T-30 due at 20:00

current epoch reserve
→ protect A
→ do not protect B with quota that expires at 19:00

after observed reset
→ recompute
→ protect B in new epoch
```

This is essential to avoid wasting quota through over-reservation.

## 13.5 Surplus quota

Define:

```text
S(t) = max(0, provider_remaining(t) - R(t))
```

Only `S(t)` is available to discretionary P4 work.

As critical work completes:

```text
R(t) decreases
→ S(t) grows
→ optional work becomes admissible
```

When all protected work in the current epoch is closed:

```text
R(t) = 0
→ all remaining quota is surplus
→ Finsport may batch non-bet results / perform secondary work
```

This directly implements the product requirement that unused quota should become freely useful late in the day instead of being stranded behind a constant reserve.

## 13.6 Retry budget

Retries must not be pre-reserved as a generic `12` for every operation.

Frozen product contract:

```text
normal logical provider execution
→ one attempt

transient network / 5xx / 429 class
→ at most one immediate retry when:
     a) retry policy says it is safe,
     b) per-minute limit/backoff permits,
     c) recomputed protected reserve remains intact

otherwise
→ persist failure/defer to next due opportunity

deterministic 4xx / plan / invalid parameter / unsupported season
→ no blind immediate retry
```

This gives a normal per-logical-execution ceiling of **2 attempts**, not 12, while retaining resilience.

The API-Football official guidance explicitly warns against automatic retry without understanding the cause and recommends backoff for 429/rate-limit conditions.

## 13.7 Hard safety circuit breaker

A hard circuit breaker may remain to protect against accidental loops, but it must be derived from admitted finite work, not used to pretend that every item costs the breaker maximum.

Acceptable concept:

```text
admitted physical calls this wake
+ bounded retry allowance for those admitted calls
→ finite safety ceiling
```

The circuit breaker is a **last-resort guard**.

It is not:

```text
estimated cost of every item
```

## 13.8 Expected effect on `INSUFFICIENT_WORST_CASE_BUDGET`

The current status was triggered because multiple one-call operations were all costed as if each might consume the same large generic worst-case allowance.

After this change, admission should distinguish:

```text
CRITICAL_RESERVE_PROTECTED
DEFERRED_FOR_CRITICAL_RESERVE
OPTIONAL_NO_SURPLUS
PROVIDER_RATE_LIMIT_BACKOFF
ACTUAL_OPERATION_COST / CALLS
```

The exact enum names are technical design, but the operator must no longer see thousands of misleading items blocked because a one-call request was modeled as a twelve-call operation.

---

# 14. Proposed operator quota summary

## 14.1 Surface

Frontend work is explicitly out of scope. The minimum useful surface is a read-only management command and/or structured service output backed by persisted audit data.

Suggested operator concept:

```text
python manage.py football_quota_summary [--date YYYY-MM-DD]
```

Exact command name is implementation detail; the required information is not.

## 14.2 Required current-state fields

The summary must show approximately:

```text
provider
provider quota epoch start/end
local date
latest quota basis
latest header observed_at
header freshness
observed daily limit
observed remaining
locally attributed attempts since latest header, if any
current conservative remaining

DYNAMIC PROTECTED RESERVE
  fixture discovery calls remaining
  T-30 calls/pages remaining before reset
  OPEN result batches due before reset
  future execution quote reserve (currently 0)
  TOTAL R(t)

SURPLUS S(t)

NEXT CRITICAL DEADLINE
```

## 14.3 Usage attribution

For the current epoch/day, display:

```text
attempts / successful calls / retries / pages by capability

DAILY_FIXTURE_DISCOVERY
ODDS_T30
ODDS_T60
ODDS_T6H
OPEN_RESULT_BATCH
NONBET_RESULT_BATCH
CATALOGUE/SEASON
OTHER MAINTENANCE
```

Also show:

```text
skipped/deferred because reserve protected
missed prospective windows
provider failures
plan/access denials
429/backoff events
```

## 14.4 Work backlog

Useful non-provider state:

```text
today fixtures known? yes/no
T-30 protected observations remaining
OPEN positions
OPEN result fixtures currently due
pending-capacity pre-match opportunities
non-bet results pending historical completion
last Football-Data reconciliation
next Football-Data reconciliation due
```

The summary must not make a provider request just to populate itself.

---

# 15. Exact implementation gaps

The implementation ticket must close all of the following. These are not optional suggestions.

## GAP-01 — Fixed generic worst-cost admission

CURRENT:

```text
mandatory reserve 10
max attempts 12
same worst_operation_cost assigned broadly
→ false `INSUFFICIENT_WORST_CASE_BUDGET`
```

REQUIRED:

```text
dynamic R(t)
+ actual capability-specific minimal costs
+ surplus-based optional admission
+ bounded retry/circuit breaker separate from cost estimate
```

## GAP-02 — Incomplete all-call quota accounting

CURRENT quota reconstruction is centered on CaptureRun/MaintenanceRun and may omit direct Capital provider consumption.

REQUIRED:

```text
all API-Football calls
→ same durable attribution/header accounting contract
```

## GAP-03 — Fixture discovery is too periodic/generic

CURRENT discovery is cadence-slot based and may repeat dates.

REQUIRED:

```text
one mandatory local-day fixture discovery at first operational opportunity
→ stored kickoffs drive rest of day
→ explicit recovery rediscovery only on proven need
```

## GAP-04 — Generic result polling wastes quota

CURRENT generic RESULT_REFRESH individually pursues all unresolved past Matches.

REQUIRED:

```text
OPEN Capital result debt
→ urgent T+130 / batched / status-aware

no OPEN Position
→ no urgent individual polling
→ surplus batch and/or twice-weekly Football-Data reconciliation
```

## GAP-05 — terminal status + blank outcome can strand generic debt

CURRENT can mark terminal blank rows ineligible.

REQUIRED:

```text
terminal-looking + blank outcome
→ explicit recoverable debt/conflict path
→ never silently abandoned
```

## GAP-06 — regulation-time 1X2 outcome can be wrong for AET/PEN

CURRENT `_fixture_outcome()` can use winner/final goals.

REQUIRED:

```text
Finsport 1X2
→ regulation/fulltime score
→ no extra-time/penalty winner contamination
```

## GAP-07 — T-30 capacity miss is prematurely terminal

CURRENT:

```text
BET at T-30 + no lane
→ EXPIRED_CAPACITY
```

REQUIRED:

```text
BET at T-30 + no lane/cash
→ PENDING_CAPACITY
→ retry before kickoff
→ place if capacity appears
→ expire at kickoff
```

Pending state consumes no lane or stake.

## GAP-08 — same-wake settlement/placement ordering

CURRENT can reconcile placement before a due result refresh releases a lane.

REQUIRED:

```text
due canonical/local settlement/result refresh
→ update capital/lane availability
→ pending pre-match placement reconciliation
```

or equivalent semantics that guarantee capacity freed during a wake is usable in that same wake before kickoff.

## GAP-09 — wake work is not sufficiently event/due-driven

CURRENT sporting candidate construction and capture planning perform repeated scans even when nothing changed.

REQUIRED:

```text
Beat wake
→ cheap due-index/state check
→ unchanged evidence = no expensive prediction/model/provider work
```

Specific triggers:

```text
new/changed sporting evidence or newly discovered target
→ sporting models

new governed odds capture
→ market-dependent model/Decision

T-30/pending capacity state change
→ Capital placement logic

new canonical result
→ evaluation/settlement

due maintenance identity
→ maintenance only
```

## GAP-10 — scheduler interval

CURRENT default = 15 minutes.

REQUIRED target after due/event gating:

```text
FOOTBALL_CAPTURE_WAKE_SECONDS = 300
```

A 5-minute wake is an orchestration frequency, not provider polling frequency.

Recent post-hotfix evidence supports this target:

```text
2026-09-15
PipelineRun count                 = 68
NO_WORK                           = 51
materially empty                 = 50
empty median                     ≈ 7.46 s
empty p95                        ≈ 7.92 s
empty max                        ≈ 8.82 s
overall p95                      ≈ 8.49 s
active max                       ≈ 15.23 s
```

Later no-work runs were frequently around 1.4–2 seconds. Ticket acceptance must confirm the new due-driven implementation preserves comfortable headroom at 5 minutes.

## GAP-11 — current-season reconciliation is not periodic/currently covered

CURRENT has current-season recovery capability but no completed automatic twice-weekly coverage lifecycle for the observed gaps.

REQUIRED:

```text
Sunday/Wednesday Football-Data-aligned maintenance
→ current-season result/historical-market completeness
→ coverage/accounting rows
→ idempotent NO_WORK on unchanged source
```

## GAP-12 — operator cannot see dynamic obligations vs free quota

REQUIRED:

```text
read-only quota summary
→ latest headers
→ attribution
→ R(t)
→ surplus
→ protected deadlines/backlog
```

## GAP-13 — current T-30 execution contract must be extended without pretending fresh price

REQUIRED MVP:

```text
pending placement before kickoff
→ use valid persisted T-30 execution evidence
→ provenance must show actual placement time != quote observation time
```

Do not fabricate a fresh quote.

Future high-frequency execution-price work is deferred to section 18.

## GAP-14 — batch UAT under current API plan

Official API-Football supports up to 20 fixture IDs in a batch and Capital code already uses the shape, but the research live probe selected historical IDs denied by the current plan.

REQUIRED UAT:

```text
choose 2..20 current-plan-accessible current/recent fixture IDs
→ one /fixtures?ids=... physical provider call
→ returned fixture set accounted
→ zero accidental per-fixture call fanout
```

This is acceptance, not additional product research.

---

# 16. Suggested ticket boundary

## 16.1 One implementation ticket

Create **one** implementation ticket after this handoff is accepted.

It should cover the cohesive runtime closure:

```text
A. provider quota lifecycle
   dynamic reserve
   all-call accounting
   capability attribution
   bounded retry policy
   quota summary

B. scheduler/planner lifecycle
   daily fixture discovery
   event/due-driven wake
   5-minute orchestration target
   eliminate unnecessary generic planning/recompute

C. prospective execution lifecycle
   protected T-30
   pending capacity T-30→kickoff
   same-wake settlement→placement availability
   kickoff hard expiry

D. result lifecycle
   T+130 OPEN result hint
   <=20 batching
   status-aware retries
   terminal blank repair
   regulation-time 1X2 correctness
   non-bet result deferral/batching

E. historical completeness lifecycle
   twice-weekly Football-Data current-season reconciliation
   historical-market coverage/currentness
   source/conflict provenance

F. observability/UAT
   quota summary
   dynamic reserve evidence
   batch-call proof
   restart catch-up proof
```

These parts should not be split into sequential tickets because the old generic quota/result behavior would distort acceptance of the new pending-Capital behavior if only half the lifecycle were deployed.

## 16.2 What the ticket must not absorb

Do not absorb:

- frontend redesign/OOM cleanup;
- integrated evaluator;
- technique winner selection;
- tuning capture windows from outcome performance;
- R45 reactivation;
- Inkabet reactivation;
- API-Football `/odds/live` execution-price feature;
- Portfolio Kelly;
- low-power/headless host operation;
- real bookmaker write integration;
- real betting.

---

# 17. Acceptance implications

The ticket is accepted only when the implementation proves the following behavior, not merely when code paths exist.

## 17.1 Daily fixture discovery

- First operational opportunity of a local day obtains/ensures today’s enabled-competition fixture slate.
- Kickoffs/fixture IDs are persisted and drive local scheduling.
- Repeated normal wakes do not keep rediscovering the same day without a recovery reason.
- Restart later in the day does not lose already-known fixtures.

## 17.2 Dynamic quota reserve

With a deterministic synthetic/current schedule, acceptance must show:

```text
R_fixture
R_t30
R_open_result
R_total
surplus
```

changing correctly as work completes.

Required scenarios:

1. morning before discovery;
2. discovery completed;
3. several T-30 obligations remain;
4. one T-30 fulfilled;
5. new Position becomes OPEN and adds result obligation;
6. one OPEN result settles and reserve falls;
7. all protected work in epoch completes and reserve reaches 0;
8. optional work becomes admissible only from surplus;
9. provider reset observed and reserve recomputed for new epoch;
10. no artificial fixed 10/12 reserve blocks critical work.

## 17.3 Quota accounting

- Every API-Football call from capture, maintenance and Capital is attributed.
- Normal provider response headers update current quota state.
- No quota-summary command makes a provider call.
- Header values override synthetic reset assumptions.
- Retry/page counts remain attached to the parent capability.

## 17.4 Retry policy

- Normal successful logical call consumes one attempt.
- Transient error can make at most one immediate retry when reserve remains protected.
- Deterministic plan/4xx error does not loop.
- 429 causes backoff/defer rather than burst retry.

## 17.5 Beat / no-work behavior

At 5-minute scheduler configuration:

- no-work wakes make zero provider calls;
- unchanged sporting basis does not refit/recreate predictions;
- no new odds evidence does not rerun Market Consensus;
- no new result does not re-evaluate completed evidence;
- maintenance that is not due does not perform heavy backtest/calibration work;
- single-flight prevents overlap/fanout;
- normal empty wake remains far below 300 seconds with comfortable margin.

Do not freeze an arbitrary micro-performance threshold tighter than the empirical environment requires, but any recurrent wake near the 300-second interval is a failed operational design.

## 17.6 T-30 protected evidence

- T-30 obligations are admitted ahead of optional T-60/T-6h when quota is scarce.
- Missed T-30 is persisted as missed/unavailable; it is never fabricated later.
- T-60/T-6h may be skipped/deferred under insufficient surplus without starving T-30.

## 17.7 Pending capacity

Required scenario:

```text
T-30 quote exists
Decision = BET
no lane available
→ pending opportunity, no stake/lane consumed

before kickoff
old OPEN Position settles
→ lane/cash becomes available
→ same wake or next 5-minute due wake before kickoff places candidate
→ placement provenance records T-30 price + actual placement time
```

And:

```text
no capacity before kickoff
→ no placement
→ terminal expired reason
```

No post-kickoff placement from this pre-match Decision.

## 17.8 Result acquisition

- OPEN Position is not queried for result before T+130 under ordinary flow.
- At/after T+130 it becomes due.
- Multiple due OPEN fixtures use batches up to 20.
- Same fixture shared by multiple configs does not multiply provider calls.
- Nonterminal response schedules retry no earlier than +30m.
- `SUSP` slows to +60m.
- `PST` leaves ordinary result polling and awaits reschedule/reconciliation.
- restart after long downtime makes overdue OPEN debt immediately eligible.
- `CANC`/`ABD` → VOID.
- terminal blank result cannot strand OPEN position.

## 17.9 Regulation-time result correctness

Tests must include at least:

```text
FT regulation HOME/DRAW/AWAY
AET where regulation was DRAW but extra time has a winner
PEN where regulation was DRAW but penalties have a winner
CANC
ABD
PST
SUSP
AWD/WO blank/explicit cases as supported
```

For AET/PEN, Finsport 1X2 must remain the regulation-time outcome.

## 17.10 Evaluation catch-up

Scenario:

```text
prospective Prediction/Decision persisted before kickoff
result missing during downtime
result recovered later
→ Prediction actual_outcome/evaluated_at closes automatically
→ Decision evaluation consumers see canonical result
→ no duplicate prospective Prediction required
```

## 17.11 Non-bet recovery

- No OPEN Position means no urgent per-Match result poll by default.
- With surplus quota, non-bet results may be batched.
- Without surplus, they can remain pending until Football-Data reconciliation.
- Historical completion does not create retroactive prospective odds or Capital.

## 17.12 Twice-weekly reconciliation

- Sunday/Wednesday due state is deterministic and idempotent.
- Current-season source rows are accounted.
- historical-market evidence is filled or explicitly unavailable.
- unchanged source converges to no delta/NO_WORK.
- source conflict does not silently overwrite API-Football primary canonical evidence.
- reconciliation itself does not consume API-Football quota unless an explicit bounded canonical-conflict path is genuinely needed.

## 17.13 Live batch proof

A bounded UAT must prove with current-plan-accessible fixture IDs:

```text
2..20 IDs
→ one physical /fixtures?ids=... request
→ expected returned IDs accounted
```

The previous research probe's plan denial is preserved as evidence but is not acceptance.

## 17.14 Quality gates

Standard Finsport quality gates apply:

- focused tests;
- full tests;
- branch coverage floor;
- migration drift/system checks;
- `make check` on isolated dev;
- `make ci-check` on disposable CI;
- real operational DB never mutated by destructive UAT;
- provider calls in UAT explicitly bounded and quota-checked;
- final post-merge operational verification under `master`.

---

# 18. Deferred work

The following is deliberately **not required** for this MVP closure.

## 18.1 Fresh execution quote between T-30 and kickoff

Current MVP fallback:

```text
T-30 quote observed
→ BET candidate waits for capacity
→ later pre-kickoff placement uses that persisted T-30 price
→ actual placement time is separately persisted
```

Future research should compare:

```text
API-Football /odds/live
→ fixture may appear 5–15 min before kickoff
→ updates roughly 5–60 sec
→ separate live bet IDs / no history

Inkabet rehabilitation
→ historically observed high-frequency Bet360-derived price updates
→ must re-audit reliability/timeouts/runtime cost/market identity
```

Preferred future behavior if a trustworthy fresh execution source is enabled:

```text
T-30 Decision
→ wait for capacity
→ capacity appears before kickoff
→ fetch fresh execution quote
→ revalidate any price-sensitive policy
→ place with actual execution quote

fresh quote unavailable
→ explicitly governed fallback to T-30 if product still permits it
```

This must be implemented before treating simulated delayed execution as a faithful model of real betting execution quality.

## 18.2 In-play betting

Not part of current pre-match strategy.

```text
kickoff
→ hard deadline for current pending pre-match opportunity
```

Future in-play models would require separate evidence, market semantics, decision policies, risk rules and evaluation cohorts.

## 18.3 Inkabet automatic reactivation

Deferred separate work. Do not re-enable incidentally while implementing this ticket.

## 18.4 API-Football live odds

Deferred separate research/UAT. The existence of `/odds/live` does not automatically prove compatible 1X2 bookmaker coverage for Finsport's required execution use.

## 18.5 Frontend/reporting redesign

Known backlog, not an experimental-readiness blocker for this ticket. Use ORM/commands/admin/Grafana as needed.

## 18.6 Integrated evaluator / technique selection

Begins after this operational closure. This handoff deliberately does not select a winning predictive technique, Decision policy, Capital configuration, capture timing optimum or Market Consensus weighting.

## 18.7 Low-power/headless host mode

Separate future operational work.

## 18.8 Real betting transition gate

Still forbidden now.

Before any future real-betting mode:

- remove/disable automatic late research reconstruction from runtime economic paths;
- require genuine execution-time market evidence or explicitly accepted stale-price policy;
- preserve OPEN result catch-up across restart;
- add explicit external financial side-effect safety/authorization boundaries;
- re-review F001/F002 product/security contracts.

---

## Decision ledger D1–D14

| Decision | Final contract |
|---|---|
| **D1 — post-downtime result catch-up** | OPEN Position = mandatory API-Football catch-up and settlement; non-bet Match = delayed batch/Football-Data historical completion, no retroactive bet. |
| **D2 — Prediction/Decision evaluation catch-up** | Existing prospective Prediction/Decision evidence evaluates automatically after late canonical result recovery; no second provider lifecycle. |
| **D3 — late research computation** | Only explicit non-prospective `BACKTEST/LATE_RESEARCH` from genuine pre-kickoff inputs; normal automatic continuity does not invent missed prospective computations. |
| **D4 — irrecoverable prospective evidence** | Missed temporal odds/placement remain lost prospectively; historical evidence never masquerades as prospective. |
| **D5 — current-season periodic reconciliation** | Yes; source-aligned twice weekly after Football-Data Sunday/Wednesday updates. |
| **D6 — source/result authority** | API-Football primary live/current and OPEN-settlement authority; Football-Data authorized secondary historical/current-season completion for non-bet evidence, with provenance/conflict fail-closed. |
| **D7 — historical odds completion** | `HistoricalMarketEvidence` only; real source price + explicit imputed time; never `OddsObservation`/prospective Capital repair. |
| **D8 — first result check** | OPEN result debt first hint = `kickoff + 130m`; restart overdue debt = first wake. |
| **D9 — retry cadence** | normal unresolved OPEN debt +30m; SUSP +60m; PST leaves frequent polling; terminal/VOID status-driven; batches <=20. |
| **D10 — daily quota authority** | response headers + locally accounted later attempts; headers win; no quota-reporting call; do not synthesize reset before observed. |
| **D11 — attribution granularity** | capability-level all-call audit including fixture, T30/T60/T6h, OPEN/non-bet batches, maintenance, retry/page dimensions. |
| **D12 — priority/reserve** | dynamic `R(t)` from actual critical work before next provider reset; fixtures > T30 > OPEN result; all else from surplus. No fixed 10/12 admission model. |
| **D13 — operator summary** | read-only command/service summary of headers, usage, dynamic reserve, surplus, attribution, backlog and deadlines; no frontend required. |
| **D14 — ticket boundary** | one cohesive implementation ticket. |

---

## Official external references

### IFAB

1. **Law 7 — The Duration of the Match / La duración del partido**
   https://www.theifab.com/es/laws/latest/the-duration-of-the-match/
   Used for: two 45-minute halves, halftime limit, added time.

2. **Law 10 — Determining the Outcome of a Match**
   https://www.theifab.com/laws/latest/determining-the-outcome-of-a-match/
   Used for: extra time/penalty shoot-out as separate winner-determination procedures.

### API-Football / API-SPORTS

3. **How to Get Started with API-Football: The Complete Beginner's Guide**
   https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide
   Used for: fixture IDs/statuses/score breakdown, once-daily future fixture guidance, odds update cadence, live-odds timing/frequency, endpoint behavior.

4. **How to Optimize API-SPORTS Calls and Quota Usage**
   https://www.api-football.com/news/post/how-to-optimize-api-sports-calls-and-quota-usage
   Used for: purpose-driven calls, quota-header use, avoiding unnecessary retries/requests.

5. **How Ratelimit Works**
   https://www.api-football.com/news/post/how-ratelimit-works
   Used for: daily/per-minute headers, 429/backoff behavior, avoiding bursts.

6. **How to Get All Fixtures Data from One League**
   https://www.api-football.com/news/post/how-to-get-all-fixtures-data-from-one-league
   Used for: `/fixtures?ids=` maximum 20 IDs and batching example.

### Football-Data

7. **Football Results, Statistics & Soccer Betting Odds Data**
   https://www.football-data.co.uk/data
   Used for: current published update cadence of at least twice weekly, Sunday nights and Wednesday nights.

---

## Final disposition

POST-DOWNTIME CONTINUITY
→ CLOSED

WEEKLY CURRENT-SEASON RECONCILIATION
→ CLOSED

RESULT FINISH-HINT
→ CLOSED

DAILY QUOTA ACCOUNTING
→ CLOSED

QUOTA PRIORITY POLICY
→ CLOSED

PROSPECTIVE/HISTORICAL SEPARATION
→ CLOSED

IMPLEMENTATION GAP
→ YES

NUMBER OF REQUIRED IMPLEMENTATION TICKETS
→ 1

RESEARCH REQUIRED BEFORE TICKET
→ NONE

MVP EXPERIMENTAL READINESS AFTER IMPLEMENTATION
→ YES
