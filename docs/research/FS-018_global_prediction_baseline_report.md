# FS-018 — Global Prediction Baseline

**Date:** 2026-09-19
**Baseline:** `GLOBAL_PREDICTION_V1`
**Selected:** `MARKET_CONSENSUS`
**Model version:** `fs013-market-consensus-v2`
**Disposition:** `CLEAR_SUPERIORITY`

## Selection contract

Final confirmation used:

`FRESH_CONFIRMATION_V2`

Selection policy:

`PAIRED_COMMON_EQUAL_LEAGUE_LOG_LOSS_V1`

Selection basis:

`LOWEST_EQUAL_LEAGUE_COMMON_LOG_LOSS`

Coverage and NATURAL sample size were diagnostics only and did not participate in selection.

All four candidates were compared on the identical COMMON cohort of **1,877 matches**.

## Final comparison

| Candidate | COMMON N | COMMON accuracy | NATURAL N | Coverage | Equal-league COMMON log-loss |
|---|---:|---:|---:|---:|---:|
| MARKET_CONSENSUS | 1,877 | 50.61% | 1,906 | 77.04% | **0.9963326648** |
| ELO_MULTINOMIAL_LOGIT | 1,877 | 49.39% | 2,474 | 100.00% | 1.0148007881 |
| DIXON_COLES | 1,877 | 49.76% | 2,425 | 98.02% | 1.0179332423 |
| INDEPENDENT_POISSON | 1,877 | 49.55% | 2,444 | 98.79% | 1.0219865430 |

Lower log-loss is better.

`MARKET_CONSENSUS` has the lowest primary score.

## Paired uncertainty

Frozen bootstrap:

- 5,000 replicates
- Competition-stratified
- Competition × Lima ISO-week blocks
- seed `18092026`
- percentile 95% interval

Challenger minus Market log-loss:

| Comparison | 95% interval |
|---|---|
| DIXON_COLES − MARKET_CONSENSUS | `[0.009728, 0.034087]` |
| ELO_MULTINOMIAL_LOGIT − MARKET_CONSENSUS | `[0.008044, 0.029198]` |
| INDEPENDENT_POISSON − MARKET_CONSENSUS | `[0.013908, 0.038005]` |

All three intervals are strictly positive.

Because lower log-loss is better, the frozen rule confirms Market Consensus against all three challengers.

Therefore:

`selection_disposition = CLEAR_SUPERIORITY`

## Historical Market recovery

Terminal recovery produced:

- `RECONSTRUCTED`: 1,907
- Market NATURAL predictions: 1,906
- Market NATURAL coverage: 77.04%
- `UNMATCHED`: 372
- `AMBIGUOUS`: 2
- `NO_USABLE_T30`: 111
- `FAILED`: 70
- historical cache hits: 1,757
- new physical historical calls: 331
- HTTP 429: 0
- retries: 0
- network errors: 0

Historical evidence profile:

`ODDSPAPI_RECONSTRUCTED_T30_V1`

Historical evidence is research evidence and is not prospective `OddsObservation`.

## Identities

Experiment spec:

`de5dc600168fd249f93848e9ca3d550b0de05eed07824f9874bf5fec68d4f9d0`

Acquisition run:

`55e2c9682f20d229b3ca67a102d4c084c581f33686fea094139333e041838b81`

Confirmation analysis:

`b9db09d96e5c5e5a390d29b72045c74e5c01d99e0512176f2105061e68e19a6a`

Confirmation run:

`5519d8a44859478e7be5e6055d49fd3b6406b5eca590a195104337553414337e`

Data cutoff:

`2026-09-19T03:17:33.457781+00:00`

## Durable evidence

Machine-readable promotion authority:

`docs/research/FS-018_global_prediction_v1.json`

Compact experiment evidence:

`docs/research/FS-018_prediction_baseline_evidence/2026-09-19_5519d8a44859/`

The repository deliberately retains only compact durable evidence.

Large run-level `summary`, per-match evidence, manifest and generated full report remain in ignored local experiment artifacts rather than Git. Their hashes are preserved in the compact selection summary.

## Interpretation

FS-018 establishes:

`GLOBAL_PREDICTION_V1 = MARKET_CONSENSUS`

This is a Prediction result, not proof of profitable betting.

The next Decision/Capital studies must test economic usefulness using available prices, selectivity/NO_BET, expected value, ROI/yield, drawdown, capital utilization and opportunity cost.

FS-018 does not automatically change operational Prediction routing and does not authorize real betting.
