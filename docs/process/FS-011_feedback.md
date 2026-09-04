# FS-011 Feedback

## IMPLEMENTATION SNAPSHOT — MAY BECOME STALE

Pass 2 of 4 consolidated pre-UAT correction feedback. This snapshot is not final operational acceptance.

### Outcome

FS-011 now has a corrected implementation candidate for fail-closed historical identity, model/config-scoped Dixon-Coles readiness, current-evidence runtime classification, pipeline failure ownership, complete focused provider organization, and bounded read-only reporting.

The implementation deliberately did not apply migration `0010` to the maintainer's persistent database, call live providers, perform the real historical backfill, start UAT, or alter the persistent final enabled-competition set.

### Pass 2 correction findings

- Finding 1: Unknown historical team identities no longer create canonical `Team` rows. Existing resolved source refs, configured aliases whose canonical target already exists, and exact canonical identity are the only automatic paths. Operators can create the legitimate historical-only `Team` and/or an explicit `TeamSourceRef`, then retry deterministically. Unknown aliases remain unresolved/PARTIAL with stable diagnostics.
- Finding 2: `DixonColesReadinessProfile` approval is now scoped to `DIXON_COLES` model version plus normalized model/time-weight configuration. Matching profile/config participates in evidence identity. Config mismatch preserves valid Prediction evidence but forces `bet_eligible=false` and readiness `NO_BET`.
- Finding 3: Runtime classification now uses whether current evidence passes the matching readiness profile, not profile existence. Below-profile known instability is UNAVAILABLE; unexpected post-readiness runtime or invalid probability output is FAILED. Backtests persist separate `failed_counts` and `unavailable_counts`.
- Finding 4: Prediction-phase reporting consumes persisted classified DC outcomes. DC-only FAILED cannot report SUCCESS, mixed successful evidence plus failure is DEGRADED, expected UNAVAILABLE remains non-error/low-noise, and bounded failed counts/reasons are exposed.

### Maintainer addendum

- AD1 PASS: The final focused provider home is `football/providers/`, containing `api_football.py`, `api_inkabet.py`, `catalog.py`, `football_data.py`, `inkabet.py`, and `inkabet_capture.py` plus `__init__.py`. All repository imports/tests were updated and the obsolete root provider modules were removed. API-Football behavior and Inkabet fail-soft/quota/safety/observability regressions pass without live calls. No registry, provider abstraction framework, or Django app was introduced.
- AD2 PASS: Existing `/` and `/daily/` server-rendered reporting now surface persisted FS-011 semantics. Historical reporting shows enabled state, coverage/season/source/strategy/reason, no-auto-retry, readiness profile approval and fail-closed state. Daily reporting distinguishes persisted DC PRODUCED, UNAVAILABLE, and FAILED; produced rows show eligibility/readiness and bounded evidence identity, and below-readiness Prediction remains visibly distinct from its `NO_BET` Decision. Tests prove zero provider calls, task dispatches, domain writes, or financial writes.

Admin remains the detailed technical audit surface. No route, SPA, React, Node/npm, API/DRF, application JavaScript, or cross-model frontend redesign was added.

### Integration evidence

An offline regression now runs through the actual historical bootstrap/reconciliation service with a frozen source adapter. It inserts relevant canonical FT football evidence, changes the Dixon-Coles evidence identity, permits a new prospective evidence version, and preserves the prior Prediction. The existing price-only regression still proves odds changes do not alter the DC identity.

### Automated validation

- Focused correction matrix: 310 passed (`tmp/FS-011_focused_tests.txt`).
- Full `make check`: 348 passed; 85.95% coverage (`tmp/FS-011_make_check.txt`).
- Black, Ruff, Django system check, migration drift, pip dependency check, and pip-audit passed.
- Separate migration drift: `No changes detected`.
- `git diff --check`: clean.
- Provider network edges were frozen/injected; real local penaltyblog Dixon-Coles mathematics was exercised.

### Migration 0010

The existing uncommitted migration `football/migrations/0010_prediction_bet_eligible_prediction_evidence_identity_and_more.py` was updated in place. `DixonColesReadinessProfile` now includes explicit `model_version` and `model_config` fields; no unnecessary `0011` was created. The migration was not applied to the persistent database.

### Pass 3 exceptional scoped pre-UAT amendment

Pass 3 corrected only the three material boundaries identified by the maintainer's completed Pass 2 review:

- P3-1: Dixon-Coles retains one reusable shared league fit, but unseen-team checks, readiness assessment, and FAILED versus UNAVAILABLE classification are now target-specific. A low-readiness target cannot suppress or reclassify a mature sibling target.
- P3-2: Prospective summaries persist a compact per-target Dixon-Coles status/reason map while retaining the aggregate state for pipeline reporting. `/daily/` consumes or deterministically derives each Match's own state, so sibling failure/unavailability reasons cannot leak across targets; reporting remains read-only.
- P3-3: One canonical DB-only helper now requires stored COMPLETE coverage to match the current completed-Season set, covered set, empty unresolved set, and current strategy version. Activation, explicit bootstrap, and DC candidate scheduling use this currentness contract. Current Seasons stay excluded and stale coverage requires explicit bootstrap/retry; no automatic acquisition was added.

Pass 3 focused validation: 71 passed. Final `make check`: 352 passed with 85.83% coverage; Black, Ruff, Django, dependency, security, and migration checks passed. Separate migration drift reported `No changes detected`, and `git diff --check` was clean. Migration `0010` did not change in Pass 3 and was not applied. Live provider calls and persistent side effects remained zero. The real-UAT work and criteria `A06`, `A07`, `A09`, `A10`, and `A17` remain pending.

### Pass 4 final real-UAT correction amendment

Real UAT exposed three ingestion defects: football-data naive times were being interpreted as America/Lima, secondary matches required identical kickoffs, and direct CSV season labels could assign rows to overlapping canonical seasons. The final normal code pass corrected only those boundaries and the associated observed source-data cases.

- Both penaltyblog and direct football-data CSV ingestion now share an explicit `Europe/London` source-time contract. Naive values use UK civil time, already-aware values are not reinterpreted, missing times remain DATE_ONLY, and bounded provenance retains the raw date/time, source-time contract, normalized kickoff, source season and adapter/URL context.
- EXACT secondary reconciliation now considers same-season/same-team candidates within two hours. A unique +60-minute same-result candidate resolves to the existing API-F Match while retaining its canonical fields and recording the source kickoff/delta; conflicts and multiple candidates remain pending/fail-closed, and no candidate may create a correctly normalized historical Match.
- Existing-Team matching gained deterministic Unicode/diacritic/case/whitespace/punctuation normalization and the evidenced Celta/Espanol aliases. It remains non-fuzzy and never auto-creates unknown Teams; normalized collisions fail closed and repeated unknown identities are summarized with bounded, deduplicated counts/seasons.
- Direct rows are partitioned by parsed Date against coherent, non-overlapping canonical Season intervals. Non-final rows with both scores absent are skipped and counted; partial scores or final-result claims without valid scores fail parsing. Missing required source seasons remain unresolved, so frozen Brazil 2010/2011 stays incomplete/disabled while fully covered frozen MLS data can pass the data-driven gate.

Pass 4 focused validation: 66 passed. The single final `make check` passed 372 tests with 86.10% coverage; Black, Ruff, Django, dependency, security, and migration checks passed. Separate migration drift reported `No changes detected`, and `git diff --check` was clean. Migration `0010` did not change in Pass 4 and was not applied. Live provider calls and persistent side effects remained zero. Criteria `A06`, `A07`, `A09`, `A10`, and `A17` remain pending until the maintainer repeats the authorized real UAT.

### Pass 5 exceptional final UAT correction amendment

Real Argentina UAT exposed a uniqueness collision when `Colon Santa FE` and `Colon Santa Fe` arrived with different football-data external IDs. Both names normalize to the same deterministic identity, but the exact-ID miss previously proceeded directly to canonical-Team matching and attempted a second `TeamSourceRef`, violating the existing unique `(source, team)` constraint.

Historical team reconciliation now preserves exact source-ID precedence, then inspects same-source/same-competition refs using the existing deterministic name normalizer. One valid resolved canonical Team is reused without creating another ref; divergent Teams or any unresolved/invalid matching ref fail closed as `AMBIGUOUS_TEAM_MAPPING`. With no normalized source-ref match, the existing canonical-Team path continues unchanged. Explicit alias keys now use the same deterministic normalization, so capitalization-only variants cannot bypass an approved alias. Canonical display names, external-ID generation, database schema/constraints, and genuine-unknown behavior remain unchanged; no fuzzy matching was added.

Pass 5 focused validation: 47 passed. The single final `make check` passed 379 tests with 86.13% coverage; Black, Ruff, Django, dependency, security, and migration checks passed. Separate migration drift reported `No changes detected`, and `git diff --check` was clean. Migration `0010` did not change in Pass 5 and was not applied. Live provider calls and persistent side effects remained zero. No new technical finding remains; criteria `A06`, `A07`, `A09`, `A10`, and `A17` still require the maintainer's authorized real UAT.

### Pending manual/real UAT

- Apply migration `0010` to the persistent local DB under maintainer authorization.
- Run `--reconcile-enabled` against the persistent DB.
- Run approved live football-data backfills for the required pool.
- Verify the exact final ten enabled competitions are all historical `COMPLETE` and all others are disabled.
- Verify current-season operation on an enabled COMPLETE competition.
- Execute UAT A–I and retain real DB/provider evidence.

Acceptance criteria `A06`, `A07`, `A09`, `A10`, and `A17` therefore remain PENDING. `AD1` and `AD2` pass with code and automated evidence. See `tmp/FS-011_acceptance_ledger.md`.

### Safety record

- Persistent migrations applied: 0.
- Live API-Football calls: 0.
- Live football-data calls: 0.
- Live Inkabet calls: 0.
- Bookmaker authentication/writes: 0.
- Betting/financial side effects: 0.
- Commits, staging, pushes, PRs and Planka actions: 0.
- Persistent PostgreSQL/Redis data was not purged or recreated.

### Research artifact

`docs/research/Finsport_historical_ingestion_dixon_coles_research_2026-09-03.md` remained byte-for-byte unchanged. Observed SHA-256: `c936a46147e87c7309f7226e0a62c4827a6f808a58cc17182e86ace5a9863b55`.

### New Work Discovered

Evidence → The Pass 1 full-suite run crossed a UTC quota-epoch boundary and briefly exposed three existing time-sensitive capture tests; both the affected regressions and subsequent full gates passed.

Impact → The tests are boundary-brittle around UTC rollover. This did not identify an FS-011 product defect and the repository gate is green.

Recommendation → In a separate maintenance ticket, freeze the quota clock or choose an epoch-relative test instant.

### Blockers / contradictions

No material ticket/research/addendum contradiction or implementation blocker remains. The only outstanding work is the intentionally deferred, authorization-dependent real UAT above.
