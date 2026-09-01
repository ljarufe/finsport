# Finsport

Finsport is currently a local-only, demo-only Django application. The supported developer workflow is Docker-first and preserves the existing PostgreSQL data volume.

## Quick Start

Prerequisites:

- Docker with Docker Compose;
- GNU Make;
- pre-commit on the host (`pipx install pre-commit==4.6.2` is recommended);
- VS Code and Dev Containers for the recommended editor workflow.

Create local configuration once:

```bash
cp .env.dist .env
```

Do not add bookmaker credentials. Build and start the development/UAT-safe stack:

```bash
make build
make dev-up
```

`make dev-up` starts PostgreSQL, Redis, Django, the manual Celery worker, and
Nginx, but never Celery Beat. It is safe even when the ignored operational
`.env` contains `FOOTBALL_PIPELINE_ENABLED=True`.

Open the normal browser/Admin endpoint at <http://localhost:8001/>. Nginx proxies Django and serves collected static files there.

The direct Gunicorn/Django endpoint at <http://localhost:8000/> is intended for technical probing. It reaches the same root-mounted Admin but does not serve collected static files.

Start the complete operational runtime, including Beat and local observability,
only when automatic provider work is intended:

```bash
make up
make status
```

Grafana is available at <http://localhost:3000/>. Beat owns the automatic
pipeline when `FOOTBALL_PIPELINE_ENABLED=True`. Due odds windows also trigger
secondary read-only Inkabet MW3W acquisition; Inkabet extended statistics are
not implemented. `make operational-up` remains an alias for `make up`.

Gracefully stop new dispatch, verify bounded worker/queue/database quiescence,
and then stop services without deleting persistent data:

```bash
make safe-down
```

`make down` delegates to the same fail-closed path. Neither command removes
named volumes.

## Development Commands

```bash
make test
make coverage
make lint
make format
make format-check
make django-check
make migration-check
make check
make shell
make migrate
make createsuperuser
```

Install the repository hooks from the host checkout with `make hooks`. Host Git and the host Python 3.13.15 selected by `.tool-versions` own hook installation and execution; application, test, and debug commands remain Docker-first.

## API-Football Data

Create an API-Sports account, obtain an API-Football key from its dashboard, and store it only in the local ignored `.env` file:

```bash
API_FOOTBALL_KEY=your-local-key
INKABET_BRAND_ID=your-local-value
INKABET_MARKET_CODE=your-local-value
```

The read-only manual workflow is:

```bash
# Occasional catalogue refresh. New competitions remain disabled.
docker compose run --rm django-web python manage.py sync_football_catalog

# Enable a selected Competition in Admin, then bootstrap one provider season.
docker compose run --rm django-web python manage.py sync_football_season <competition-id> <year>

# Current fixtures plus per-fixture API-Football and reconciled Inkabet odds.
docker compose run --rm django-web python manage.py sync_football_day --date YYYY-MM-DD --with-odds

# Evening status/result refresh without odds calls.
docker compose run --rm django-web python manage.py sync_football_day --date YYYY-MM-DD
```

Every command reports created, updated, unchanged/skipped,
reconciliation-pending counters, provider calls, and the latest known
API-Football daily quota. The automatic pipeline owns quota-aware API-Football
fixture discovery, result refresh, intended-window API-Football/Inkabet odds,
daily catalogue/season maintenance, and weekly chronological evaluation.
Manual commands remain available for bounded diagnostics and overrides. The
shipped free-plan discovery horizon is today plus tomorrow
(`FOOTBALL_CAPTURE_DISCOVERY_DAYS_AHEAD=1`).

## Developer Documentation

- [Dev Container and VS Code workflow](docs/development/devcontainer.md)
- [Safe local runtime](docs/operations/local_runtime.md)
- [Capability execution matrix](docs/operations/capability_matrix.md)
- [Local observability and incident triage](docs/operations/observability_incident_triage.md)
- [FS-008 PRE-UAT feedback](docs/process/FS-008_feedback.md)
- [FS-001 feedback](docs/process/FS-001_feedback.md)
- [FS-002 feedback](docs/process/FS-002_feedback.md)

There is no supported external server, staging environment, production environment, or deployment workflow in the current product stage.
There is no real-betting implementation or supported bookmaker-authentication
path; both remain forbidden.
