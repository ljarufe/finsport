# Safe Local Runtime

Finsport is local-only and demo-only. This document describes the supported runtime; it does not define any external server or deployment path.

## Normal Startup

Create `.env` from `.env.dist`, then run:

```bash
make build
make up
```

The normal Compose path starts PostgreSQL, Redis, Django, Celery, Celery Beat, and Nginx. Legacy scraping and bookmaker-browser services are not part of the runtime.

| Port | Service |
| --- | --- |
| 5432 (or `DATABASE_PORT`) | PostgreSQL |
| 6379 | Redis |
| 8000 | Direct Django/Gunicorn technical endpoint |
| 8001 | Normal browser/Admin endpoint through Nginx |
| 8002 | VS Code Django debug server |

Admin is mounted at the root `/`, not `/admin/`. The supported normal browser endpoint is <http://localhost:8001/>. Nginx proxies Django and serves collected files under `/static/`, including Django Admin CSS.

The direct endpoint <http://localhost:8000/> reaches Gunicorn/Django and is useful for technical probes. It is not expected to serve collected static files and may therefore appear unstyled in a browser.

Stop the stack while preserving normal data:

```bash
make down
```

Never add `-v`. The named `postgres_data` volume is the persistent development database and must not be deleted, recreated, or restored from `finsport.sql` as part of routine development. Django tests use Django's separate test database isolation.

## Celery And Redis Safety Model

Redis is persistent and can contain unknown legacy messages. It is not purged. The current local boundaries are:

- Redis DB 13: Django cache;
- Redis DB 14: local Celery broker;
- Redis DB 15: local Celery results;
- queue `finsport.local.safe`: the only queue consumed by the normal worker.

The historical worker used Redis DB 0, so the normal worker cannot consume that retained broker state. This isolates old messages without deleting them.

Celery Beat remains available. FS-005 adds one safe optional wake task, but its schedule is absent unless `FOOTBALL_CAPTURE_ENABLED=True`. The normal Beat command uses Celery's file scheduler at an ephemeral `/tmp` path, not `django-celery-beat`'s `DatabaseScheduler`; persisted PostgreSQL schedule rows therefore cannot dispatch the historical betting cycle.

The historical `bet.tasks.run_betting_cycle` module and all betting management commands have been removed. The only supported application task is `football.capture.wake`; it delegates to the same read-only capture service used by the operator command and contains no fixture, window, quota, or betting business rules.

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

There is no notification email or automatic new-season bootstrap. Source documentation/official status is tracked as reliability context, not a terms/licensing acceptance gate for this local personal research project.

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
- `FOOTBALL_CAPTURE_DISCOVERY_ENABLED`, `FOOTBALL_CAPTURE_DISCOVERY_CADENCE_MINUTES`, and `FOOTBALL_CAPTURE_DISCOVERY_DAYS_AHEAD`: optional canonical date discovery horizon/cadence, disabled by default.

The shipped offsets are research defaults, not product truth. `target_at`, `not_before`, `not_after`, actual execution time, observation time, and lateness remain distinct aware timestamps. A kickoff change produces new future targets; observations always retain actual capture time.

### Automatic wake lifecycle

`FOOTBALL_CAPTURE_ENABLED=False` is the default. In that state `make up` still starts worker and Beat, but FS-005 contributes no Beat schedule and causes zero automated provider calls. Direct invocation of the task also returns `DISABLED` without calling the service.

To opt in, set at least:

```dotenv
FOOTBALL_CAPTURE_ENABLED=True
FOOTBALL_CAPTURE_WAKE_SECONDS=900
```

Then restart with `make up`; no additional activation command is needed after later machine restarts while the setting remains enabled. Django settings add `football.capture.wake` to the file-backed Beat schedule. Beat only wakes `run_capture`; a no-due plan instantiates no provider client, records a `NO_WORK` run, and consumes zero quota.

The required processes are PostgreSQL, Redis, Django, the `finsport.local.safe` Celery worker, and Celery Beat. Verify wake delivery with:

```bash
docker compose logs --tail=80 celery-beat celery
```

Then inspect `Football > Capture runs` and `Football > Capture work items` in Admin. Runs expose scheduler/planner/executor activity, quota blocking, missed/late windows, provider attempts, pagination, result failures, and sanitized async errors. Transport startup failures before Django can create a run, Beat/worker process death, and broker-level delivery loss remain log-only; general alerting and cross-pipeline health belong to a future observability ticket.

Inkabet remains secondary, read-only, GET-only, and fail-soft in the existing manual daily workflow. FS-005 does not schedule it and does not apply API-Football quota semantics to it.

## Checks

```bash
make django-check
make test
make coverage
make lint
make format
make format-check
make check
docker compose config
```

`make check` is a non-mutating gate containing Black format verification, Ruff lint, Django's system check, and the focused pytest suite. Coverage remains informational and migration drift remains outside the gate.
