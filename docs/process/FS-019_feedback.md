# FS-019 — Feedback final

**Ticket:** FS-019 — Global Decision Baseline
**Branch:** `fs019-global-decision-baseline`
**PR:** `#25 — FS-019 — Select global Decision baseline and cross-layer handoff`
**Estado técnico:** `CLOSED / ACCEPTED`
**Estado de feedback:** `FINAL`
**Fecha:** `2026-09-21`

---

## 1. Resultado del ticket

FS-019 quedó cerrado con una baseline Decision reproducible, auditable y utilizable por la siguiente capa experimental.

La autoridad local de Prediction permanece:

```text
GLOBAL_PREDICTION_V1
= MARKET_CONSENSUS / fs013-market-consensus-v2
```

La autoridad local de Decision seleccionada por FS-019 es:

```text
GLOBAL_DECISION_V1
= MODAL_ALL / fs003-modal-all-v1
```

La disposición científica del torneo Decision fue:

```text
UNSTABLE
```

El point leader observado dentro del torneo Decision fue:

```text
SELECTIVE_CONFIDENCE 0.60
GLOBAL_PPO = -0.011338702817383533
```

No se estableció superioridad simultánea y estable. Bajo la regla determinista E1.2, `MODAL_ALL` permaneció en el survivor set y fue seleccionado como baseline usable.

Este resultado no implica que `MODAL_ALL` sea económicamente rentable. En el corpus real de 1,906 oportunidades:

```text
MARKET_CONSENSUS + MODAL_ALL

GLOBAL_PPO
= -0.032469827811544304

P&L
= -56.028u
```

Su función es actuar como baseline Decision conservadora, determinista y reproducible para continuar el programa experimental.

---

## 2. Handoff durable de Decision

FS-019 publica una autoridad durable y exactamente un selected Decision stream:

```text
docs/research/FS-019_global_decision_v1.json

docs/research/FS-019_decision_baseline_evidence/
  eb5ab6585b5dd36a/
    selection-summary.json
    selected-decision-stream.jsonl.gz
    SHA256SUMS
```

Selected stream:

```text
rows
= 1,906

semantic SHA-256
= 5ee79477d0e9c6709f0530b0971a853205780966bc5c8c40eabac148ef963391

gzip SHA-256
= 52f3a850e6c9781d26021878698199b54c014eb368e7262e1aec55f777ffd7cc

size
= 314,106 bytes
```

El resolver downstream falla cerrado y verifica autoridad, lineage, cohort, path, row count, semantic hash, gzip hash y semántica Decision antes de exponer el stream.

---

## 3. Corpus e identidad experimental

El freeze real de FS-019 produjo:

```text
Decision rows
= 1,906

competitions
= 10

Competition × Lima ISO-week blocks
= 229

snapshot semantic SHA-256
= d17f693ec576dc926ebe7ef3e22b242930e226c09e2038e5f0d27b9ed1988e86

decision_common_cohort_hash
= c5a716c6940c135fd59c2b313faedf42b5957184e4bcc8aad67657b46924870b
```

Run real:

```text
run_id
= eb5ab6585b5dd36a94f4727003ebf7315badd0dab87bd871b0250b3e29ab321a

execution_id
= fa23c8f1939dbb8ef0f5aeb2333ccdbb4e5950bef4caed97aa0c89f9b4b52441

spec_id
= 6885728b3a5c5f84b3f413ed57f0fcfb4fb69625bd2578fef9bcd66121a0bf7e

decision_rows_hash
= 25dcb9139315fd991f15f5a9c84d892f6a9dac5a3b3322aca16d0fae11da9eef
```

La promoción fue repetida y resultó idempotente.

---

## 4. Cross-layer addendum

Durante el cierre de FS-019 se comprobó que seleccionar cada capa de manera aislada no garantiza encontrar la mejor combinación económica integrada.

Se congeló y evaluó una matriz de:

```text
4 Prediction families
×
Decision policies elegibles
=
33 Prediction × Decision combinations
```

Prediction:

```text
DIXON_COLES
INDEPENDENT_POISSON
ELO_MULTINOMIAL_LOGIT
MARKET_CONSENSUS
```

Decision universal:

```text
MODAL_ALL
SELECTIVE_CONFIDENCE 0.40
SELECTIVE_CONFIDENCE 0.45
SELECTIVE_CONFIDENCE 0.50
SELECTIVE_CONFIDENCE 0.55
SELECTIVE_CONFIDENCE 0.60
```

VALUE adicional para Predictions independientes del mercado:

```text
VALUE 0.00
VALUE 0.02
VALUE 0.05
```

`MARKET_CONSENSUS × CURRENT VALUE` permanece ineligible bajo el contrato actual por circularidad económica.

El primary cross-layer cohort fue:

```text
paired/common Matches
= 1,877

competitions
= 10

blocks
= 229

price profile
= ODDSPAPI_RECONSTRUCTED_T30_V1
```

---

## 5. Cross-layer point leader

El point leader observado fue:

```text
DIXON_COLES / fs011-dixon-coles-v2
+
VALUE 0.05
```

Resultado observado:

```text
GLOBAL_PPO
= +0.009653719670368769

BET
= 1,518

NO_BET
= 359

pooled P&L
= +38.584u

yield per BET
= +2.5417654808959158%

hit rate
= 30.10540184453228%
```

Fue la única combinación del screen de 33 candidatos con `GLOBAL_PPO` positivo.

Sin embargo, el confirmatorio no estableció superioridad:

```text
q95
= 0.0884080380133749

minimum simultaneous lower bound
= -0.07704257802975936

lower bound vs current integrated control
= -0.04927320613106208

scientific disposition
= UNSTABLE

survivors
= 33 / 33
```

También existieron deltas de estabilidad negativos.

Por tanto:

```text
CROSS_LAYER_POINT_LEADER_V1
= DIXON_COLES + VALUE 0.05

status
= OBSERVED_TOP / UNSTABLE / NOT PROVEN SUPERIOR
```

El control integrado conservador permanece:

```text
MARKET_CONSENSUS + MODAL_ALL
```

No se declara rentabilidad demostrada ni superioridad estadística para `DIXON_COLES + VALUE 0.05`.

---

## 6. Cambio durable del programa experimental

FS-019 deja congelada una nueva regla metodológica para las fases posteriores.

Cada fase conserva dos estudios complementarios:

### Layer-local / sequential

La nueva capa se evalúa sobre la autoridad secuencial previamente congelada.

Esto preserva atribución y permite diagnosticar la contribución específica de Prediction, Decision, Capital o una capa posterior.

### Cumulative cross-layer

Todas las alternativas elegibles de las capas ya abiertas se combinan nuevamente.

```text
Prediction
→ Prediction tournament

Decision
→ Prediction × Decision tournament

Capital
→ Prediction × Decision × Capital tournament

future layer N
→ cumulative Layer1 × Layer2 × ... × LayerN tournament
```

Las autoridades locales continúan siendo resultados científicos válidos y auditables.

La autoridad integrada y el point leader cross-layer se conservan separadamente cuando la inferencia no demuestra una superioridad estable.

---

## 7. Contrato entregado a Capital

La siguiente capa experimental recibe como evidencia estable:

```text
GLOBAL_PREDICTION_V1
= MARKET_CONSENSUS

GLOBAL_DECISION_V1
= MODAL_ALL

SEQUENTIAL / INTEGRATED CONTROL
= MARKET_CONSENSUS + MODAL_ALL

CROSS_LAYER_POINT_LEADER_V1
= DIXON_COLES + VALUE 0.05
status = UNSTABLE / NOT PROVEN SUPERIOR

FROZEN CROSS-LAYER MATRIX
= 33 eligible Prediction × Decision combinations
```

El contrato de la capa Capital queda definido en dos vistas:

```text
Capital-local:
sequential Prediction × Decision control
× eligible Capital configurations

Cumulative:
eligible Prediction
× eligible Decision
× eligible Capital
```

Los outputs conceptuales quedan separados:

```text
GLOBAL_CAPITAL_V1
= resultado local de Capital condicionado al control secuencial

GLOBAL_STRATEGY_V1
= resultado integrado acumulativo Prediction × Decision × Capital
```

No se presupone que la concatenación de los ganadores locales sea la mejor estrategia integrada.

---

## 8. Larger-universe robustness

Se ejecutó además un diagnóstico histórico separado usando `HistoricalMarketEvidence`.

Corpus disponible:

```text
rows
= 2,422

BET365_CLOSING
= 2,306

PINNACLE_CLOSING
= 116

time_semantics
= ASSUMED_T30M for all rows
```

Esta evidencia permanece clasificada como historical/research.

No se representa como evidencia prospectiva ni como `ODDSPAPI_RECONSTRUCTED_T30_V1`.

El primary election cross-layer sigue ligado al cohort paired/common de 1,877 Matches.

---

## 9. Integridad upstream FS-018

FS-019 verifica la autoridad FS-018 y su lineage antes del freeze.

Se verifican:

```text
GLOBAL_PREDICTION_V1 authority
run identity
spec identity
manifest identity
prediction cohort identity
data cutoff
source acquisition identity
execution runtime identity
backfill lineage
authoritative Market evidence
```

El review del PR identificó además que el derived view `per_match.jsonl.gz` debía autenticarse explícitamente y no sólo asumirse válido por existir.

El finding fue aceptado y resuelto.

La corrección final:

```text
verified FS-018 run
→ regenerate deterministic per_match rows
→ deterministic gzip
→ exact comparison against retained per_match.jsonl.gz
→ mismatch fails closed with UPSTREAM_PER_MATCH_VIEW_MISMATCH
```

Esto cierra la posibilidad de modificar campos derivados como `competition_id` conservando únicamente aggregate league counts.

Se añadió cobertura específica que prueba que una alteración del derived per-match view falla cerrada.

El freeze real conserva las mismas identidades de snapshot y cohort, por lo que el resultado científico de FS-019 no cambia.

---

## 10. PR review

PR:

```text
#25
FS-019 — Select global Decision baseline and cross-layer handoff
```

Review sustantivo recibido:

```text
P2 — Verify the derived per-match view before freezing it
```

Resolución:

```text
ACCEPTED
+
FIXED
+
REGRESSION COVERAGE ADDED
```

El finding no requirió cambio de metodología, candidate matrix, prices, bootstrap, stability, fallback ni resultado experimental.

Fue una mejora de integridad/fail-closed del boundary upstream.

No quedan findings sustantivos conocidos de implementación, evidencia o review sin resolver.

---

## 11. Validación

La implementación FS-019 fue validada mediante:

```text
focused FS-019 tests
= PASS

affected/regression matrix
= PASS

full suite
= PASS

Black
= PASS

Ruff
= PASS

Django system check
= PASS

migration check
= no changes

pip check
= PASS

pip-audit
= PASS

git diff --check
= PASS
```

La validación original del ticket alcanzó:

```text
full suite
= 805 passed

coverage
= 85.01%
```

La corrección final del review añadió un test de regresión dirigido al derived per-match integrity boundary.

El cambio final no altera las entradas congeladas ni el resultado de elección; fortalece exclusivamente la verificación upstream antes del freeze.

---

## 12. Safety y límites operacionales

FS-019 cerró respetando:

```text
real bets
= 0

provider calls during UAT
= 0

external FS-019 network calls
= 0

CapitalRuntimeConfig mutations
= 0

Capital automatic routing changes
= 0

pipeline/capture/prediction routing changes
= 0

database migrations
= 0
```

No se conectó la nueva baseline Decision al placement automático actual.

R45 e Inkabet automáticos permanecen fuera de este ticket.

---

## 13. Retención y packaging

Los artifacts compactos y downstream-authoritative permanecen en el repositorio.

Los artifacts grandes de investigación cross-ticket pueden permanecer fuera del repo bajo:

```text
/home/ljarufe/Documents/finsport/research-evidence/
```

con:

```text
SHA-256
+
RETENTION_INDEX.tsv
```

El ticket consumidor los restaura a su workspace `tmp/`, verifica identidad y los incorpora a su propio lineage.

FS-018 multi-model evidence permanece:

```text
PRESERVE_ACTIVE
```

porque la evaluación acumulativa Prediction × Decision × Capital necesita alternativas de Prediction que no están contenidas en el único selected Prediction stream.

La condición de borrado queda ligada a que la fase acumulativa de Capital haya absorbido de forma durable la evidencia requerida y ya no exista dependencia downstream directa.

Esta regla evita introducir bundles grandes innecesarios en Git sin perder reproducibilidad cross-ticket.

---

## 14. Artifacts durables

FS-019 deja como artifacts principales:

```text
docs/research/FS-019_global_decision_methodology_research.md

docs/research/FS-019_global_decision_baseline_report.md

docs/research/FS-019_global_decision_v1.json

docs/research/FS-019_cross_layer_selection_addendum.md

docs/research/FS-019_cross_layer_confirm_v1.json

docs/research/FS-019_decision_baseline_evidence/
  eb5ab6585b5dd36a/
    selection-summary.json
    selected-decision-stream.jsonl.gz
    SHA256SUMS

docs/process/FS-019_feedback.md
```

Los temporary experiment workspaces y artifacts grandes no necesarios para consumo directo no forman parte del contrato runtime.

---

## 15. Findings de proceso

FS-019 produjo dos aprendizajes durables.

### 15.1. Baseline por capa y baseline integrada deben coexistir

La elección secuencial es útil para diagnóstico, pero no debe asumirse como óptimo global.

El programa experimental debe mantener:

```text
layer-local authority
+
cumulative cross-layer tournament
```

a medida que se abren nuevas capas.

### 15.2. Derived research views usados como input deben estar autenticados

No basta verificar el artifact raíz si una elección downstream consume un view derivado que contiene campos científicamente relevantes.

Cuando el view pueda regenerarse de una autoridad ya verificada:

```text
verified root artifact
→ deterministic regeneration
→ exact/hash binding of derived view
→ downstream freeze
```

es preferible a confiar sólo en existencia, aggregate counts o validaciones parciales.

---

## 16. Source-update recommendations

La siguiente reconciliación de fuentes permanentes debe conservar estas reglas durables:

```text
F001 / F006 / F010:
- selección acumulativa por capas;
- coexistencia de autoridades locales y combinación integrada;
- paired/common cohort como base de elección directa;
- natural/larger universes como robustness;
- multiplicity-aware inference al crecer la matriz combinatoria;
- GLOBAL_CAPITAL_V1 separado de GLOBAL_STRATEGY_V1.

F009:
- verificar/bindear derived research views cuando contienen campos que afectan la elección;
- mantener artifacts grandes cross-ticket fuera del repo cuando exista un contrato de hash + retention + restore.
```

Estas recomendaciones reflejan reglas generales aprendidas en FS-019, no detalles accidentales del ticket.

---

## 17. Cierre

FS-019 queda aceptado como cierre de la capa Decision y como primer handoff acumulativo Prediction × Decision.

Estado final:

```text
implementation
= ACCEPTED

Decision UAT
= ACCEPTED

cross-layer experiment
= COMPLETED

cross-layer confirmatory
= COMPLETED

PR substantive finding
= RESOLVED

durable handoff
= PUBLISHED

known unresolved substantive findings
= NONE
```

No quedan acciones técnicas abiertas dentro del scope de FS-019.

El resultado durable conserva simultáneamente:

```text
local Prediction authority
+
local Decision authority
+
sequential integrated control
+
cross-layer observed point leader
+
frozen 33-candidate Prediction × Decision matrix
```

como base reproducible y auditable para la siguiente capa experimental.
