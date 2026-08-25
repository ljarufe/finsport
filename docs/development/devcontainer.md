# VS Code Dev Container Workflow

Finsport is Docker-first. The recommended editor workflow attaches VS Code to the `django-web` application image at `/app`, so Python, Pylance, pytest, Black, and debugpy use the same runtime as Django.

## Prerequisites

- Docker and Docker Compose running on the host.
- VS Code.
- The VS Code Dev Containers extension.

## Open The Repository

1. Open the repository folder in VS Code.
2. Run `Dev Containers: Reopen in Container` from the Command Palette.
3. Wait for VS Code to attach to `django-web`.
4. Confirm the integrated terminal opens in `/app` and `python` resolves to `/usr/local/bin/python`.

The Dev Container has an explicit service allowlist: `init-logs`, PostgreSQL, Redis, and `django-web`. Its application command is `sleep infinity`. Opening it does not start Celery, Celery Beat, Nginx, or Selenium and therefore does not consume legacy queue state or load historical Beat schedules.

VS Code connects as the non-root `appuser` and updates its UID/GID to reduce bind-mount ownership problems. The container does not require Docker-in-Docker or the host Docker socket.

## Tests And Quality

Inside the Dev Container, Makefile Python targets run directly in the current container:

```bash
make test
make coverage
make lint
make format
make format-check
make django-check
make check
```

Pytest and coverage caches are placed outside the checkout. Coverage is reported without a global fail-under threshold while the new core has only its initial focused tests.

VS Code Test Explorer discovers pytest tests using `finsport.settings`. To debug one test, select it in Test Explorer and choose `Debug Test`; the `Python: Debug tests` launch configuration supplies the Django settings module.

## Debug Django

Select `Django: Debug server` in Run and Debug. It starts:

```bash
python manage.py runserver 0.0.0.0:8002 --noreload
```

Open <http://localhost:8002/>. The separate debug port avoids the normal Django port (`8000`) and Nginx port (`8001`).

## Host Git Hooks And Extensions

VS Code recommendations cover Python, Pylance, debugpy, Black, Ruff, Django, Docker, Dev Containers, YAML, GitHub pull requests, and EditorConfig.

Git hook installation and execution belong to the host checkout, where `.tool-versions` selects Python 3.13.15. Run this from a host terminal, not the Dev Container:

```bash
pipx install pre-commit==4.6.2  # once, if pre-commit is not installed
make hooks
```

The generated hooks use the host pre-commit interpreter (a host pipx environment in the validated setup) with a command fallback. Their Python hook environments resolve the project `python3` shim to Python 3.13.15; they do not contain a container-only `/usr/local/bin/python` path.

Pre-commit performs fast staged-file hygiene, Black formatting, and safe Ruff fixes. Pre-push runs the stable Docker-first `make check` gate. The Dev Container remains the preferred editor, test, debug, and direct Python-command environment; it does not own hooks used by host Git.

If generated files appear with the wrong ownership, stop and inspect `id`, `stat`, and the Dev Container UID mapping before continuing.
