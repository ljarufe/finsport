# FS-009 Feedback

## IMPLEMENTATION SNAPSHOT — MAY BECOME STALE

Status: PRE-UAT implementation snapshot (Pass 4 human-UAT correction).

- Added read-only Django reporting selectors/views under `football.reporting`.
- `/` is historical prospective reporting; `/daily/` is local-day inspection; `/admin/` preserves Django Admin.
- Backtest unavailable arms are displayed independently from prospective aggregates.
- Bootstrap 5.3.8 is vendored under `static/reporting/` with MIT attribution; no application JavaScript or CDN is used.
- No models, migrations, providers, task dispatch, domain writes, or financial writes were introduced.

Pass 2 corrects list-valued unavailable reasons, configuration-safe comparison identities, resolved Decision/economic samples, grouped cross evidence, config/instance-safe agreement, prospective-only daily detail, and filter scope for backtest/capital evidence.

Pass 3 reproduced the maintained-DB `/` failure and corrected safe Capital metric rendering. It also introduced one ratio-to-percent formatter, expanded focused reporting coverage from 2 to 10 tests, and removed the Team competition N+1 exposed by the new constant-query regression.

Pass 4 addressed the consolidated human-UAT findings:

- Root static source files were not discoverable because `STATICFILES_DIRS` omitted the repository `static/` directory. The normal `entrypoint.sh` already ran `collectstatic`, nginx already mounted the shared `STATIC_ROOT`, and its alias was correct. Adding the source directory makes a normal `make dev-up` publish both CSS assets durably.
- Decision reasons now have a separate contextual Spanish vocabulary and neutral Decision-specific fallback.
- Model/policy configurations have deterministic compact labels plus full key/value detail.
- Confusion matrices and calibration bins render as semantic tables.
- Decision denominators are explicit; Capital preserves false, zero and missing values and labels its two exposure metrics separately.
- Backtests are grouped by owning PredictionExperiment; daily rows expose source-model/policy provenance, Spanish match status, clean Team names and timestamp-valid price provenance.
- Historical and daily information hierarchy was revised using only local Bootstrap, small CSS and native details/summary.

Maintainer-owned UAT context: Competition 1270 Ligue 1, 1276 Eredivisie and 1524 Primera División (PE) were already enabled by the maintainer. Codex did not alter these flags or backfill their evidence.

Fresh normal-lifecycle HTTP evidence through nginx after `make safe-down && make dev-up`: `/` 200, `/daily/?date=2026-08-29` 200, Bootstrap CSS 200 `text/css`, custom CSS 200 `text/css`. Both bodies contain CSS and home references both local paths.

Read-only browsing baseline and after counts were identical: PredictionExperiment 10, Prediction 2312, Decision 21162, OddsObservation 321, CapitalExperiment 5, CapitalPolicyRun 5. Delta: zero for every model.

Automated validation: 21 focused reporting tests passed; full suite 294 tests passed with 86.61% coverage; Black, Ruff, Django check, migration dry-run, pip check and pip-audit passed. Human visual/browser delta-UAT remains maintainer-operated and PENDING in the acceptance ledger.
