# FS-015 — Final pre-merge implementation feedback

**Ticket:** FS-015 — Historical 1X2 Market Evidence Foundation
**Branch:** `FS-015-historical-1x2-market-evidence`
**Implementation passes:** 4/4 consumed
**Repository implementation:** COMPLETE
**Development UAT:** COMPLETE / PASS
**PR review correction:** COMPLETE / PASS
**Operational promotion:** PENDING POST-MERGE

## 1. Outcome

FS-015 implements a separate, auditable, research-only historical 1X2 market domain backed by Football-Data.co.uk.

Historical market evidence cannot masquerade as prospectively observed odds. Real source prices are persisted with explicitly imputed time semantics and `SYNTHETIC_TIME_RESEARCH_ONLY` classification.

The completed implementation includes:

- completed-season historical 1X2 ingestion;
- source acquisition with explicit live versus cache-only authority;
- deterministic same-group H/D/A price selection;
- canonical Team/Match reconciliation;
- explicit historical market unavailability;
- coverage/currentness lifecycle;
- current-season finalized-match recovery;
- automatic future historical-market maintenance behind the baseline-promotion barrier;
- bounded dev-to-operational package export/import;
- package integrity, aggregate and scope validation;
- idempotence across historical ingestion, current recovery and promotion import;
- isolation from prospective `OddsObservation`;
- bounded FS-014 Nginx dynamic-DNS correction required for concurrent dev/operational lifecycle.

No Capital Runtime/Event-Time v2 behavior, bookmaker authentication, betting execution or real financial side effect was introduced.

## 2. Frozen historical market semantics

Historical market evidence uses complete same-group H/D/A prices only.

Priority remains:

1. Pinnacle closing
2. Bet365 closing
3. Average closing
4. Maximum closing
5. Pinnacle pre
6. Bet365 pre
7. Average pre
8. Maximum pre

Time semantics:

```text
closing → ASSUMED_T30M
pre/opening → ASSUMED_T6H
```

Every persisted historical price keeps:

```text
source_price_is_real=true
timestamp_is_imputed=true
evidence_class=SYNTHETIC_TIME_RESEARCH_ONLY
```

Historical evidence remains separate from prospective:

```text
OddsObservation
OddsSnapshot
```

A canonical sporting Match without a complete approved 1X2 triplet receives:

```text
SOURCE_NO_COMPLETE_1X2
```

This is market-specific unavailable evidence and does not invalidate the sporting Match or sporting historical coverage.

## 3. Coverage and malformed-row semantics

`HistoricalMarketCoverage.COMPLETE` now requires explicit source accounting in addition to canonical reconciliation.

Relevant malformed source rows may not disappear behind a `COMPLETE/current` state.

The parser retains diagnostic identity for invalid selected-season rows, including:

- CSV line;
- source row identity;
- parsed date when available;
- source home/away names;
- generated external identity when possible;
- parse failure reason.

Invalid rows are separated into two classes.

### Structural loss

A malformed row is structural when it may correspond to canonical evidence but cannot safely reach a terminal accounting state.

Examples include:

- unresolved identity;
- unresolved or conflicting Match source ref;
- canonical Match association;
- ambiguous canonical Match association.

Structural invalid rows:

```text
increment unresolved_rows
→ force coverage PARTIAL
→ prevent historical_market_is_current()
→ prevent terminal recognition
→ permit later retry after source correction
```

### Safe source artifacts

Malformed material may remain non-blocking only when it can be deterministically classified as outside the canonical sporting pool.

Examples proven by tests include:

- empty source-artifact rows;
- malformed rows whose Teams resolve but for which no canonical Match exists in the accepted bounded date window.

These rows remain audit-visible but do not fabricate Team or Match entities and do not falsely poison an otherwise complete season.

`historical_market_is_current()` and `historical_market_is_terminal()` also reject coverage whose new structural accounting reports unresolved source loss.

### Accepted-baseline compatibility

The accepted 152-season development baseline was created before the final structural-accounting diagnostics were added.

Its 24 invalid source rows were therefore inspected explicitly before accepting the PR correction:

```text
23 → empty/no-match-identity source artifacts
1  → BR 2016 Chapecoense-SC vs Atletico-MG row with invalid/missing score
```

For the BR row:

```text
teams resolve
canonical corresponding Match does not exist
→ MALFORMED_ROW_OUTSIDE_CANONICAL_POOL
```

All 24 are safe under the corrected semantics.

The already accepted development data therefore remains valid and no historical backfill or package regeneration is required.

Existing accepted coverage diagnostics are intentionally backward-compatible when the new accounting fields are absent. That compatibility is safe only because this specific accepted baseline was manually audited. Future ingestion writes the stronger structural accounting.

## 4. Completed-season UAT

Full cache-only historical UAT covered exactly:

```text
10 enabled competitions
152 authoritative completed seasons
129 required source files
```

Observed:

```text
SOURCE_ROWS                    53,641
VALID_ROWS                     53,617
INVALID_ROWS                       24
COMPLETE_TRIPLET_ROWS          53,579

HISTORICAL EVIDENCE            52,899
HISTORICAL UNAVAILABLE             38
OUTSIDE CANONICAL POOL             680

UNRESOLVED                          0
CONFLICTS                           0
EXTRA COVERAGES                     0
SILENT VALID-ROW LOSS               0
```

Every authoritative coverage ended:

```text
status=COMPLETE
current=True
terminal=True
```

Invalid source classification:

```text
INVALID_DATE                    23
decimal.ConversionSyntax         1
```

Historical idempotence rerun:

```text
152 / 152 → NO_WORK

coverage     152 → 152
evidence  52,899 → 52,899
unavailable    38 → 38
```

No historical provider call was required for idempotence.

## 5. Current-season 2026 UAT

Current-season recovery was validated independently from completed historical ingestion.

Dry-run cache-only:

```text
SOURCE_ROWS        900
VALID_ROWS         900
INVALID_ROWS         0
BLOCKERS              0
NETWORK DOWNLOADS     0
DURABLE MUTATIONS     0
```

Accepted apply:

```text
CREATE_MISSING_MATCH          819
PRESERVE_EXISTING_RESULT       81
CREATE_HISTORICAL_1X2         900
APPROVED TEAM CREATIONS         2
BLOCKERS                        0
```

The only new Teams created inside the enabled competition scope were:

```text
FR — Le Mans
AR — Gimnasia Mendoza
```

Post-apply durable state:

```text
CURRENT MATCHES                 969
CURRENT HISTORICAL EVIDENCE     900
CURRENT HISTORICAL UNAVAILABLE    0
FOOTBALL-DATA MATCH REFS        900

FS015 CREATED MATCH REFS        819
FS015 RECONCILED MATCH REFS      81
```

All 900 current rows use:

```text
selected_group=BET365_CLOSING
time_semantics=ASSUMED_T30M
```

The 150 pre-existing Matches remained unchanged.

The 759 prospective odds observations remained byte-equivalent at the audited ORM-value level.

Current-season idempotence:

```text
NO_WORK                   900
PRESERVE_EXISTING_RESULT  900
```

No durable set changed on the second apply.

## 6. Live source authority proof

Exactly two deliberate real HTTP proofs were executed.

### Europe season-file route

```text
Competition: Eredivisie
URL: https://www.football-data.co.uk/mmz4281/2627/N1.csv
downloaded=True
```

### Direct multi-season route

```text
Competition: Liga Profesional Argentina
URL: https://www.football-data.co.uk/new/ARG.csv
downloaded=True
```

Both proofs confirmed:

- live mode performs fresh HTTP acquisition;
- explicit cache-only mode is not silently reused in live mode;
- HTTP URL remains source provenance;
- development CSV cache files are unchanged;
- dry-run creates no durable DB mutation.

No further live/provider calls were made after this evidence was closed.

## 7. Accepted promotion package

Accepted package:

```text
schema=fs015-historical-market-package-v1
```

Contents:

```text
coverage                 152
evidence              53,799
unavailable               38
created_matches           819
current_match_refs         81
team_refs                 200
```

Evidence split:

```text
completed-season       52,899
current-season 2026       900
```

Team refs are limited to the exact transitively required set for the 900 FS-015 current Match refs. Unrelated legacy Football-Data Team mappings are not exported.

Package SHA-256:

```text
384099c52c1be2a0d70048b34028c7453c3817027aa6e0d75d0ee23395a0abeb
```

Dry-run import against the accepted dev state produced:

```text
coverage_unchanged       152
evidence_unchanged    53,799
unavailable_unchanged     38
matches_unchanged        900
match_refs_unchanged     900
team_refs_unchanged      200
teams_created              0
```

The baseline-promotion marker remained absent after dry-run.

The accepted package was copied outside the branch checkout to:

```text
~/.local/share/finsport/promotions/FS-015
```

This copy must remain until successful post-merge operational import and verification.

It must then be explicitly deleted during final cleanup.

## 8. Promotion barrier and automatic lifecycle

Automatic historical-market maintenance cannot race ahead of initial accepted data promotion.

Before successful applied package import:

```text
FS015_MARKET_BASELINE_NOT_PROMOTED
→ NO_WORK
```

Successful operational `--apply` creates the durable marker:

```text
fs015-historical-market-baseline-promoted:v1
```

inside the same transaction as the package import.

Dry-run and failed imports cannot create the marker.

After promotion, future newly enabled competitions may use the normal one-shot historical sporting → historical market bootstrap lifecycle and converge to `NO_WORK`.

## 9. Implementation integrity corrections

Material implementation findings closed during the ticket included:

### Initial implementation / complete-diff review

- one-shot historical candidates could be blocked by previously claimed nonterminal work;
- `UNSUPPORTED_SOURCE` could retain the wrong strategy version and fail terminal recognition;
- package scope initially omitted required source refs for some current Matches;
- supported management-command allowlist required extension.

### Pass 2

- long-lived Nginx could retain stale Docker service DNS after Django recreation;
- dev cache behavior could incorrectly become live runtime authority;
- requested historical sporting bootstrap had to remain selectable while Competition activation was incomplete;
- market required seasons needed sporting history as the sole authority;
- current result recovery needed additive result filling;
- exact Football-Data MatchSourceRef had to precede bounded date fallback;
- historical unavailable needed a valid later transition to real evidence;
- package aggregate validation required deterministic scope;
- market selector accounting needed explicit unavailable behavior.

### Pass 3

- manual historical commands needed fail-closed authoritative scope validation before writes/acquisition;
- initial package promotion required a deterministic baseline barrier against automatic maintenance;
- exported Team refs needed strict transitive FS-015 scope.

### Manual pre-UAT correction

A pre-existing compatible Football-Data MatchSourceRef could be reused while FS-015 filled a missing canonical result, but the existing ref was not marked for promotion.

This could leave:

```text
dev Match → final result
operational Match → still NS
```

after package import.

The correction marks promotion provenance at mutation time only when FS-015 actually fills the result.

General rule:

```text
Durable state changed in dev and required operationally
→ promotion provenance must be recorded at mutation time

pre-existing entity/reference
!=
does not need export
```

### PR review correction

Invalid parser rows could previously be dropped while coverage still became `COMPLETE`.

The final implementation pass added structural invalid-row accounting and retry/currentness protection described in section 3.

All 24 accepted-baseline invalid rows were proven safe, so accepted UAT and package remain valid.

## 10. Test harness / repository findings

### Local-day fixture flake

The final repository gate initially produced 7 failures:

```text
6 × FS-011 Dixon-Coles
1 × FS-012 readiness
```

The failures were not FS-015 product regressions.

Shared test helper `future_target()` used:

```text
timezone.now() + 12h
```

while production target selection is based on local `America/Lima` day.

Depending on execution time, the target crossed UTC or local midnight and became ineligible for the requested test day.

The fixture was changed to a deterministic safe local-day anchor.

Targeted result:

```text
61 passed
```

Durable lesson:

```text
Tests for local-day behavior must use deterministic local-day fixtures,
not now()+N-hours plus UTC .date().
```

### Black authority mismatch

The repository had two incompatible formatter authorities:

```text
pre-commit Black     25.1.0
dev / requirements   26.5.1
```

For `test_cleanup_and_inspector.py`, the versions formatted a multiline string differently, producing an infinite loop:

```text
make format
→ pre-commit rewrites
→ pre-push make check rewrites expectation
→ repeat
```

The pre-commit Black revision was aligned to `26.5.1`.

Durable requirement:

```text
pre-commit formatter
==
dev formatter
==
local gate formatter
==
CI formatter
```

## 11. Final automated validation

Final PR-review correction validation:

```text
4 focused malformed-row regressions → PASS
FS-015 full suite                  → PASS
```

Final repository gate:

```text
Black             PASS
Ruff              PASS
Django check      PASS
migration drift   PASS — No changes detected
pip check         PASS
pip-audit         PASS

pytest            527 passed
coverage          84.12%
required          80%
```

The final malformed-row correction made no HTTP calls and did not regenerate accepted data or the promotion package.

## 12. PR review disposition

Three automated PR comments were reviewed.

### Structural invalid rows

```text
ACCEPTED
→ fixed in final implementation pass
```

### Missing FS-015 feedback

```text
EXPECTED AT REVIEW TIME
→ satisfied by this final pre-merge feedback commit
```

The feedback was intentionally deferred until the final substantive pre-merge commit rather than updated ceremonially after each green event.

### Nginx / FS-014 dynamic-DNS delta

```text
NOT REMOVED
```

The change is deliberately retained because concurrent dev/operational lifecycle testing exposed a real stale-upstream failure and the dynamic-DNS behavior is required by the FS-014 runtime addendum.

It is not accidental historical-market logic.

## 13. Execution-process findings and lessons

Several orchestration mistakes occurred during FS-015 even though the corresponding rules already existed in F009. They must be preserved so later tickets do not repeat them.

### Interactive shell was made fail-fast

A diagnostic/UAT block used:

```text
set -euo pipefail
```

globally in the user's interactive shell.

When `make check` correctly returned non-zero to expose test failures, the shell closed and made failure evidence harder to recover.

Required future behavior:

```text
diagnostic / UAT script
→ capture command RC
→ preserve output with tee/file
→ continue to summary
→ never kill the interactive shell merely because the test under investigation failed
```

### Temporary artifacts were treated as closure documents

There were proposals to update temporary/acceptance artifacts merely to reflect closure.

F009 already prohibits rewriting `tmp/**` to manufacture a green state.

Required distinction:

```text
existing expensive/UAT artifact → preserve, do not rewrite ceremonially

missing mechanical complete-diff artifact
→ may be reconstructed under tmp/ for actual review
```

### Feedback was proposed too early

There were attempts to update final feedback before PR review was complete.

Final feedback belongs to ticket closure and is versioned once in the final substantive pre-merge commit.

### GitHub CLI was proposed despite manual PR ownership

The user's workflow creates and manages the PR manually in GitHub.

No `gh pr create`, `gh pr ...`, or other GitHub CLI step should be inserted into this workflow.

### Broad staging caused scope leakage

Broad staging with:

```text
git add .
```

caused `FS-015_feedback.md` to enter the implementation commit before its intended final position.

Future ticket closure should stage explicit reviewed paths only.

### Formatter authority was not verified before push

The Black 25.1.0 versus 26.5.1 mismatch was discovered only after repeated commit/push failures.

Formatter/runtime authorities should be aligned before relying on pre-commit and pre-push as sequential gates.

### Push failures were initially treated as reasons to rerun gates manually

F009 already specifies:

```text
push hook failure
→ classify
→ correct exact cause
→ rerun only invalidated evidence
→ push again
```

Do not manually rerun the same full gate immediately before a push when that push hook will execute the same gate.

## 14. Observability / audit impact

FS-015 adds persistent audit surfaces for:

- historical source coverage;
- historical market provenance;
- source checksum and row identity;
- explicit unavailable market evidence;
- reconciliation outcomes;
- malformed-row structural versus source-artifact accounting;
- current-season reconciliation provenance;
- package aggregates and checksum;
- initial baseline-promotion state.

Historical raw CSV files are not durable production state.

No new bookmaker credential/audit surface or financial action path is introduced.

## 15. Post-merge operational handoff

The ticket is not operationally closed until the accepted package is promoted.

Required order:

```text
merge PR
→ make dev-destroy
→ sync master
→ make deploy-local
→ verify operational stack
→ import preserved FS-015 package --apply
→ verify counts/checksum
→ verify baseline promotion marker
→ repeat import/idempotence proof as bounded by the import contract
→ verify historical-market maintenance lifecycle
→ verify operational prospective pipeline remains healthy
→ remove preserved external FS-015 package
→ final ticket handoff / Planka Done
```

Do not perform another full historical download or full historical backfill during promotion.

The preserved package to use is:

```text
~/.local/share/finsport/promotions/FS-015
```

Expected package SHA-256:

```text
384099c52c1be2a0d70048b34028c7453c3817027aa6e0d75d0ee23395a0abeb
```

After successful operational import and verification:

```text
delete ~/.local/share/finsport/promotions/FS-015
```

This cleanup is part of FS-015 closure and must not be forgotten.

## 16. Remaining work / blockers

Pre-merge implementation blocker:

```text
NONE
```

Development UAT blocker:

```text
NONE
```

Package blocker:

```text
NONE
```

Remaining work is operational only:

```text
merge
→ dev cleanup
→ master deployment
→ accepted package import
→ operational verification
→ external package cleanup
→ final handoff
```

FS-015 is ready to merge once the final feedback/code commit is pushed and the PR gate is green.
