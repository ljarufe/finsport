# FS-018 Prediction Experiment Lab

Manual historical research in the existing football app, using finsport-dev.
No migrations, prospective prediction/odds writes, Beat entry, or routing change.
The maintainer-owned methodology is
`docs/research/FS-018_experiment_lab_global_prediction_research.md`.

## Ownership and artifacts

- `spec.py`: canonical immutable JSON, frozen CURRENT configs/readiness profiles,
  exact candidates/tournaments/methodology, runtime/dependency/source identity.
- `football/providers/oddspapi.py`: reusable OddsPapi v4 HTTP and response boundary.
  It imports no Experiment Lab module and has no automatic caller.
- `provider.py`, `mapping.py`, `market.py`: FS-018 private cache, durable physical
  attempt audit, read-only canonical mapping, reconstructed historical T-30
  evidence. The pure Market v2 mathematics
  are shared with `football.prediction.market`; prospective one-book behavior stays valid.
- `backfill.py`: one-shot resumable acquisition; `football/tasks.py` registers the
  explicitly named Celery task through existing autodiscovery.
- `replay.py`, `runner.py`: frozen input snapshot, daily strict-prior sporting
  replay and per-league checkpoints; no hyperparameter selection.
- `analysis.py`: COMMON/NATURAL, proper scores, equal-league objective, paired
  stratified weekly bootstrap (5,000, seed 18092026), eligibility and fallback.
- `views.py`: deterministic local `spec.json`, `manifest.json`, `summary.json`,
  `per_match.jsonl.gz` and `report.md` for each completed run.
- `artifacts.py`: human report and reviewed GLOBAL_PREDICTION_V1 promotion record.

Private raw responses live only in ignored `tmp/FS-018_oddspapi/`. Derived inputs,
backfill state, replay checkpoints and complete run evidence live under
`tmp/FS-018_experiments/`. JSON writes use temporary files, fsync and rename.
A shared filesystem lock spans physical provider requests and retries, including
cache recheck; persisted timestamps preserve spacing after worker restart.
Physical starts, HTTP statuses, 429 responses, retries and cache hits are
checkpointed under the run directory. Terminal backfill audit also reports
mapping outcomes, complete-book counts and quote-age distribution. Quote age
is measured from canonical kickoff; T-30 is only the admissibility cutoff.
Completed fixture acquisition is not repeated. Failed fixtures can be retried by
reenqueueing the same spec. Duplicate running backfills fail `ALREADY_RUNNING`.
The same discovered fixture list is retained across resume, including mapping
exclusions. Fixing canonical identities later requires a new spec/run; it does
not rewrite frozen evidence.

## Commands for later UAT (not executed during Pass 1)

Use the Dev Container, or prefix commands with
`docker compose -p finsport-dev -f compose.dev.yml run --rm --no-deps django-web`.
Before enqueueing, the dev Celery container must load this checkout's task code
and the new `FINSPORT_EXPERIMENT_RUNTIME=finsport-dev` environment marker. Recreate
only the dev Celery service through normal dev lifecycle management. No Beat is
needed. The marker is provided only by compose.dev.yml; commands and the task
also require automatic pipeline/capture to be disabled, Lima timezone and the
safe queue. `.env` supplies `ODDSPAPI_API_KEY`; never put its value on a command line.

Freeze a pilot spec using an explicitly chosen UTC cutoff containing the frozen
Betis/Getafe fixture (replace CUT_OFF with the reviewed ISO instant):

```sh
python manage.py run_prediction_experiment --freeze --competitions 1278 --cutoff CUT_OFF --spec /app/tmp/FS-018_experiments/pilot-spec.json
python manage.py enqueue_oddspapi_historical_backfill --account-only --allow-network
python manage.py enqueue_oddspapi_historical_backfill --spec /app/tmp/FS-018_experiments/pilot-spec.json --pilot --allow-network
```

`--pilot` discovers La Liga but fetches history only for `id1000000872478570`.
Inspect the terminal backfill checkpoint and reviewed pilot evidence before the
full run. Once it is terminal:

```sh
python manage.py run_prediction_experiment --spec /app/tmp/FS-018_experiments/pilot-spec.json --pilot
```

After independent live pilot PASS, freeze the full spec (all ten leagues are the
default), revalidate account quota, then manually enqueue the full backfill:

```sh
python manage.py run_prediction_experiment --freeze --cutoff CUT_OFF --spec /app/tmp/FS-018_experiments/full-spec.json
python manage.py enqueue_oddspapi_historical_backfill --account-only --allow-network
python manage.py enqueue_oddspapi_historical_backfill --spec /app/tmp/FS-018_experiments/full-spec.json --allow-network
```

Reissuing the enqueue command resumes the same checkpoint. Each unique cached
tournament/window avoids another billable discovery request. Historical requests
use the exact three frozen bookmakers and >=10-second spacing; fixture requests
use >=2-second spacing. Retry-After or deterministic increasing backoff is
persisted across worker restarts. There are at most three attempts with classified errors.
The optional account check is uncached and prints only request_limit/request_count.
No account values are hardcoded as quota configuration.

Once every league was attempted and acquisition is terminal, run offline:

```sh
python manage.py run_prediction_experiment --spec /app/tmp/FS-018_experiments/full-spec.json
```

The first analysis freezes canonical inputs plus the acquisition checkpoint.
Replay can resume by league; subsequent completed analysis reads and verifies
`run.json` without querying the DB or provider. An acquisition completed *after*
this input snapshot cannot silently enter that run; choose a newly frozen spec
with a new cutoff for a later evidence corpus. Preserve the ignored input/run
artifacts locally for reproducibility. Source/dependency identities are in the
spec; the run hash covers measured resources as well as all evidence.
The five local views are reconstructed deterministically from the verified run.
The compressed per-Match view uses fixed gzip metadata and contains derived
probabilities, losses, cohorts and selected historical quote provenance, never
the raw provider response. A mismatch with an existing view fails closed.

After independent full UAT review, explicitly request promotion:

```sh
python manage.py run_prediction_experiment --spec /app/tmp/FS-018_experiments/full-spec.json --promote
```

This writes the two durable filenames prescribed by FS-018. It refuses pilot,
incomplete league scope, FAILED acquisition, insufficient COMMON evidence, or a
conflicting prior GLOBAL_PREDICTION_V1. It does not rewrite run evidence or update
operational routing. No placeholder final report/winner is produced in Pass 1.

## Pass 3 recovery and fresh confirmation (Luis's later live UAT)

The original full spec, acquisition checkpoint and raw cache remain reference
evidence. Freeze a recovery spec from the original full spec; this inherits the
exact cutoff, ten competitions, three books, T-30 and sporting configs while
recording the new ordered-pair mapping policy and source run:

```sh
python manage.py run_prediction_experiment --freeze --recover-from /app/tmp/FS-018_experiments/full-spec-v1.json --spec /app/tmp/FS-018_experiments/recovery-spec-v2.json
python manage.py enqueue_oddspapi_historical_backfill --account-only --allow-network
python manage.py enqueue_oddspapi_historical_backfill --spec /app/tmp/FS-018_experiments/recovery-spec-v2.json --allow-network
```

The manual command uses Celery broker dispatch on `finsport.local.safe` even
when DEBUG makes other tasks eager. It returns a task ID promptly. Recovery
refreshes each tournament discovery once into a new private cache revision,
remaps all discovered fixtures, reuses valid successful historical cache, and
refreshes prior FAILED or one-book NO_USABLE_T30 fixtures once into a separate
revision. The checkpoint and cache make re-enqueue after a worker reboot
resumable. Inspect the new terminal acquisition and its audit before offline
analysis:

```sh
python manage.py run_prediction_experiment --spec /app/tmp/FS-018_experiments/recovery-spec-v2.json --confirm
```

`--confirm` creates a separate `FRESH_CONFIRMATION_V2` analysis directory and
recomputes the sporting replays from full chronological history, Market
predictions, paired cohorts, metrics, bootstrap and selection. The confirmation
requires all four frozen candidates to be globally eligible, scores all four on
the exact same COMMON Match set, and selects the lowest equal-league COMMON
log-loss. NATURAL coverage, stability, failures, provider dependency and runtime
remain reported diagnostics but cannot change the selected model. The paired
bootstrap determines whether the observed leader is `CLEAR_SUPERIORITY`; when its
intervals do not separate it from every other arm the disposition remains
`NO_CLEAR_SUPERIORITY`, but the selected model is still the best observed COMMON
score. Completed confirmation reruns verify and reproduce the same artifacts. The
original acquisition, raw cache, replay and scientific run are untouched.

After reviewing live recovery and confirmation UAT, Luis may explicitly
replace the existing **untracked provisional** promotion by naming its prior
run ID:

```sh
python manage.py run_prediction_experiment --spec /app/tmp/FS-018_experiments/recovery-spec-v2.json --confirm --promote --replace-provisional --expected-previous-run-id 2c65930e712d2a594385741ed105d19c3f981f7a8bf4908282dc6f53a78fa291
```

The command verifies that the provisional pair is untracked and matches the
expected prior run, backs both files up under ignored `tmp/`, then writes the
new record and report. It will not replace committed promotion files. Codex
does not execute this promotion.

## Analysis details

Coverage uses eligible finished targets as denominator; the manifest also keeps
excluded canonical targets with reasons. All three sporting models use exactly
frozen CURRENT config. Readiness is recorded and used for DC's existing diagnostic
classification, not as an invented betting filter on legitimate research predictions.
All history before each Lima target day is allowed, including history before 2026;
the scored window starts at 2026-01-01 UTC.

A global candidate needs legitimate evidence in each required league. COMMON is
the intersection of those globally eligible candidates. Partial Market stays in
diagnostic reports and cannot win. Empty COMMON in any required league yields
INSUFFICIENT_EVIDENCE and blocks promotion. Bootstrap resamples entire ISO Lima
calendar weeks independently within leagues, using the same draws for every
candidate; league means retain equal weight regardless of Match counts.

For historical STANDARD runs, the original frozen qualitative guardrails remain
unchanged: stability is the ordered pair of population standard deviations of
NATURAL league and Lima-week log-loss; clear superiority also requires no loss in
coverage, stability or failure count, and the original fallback begins with
coverage. This preserves the first run exactly for auditability.

For `FRESH_CONFIRMATION_V2`, that fallback is deliberately not used. All four
models must participate and are ranked only by equal-league COMMON log-loss on
the identical paired Match cohort. NATURAL coverage, stability, failures,
dependency and resources are diagnostics only and cannot select Elo (or any other
model) merely for covering more Matches. Bootstrap significance changes only the
disposition (`CLEAR_SUPERIORITY` vs `NO_CLEAR_SUPERIORITY`), not which observed
COMMON leader is selected. Exact score ties fall back only to stable model/version
identity. Resource measurements are frozen with the run, so repeating analysis
of the same artifact is deterministic.
RSS is the process high-water mark, not isolated per-model allocation; provider
cooldown is excluded from replay timing. The run records warnings beyond 60 minutes
or 1 GiB for UAT investigation.

Frozen CURRENT selection metadata stays in `configs[*].selected`; only `xi`,
`k` and `C` as appropriate enter `configs[*].executable` and the adapters.
The promotion record hashes the selected model's effective configuration across
the ten leagues, or the exact historical Market policy if Market is selected.

`compare(manifest, model_identities, competitions, resources)` can compare a future
frozen challenger using the same cohorts/metrics/bootstrap. Declaring a real new
family requires a subsequent reviewed spec version; FS-018's four-arm spec is
intentionally fixed. The synthetic challenger test exercises this reuse without
adding a production family or fabricating a baseline.

## Validation

Offline tests use fake responses/clocks and a temporary test DB. The historical
oracle test derives equivalent synthetic bookmaker prices from the approved fair
vectors; it is not a redistributed provider payload. Run focused tests with pytest
inside finsport-dev, then the repository gate `make check`. Live UAT, ten-league
coverage, final scores, resource practicality and baseline promotion remain
separate evidence that cannot be inferred from these tests.
