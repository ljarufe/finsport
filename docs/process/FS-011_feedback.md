# FS-011 Feedback

## Final outcome

FS-011 is complete.

The ticket delivers auditable multi-source historical ingestion for the final enabled competition pool, source-aware reconciliation and historical readiness, a complete Dixon-Coles operational/readiness contract, reporting of Dixon-Coles terminal states, and the initial approved readiness configuration required for end-to-end simulation.

The final implementation includes all UAT-driven corrections and all material PR review findings. Historical acquisition is not part of the recurring daily provider path, existing API-Football canonical evidence remains authoritative, and Dixon-Coles remains fail-closed for structurally insufficient targets.

## Final enabled competition pool

Exactly these 10 first divisions are enabled for the FS-011 operating pool:

- FR — Ligue 1 (`1270`)
- BR — Serie A (`1272`)
- EN — Premier League (`1273`)
- DE — Bundesliga (`1274`)
- IT — Serie A (`1275`)
- NL — Eredivisie (`1276`)
- PT — Primeira Liga (`1277`)
- ES — La Liga (`1278`)
- TR — Süper Lig (`1325`)
- AR — Liga Profesional Argentina (`1459`)

Peru Liga 1 (`1524`) and MLS (`1432`) are outside the final enabled pool.

All 10 final competitions were verified with historical coverage `COMPLETE`, current strategy/basis, no unresolved required seasons, and no unresolved ambiguity/conflict in their effective required source-supported windows.

## Historical ingestion and reconciliation

FS-011 adds an explicit `HistoricalCoverage` lifecycle and manual historical bootstrap/retry path.

Approved source behavior:

- Europe: football-data.co.uk through penaltyblog.
- Argentina and Brazil: direct football-data.co.uk CSV ingestion.
- API-Football remains the primary current/canonical source.
- Historical API-Football entitlement is not used as the default bulk-history mechanism.
- Inkabet behavior is unchanged by historical bootstrap.

Historical acquisition remains manual and idempotent. It is not added to normal daily scheduling and completed historical seasons are not repeatedly downloaded after readiness is established.

Reconciliation is deterministic and fail-closed:

- exact source references take precedence;
- deterministic Unicode/diacritic/case/whitespace/punctuation normalization is allowed;
- explicit aliases are supported;
- fuzzy matching is not used;
- unknown identities do not silently create canonical Teams;
- ambiguous identities remain unresolved;
- existing API-Football canonical results are not silently overwritten by secondary historical evidence;
- source provenance and reconciliation diagnostics are persisted.

Historical reimports validate both result evidence and kickoff evidence before being counted as unchanged. `EXACT` source timestamps must remain within the approved reconciliation tolerance; a corrected exact kickoff outside that tolerance becomes a source-reimport conflict rather than silently preserving an incompatible canonical timestamp.

## Source-supported historical window

The effective required historical window is:

`canonical completed Seasons ∩ actual approved source availability`

A contiguous leading prefix of canonical seasons for which the approved source exposes no rows is audited as `SOURCE_OUTSIDE_AVAILABLE_HISTORY_WINDOW` and is not a readiness blocker.

This exemption applies only to the leading unavailable source prefix. Missing seasons inside the effective supported interval remain a hard stop.

Brazil therefore closes on the supported 2012–2025 interval while 2010–2011 remain explicitly audited outside source availability. Internal gaps continue to produce PARTIAL coverage.

This is the final interpretation of acceptance criterion A08: COMPLETE requires every season in the effective source-supported required window to be covered without unresolved ambiguity/conflict.

## Real historical UAT

Authorized real backfills were completed for all 10 final competitions.

Verified real/idempotent examples include:

- La Liga: COMPLETE/current, 2010–2025, 6080 historical rows.
- Premier League: COMPLETE/current, 6080 rows; repeated import created 0 and left 6080 unchanged.
- Bundesliga: COMPLETE/current, 4896 historical rows; repeated import created 0 and left 4896 unchanged.
- Serie A Italy: COMPLETE/current, 6080 rows.
- Ligue 1: COMPLETE/current, 5757 rows.
- Eredivisie: COMPLETE/current, 4822 rows.
- Primeira Liga: COMPLETE/current, 4632 rows.
- Süper Lig: COMPLETE/current, 2011–2025, 4924 rows; repeated import created 0 and left 4924 unchanged.
- Liga Profesional Argentina: COMPLETE/current, 2015–2025, 4359 rows; historical team identities were explicitly reconciled and repeated import created 0 and left 4359 unchanged.
- Serie A Brazil: COMPLETE/current over the effective 2012–2025 source-supported window, 5307 rows; 2010–2011 remain audited outside source availability; repeated import created 0 and left 5307 unchanged.

The final DB inventory verified exactly 10 enabled competitions and all 10 historical readiness states as COMPLETE/current.

## Dixon-Coles operational contract

Dixon-Coles is football-evidence driven and does not depend on odds to fit or generate probabilities.

FS-011 separates:

- structural fit/readiness;
- valid probability production;
- betting eligibility;
- Decision policy eligibility.

Expected structural insufficiency is `UNAVAILABLE`. Unexpected runtime failure after approved readiness is `FAILED`. Valid probability output can be persisted even when betting eligibility is denied.

Dixon-Coles evidence identity depends on relevant football evidence, model version/configuration and readiness identity. Price-only changes do not create a new Dixon-Coles evidence version. New relevant FT football evidence does.

Prior Predictions are preserved when a new football-evidence version is created.

For batches that do not request Dixon-Coles, FS-011 does not persist a synthetic Dixon-Coles status block. A non-DC experiment therefore cannot create a spurious `DIXON_COLES_NOT_PRODUCED` state in `/daily/`.

## Historical data use

The imported historical pool is active model evidence, not archival-only data.

Prospective Dixon-Coles fits consume eligible same-competition FT history strictly before the target cutoff. The approved model configuration currently has `max_history=None`, so the runtime is not restricted to the 2025 season used for outer evaluation.

Independent Poisson and Elo also receive the eligible historical match pool under their respective model contracts. Market Consensus remains market/odds-driven.

The 2025 evaluation was used as a chronological outer holdout for model/configuration selection and readiness approval; it was not a restriction on the history available to prospective model fitting.

## Dixon-Coles readiness profiles

A chronological 2025 outer backtest was run for each of the 10 final competitions.

All 10 runs produced Dixon-Coles predictions with valid normalized probability output and no invalid-probability findings.

Selected initial configurations:

- Ligue 1: `xi=0.002`
- Serie A Brazil: `xi=0.002`
- Premier League: `xi=0.002`
- Bundesliga: `xi=0.002`
- Serie A Italy: `xi=0.0`
- Eredivisie: `xi=0.002`
- Primeira Liga: `xi=0.0`
- La Liga: `xi=0.002`
- Süper Lig: `xi=0.002`
- Liga Profesional Argentina: `xi=0.002`

Ten `DixonColesReadinessProfile` rows were created and verified:

- `approved=True`
- `active=True`
- profile version `fs011-initial-2025-v1`
- model version `fs011-dixon-coles-v2`
- exact runtime-compatible model config
- `require_connected=True`
- runtime assessment `APPROVED_READINESS_PROFILE_PASSED`

No arbitrary universal minimum-match threshold was introduced. Existing target-specific structural checks continue to reject unseen or otherwise insufficient teams.

These profiles are the initial simulation approval. They must be revalidated after each completed league season and whenever the Dixon-Coles model version or selected configuration changes.

## Dixon-Coles real UAT

Real mature target:

- Bundesliga match `1567`, VfB Stuttgart vs 1. FC Köln.
- Dixon-Coles produced normalized probabilities from approximately 4900 eligible historical matches.
- The original UAT Prediction correctly remained below readiness because it was created before profiles were approved.

Real insufficient-history target:

- Argentina match `1573`, Estudiantes de Rio Cuarto vs Sarmiento Junin.
- Dixon-Coles classified the target as `UNAVAILABLE / INSUFFICIENT_TEAM_HISTORY`.
- No false Prediction or Decision was created.

Versioning UAT:

- a price-only delta preserved the Dixon-Coles evidence identity;
- one additional eligible FT football result changed the evidence identity;
- the changed football basis created a new prospective Dixon-Coles Prediction version;
- the prior Prediction remained unchanged;
- all synthetic UAT data was rolled back;
- persistent DB state was unchanged after rollback.

The measured full Bundesliga Dixon-Coles refit took approximately 169 seconds. This is a performance follow-up, not a functional correctness blocker.

## Current-season acquisition UAT

Authorized `sync_football_day --date 2026-09-04 --with-odds` completed successfully for API-Football:

- command result: success;
- 13 API-Football calls;
- 86 records created;
- 12 updated;
- 110 unchanged;
- no pending competition/team/match mappings;
- reported API-Football daily remaining quota: 87.

Inkabet made one secondary call and timed out. The sync remained fail-soft/degraded and API-Football acquisition completed successfully.

The later normal pipeline execution found no new prospective prediction work because the day's relevant fixtures had already started or finished. This was a timing limitation of the live smoke attempt, not a model or historical-readiness failure.

A separate future-match smoke test should exercise API-Football → normal pipeline → approved/eligible Dixon-Coles Prediction → Decisions → `/daily/` before kickoff. It is operational follow-up evidence, not unfinished FS-011 implementation.

## Reporting

Existing server-rendered reporting remains the product surface.

Historical reporting exposes enabled/coverage/source/strategy/reason/readiness state.

Daily reporting distinguishes per-target Dixon-Coles:

- `PRODUCED`
- `UNAVAILABLE`
- `FAILED`

Produced rows expose betting eligibility/readiness and bounded evidence identity. Per-target state prevents one sibling target from leaking its failure/unavailability reason into another.

Experiments that did not request Dixon-Coles do not contribute a Dixon-Coles status to daily reporting.

The attempted shell-level `/daily/` smoke using Django `Client()` returned `400` because the harness used `HTTP_HOST=testserver`, which is not allowed by the project settings. This was a harness issue and is not recorded as a frontend defect.

## Final PR review corrections

The final PR correction resolves all material review findings:

1. **Non-requested Dixon-Coles status**
   - Dixon-Coles summary/status is now persisted only when Dixon-Coles was actually requested for that experiment.
   - Regression coverage proves non-DC batches do not invent Dixon-Coles terminal state.

2. **Kickoff-aware historical reimport**
   - unchanged historical reimports must satisfy the same approved kickoff precision/tolerance contract used during initial reconciliation.
   - an exact kickoff correction outside tolerance is classified as `SOURCE_REIMPORT_CONFLICT`.
   - canonical API-Football evidence remains unchanged.

3. **UTC quota-test rollover**
   - three capture tests that depended on wall-clock `timezone.now()` are pinned to a deterministic midday UTC instant.
   - production quota epoch logic is unchanged.
   - this removes the previously observed midnight-UTC CI flake.

4. **Final feedback reconciliation**
   - this document replaces the stale pre-UAT snapshots and records the actual automated evidence, real/manual UAT, warnings and future work.

## Final automated validation

The final corrected tree passed the repository validation required for technical close:

- focused PR-correction tests: PASS;
- `make check`: PASS;
- Black: PASS;
- Ruff: PASS;
- Django system check: PASS;
- migration drift: no changes detected;
- dependency check: PASS;
- pip-audit: PASS;
- coverage gate: PASS;
- `git diff --check`: clean.

The PR correction delta required no additional live provider calls or historical backfills.

## Acceptance closure

The previously pending real-UAT criteria are closed:

- A06 PASS — pre-existing enabled competitions were audited/backfilled.
- A07 PASS — exactly 10 final competitions are enabled and historical COMPLETE/current.
- A09 PASS — European historical bootstrap used football-data.co.uk/penaltyblog rather than live API-Football bulk history.
- A10 PASS — direct football-data CSV ingestion for Argentina/Brazil is source-aware, reproducible and idempotent.
- A17 PASS — current-season API-Football acquisition remained operational after historical readiness activation.

A08 uses the final effective source-supported historical-window interpretation documented above.

No material FS-011 implementation blocker remains.

## Safety record

- Real-money betting remains prohibited/fail-closed.
- No bookmaker write/authentication behavior was added.
- Historical bootstrap does not run recurrently.
- API-Football canonical rows are not destructively rewritten by secondary history.
- PR correction validation requires no live-provider quota.
- Persistent UAT migrations/backfills were operator-authorized.
- Synthetic versioning UAT changes were transactionally rolled back.

## New work discovered / future maintenance

### Dixon-Coles fit performance

Evidence: a real Bundesliga fit over approximately 4900 historical matches took about 169 seconds.

Impact: correctness is unaffected, but repeated full refits across the final 10-league pool may be operationally expensive.

Recommendation: evaluate bounded history, cached fits keyed by football evidence identity, incremental fitting, or another evidence-backed performance strategy in a dedicated ticket.

### Readiness revalidation

Evidence: initial profiles are based on the completed historical pool and chronological 2025 evaluation.

Impact: a completed new season or a model/configuration change can change the evidence supporting approval.

Recommendation: re-run model/config evaluation and version the active readiness profile after each completed league season and whenever Dixon-Coles model/config semantics change.

### Prospective live smoke

Evidence: the 2026-09-04 live attempt occurred after the relevant fixtures had started/finished.

Impact: individual components are validated, but a same-run pre-kickoff API-Football → pipeline → eligible Prediction → Decisions → `/daily/` smoke was not captured.

Recommendation: repeat this as an operational smoke test on the next suitable future fixture without reopening FS-011.

### Inkabet timeout

Evidence: one Inkabet request timed out during the authorized current-day sync while API-Football completed successfully.

Impact: secondary-source enrichment degraded for that call only.

Recommendation: observe recurrence separately; do not conflate it with historical readiness or Dixon-Coles correctness.

## Research artifact

`docs/research/Finsport_historical_ingestion_dixon_coles_research_2026-09-03.md` remains the reference research artifact. Runtime and UAT decisions above supersede any earlier implementation snapshot that described real UAT as still pending.
