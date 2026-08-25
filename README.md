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

The normal stack includes PostgreSQL, Redis, Django, Celery, Celery Beat, and Nginx. It does not start Selenium. Real betting and the legacy automatic betting schedule are disabled.

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

Selenium remains available only through explicit activation:

```bash
make selenium-up
make selenium-down
```

Do not use Selenium against Inkabet or another bookmaker.

## Developer Documentation

- [Dev Container and VS Code workflow](docs/development/devcontainer.md)
- [Safe local runtime](docs/operations/local_runtime.md)
- [FS-001 feedback](docs/process/FS-001_feedback.md)

There is no supported external server, staging environment, production environment, or deployment workflow in the current product stage.
