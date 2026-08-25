# Repository Instructions For Codex

These instructions apply to the whole repository.

## Working Rules

- Finsport is local-only and demo-only. There is no remote deployment or SSH/server workflow; do not reintroduce one unless a future explicit product decision authorizes it.
- The supported runtime is Docker-first. Use the Dev Container as the preferred Python editor, test, and debug environment.
- Use the Makefile as the stable developer interface and `make check` as the general repository gate.
- Ruff and Black are the repository lint and formatting baseline. Keep `make check` non-mutating and green.
- Inspect the active branch, worktree, relevant files, and current repository instructions before editing.
- Implement only the current ticket. Historical code is evidence of past behavior, not automatically current product intent.
- Do not commit, push, open or merge pull requests, or perform Planka actions unless the maintainer explicitly authorizes them.
- Do not commit secrets, credentials, tokens, private keys, environment files, dumps, or production values.
- Do not run destructive Git, database, or Docker volume commands. Never use `docker compose down -v`, delete `postgres_data`, load `finsport.sql`, or purge unknown persistent Redis state.
- Keep repository-writing commands non-root where possible and verify ownership when a container command generates files in the bind-mounted checkout.

## Financial Safety

Never:

- run `bet.tasks.run_betting_cycle`;
- authenticate to Inkabet or another bookmaker;
- place a real bet;
- execute the historical betting Selenium path;
- use bookmaker credentials;
- purge persistent Redis merely to make a worker or test pass;
- delete or recreate the persistent PostgreSQL data volume.

The `make_bets` command must remain unconditionally fail-closed while Finsport is demo-only. The normal worker must remain isolated from legacy Redis broker state, and the normal Beat service must not load persisted database schedules.

## Validation And Handoff

- Use focused checks while editing, then run `make check` before technical close.
- Validation is delta-based. Do not make the gate red with unrelated legacy lint or migration drift solely to expand the gate.
- Record discovered work with `evidence`, `impact`, and `recommendation`; do not automatically absorb it into the current ticket.
- Do not invent UAT results. Final ticket feedback must distinguish automated evidence, manual UAT, warnings or deferred validation, and future work.
- For implementation tickets, update `docs/process/<TICKET-ID>_feedback.md` and generate the requested untracked review artifacts under `tmp/` after all implementation and validation changes are complete.
