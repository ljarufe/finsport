# FS-006 — Lifecycle de partidos definitivamente cancelados y limpieza de evidencia derivada — REFERENCE ONLY

**Proyecto:** Finsport
**Fecha:** 2026-08-28
**Estado:** `REFERENCE ONLY`
**Baseline de repositorio:** `master@5ccb99d89829efdb74ffac47ad44fd3c2ec22279` (merge de FS-005)
**Decisión que habilita:** cerrar la frontera destructiva que FS-006 debe aplicar cuando un fixture queda definitivamente cancelado/no realizado, sin confundirlo con postponement/reschedule y sin dejar evidencia experimental/económica inconsistente.

---

## 1. Pregunta principal

> Cuando el primary canonical provider indica de forma inequívoca que un partido fue cancelado y no se jugará, ¿qué debe conservar Finsport y qué evidencia derivada debe eliminar o invalidar para que el pipeline prospectivo siga siendo reproducible y no reprocese indefinidamente el fixture?

## 2. Known facts

### 2.1. Decisión de producto ya tomada

El handoff de FS-005 registra la decisión del maintainer:

```text
definitively cancelled / never played
→ no longer useful for experimentation
→ dependent research/economic evidence should be cleaned
```

La misma decisión exige distinguir:

```text
definitively cancelled / never played
!=
postponed / rescheduled
```

### 2.2. Semántica actual de API-Football

La guía oficial actual de API-Football publicada el 13 de marzo de 2026 documenta:

```text
CANC
→ cancelled

PST
→ postponed

SUSP
→ suspended mid-match
```

También documenta que fixtures postponed/cancelled permanecen en `/fixtures` con su
status actualizado; no desaparecen del proveedor.

Consecuencia:

```text
delete canonical Match on CANC
→ provider can rediscover the same fixture later
→ identity churn / repeated recreation risk
```

Referencia durable:

- API-SPORTS, “How to Get Started with API-Football: The Complete Beginner's Guide”, 2026-03-13.
  https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide

Documentación general:
- API-Football Documentation v3.
  https://www.api-football.com/documentation-v3

### 2.3. Current repository relationships

Current `football/models.py` on `master@5ccb99d...` establishes:

```text
MatchSourceRef.match
→ CASCADE

OddsSnapshot.match
→ CASCADE

OddsObservation.match
→ CASCADE

CaptureWorkItem.match
→ CASCADE

Prediction.match
→ CASCADE

Decision.match
→ CASCADE
```

but also:

```text
Decision.selected_odds_observation
→ PROTECT

CapitalLedgerEntry.source_decision
→ PROTECT

CapitalExperiment.source_experiment
→ PROTECT
```

and `CapitalExperiment` freezes its source stream in:

```text
input_manifest
input_hash
input_count
```

Therefore a generic `Match.delete()` is not a safe data-hygiene contract.

Repo references:

- `football/models.py`
- `football/prediction/evaluation.py`
- `football/prediction/service.py`
- `football/capital/service.py`
- `football/capture/service.py`

all at `master@5ccb99d89829efdb74ffac47ad44fd3c2ec22279`.

---

## 3. Evidence classification

| Claim | Class | Consequence |
|---|---|---|
| `CANC` means cancelled | ESTABLISHED — current official provider docs | valid destructive trigger candidate |
| `PST` means postponed | ESTABLISHED — current official provider docs | MUST NOT trigger cleanup |
| cancelled fixtures remain in provider | ESTABLISHED — official provider docs | preserve canonical identity/tombstone |
| generic Match cascade is unsafe | ESTABLISHED — current FK graph | explicit cleanup service required |
| capital results become invalid if an input Decision disappears | ESTABLISHED — input manifest/hash semantics | whole affected capital experiment must be invalidated/deleted |
| CaptureRun/WorkItem is operational audit, not experimental evidence | STRONG INFERENCE from FS-005 contract | preserve audit unless future policy explicitly says otherwise |
| other unusual terminal statuses should be cleaned | UNKNOWN for this ticket | preserve; do not generalize from `CANC` |

---

## 4. Recommendation accepted for FS-006

### 4.1. Trigger

FS-006 should automatically clean only when the **primary canonical football state**
has unequivocally reached:

```text
status_short == "CANC"
```

or an exactly equivalent canonical value if preflight proves the current checkout
normalizes provider status differently.

Do **not** trigger cleanup for:

```text
PST
SUSP
unknown/ambiguous terminal-no-outcome status
```

If preflight discovers an additional provider code that is claimed to mean “never
played”, it must not be added silently. It requires explicit evidence and ticket
reconciliation.

### 4.2. Preserve canonical tombstone

Keep:

```text
Match
MatchSourceRef
canonical CANC status
kickoff/source identity metadata
CaptureRun
CaptureWorkItem audit
```

Reason:

- prevents rediscovery/recreation churn;
- preserves provider identity;
- records why the fixture ceased to participate;
- preserves operational evidence about calls already spent;
- remains reversible if provider state is corrected unexpectedly.

### 4.3. Remove dependent experimental/economic evidence

For the cancelled Match, remove:

```text
OddsSnapshot
OddsObservation
Prediction
Decision
```

because they no longer belong in the experimental sample requested by the maintainer.

### 4.4. Capital invalidation

Before deleting affected Decisions:

1. collect affected Decision IDs;
2. identify every `CapitalExperiment` whose frozen `input_manifest` contains any of
   those Decision IDs;
3. delete/invalidate the **whole** affected `CapitalExperiment` and its dependent
   `CapitalPolicyRun` / `CapitalLedgerEntry`;
4. only then delete Decisions.

Do not partially edit:

```text
CapitalExperiment.input_manifest
CapitalExperiment.input_hash
CapitalPolicyRun.metrics
```

A capital result is reproducible only for its original frozen stream.

### 4.5. PredictionExperiment handling

Do not delete a multi-match `PredictionExperiment` merely because one target was
cancelled.

After removing the cancelled match's Prediction/Decision rows:

```text
recompute experiment summary
→ counts/metrics based only on remaining valid rows
```

Record bounded hygiene metadata in the summary or equivalent audit boundary so the
removal is explainable.

If an experiment becomes empty, it may remain as a zero-valid-target audit container;
it must not retain stale performance metrics.

### 4.6. Cleanup order

Recommended transactional order:

```text
identify CANC Match
→ dry-run impact plan
→ affected Decision IDs
→ delete affected CapitalExperiments
→ delete Decisions
→ delete Predictions
→ delete OddsObservation / OddsSnapshot
→ recompute PredictionExperiment summaries
→ persist cleanup audit/result
```

Never rely on an implicit database cascade as the business rule.

### 4.7. Idempotency

Second cleanup of the same already-sanitized CANC fixture:

```text
NO_WORK / ALREADY_CLEAN
```

No error and no unrelated deletion.

---

## 5. Required safety controls

- dedicated service boundary;
- `dry_run=True` or equivalent;
- transaction;
- exact CANC eligibility guard;
- primary-source/canonical-state authority;
- per-model counts before delete;
- explicit list/count of capital experiments invalidated;
- no generic “delete all terminal no-outcome” query;
- no deletion of `PST`;
- no provider write;
- no bookmaker auth;
- no real betting;
- no mutation of unrelated matches;
- test with at least:
  - CANC;
  - PST;
  - valid FT;
  - repeated cleanup;
  - Decision protecting OddsObservation;
  - deterministic capital ledger;
  - stochastic capital experiment with no ledger but input manifest;
  - multi-match PredictionExperiment summary recomputation.

---

## 6. Falsification / stop conditions

The recommendation must be revisited if preflight proves any of the following:

1. the primary provider no longer uses `CANC` with the documented meaning;
2. Finsport maps `CANC` into a different canonical state;
3. a current foreign key not inspected here makes the proposed order unsafe;
4. a CapitalExperiment can depend on Decisions without exposing them in either ledger
   or input manifest;
5. another current subsystem treats deleting OddsObservation as an irreversible
   audit/provenance violation;
6. the repo has already introduced a dedicated tombstone/invalidation model after the
   referenced master commit.

---

## 7. Project consequence

This research supports:

```text
FS-005 finding
→ ABSORB into FS-006 post-match lifecycle
```

because cleanup is needed to keep:

```text
Capture
→ Prediction
→ Decision
→ Outcome
→ Evaluation
→ Capital
→ Report
```

internally consistent.

It does **not** justify a generic data-retention framework or broad historical cleanup.

---

## 8. Open questions intentionally left to F009 preflight

- exact package/class name of the cleanup service;
- exact migration needed for pipeline/cleanup audit;
- exact query strategy for `CapitalExperiment.input_manifest`;
- actual count of current CANC/PST fixtures in the local DB;
- exact competition set for multi-league UAT;
- exact scheduler wiring after FS-005 merge.

These are checkout/DB/runtime facts, not external research questions.
