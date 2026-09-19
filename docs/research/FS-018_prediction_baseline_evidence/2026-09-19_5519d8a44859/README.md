# FS-018 Prediction baseline evidence

This directory contains the compact durable evidence for the final FS-018 Prediction baseline.

Final result:

`GLOBAL_PREDICTION_V1 = MARKET_CONSENSUS`

Model:

`fs013-market-consensus-v2`

Disposition:

`CLEAR_SUPERIORITY`

The four candidates were compared on the same COMMON cohort of 1,877 matches using:

`PAIRED_COMMON_EQUAL_LEAGUE_LOG_LOSS_V1`

## Retained in Git

- `README.md`
- `recovery-spec-v2.json`
- `backfill-summary.json`
- `selection-summary.json`
- `SHA256SUMS`

The authoritative promoted baseline remains:

`docs/research/FS-018_global_prediction_v1.json`

The human-readable final report remains:

`docs/research/FS-018_global_prediction_baseline_report.md`

## Full local run evidence

Large run-level artifacts are intentionally not committed.

They remain locally under:

`tmp/FS-018_final_evidence_local/2026-09-19_5519d8a44859/`

and in the original ignored Experiment Lab run directory.

`selection-summary.json` records hashes for the preserved full local artifacts.

Raw OddsPapi provider payloads remain private/ignored and are not part of the durable repository evidence.
