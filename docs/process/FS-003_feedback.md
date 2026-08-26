# FS-003 — Feedback final de implementación

**Ticket:** `FS-003 — Construir baseline predictivo multi-modelo y evaluar HOME/DRAW/AWAY/NO_BET`
**Branch de ejecución:** `FS-003-predictive-baseline`
**Base:** `master`
**Producto:** `local-only / demo-only / research-oriented`
**Estado final:** `PASS — implementación, UAT, CI y review completados`
**Fecha:** `2026-08-26`

---

## 1. Outcome final

FS-003 convirtió el core canónico de fútbol construido en FS-002 en un pipeline predictivo reproducible, auditable y leakage-safe que separa explícitamente:

```text
Prediction
→ P(HOME), P(DRAW), P(AWAY)

Decision
→ HOME / DRAW / AWAY / NO_BET
```

Invariantes finales:

```text
Prediction != Decision
NO_BET != NO_PREDICTION
DRAW es outcome válido
DRAW es acción válida
real betting sigue fuera del runtime
```

El ticket no tenía como criterio demostrar rentabilidad, hacer que Dixon-Coles ganara ni elegir un threshold productivo definitivo. El objetivo era producir evidencia reproducible y representar honestamente tanto resultados positivos como indisponibilidades o hipótesis sin señal.

Resultado global:

```text
implementation              PASS
automated gates             PASS
persistent migration        PASS
temporal odds UAT           PASS
historical evaluator UAT    PASS
prospective UAT             PASS
R45 UAT                     PASS
Django Admin UAT            PASS
GitHub CI                   PASS
GitHub review               PASS
financial side effects      NONE
```

---

## 2. Dependencias y library-first

Pins directos añadidos:

```text
penaltyblog==1.12.0
scikit-learn==1.9.0
```

Se reutilizó matemática madura en lugar de reimplementarla:

| Capability | Implementación |
| --- | --- |
| Dixon-Coles | `penaltyblog.models.DixonColesGoalModel` |
| Independent Poisson | `penaltyblog.models.PoissonGoalsModel` |
| Time decay | `penaltyblog.models.dixon_coles_weights` |
| Elo | `penaltyblog.ratings.Elo` |
| De-vig multiplicativo | `penaltyblog.implied.calculate_implied` |
| Multinomial/binary logit | `sklearn.linear_model.LogisticRegression` |
| Scaling | `sklearn.preprocessing.StandardScaler` |
| Métricas base | sklearn + agregaciones pequeñas Finsport |

No se añadieron NumPy/SciPy/Pandas como dependencias directas por conveniencia y no se reimplementaron optimizadores, Elo, de-vig ni regresión logística.

### Warning conocido

`penaltyblog==1.12.0` emite `DeprecationWarning` con NumPy 2.5 al asignar `score_matrix.shape` en Dixon-Coles/Poisson.

Disposición:

```text
DEFER
```

No produce failures ni rompe assertions.

No:

- parchear `penaltyblog`;
- sustituir mature-library math;
- pinnear transitivas sólo para silenciar warnings.

Reevaluar en un ticket futuro de mantenimiento/dependencias.

---

## 3. Modelos, policies y versiones

Brazos experimentales:

```text
DIXON_COLES
INDEPENDENT_POISSON
ELO_MULTINOMIAL_LOGIT
MARKET_CONSENSUS
LEGACY_R45
MODERNIZED_R45
```

Policies:

```text
MODAL_ALL
SELECTIVE_CONFIDENCE
VALUE
LEGACY_R45
```

Versiones:

```text
engine
→ fs003-v1

Dixon-Coles
→ fs003-dixon-coles-v1

Independent Poisson
→ fs003-independent-poisson-v1

Elo multinomial
→ fs003-elo-multinomial-logit-v1

Market consensus
→ fs003-market-consensus-v1

Modernized R45
→ fs003-modernized-r45-v1

Legacy R45 exact
→ R45-refund-stop@ef861a4897e4bfdff938e8541e8185f731ddaa5c
```

Grids/config principales:

```text
Dixon-Coles xi
→ 0.0, 0.001, 0.002

Elo K
→ 10, 20, 40

Logistic C
→ 0.1, 1.0, 10.0

Modernized R45 prior strength
→ 10, 20, 40

Selective confidence
→ 0.40, 0.45, 0.50, 0.55, 0.60

Minimum EV
→ 0.00, 0.02, 0.05
```

Los thresholds de confidence/EV son variantes de evaluación, no policy productiva congelada.

---

## 4. Schema y persistencia

Migración aditiva:

```text
football.0002
```

Añade:

### `OddsObservation`

Historial temporal append-only de odds.

Identidad:

```text
Match
+ Source
+ Bookmaker
+ Market
+ observed_at
```

Conserva:

```text
HOME
DRAW
AWAY
provider_updated_at
observed_at
```

### `PredictionExperiment`

Persiste:

- Competition;
- BACKTEST / PROSPECTIVE;
- período;
- engine version;
- config;
- summary;
- completion timestamp.

### `Prediction`

Persiste:

- experiment;
- match;
- model code / variant / version;
- cutoff;
- `p_home`;
- `p_draw`;
- `p_away`;
- predicted outcome;
- diagnostics;
- actual outcome cuando se evalúa.

### `Decision`

Persiste:

- experiment;
- match;
- Prediction nullable;
- policy/version/config;
- decision time;
- HOME/DRAW/AWAY/NO_BET;
- reason;
- model probability;
- selected `OddsObservation`;
- selected price;
- expected value.

`Prediction` nullable es necesario para `LEGACY_R45`, que no produce un vector H/D/A legítimo.

`OddsSnapshot` permanece como proyección latest/current.

No hubo backfill artificial de `OddsObservation` desde `OddsSnapshot`.

---

## 5. Odds temporales

El boundary de sync existente conserva simultáneamente:

```text
OddsSnapshot
→ latest/current projection

OddsObservation
→ temporal append-only history
```

Una quote ya recibida por provider crea la Observation sin una llamada adicional.

Semántica demostrada:

- una captura nueva puede coexistir con otra anterior;
- incluso precios iguales pueden quedar en timestamps distintos;
- mismo logical quote dentro del mismo batch/timestamp se deduplica;
- `OddsSnapshot` sigue siendo una sola fila latest por identidad;
- no se reconstruye historia inexistente.

---

## 6. Contrato temporal y anti-leakage

### Backtest

Unidad temporal:

```text
America/Lima
```

Para fecha local `D`:

```text
TRAIN
→ sólo resultados de días locales < D

PREDICT
→ todo el batch de D con estado congelado

REVEAL / UPDATE
→ después de emitir/persistir el batch
```

No entran:

- target;
- fixtures futuros;
- resultados del mismo día;
- non-FT;
- AET/PEN/AWD/WO.

### Prospective

Un único cutoff se captura al iniciar el comando.

Training history requiere simultáneamente:

```text
match.kickoff < cutoff
AND
local_day(match.kickoff) < target_day
```

Odds:

```text
OddsObservation.observed_at < cutoff
```

`OddsSnapshot` no actúa como history.

### Cutoff CLI

`predict_football_day --cutoff` exige ahora un ISO datetime timezone-aware.

Un cutoff naive se rechaza explícitamente.

Esto evita que una frontera anti-leakage dependa de timezone implícita.

---

## 7. Dataset sintético / correctness

El harness sintético cubre:

- League doméstica;
- 3 Seasons;
- 8 equipos;
- nuevos/cold-start;
- HOME/DRAW/AWAY;
- low scores;
- múltiples bookmakers;
- múltiples timestamps;
- quotes idénticas en tiempos distintos;
- invalid market tuples;
- post-cutoff observations;
- best H/D/A en distintos books;
- DRAW value no modal;
- NO_BET;
- overround variable.

El dataset sintético prueba correctness/integration.

No se usa como evidencia de rendimiento real.

---

## 8. UAT de migración y no-backfill

PostgreSQL persistente:

```text
football
 [X] 0001_initial
 [X] 0002_oddsobservation_predictionexperiment_prediction_and_more
```

Evidencia observada inmediatamente después:

```text
ODDS_SNAPSHOTS=15
ODDS_OBSERVATIONS=0
```

Conclusión:

- las 15 snapshots previas se preservaron;
- la migración no fabricó ninguna Observation histórica.

PASS.

---

## 9. UAT real de odds temporales

Antes del primer sync post-migración:

```text
OddsSnapshot = 15
OddsObservation = 0
```

Después del primer sync:

```text
OddsSnapshot = 45
OddsObservation = 30
```

Después del segundo sync:

```text
OddsSnapshot = 45
OddsObservation = 59
```

Conclusiones:

1. history append-only funciona;
2. current/latest projection queda estable;
3. la segunda captura añadió Observations aunque muchas quotes quedaron `unchanged`;
4. precios idénticos en un momento posterior pueden conservar nueva evidencia temporal;
5. no hubo provider calls adicionales para crear history.

Durante el segundo sync:

```text
Inkabet request timed out
```

pero:

```text
error=none
```

La fuente secundaria falló fail-soft y el resto de la ingestión se preservó.

PASS.

---

## 10. Backtest real — La Liga 2024

Competition:

```text
1278 — La Liga
```

Inventario:

```text
2022
→ 380 FT

2023
→ 380 FT

2024
→ 380 FT

total
→ 1,140 FT
```

Outcome distribution total:

```text
HOME = 518
DRAW = 293
AWAY = 329
```

Split congelado:

```text
inner train
→ 2022

validation
→ 2023

outer test
→ 2024
```

Target outer:

```text
380 fixtures
```

### Hyperparameters elegidos

Dixon-Coles:

```text
xi = 0.0
validation log loss ≈ 0.9802318465
```

Independent Poisson:

```text
xi = 0.0
```

por selección compartida con Dixon-Coles.

Elo multinomial:

```text
K = 10
C = 0.1
validation log loss ≈ 0.9737307714
```

### Outer results

#### Independent Poisson

```text
n = 379
log loss ≈ 0.9715692555
Brier ≈ 0.5758445644
RPS ≈ 0.1955086485
accuracy ≈ 0.5356200528
```

#### Dixon-Coles

```text
n = 379
log loss ≈ 0.9717946926
Brier ≈ 0.5759849880
RPS ≈ 0.1955362388
accuracy ≈ 0.5356200528
```

#### Elo multinomial

```text
n = 380
log loss ≈ 0.9886192155
Brier ≈ 0.5849436354
RPS ≈ 0.1994383177
accuracy ≈ 0.5342105263
```

DC/Poisson producen 379, no 380, por:

```text
INSUFFICIENT_TEAM_HISTORY = 1
```

en cada brazo.

### Interpretación

- Independent Poisson fue marginalmente mejor en este outer season.
- Dixon-Coles quedó prácticamente empatado.
- `xi=0` indica que el decay probado no aportó en validation.
- Elo quedó ligeramente detrás en outer.
- No existe evidencia para declarar un ganador estadístico general con una sola temporada outer.

Resultado experimental válido:

```text
Poisson ≈ Dixon-Coles
```

La complejidad adicional de DC no demostró ventaja material en este piloto.

---

## 11. Hallazgo DRAW

Los tres modelos locales produjeron probabilidades DRAW válidas y evaluables, pero:

```text
modal DRAW predictions
→ 0
```

en el outer La Liga 2024.

Esto no es un bug.

DRAW puede:

- recibir probabilidad;
- participar en calibration/log loss/Brier;
- ser seleccionado por VALUE aunque no sea la clase modal.

No confundir:

```text
modal prediction
con
economic decision
```

---

## 12. Selectividad

`SELECTIVE_CONFIDENCE` mostró el comportamiento esperado:

```text
threshold ↑
→ coverage ↓
→ hit rate ↑
```

Ejemplo Dixon-Coles:

```text
MODAL_ALL
coverage = 100%
hit rate ≈ 53.56%

threshold 0.60
coverage ≈ 25.59%
hit rate ≈ 77.32%
```

Independent Poisson y Elo muestran el mismo patrón general.

Esto demuestra selectividad.

No demuestra rentabilidad.

---

## 13. Mercado histórico 2024

No existen `OddsObservation` legítimas de 2022–2024.

Por tanto:

```text
MARKET_CONSENSUS historical
→ UNAVAILABLE

MODERNIZED_R45 historical
→ UNAVAILABLE

VALUE historical
→ NO_BET / NO_VALID_MARKET
```

No se sustituyó history faltante con:

- `OddsSnapshot` actual;
- quotes futuras;
- datos sintéticos;
- precios reconstruidos.

No se calculó ROI histórico ficticio.

---

## 14. Legacy R45 histórico

Versión exacta:

```text
R45-refund-stop@ef861a4897e4bfdff938e8541e8185f731ddaa5c
```

Legacy no recibe probabilidades H/D/A falsas.

El evaluator registra indisponibilidad cuando falta replay exacto.

Razones históricas originalmente relevantes:

```text
MISSING_HISTORICAL_PREKICKOFF_R45_ODDS
MISSING_HISTORICAL_LEAGUE_DRAW_PERCENTAGE
```

El comparator sigue siendo evidencia histórica, no baseline productivo.

---

## 15. Backup legacy real de producción

Durante UAT se inspeccionó offline/read-only un backup real de la etapa histórica de Finsport.

El dump nunca:

- se restauró sobre la DB actual;
- se convirtió en fixture del repo;
- se importó a `OddsObservation`;
- se utilizó para habilitar live R45;
- se versionó.

### Inventory

```text
legacy Matches = 25,850
```

Todos tienen factores H/D/A válidos.

BetRows:

```text
total = 2,365

W = 690
L = 1,671
C = 4
```

Draw hit rate histórico de los BetRows resueltos:

```text
≈ 29.22%
```

Esta es evidencia de decisiones realmente seleccionadas por el sistema histórico.

No representa el universo de todos los candidatos contrafactuales.

### Provenance temporal

El código histórico sólo creaba/actualizaba los factores mientras:

```text
start_datetime > now
```

Por ello los factores almacenados son evidencia legacy pre-kickoff.

Pero no son una serie temporal exacta.

En el dump:

```text
2,485 Matches
```

fueron modificados después del kickoff.

### Exact Legacy replay

No es defendible.

Razones:

- factores de Match mutables;
- `League.draw_percentage` mutable;
- porcentaje de ProgressiveBetting actualizado in-place;
- sólo existe el valor final en el dump;
- `Match` no guardaba League FK;
- `Match.league` dependía de `local_team.league`;
- `Team.league` podía mutar por `update_or_create(name=...)`;
- existen mappings incompatibles entre local/visitor league.

Diagnóstico de reproducción de stored `Match.score` usando el estado final:

```text
528 / 25,850
```

reproducen bajo tolerancia estricta.

Conclusión:

```text
EXACT_LEGACY_COUNTERFACTUAL_REPLAY_UNAVAILABLE
```

No es un failure de FS-003.

---

## 16. Modernized R45 — probe offline real

Se ejecutó un probe usando exclusivamente el backup legacy como:

```text
LEGACY_BACKUP_OFFLINE_RESEARCH_ONLY
```

No se persistió en `PredictionExperiment`.

### M0

```text
n = 5,720
log loss ≈ 1.017064
Brier ≈ 0.608908
```

### M1

```text
n = 5,720
log loss ≈ 1.017185
Brier ≈ 0.608844
```

M1 añade la feature de parity:

```text
abs(pH_market - pA_market)
```

Resultado preliminar:

- M1 no mejora log loss;
- la mejora de Brier es minúscula;
- no aparece evidencia clara de señal incremental de parity en este dataset.

No generalizar este resultado a otras competitions/períodos.

### M2 / M3

```text
UNAVAILABLE
```

porque requieren contexto de Competition/Season estable y un `z3` rolling/shrunk leak-safe que el dump legacy no puede reconstruir.

### Live enablement

El backup NO habilita `MODERNIZED_R45` live porque carece de:

- identidad canónica estable;
- Season mapping fiable;
- temporal market provenance completa;
- contexto moderno leak-safe.

No usar legacy data para fingir disponibilidad prospectiva.

---

## 17. UAT prospectiva real

Fecha:

```text
2026-08-27
```

Fixtures La Liga:

```text
Celta Vigo vs Osasuna
Barcelona vs Athletic Club
```

Temporal market observations disponibles:

```text
match 1142
→ 30

match 1143
→ 29
```

Primera corrida prospectiva:

```text
predictions = 8
decisions = 66
```

Predictions:

```text
DIXON_COLES = 2
INDEPENDENT_POISSON = 2
ELO_MULTINOMIAL_LOGIT = 2
MARKET_CONSENSUS = 2
```

Todas las `MODAL_ALL` fueron HOME.

Las VALUE policies de los tres modelos locales eligieron AWAY para ambos fixtures/thresholds correspondientes.

Esto demuestra con datos reales:

```text
Prediction != Decision
```

y que un outcome no modal puede ser elegido por precio/EV.

---

## 18. Finding UAT — R45 omitido prospectivamente

La primera UAT prospectiva expuso que:

```text
MODERNIZED_R45
LEGACY_R45
```

no aparecían ni como produced ni como unavailable.

Era un finding material:

```text
required experimental arm
→ no puede desaparecer silenciosamente
```

### Corrección

`predict_day()` ahora representa explícitamente ambos brazos.

### UAT final R45

Experiment prospectivo corregido:

```text
predictions = 8
decisions = 68
```

#### Legacy R45

```text
status = UNAVAILABLE
reason = EXACT_LEGACY_CONTEXT_UNAVAILABLE
decision_count = 2
prediction_count = 0
```

Se persistieron dos Decisions:

```text
action = NO_BET
prediction = NULL
policy_version =
R45-refund-stop@ef861a4897e4bfdff938e8541e8185f731ddaa5c
```

No existen probabilidades Legacy falsas.

#### Modernized R45

```text
status = UNAVAILABLE
reason = INSUFFICIENT_HISTORICAL_MARKET_OBSERVATIONS
historical_temporal_market_matches = 0
```

No se fabrican Predictions.

PASS.

---

## 19. Django Admin UAT

Admin normal:

```text
http://localhost:8001/
```

Superficies auditables:

- `OddsObservation`;
- `PredictionExperiment`;
- `Prediction`;
- `Decision`.

Se verificaron:

- observations reales;
- experimentos BACKTEST/PROSPECTIVE;
- probabilities;
- cutoffs;
- model/policy/version;
- action/reason;
- selected odds/price;
- nullable Legacy Prediction;
- R45 arm summary.

### Finding Admin

Prediction y Decision inicialmente permitían filtrar por experiment mode, pero no por `PredictionExperiment` concreto.

Corrección localizada:

```text
Prediction Admin
→ filter by experiment

Decision Admin
→ filter by experiment
```

UAT final:

```text
PASS
```

No fue necesario probar CRUD; la UAT fue read-only/audit-oriented.

---

## 20. Findings corregidos

### A. Complete-diff review pre-UAT

Se encontraron tres findings materiales:

#### 1. Explicit/backdated cutoff leakage

El prospective service filtraba history por día local, pero un cutoff explícito pasado podía permitir un match posterior al cutoff.

Fix:

```text
history kickoff < cutoff
AND
local day < target day
```

#### 2. NO_BET reasons ausentes del summary

`Decision.reason` estaba persistido pero no agregado en policy metrics.

Fix:

```text
no_bet_reasons
→ distribución sólo de Decisions NO_BET
```

#### 3. Market coverage por book count ausente

Cada Prediction tenía `book_count`, pero el Experiment summary no agregaba esa cobertura.

Fix:

```text
book_count_distribution
```

para `MARKET_CONSENSUS`.

Los tres quedaron cubiertos por regresiones.

### B. UAT prospective

#### 4. R45 arms omitidos silenciosamente

Fix:

```text
required R45 arm
→ produced OR unavailable + reason
```

### C. UAT Admin

#### 5. Falta filtro por experiment concreto

Fix localizado en Admin.

### D. GitHub PR review

#### 6. `--cutoff` timezone-naive

El management command aceptaba un ISO datetime sin offset.

Fix:

```text
timezone-naive cutoff
→ CommandError
```

El cutoff explícito ahora debe incluir timezone offset.

### E. GitHub feedback artifact

El review también detectó que el feedback final no estaba versionado todavía.

Esto fue intencional durante ejecución para evitar commits documentales intermedios, pero el artefacto debe existir en el cierre durable.

Resolución:

```text
docs/process/FS-003_feedback.md
→ reconciliado una sola vez después de implementation + corrections + UAT + PR review
→ incluir en el último commit
```

No se requirió una pasada Codex exclusiva para wording.

---

## 21. Evidencia automatizada final

Durante implementación/correcciones:

```text
focused implementation
→ PASS

focused correction
→ PASS

focused R45/prospective
→ 18 passed

focused final PR-cutoff correction
→ 3 passed
```

General repository gate:

```text
make check
→ PASS
```

El gate anterior a la última corrección registró:

```text
128 tests passed
```

La corrección final de cutoff volvió a ejecutar el gate y permaneció verde.

Además:

```text
Django check
→ PASS

git diff --check
→ PASS

makemigrations --check --dry-run
→ PASS / No changes detected

GitHub Actions
→ GREEN

GitHub review
→ findings corregidos
→ final green
```

Warnings finales:

```text
penaltyblog / NumPy 2.5 DeprecationWarning
```

únicamente; no failures funcionales.

---

## 22. Acceptance final

Reconciliación final:

```text
PASS     28
PENDING   0
N/A       3
```

Los tres `N/A` corresponden a replay histórico que no puede producirse honestamente por ausencia de history temporal/contexto exacto:

- historical Market consensus;
- historical Modernized R45;
- exact historical Legacy R45 counterfactual replay.

Esto está permitido por el contrato del ticket y no se sustituyó con datos fabricados.

---

## 23. Financial / safety boundary

FS-003 no:

- autentica bookmakers;
- hace bet placement;
- ejecuta Selenium de apuestas;
- cambia bankroll;
- calcula stakes reales;
- implementa Martingale/recovery/Kelly;
- genera external financial writes.

Predictor/evaluator:

```text
DB-only
```

Los provider calls pertenecen al sync de datos existente, no a prediction/evaluation.

`BetTable` / `BetRow` legacy no fueron reactivados como runtime financiero.

---

## 24. Performance — deferred

El backtest real La Liga 2024 tuvo runtime perceptible.

Disposición:

```text
DEFER — profile before optimize
```

Antes de escalar a múltiples competitions medir:

- total runtime;
- runtime por modelo;
- runtime por daily batch;
- refit count;
- duración de refits;
- CPU;
- RAM;
- SQL query count/hotspots;
- trabajo redundante.

Comparar especialmente:

```text
Dixon-Coles / Poisson
vs
Elo
```

No prescribir caching, paralelismo o nuevo hardware antes del profiling.

---

## 25. Modernized R45 — siguiente condición

El brazo existe y es falsable.

Todavía no está live-operational porque la DB canónica no contiene history temporal resuelta suficiente para entrenarlo/configurarlo prospectivamente.

Para habilitarlo en trabajo futuro se necesita:

```text
canonical Competition/Season identity
+
timestamped market observations
+
resolved outcomes
+
leak-safe chronological training
+
config selection frozen before targets
```

No usar:

- legacy dump;
- final legacy draw percentages;
- OddsSnapshot retrospectivo;
- synthetic data;

para saltarse esa condición.

### Finding futuro de arquitectura

La implementación actual representa bien el estado unavailable, pero el camino operacional de selección/congelación prospectiva de Modernized R45 cuando exista history suficiente debe diseñarse explícitamente en trabajo posterior.

No reabrir FS-003 por ello.

---

## 26. Learnings de producto / research

### 26.1. Complejidad no equivale a performance

El piloto real produjo:

```text
Poisson ≈ Dixon-Coles
```

con Poisson marginalmente mejor.

DC no recibe preferencia automática por ser más sofisticado.

### 26.2. Decay no demostró valor en este piloto

El `xi` elegido fue:

```text
0.0
```

No generalizar; conservarlo como resultado del fold evaluado.

### 26.3. DRAW no necesita ser modal para ser relevante

Ningún modelo local tuvo DRAW modal en el outer test, pero DRAW sigue siendo:

- probability válida;
- objeto de calibration;
- posible VALUE action.

### 26.4. Forecast y economic decision deben seguir separados

La UAT prospectiva mostró:

```text
modal = HOME
value action = AWAY
```

en los fixtures reales observados.

Esta separación debe mantenerse durablemente.

### 26.5. Temporal odds provenance es requisito duro

Sin precio contemporáneo válido:

```text
no historical ROI claim
```

### 26.6. Legacy real no equivale a replay exacto

Los BetRows prueban decisiones históricas realmente realizadas.

No prueban qué habría seleccionado el algoritmo entre todos los candidatos bajo un estado contrafactual reconstruido.

### 26.7. Parity legacy no mostró señal incremental clara

M0 vs M1 en el backup real:

```text
log loss
M0 < M1

Brier
diferencia mínima
```

La parity feature debe permanecer falsable, no convertirse en regla.

### 26.8. Resultado experimental negativo es success

FS-003 está diseñado para aceptar:

```text
market > model
Poisson ≈ DC
R45 adds no signal
```

si la evidencia es reproducible.

---

## 27. New Work Discovered / deferred

### A. Predictive pipeline profiling

Antes de escalar volumen.

### B. Modernized R45 prospective enablement

Sólo cuando exista history temporal canónica suficiente.

### C. Odds sync cadence / quota allocation

Ahora que cada sync acumula observations, la cadence determina directamente la calidad del futuro dataset de mercado.

Investigar:

- discovery;
- pre-kickoff refresh windows;
- result refresh;
- quota reserve;
- useful decision cutoffs.

No crear scheduler antes de definir cadence/quota/observability.

### D. Market timing

T-60 / T-30 / T-15 / etc. sólo cuando exista sample temporal suficiente.

### E. Bookmaker quality / weighting

No hardcodear sharp/recreational taxonomy.

Medir con history propia.

### F. Legacy dump canonical reconciliation

Sólo si una pregunta futura justifica mapear fixtures históricos legacy contra un catálogo canónico externo.

No importar raw legacy state al core actual.

### G. Dependency warning

Revisar penaltyblog/NumPy en mantenimiento futuro.

### H. Capital / loss-recovery

FS-003 ya entrega el primer checkpoint de forecast/selectivity.

Sin embargo todavía no existe suficiente evidence económica temporal para congelar parámetros de bankroll/recovery específicos de Finsport.

El siguiente trabajo puede investigar matemáticamente y diseñar simulaciones, pero debe distinguir:

```text
lo que FS-003 ya demuestra
vs
lo que requiere más shadow market history
```

No reintroducir betting real.

---

## 28. Aprendizajes de proceso

### 28.1. Acceptance ledger debe ser obligatorio en tickets multi-boundary

La versión activa de F009 perdió una regla útil ya demostrada en iteraciones anteriores.

Restaurar:

```text
tmp/<TICKET-ID>_acceptance_ledger.md
```

Para un ticket multi-boundary:

```text
PENDING
→ bloquea technical close
```

Formato:

- un solo archivo;
- overwrite;
- untracked;
- efímero.

### 28.2. Complete diff review debe incluir untracked

Restaurar:

```text
tmp/<TICKET-ID>_diff_review.txt
```

Debe representar:

```text
tracked diff
+
relevant untracked as /dev/null → file
```

No stagear archivos sólo para poder revisarlos.

Un archivo único, overwrite, nunca `v2/final`.

### 28.3. Tmp no pertenece al repo

Los artefactos técnicos de revisión/UAT viven en `tmp/`.

No pedir a Codex que los documente para el repositorio.

### 28.4. Feedback final se reconcilia una sola vez

Patrón confirmado:

```text
implementation
→ corrections
→ UAT
→ PR review
→ final feedback once
```

No crear passes Codex/docs-only para mantener feedback intermedio.

### 28.5. Findings pequeños pueden resolverse directamente

Los findings inequívocos de Admin y PR se corrigieron localmente sin otra pasada de Codex.

Después:

```text
rerun only invalidated evidence
```

más gate general cuando el delta de Python de producción lo justificó.

### 28.6. No repetir comandos caros para recuperar output

El backtest ya había persistido el Experiment aunque el terminal perdiera scrollback.

Patrón recomendado:

```text
resultado persistido
→ extraer desde DB
```

o para comandos futuros:

```text
command 2>&1 | tee tmp/<artifact>.txt
```

No repetir un backtest costoso sólo por evidencia textual.

### 28.7. Historical backup necesita provenance classification antes de uso

Antes de convertir un dump antiguo en dataset:

```text
inspect schema
→ inspect mutability
→ inspect timestamp semantics
→ inspect identity stability
→ classify what it can/cannot prove
```

No usar “muchos datos” como sustituto de provenance.

### 28.8. Experimental arms no pueden desaparecer silenciosamente

Contrato reusable:

```text
required experimental arm
→ PRODUCED
or
→ UNAVAILABLE + explicit reason
```

Esto debe proyectarse a F008/F009.

---

## 29. Fuentes que debe reconciliar el chat principal

### F000 — catálogo / bootstrap

- registrar los nuevos durable artifacts de FS-003;
- mantener research reports como `REFERENCE ONLY`;
- actualizar versiones sólo cuando se promuevan cambios durables.

### F001 — producto

Conservar/promover durablemente:

```text
Prediction != Decision
NO_BET != NO_PREDICTION
DRAW válido
research → hypothesis → experiment → keep/refine/discard
```

FS-003 demuestra estos contratos end-to-end.

### F002 — dominio / seguridad

Actualizar:

- temporal provenance de market data ya demostrado;
- `Prediction` y `Decision` como conceptos separados;
- `Decision` puede tener Prediction nullable sólo en comparators no probabilísticos como Legacy;
- `DRAW` como acción válida;
- no historical ROI sin timestamp-valid price;
- legacy dump como sensitive/research-only;
- BetRows históricos = executed selections, no candidate population;
- unavailable data nunca debe inventarse.

F002 puede reevaluar su madurez porque FS-003 ya demostró varias fronteras que estaban pendientes.

### F003 — arquitectura

Actualizar arquitectura real:

- `OddsObservation`;
- `PredictionExperiment`;
- `Prediction`;
- `Decision`;
- `football/prediction/*`;
- evaluator y prospective service;
- DC/IP/Elo/Market/R45 adapters;
- model/policy versioning;
- strict as-of market queries;
- append-only odds history;
- `penaltyblog` / sklearn pins;
- management commands reales;
- explicit R45 unavailable accounting;
- Admin experiment filtering.

Lo que antes era direction futura de temporal odds ya es arquitectura implementada.

### F004 — operación

Registrar:

```text
evaluate_football_predictions
predict_football_day
```

`--cutoff` debe incluir timezone offset.

Outputs largos/costosos:

```text
tee tmp/...
```

o inspección de persistence antes de rerun.

Admin normal:

```text
http://localhost:8001/
```

Legacy dump/probes:

- private;
- ephemeral;
- never restore into normal DB;
- never stage.

### F006 — roadmap/backlog

Marcar:

```text
FS-003
→ COMPLETED
```

El candidato:

```text
Capital / loss-recovery / bankroll research
```

ya no está “waiting for any FS-003 evidence”, pero debe reevaluarse con la calidad real de evidence disponible.

Reconciliar además, sin crear tickets automáticamente:

- predictive profiling;
- Modernized R45 enablement;
- quota/cadence;
- market timing;
- bookmaker weighting;
- legacy reconciliation;
- dependency warning.

### F007 — Planka

Registrar otra ejecución end-to-end:

```text
Ready
→ In Progress
→ Review
→ Done
```

Planka continúa externo al repo.

No polling.

### F008 — ticket definition / sequencing

Añadir learning reusable:

```text
experimental arm
→ must end PRODUCED or UNAVAILABLE + reason
```

Además:

```text
historical research dataset
→ provenance/canonicality gate before it can enable live behavior
```

Y:

```text
expensive UAT
→ plan evidence persistence before execution
```

### F009 — execution / tracking

Restaurar prioritariamente:

```text
tmp/<TICKET-ID>_acceptance_ledger.md
tmp/<TICKET-ID>_diff_review.txt
```

con sus reglas originales:

- required when applicable;
- overwrite;
- one file;
- untracked;
- `/dev/null → new file` for relevant untracked;
- PENDING blocks technical close;
- post-correction review only correction delta + invalidated evidence.

Mantener:

- no docs-only Codex pass;
- final feedback once;
- small Git commands;
- no status/diff/show spam;
- no polling;
- no ceremonial post-merge suites.

---

## 30. Artefactos durables

Debe quedar versionado:

```text
docs/research/FS-003_predictive_strategy_research.md
docs/research/FS-003_legacy_draw_research.md
docs/process/FS-003_feedback.md
```

Research:

```text
REFERENCE ONLY
```

Feedback:

```text
durable execution evidence / handoff source
```

No versionar:

```text
tmp/FS-003_*
legacy production dump
probe scripts/results
acceptance ledger
diff review
UAT terminal captures
```

---

## 31. Final disposition

FS-003 queda aceptado.

```text
research references          PASS
library-first                PASS
dependency pins              PASS
schema/migration             PASS
OddsSnapshot preservation    PASS
OddsObservation append       PASS
DC/IP/Elo predictions        PASS
market consensus             PASS
Legacy R45 fidelity          PASS
Modernized R45 falsifiable   PASS
anti-leakage                 PASS
prediction metrics           PASS
policy metrics               PASS
DRAW semantics               PASS
timestamp-valid economics    PASS
audit persistence            PASS
Django Admin                 PASS
focused tests                PASS
make check                   PASS
git diff check               PASS
migration drift              PASS
persistent migration UAT     PASS
real odds-history UAT        PASS
La Liga backtest UAT         PASS
prospective UAT              PASS
R45 UAT                      PASS
Admin UAT                    PASS
GitHub Actions               PASS
GitHub review                PASS
financial side effects       NONE
```

Acceptance reconciliation:

```text
PASS     28
PENDING   0
N/A       3
```

No repetir UAT ni suite completa post-merge por ceremonia.

Cierre esperado:

```text
commit final feedback/review fix
→ push
→ final CI/review green
→ Squash and merge
→ sync master
→ delete branch
→ remove tmp/FS-003*
→ Planka Review → Done
→ handoff al chat principal
```

El siguiente owner es el chat principal, que debe reconciliar F000–F009 y decidir el siguiente incremento a partir de esta evidencia, sin convertir automáticamente findings/deferred work en tickets.
