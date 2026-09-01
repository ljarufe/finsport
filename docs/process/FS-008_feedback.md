# FS-008 Feedback

Status: **FINAL RECONCILED FEEDBACK**
Updated: 2026-09-01
Branch: `FS-008-maintenance-refactor-cleanup`
PR: `https://github.com/ljarufe/finsport/pull/13`
Base: `master` at `23a36fdcdd2354145360f1ab6b488ab4c5d1c838`
Latest review-correction head before this final-feedback commit: `df38557cc67c9d8ee61e1e10fbb53d2f39d1a148`

## 1. Outcome

FS-008 reached technical close successfully.

The baseline is smaller, more explicit operationally, and safer to maintain:

- legacy `bet` runtime and its two superseded tables are removed;
- unused DRF, `django-celery-beat`, and `django-celery-results` runtime dependencies are removed;
- retained dependencies were refreshed and `pip-audit` became part of the reproducible gate;
- avoidable Penaltyblog/NumPy warning noise was removed without global warning suppression;
- branch coverage remains above the required 80% floor;
- `MODERNIZED_R45` is ACTIVE with chronological/leak-safe availability semantics;
- automatic Inkabet MW3W capture is ACTIVE only on successful due `ODDS_CAPTURE` work and remains read-only/fail-soft;
- daily catalogue maintenance, daily new-season eligibility detection, and weekly backtest/config reselection are ACTIVE under one pipeline-owned scheduler;
- runtime ownership is explicit through `make up`, `make dev-up`, `make status`, and `make safe-down`;
- watchdog DB recovery is bounded and survives a real PostgreSQL interruption without restart/error storm;
- the exact reviewed FS-004 synthetic UAT graph was removed safely while preserving known real pipeline/capture evidence.

No real betting, bookmaker authentication, or financial external side effect was added.

## 2. Final capability disposition

| Capability | Final FS-008 disposition |
| --- | --- |
| `MODERNIZED_R45` | **ACTIVE** |
| `LEGACY_R45` active runtime | **REMOVED / not an active runtime arm** |
| API-Football prospective capture | **ACTIVE under existing bounded pipeline ownership** |
| Inkabet MW3W prospective capture | **ACTIVE secondary/read-only/fail-soft on due odds captures** |
| Inkabet extended statistics | **NOT_IMPLEMENTED; no ingestion path exists in FS-008** |
| Catalogue refresh | **ACTIVE once per America/Lima local day when due** |
| New-season eligibility detection | **ACTIVE daily; provider bootstrap only for eligible current empty seasons** |
| Backtest/config reselection | **ACTIVE weekly plus manual on-demand** |
| Automatic scheduler | **one owner: `football.pipeline.wake` through Celery Beat** |
| Development runtime | **safe no-Beat runtime through `make dev-up`** |

These dispositions supersede earlier FS-006/ticket language that described R45 activation, Inkabet automation, new-season bootstrap, or automatic retraining as future/deferred work.

## 3. Dependency / tooling result

Removed from active runtime because no current consumer remained:

- `djangorestframework`;
- `django-celery-beat`;
- `django-celery-results`;
- legacy `bet` app/runtime;
- obsolete serializer/Pylint surfaces associated with the removed baseline.

Retained dependencies were audited deliberately rather than mass-upgraded blindly.

Final known dependency evidence:

- `pip check`: PASS;
- `pip-audit --local`: PASS, no known vulnerabilities;
- Django system check: PASS;
- migration drift: PASS;
- Black/Ruff: PASS;
- `make check`: PASS after the final PR-review corrections, maintainer-reported;
- pre-review final full suite: 271 tests, 86.41% branch coverage;
- required global branch-coverage floor: satisfied;
- avoidable Penaltyblog/NumPy/test warnings: none reported.

NumPy remains on the documented compatibility version selected for Penaltyblog warning hygiene rather than being blindly advanced to the incompatible warning-producing combination.

## 4. Persistent migration and cleanup UAT

The maintainer persistent database was backed up before destructive UAT.

Safety dump:

- `tmp/FS-008-pre-uat-cleanup.dump`;
- created before applying cleanup;
- local/ephemeral only.

Persistent migrations:

- applied successfully;
- Django integrity check PASS;
- migration drift PASS;
- PostgreSQL unvalidated FK query returned 0.

The exact synthetic FS-004 UAT graph was classified as unambiguous and deleted only after a dry-run manifest showed zero unexpected related rows.

Deleted exact synthetic graph:

- Source: `3`
- Competition: `2508`
- Season: `21200`
- Teams: `25`, `26`
- Matches: `1144`–`1153`
- Bookmaker: `16`
- OddsMarket: `3`
- OddsObservation: `60`–`68`
- PredictionExperiment: `4`
- Predictions: `1155`–`1164`
- Decisions: `10757`–`10766`
- CapitalExperiments: `1`–`6`
- CapitalPolicyRuns: `1`–`42`
- CapitalLedgerEntries: `1`–`70`

Post-cleanup verification found no remaining rows for those exact candidates.

Known real evidence was preserved, including:

- CaptureRuns `40`–`47`;
- PipelineRuns `17`–`24`.

Post-cleanup DB counts recorded during UAT:

- Source: 2
- Competition: 1241
- Season: 8674
- Team: 72
- Match: 1547
- Bookmaker: 15
- OddsMarket: 2
- OddsObservation: 321
- PredictionExperiment: 9
- Prediction: 1174
- Decision: 10920
- CapitalExperiment: 5
- CapitalPolicyRun: 5
- CapitalLedgerEntry: 6
- CaptureRun: 47
- PipelineRun: 20
- MaintenanceRun: 0

## 5. Weekly maintenance / reselection UAT

A forced real weekly maintenance cycle executed successfully.

Persisted maintenance audit:

- catalogue run `1`: `SKIPPED_QUOTA` under the then-conservative local quota state;
- weekly evaluation run `2`: `SUCCESS`;
- same-day repeat: daily catalogue `NOT_DUE` / `QUOTA_RETRY_NOT_DUE`;
- same-day weekly repeat: `NOT_DUE` / `WEEKLY_INTERVAL_NOT_ELAPSED`.

The weekly evaluation found a complete chronological population for La Liga 2022–2024 and produced backtest experiment `11` for the 2024 outer season.

Selected hyperparameters included:

- Dixon-Coles: `xi=0.0`;
- Independent Poisson: selected using the Dixon-Coles selection basis;
- Elo multinomial logit: `C=0.1`, `k=10`.

Backtest experiment `11`:

- Predictions: 1138;
- Decisions: 10242;
- `MODERNIZED_R45` predictions: 0;
- `MODERNIZED_R45` decisions: 0;
- `MODERNIZED_R45`: `UNAVAILABLE` with `INSUFFICIENT_LEAK_SAFE_SELECTION_EVIDENCE`;
- `MARKET_CONSENSUS`: `UNAVAILABLE` with `INSUFFICIENT_HISTORICAL_MARKET_OBSERVATIONS`.

This is an accepted factual negative result, not dormant wiring: the arm is ACTIVE but historical market evidence is insufficient.

Premier League, Bundesliga, and Serie A initially remained unavailable for this weekly backtest because the persistent DB lacked three populated consecutive historical seasons.

## 6. Real post-cleanup pipeline UAT

A bounded real pipeline was executed after cleanup:

- PipelineRun: `25`;
- trigger: `MANUAL`;
- status: `SUCCESS`;
- CaptureRun: `48`;
- provider attempts: exactly `1`;
- provider pages: `1`;
- fixtures changed: `1`;
- matches resolved: `1`;
- observations created: `0`;
- Inkabet secondary status: `NO_WORK` because this run executed `RESULT_REFRESH`, not a due `ODDS_CAPTURE`;
- errors: none.

The completed real work resolved Match `1554`.

The provider response established current quota headers and changed the runtime quota view from the previous conservative bootstrap estimate to:

- basis: `HEADER_CURRENT_UTC_EPOCH`;
- daily limit: `100`;
- remaining after the call: `99`.

This confirms provider headers are the current quota authority once observed.

## 7. Prospective Prediction → Decision evidence

Real resolved prospective evidence was verified without fabricating historical timestamps.

Prediction `1181`:

- experiment: `8`;
- competition: La Liga (`1278`);
- match: `1156`, Levante vs Real Betis;
- model: `MARKET_CONSENSUS`;
- cutoff: `2026-08-29T00:01:19+00:00`;
- predicted outcome: `AWAY`;
- actual outcome: `HOME`;
- evaluated at: `2026-08-31T02:43:45.659310+00:00`.

Associated actionable Decision `10895`:

- policy: `MODAL_ALL`;
- action: `AWAY`;
- decision time equals the prediction cutoff;
- selected price: `2.2800`;
- selected OddsObservation: `197`;
- expected value: approximately `-0.02064646`.

Additional selective-confidence decisions were persisted, including explicit `NO_BET` outcomes above their thresholds.

No CapitalLedger trace was fabricated for this selected decision. Existing capital replay correctly reported factual unavailability where no selected decision basis or resolved canonical outcome was available.

## 8. Scheduler / observability UAT

Scheduler ownership:

- pipeline automation enabled;
- capture standalone automation disabled;
- registered Beat schedule contains only `football-pipeline-wake` → `football.pipeline.wake`;
- no second independent maintenance/Inkabet scheduler exists.

Grafana health:

- database: `ok`;
- Grafana version observed: `13.2.0`.

Scheduler terminal correlation:

- PipelineRun `22`;
- persisted status: `FAILED`;
- exactly one Loki `PIPELINE_FAILED`;
- correlated by `pipeline_run_id=22`;
- capture_run_id: `45`;
- incident fingerprint: `8237c8f971ba52dbbc3c9e26`.

Healthy terminal correlation:

- PipelineRun `25`;
- exactly one Loki `PIPELINE_SUCCEEDED`;
- outcome `SUCCESS`;
- capture_run_id: `48`;
- incident fingerprint: `e8b78eae4dc72a46138e6811`.

## 9. Watchdog controlled-failure UAT

A real controlled PostgreSQL interruption was executed.

Before failure:

- watchdog container ID: `016524213d7169609e84338e9fad0d8fddfbe0d1e79b23f30ba1846f034ad9f4`;
- restart count: 0;
- status: running.

During DB failure Loki contained exactly one new incident:

- event: `OBSERVABILITY_WATCHDOG_FAILED`;
- severity: `ERROR`;
- component: `observability-watchdog`;
- operation: `query_pipeline_liveness`;
- failure kind: `database_dependency`;
- exception: `OperationalError`;
- incident fingerprint: `cb109b86d0e3caa6c3e9824c`.

After PostgreSQL recovery:

- same watchdog container ID;
- restart count remained 0;
- watchdog still running;
- total failure events since test start remained exactly 1.

Result:

```text
DB failure
→ one actionable bounded incident
→ no error storm
→ PostgreSQL restored
→ same watchdog reconnects without container restart
```

PASS.

## 10. Runtime lifecycle UAT

`make up`:

- complete operational/observability topology runs together;
- scheduled dispatch is possible;
- one Beat owner only.

`make safe-down`:

- drained with zero active/reserved/scheduled Celery work;
- zero running CaptureRun/MaintenanceRun/PipelineRun;
- removed all project containers;
- Grafana port 3000 became unreachable;
- did not use `down -v`.

Named volumes before and after were identical:

- `finsport_postgres_data`;
- `finsport_redis_data`;
- `finsport_loki_data`;
- `finsport_alloy_data`;
- `finsport_grafana_data`.

`make dev-up`:

- starts db, Redis, Django, Celery worker, Nginx;
- does not start Celery Beat;
- does not start watchdog, Loki, Alloy, or Grafana;
- `scheduled_dispatch_possible=false`;
- queue depth 0;
- no active/reserved/scheduled Celery work.

PASS.

## 11. Unit-test provider isolation

During FS-008 execution a harness defect was found: old capture tests could inherit operational `INKABET_AUTOMATIC_ENABLED=True` and therefore construct the real Inkabet client, causing unintended external HTTP during pytest.

Correction:

- capture-test defaults explicitly disable automatic Inkabet unless the test enables it;
- automatic Inkabet tests inject a fake client;
- an autouse test guard fails fast on unmocked API-Football/requests provider HTTP.

A first direct test override introduced duplicate `override_settings` keys and caused collection failure; this was corrected with dictionary-merge overrides.

Focused capture result after correction:

- 35 passed;
- approximately 2.68 seconds;
- no real provider delay.

This is a HARNESS finding, not a product failure.

## 12. GitHub review findings

Codex review on PR #13 produced three P2 findings. All three were verified as valid and corrected in the review-fix commit pushed at head `df38557cc67c9d8ee61e1e10fbb53d2f39d1a148`.

### P2 — bounded maintenance bootstrap

Problem:

- headerless `BOUNDED_BOOTSTRAP` used bootstrap availability but still subtracted the normal capture reserve;
- with bootstrap `2` and reserve `10`, maintenance could reject itself before making the bounded call needed to establish real quota headers.

Fix:

- unknown-reserve bootstrap admission now waives the reserve for that bounded bootstrap admission, matching the established capture-executor principle;
- once real headers are known, normal provider reserve enforcement remains active.

### P2 — weekly evidence signature omitted market observations

Problem:

- weekly change detection only included resolved Match evidence;
- adding new historical `OddsObservation` rows without modifying Matches could incorrectly produce `NO_WORK`;
- `MARKET_CONSENSUS` / `MODERNIZED_R45` could remain stale after legitimate market evidence arrived.

Fix:

- weekly evidence signature now includes relevant historical odds-observation count/freshness/identity evidence;
- regression coverage proves new market evidence makes the next due weekly cycle execute.

### P2 — Inkabet snapshot update metric

Problem:

- `snapshots_changed` compared row counts only;
- changing prices on an existing Inkabet `OddsSnapshot` preserved the row count and incorrectly reported zero changes.

Fix:

- Inkabet snapshots are compared by before/after value state, analogous to the primary API-Football path;
- regression coverage proves a later price update counts as a changed snapshot.

Focused tests and `make check` passed before the review-fix push.

## 13. Product findings

1. `MODERNIZED_R45` can be operationally ACTIVE while producing an honest `UNAVAILABLE` result for a specific population. Lack of evidence must not be confused with dormant code.
2. Historical fixture/results coverage and historical market-price coverage are separate problems. Existing results are not sufficient for market-consensus/R45 backtesting.
3. Provider quota headers are authoritative once observed; conservative bootstrap state is only a safe temporary estimate.
4. Periodic maintenance is evidence-generation infrastructure and belongs under the same pipeline scheduler ownership rather than under a second scheduler.
5. Inkabet is secondary market evidence only; it is not canonical identity/outcome authority.
6. New historical market evidence is a real input to weekly evaluation and therefore must invalidate the unchanged-evidence signature.

## 14. Harness / process findings

1. The initial FS-008 Codex prompt incorrectly prohibited the versioned feedback file, repeating the FS-007 orchestration regression. Correct durable sequence:

   ```text
   implementation/correction pass
   → create/update factual PRE-UAT feedback snapshot in the same pass
   → execution chat reconciles final feedback after UAT + PR review
   → never spend a separate Codex pass only on feedback
   ```

2. The first complete-diff artifact omitted a safety-critical cleanup script; relevant versionable/untracked implementation surfaces must be represented during real diff review.
3. A free-plan fixture discovery horizon of 2 days attempted an unsupported provider date; corrected baseline is 1 day ahead.
4. `make dev-up` originally did not fail closed against prior profiled runtime/stale Redis work; it now tears down prior project services and guards the persistent safe queue before starting the development runtime.
5. Prospective R45 summary originally treated an available fit as `PRODUCED` even when no R45 Prediction persisted; status now follows actual persistence.
6. Unit tests accidentally allowed real Inkabet HTTP; provider HTTP is now fail-fast unless explicitly mocked/injected.
7. Several execution-chat probes were wrong but did not indicate product defects:
   - queried nonexistent `CaptureRun.operational_cause`;
   - broad legacy `git grep` matched intentional test literals;
   - stdout was incorrectly treated as watchdog observability authority before querying Loki.
8. Interactive-shell command blocks must not use `exit` in a way that can close the maintainer terminal. This is already covered by F009 and was violated once during UAT orchestration.
9. `tmp/**` artifacts are ephemeral and must not be regenerated/frozen for closure ceremony after the relevant diff/evidence has already been reviewed. This is already covered by F009 and was violated once in the proposed UAT flow.
10. Long/critical output should state in advance exactly what evidence must be retained; use `tee tmp/...` from the first run when the output can scroll away.

## 15. New Work Discovered / follow-up

These are follow-ups, not blockers to FS-008 and not automatically approved tickets.

### A. Complete historical fixture/results populations

Current persistent historical population found during UAT:

- Premier League: 2024 complete; 2022/2023 missing;
- Bundesliga: 2022/2023/2024 missing;
- Serie A: 2022/2023/2024 missing;
- La Liga: 2022/2023/2024 already populated.

When API-Football quota is available, ingest only the eight missing season populations using the existing `sync_football_season` command and stop on the first provider/quota/access error.

This improves ordinary model/backtest evidence but does **not** solve historical market evidence.

### B. Research a historical-odds source

The current DB has historical results but lacks historical `OddsObservation` populations for the seasons needed by market-dependent evaluation.

A future F010 research task should identify a lawful/usable source that can provide:

- historical prematch 1X2 / MW3W odds;
- bookmaker-level values where possible;
- real historical observation/provider timestamps;
- Premier League, Bundesliga, Serie A, and La Liga coverage;
- at least the historical seasons used by backtests;
- documented ToS/licensing;
- cost/quota/access constraints;
- a provenance-preserving ingestion path into canonical `OddsObservation`.

Do **not** synthesize historical prices or backdate current snapshots.

The PR-review correction to the weekly evidence signature means that a legitimate future odds backfill will now trigger the next due evaluation instead of being ignored as unchanged evidence.

### C. Historical-ingest operator recipe

Run only after checking quota and only with the scheduler stopped:

```bash
cd ~/Projects/finsport

make safe-down
docker compose up -d --wait db

for spec in \
  "1273 2022" \
  "1273 2023" \
  "1274 2022" \
  "1274 2023" \
  "1274 2024" \
  "1275 2022" \
  "1275 2023" \
  "1275 2024"
do
  set -- $spec
  competition="$1"
  season="$2"

  count=$(
    docker compose run --rm --no-deps -T django-web \
      python manage.py shell -c \
      "from football.models import Match; print(Match.objects.filter(season__competition_id=$competition, season__year=$season).count())" \
      | tail -n 1
  )

  if [ "$count" != "0" ]; then
    echo "SKIP competition=$competition season=$season existing_matches=$count"
    continue
  fi

  echo "=== SYNC competition=$competition season=$season ==="

  docker compose run --rm --no-deps django-web \
    python manage.py sync_football_season \
    "$competition" "$season" || break
done
```

Afterward verify exact Match counts before running focused backtests.

No historical odds sweep is implied by this command.

## 16. Durable source reconciliation for Main Chat

Recommended source projection after merge:

- **F001**: reflect materially active capability state if it currently still describes R45/Inkabet/maintenance as deferred.
- **F003**: incorporate `MaintenanceRun`, pipeline-owned periodic maintenance, active R45 path, and automatic Inkabet MW3W boundary.
- **F004**: incorporate final operator contract for `make up`, `make dev-up`, `make status`, `make safe-down`, single Beat owner, persistent queue guard, and watchdog reconnect behavior.
- **F006**: mark FS-008 completed; replace stale deferred language for R45/Inkabet/new-season/weekly reselection; record historical results enrichment and historical-odds research as discovered future work without inventing priority.
- **F008/F009**: do not version-bump for ticket-specific bugs or individual review comments. Most execution problems found here are already covered by F009 v1.7. Main Chat should only consider clarifying the feedback-sequencing rule if the current wording still permits an implementation prompt to prohibit the versioned factual feedback snapshot.
- **F010**: use for the future historical-odds source investigation; no methodology change was established by FS-008 itself.

## 17. Acceptance status

Technical acceptance: **PASS**

Blocking PENDING items: **0**

Permitted factual limitations:

- historical market evidence is insufficient for market-dependent historical arms;
- some enabled leagues do not yet have complete 2022–2024 Match populations;
- Inkabet extended statistics are not implemented.

These limitations are explicit and do not invalidate FS-008.

## 18. Operational close

At final feedback generation:

- PR #13 is open and mergeable;
- review-fix code is pushed;
- final feedback still needs one versioned documentation commit because the last review correction was already committed without the reconciled final feedback;
- merge must wait for the latest GitHub checks required by the repository to be green.

After that:

```text
final feedback commit
→ push
→ squash merge PR #13
→ sync local master
→ delete ticket branch
→ delete FS-008 tmp artifacts
→ move Planka Review → Done
→ handoff to Main Chat
```
