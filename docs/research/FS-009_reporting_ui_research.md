FS-009 — Reporting UI research
Status: REFERENCE ONLY
Project: Finsport
Date: 2026-08-31
Brief: PRE-FS-009
Product mode: local-only / demo-only / research-oriented
Financial side effects: none

# 1. Executive summary

FS-009 should add a small, server-rendered Django reporting surface for one human operator. Its job is not to evaluate Finsport scientifically, select winners, change model/policy behavior, or automate capital-policy comparison. Its job is to make the evidence that already exists understandable, comparable within valid boundaries, and explicit when something cannot yet be evaluated.

The minimum product should therefore have two reporting surfaces:

1. `/` — historical evidence summary, with three clearly separate sections:
   - Modelos predictivos;
   - Políticas de decisión / selección;
   - Políticas de capital.
2. `/daily/` — secondary day-by-day view, with league filtering and native expandable match detail.

FS-009 should also move Django Admin from `/` to `/admin/`. Admin remains the detailed audit/object-inspection surface; its internal functionality is not redesigned. Operational incident diagnosis remains outside the reporting UI at `http://localhost:3000/` in Grafana, backed by Loki, Alloy and the observability watchdog.

The core statistical recommendation is to preserve the multiclase 1X2 metrics Finsport already implements instead of adding a generic classifier dashboard. Prediction comparison should be anchored on `sample_count`, `accuracy`, `log_loss`, `multiclass_brier`, `rps`, `confusion_matrix` and `calibration`, always with the relevant sample, period, league scope and availability context. Decision comparison must treat coverage/selectivity and `NO_BET` as descriptive behavior, not as “more is better”. Capital reporting must use the metrics FS-004 already produces and must distinguish CapitalPolicy families from evaluation modes (`REPLAY`, `MONTE_CARLO`, `STRESS`).

The phrase recommended for fast comparison is **“mejor resultado observado en esta métrica”** or, when space is tight, **“líder observado”**. It must never appear without the relevant sample and scope, and it must never be promoted to “ganador”, “mejor modelo definitivo” or equivalent scientific claim.

The recommended styling is **Bootstrap 5 compiled CSS stored and served locally through Django static files**, plus a small project CSS override. FS-009 should not depend on a CDN at runtime, should not add Node or a frontend build pipeline, and should not require Bootstrap JavaScript, HTMX or any SPA framework. Native `<details>/<summary>` is sufficient for the initial match expansion interaction.

# 2. Research questions and disposition

| Question | Status | Conclusion for FS-009 |
|---|---|---|
| What should Prediction show? | ANSWERED | Use the existing 1X2 metric baseline plus sample/availability context; no binary precision/recall/F1/ROC layer. |
| What should Decision show? | ANSWERED | Separate behavior/selectivity, predictive hit behavior and economic evaluability; `NO_BET` is a valid decision. |
| How should Prediction × Decision be shown? | ANSWERED | Use four neutral descriptive cells; economic outcome of the selected action is separate. |
| What model agreement signals are useful now? | ANSWERED | Pairwise agreement/disagreement, exclusive correctness and shared errors; descriptive only, no ensemble recommendation. |
| What should Capital show? | ANSWERED | Only FS-004 metrics that exist; distinguish single-path metrics from stochastic distributions and distinguish policies from modes. |
| What Capital comparison exists today? | ANSWERED | Show current automatic prospective baseline and any existing experiments only within valid comparability groups; do not fabricate a longitudinal all-policy comparison. |
| How should unavailable/reason states be explained? | ANSWERED | Persisted internal reason → Spanish presentation mapping → neutral fallback for unclassified reason. |
| What should `/` prioritize? | ANSWERED | Historical summary first, separated into Prediction / Decision / Capital. |
| What should the daily view do? | ANSWERED | Date navigation, league filter, match summary, every model and every Decision policy separately, native expandable detail. |
| What styling/interactions should be used? | ANSWERED | Local Bootstrap 5 compiled CSS + minimal custom CSS; native HTML interaction first. |
| Exact persisted vocabulary/field representation for every current reason/calibration payload | PARTIALLY ANSWERED | Durable known meanings are defined here; exact current tokens/field shapes remain a preflight inventory task and must not be guessed in the UI. |

# 3. Evidence and recommendation summary

| Conclusion | Evidence class | Project consequence |
|---|---|---|
| Prediction, Decision and CapitalPolicy must remain distinct in reporting. | ESTABLISHED — F001/F002 | Three separate historical sections and no metric mixing that implies equivalence. |
| Proper probabilistic scores complement class accuracy. | ESTABLISHED — statistical literature | Show accuracy together with Log Loss, multiclass Brier and RPS, not accuracy alone. |
| `NO_BET` is a legitimate Decision, not failure. | ESTABLISHED — F001/F002 | Coverage/selectivity and `NO_BET` get explicit descriptive reporting. |
| Timestamp-valid market evidence is required for economic claims. | ESTABLISHED — F002 | Decision economics is shown only for economically evaluable decisions; otherwise explain unavailable. |
| FS-004 implements CapitalPolicy families; the missing capability is a common longitudinal automatic comparison on growing real resolved evidence. | ESTABLISHED — project decision + F003 | FS-009 reports existing evidence only; FS-010 owns longitudinal capital evaluation. |
| A fixed “recent 30 days” window is not justified by the brief. | RECOMMENDATION | Default home to total history and let the operator select an explicit date range; no arbitrary recent threshold. |
| Tables/cards are better than a chart-heavy dashboard for this single-operator minimum. | RECOMMENDATION | Use comparison tables, compact cards and `<details>`; add only metric-specific visualization where it materially answers a question. |
| Bootstrap 5 compiled CSS can be dropped in without a build pipeline. | ESTABLISHED — official Bootstrap docs | Vendor the compiled CSS into Django static assets; no CDN runtime dependency or Node pipeline. |
| Native `<details>/<summary>` is sufficient for disclosure without application JavaScript. | ESTABLISHED — HTML/MDN | Use it for per-match expansion; no Bootstrap JS or HTMX requirement in FS-009. |

# 4. Information model that the UI must preserve

```text
Prediction
!=
Decision
!=
CapitalPolicy
```

Prediction answers what outcome distribution a model estimated. Decision answers whether a policy selected `HOME`, `DRAW`, `AWAY` or `NO_BET`. CapitalPolicy answers what simulated exposure/risk behavior results when sizing a stream of Decisions.

A real match outcome and a timestamp-valid observed price are real evidence. A bankroll, stake/exposure and resulting PnL in FS-009 remain **simulation** and must be labelled as such.

# 5. Prediction reporting

## 5.1 Human reading order

The historical Prediction table should let the operator answer, in this order:

1. How much resolved evidence is behind this row?
2. How often was the modal class correct?
3. How good were the probabilities, not just the chosen class?
4. Is probability calibration visibly reasonable?
5. What classes does the model confuse?
6. Was the model available for the population being inspected?

The primary baseline is the metric set already implemented by Finsport:

```text
sample_count
accuracy
log_loss
multiclass_brier
rps
confusion_matrix
calibration
```

`precision`, `recall`, `F1`, `FPR` and `ROC-AUC` are not part of the FS-009 contract. They would add a binary/one-vs-rest explanatory layer that is not required to understand the existing 1X2 evidence and would broaden the UI beyond the metrics Finsport already uses.

## 5.2 Prediction metric dictionary

| metric | Spanish label | question answered | formula / denominator | range / unit | direction | data required | summary/detail | common misinterpretation | recommended display | source |
|---|---|---|---|---|---|---|---|---|---|---|
| `sample_count` | Muestra evaluada | ¿Con cuántos partidos resueltos se calculan estas métricas? | Conteo de predicciones resolubles/evaluadas para el contexto actual. | `N` partidos | Descriptiva; más muestra no significa mejor modelo. | Prediction + resultado canónico resuelto. | **Summary** | Comparar métricas sin mirar `N`; asumir que una muestra mayor implica mejor calidad. | Número siempre visible junto al modelo y filtros. | Finsport implementation baseline. |
| `accuracy` | Exactitud | ¿Qué proporción de resultados 1X2 fueron acertados por la clase modal? | `correct / sample_count`. | 0–1 o % | Mayor es mejor **dentro del mismo contexto**, pero no basta para evaluar probabilidades. | `predicted_outcome`, resultado canónico. | **Summary** | Confundir exactitud con calidad probabilística o rentabilidad. | Columna porcentual; mostrar `correct / N` en texto secundario. | Standard multiclass accuracy; Finsport baseline. |
| `log_loss` | Pérdida logarítmica | ¿Cuánta probabilidad asignó el modelo al resultado que realmente ocurrió, penalizando especialmente la confianza equivocada? | Promedio de `-log(p_true_class)`; equivalente a cross-entropy multiclase. | 0 a ∞ | **Menor es mejor.** | Vector `P(HOME/DRAW/AWAY)` + resultado real. | **Summary** | Leer diferencias pequeñas como concluyentes sin muestra/contexto; olvidar que una predicción muy confiada y equivocada pesa mucho. | Valor numérico + `N`; resaltar sólo “mejor resultado observado” dentro del grupo comparable. | [R1], [R4] |
| `multiclass_brier` | Brier multiclase | ¿Qué tan cerca estuvo el vector completo de probabilidades del vector real 1X2? | `mean(sum_c (p_c - y_c)^2)` bajo la forma cuadrática multiclase usada por Finsport. | 0 es perfecto; con la forma no normalizada de 3 clases, máximo teórico 2. No rescalar en UI. | **Menor es mejor.** | Vector de probabilidades + resultado one-hot. | **Summary** | Tratarlo como pura calibración: combina distintos aspectos de calidad probabilística. | Valor numérico + `N`; mismo contexto que Log Loss/RPS. | [R2], [R1] |
| `rps` | RPS — puntuación probabilística ordenada | ¿Qué tan lejos estuvo la distribución acumulada pronosticada de la categoría observada, respetando el orden 1X2 definido por el motor? | Para clases ordenadas, suma de diferencias cuadradas entre probabilidades acumuladas pronosticadas y observadas. | 0 es perfecto; el máximo depende de la normalización implementada. Mostrar el valor del motor sin reescalarlo. | **Menor es mejor.** | Vector de probabilidades, resultado y orden de categorías consistente. | **Summary** | Cambiar el orden/normalización entre comparaciones; interpretar el valor absoluto sin benchmark/contexto. | Valor numérico + `N`; tooltip/ayuda breve “menor = mejor”. | [R3], [R1] |
| `confusion_matrix` | Matriz de confusión 1X2 | ¿Qué resultados confunde el modelo entre HOME, DRAW y AWAY? | Conteos `actual × predicted`. Denominador no único; cada celda es conteo. | Conteos | Descriptiva; no existe “mayor es mejor” global. | Clase predicha + resultado real. | **Detail** | Reducirla a VP/FP/VN/FN binarios o comparar matrices con muestras distintas sin normalizar visualmente el contexto. | Tabla 3×3 con totales por fila/columna; no requiere gráfico. | Finsport baseline; standard confusion-matrix semantics. |
| `calibration` | Calibración | ¿Las probabilidades declaradas se parecen a las frecuencias observadas? | Usar **exactamente** la representación/calculation que ya produzca Finsport. Para reliability bins: probabilidad media pronosticada vs frecuencia observada. | Descriptiva; ideal = coincidencia entre probabilidad y frecuencia. | Más cerca de correspondencia perfecta es mejor; no inventar un único scalar si el motor no lo tiene. | Probabilidades + resultados, suficiente muestra por bin/clase. | **Summary compact + Detail** | Confundir un buen Brier con buena calibración; sacar conclusiones con bins escasos; inventar “calibración por partido”. | En home: indicador/valor existente del motor. En detalle: tabla de reliability por clase/bin si esa estructura existe; no requiere librería de gráficos. | [R5], [R1] |
| derived context: availability | Disponibilidad de predicción | ¿En qué proporción de oportunidades elegibles el modelo pudo producir Prediction? | `produced_predictions / eligible_model_fixture_opportunities` para el contexto. | 0–100% | Descriptiva; mayor disponibilidad no demuestra mayor calidad. | Población elegible + produced/unavailable state. | **Summary** | Usar distinto denominador entre modelos o contar fixtures no elegibles. | `producidas / elegibles` + tasa; reasons en detalle. | F002/F010 provenance rules. |
| derived context: outcome mix | Distribución HOME / DRAW / AWAY | ¿Qué clases tiende a predecir el modelo? | Conteo o % por `predicted_outcome`, denominador = Predictions producidas. | Conteo / % | Descriptiva. | `predicted_outcome`. | **Detail** | Leer una mezcla “equilibrada” como mejor; ignorar distribución real de resultados. | Tabla pequeña H/D/A, no gráfico obligatorio. | Project-derived reporting context. |

### 5.3 What belongs on the Prediction summary

Home should show one row per model with:

- modelo/version/config identity sufficient to distinguish the experiment;
- `sample_count`;
- availability count/rate;
- accuracy;
- log loss;
- multiclass Brier;
- RPS;
- compact calibration indication using the current implementation output;
- “mejor resultado observado en esta métrica” marker only where comparison is valid.

Confusion matrix, class distribution, calibration detail and unavailable reasons belong behind a detail disclosure.

# 6. Decision reporting

Decision metrics answer a different question from Prediction metrics: how a selection policy behaved after model/market context. `NO_BET` is a valid first-class outcome of that policy.

`coverage`, actionable rate, `NO_BET` rate and action mix are **descriptive**. There is no valid generic direction such as “more actions is better”, “less NO_BET is better” or “more coverage is better”. Their value is only interpretable together with later selection quality, availability and provenance.

## 6.1 Decision metric dictionary

| metric | Spanish label | question answered | formula / denominator | range / unit | direction | data required | summary/detail | common misinterpretation | recommended display | source |
|---|---|---|---|---|---|---|---|---|---|---|
| `evaluated_fixtures` | Partidos evaluados por la policy | ¿Sobre cuántos fixtures tuvo oportunidad de decidir esta policy? | Conteo del universo efectivamente evaluado por la policy bajo el filtro actual. | `N` fixtures | Descriptiva. | Decision evaluation population. | **Summary** | Confundir “evaluado” con “tenía precio válido” o “terminó resuelto”. | Conteo visible como denominador base. | Finsport Decision semantics. |
| actionable decisions | Acciones seleccionadas | ¿Cuántas Decisions fueron HOME/DRAW/AWAY? | Conteo `action != NO_BET`. | `N` | Descriptiva. | Decision action. | **Summary** | “Más selecciones = mejor”. | `N` + coverage. | F002. |
| `coverage` / actionable rate | Cobertura de selección | ¿Qué proporción de fixtures evaluados terminó en una acción HOME/DRAW/AWAY? | `actionable / evaluated_fixtures`. | 0–100% | **Descriptiva.** | Evaluated + action. | **Summary** | Optimizar cobertura aislada; confundir selectividad con calidad. | `%` y `actionable/evaluated`. | F002 coverage-vs-hit-rate semantics. |
| `no_bet_count` | Decisiones NO_BET | ¿Cuántos fixtures fueron deliberadamente no seleccionados? | Conteo `action == NO_BET`. | `N` | Descriptiva. | Decision action. | **Summary** | Tratar `NO_BET` como error o missing Decision. | Conteo. | F001/F002. |
| `no_bet_rate` | Tasa NO_BET | ¿Qué proporción de fixtures evaluados recibió abstención? | `NO_BET / evaluated_fixtures`. | 0–100% | **Descriptiva.** | Evaluated + action. | **Summary** | “Menos NO_BET = mejor”. | `%` + `count/evaluated`. | F001/F002. |
| `no_bet_reasons` | Motivos de NO_BET | ¿Por qué la policy se abstuvo cuando existe una razón persistida? | Conteo por **reason persistido**; denominador = `no_bet_count` para tasas. | Conteo / % | Descriptiva. | Persisted Decision reason. | **Detail** | Inventar causas desde la UI; convertir un reason técnico en explicación económica. | Tabla `motivo → count/%` usando mapping castellano; fallback neutro para código no clasificado. | F002 + UI mapping rule in this report. |
| `action_mix` | Distribución de acciones | ¿Cómo se distribuyen HOME/DRAW/AWAY entre las acciones seleccionadas? | Conteo/% por acción; denominador = actionable. | Conteo / % | Descriptiva. | Decision action. | **Detail** | Suponer que una distribución equilibrada es deseable. | Tabla H/D/A. | Finsport Decision semantics. |
| `hits` | Aciertos de selección | ¿En cuántas acciones seleccionadas y resueltas coincidió la acción con el resultado real? | Conteo entre actionable + resolved. | `N` | Mayor observado es mejor **sólo con denominator visible**. | Action + canonical result. | **Summary** | Comparar counts con coberturas distintas; confundir con Prediction accuracy. | `hits / resolved actionable`. | F002. |
| `losses` | Fallos de selección | ¿En cuántas acciones seleccionadas y resueltas no coincidió la acción con el resultado? | Conteo entre actionable + resolved. | `N` | Menor observado es mejor **sólo con denominator visible**. | Action + canonical result. | **Summary** | Igual que hits; no incorpora cuota. | `losses / resolved actionable`. | F002. |
| `hit_rate` | Tasa de acierto de selección | ¿Qué proporción de acciones seleccionadas y resueltas acertó? | `hits / (hits + losses)`. `NO_BET` y unresolved no entran en el denominador. | 0–100% | Mayor observado es mejor para hit behavior, **no implica mayor retorno**. | Action + canonical result. | **Summary** | Confundir con model accuracy o rentabilidad. | `%` + `hits/(hits+losses)`. | F002. |
| `longest_losing_streak` | Racha perdedora más larga | ¿Cuál fue la secuencia más larga de acciones seleccionadas fallidas? | Máximo conteo cronológico consecutivo de losses evaluables. | `N` decisiones | Menor es favorable como descripción de racha; sample-dependent. | Ordered resolved actionable Decisions. | **Detail** | Comparar rachas entre muestras/períodos muy distintos como si fueran equivalentes. | Número + período. | Finsport implemented Decision metrics. |
| valid-price actionable count | Acciones con precio temporal válido | ¿Cuántas acciones seleccionadas tienen la evidencia de mercado requerida para evaluación económica? | Conteo actionable con selected timestamp-valid price conforme a provenance. | `N` | Descriptiva. | Selected OddsObservation/price + Decision time. | **Summary** | Rellenar missing price con snapshot actual o precio posterior. | `N`. | F002 temporal provenance. |
| valid-price coverage | Cobertura de precio válido | ¿Qué parte de las acciones seleccionadas tiene evidencia de mercado temporal válida? | `valid_price_actionable / actionable`. | 0–100% | Descriptiva; mayor cobertura significa más evaluabilidad, no mejor policy. | Actionable + temporal price validity. | **Summary** | Tratar disponibilidad de precio como calidad de selección. | `%` + numerator/denominator. | F002. |
| `economic_decisions` | Decisiones económicamente evaluables | ¿Cuántas acciones permiten calcular un resultado económico simulado con provenance suficiente? | Conteo de acciones con precio temporal válido y resultado canónico resuelto, bajo el contrato económico actual. | `N` | Descriptiva. | Action + valid selected price + resolved result. | **Detail** | Incluir unresolved o precios no válidos para inflar muestra. | Conteo + unavailable count. | F002. |
| `flat_unit_pnl` | PnL simulado — flat 1u | ¿Qué PnL habría producido la misma policy bajo exposición simulada plana de 1 unidad en cada decisión económicamente evaluable? | Suma de payoffs simulados sobre `economic_decisions`, con 1u por acción. | unidades simuladas (`u`) | Mayor observado es mejor, condicionado a sample/provenance. | Economic decisions + valid price + result. | **Detail** | Presentarlo como dinero real o ejecución externa; extrapolar fuera de la muestra. | `+/- Xu`, con label “simulado”. | Finsport Decision economic metric. |
| `roi` | ROI simulado de selección | ¿Cuánto PnL simulado produjo por unidad total expuesta en el cálculo económico de la policy? | `flat_unit_pnl / total_flat_unit_staked` (o la definición exacta persistida por el motor si difiere); denominator must be visible/derivable. | % | Mayor observado es mejor; no es winner criterion. | Economic decisions + simulated stake basis. | **Detail** | Comparar policies con evidencia/periods/prices distintos; confundir con retorno real ejecutado. | `%` junto a `economic_decisions`. | F002/Finsport metric semantics. |
| `mean_selected_odd` | Cuota seleccionada media | ¿Qué nivel medio de precio temporal tuvieron las acciones seleccionadas evaluables? | Mean of selected valid decimal odds. | decimal odds | Descriptiva. | Selected valid prices. | **Detail** | “Cuota más alta = mejor”. | Número con `N`. | Finsport implemented metric. |
| `mean_predicted_ev` | EV predicho medio | ¿Qué valor esperado estimó la policy/modelo para las decisiones donde ese valor existe? | Mean of persisted predicted EV across eligible Decisions. | implementation-defined EV unit | Descriptiva; higher predicted EV is not realized proof. | Persisted predicted EV. | **Detail** | Confundir EV modelado con retorno observado o edge probado. | Número + sample. | F002. |
| derived cross metric | Aciertos predictivos en NO_BET | ¿Cuántos fixtures NO_BET tenían una Prediction modal correcta? | Count of `Prediction correct AND Decision == NO_BET`; rate denominator = resolved NO_BET fixtures with a valid Prediction for the same model-policy pairing. | `N` / % | Descriptiva only. | Prediction + Decision + resolved result. | **Detail** | Llamarlo “ganancia perdida”; asumir que existía una acción contrafactual o precio válido. | Count/rate inside Prediction × Decision table, explicitly non-economic. | Project-derived; constrained by F002. |

## 6.2 Decision summary

The home Decision table should prioritize:

- policy identity/config;
- evaluated fixtures;
- actionable count;
- coverage;
- `NO_BET` count/rate;
- resolved actionable sample;
- hits/losses;
- hit rate;
- valid-price coverage.

Economic metrics (`economic_decisions`, flat-unit simulated PnL, ROI, mean selected odd, mean predicted EV) should be visually separated under a label such as **“Evidencia económica simulada disponible”**, and only shown where temporal provenance makes the calculation valid.

# 7. Prediction × Decision: neutral cross-analysis

Prediction correctness and Decision outcome are distinct dimensions. A Prediction can be correct while a Decision policy selected a different action; an actionable Decision can also be correct or incorrect independently of whether the model’s modal class was correct.

FS-009 should therefore use neutral descriptors only:

| | Decision actionable | Decision `NO_BET` |
|---|---|---|
| **Prediction correcta** | Prediction correcta + Decision accionable | Prediction correcta + `NO_BET` |
| **Prediction incorrecta** | Prediction incorrecta + Decision accionable | Prediction incorrecta + `NO_BET` |

For every cell show:

- count;
- denominator used;
- percentage within the model-policy pair and current filter scope.

For `Prediction correcta + NO_BET`, the recommended Spanish explanatory label is **“acierto predictivo en partido no seleccionado”**. It is descriptive. It is not “ganancia perdida”.

For `Prediction incorrecta + NO_BET`, use **“predicción incorrecta en partido no seleccionado”**. It is not “pérdida evitada”.

If the Decision was actionable, its own hit/loss and any economic simulated outcome must be shown **separately**, based on the action actually selected and the real match outcome. The cross-table must never label `Prediction correcta + Decision accionable` as a winning Decision or positive PnL.

# 8. Agreement, disagreement and complementarity signals

FS-009 may expose simple descriptive signals that help identify future scientific questions without constructing or recommending an ensemble.

Recommended minimum signals:

| Signal | Definition / denominator | Human question | FS-009 display | Boundary |
|---|---|---|---|---|
| Pairwise agreement rate | Same `predicted_outcome` / fixtures where both models produced a Prediction. | ¿Con qué frecuencia estos dos modelos eligen la misma clase? | Pairwise matrix, % + joint `N`. | Descriptive only. |
| Pairwise disagreement distribution | Counts of outcome-pair combinations among jointly available predictions. | ¿Cómo discrepan: HOME vs DRAW, HOME vs AWAY, etc.? | Expandable table. | No ranking. |
| Exclusive correct — A | A correct and B incorrect / jointly resolved fixtures with both Predictions. | ¿Cuándo A acierta donde B falla? | Count/% in pair detail. | Does not imply ensemble value. |
| Exclusive correct — B | Symmetric definition. | ¿Cuándo B acierta donde A falla? | Count/%. | Same. |
| Shared errors | Both incorrect / jointly resolved fixtures with both Predictions. | ¿Con qué frecuencia fallan juntos? | Count/%. | Same. |
| All-model agreement | All available models choose the same class / fixtures where the required compared set is available. | ¿Cuándo existe consenso descriptivo? | Small count/rate near daily match detail or model-comparison detail. | Must not become “official prediction”. |

Do not add Venn diagrams, correlation scatterplots, ensemble scores or automatic combination recommendations to FS-009. A small table communicates the useful evidence with less visual and implementation cost.

# 9. Capital reporting

## 9.1 Policies are not modes

FS-009 must keep the following distinction explicit:

```text
FLAT_UNIT
FIXED_FRACTION_BANKROLL
FIXED_TARGET_PROFIT_NO_RECOVERY
LEGACY_RECOVERY
LEGACY_CAPPED
LEGACY_PARTIAL
FRACTIONAL_KELLY
→ CapitalPolicy families

REPLAY
MONTE_CARLO
STRESS
→ evaluation modes
```

A policy name and a mode must never be presented as alternatives in the same dimension.

## 9.2 Mode semantics in the UI

- **REPLAY**: deterministic evaluation of a concrete Decision stream under a policy/config. Report realized simulated path metrics. Distributional metrics such as Expected Shortfall are not fabricated from a single path.
- **MONTE_CARLO**: stochastic repeated paths. Report distributions/probabilities only when the experiment actually contains them.
- **STRESS**: stress/scenario evaluation. Values describe the configured scenario; they are not automatically empirical probabilities or “what will happen”. If a stress experiment is multi-path, only then may distribution fields produced by the engine be shown as such.

## 9.3 Capital metric dictionary

| metric | Spanish label | question answered | formula / denominator | range / unit | direction | data required | summary/detail | REPLAY? | MONTE_CARLO? | STRESS? | common misinterpretation | recommended display | comparability constraints |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| initial/reference bankroll | Bankroll simulado inicial | ¿Desde qué base de unidades parte el experimento? | Config value. | `u` | Context, not a quality metric. | Experiment config. | **Summary context** | ✓ | ✓ | ✓ | Comparing terminal values without the same starting base. | `100u`, etc., beside mode/config. | Must match to compare terminal values directly. |
| `total_staked` | Exposición simulada total aplicada | ¿Cuántas unidades se aplicaron realmente a lo largo del run/path? | `sum(applied_stake)`. | `u` | Descriptive. | Ledger applied stakes. | **Detail** | ✓ | Per-path / aggregate if produced | Scenario-dependent | Confusing requested stake with applied stake. | `Xu`; label “aplicada”. | Same stream/config needed for meaningful comparison. |
| `turnover` | Rotación sobre bankroll inicial | ¿Cuántas veces la exposición aplicada acumulada equivale al bankroll inicial? | `total_staked / initial_bankroll`. | ratio (`x`) | Descriptive; lower/higher is not inherently better. | Total applied stake + initial bankroll. | **Summary/detail** | ✓ | Per-path/distribution if produced | Scenario-dependent | Calling turnover “total stake”; ignoring different initial bankrolls. | `1.35×`, etc. | Initial bankroll and stream/config must be comparable. |
| `total_pnl` | PnL simulado total | ¿Cuál fue el resultado económico simulado neto? | Engine sum of simulated settled PnL. | `u` | Higher observed is better on return dimension only. | Applied stakes + valid payoff evidence/results. | **Summary** | ✓ | Mean/median/distribution may also exist | ✓ if produced | Treating simulated PnL as real money; comparing different streams. | Signed units, e.g. `+4.2u`. | Same Decision stream, price basis, policy config and mode. |
| `roi` | ROI simulado | ¿Qué retorno produjo el PnL por unidad aplicada/expuesta según la engine definition? | Use the exact FS-004 persisted metric definition; do not recalculate with a different denominator in the template. | % | Higher observed is better on return dimension only. | Engine metrics. | **Summary** | ✓ | aggregate/distribution if produced | ✓ if produced | ROI alone as winner; mixing modes/configs/samples. | `%` + total stake/PnL context. | Same evidence/config/mode group. |
| `terminal_bankroll` | Bankroll simulado final | ¿Con cuántas unidades terminó este path/run? | Engine terminal state. | `u` | Higher observed is better on terminal-return dimension only. | Initial bankroll + path settlements. | **Summary** | ✓ | Distribution summary | ✓ if produced | Ignoring path risk/drawdown. | `Xu`, paired with MDD. | Same initial bankroll and comparable stream/config. |
| `maximum_drawdown` | Máximo drawdown relativo | ¿Cuál fue la mayor caída desde un pico previo del bankroll simulado? | Engine peak-to-trough relative drawdown. | ratio / % according to stored metric | Lower is better on this risk dimension. | Bankroll path. | **Summary** | ✓ | Distribution | ✓ if produced | Comparing without same mode/stream; assuming it captures all risk. | `%` with label “máxima caída”. | Same unit/definition and comparable evidence. |
| `maximum_drawdown_amount` | Máximo drawdown en unidades | ¿Cuántas unidades separaron el pico y valle del peor drawdown? | Engine peak minus trough amount. | `u` | Lower is better on this risk dimension. | Bankroll path. | **Detail** | ✓ | Distribution if produced | ✓ if produced | Comparing absolute values with different initial bankroll. | `Xu`. | Initial bankroll must be visible. |
| `drawdown_duration` | Duración del drawdown | ¿Durante cuántos pasos del motor persistió la caída relevante? | Engine-defined count along the ledger/path. | engine steps / entries; exact label confirmed in preflight | Lower is favorable as risk-duration context. | Ordered bankroll path. | **Detail** | ✓ | Distribution if produced | ✓ if produced | Calling it calendar days without engine evidence. | Count + engine unit label. | Same path granularity. |
| `max_single_stake` | Máxima exposición individual aplicada | ¿Cuál fue el mayor `applied_stake` individual? | `max(applied_stake)`. | `u` | Descriptive risk context; smaller often means less absolute concentration, not automatic superiority. | Ledger. | **Detail** | ✓ | Distribution | ✓ if produced | Using requested rather than applied stake. | `Xu`. | Initial bankroll/config visible. |
| `max_stake_pre_bankroll_ratio` | Máxima exposición relativa al bankroll previo | ¿Qué fracción del bankroll disponible antes del batch representó la mayor exposición aplicada? | `max(applied_stake / bankroll_before)` using the corresponding pre-batch/pre-action bankroll; **not initial bankroll**. | ratio / % | Lower indicates less peak relative concentration. | Applied stake + corresponding bankroll-before. | **Summary/detail** | ✓ | Per path + distribution | ✓ if produced | Dividing by initial bankroll; using requested stake. | `%` + max stake. | Same policy semantics and batching. |
| `stake_concentration` | Concentración de exposición | En un conjunto de paths, ¿cuál es el promedio del máximo ratio de exposición de cada path? | **FS-004 semantics:** per path `max(applied_stake / pre_batch_bankroll)`; aggregate `mean(per-path maxima)`; only funded/applied actions count. | ratio / % | Lower = less average peak concentration across paths. | Multi-path metrics with applied stakes and pre-batch bankroll. | **Summary for stochastic; otherwise only if engine persists it** | Do **not** fabricate an aggregate from a single path; use `max_stake_pre_bankroll_ratio` for the deterministic path unless engine explicitly stores concentration. | ✓ | Only if stress run is multi-path and engine produces it | Describing it as Gini; dividing by initial bankroll. | Ratio/% with path count. | Same mode/path-generation/config. |
| `practical_ruin` | Ruina práctica simulada | ¿El path llegó a una engine-defined state in which the capital process cannot continue without violating capital constraints? | Engine boolean/termination semantics; examples in F002 include joint overcommit and funded bankroll depletion. **No invented percentage threshold.** | boolean | `false` is preferable on ruin dimension. | Engine path state. | **Summary** | ✓ | Per-path source for ruin probability | ✓ per path if produced | Interpreting it as personal financial ruin or as a generic “bankroll below X%”. | Badge `Sí/No` + reason where persisted. | Compare only under same policy/config and ruin semantics. |
| `cap_hits` | Activaciones de límite | ¿Cuántas veces intervino un cap configurado? | Engine count. | `N` | Descriptive; fewer is not automatically better across different configs. | Policy/ledger state. | **Detail** | ✓ | Distribution/aggregate if produced | ✓ if produced | Ranking policies by cap hits despite different caps/configs. | Count + config identity. | Same cap/config required. |
| `longest_losing_streak` | Racha perdedora más larga | ¿Cuál fue la secuencia más larga de outcomes negativos en la stream evaluada? | Engine count on ordered settled exposures. | `N` | Lower favorable as risk-path descriptor. | Ordered resolved exposures. | **Detail** | ✓ | Distribution if produced | ✓ if produced | Treating as independent of sample size. | Count. | Same stream horizon/sample. |
| stochastic: mean terminal bankroll | Bankroll final medio | ¿Dónde termina en promedio la distribución de paths? | Mean across terminal bankrolls. | `u` | Higher observed on return dimension. | Multiple stochastic paths. | **Summary** | — | ✓ | Only if multi-path stress | Mean can hide tail risk. | Mean + median + quantiles together. | Same path generator/config/seed policy and sample count. |
| stochastic: median terminal bankroll | Bankroll final mediano | ¿Cuál es el centro robusto de la distribución final? | Median across paths. | `u` | Higher observed on return dimension. | Multiple paths. | **Summary** | — | ✓ | Conditional | Can differ materially from mean in skewed distributions. | Alongside mean. | Same as above. |
| stochastic: terminal bankroll quantiles | Cuantiles de bankroll final | ¿Qué resultados aparecen en distintas zonas de la distribución? | Engine quantiles (for the configured output, e.g. 1%/5% where present). | `u` | Context-dependent; higher lower-tail quantiles are favorable. | Multiple paths. | **Detail/Summary compact** | — | ✓ | Conditional | Inventing percentiles not actually produced. | Show only stored/produced quantiles with labels. | Same path/config. |
| `expected_shortfall` | Expected Shortfall | ¿Cuál es el resultado medio dentro de la cola adversa definida por el engine? | Use exact stochastic engine definition/configured tail. | `u` or loss metric per engine | Less severe tail loss is better. | Distribution of paths. | **Detail** | **UNAVAILABLE from one deterministic path** | ✓ when produced | Conditional | Fabricating ES from one replay or using unspecified tail level. | Value + tail definition/config. | Same tail definition/path generation. |
| `practical_ruin_probability` | Probabilidad de ruina práctica simulada | ¿Qué fracción de paths entra en `practical_ruin`? | `ruined_paths / total_paths`. | 0–100% | Lower is better on ruin dimension. | Multiple paths + engine ruin state. | **Summary** | — | ✓ | Conditional | Treating it as real-world probability outside simulation assumptions. | `%` + path count. | Same simulation/stress assumptions/config. |
| `maximum_drawdown_distribution` | Distribución de máximo drawdown | ¿Cómo varía el peor drawdown entre paths? | Distribution of per-path MDD. | % / ratio | Lower distribution/tails favorable. | Multiple paths. | **Detail** | — | ✓ | Conditional | Comparing distributions with different stress/sampling assumptions. | Quantile table; no chart library required. | Same mode/config/path count. |
| `max_stake_distribution` | Distribución de máxima exposición | ¿Cómo varía el máximo stake aplicado entre paths? | Distribution of per-path maximum applied stake. | `u` | Descriptive risk context. | Multiple paths. | **Detail** | — | ✓ | Conditional | Confusing with `stake_concentration`. | Quantile table. | Same mode/config. |
| termination probability | Probabilidad de terminación | ¿Qué fracción de paths se detiene por las reglas del motor? | `terminated_paths / total_paths`. | 0–100% | Lower is favorable on continuity dimension. | Multiple paths + terminated state. | **Summary/detail** | Use a boolean/state, not probability. | ✓ | Conditional | Assuming every termination is identical to every ruin reason. | `%` + reason breakdown if persisted. | Same termination semantics/config. |

## 9.4 Return and risk must be shown together

A Capital row should never show ROI or terminal bankroll alone. The minimum compact grouping is:

1. terminal bankroll;
2. total PnL / ROI;
3. maximum drawdown;
4. practical ruin state/probability when applicable;
5. peak relative exposure (`max_stake_pre_bankroll_ratio`) or stochastic `stake_concentration` when applicable;
6. sample/Decision stream identity and mode/config context.

This is not a composite score. It is a side-by-side return/risk view.

# 10. What Capital can honestly show today

FS-004 already implements the CapitalPolicy families. The missing capability is **not policy implementation**. The missing capability is a **common longitudinal automatic comparison over growing real resolved evidence**.

FS-009 should classify current Capital evidence into four groups:

| Group | What FS-009 may show | What it must not imply |
|---|---|---|
| **A. Automatic prospective baseline** | The current normalized automatic baseline from FS-006: `REPLAY`, initial bankroll `100u`, `FLAT_UNIT`, stake `1u`, based on the current DIXON_COLES / MODAL_ALL stream as defined by the pipeline. Show its actual persisted metrics and sample. | It is not “the chosen production CapitalPolicy” and does not prove FLAT_UNIT superiority. |
| **B. Manual/historical CapitalExperiments** | Existing experiment rows and metrics, when present, with policy, mode, config identity, Decision stream/sample and date scope. | Do not merge them into one ranking if inputs/config/modes differ. |
| **C. Implemented policies without comparable prospective longitudinal evidence** | List the family as **“Implementada; sin evidencia prospectiva longitudinal comparable en el flujo automático actual”** only if this status is supported by current project state. | Do not label the policy “not implemented”, “worse”, or “not viable”. |
| **D. Non-comparable experiments** | Show individually with a visible “No comparable con este grupo” note and the differing mode/config/sample fields. | Do not sort them into a winner table. |

A home Capital comparison table should only rank/highlight metrics **inside a comparability group**. A valid group needs, at minimum, the same relevant Decision stream/population, mode, initial bankroll/reference basis, price/evidence basis and materially comparable policy configuration assumptions. If these are not satisfied, FS-009 should present separate experiment blocks rather than a single leaderboard.

Approved forward sequence for this report:

```text
FS-009
→ human frontend/reporting with current evidence

FS-010
→ longitudinal CapitalPolicy evaluation with growing real resolved results
→ small later frontend delta to expose that new evidence

FS-011
→ evaluator of Prediction + Decision + Capital
```

FS-009 must not freeze whether FS-010 will automatically include `MONTE_CARLO` or `STRESS`; FS-010 will decide its own methodology and modes.

# 11. Availability, status and reason presentation

## 11.1 Core UI rule

The reporting UI must not infer causes from missing output. It should apply this pipeline:

```text
persisted internal status/reason
→ presentation mapping in castellano
→ plain-language explanation
→ neutral fallback when the code is not classified
```

Fallback format:

> **No evaluable — motivo no clasificado (`<INTERNAL_CODE>`)**. Revisar el detalle/auditoría para conocer el estado persistido.

Do not replace an unknown reason with a guess such as “needs more CPU”, “provider problem” or “insufficient history”.

## 11.2 Availability/status dictionary

The exact current token inventory must be confirmed in FS-009 preflight. The table below contains only reason/status families already present in the PRE-FS-009 contract or durable Finsport semantics, plus a neutral fallback.

| internal status/reason | Spanish operator label | plain-language explanation | expected or concerning? | possible resolution | classification | where to inspect further |
|---|---|---|---|---|---|---|
| `UNAVAILABLE` | No evaluable | El resultado analítico solicitado no puede producirse honestamente con la evidencia válida disponible; debe mostrarse el reason persistido. | Depends on reason. | Depends on persisted reason; no generic retry promise. | Evidence state | Frontend detail → Django Admin/audit; Grafana only if reason is operational. |
| `INSUFFICIENT_HISTORY` | Historia insuficiente | El modelo/policy no dispone de la historia válida exigida para producir esa salida. | Usually expected while evidence accumulates. | More canonical eligible/resolved history may make it evaluable. | **Needs more data** | Frontend detail + Admin data audit. |
| `NO_VALID_MARKET` | Sin evidencia de mercado válida | No existe una observación de precio que cumpla el provenance temporal/market mapping requerido para este cálculo. | Expected data-coverage limitation unless caused by an operational failure recorded separately. | A future valid timestamped observation can make future Decisions/evaluations evaluable; do not backfill with latest/post-cutoff price. | **Missing market evidence** | Decision/Odds audit in Admin; Grafana only if a separate runtime/provider failure exists. |
| `UNRESOLVED` | Partido no resuelto | El resultado canónico todavía no permite evaluar Prediction/Decision/economics. | Expected pending state. | Canonical settlement when the match becomes validly resolved. | **Pending real outcome** | Match audit in Admin. |
| `NO_WORK` | Sin trabajo | En ese run/context no existían items elegibles que procesar. | Often expected. | No correction required unless unexpected for the chosen filters/run. | **No eligible work** | Run/fixture audit; Grafana only if operational symptoms exist. |
| `SKIPPED` | Omitido | El item fue omitido deliberadamente; la UI must show the persisted reason. | Depends on reason. | Only the reason determines whether anything should change. | **Reason-dependent** | Frontend detail / Admin. |
| `FAILED` | Fallo operativo | La ejecución no pudo satisfacer su contrato por un error/runtime defect/configuration failure. | Concerning. | Diagnose the actual failure; do not guess resources. | **Operational problem** | **Grafana + Loki + Alloy + watchdog**, then Admin/audit for affected domain objects. |
| `DEGRADED` | Resultado degradado / parcial | El run completed with a recorded degraded condition; display the persisted cause/context. | Concerning or expected fail-soft depending on cause. | Resolve the persisted underlying condition if action is needed. | **Operational/data quality context** | Frontend summary + Grafana for operational diagnostics + Admin for data audit. |
| capability disposition `DEFERRED_WITH_OWNER` or equivalent not-operational state | Capacidad no operativa actualmente | El código/capability existe o está reconocida, pero no participa del flujo actual según su disposición. | Expected if deliberate. | Future approved work/trigger, not an FS-009 runtime retry. | **Capability not integrated/operational** | Project source/ticket context; Admin only if relevant data exists. |
| `UNAVAILABLE_CONCURRENT_RECOVERY_STEP` | Recovery no evaluable por concurrencia | La recovery policy no puede construir una secuencia válida cuando existen múltiples Decisions accionables en el mismo batch sin ordering canónico independiente. | Expected model/engine limitation for that input shape. | Requires a future deliberate methodology/domain change if the project chooses to support it. | **Method/capability constraint** | CapitalExperiment detail + Admin. |
| `INSUFFICIENT_CAPITAL` | Exposición simulada no financiable | El batch solicitado excede el bankroll simulado disponible under the engine rules; affected applied stake is not silently rescaled. | Produced risk outcome, not operational failure. | Different policy/config may behave differently; FS-009 does not change it. | **Capital simulation outcome** | Capital run/ledger audit. |
| `BANKROLL_DEPLETED` | Bankroll simulado agotado | Un batch funded and settled leaves bankroll at or below the engine continuation condition, producing practical ruin/termination. | Produced risk outcome, not operational failure. | No FS-009 remediation; it is evidence about that policy/path. | **Capital simulation outcome** | Capital run/ledger audit. |
| unknown persisted code | Motivo no clasificado | Finsport has a persisted reason that this presentation mapping does not yet know. | Needs mapping review, not cause guessing. | Add a presentation mapping only after semantics are verified. | **Unknown classification** | Raw reason in Admin/audit; Grafana only if independently operational. |

## 11.3 Four categories the operator must be able to distinguish

- **Necesita más datos:** the valid historical sample does not yet satisfy the model/policy input requirement. This is an evidence-accumulation state.
- **Falta evidencia de mercado:** the required timestamp-valid price/market evidence is absent. This is provenance/market coverage, not model weakness.
- **Capability no integrada/no operativa:** capability exists or is recognized but is deliberately not part of the current automatic/product flow. This needs future scoped work, not more data by itself.
- **Problema operativo:** runtime/provider/system execution failed or degraded according to persisted operational evidence. This is the category that points to Grafana diagnostics.

No UI copy should attribute a state to CPU/RAM/performance unless operational evidence specifically establishes that cause.

# 12. “Leader observed” language

Recommended taxonomy:

- **“Mejor resultado observado en esta métrica”** — preferred full phrase.
- **“Líder observado”** — compact badge/table label.
- **“Resultado actual”** — neutral value without a leader marker.
- **“Muestra limitada”** — descriptive only when the UI has an explicit project-provided reason/flag; FS-009 must not invent a numeric sufficiency threshold.
- **“Todavía no evaluado científicamente”** — page-level disclaimer for the reporting stage.
- **“No comparable”** — required when mode/config/population differs materially.

Every leader marker must retain visible context:

```text
metric value
+ sample N
+ period
+ league scope
+ availability
```

If rows do not share a sufficiently comparable context, do not highlight a leader.

# 13. Historical home `/`

## 13.1 Primary information architecture

The home must start with **Estado general de evidencia**, then three separate blocks:

1. **Modelos predictivos**
2. **Políticas de decisión / selección**
3. **Políticas de capital**

The home is not the day list and must not become a wall of charts.

## 13.2 Filters and historical/recent handling

Default scope:

```text
all available historical evidence
+
all enabled/reportable competitions
```

Server-side GET filters:

- league/competition;
- `date_from`;
- `date_to`.

Do **not** hard-code “last 30 days” or another rolling window as a scientific comparator. If the operator selects a date range, the page may label it **“Periodo seleccionado”** and compare it visually with the total-history context if the implementation can do so simply. The period is explicit, not implicitly “recent”.

League breakdown belongs in an expandable/detail table under each category or via the same league filter. This is enough for FS-009 to study different leagues without adding separate dashboards.

## 13.3 General evidence state

At the top of `/`, show a compact text/card summary:

- selected date/league scope;
- number of resolved fixtures/evidence opportunities in scope;
- any material `DEGRADED`/`FAILED` reporting condition that is actually persisted;
- link to daily view;
- link to Grafana **only when useful for operational diagnosis** or as a clearly labelled “Diagnóstico operativo” navigation item.

Do not duplicate operational logs in the reporting page.

# 14. Daily view

## 14.1 Navigation

Recommended route:

```text
/daily/?date=YYYY-MM-DD&competition=<id>
```

Controls:

```text
← Día anterior
fecha seleccionada
Día siguiente →

Liga: [Todas / one competition]
```

All navigation is server-side and works as normal links/forms.

## 14.2 Match summary row

For each match show only:

- league;
- kickoff;
- home team;
- away team;
- canonical match status;
- final score/outcome when resolved;
- compact availability/state summary if anything is unavailable/degraded.

The summary row must **not** invent a “predicción principal”, “predicción oficial” or single Decision. Every model and every Decision policy remains separately inspectable.

An optional tiny descriptor such as “3/5 modelos coinciden en HOME” may appear as a descriptive agreement summary, but it cannot replace model-specific output.

## 14.3 Expanded match detail

Native `<details>` should reveal two main sub-tables.

### Prediction by model

For every Prediction model/experiment relevant to the fixture:

- model identity/version/config display name;
- `P(HOME)`;
- `P(DRAW)`;
- `P(AWAY)`;
- predicted outcome;
- actual outcome if resolved;
- correct/incorrect if evaluable;
- availability status/reason if unavailable.

No per-match “calibration” metric is required. Calibration is an aggregate property and stays in historical model reporting.

### Decision by policy

For every Decision policy relevant to the fixture:

- policy identity/config display name;
- action (`HOME`/`DRAW`/`AWAY`/`NO_BET`);
- persisted reason;
- selected timestamp-valid price when present;
- actual outcome if resolved;
- selection hit/loss if evaluable;
- simulated economic result only when the existing evidence contract permits it.

FS-009 does **not** require complete odds history in match detail. It shows the selected/linked valid evidence needed to understand the persisted Decision, while detailed object/provenance inspection remains available in Django Admin.

# 15. Detail interaction alternatives

| option | complexity | JavaScript | strengths | weaknesses | recommendation |
|---|---:|---|---|---|---|
| Native `<details>/<summary>` | Lowest | None | Semantic disclosure; keyboard-operable with native browser behavior; no dependency; keeps day context. | Styling is simpler/less controlled than custom accordions. | **Use in FS-009.** |
| Bootstrap Collapse or HTMX partial loading | Medium | Required | More interaction control; HTMX can defer server-rendered fragments. | Adds JS/runtime surface that the initial requirement does not need. | **Do not require in FS-009.** Reconsider only if preflight proves a material payload/usability need. |
| Separate match-detail page | Low-medium | None | Stable URL and unlimited detail capacity. | Extra navigation and duplicate page structure for a single-operator initial UI. | **Not required initially.** Can be added later if inline detail becomes unwieldy. |

The initial product contract therefore uses native `<details>` and no application JavaScript requirement.

# 16. UI information/component table

| information | page | component | primary/detail | filter/group | interaction needed? | recommended primitive |
|---|---|---|---|---|---|---|
| Current reporting scope | `/` | Context strip/card | Primary | league + date range | GET form | Bootstrap form controls / text |
| General evidence state | `/` | Alert/summary card | Primary | current scope | None | Card/alert with text |
| Prediction model comparison | `/` | Comparison table | Primary | model, league, period | Optional row detail | Responsive table |
| Prediction confusion/calibration/outcome mix | `/` | Model detail disclosure | Detail | selected model/context | Native expand | `<details>` + tables |
| Model agreement matrix | `/` | Pairwise table | Detail | model pair/context | Native expand | Table |
| Decision policy comparison | `/` | Comparison table | Primary | policy, league, period | Optional detail | Responsive table |
| `NO_BET` reasons/action mix/economic detail | `/` | Policy detail disclosure | Detail | selected policy/context | Native expand | `<details>` + tables |
| Prediction × Decision cross | `/` | 2×2 neutral table | Detail | model + policy + scope | None | Table |
| Current Capital evidence | `/` | Capital group card + table | Primary | comparability group | Optional detail | Cards + table |
| Manual/non-comparable CapitalExperiments | `/` | Separate experiment block | Detail | mode/config | Native expand | `<details>` + table |
| Previous/next day | `/daily/` | Navigation | Primary | date | Links | `<a>` / button-styled links |
| League filter | `/daily/` | GET select | Primary | competition | Submit | `<select>` + submit |
| Match summary | `/daily/` | Dense row/card | Primary | date/league | Expand | `<summary>` |
| Prediction per model | `/daily/` | Nested table | Detail | match | None | Table |
| Decision per policy | `/daily/` | Nested table | Detail | match | None | Table |
| Availability explanation | both | Inline reason text / badge + detail | Primary where material | status/reason | Optional disclosure | Text + badge; never color-only |
| Operational diagnosis link | global nav / material incident notice | Link | Secondary | N/A | External localhost link | Normal anchor labelled “Diagnóstico operativo” |

# 17. Styling decision

## 17.1 Styling option comparison

Only two options are necessary; a third framework does not add enough value to justify another dependency choice.

| option | integration cost | dependencies | JS | tables/cards/badges/pagination | accessibility baseline | local/offline suitability | maintenance | recommendation |
|---|---|---|---|---|---|---|---|---|
| **Bootstrap 5 compiled CSS, vendored locally** | Low | One compiled CSS asset + optional small project CSS | **None required** for FS-009 | Strong built-in classes for grid, tables, cards, badges, forms and pagination | Good semantic compatibility when HTML is authored correctly; framework does not replace WCAG work | **Excellent** when stored under Django static files; no runtime CDN | Low; version can be updated deliberately | **RECOMMENDED** |
| **Minimal custom CSS only** | Medium | Project CSS only | None | Everything must be designed/maintained manually | Fully controllable, but accessibility/consistency depends more on project CSS decisions | Excellent | Higher ongoing UI maintenance for common patterns | Valid fallback, but not preferred for this reporting scope |

## 17.2 Bootstrap delivery contract

FS-009 should introduce Bootstrap as a lightweight UI asset, not claim it already exists in Finsport.

Recommended asset model:

```text
Bootstrap 5.3.x compiled CSS
→ stored in project static assets
→ served by Django/Nginx static handling
→ no CDN dependency at runtime
→ no Sass compilation requirement
→ no Node/npm build pipeline
```

Current official Bootstrap documentation exposes ready-to-use compiled CSS; as of the research date the current 5.3 documentation reports Bootstrap 5.3.8. The ticket should not hard-code “always 5.3.8 forever”; preflight should choose the current compatible 5.x compiled asset and record it normally in the implementation diff.

Because FS-009 uses native `<details>`, it does not need Bootstrap JS. Bootstrap 5 also does not require jQuery. HTMX is not required.

## 17.3 Typography, spacing and density

- Use Bootstrap/system font stack; no external webfont requirement.
- Normal base text around browser/Bootstrap defaults; do not set a tiny dashboard font.
- Use compact but readable table spacing (`table-sm` style density is appropriate for the single-operator data tables).
- Keep section headings visually stronger than metric labels.
- On narrow screens, allow horizontal table scrolling rather than hiding metric columns silently.
- Avoid ornamental shadows/animations; hierarchy should come from spacing, headings, borders and restrained badges.

# 18. Semantic visual language and accessibility

## 18.1 Status semantics

Color is supplemental, never the sole carrier of meaning.

| Semantic state | Text label example | Visual treatment |
|---|---|---|
| Positive observed result | `Líder observado` | restrained success/accent badge **plus text** |
| Negative produced result | `Resultado desfavorable` | danger/negative styling **plus text/value** |
| Warning / degraded | `Degradado` | warning badge **plus reason text** |
| Unavailable | `No evaluable` | neutral/secondary or warning treatment depending reason **plus explanation** |
| Pending | `Pendiente de resolución` | neutral badge + text |
| Operational failure | `Falló` | danger badge + “Revisar diagnóstico operativo” link when appropriate |
| Informational | `Solo descriptivo` / `No comparable` | info/secondary badge + text |

Do not use green to imply scientific proof or red to imply a policy should be dropped.

## 18.2 Tables

- Use `<caption>` when the table context is not otherwise explicit.
- Use `<th scope="col">` and `<th scope="row">` where appropriate.
- Keep `N`, period and league scope visible near metrics.
- Do not encode correct/incorrect only with background color; also show `Correcta` / `Incorrecta`.
- Do not hide unavailable reasons only in hover tooltips. Reasons must be readable in visible detail/disclosure content.

## 18.3 WCAG baseline

Use WCAG 2.2 as the accessibility reference:

- text contrast at least 4.5:1 for normal text and 3:1 for large text under SC 1.4.3;
- do not use color as the only visual means under SC 1.4.1;
- preserve keyboard operation/focus through native links, forms and `<details>`;
- set the page language to Spanish (`lang="es"` or the project’s chosen Spanish locale tag);
- keep labels explicit and navigation consistent.

# 19. Responsibility and current/future boundary

| need | FS-009 | FS-010 | FS-011 / later evidence-guided work |
|---|---|---|---|
| Human historical reporting | **Yes** | Small later Capital UI delta after longitudinal evidence exists | May consume/extend reporting as evaluator output requires |
| Daily match inspection | **Yes** | No required redesign | Only if evaluator findings justify a later change |
| Prediction metric calculation already available | Display only | No new model integration required by this sequence | Evaluator may assess evidence |
| Decision metric calculation already available | Display only | Not the focus | Evaluator may assess evidence |
| Current Capital baseline display | **Yes** | — | — |
| Common longitudinal CapitalPolicy comparison on growing real resolved evidence | No | **Yes — research/implementation target of FS-010** | Evaluator consumes resulting evidence later |
| Automatically include `MONTE_CARLO`/`STRESS` in longitudinal process | No | **OPEN for FS-010 methodology** | — |
| Small frontend update to show FS-010 longitudinal Capital results | No initial implementation beyond extensible UI | **After FS-010 results/contract** | — |
| Winner selection | **No** | Capital longitudinal evidence only; no final integrated winner mandate | **FS-011 evaluator / later product decision** |
| Model combination / ensemble | **No** | No | **FS-011/later research if evidence warrants** |
| DROP/PROMOTE recommendations | No | No integrated evaluator responsibility | **FS-011 evaluator**, then main-chat/F008 disposition |
| Sample sufficiency thresholds | **No arbitrary thresholds** | Do not freeze globally unless FS-010 specifically needs capital methodology | **FS-011 research/evaluator** for integrated evaluation |
| Sequential evaluation / multiple testing | No | Only if FS-010 capital methodology explicitly requires it | **FS-011 evaluator** for integrated process |
| Automatic CapitalPolicy selection | No | **No** — produce longitudinal evidence, not automatic selection | FS-011/later decision if justified |
| Evaluator JSON/export/API | **No** | No requirement from FS-009 | FS-011 decides its own direct DB methodology; no precommitted export |
| Real financial execution | **Forbidden** | Forbidden | Requires a separate future explicit product/safety decision; not implied by evaluator |

# 20. Admin / reporting / Grafana boundary

The three surfaces have distinct responsibilities:

```text
/
→ FS-009 human reporting
→ historical evidence + daily inspection

/admin/
→ Django Admin / audit
→ detailed objects, IDs, relations and technical data inspection

http://localhost:3000/
→ Grafana operational incident diagnostics
→ Loki + Alloy + observability watchdog evidence
```

Moving the Django Admin mount from `/` to `/admin/` is part of FS-009 because `/` becomes the reporting home. The internal Admin functionality is not redesigned.

FS-009 must not embed Grafana via iframe and must not duplicate Loki events, stacktraces or incident dashboards. It may provide a normal labelled link to Grafana when an operational status warrants deeper diagnosis.

# 21. Falsification criteria

Reject or revise the FS-009 proposal if implementation would require any of the following:

1. Conflating Prediction accuracy with Decision hit rate.
2. Treating `NO_BET` as failure or optimizing coverage as inherently better.
3. Treating `Prediction correct + actionable Decision` as a winning Decision/PnL without checking the selected action.
4. Calculating economic Decision results without timestamp-valid price provenance.
5. Inventing unavailable/NO_BET causes instead of reading persisted reasons.
6. Presenting a Capital leaderboard across different modes, Decision streams, initial bankrolls, configs or samples as if directly comparable.
7. Describing `stake_concentration` as Gini or using initial bankroll as the denominator for `max_stake_pre_bankroll_ratio`.
8. Defining practical ruin with an arbitrary UI threshold instead of engine semantics.
9. Claiming CapitalPolicy families are unimplemented.
10. Adding a longitudinal all-policy automation to FS-009.
11. Adding a separate SPA/frontend service, Node build pipeline or runtime CDN dependency.
12. Requiring Bootstrap JS/HTMX where native HTML satisfies the interaction.
13. Making Grafana part of the reporting page instead of leaving it as operational diagnostics.
14. Adding new markets, sport filters, complete odds-history requirements, new model integration or other features outside PRE-FS-009.
15. Presenting simulated units/PnL/bankroll as real financial execution.
16. Declaring scientific winners, universal policies or sample-sufficiency thresholds.

# 22. What can be closed now vs preflight

## 22.1 Product/statistical/UI decisions closed by this research

- `/` is the historical reporting home.
- Django Admin moves to `/admin/` and retains its audit role.
- Grafana remains at `localhost:3000` for operational diagnostics; no embed.
- Prediction summary baseline is the existing multiclasse metric set plus sample/availability context.
- Decision summary uses evaluated/actionable/coverage/NO_BET/hit behavior with price availability explicitly separated.
- Prediction × Decision uses neutral 2×2 descriptors; economic outcome is separate.
- Model agreement is descriptive table-level evidence, not ensemble logic.
- Capital displays current evidence only and uses FS-004 metrics/semantics.
- Capital policies and evaluation modes are separate dimensions.
- Bootstrap 5 compiled CSS is introduced locally as static asset; no Node/CDN runtime.
- `<details>` is the initial disclosure primitive; no JS/HTMX requirement.
- Daily view shows every model and every Decision policy separately.
- Availability explanations come from persisted reasons with a neutral unknown fallback.
- Financial language uses simulated units/exposure/PnL/bankroll.
- No evaluator export/API is created.

## 22.2 Preflight facts still to confirm

These are implementation facts, not product research questions:

- exact current URL wiring and templates/static layout after FS-008;
- exact concrete metric/reason fields and payload shapes currently persisted or derivable;
- exact `calibration` representation already implemented and the simplest faithful HTML rendering;
- exact current policy/model/config display identities;
- current DB evidence inventory and which CapitalExperiments/comparability groups actually exist;
- exact current Bootstrap-compatible static asset placement conventions;
- query performance/need for bounded pagination on the real dataset;
- whether inline `<details>` payload size is materially problematic; only if it is should HTMX/separate detail be reconsidered.

## 22.3 Explicit non-goals

FS-009 does not:

- choose a model, Decision policy or CapitalPolicy winner;
- build or recommend an ensemble;
- define sample-sufficiency thresholds;
- define DROP/PROMOTE rules;
- design sequential evaluation/multiple-testing policy;
- automate longitudinal all-policy Capital evaluation;
- decide automatic Monte Carlo/Stress cadence;
- create evaluator export/JSON/API/DRF;
- implement new Prediction models or new Decision/Capital semantics;
- add markets/sports;
- redesign Admin;
- duplicate Grafana;
- create a separate frontend service;
- create real financial side effects.

# 23. New Work Discovered

The research confirms only the already approved future sequence; it does not invent priority beyond it.

1. **FS-010 — longitudinal CapitalPolicy evaluation with growing real resolved evidence.**
   - Evidence: FS-004 has policy families/modes, while the current automatic pipeline mainly yields the normalized FLAT_UNIT/REPLAY baseline.
   - Impact: a common longitudinal evidence process is required before honest ongoing all-policy comparison exists.
   - Recommendation: FS-010 defines its methodology/configuration and whether/how `MONTE_CARLO` or `STRESS` participate.

2. **Small frontend delta after FS-010.**
   - Evidence: FS-009 should not render comparison dimensions that do not yet exist.
   - Impact: once FS-010 produces longitudinal capital evidence, reporting needs a bounded extension to expose it.
   - Recommendation: keep FS-009 templates/components structurally simple enough to add another comparable Capital group later; do not implement empty future controls now.

3. **FS-011 — evaluator of Prediction + Decision + Capital.**
   - Evidence: scientific winner selection, sample sufficiency, sequential evaluation, DROP/PROMOTE and model complementarity require methodology beyond descriptive reporting.
   - Impact: FS-009 must remain observational.
   - Recommendation: FS-011 owns integrated evaluator research/logic; no precommitted export schema from FS-009.

# 24. Durable project references

These project documents are the durable Finsport basis for the report:

- `F001_contexto_producto_finsport_v1.1.md` — product mode, operator, Prediction/Decision/Capital boundaries and no real betting.
- `F002_contexto_dominio_reglas_privacidad_seguridad_finsport_v1.2.md` — provenance, Prediction/Decision semantics, `NO_BET`, temporal price validity, capital ruin/batching/metrics semantics.
- `F003_contexto_tecnico_arquitectura_finsport_v1.4.md` — implemented Prediction/Decision/Capital architecture, FS-004 capital semantics, observability architecture.
- `F006_roadmap_backlog_finsport_v1.3.md` — reporting direction and historical roadmap context; the explicit FS-009 → FS-010 → FS-011 sequencing supplied with this research correction governs this report where it is more specific/current.
- `F008_guia_definicion_secuenciacion_tickets_finsport_v1.3.md` — ticket boundary/readiness and implemented-but-not-operational dispositions.
- `F010_guia_investigacion_handoff_research_finsport_v1.1.md` — evidence classification, metric-definition discipline, falsification and research handoff.

# 25. Durable external bibliography

Access date for current web documentation: **2026-08-31**.

**[R1] Strictly Proper Scoring Rules, Prediction, and Estimation**
Authors: Tilmann Gneiting; Adrian E. Raftery
Publication: *Journal of the American Statistical Association*, Vol. 102, Issue 477, 2007
DOI/URL: https://doi.org/10.1198/016214506000001437
Use in this report: authoritative basis for proper scoring rules and the role of logarithmic/quadratic scores in probabilistic forecast evaluation.

**[R2] Verification of Forecasts Expressed in Terms of Probability**
Author: Glenn W. Brier
Organization/Journal: U.S. Weather Bureau / *Monthly Weather Review*
Publication date: 1950-01-01
DOI/URL: https://doi.org/10.1175/1520-0493(1950)078%3C0001:VOFEIT%3E2.0.CO;2
Use in this report: original Brier probability-score reference.

**[R3] A Scoring System for Probability Forecasts of Ranked Categories**
Author: Edward S. Epstein
Organization/Journal: American Meteorological Society, *Journal of Applied Meteorology*
Publication date: 1969-12-01
DOI/URL: https://doi.org/10.1175/1520-0450(1969)008%3C0985:ASSFPF%3E2.0.CO;2
Use in this report: original Ranked Probability Score reference.

**[R4] `log_loss` — scikit-learn 1.9.0 documentation**
Organization: scikit-learn developers
Publication/update: living versioned documentation, scikit-learn 1.9.0; current page accessed 2026-08-31
URL: https://scikit-learn.org/stable/modules/generated/sklearn.metrics.log_loss.html
Access date: 2026-08-31
Use in this report: current technical definition/input shape for multiclass Log Loss/cross-entropy.

**[R5] Probability calibration — scikit-learn 1.9.0 documentation**
Organization: scikit-learn developers
Publication/update: living versioned documentation, scikit-learn 1.9.0; current page accessed 2026-08-31
URL: https://scikit-learn.org/stable/modules/calibration.html
Access date: 2026-08-31
Use in this report: reliability/calibration interpretation and warning that proper scores such as Brier combine calibration with other forecast-quality components.

**[R6] Download · Bootstrap v5.3**
Organization: Bootstrap team and contributors
Publication/update: living Bootstrap 5.3 documentation; page reports current version 5.3.8 at access time
URL: https://getbootstrap.com/docs/5.3/getting-started/download/
Access date: 2026-08-31
Use in this report: availability of ready-to-use compiled CSS/JS and the ability to consume compiled assets without adopting Bootstrap’s source build tooling.

**[R7] `<details>`: The Details disclosure element**
Organization: Mozilla Developer Network (MDN)
Publication/update: living web-platform documentation; page current at access time and reports broad browser availability since January 2020
URL: https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/details
Access date: 2026-08-31
Use in this report: native disclosure behavior supporting the no-JavaScript initial match expansion recommendation.

**[R8] Web Content Accessibility Guidelines (WCAG) 2.2**
Organization: World Wide Web Consortium (W3C), Accessibility Guidelines Working Group
Publication/update date: W3C Recommendation, 2024-12-12
URL: https://www.w3.org/TR/WCAG22/
Access date: 2026-08-31
Use in this report: SC 1.4.1 Use of Color, SC 1.4.3 Contrast (Minimum), keyboard/focus and related accessibility baseline.

# RECOMMENDED FS-009 PRODUCT CONTRACT

## Routes

```text
/
→ FS-009 historical reporting home

/daily/
→ secondary day/league match view using server-side GET filters

/admin/
→ Django Admin / detailed audit
→ Admin mount moves here as part of FS-009

http://localhost:3000/
→ Grafana operational diagnostics
→ backed by Loki + Alloy + observability watchdog
```

No additional public/API route is required by this contract. Match detail is initially inline via native `<details>` on `/daily/`; a separate match-detail route is not required.

## Pages

FS-009 has two reporting pages/surfaces:

1. `/` — historical evidence summary.
2. `/daily/` — day-by-day match inspection.

`/admin/` is not a reporting page; it remains Django Admin/audit. Grafana remains a separate operational surface.

## Historical home

The first content on `/` is historical evidence, not today’s fixtures.

Order:

1. current reporting scope / general evidence state;
2. Modelos predictivos;
3. Políticas de decisión / selección;
4. Políticas de capital.

Default to total available history. Support explicit league and `date_from`/`date_to` filters. Do not define an arbitrary fixed “recent” window. When a period filter is active, label it explicitly as “Periodo seleccionado”.

Prefer comparison tables and small cards over a wall of charts.

## Prediction summary

One row per model/config in the selected scope, based primarily on Finsport’s existing metrics:

```text
sample_count
accuracy
log_loss
multiclass_brier
rps
calibration
```

Also show prediction availability context. Put `confusion_matrix`, class mix and calibration detail behind disclosure/detail.

Never reduce the page to accuracy alone. Do not add precision/recall/F1/FPR/ROC-AUC to the initial contract.

A “mejor resultado observado en esta métrica” marker is allowed only with visible sample, period, league scope and availability, and only inside a valid comparison context.

## Decision summary

One row per Decision policy/config with:

```text
evaluated_fixtures
actionable decisions
coverage
no_bet_count
no_bet_rate
resolved actionable sample
hits
losses
hit_rate
valid-price coverage
```

Coverage, actionable rate, `NO_BET` rate and action mix are descriptive; there is no generic “more is better” direction.

Keep economic evidence in a visibly separate sub-block and only where provenance permits it:

```text
economic_decisions
flat_unit_pnl (simulated, 1u basis)
roi (simulated)
mean_selected_odd
mean_predicted_ev
```

## Prediction × Decision

Use neutral cross-cells only:

```text
Prediction correcta + Decision accionable
Prediction incorrecta + Decision accionable
Prediction correcta + NO_BET
Prediction incorrecta + NO_BET
```

Show count, denominator and percentage.

“Prediction correcta + NO_BET” may be labelled “acierto predictivo en partido no seleccionado”. It is not a lost-profit claim.

For actionable Decisions, show selection hit/loss and simulated economic result separately according to the **actual selected action** and real match outcome. Never infer Decision success from Prediction correctness.

## Capital summary

FS-009 displays only Capital evidence that currently exists.

Always distinguish:

```text
CapitalPolicy family
vs
evaluation mode
```

Primary current automatic evidence is the normalized prospective baseline:

```text
REPLAY
initial bankroll 100u
FLAT_UNIT
stake 1u
current DIXON_COLES / MODAL_ALL Decision stream
```

Show return and risk together, using FS-004 metrics. Primary compact values should include terminal bankroll, total PnL/ROI, maximum drawdown, practical ruin state/probability when applicable, and peak relative exposure/concentration when applicable, always with Decision/sample and mode/config context.

Exact semantics required:

```text
total_staked
= sum(applied_stake)

turnover
= total_staked / initial_bankroll

max_stake_pre_bankroll_ratio
= max(applied_stake / bankroll_before)

stake_concentration (multi-path aggregate)
= mean over paths of max(applied_stake / pre_batch_bankroll)
= applied/funded actions only

practical_ruin
= engine-defined inability to continue under capital constraints / termination semantics
= no invented percentage threshold
```

FS-004 CapitalPolicy families are already implemented. FS-009 does not automate a common longitudinal all-policy comparison.

## Daily view

`/daily/` supports:

```text
← Día anterior
selected date
Día siguiente →
league filter
```

Each match summary shows league, kickoff, home, away, status and final result when available.

Each match must expose **every relevant Prediction model and every Decision policy separately**. There is no “predicción principal” or “predicción oficial”. A descriptive agreement count may supplement, never replace, the individual rows.

## Match detail

Initial detail is a native `<details>` disclosure inside the daily list.

Prediction detail per model:

```text
P(HOME)
P(DRAW)
P(AWAY)
predicted outcome
actual outcome when resolved
correct/incorrect when evaluable
availability/reason
```

Decision detail per policy:

```text
action
NO_BET or selected outcome
persisted reason
selected timestamp-valid price when present
actual outcome
selection hit/loss when evaluable
simulated economic result only when provenance permits
```

Do not require per-match calibration, complete odds history or new match statistics.

## Filters/navigation

Historical home:

```text
league/competition
date_from
date_to
```

Daily view:

```text
date
league/competition
previous/next day
```

All are server-side GET navigation. No sport filter or new-market filter.

## Availability explanations

Mandatory presentation rule:

```text
persisted internal reason
→ verified Spanish mapping
→ plain-language explanation
→ neutral fallback for unclassified reason
```

The fallback must display the actual internal code and say it is not yet classified; it must not guess the cause.

The UI must distinguish at least:

```text
needs more valid history
missing timestamp-valid market evidence
pending/unresolved real outcome
capability not operational/integrated
operational failure/degradation
capital simulation outcome/termination
```

Never claim a resource bottleneck without operational evidence.

## Styling

Introduce **Bootstrap 5 compiled CSS** as a local static asset:

```text
compiled CSS
→ stored in Django static files
→ served locally
→ no CDN runtime dependency
→ no Node/build pipeline
```

Add only a small project CSS file for Finsport-specific spacing/state refinements.

Use Bootstrap/system font stack. Do not add external Noto/Roboto webfonts unless a later demonstrated requirement justifies them.

Use compact responsive tables, cards, badges and normal form controls. Status meaning must always include text, not color alone.

## JavaScript/HTMX

Initial requirement:

```text
none
```

Use `<details>/<summary>` for match expansion. Bootstrap JS and HTMX are not required in FS-009. They may be reconsidered only if technical preflight demonstrates a material payload/interaction problem that native server-rendered HTML cannot solve simply.

No SPA and no separate frontend service.

## Admin boundary

`/admin/` remains Django Admin for detailed audit of objects, IDs, relations and technical data.

FS-009 **does** move the Admin mount from `/` to `/admin/` so `/` can become reporting.

FS-009 does **not** redesign Admin internals, add user-management scope, or turn Admin into the reporting UI.

## Grafana boundary

`http://localhost:3000/` remains operational incident diagnosis through:

```text
Grafana
+
Loki
+
Alloy
+
observability watchdog
```

FS-009 does not embed Grafana or reproduce operational logs/stacktraces. It may provide a labelled normal link for diagnosis when appropriate.

## Accessibility

Use WCAG 2.2 as baseline:

- normal-text contrast ≥ 4.5:1 and large text ≥ 3:1;
- never use color as the only indicator;
- semantic headings and native controls;
- table captions/headers with proper scope;
- keyboard-operable links/forms/details;
- Spanish page language;
- responsive/reflow behavior with horizontal table scrolling rather than silently dropping information.

## Explicitly deferred work

```text
FS-010
→ longitudinal CapitalPolicy evaluation over growing real resolved evidence
→ decides its own methodology and whether/how MONTE_CARLO/STRESS participate
→ followed by a small frontend delta to expose new longitudinal Capital evidence

FS-011
→ evaluator of Prediction + Decision + Capital
→ scientific evaluation/recommendation questions such as winner selection,
   sample sufficiency, sequential evaluation, DROP/PROMOTE and model complementarity
```

Also deferred/not part of FS-009:

- model ensembles/combinations;
- new Prediction models;
- new Decision/Capital semantics;
- automatic CapitalPolicy selection;
- evaluator JSON/API/export;
- new sports/markets;
- real financial execution.

## New Work Discovered

1. **FS-010 longitudinal CapitalPolicy evaluation** — already approved sequence; methodology remains to be researched/defined there.
2. **Bounded post-FS-010 frontend delta** — expose the new longitudinal Capital evidence once it actually exists.
3. **FS-011 integrated evaluator** — consume Prediction + Decision + Capital evidence and make scientifically governed recommendations; no implementation details are frozen by FS-009.
