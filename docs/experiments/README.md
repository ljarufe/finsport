# Experiment Lab — compact indices

`docs/research/` contains maintainer-owned research documents only. Per-run results,
ledgers, matrices, metrics, diagnostics, reports and manifests are retained under
`~/Documents/finsport/research-evidence/FS-021/<execution_id>/` (configurable via
`FS021_ROOT`). `docs/experiments/FS-021/<execution_id>/` contains only compact,
source-bound JSON locators for native publications; it is not the data authority.

FS-021 original `run.json` and the prior economic `economic_selection_v1/` are
immutable. Economic reporting v1.1 uses a separate `economic_selection_v1_1/`
publication to correct top20 order and remove the mutable retention flag without
altering the v1 selector method, winner, scores or the scientific conclusion.

The optional cleanup tool `tools/fs021_cleanup_research.py` refuses to remove
any copied data before the original, v1.1 economic and diagnostic indices are
present and hashed. Never clean original execution folders as part of this step.
