# FS-006 — IMPLEMENTATION SNAPSHOT — MAY BECOME STALE

**Ticket:** FS-006 — Automatizar pipeline prospectivo end-to-end multi-liga
**Branch inspected:** `FS-006-prospective-pipeline`
**Pass:** implementation
**Snapshot date:** 2026-08-28
**Runtime boundary:** local-only / demo-only / research-oriented
**Financial side effects:** none; forbidden paths were not invoked

## Implemented architecture

- `football.pipeline.run_pipeline` is the reusable orchestration boundary. It calls the FS-005 capture service, the reusable per-competition prediction service, canonical settlement, the FS-004 capital service through a normalized baseline wrapper, cancellation hygiene, and report construction. It does not shell out to management commands.
- Every cycle exposes `CAPTURE`, `PREDICTION`, `RESULT_SETTLEMENT`, `CAPITAL`, and `REPORT` with explicit `SUCCESS`, `NO_WORK`, `SKIPPED`, `UNAVAILABLE`, `DEGRADED`, or `FAILED` state.
- `PipelineRun` persists cycle UUID/time, phase results, CaptureRun IDs, PredictionExperiment IDs, CapitalExperiment IDs, warnings/errors, configuration snapshot, and the full `fs006-report-v1` JSON-compatible report.
- The report is rolling over prospective experiments belonging to enabled domestic League competitions and includes current-cycle created/reused IDs separately.
- Competition selection remains data-driven through `Competition.enabled`; no league/provider ID is hardcoded in orchestration.

## Consolidated pre-UAT correction

- Pass-1 review found that the pipeline candidate contained exact `match_ids`, but `predict_competition_day` queried every eligible fixture in the same competition/day. A fixture whose own FS-005 `target_at` was later could therefore leak into an earlier logical experiment.
- `predict_competition_day(..., match_ids=None)` now preserves the existing public all-day behavior when omitted and, when supplied, normalizes IDs, intersects them with the existing prospective eligibility query, and predicts only the resulting rows.
- Pipeline candidates now normalize duplicated planner representation into sorted unique Match IDs and pass that frozen batch into the prediction service.
- Each created PredictionExperiment config persists the actual eligible `target_match_ids`; no schema or migration change was needed.
- The frozen prospective identity itself is unchanged.

## Frozen identities and semantics

- Prospective identity: `competition + America/Lima match day + FS-005 intended_window + target_at`. It is persisted on `PredictionExperiment` and protected by a conditional database unique constraint for `PROSPECTIVE` rows. Its content is restricted to the sorted unique Match batch belonging to that exact candidate identity.
- The prediction cutoff is the first actual aware cycle cutoff that processes that logical identity. Repeated wakes reuse the frozen experiment; later odds never rewrite its Predictions or Decisions. A later FS-005 target/window has a distinct identity.
- Missing market evidence records the market arm as unavailable while fitted non-market arms continue to persist Predictions and Decisions.
- Settlement updates only previously unresolved prospective Predictions whose Match has a status in canonical `FINISHED_STATUSES` and a canonical `Match.outcome` in HOME/DRAW/AWAY. It does not derive settlement from scores and does not modify Decision action/reason/price/observation.
- Capital identity hashes source prospective experiment, frozen input hash, selector, engine, and normalized configuration. Equivalent produced runs are reused; new pipeline-owned runs also have a database-unique identity.
- The capital measurement basis is explicitly labeled `DIXON_COLES / MODAL_ALL` with `REPLAY`, initial bankroll `100`, and one `FLAT_UNIT {"unit": "1"}` arm. It is a normalized research measurement basis, not a winning model or production policy selection.

## CANC lifecycle

- `cleanup_cancelled_matches` is transactional, exact-status guarded, dry-runnable, and idempotent.
- Its only destructive trigger is canonical `Match.status_short == "CANC"`.
- It preserves Match, MatchSourceRef, CaptureRun, and CaptureWorkItem audit.
- It deletes OddsSnapshot, OddsObservation, Prediction, and Decision derivatives for affected Matches.
- Before deleting Decisions it scans every `CapitalExperiment.input_manifest.decision_ids`, deletes each whole affected CapitalExperiment and its dependent policy/ledger rows, and therefore also catches stochastic experiments without ledger rows.
- It refreshes affected PredictionExperiment prediction/policy summaries and records bounded hygiene metadata there and in the pipeline report.
- PST, SUSP, FT, and ambiguous statuses are covered as non-destructive cases.

## Migration, interfaces, and settings

- Migration file: `football/migrations/0005_pipeline_run_and_prospective_identities.py`.
- New model: `PipelineRun`.
- New PredictionExperiment fields: `logical_identity`, `intended_window`, `target_at` plus prospective uniqueness constraint.
- New CapitalExperiment field: `logical_identity` plus conditional uniqueness constraint.
- New operator command: `run_football_pipeline --at <aware ISO-8601> [--dry-run] [--max-provider-attempts N]`.
- New Celery task: `football.pipeline.wake`.
- New setting: `FOOTBALL_PIPELINE_ENABLED`, default `False` in code and `.env.dist`.
- Scheduler invariant: pipeline enabled registers `football-pipeline-wake`; the standalone capture Beat entry is registered only by the `elif` branch. Manual `run_football_capture` and callable `football.capture.wake` remain present.
- The read-only Admin inventory now includes PipelineRun.
- `docs/operations/local_runtime.md` documents the command, service, default-off lifecycle, single-owner rule, baseline label, and CANC boundary.

## Automated evidence actually run

- Focused FS-006 suite: `16 passed`, including real explicit-target filtering for same-day earlier/later/shared logical targets — `tmp/FS-006_focused_evidence.txt`.
- Directly affected prediction regression: `25 passed`, with six existing dependency deprecation warnings — `tmp/FS-006_prediction_regression_evidence.txt`.
- General repository gate: `make check` PASS — Black PASS, Ruff PASS, Django system check PASS, full suite `214 passed`, six dependency deprecation warnings — `tmp/FS-006_make_check_evidence.txt`.
- Migration drift: `No changes detected` — `tmp/FS-006_migration_evidence.txt`.
- Scheduler enabled wiring: only `football-pipeline-wake` scheduled while both callable tasks are registered — `tmp/FS-006_scheduler_evidence.txt`.
- Scheduler normal configuration: pipeline OFF, capture OFF, empty Beat schedule — `tmp/FS-006_scheduler_default_evidence.txt`.
- `git diff --check`: PASS.
- No live provider call was made. All executed pipeline/capture integration in tests used dry-run or controlled test doubles.

## Acceptance state

- A01–A47 implementation acceptance ledger: `47 PASS / 0 PENDING / 0 N/A` in `tmp/FS-006_acceptance_ledger.md`.
- Automated multi-competition behavior uses two enabled domestic League fixtures.
- Automated cancellation UAT uses isolated Django test data only.
- No manual result was invented and no persistent local data was destructively modified.

## Manual UAT not executed in this pass

- Bounded real API-Football capture wiring: PENDING, execution-chat owned. Provider calls in this implementation pass were explicitly forbidden.
- Real multi-league UAT: UNAVAILABLE in the preflight snapshot because only La Liga had enabled/sufficient local history/upcoming data. The automated two-competition proof passes.
- Persistent local migration application and subsequent operator dry-run: PENDING, maintainer/UAT owned.
- Full Beat process restart/lifecycle observation: PENDING, execution-chat owned. Settings/task registration and single-owner scheduling are automated and evidenced.

## Warnings and deferred validation

- The repository emitted six Penaltyblog/NumPy deprecation warnings during the green suite. They are unrelated to FS-006 behavior and were not absorbed.
- A real provider run can change canonical Match state and can trigger CANC hygiene. It must use the ticket's bounded UAT fixtures/budget and must not sacrifice valuable local prospective observations.
- The normalized capital baseline requires a fully resolved, actionable, timestamp-valid selected-price stream. `UNAVAILABLE` is expected before honest settlement/price coverage and creates no pipeline baseline CapitalExperiment.

## New Work Discovered

### NWD-1 — Real multi-league local evidence is not yet available

- Evidence: `tmp/FS-006_preflight_inventory.txt` and `tmp/FS-006_multileague_candidates.txt` show one enabled/supported domestic League candidate with sufficient local evidence (La Liga).
- Impact: real two-league UAT cannot be claimed in this implementation pass.
- Recommendation: execution chat should bootstrap/enable the already frozen pilot leagues only under a separate bounded provider-authorized UAT, then rerun the pipeline report inspection.

### NWD-2 — Dependency deprecation warnings

- Evidence: the green focused regression and `make check` runs report six warnings from Penaltyblog code assigning NumPy array shapes.
- Impact: no current failure; a future NumPy/Penaltyblog upgrade could turn this compatibility warning into breakage.
- Recommendation: track dependency compatibility separately; do not expand FS-006 into dependency maintenance.

## Explicit exclusions confirmed

- No bookmaker authentication, cookies, browser, or Selenium path was added or executed.
- No real betting, financial external write, CapitalPolicy promotion, winner selection, dashboard, generic provider abstraction, generic observability platform, or retention framework was added.
- The maintainer-owned `docs/research/FS-006_cancelled_match_lifecycle_research.md` was read as reference and not modified.
- No commit, push, PR, merge, Planka action, destructive Git command, PostgreSQL volume operation, Redis purge, or live provider request occurred.
