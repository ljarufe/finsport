# FS-001 Feedback

## Outcome

FS-001 now has a technically complete pre-UAT local foundation. The accepted financial-safety architecture remains unchanged, the real Admin/static path is documented, obsolete remote-deployment access is removed, and Ruff plus Black form a green repository-wide quality baseline.

## Implemented Boundaries

- `.tool-versions` pins host Python 3.13.15 and no Planka tooling is tracked.
- `make_bets` remains unconditionally fail-closed before the preserved historical implementation.
- Django cache uses Redis DB 13; the safe Celery broker uses DB 14; results use DB 15; the worker consumes only `finsport.local.safe`.
- Beat has an empty configured schedule and uses an ephemeral file scheduler instead of persisted database schedules.
- PostgreSQL remains persistent, Selenium remains explicit/default-off, and the normal stack retains Django, Redis, Celery, Beat, and Nginx.
- The Dev Container retains its safe service allowlist and non-root application workflow.
- The personal `~/.ssh` mount, runtime `openssh-client`, `fabfile.py`, Fabric dependency, and unused Scrapyd deploy block were removed. No replacement deployment surface was introduced.
- Ruff 0.16.2 and Black 25.1.0 are pinned and configured. Migrations are excluded from lint/format.
- `make check` is non-mutating and runs Black check, Ruff, Django system check, and pytest. Coverage remains informational.
- Host Git owns pre-commit/pre-push installation and execution; the Dev Container owns editor, test, debug, and direct application commands.

## Admin And Static Architecture

Maintainer browser evidence showed that port 8000 redirects from `/` to the Admin login and appears unstyled. Inspection confirmed that Admin is mounted at root `/`, not `/admin/`.

Automated runtime evidence established the intended split:

- `http://localhost:8000/`: direct Gunicorn/Django technical endpoint; HTTP 302 to `/login/?next=/`; not responsible for collected static files.
- `http://localhost:8001/`: supported normal browser/Admin endpoint through Nginx; HTTP 302 to `/login/?next=/`.
- `http://localhost:8001/static/admin/css/base.css`: HTTP 200 with `text/css`.
- `/app/staticfiles/admin/css/base.css`: present in the shared volume, owned by the non-root application UID, after collectstatic copied 424 files.

No second static-serving dependency was added.

## Safe Brownfield Quality Cleanup

The initial read-only Ruff run reported 29 findings: 27 safe import/unused fixes, one ambiguous local variable, and one undefined legacy return name. Black initially identified eight source files.

Applied changes were limited to:

- import sorting;
- removal of clearly unused placeholder imports;
- Black-only formatting;
- renaming the local variable `l` to `league`;
- EOF normalization in two templates and `nginx.conf`.

The undefined `stages` return in `football/tasks.py` was not repaired because choosing a value would change legacy behavior. It has a line-specific Ruff exclusion and is recorded below. A migration briefly selected by an explicit pre-commit file list was restored unchanged, and the Black hook now excludes migrations.

## Automated Validation

- `make build`: PASS after SSH/Fabric removal.
- Image probe: PASS; neither the `ssh` executable nor the Fabric module is present.
- `docker compose config` and merged Dev Container Compose: PASS.
- `make format`: PASS and stable; 59 Python files unchanged on the final pass.
- `make format-check`: PASS.
- `make lint`: PASS.
- `make check`: PASS; Black, Ruff, Django system check, and 2 focused tests passed.
- `make coverage`: PASS; 2 tests passed, 37.9% informational brownfield coverage, no fail-under.
- Host `make hooks`: PASS using the host pipx pre-commit installation and the project `python3` shim resolving Python 3.13.15.
- `pre-commit run --all-files`: PASS on the final run.
- Hooks against the new untracked FS-001 files: PASS, including YAML, JSON, and TOML validation.
- Explicit pre-push `make-check` hook: PASS without pushing.
- Normal stack startup: PASS; running services exclude Selenium.
- Worker logs: PASS; Redis DB 14, result DB 15, and queue `finsport.local.safe`.
- Beat logs: PASS; ephemeral scheduler at `/tmp/finsport-celerybeat-schedule`, no legacy task dispatch observed.
- Admin/static HTTP and volume evidence: PASS as described above.
- Focused current-tree secret review: PASS; no tracked sensitive paths or high-confidence credential/private-key signatures found.
- `git diff --check`: repeated at final self-review.

## Manual UAT Still Pending

The maintainer must still:

1. Open `http://localhost:8001/` and confirm the styled Django Admin login page.
2. Reopen the repository in the Dev Container and confirm Python/Pylance, Test Explorer, individual test debugging, and the Django debug profile on port 8002.
3. Confirm from the normal workflow that Selenium is not running.

No betting UAT is permitted.

## Warnings And Deferred Validation

- The GitHub PR workflow is structurally validated and uses the same local `make check` contract, but it has not run on GitHub because no PR was opened.
- Selenium's explicit profile was configuration-validated but not started; bookmaker Selenium must not be used.
- Historical betting, scraper behavior, and external sites were deliberately not exercised.
- The previous `static_volume` ownership and Django Redis cache-option blockers remain fixed and were revalidated.

## New Work Discovered

### Legacy football model/migration drift

- Evidence: `python manage.py makemigrations --check --dry-run` reports pending football model options, indexes, and a uniqueness constraint.
- Impact: migration drift cannot join the stable gate until the brownfield schema is deliberately reconciled.
- Recommendation: address model/migration reconciliation in a separate scoped ticket.

### Undefined legacy return in `football.tasks.get_livescore_matches`

- Evidence: Ruff reports `return stages`, but only the loop variable `stage` exists and the loop itself may not execute.
- Impact: explicit execution can raise `NameError` after performing external/API and database work.
- Recommendation: define the intended task return contract in a separate functional ticket before changing it.

### Explicit historical betting entry points remain

- Evidence: `bet.tasks.run_betting_cycle` and `execute_commands` remain outside the automatic runtime path.
- Impact: a developer could still explicitly invoke unsafe legacy workflows; `make_bets` itself remains fail-closed, but earlier chain steps include bookmaker behavior.
- Recommendation: decide which legacy betting components the new product will reuse, then remove or hard-disable unused explicit entry points in a separate safety ticket.

## Future Improvements

- Refine coverage policy after the new core has meaningful tests.
- Expand CI, Dev Container, VS Code tasks, and Makefile targets only when real workflows justify them.
- Refactor or remove legacy components only after deciding what the new product reuses.
- Add tests around components that become part of the new core.
- Consider browser/Admin automation after stable interactive behavior exists.
