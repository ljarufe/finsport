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

Do not add bookmaker credentials. Build and start the normal safe stack:

```bash
make build
make up
```

Open the normal browser/Admin endpoint at <http://localhost:8001/>. Nginx proxies Django and serves collected static files there.

The direct Gunicorn/Django endpoint at <http://localhost:8000/> is intended for technical probing. It reaches the same root-mounted Admin but does not serve collected static files.

The normal stack includes PostgreSQL, Redis, Django, Celery, Celery Beat, and Nginx. There is no bookmaker automation or legacy automatic betting schedule.

Stop services without deleting persistent data:

```bash
make down
```

## Development Commands

```bash
make test
make coverage
make lint
make format
make format-check
make django-check
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

Every command reports created, updated, unchanged/skipped, reconciliation-pending counters, provider calls, and the latest known API-Football daily quota. The API client uses the full known budget by default (`API_FOOTBALL_DAILY_RESERVE=0`), stops before a known overrun, bounds retries/pagination, and paces sequential calls. Inkabet uses one categories discovery request plus strict MW3W requests only for resolved relevant Matches. Catalogue/season transition and intraday odds scheduling remain manual.

## Developer Documentation

- [Dev Container and VS Code workflow](docs/development/devcontainer.md)
- [Safe local runtime](docs/operations/local_runtime.md)
- [Local observability and incident triage](docs/operations/observability_incident_triage.md)
- [FS-001 feedback](docs/process/FS-001_feedback.md)
- [FS-002 feedback](docs/process/FS-002_feedback.md)

There is no supported external server, staging environment, production environment, or deployment workflow in the current product stage.
