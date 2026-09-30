# FS-023 pre-UAT runtime contract

This is an operator checklist for the later local-only demo checkpoint. It does not authorize deployment, provider traffic, scientific execution, or real betting during F009 Pass 2.

## Effective settings before enabling the single scheduler

The ignored `.env` can retain an FS-022 T6/T60/T30 JSON override. Compare it privately with `.env.dist` and set `FOOTBALL_MARKET_CONSENSUS_WINDOWS` to exactly:

```json
[{"name":"market-t10m","offset_minutes":10,"before_tolerance_minutes":0,"normal_tolerance_minutes":3,"late_tolerance_minutes":8}]
```

The effective wake is 180 seconds. One Beat owner schedules `football.pipeline.wake`; no separate capture wake or persisted database Beat schedule is permitted. R45, R45 Capital and Inkabet automatic flags stay false. A missing BSD token is permitted and reports `BSD_NOT_CONFIGURED` with API-F result fallback. Never print `.env` or provider tokens in the review evidence.

Run the read-only check **inside the built runtime container** before enabling automation:

```sh
docker compose -f compose.yml run --rm --no-deps django-web python manage.py verify_fs023_runtime --require-automatic
```

It exits nonzero with `FS023_T10_EFFECTIVE_CONFIG_INVALID` for stale three-window configuration, and reports only safe settings. If automation is intentionally disabled in the Dev Container, omit `--require-automatic`. After local start, verify that exactly one `celery-beat` service owns the wake using `docker compose -f compose.yml ps --services --filter status=running` and inspect the effective Beat schedule with the same safe preflight. Do not use `docker compose down -v` or modify persistent volumes.

## Reproducible later U33/U34 corpus contract

The retained source directory on the host must be mounted read-only at `/app/fs023-corpus`; a host `/home/...` path is not visible inside the application image by default. The `run_fs023_experiment` command requires `--durable-corpus` explicitly. Before either run, prepare a frozen benchmark JSON at `/app/tmp/FS-023_benchmark_frozen.json` using the approved official MEF/SBS source, freeze date and provenance. `validate_benchmark` checks its identity and rejects invented or future values. The corpus loader verifies both frozen SHA-256 hashes, 2,059 + 546 rows, zero overlap and the 2,605-row/16-country union before execution.

For U33, evaluation of `[209]` only:

```sh
docker compose -f compose.dev.yml run --rm --no-deps \
  -v /home/ljarufe/Documents/finsport/research-evidence/FS-023/final:/app/fs023-corpus:ro \
  django-web python manage.py run_fs023_experiment \
  --candidate-ids 209 \
  --benchmark-spec /app/tmp/FS-023_benchmark_frozen.json \
  --durable-corpus /app/fs023-corpus \
  --root /app/tmp/fs023-u33
```

For U34, restricted selection of `[209,216,223]` only:

```sh
docker compose -f compose.dev.yml run --rm --no-deps \
  -v /home/ljarufe/Documents/finsport/research-evidence/FS-023/final:/app/fs023-corpus:ro \
  django-web python manage.py run_fs023_experiment \
  --candidate-ids 209,216,223 \
  --benchmark-spec /app/tmp/FS-023_benchmark_frozen.json \
  --durable-corpus /app/fs023-corpus \
  --root /app/tmp/fs023-u34
```

The benchmark file is deliberately absent until approved UAT evidence exists. Both commands enforce 5,000 frozen replicates. U33 has no selection or promotion authority; U34 remains a restricted publication with `activation=false`. Neither command changes `StrategyBinding`, `StrategyEpoch` or `CapitalDeployment`.
