# Capability Execution Matrix

This matrix describes the local-only/demo-only FS-008 experimental runtime.
`ACTIVE` means the capability belongs to the current evidence-generation
lifecycle. Manual commands remain valid diagnostic/override paths and do not
make an otherwise automatic capability manual-by-design.

| Capability | Code exists | Automatic path | Manual path | Current blocker or reason | Classification | Next owner or trigger |
| --- | --- | --- | --- | --- | --- | --- |
| API-Football fixture discovery | Yes | Pipeline capture phase when discovery is enabled | `run_football_capture --purpose FIXTURE_REFRESH` | Free-plan baseline is today plus tomorrow | ACTIVE | Operations/configuration |
| API-Football odds capture | Yes | Due `ODDS_CAPTURE` intended windows | `run_football_capture` with bounded filters | Requires eligible coverage, identity, quota, and valid window | ACTIVE | Operations/configuration |
| API-Football result refresh | Yes | Pipeline unresolved-result debt | `run_football_capture --purpose RESULT_REFRESH` | Requires resolved provider identity | ACTIVE | Operations/configuration |
| Inkabet prospective MW3W acquisition | Yes | Same due, successfully completed `ODDS_CAPTURE` work; one categories discovery per run and MW3W per resolved event | `sync_football_day --with-odds` | Local brand/market configuration and safe reconciliation; secondary/fail-soft only | ACTIVE | Operations/configuration |
| Inkabet extended statistics | No | None | None | NOT_IMPLEMENTED | NOT_IMPLEMENTED | Separate future product decision |
| Catalogue maintenance | Yes | Persistent once-per-Lima-day due check after immediate pipeline work | `sync_football_catalog` or `run_football_maintenance` | May defer under conservative API-Football quota/reserve policy | ACTIVE | Daily due identity |
| New-season bootstrap | Yes | Daily DB eligibility; provider sync only for an enabled, current, resolved, empty Season | `sync_football_season` or `run_football_maintenance` | No fabricated Season; provider denial is factual degraded evidence | ACTIVE | Newly discovered eligible Season |
| Chronological backtests | Yes | Weekly maintenance when resolved evidence changed | `evaluate_football_predictions` or forced maintenance | Requires eligible enabled population across train/validation/outer seasons | ACTIVE | Seven-local-day due state |
| Hyperparameter/config reselection | Yes | Same weekly chronological maintenance cycle | Same backtest commands | `NO_WORK` preserves prior selection when evidence is unchanged | ACTIVE | Seven-local-day due state |
| `MODERNIZED_R45` | Yes | Chronological weekly backtest and prospective pipeline | Backtest/prediction management commands | Factual history, outcome-class, or temporal-market insufficiency may yield `UNAVAILABLE` | ACTIVE | Every eligible evaluation/prospective target |
| Prospective Prediction | Yes | Pipeline prediction phase from due odds work | `predict_football_day` or executed pipeline | Individual fitted arms may be factually unavailable | ACTIVE | FS-009 presentation |
| Decision policies | Yes | Created for persisted Predictions | Prediction commands | Thresholds/grids remain frozen product behavior | ACTIVE | FS-009 presentation |
| Canonical settlement | Yes | Pipeline settlement phase | Executed pipeline | Requires canonical finished status/outcome | ACTIVE | FS-009 presentation |
| Capital research baseline | Yes | Pipeline normalized replay when evidence is sufficient | `evaluate_capital_policies` | Unavailable without resolved actionable timestamp-valid Decisions | ACTIVE | FS-009/FS-010 evaluation |
| Pipeline report | Yes | Every executed pipeline audit | `run_football_pipeline` | Rolling JSON report, not a frontend | ACTIVE | FS-009 |
| `LEGACY_R45` | Historical docs/migration evidence only | None | None | Inert runtime/accounting removed | REMOVE | No runtime owner |
| Legacy `bet`/DRF API | No | None | None | Superseded by Prediction/Decision/Capital | REMOVE | New product decision required |

One file-backed Celery Beat instance owns scheduling. When pipeline automation is
enabled it registers only `football.pipeline.wake`; persistent maintenance
identities keep daily/weekly capabilities from repeating on its frequent wake.
`make up` starts the complete operational/observability profiles, `make dev-up`
starts no Beat, and `make safe-down` drains and removes all profiles without
deleting named volumes.

Prediction probabilities, Decision action space, selected temporal prices,
canonical settlement, Capital semantics, cancellation hygiene, and legitimate
unavailability are unchanged. Inkabet is never canonical authority, no
bookmaker authentication exists, and real betting remains forbidden.
