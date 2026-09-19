# FS-018 — Global Prediction Baseline

**Date:** 2026-09-19
**Baseline:** `GLOBAL_PREDICTION_V1`
**Selected:** `MARKET_CONSENSUS`
**Model version:** `fs013-market-consensus-v2`
**Disposition:** `CLEAR_SUPERIORITY`

## Selection contract

`FRESH_CONFIRMATION_V2`

Selection policy:

`PAIRED_COMMON_EQUAL_LEAGUE_LOG_LOSS_V1`

Selection basis:

`LOWEST_EQUAL_LEAGUE_COMMON_LOG_LOSS`

Coverage and NATURAL sample size are diagnostic only.

All candidates were compared on the identical COMMON cohort of **1,877 matches**.

## Final comparison

| Candidate | COMMON N | COMMON accuracy | NATURAL N | Coverage | Equal-league COMMON log-loss |
|---|---:|---:|---:|---:|---:|
| MARKET_CONSENSUS | 1,877 | 50.61% | 1,906 | 77.04% | 0.9963326648 |
| ELO_MULTINOMIAL_LOGIT | 1,877 | 49.39% | 2,474 | 100.00% | 1.0148007881 |
| DIXON_COLES | 1,877 | 49.76% | 2,425 | 98.02% | 1.0179332423 |
| INDEPENDENT_POISSON | 1,877 | 49.55% | 2,444 | 98.79% | 1.0219865430 |

Lower log-loss is better.

## Paired uncertainty

5,000 Competition-stratified Lima-week bootstrap replicates, seed `18092026`.

| Challenger minus MARKET_CONSENSUS | 95% interval |
|---|---|
| DIXON_COLES | `[0.009728, 0.034087]` |
| ELO_MULTINOMIAL_LOGIT | `[0.008044, 0.029198]` |
| INDEPENDENT_POISSON | `[0.013908, 0.038005]` |

All three intervals are strictly positive.

`selection_disposition = CLEAR_SUPERIORITY`

## Final lineage

Experiment spec: `de5dc600168fd249f93848e9ca3d550b0de05eed07824f9874bf5fec68d4f9d0`

Source acquisition: `55e2c9682f20d229b3ca67a102d4c084c581f33686fea094139333e041838b81`

Execution runtime identity: `7cbeae3db86c33001e5c82f8aa66d9619a54be247569ec5abddf465730e09cd3`

Confirmation analysis: `15f313269bf23ed189ff3e50599b0b30785c23b61a1c361a7a7816f691a8ccc8`

Confirmation run: `b41fd8a324f4fd0265c8a9d43a1308dc21f5b862d45f6583b3a75542df5c711b`

Manifest hash: `3339a7f8247feee99e232d94be109cb32424234661bf1a7c6c2179b4db82c61e`

Cohort hash: `08d8f7c2852444c2e66ed28c4075e2bc51708d3ac918cdb7cf75daf858ae2c1c`

## Historical Market recovery

- `RECONSTRUCTED`: 1,907
- `UNMATCHED`: 372
- `AMBIGUOUS`: 2
- `NO_USABLE_T30`: 111
- `FAILED`: 70

Historical evidence remains research-only and is not prospective `OddsObservation`.

## Interpretation

`GLOBAL_PREDICTION_V1 = MARKET_CONSENSUS`

FS-018 establishes the Prediction baseline, not profitable betting.
Decision/Capital studies must evaluate available prices, EV, NO_BET selectivity, ROI/yield, drawdown, capital utilization and opportunity cost.
