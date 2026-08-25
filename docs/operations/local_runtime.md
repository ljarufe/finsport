# Safe Local Runtime

Finsport is local-only and demo-only. This document describes the supported runtime; it does not define any external server or deployment path.

## Normal Startup

Create `.env` from `.env.dist`, then run:

```bash
make build
make up
```

The normal Compose path starts PostgreSQL, Redis, Django, Celery, Celery Beat, and Nginx. It does not start Selenium because that service belongs to the `selenium` profile.

| Port | Service |
| --- | --- |
| 5432 (or `DATABASE_PORT`) | PostgreSQL |
| 6379 | Redis |
| 8000 | Direct Django/Gunicorn technical endpoint |
| 8001 | Normal browser/Admin endpoint through Nginx |
| 8002 | VS Code Django debug server |
| 4444 | Selenium, only when explicitly activated |

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

Do not run `bet.tasks.run_betting_cycle` as a check. The historical task code remains for reference and is not repaired by FS-001.

## Betting And Selenium

`python manage.py make_bets` is unconditionally disabled and exits with an explicit `CommandError` before the historical implementation. There is no ordinary flag or environment variable to re-enable it.

Selenium is not needed for normal startup. To make its standalone service available for future non-bookmaker work:

```bash
make selenium-up
make selenium-down
```

Do not execute Selenium against Inkabet, authenticate to a bookmaker, use bookmaker credentials, or place a real bet.

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
