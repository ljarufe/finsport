# Safe Local Runtime

Finsport is local-only and demo-only. This document describes the supported runtime; it does not define any external server or deployment path.

## Development / Normal UAT Startup

Create `.env` from `.env.dist`, then run:

```bash
make build
make dev-up
```

This path explicitly starts PostgreSQL, Redis, Django, the manual Celery worker,
and Nginx. It does not start `celery-beat` or the watchdog. Scheduled provider
dispatch is therefore impossible even when the unchanged operational `.env`
contains `FOOTBALL_PIPELINE_ENABLED=True`. Use only `make dev-up` for this
development-safe contract.

| Port | Service |
| --- | --- |
| 5432 (or `DATABASE_PORT`) | PostgreSQL |
| 6379 | Redis |
| 8000 | Direct Django/Gunicorn technical endpoint |
| 8001 | Normal browser/Admin endpoint through Nginx |
| 8002 | VS Code Django debug server |

Admin is mounted at the root `/`, not `/admin/`. The supported normal browser endpoint is <http://localhost:8001/>. Nginx proxies Django and serves collected files under `/static/`, including Django Admin CSS.

The direct endpoint <http://localhost:8000/> reaches Gunicorn/Django and is useful for technical probes. It is not expected to serve collected static files and may therefore appear unstyled in a browser.

## Operational Startup

Use the complete runtime only when scheduled provider work is intended:

```bash
make up
make status
```

This starts the `operational` and `observability` profiles: Beat, watchdog,
Loki, Alloy, and Grafana in addition to the base services. Grafana is available
at <http://localhost:3000/>. `make observability-up` is a compatibility alias for
the same complete operational path; `make operational-up` is the descriptive
alias for `make up`. The ignored `.env` still controls whether the pipeline task
is registered and whether read-only provider work is authorized.

## Graceful Shutdown

Stop the stack while preserving normal data:

```bash
make safe-down
```

The command first stops Beat, then stops the watchdog before PostgreSQL. It
polls Celery active/reserved/scheduled work, Redis DB 14 queue
`finsport.local.safe`, and persisted `PipelineRun`/`CaptureRun`/`MaintenanceRun`
`RUNNING` rows.
Only a completely quiescent snapshot permits Compose shutdown. The default
timeout is 120 seconds and can be narrowed or extended with
`FINSPORT_SAFE_DOWN_TIMEOUT_SECONDS`; timeout leaves the stack running with
dispatchers stopped. `make down` delegates to this same path.

Never add `-v`. The named `postgres_data` volume is the persistent development
database and must not be deleted, recreated, or restored from `finsport.sql` as
part of routine development. Django tests use Django's separate test database
isolation.

## Celery And Redis Safety Model

Redis is persistent and can contain unknown legacy messages. It is not purged. The current local boundaries are:

- Redis DB 13: Django cache;
- Redis DB 14: local Celery broker;
- Redis DB 15: local Celery results;
- queue `finsport.local.safe`: the only queue consumed by the normal worker.

The historical worker used Redis DB 0, so the normal worker cannot consume that retained broker state. This isolates old messages without deleting them.

Celery Beat exists only in the explicit `operational` profile. The safe football
schedules are absent by default. FS-005 capture can be enabled with
`FOOTBALL_CAPTURE_ENABLED=True`; FS-006 pipeline automation can be enabled with
`FOOTBALL_PIPELINE_ENABLED=True`. When pipeline automation is enabled it is the
only scheduled owner that can invoke capture, even if both flags are true. Beat
uses Celery's file scheduler at an ephemeral `/tmp` path. The unused
`django-celery-beat` and `django-celery-results` integrations are not installed;
Redis DB 15 remains the result backend.

The pipeline wake is the single automatic orchestration owner. Its frequent
wake performs normal prospective work and then checks persistent daily/weekly
maintenance identities; it does not turn daily catalogue/season work or weekly
evaluation into 15-minute work. `make status` reports the complete profile-aware
service set, dispatch capability, quiescence counters, and maintenance due/last
state.

The legacy `bet` application, its API, and all betting management commands have
been removed. The supported application tasks are `football.capture.wake` and
`football.pipeline.wake`. They delegate to reusable read-only/research services
and contain no betting business rules. Manual capture remains available when
pipeline automation owns the Beat schedule. Real betting and bookmaker
authentication remain forbidden.

## API-Football Manual Workflow

Store `API_FOOTBALL_KEY`, `INKABET_BRAND_ID`, and `INKABET_MARKET_CODE` only in the ignored local `.env`. Do not place their local values in commands, source, tests, logs, or feedback. Run the occasional catalogue operation first:

```bash
docker compose run --rm django-web python manage.py sync_football_catalog
```

This refreshes canonical Competition and Season lifecycle/coverage metadata from `/leagues`, resolves Match Winner from `/odds/bets`, seeds resolved API-Football CompetitionSourceRefs, and leaves newly discovered competitions disabled. Enable only a selected domestic professional Competition in Admin. Use its canonical local ID for a supported historical season bootstrap:

```bash
docker compose run --rm django-web python manage.py sync_football_season <competition-id> <provider-year>
```

The season command gets all fixture/team identity from the fixture payload; it does not call `/teams`. The daily morning/evening flow is:

```bash
docker compose run --rm django-web python manage.py sync_football_day --date YYYY-MM-DD --with-odds
docker compose run --rm django-web python manage.py sync_football_day --date YYYY-MM-DD
```

The first global Lima-timezone fixture-date response is filtered locally by `Competition.enabled`. API-Football Teams and Matches are canonicalized through resolved source refs. With odds enabled, API Match Winner calls are per relevant fixture and require explicit Season API odds coverage. Inkabet categories are fetched once, mappings are reconciled without prompts, and accordion MW3W is fetched only for resolved relevant Match refs. Pending mappings are skipped and reported for Django Admin review.

Every API-Football call and pagination page is counted. Quota headers are authoritative; the legacy sync command retains its own `API_FOOTBALL_DAILY_RESERVE`, while FS-005 uses `FOOTBALL_CAPTURE_MANDATORY_RESERVE`. Retries, pagination, and sequential pacing are bounded. No final T-minus cutoff or intraday allocation algorithm is implemented.

There is no notification email. Automatic new-season work uses only a current
Season already discovered by catalogue maintenance, an enabled Competition, a
resolved API-Football source ref, and an empty canonical match set. A completed
season bootstrap is not fetched again. Source documentation/official status is
tracked as reliability context, not a terms/licensing acceptance gate for this
local personal research project.

## Quota-Aware Temporal Capture

FS-005 exposes one reusable Python service:

```python
from football.capture import run_capture

result = run_capture(
    at=aware_datetime,             # default: timezone.now()
    dry_run=False,
    trigger="MANUAL",             # or CaptureRun.Trigger.SCHEDULER
    match_id=None,                 # optional safe operator/UAT filter
    purpose=None,                  # ODDS_CAPTURE/FIXTURE_REFRESH/RESULT_REFRESH
    window=None,                   # optional configured window name
    max_provider_attempts=None,    # narrows, never expands, the configured bound
    allow_bootstrap=False,         # explicit first-call authority only
)
```

It returns a `CaptureResult`; `as_dict()` contains the audit run ID, quota before/after and basis, attempts/pages/retries, observations and snapshot effects, fixtures changed, matches resolved, completed work, explicit skips, and failures. Provider/configuration errors are converted to persisted, sanitized `CaptureWorkItem` statuses. A concurrent executor returns `CONCURRENT_EXECUTOR` with zero provider calls. Idempotency is the successful logical identity `provider + fixture + market + intended window + target_at`; failed/partial work is not automatically retried within the same identity, while a later configured window remains valid.

The operator interface is:

```bash
docker compose run --rm django-web \
  python manage.py run_football_capture \
  --at 2026-08-29T13:00:00-05:00 \
  --dry-run
```

Dry-run is the normal first step. It makes no provider call and writes no `CaptureRun`, `CaptureWorkItem`, `OddsObservation`, or other data. Its JSON shows planning time, quota basis/freshness, reserve, eligible/due work, min/max cost, deterministic priorities, planned calls, and skips/reasons. Safe UAT filters are `--match-id`, `--purpose`, `--window`, and `--max-provider-attempts`; they do not affect scheduler eligibility. `--allow-bootstrap` explicitly permits an optional odds call only within `FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS` when no header exists in the current UTC quota epoch. Mandatory result/discovery work can use the same bounded bootstrap without that flag; the scheduler never opts optional odds into bootstrap.

Capture policy is local configuration:

- `FOOTBALL_CAPTURE_WINDOWS`: JSON list containing `early`, `middle`, and at most one optional `near...` name; each item has `offset_minutes`, `before_tolerance_minutes`, `normal_tolerance_minutes`, and `late_tolerance_minutes`;
- `FOOTBALL_CAPTURE_HORIZON_HOURS`: future eligibility horizon;
- `FOOTBALL_CAPTURE_MANDATORY_RESERVE`: absolute quota protected from optional odds work;
- `FOOTBALL_CAPTURE_MAX_OPERATION_PAGES`, `FOOTBALL_CAPTURE_MAX_PROVIDER_ATTEMPTS`, and `FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS`: independent safety bounds;
- `FOOTBALL_CAPTURE_RESULT_REFRESH_ENABLED`, `FOOTBALL_CAPTURE_RESULT_DELAY_MINUTES`, and `FOOTBALL_CAPTURE_RESULT_CADENCE_MINUTES`: bounded canonical outcome refresh;
- `FOOTBALL_CAPTURE_DISCOVERY_ENABLED`, `FOOTBALL_CAPTURE_DISCOVERY_CADENCE_MINUTES`, and `FOOTBALL_CAPTURE_DISCOVERY_DAYS_AHEAD`: optional canonical date discovery horizon/cadence, disabled by default. The free-plan-safe baseline is `1`, meaning today and tomorrow only; a genuinely unsupported request remains an actionable `provider_access_denied` failure.

The shipped offsets are research defaults, not product truth. `target_at`, `not_before`, `not_after`, actual execution time, observation time, and lateness remain distinct aware timestamps. A kickoff change produces new future targets; observations always retain actual capture time.

### Automatic wake lifecycle

`FOOTBALL_CAPTURE_ENABLED=False` is the default. In the operational path it
contributes no capture Beat schedule and causes zero automated provider calls;
the development path never starts Beat at all. Direct invocation of the task
also returns `DISABLED` without calling the service.

To opt in, set at least:

```dotenv
FOOTBALL_CAPTURE_ENABLED=True
FOOTBALL_CAPTURE_WAKE_SECONDS=900
```

Then restart with `make operational-up`; no additional activation command is
needed after later operational starts while the setting remains enabled. Django
settings add `football.capture.wake` to the file-backed Beat schedule. Beat only
wakes `run_capture`; a no-due plan instantiates no provider client, records a
`NO_WORK` run, and consumes zero quota. `make dev-up` never starts Beat.

The required processes are PostgreSQL, Redis, Django, the `finsport.local.safe` Celery worker, and Celery Beat. Verify wake delivery with:

```bash
docker compose logs --tail=80 celery-beat celery
```

Then inspect `Football > Capture runs` and `Football > Capture work items` in Admin. Runs expose scheduler/planner/executor activity, quota blocking, missed/late windows, provider attempts, pagination, result failures, and sanitized async errors. Transport startup failures before Django can create a run, Beat/worker process death, and broker-level delivery loss remain log-only; general alerting and cross-pipeline health belong to a future observability ticket.

Inkabet remains secondary, read-only, GET-only, and fail-soft. A successfully
completed due API-Football `ODDS_CAPTURE` item triggers one shared categories
discovery for the run and one MW3W request per resolved relevant event. A
non-due/repeated window makes no Inkabet request. Failures mark the capture
degraded while preserving canonical API-Football work; Inkabet never becomes
football authority and does not inherit API-Football quota semantics.

## Prospective Multi-League Pipeline

FS-006 composes capture, prospective prediction, canonical settlement, the normalized research capital comparator, cancellation hygiene, and a rolling JSON report without invoking management commands from Python services:

```python
from football.pipeline import run_pipeline

result = run_pipeline(
    at=aware_datetime,
    dry_run=False,
    max_provider_attempts=None,  # narrows the FS-005 configured bound
)
```

The operator entry point requires an explicit offset-aware cutoff:

```bash
docker compose run --rm django-web \
  python manage.py run_football_pipeline \
  --at 2026-08-29T03:00:00-05:00 \
  --dry-run
```

Dry-run calls the FS-005 DB-only planner but makes zero provider calls and writes no pipeline audit, prediction, Decision, capital, or cleanup rows. Executed cycles persist a read-only `PipelineRun` audit with phase states, linked run/experiment IDs, warnings/errors, and the `fs006-report-v1` report.

Prospective identity is `competition + America/Lima match day + intended_window + target_at`; the database prevents duplicates for the same logical cutoff while allowing a later FS-005 window. Missing market evidence is explicit and does not suppress fitted non-market arms. Settlement accepts only a canonical finished status plus canonical HOME/DRAW/AWAY outcome and never rewrites the original Decision or selected price.

The capital phase uses only the labeled research comparator `REPLAY / 100 units / FLAT_UNIT {"unit": "1"}` over the frozen Dixon-Coles/MODAL_ALL basis. It records `UNAVAILABLE` without creating a `CapitalExperiment` when outcomes, actionable Decisions, or timestamp-valid prices are absent. This is not a selected production model or capital policy.

Cancellation hygiene triggers only on canonical `status_short == "CANC"`. It preserves Match, MatchSourceRef, CaptureRun, and CaptureWorkItem audit while transactionally removing invalid OddsSnapshot, OddsObservation, Prediction, Decision, and whole dependent CapitalExperiments. `PST`, `SUSP`, `FT`, and ambiguous statuses are not destructive triggers.

Pipeline automation is off by default:

```dotenv
FOOTBALL_PIPELINE_ENABLED=False
```

When explicitly changed to `True`, use `make up`. Beat registers
`football.pipeline.wake` and suppresses the standalone `football.capture.wake`
schedule, preserving one automatic provider-calling path. The callable capture
task and both manual commands remain available. Prediction candidates continue
to originate from due `ODDS_CAPTURE` work in an intended window, not every match
on every wake.

### Daily and weekly experimental maintenance

`FOOTBALL_MAINTENANCE_ENABLED=True` lets that same pipeline wake evaluate three
persistent capabilities in `America/Lima`:

- catalogue refresh once per local day, after immediate pipeline work and only
  when its conservative API-Football budget fits above the mandatory reserve;
- a DB-only season eligibility check once per local day, with at most the
  configured number of genuinely empty current Seasons bootstrapped;
- chronological backtests and hyperparameter/config reselection once every
  seven local days, with `NO_WORK` when the resolved-evidence signature did not
  change.

`MaintenanceRun` records identities, attempts, terminal state, quota evidence,
configuration, summaries, selected experiment IDs, and sanitized failures. A
quota-deferred catalogue refresh has a bounded same-day retry time; failed or
denied season work waits for a later daily check. The manual commands remain:

```bash
docker compose run --rm django-web python manage.py run_football_maintenance
docker compose run --rm django-web python manage.py run_football_maintenance --force-weekly
docker compose run --rm django-web python manage.py evaluate_football_predictions <competition-id> <season-year>
```

The weekly backtest performs chronological inner selection and outer
train/predict/reveal for every active arm, including `MODERNIZED_R45`. A latest
completed backtest configuration feeds prospective R45; when none exists, the
prospective path may make an equivalent selection using strictly prior resolved
history and timestamp-valid market observations. Factual insufficiency remains
an explicit `UNAVAILABLE`; no arm or policy is declared a winner.

The long-running watchdog refreshes old Django connections before each query
and explicitly discards a failed PostgreSQL connection. A real interruption may
emit one bounded `OBSERVABILITY_WATCHDOG_FAILED`; duplicates remain suppressed
until a successful query reconnects and resets the episode without a container
restart.

See [Capability execution matrix](capability_matrix.md) for automatic, manual,
deferred, and removed capabilities.

## Checks

```bash
make django-check
make migration-check
make test
make coverage
make lint
make format
make format-check
make check
docker compose config
```

`make check` is the non-mutating shipping gate: Black verification, Ruff,
Django system checks, migration drift, the full pytest suite, branch coverage,
and the global 80% coverage minimum. Its cache and coverage data are written
under `/tmp`.

Observability / audit impact: new daily/weekly terminal events, MaintenanceRun
Admin/state, Inkabet degradation evidence, and persisted R45 diagnostics are
bounded to actual due work or meaningful failures rather than every wake.
