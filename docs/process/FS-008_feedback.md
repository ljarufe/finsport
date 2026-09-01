# FS-008 Feedback

Status: **PRE-UAT / MAY BECOME STALE**
Updated: 2026-08-31
Branch: `FS-008-maintenance-refactor-cleanup`
Base/HEAD during implementation: `23a36fdcdd2354145360f1ab6b488ab4c5d1c838`

This document records automated implementation evidence only. Maintainer UAT,
CI, review, persistent migration, and the guarded FS004 synthetic cleanup have
not been claimed as passed.

## Current implementation

- Removed the legacy `bet` application/API, DRF, unused Celery database
  integrations, obsolete serializers, and obsolete pylint configuration.
- Added irreversible migration `football.0006_remove_legacy_bet_tables`, scoped
  to the two superseded bet tables, plus `football.0007_maintenancerun` for
  persistent daily/weekly due and audit state.
- Refreshed every retained direct dependency to the selected current supported
  release. Django remains on supported 5.2 LTS at 5.2.17. NumPy 2.4.6 is the
  documented compatibility exception for Penaltyblog 1.12.0 warning hygiene.
- Added `pip check` and pip-audit of the complete installed environment to the
  local/CI `make check` gate.
- `make up` starts core, worker, Beat, watchdog, Loki, Alloy, and Grafana across
  both profiles. `make dev-up` starts no Beat. `make status` is profile-aware
  and includes automation, maintenance due/last state, worker/queue, and DB-run
  state. `make safe-down` stops dispatchers first, drains with a bound, and
  removes every profile without `-v`.
- Activated `MODERNIZED_R45` in chronological backtests and prospective
  Prediction/Decision production. Selection is inner walk-forward; fitting and
  market evidence are strictly before the target cutoff. Factual insufficiency
  remains explicit `UNAVAILABLE`.
- Activated secondary, read-only, fail-soft Inkabet MW3W on successfully
  completed due odds windows. One categories discovery serves the run; only
  resolved relevant events receive MW3W requests. Manual and automatic paths
  now share one acquisition service.
- Added once-per-Lima-day catalogue maintenance, once-per-Lima-day DB season
  eligibility, and provider bootstrap only for enabled/current/resolved Seasons
  with no canonical Matches. Quota/reserve checks precede lower-priority
  maintenance and retries are bounded.
- Added weekly chronological evaluation and hyperparameter/config reselection
  under the same pipeline-owned maintenance cycle. An unchanged resolved
  evidence signature produces `NO_WORK` and preserves the prior selection.
- Inkabet extended statistics remain exactly `NOT_IMPLEMENTED`.
- Hardened watchdog DB reconnection and the guarded FS004 cleanup external-
  reference audit. No cleanup or persistent migration was executed.

## Scheduling and audit contract

There is one file-backed Celery Beat owner. With pipeline automation enabled it
registers `football.pipeline.wake` and suppresses the standalone capture wake.
The frequent wake runs immediate prospective phases first, then consults
persistent `MaintenanceRun` identities. Daily/weekly work is not repeated every
15 minutes and the first eligible wake after downtime can execute overdue work.

Actual due maintenance emits one bounded terminal event and persists identity,
attempts, status, quota evidence, configuration, summary, selected experiment
IDs, and sanitized errors. `CaptureRun.summary.secondary.inkabet` records
Inkabet effects/failures. R45 Predictions persist model version, variant,
configuration, cutoff, probabilities, and diagnostics.

## Dependency and automated evidence

- Clean image rebuild: PASS.
- `pip check`: PASS, no broken requirements.
- `pip-audit --local`: PASS, no known vulnerabilities.
- Black 26.5.1: PASS.
- Ruff 0.16.5: PASS.
- Django 5.2.17 system check: PASS, 0 silenced.
- Migration drift: PASS, no changes detected.
- Focused Pass-2 suite: PASS, 68 tests.
- Final runtime-control focus: PASS, 4 tests.
- Final `make check`: PASS, 271 tests, 86.41% branch coverage.
- Avoidable runtime/test warnings: none reported.
- Compose base/profile configuration: PASS; all-profile service list includes
  Beat, watchdog, Loki, Alloy, and Grafana.
- Read-only pre-migration `make status`: PASS; it saw the running DB/Redis across
  the complete project, reported zero queue/known running jobs, represented the
  not-yet-migrated MaintenanceRun table as `null`, and did not claim dispatch.
- `git diff --check`: recorded in the final acceptance artifact.

The full pytest database proves the fresh migration path. The Pass-1 disposable
PostgreSQL validation proved both fresh and existing upgrade behavior for 0006.
Migration 0007 has schema/drift/fresh-test evidence; applying 0006/0007 to the
maintainer database remains explicitly pending.

## Behavior-preserving refactor review

| Problem | Change | Equivalence/safety | Evidence |
| --- | --- | --- | --- |
| Manual and automatic Inkabet paths could duplicate categories/reconciliation/MW3W/error handling | Both use `capture_inkabet_matches` | Same read-only provider calls and canonical persistence; automatic-only enable flag does not disable the manual override | Command, automatic, schema-drift, fail-soft, and idempotency tests pass |
| Capture quota state knew only CaptureRun attempts | Combined CaptureRun and MaintenanceRun evidence in one quota calculation | Existing capture priorities/reserves remain; maintenance cannot hide headerless attempts | Capture/quota and daily-maintenance tests pass |
| Modernized R45 helpers existed without runtime ownership | Factored reusable grid/select/fit/predict helpers into backtest and prospective services | Existing probability/Decision semantics are unchanged; only a formerly disconnected arm is produced when evidence is valid | Positive persistence and strict-cutoff tests pass |
| Long-running watchdog could retain a failed DB wrapper | Refresh old connections and close a failed wrapper | Liveness semantics/event suppression remain unchanged | Failure/recovery tests pass |
| Runtime profile inspection could hide profiled containers | One all-profile Compose boundary serves status and shutdown | Same project/volumes; broader correct visibility only | Runtime-control tests and Compose service inventory pass |
| New maintenance paths repeated provider/error/audit concerns | Central persistent MaintenanceRun lifecycle and terminal event helper | Capability-specific due/call logic remains explicit; no extra scheduler | Daily/weekly idempotency tests pass |

Repository-wide inspection covered capture, pipeline, prediction, capital,
sync/reconciliation, both provider clients, management commands, observability,
settings/tooling, and the complete test tree. No product-semantic capital,
Decision, outcome, price, or betting changes were absorbed.

## Test-suite maintenance review

- Removed tests for deleted legacy bet/serializer runtime.
- Replaced legacy R45 inert-accounting assertions with active persistence and
  anti-leakage contracts.
- Reused the existing football factories/helpers for maintenance, R45, capture,
  and Inkabet coverage rather than adding a second model factory layer.
- Consolidated manual/automatic Inkabet behavior behind one implementation
  while preserving command/provider contract tests.
- Added focused profile visibility/quiescence, daily catalogue, season
  eligibility, weekly no-new-evidence, automatic Inkabet, and watchdog recovery
  tests.
- Kept branch coverage global; no functional code was excluded to raise it.

## Product Findings

- Active experimentation now has an evidence-generation lifecycle, but no model
  or policy has been selected as a winner.
- Provider quota on the free plan is shared by immediate capture and maintenance;
  maintenance correctly runs after immediate work and can defer.
- A current Season with zero canonical Matches is the auditable bootstrap signal.
  A valid empty provider response remains incomplete and may retry on a later
  daily cycle; a populated successful Season is never fetched again.
- Inkabet remains useful only as secondary market evidence. It is not canonical
  football identity/outcome authority.

## Harness Findings

- Buildx needs to update state under `~/.docker`; the sandboxed rebuild fails
  before compilation and requires approved Docker execution.
- pip-audit 2.10.1 rejects the older `--disable-pip` invocation without a hashed
  requirements file. Auditing the complete installed image with `--local` is the
  compatible reproducible gate.
- Compose-run checks start DB/Redis dependencies but do not migrate the normal
  persistent database. CI therefore uses profile-aware `compose down` for its
  disposable cleanup; operator `safe-down` checks whatever run tables exist and
  reports a missing new maintenance table until migration.

## New Work Discovered

- PRODUCT: FS-009 still owns presentation/reporting over persisted experiments;
  FS-010 still owns comparative model/policy evaluation. Neither is part of
  FS-008.
- PRODUCT: Inkabet extended-statistics ingestion remains unimplemented and needs
  a separate explicit product decision.
- HARNESS: a future lockfile/hashes decision could make requirement-file
  pip-audit independent of the built environment; the current installed-image
  audit is complete and green.
- OPERATIONS: provider-denied or genuinely empty new Seasons need observation in
  real UAT to calibrate daily bounds; no automatic expansion is justified yet.

## Pending / blocked

PENDING maintainer control:

- review the complete diff and artifacts;
- back up and migrate the persistent database;
- run real provider/R45/maintenance UAT;
- run operational, dev, shutdown, Grafana, and watchdog interruption UAT;
- review and optionally apply the exact FS004 synthetic cleanup;
- CI and maintainer review.

BLOCKED: none in implementation. Live/persistent/destructive evidence is
intentionally maintainer-owned.

## Exact maintainer UAT order

Use the new image and the ignored local `.env`; never add bookmaker credentials.
Replace only the explicitly marked research IDs/dates after inspecting the
queries.

### 1. Quiesce, back up, and migrate the existing database

```bash
cd ~/Projects/finsport
git branch --show-current
git status --short
make safe-down
docker compose up -d --wait db
mkdir -p tmp
docker compose exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > tmp/FS-008-pre-uat-cleanup.dump
test -s tmp/FS-008-pre-uat-cleanup.dump
docker compose run --rm --no-deps django-web \
  python manage.py showmigrations football
docker compose run --rm --no-deps django-web \
  python manage.py migrate --noinput
docker compose run --rm --no-deps django-web \
  python manage.py showmigrations football
```

### 2. Prove the fresh migration/test path and cleanup dry run

```bash
make check
docker compose run --rm --no-deps -T django-web \
  python manage.py shell < tmp/FS-008_uat_cleanup.py
```

Review that JSON. Do not set `FS008_APPLY` yet.

### 3. Discover an eligible real research population

```bash
docker compose run --rm --no-deps django-web python manage.py shell -c \
  "from django.db.models import Count; from football.models import Competition, Season; print(list(Season.objects.filter(competition__enabled=True, competition__competition_type='League').annotate(matches_count=Count('matches')).values('competition_id','competition__name','year','is_current','matches_count').order_by('competition_id','year')))"
```

Set these task-specific values from reviewed canonical rows:

```bash
export FS008_COMPETITION_ID=<local-competition-id>
export FS008_OUTER_SEASON=<outer-season-year-with-two-prior-seasons>
export FS008_TARGET_DATE=<YYYY-MM-DD-with-eligible-upcoming-match>
export FS008_CUTOFF=<offset-aware-ISO-8601-before-kickoff>
export FS008_MATCH_ID=<eligible-local-match-id>
```

### 4. Run daily maintenance and weekly evaluation/reselection now

This performs bounded read-only provider work when due.

```bash
docker compose run --rm django-web \
  python manage.py run_football_maintenance --force-weekly
docker compose run --rm django-web \
  python manage.py run_football_maintenance
docker compose run --rm --no-deps django-web python manage.py shell -c \
  "from football.models import MaintenanceRun; print(list(MaintenanceRun.objects.values('id','capability','logical_identity','status','attempt_count','provider_attempts','next_eligible_at','completed_at','summary').order_by('-id')[:20]))"
```

The second same-day call must show daily `NOT_DUE`; weekly must not recompute.
Catalogue/season failures must be factual `SKIPPED_QUOTA`, `DEGRADED`, or
`FAILED`, never silent repeated calls.

### 5. Prove MODERNIZED_R45 backtest selection and persistence

```bash
docker compose run --rm --no-deps django-web \
  python manage.py evaluate_football_predictions \
  --competition "$FS008_COMPETITION_ID" --season "$FS008_OUTER_SEASON"
docker compose run --rm --no-deps django-web python manage.py shell -c \
  "from football.models import PredictionExperiment, Prediction; e=PredictionExperiment.objects.filter(competition_id=$FS008_COMPETITION_ID, mode='BACKTEST', completed_at__isnull=False).latest('completed_at'); print({'experiment':e.id,'config':e.config.get('selected_hyperparameters',{}).get('modernized_r45'),'summary':e.summary,'r45_predictions':e.predictions.filter(model_code=Prediction.MODERNIZED_R45).count(),'r45_decisions':e.decisions.filter(prediction__model_code=Prediction.MODERNIZED_R45).count()})"
```

### 6. Prove bounded prospective API-Football + Inkabet + R45

```bash
docker compose run --rm django-web python manage.py run_football_capture \
  --at "$FS008_CUTOFF" --match-id "$FS008_MATCH_ID" \
  --purpose ODDS_CAPTURE --max-provider-attempts 2 --dry-run
docker compose run --rm django-web python manage.py run_football_pipeline \
  --at "$FS008_CUTOFF" --max-provider-attempts 2
docker compose run --rm --no-deps django-web python manage.py shell -c \
  "from football.models import CaptureRun, OddsObservation, Prediction, Decision; print({'capture':CaptureRun.objects.latest('id').summary,'inkabet_observations':list(OddsObservation.objects.filter(match_id=$FS008_MATCH_ID,source__code='inkabet').values('id','observed_at','home','draw','away')),'r45_predictions':list(Prediction.objects.filter(match_id=$FS008_MATCH_ID,model_code=Prediction.MODERNIZED_R45).values('id','experiment_id','variant','model_version','model_config','cutoff','diagnostics')),'r45_decisions':list(Decision.objects.filter(match_id=$FS008_MATCH_ID,prediction__model_code=Prediction.MODERNIZED_R45).values('id','policy_code','action','selected_odds_observation_id'))})"
```

If no odds window is actually due, preserve the `NO_WORK` evidence and choose a
real eligible row; do not move timestamps or fabricate provider data.

### 7. Operational stack, scheduler, maintenance state, and Grafana

```bash
make up
make status
docker compose --profile operational --profile observability ps
docker compose logs --tail=120 celery-beat celery observability-watch
curl --fail --silent --show-error http://127.0.0.1:3000/api/health
```

Verify exactly one pipeline Beat entry and no second maintenance/Inkabet
scheduler. Inspect `Football > Maintenance runs`, Capture runs, Prediction
experiments, Predictions, and Decisions in Admin.

### 8. Watchdog PostgreSQL interruption/recovery

```bash
docker compose stop db
sleep 75
docker compose logs --tail=120 observability-watch
docker compose start db
docker compose up -d --wait db
sleep 75
docker compose logs --tail=120 observability-watch
```

Expect one bounded actionable dependency incident, successful reconnection
without restarting the watchdog, and no error storm.

### 9. Profile-complete safe shutdown and volume preservation

```bash
docker volume inspect finsport_postgres_data finsport_redis_data \
  finsport_loki_data finsport_alloy_data finsport_grafana_data \
  > tmp/FS-008-volumes-before.json
make safe-down
docker compose --profile operational --profile observability ps -a
if curl --fail --silent http://127.0.0.1:3000/api/health; then exit 1; fi
docker volume inspect finsport_postgres_data finsport_redis_data \
  finsport_loki_data finsport_alloy_data finsport_grafana_data \
  > tmp/FS-008-volumes-after.json
```

### 10. Development-safe stack with operational `.env` unchanged

```bash
make dev-up
make status
docker compose --profile operational --profile observability ps
if docker compose --profile operational --profile observability ps --services \
  | grep -E 'celery-beat|observability-watch|loki|alloy|grafana'; then exit 1; fi
make safe-down
```

`scheduled_dispatch_possible` must be false and Beat must be absent.

### 11. Optional maintainer-owned synthetic cleanup, only after review

```bash
docker compose up -d --wait db
test -s tmp/FS-008-pre-uat-cleanup.dump
docker compose run --rm --no-deps -T \
  -e FS008_APPLY=DELETE_FS004_SYNTHETIC_GRAPH \
  -e FS008_SAFETY_DUMP=/app/tmp/FS-008-pre-uat-cleanup.dump \
  django-web python manage.py shell < tmp/FS-008_uat_cleanup.py
docker compose run --rm --no-deps django-web python manage.py check
docker compose run --rm --no-deps django-web python manage.py migrate --check
make dev-up
make status
```

This final apply remains optional and destructive. Stop and investigate any
manifest mismatch or external-reference finding; never weaken the guard.
