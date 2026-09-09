# Finsport

Finsport is currently a local-only, demo-only Django application. The Docker-first runtime keeps the stable operational stack running while ticket work uses a disposable, isolated development clone.

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

Do not add bookmaker credentials. Keep the operational stack on deployed stable
images with `make up`. Create a fresh ticket development stack from a consistent
copy of the operational database with:

```bash
make dev-create
```

`make dev-create` fails if stale `finsport-dev` resources exist. It creates
isolated PostgreSQL and Redis volumes, clones only from `finsport/db`, applies
the current branch migrations, then starts Django, the worker, and Nginx. It
never starts Celery Beat and explicitly disables automatic provider work.
`make dev-up` only restarts an environment already created by that lifecycle.

Open development Admin through Nginx at <http://localhost:18001/>. Direct
development Django is at <http://localhost:18000/>.

The operational browser and direct endpoints remain at ports 8001 and 8000.
`make up` starts only previously deployed immutable images; it never builds the
current feature branch. The complete operational runtime includes Beat and
local observability:

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

At ticket end, `make dev-destroy` removes only `finsport-dev` containers,
network, and volumes. After merge and synchronization on a clean `master`,
`make deploy-local` refreshes the rolling backup, builds immutable operational
images, performs a bounded safe shutdown and migration, then validates startup.

Rolling backup commands are `make backup` and `make backup-verify`. See the
[backup and local deployment runbook](docs/operations/backup_and_deploy.md).

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
docker compose -p finsport-dev -f compose.dev.yml run --rm --no-deps django-web python manage.py sync_football_catalog

# Enable a selected Competition in Admin, then bootstrap one provider season.
docker compose -p finsport-dev -f compose.dev.yml run --rm --no-deps django-web python manage.py sync_football_season <competition-id> <year>

# Current fixtures plus per-fixture API-Football and reconciled Inkabet odds.
docker compose -p finsport-dev -f compose.dev.yml run --rm --no-deps django-web python manage.py sync_football_day --date YYYY-MM-DD --with-odds

# Evening status/result refresh without odds calls.
docker compose -p finsport-dev -f compose.dev.yml run --rm --no-deps django-web python manage.py sync_football_day --date YYYY-MM-DD
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
