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

Celery Beat remains available, but `CELERY_BEAT_SCHEDULE` is empty. The normal Beat command uses Celery's file scheduler at an ephemeral `/tmp` path, not `django-celery-beat`'s `DatabaseScheduler`; persisted PostgreSQL schedule rows therefore cannot dispatch the historical betting cycle.

The historical `bet.tasks.run_betting_cycle` module and all betting management commands have been removed. Celery remains available for future safe application tasks, but has no configured Beat jobs.

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

Every API-Football call and pagination page is counted. Quota headers are authoritative; the default daily reserve is zero and another request is refused once the known remaining budget reaches zero. Retries, pagination, and sequential pacing are bounded. No final T-minus cutoff or intraday allocation algorithm is implemented.

There is no scheduler, notification email, or automatic new-season bootstrap in FS-002. Source documentation/official status is tracked as reliability context, not a terms/licensing acceptance gate for this local personal research project.

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
