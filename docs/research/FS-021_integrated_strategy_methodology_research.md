# FS-021 — Investigación previa para seleccionar la estrategia global integrada

**Proyecto:** Finsport · **Fecha:** 2026-09-23 · **Versión:** `FS021_RESEARCH_PRE_TICKET_V2_FINAL_SETTLEMENT_GATE`\
**Estado de investigación:** `RESEARCH_COMPLETE__PENDING_SOURCE_RECONCILIATION`\
**Estado del ticket:** `NOT_YET_READY_FOR_CODEX`; F008 debe reconciliar el nuevo contrato fuente por fuente y emitir DoR.\
**Alcance:** investigación y diseño exclusivamente. **Ningún torneo económico FS-021 ejecutado, ningún ganador global seleccionado, ningún runtime ni fuente ACTIVE modificados.**

## 0. Decisión ejecutiva para F008

FS-021 evaluará la **familia íntegra de 231 combinaciones** de FS-019/E2.3, sin cribado económico. Cada una inicia con **una sola banca global de 100u**, compartida entre sus 1 o 10 lanes: ninguna lane tiene sub-banca ni transfiere dinero a una lane principal. El nuevo contrato `FS021_OPERATIONAL_DEPLETION_5U_AFTER_ALL_OPEN_V2` detiene definitivamente el path **sólo después de liquidar absolutamente todas las posiciones OPEN** y comprobar, tras el batch completo del mismo instante, `bankroll_equity <= Decimal("5")` y `open_count == 0`. Si cruza 5u con OPEN vivas, entra en una **pausa reversible de nuevas colocaciones** hasta liquidarlas; una recuperación posterior a más de 5u permite continuar sin inventar apuestas retrospectivas. Tras la parada definitiva, se conserva la cohorte completa y toda la evidencia, pero se deja de recorrer partidos posteriores: las filas BET futuras se clasifican por índice como no ejecutadas, y las NO_BET conservan su identidad. El agotamiento en cualquier lag veta la baseline práctica, **no borra** al candidato de las 231 comparaciones científicas.

**Nuevo alcance de lags:** T+150m es el **único lag con inferencia bootstrap confirmatoria condicionada**; T+120m y T+130m conservan un recorrido observado de las 231 combinaciones, para sensibilidad de ejecución, veto práctico y regla robusta. No hay bootstrap completo a 120m/130m en FS-021 v1. Se conservan **todos los candidatos** y los **tres tamaños de bloque 1w/2w/4w**, 5.000 réplicas cada uno, a T+150m. Esto sustituye explícitamente el plan de nueve celdas de E2.3 para FS-021, sin reescribirlo retrospectivamente ni atribuirse la antigua conclusión científica sobre estabilidad cross-lag. Se mantiene disponible la extensión futura a las nueve celdas si el producto la aprueba con un propósito científico adicional.

**Selección práctica antes del resultado:** entre paths de los 231 con evidencia completa, sin ruina/terminación ni agotamiento 5u en **ningún** lag, y con actividad mínima explícita, maximizar `min(TOTAL_RETURN_120,TOTAL_RETURN_130,TOTAL_RETURN_150)`. Desempatar por retorno T+150 descendente, peor máximo drawdown ascendente, mínimo número de colocaciones en los tres lags descendente, peor exposición reservada ascendente, e identidad canónica ascendente. Ninguna victoria observada, incluido DIXON_COLES+VALUE 0.05, obtiene prioridad extra. La disposición científica se calcula y publica **por separado**, sin convertir la selección práctica en superioridad demostrada.

Si no hay ninguna combinación activa que pase los vetos, publicar una **composición identificable para diagnóstico** si la evidencia está completa, `DIAGNOSTIC_ONLY__NO_NEW_STAKES`, sin autorización para abrir nuevas apuestas simuladas en esa baseline; no simular que una trayectoria agotada es económicamente admisible. Ante integridad física/semántica faltante y recuperable, **STOP técnico**, restaurar el artefacto y no fabricar baseline.

**Frontera:** FS-021 evalúa/publica; FS-022 podrá plantear simulación prospectiva, shadow limitado, frontend y eventual cutover bajo nueva decisión; las apuestas reales están fuera de alcance y requieren un gate independiente.

---

## 1. Autoridad y material utilizado

### 1.1 Fuentes aceptadas (hechos heredados, sin recalcularlos)

1. `FS-020_handoff_final.md` y `FS-020_feedback.md` entregados el 2026-09-23. El handoff declara cierre/merge/deploy **en su escenario de cierre**; su declaración no sustituye logs operacionales. Autoridad local aceptada: `GLOBAL_PREDICTION_V1=MARKET_CONSENSUS/fs013-market-consensus-v2`; `GLOBAL_DECISION_V1=MODAL_ALL/fs003-modal-all-v1`; `GLOBAL_CAPITAL_V1=FRACTIONAL_KELLY`, `lambda=0.25`, `max_lanes=10`, selección práctica `FS020_MAXIMIN_LAG_RETURN_V1`, disposición científica `UNSTABLE`.
2. Repo `master` inspeccionado en modo lectura, principalmente `docs/research/FS-018_global_prediction_v1.json`, `FS-019_global_decision_v1.json`, `FS-019_cross_layer_confirm_v1.json`, `FS-020_global_capital_v1.json`, `FS-020_capital_baseline_evidence/aa93332a114f5e0a/run.json`, `FS-020_e2_4_v2r_reconciliation.json`, `FS-020_global_capital_methodology_research.md`; y código `football/experiments/capital_events.py`, `capital_runner.py`, `football/capital/policies.py`.
3. Checkpoints E2 Phase 1/2, E2.3 corregido y E2.4/V2R, incluidos los manifiestos de 231 brazos, cohorte bootstrap y binding de 33 streams, disponibles en esta conversación. Los resultados financieros FS-018/019/020 siguen **inmutables**.
4. Fuentes ACTIVE de Project: F001 v1.8, F003 v1.12, F006 v1.11, F008 v1.7 y F010 v1.5, consumidas para detectar obligaciones y dependencias. Reflejan principalmente el estado post-FS-019; el estado FS-020 posterior procede del handoff/repo, no de una reescritura tácita de ACTIVE.
5. Referencias metodológicas dirigidas, **no evidencia empírica Finsport**: White (2000), *A Reality Check for Data Snooping*, https://doi.org/10.1111/1468-0262.00152 ; Hansen (2005), *A Test for Superior Predictive Ability*, https://doi.org/10.1198/073500105000000063 ; Hyndman (2023), *Forecast model selection*, https://fpp.robjhyndman.com/hyndsight/model-selection.html . Ilustran por qué reutilizar una muestra para búsqueda y evaluación exige controlar multiplicidad y validar después en el tiempo; **no sustituyen** el método max-t específico de E2.

### 1.2 Identidades físicas conocidas; obligaciones pendientes del futuro preflight

| Artefacto | Identidad SHA-256 o máquina | Situación |
|---|---|---|
| Research FS-020 canónico post-hook | `808f5ca4339382de986a285e22fb55d4d64165969befddf36c5ab0861049e61b` | vinculado por autoridad FS-020 |
| FS-020 `run.json` | `a552ac781ab13d170f5cd8960167a2dbf5c2d505b2433f524a17c305342eae33` | evidencia compacta en repo; revalidar bytes del checkout real |
| FS-020 execution | `77d6db0a93ad357f5eda92a858dc6f8d885553d43b53dd021be84ea39b43b9d7` | retained UAT-4 consumer FS-021 |
| FS-020 run | `aa93332a114f5e0aaaad8c59b9b60048b15c02d40e380b5deae41e8f32e08701` | frozen |
| V2R reference | `E2_PHASE3_EVENT_TIME_REFERENCE_V2R_LANE_FIRST`, SHA `fa55e297ec2b334b6b8cf2aa70bd62974f98f1994a951446d59d9047c1e8e833` | aceptado por reconciliación; no equiparar al V2 ejecutable original no recuperado |
| FS-018 multi-model bundle | `8776ff4e91bdbc93d5e3f7826e9b6b28a1128b65220f2dbdaf0475992c577db6` | `PRESERVE_ACTIVE`; verificar físicamente en preflight FS-021 |
| FS-018/019 common prediction cohort | `08d8f7c2852444c2e66ed28c4075e2bc51708d3ac918cdb7cf75daf858ae2c1c` | 1.877 Matches |
| common 1.877 identity — Phase-3 binding | `6b73234190eabfc77c0b597090576c52e798bbe8c902098c965215d38e89c131` | verificar restore/identidad en FS-021 |
| exact 33 P×D matrix identity | `05ac15800a11ca887d3b1802ae3cdace0a85aa11e7e5d942be88805f51c23006` | Phase-3 binding; 33 streams únicos |
| 33×7 conceptual family identity anterior | `279c2bde5e164be9d30bc5e42502dfcedf1fcdb938abfd123bef58d8b439286c` | se preserva como identidad de **matriz conceptual**; el spec FS-021 nuevo obtiene otra identidad por lag/depletion |

Al menos 61.941 filas de P×D (=33×1.877) ya fueron materializadas/regeneradas en Phase 3 y hash-verificadas, pero las rutas externas del host deben restaurarse/validarse para este consumidor. `tmp/` no certifica retención. FS-020 retiene evidencia adicional en `/home/ljarufe/Documents/finsport/FS-020_e2_4_v2r/` y `/home/ljarufe/Documents/finsport/FS-020_uat4/<execution_id>/`, protegida por `RETENTION_INDEX.tsv`.

### 1.3 Por qué no podemos inferir el resultado FS-021 de los rankings previos

FS-018 midió log-loss predictivo; FS-019 local calculó GLOBAL_PPO sobre 1.906; FS-019 cumulative puntuó 33 P×D sobre 1.877 con apuesta fija; FS-020 evaluó siete Capital sobre MARKET_CONSENSUS+MODAL_ALL y **1.906**. Ninguno ejecutó `33×7` con **banca stateful, 1.877, stop a 5u**. El líder puntual P×D `DIXON_COLES + VALUE 0.05` (GLOBAL_PPO `+0.00965372`, 1.518 BET) fue `OBSERVED_TOP / UNSTABLE / NOT PROVEN SUPERIOR`, con 33/33 supervivientes. FS-020 Kelly cerró 179,62/179,97/179,95u; LEGACY_RECOVERY 5,07/5,07/395,84u (T+120/130/150), diferencia causal de liberación de su única lane, no bug establecido. **La sensibilidad observada justifica conservar los tres recorridos descriptivos, no sus tres bootstraps completos.**

El umbral 5u no tiene efecto retroactivo: FIXED_FRACTION_BANKROLL, que cerró 1,14/1,02/1,27u en FS-020, podría tener otra trayectoria al detenerse **sólo tras su última OPEN**. Un saldo final histórico de 5,07u **no demuestra** cruce terminal del umbral `<=5` con cero OPEN; además, estar por encima de 5u tampoco demuestra que se pueda costear cualquier stake de recuperación. La insuficiencia puntual de efectivo sigue siendo `PENDING_CAPACITY`, no agotamiento por definición.

---

## 2. Población, candidatos y banca: contrato nuevo FS-021

### 2.1 Matriz íntegra, SIN cribado

Predictions/versiones: `DIXON_COLES/fs011-dixon-coles-v2`, `INDEPENDENT_POISSON/fs003-independent-poisson-v1`, `ELO_MULTINOMIAL_LOGIT/fs003-elo-multinomial-logit-v1`, `MARKET_CONSENSUS/fs013-market-consensus-v2`.

Decisions universales: `MODAL_ALL`, `SELECTIVE_CONFIDENCE` de umbral exacto `0.40`, `0.45`, `0.50`, `0.55`, `0.60`. `VALUE` con `minimum_ev` exacto `0.00`, `0.02`, `0.05` **sólo** con los tres Predictions no-Market. `MARKET_CONSENSUS × VALUE` sigue INELIGIBLE por circularidad de precios CURRENT.

Se mantienen exactamente los 33 P×D congelados en el orden de `FS-019_cross_layer_confirm_v1.json`: nueve Dixon, nueve Poisson, nueve Elo y seis Market. Cada uno se cruza con las siete Capital configs en el orden CURRENT siguiente:

| Índice Capital (0-based) | Política | Config exacta | `max_lanes` | Dependencia de la equity actual |
|---:|---|---|---:|---|
| 0 | `FLAT_UNIT` | `{"unit":"1"}` | 10 | no; apuesta fija 1u |
| 1 | `FIXED_FRACTION_BANKROLL` | `{"fraction":"0.05"}` | 10 | sí, `0.05*equity` |
| 2 | `FIXED_TARGET_PROFIT_NO_RECOVERY` | `{"target_profit":"1"}` | 10 | no; `1/(price-1)` |
| 3 | `LEGACY_RECOVERY` | `{"initial_stake":"1"}` | 1 | depende de pérdidas/policy state y cuota, no proporcional automáticamente |
| 4 | `LEGACY_CAPPED` | `{"initial_stake":"1","max_absolute_stake":"5"}` | 1 | depende de recovery state; tope absoluto 5u |
| 5 | `LEGACY_PARTIAL` | `{"target_profit":"1","alpha":"0.5"}` | 1 | depende de pérdidas parciales y cuota |
| 6 | `FRACTIONAL_KELLY` | `{"lambda":"0.25"}` | 10 | sí, `0.25*max(0,(p*price-1)/(price-1))*equity` |

`integrated_index=pd_index*7+capital_index` (0-based). **231 combinaciones estructuralmente elegibles**; no se sustituyen políticas ni se retocan sus parámetros. Los 33 P×D inputs tenían hashes Capital-relevantes distintos: no declarar deduplicación conductual. Toda reducción posterior por scores, siquiera de una técnica que ya perdió localmente, cambiaría la pregunta y no está autorizada en FS-021.

### 2.2 Población y continuidad

Población primaria: mismos 1.877 Match IDs en diez ligas, resultados reglamentarios, evidencia `ODDSPAPI_RECONSTRUCTED_T30_V1`, con oportunidad económica `synthetic_execution_at=kickoff−30m`. **NO_BET permanece una fila completa**, no se eliminan Matches sin apuesta; faltas irrecuperables se registran y bloquean la comparabilidad si afectan un campo obligatorio. No mezclar con los 1.906 del Capital local ni comparar directamente sus saldos.

Cada combinación inicia **su propio** bankroll global con equity=100u, reservas=0, política inicial, OPEN/PENDING vacíos. Se comparte esa banca **entre ligas, días, partidos y todas las lanes del mismo candidato**. Las lanes no reciben 100u por separado. Equity de partida sólo se restablece al iniciar un **path independiente de bootstrap** o un estudio de estabilidad independiente, nunca cada jornada o competencia. El stake se recalcula con la equity/policy state CURRENT al colocar o reintentar; las ganancias ya liquidadas incrementan futuras stakes bajo políticas proporcionales. La capacidad de efectivo es `available_cash=bankroll_equity−reserved_exposure`; reservar stakes no reduce equity contable, sólo efectivo disponible.

---

## 3. Contrato ejecutable `FS021_OPERATIONAL_DEPLETION_5U_AFTER_ALL_OPEN_V2`

### 3.1 Identidad, umbral y regla de cierre DEFINITIVA

Constante exacta `DEPLETION_FLOOR = Decimal("5")` en unidades simuladas `u`, sin moneda real asignada. **No es stake mínimo, saldo por lane, límite de efectivo disponible ni drawdown del 95 %**. Una combinación completa comparte una única equity y un único conjunto de posiciones OPEN. Una lane sólo representa capacidad de concurrencia; al cerrar una posición, el stake reservado se libera y el P&L actualiza directamente la misma equity. No existe transferencia ni reintegro entre sub-bancas por lane.

La única condición de terminación **por este umbral** es:

```python
# Evaluar DESPUÉS de liquidar todas las posiciones vencidas en el mismo instante.
if not OPEN and bankroll_equity <= Decimal("5"):
    status = "OPERATIONAL_DEPLETION"
    stop_new_placements = True
    permanently_stop_future_match_wakes = True
```

Mientras `OPEN` no esté vacío, ningún descenso a 5u o menos puede terminalizar por `OPERATIONAL_DEPLETION`. En cambio, para que puedan llegar a liquidarse **todas** las OPEN sin un flujo infinito de nuevas posiciones, si el batch de settlement deja `equity <= 5u` pero todavía hay OPEN, se activa el estado **reversible** `AWAITING_FINAL_OPEN_SETTLEMENT` y se suspenden nuevas colocaciones; sólo se procesan los settlements de esas posiciones y las expiraciones lógicas de PENDING. Aunque una liquidación intermedia eleve `equity > 5u`, **la pausa continúa mientras exista cualquier OPEN del conjunto ya colocado**: no se abren posiciones adicionales que retrasen artificialmente la evaluación. Sólo después de liquidar la **última** OPEN se decide: si entonces la equity es `>5u`, se sale de pausa y se retoma el flujo normal exclusivamente con oportunidades todavía anteriores a kickoff; si es `<=5u`, se produce el stop irreversible. Un cruce provisional por debajo del umbral **no** equivale a una terminación definitiva.

`OPERATIONAL_DEPLETION` es distinto de `ZERO_STAKE`, `NO_BET`, `PENDING_CAPACITY`, `EXPIRED_CAPACITY`, `BANKROLL_DEPLETED`, `POLICY_TERMINATION` e `INPUT_INTEGRITY_FAIL`. Conservar estas causas de manera no intercambiable. Equity `<=0` es un hard-risk económico aunque haya OPEN pendientes; **no se pierde la obligación de liquidarlas**. El nuevo gate a 5u se decide sólo después del cierre de todas las OPEN. Registrar cualquier episodio intrabatch/intraperíodo `equity<=0` con una bandera `ever_nonpositive_equity` independiente, conservando el veto de riesgo original aun cuando OPEN posteriores recuperen la banca; no presentar tal recuperación como ausencia de riesgo. Una terminación explícita de política mantiene su propio contrato de no nuevas colocaciones y liquidación de OPEN existentes.

### 3.2 Máquina de estados y precedencia Event-Time

```text
ACTIVE
  + equity>5 después de liquidaciones → ACTIVE
  + equity<=5, OPEN>0             → AWAITING_FINAL_OPEN_SETTLEMENT
  + equity<=5, OPEN=0             → OPERATIONAL_DEPLETION (terminal)

AWAITING_FINAL_OPEN_SETTLEMENT
  + batch completo, OPEN>0        → permanece en pausa
  + batch completo, OPEN=0,
      equity>5                    → ACTIVE (reanudación; no retroactividad)
  + batch completo, OPEN=0,
      equity<=5                   → OPERATIONAL_DEPLETION (terminal)

OPERATIONAL_DEPLETION
  → no más policy.request, placement ni procesamiento de partidos futuros
  → conservar exactamente el ledger previo, los inputs de todos los Matches,
    el sufijo de eventos pendientes de ejecutar y el saldo terminal constante
```

Para cada wake `t` de un path todavía no terminal:

1. Liquidar **todas** las OPEN con `settlement_at <= t`, con orden estable `(settlement_at, position_identity)`. En cada settlement: liberar el stake reservado y la lane ocupada; aplicar P&L al equity global; actualizar el estado CURRENT de la política con `policy.settle` y verificar invariantes. Nunca evaluar el gate en medio de varias liquidaciones **del mismo instante**.
2. Una vez terminado el batch, actualizar el registro de riesgo y evaluar `equity` y `len(OPEN)`. Si `equity<=5` con OPEN todavía vivas, entrar en pausa reversible; **no** invocar `policy.request` ni crear nuevas OPEN. **Una vez iniciada, la pausa no termina hasta que `OPEN=0`, aunque el saldo intermedio recupere más de 5u**. Durante ella procesar sólo settlements futuros de las OPEN existentes; cualquier PENDING que llegue a kickoff durante la espera vence como `EXPIRED_CAPACITY`. La pausa no inventa una nueva cuota ni vuelve a generar un T-30 retrospectivo.
3. Si `OPEN` queda vacío: `equity<=5` causa `OPERATIONAL_DEPLETION` **antes de los reintentos o nuevas colocaciones en ese mismo wake**; `equity>5` permite continuar y, si había pausa, reanudar. Si se confirmó depletion, persistir evidencia de cierre, terminalizar PENDING anteriores con causa `PATH_STOPPED_OP_DEPLETION`, registrar el sufijo futuro por índice y **abandonar el event loop del path**. No esperar el kickoff ni los resultados de partidos posteriores.
4. Si sigue ACTIVE, primero expirar los PENDING ya fuera de plazo (`kickoff<=t`), conservar los `NO_BET`, combinar PENDING todavía válidos con oportunidades nuevas y ordenar `(EV_unit DESC, kickoff ASC, identity ASC)`. Aplicar V2R: comprobar `kickoff`/lane **antes** de `policy.request`. Si lane no disponible, `PENDING_CAPACITY` sin stake request ni posición; con lane libre, `policy.request` usando equity/estado actuales; evaluar terminación explícita, cero stake, cash insuficiente y finalmente placement, en ese orden CURRENT. Una reserva de efectivo no reduce equity, sólo `available_cash=equity-reserved_exposure`.
5. Ni una lane libre ni una oportunidad futura rehabilitan una combinación que **ya cumplió** el stop definitivo. El estado ACTIVE sólo puede recuperarse desde la **pausa reversible** antes del cierre de todas las OPEN.

Una combinación que permanezca por encima de 5u pero no pueda costear un stake particular recibe la clasificación CURRENT `PENDING_CAPACITY` y su expiración reglada, no un agotamiento ficticio. `LEGACY_RECOVERY` puede pedir más que su banca sin cumplir el umbral; no se elimina por heurística.

### 3.3 Ahorro real de cómputo y conservación TOTAL de evidencia

La corrida **deja de simular** el path cuando se confirma `OPERATIONAL_DEPLETION` con `OPEN=0`: no recorre los siguientes `event_time`, no llama otra vez a Capital/Decision ni espera por partidos posteriores. Esto es un ahorro exacto de trabajo, **no una eliminación de filas ni una reducción de candidatos**.

Cada candidato mantiene una referencia immutable al stream P×D completo de 1.877 Matches y a la cohorte/skeleton común de resultados y odds. El ledger propio registra todos los eventos realmente procesados hasta `terminal_at`; para las oportunidades que quedan después se conserva un `unprocessed_suffix` (`start_index`, `last_index`, `match_stream_sha256`, counts preindexados de BET/NO_BET y regla de expansión determinista). Al materializar una vista completa, las BET no ejecutadas se proyectan como `NOT_EXECUTED_AFTER_OP_DEPLETION`, con motivo y timestamp de stop; los `NO_BET` originales siguen siendo `NO_BET`, no pérdidas ni apuestas canceladas. El resultado reglamentario y la predicción histórica de esos Matches **permanecen en la evidencia upstream**, aunque el path Capital no los espere ni los liquide. Separar contadores de apuestas colocadas, oportunidades dejadas de evaluar y resultados históricos preservados.

La equity terminal se mantiene constante hasta el horizonte comparable de esa réplica/lag; persistir `total_return=(terminal_equity-100)/100`, `terminal_at`, `last_open_settlement_at`, `op_depletion_at`, `equity_at_depletion`, `open_count_at_depletion=0`, `reserved_exposure_at_depletion=0` sujeto a invariantes Decimal, `ever_below_floor_while_open`, `pause_entry/exit`, `ever_nonpositive_equity`, `remaining_bet_count`, `remaining_no_bet_count` y `unprocessed_suffix_sha256`. Si el drawdown sigue en curso, su duración a horizonte común se calcula aritméticamente sin procesar partidos posteriores.

Un oracle de conformance debe comparar `scalar_full_scan` frente a `fast_stop_with_indexed_suffix`: misma equity, posiciones, estado terminal, causa, P&L, recuentos lógicos expandidos, hashes del ledger materializado, duración de drawdown y `TOTAL_RETURN`, **sin** exigir que el fast path haya invocado el mismo número de wakes físicos después de terminar. El hash debe distinguir identidad del stream original de identidad del ledger derivado. Nunca usar simplemente `break` si existen OPEN o si deja de ser reconstruible alguna fila futura.

**Replicación:** un path detenido permanece en la familia de 231 y sus métricas adversas entran en el análisis. Las siguientes réplicas bootstrap del mismo candidato empiezan **cada una en 100u** y vuelven a recorrer sus bloques; la parada del observado no descarta automáticamente sus otras réplicas. Si un candidato termina en el 30 % del calendario de una réplica, se ahorra el 70 % restante de sus wakes de esa réplica, no el resto de la familia. El ahorro global de tiempo sólo se estimará con una medición acotada V2R/FS-021 sobre streams reales y la nueva regla.

### 3.4 Fixtures de conformance nuevos — además de E2.4/V2R C01–C12

| ID | Caso adversarial | Resultado ejecutable obligatorio |
|---|---|---|
| D01 | equity exactamente 5u, `OPEN=0`, nuevo BET en el mismo wake | stop de la combinación **antes** de stake request; sufijo conservado |
| D02 | equity 4u, `OPEN>0`; última liquidación gana +4u | pausa reversible; equity 8u y ACTIVE; no falsear depletion |
| D03 | equity 4u, `OPEN>0`; última liquidación pierde o deja equity 4u | sólo entonces OPERATIONAL_DEPLETION; `OPEN=0` |
| D04 | dos liquidaciones **simultáneas**, primera baja a 3u y segunda sube a 7u; después `OPEN=0` | evaluar tras batch entero: ACTIVE; ningún stop intermedio |
| D05 | equity 4u, dos OPEN con distintas fechas; primer settlement deja 3u y siguiente deja 6u, pero resta una OPEN que liquida después dejando 9u | mantener pausa incluso tras recuperar 6u; reanudar **sólo** tras último settlement; pendientes aún pre-kickoff son elegibles |
| D06 | equity 4u, dos OPEN; primer settlement deja 3u y último deja 4u | pausa seguida por stop terminal al quedar `OPEN=0`; no esperar el resto del calendario |
| D07 | equity 6u, `OPEN` ocupa todo el efectivo | no depletion; `PENDING_CAPACITY` si procede; settlement/retry CURRENT |
| D08 | 10 lanes llenas + 11.º Kelly sin edge | V2R lane-first: `PENDING_CAPACITY`, 0 `policy.request` antes de liberar lane |
| D09 | equity 5,07u, `OPEN=0` | por el límite 5u **no** termina; falta de efectivo puntual conserva causa CURRENT |
| D10 | después del stop quedan 400 BET y 200 NO_BET históricos | cero wakes/eventos posteriores procesados; 400 `NOT_EXECUTED_AFTER_OP_DEPLETION` expandibles + 200 NO_BET intactos |
| D11 | control de scalar-full-scan vs fast-stop + sufijo indexado | equity/drawdown/ledgers lógicos/recuento/identidad iguales; menos wakes físicos |
| D12 | sharding, reinicio/recompute y bloque bootstrap duplicado | misma pausa, instante de stop, equity, causalidad y hash por candidato/réplica |
| D13 | equity <=0 mientras hay OPEN y las restantes recuperan >5u | registrar `ever_nonpositive_equity` y `HARD_RISK=FAIL` histórico; no borrar settlements; respetar la regla de gate al cerrar OPEN |
| D14 | terminación explícita de política mientras existen OPEN | no nuevas apuestas por razón independiente; liquidar OPEN y conservar ledger, sin recodificarla como sólo depletion |

Fixture de integridad: un Match futuro modificado en el stream upstream debe hacer fallar el SHA y el restore, **aunque** el fast path no lo haya simulado tras depletion. Los fixtures se fijan y ejecutan **antes** de la corrida económica FS-021; `SHA256SUMS=PASS` sin estos oracles nunca es `SEMANTIC_CONFORMANCE=PASS`.

FS-020 y sus autoridades económicas no se recalculan ni modifican. FS-021 obtendrá su propio `experiment_spec_id`, `runner_version`, `DEPLETION_RULE_ID` y hashes después de hooks/índice Git.

---

## 4. Settlement lags: una comparación que no triplica el bootstrap

### 4.1 Por qué 150m es primario, pero no único observado

Los tres lags son **hipótesis sintéticas de disponibilidad del resultado**, no afirmaciones sobre `result_known_at` real. T+130m se ha usado en CURRENT como primer intento de consulta, no como garantía de que el resultado ya estaba disponible; T+150m incluye un margen histórico de partido reglamentario, descanso y añadido. E2.3 no tuvo en vano tres lags: en FS-020 las diferencias de `LEGACY_RECOVERY` 5,07/5,07/395,84u muestran un cambio económico enorme por una lane y pocos eventos. Por ello suprimir completamente T+120/130 negaría un riesgo observado; repetir tres veces la inferencia costosa no es condición necesaria para **escoger una baseline práctica simulada**.

### 4.2 Sustitución explícita de E2.3 para FS-021 v1

| Contrato | E2.3 original | FS-021 propuesto | Efecto autorizado |
|---|---|---|---|
| Candidatos | 231 conceptual | **231 íntegros** | PRESERVED |
| Población | 1.877 común | **1.877 idénticos** | PRESERVED |
| Escenarios económicos observados | 120/130/150 | **120/130/150** | PRESERVED |
| Bootstrap por bloque | 5.000, L=1/2/4 | **5.000, L=1/2/4** | PRESERVED |
| Lags con bootstrap all-pairs | tres | **sólo T+150** | EXPLICITLY_SUPERSEDED |
| Inferencia de estabilidad cross-lag | tres firmas independientes | **no evaluable en FS-021 v1** | EXPLICITLY_SUPERSEDED; no declarar PASS |
| Ranking práctico | fallback control condicionado | **regla 3-lag maximin predeclarada + agotamiento 5u** | EXPLICITLY_SUPERSEDED |
| Evidencia nominal | 9 celdas lag×bloque | **3 celdas T+150×bloque** | 1/3 de los replays bootstrap |

**Recorridos observados:** `231×3=693`, donde 231 sigue siendo el número de candidatos, no se convierte en 693 técnicas. **Replays bootstrap:** `231×5.000×3=3.465.000`. El original `231×5.000×3×3=10.395.000`; la reducción es del **66,67 %** del número de replays bootstrap sin quitar candidatos. **Stability** del escenario primario: `231×(2 mitades + 10 LOO)=2.772` paths adicionales, sobre la misma cohorte calendario y starting equity=100u por slice. Total nominal de recorridos completos observados+bootstrap+stability **3.468.465** antes de materializaciones/fixtures y posibles replays de validación. La terminación anticipada de un path reduce *eventos procesados*, no el número conceptual de paths de su familia.

**Alcance científico legítimo:** inferencia simultánea/stability **condicionada al lag 150m y al diseño FS-021**. Los lags 120/130 soportan sensibilidad descriptiva, veto práctico y min3, **no** intervalos de confianza, ni `SETTLEMENT_SIGNATURE_120m/130m` inferenciales, ni `settlement_time_stability=PASS`. Si hay líderes observados divergentes: `OBSERVED_LAG_SENSITIVE=true` y reportar movimientos de ranking/riesgo; no mover los pesos de selección ni modificar candidaturas. Una afirmación confirmatoria **cross-lag** requeriría ejecutar los seis diseños restantes sobre la familia íntegra, verificar igualdad de las tres firmas originales, y reconocer por separado el efecto del nuevo umbral 5u.

No se puede deducir una duración exacta de este recuento: el benchmark antiguo de ~24h era V1 y carecía de conformidad lane-first. La reconciliación V2R aportó un microbenchmark de 2,6s paralelo con cuatro workers, 9,866s serial y una **proyección aritmética** de 24.647,5 segundos CPU para su alcance local, no una medición sostenida de 231×1.877 con stop 5u. Los efectos de los nuevos P×D y de las terminaciones sobre el throughput aún no están medidos; FS-021 medirá su propia pantalla observada antes de presupuestar los shards bootstrap. Tampoco es legítimo prometer que los peores siempre terminarán: `LEGACY_RECOVERY` pudo conservar 5,07u, por encima del umbral estricto. Sin motivos medidos, mantener GPU fuera del alcance.

---

## 5. Regla práctica de publicación `FS021_INTEGRATED_MAXIMIN_LAG_5U_V1`

### 5.1 Tres gates antes de puntuación práctica

**Gate A — integridad/estructura, por candidato:** 1.877 identidades Match exactas; las 1.877 Prediction/Decision filas y sus `BET/NO_BET`; probabilidad/precio/identidad/timestamps válidos en cada BET; resultados reglamentarios y lineage; política/configuración/lane fijas; 100u inicial; tres paths observados deterministas y completos con los mismos inputs salvo lag. Un gap recuperable causa `RESTORE_REQUIRED` y **STOP técnico** de la publicación comparativa, no exclusión oportunista. Error de invariant/replay/ledger también es STOP técnico. Distinto es una incompatibilidad semántica verdadera y declarada **antes** de ver scores.

**Gate B — veto económico-práctico:** `economic_ruin=false`, `explicit_policy_termination=false`, `operational_depletion_5u=false` **en todos los lags 120/130/150**. Este es un guardrail de publicación, **no censura científica**: los 231 siguen en inferencia y en reportes. Una oportunidad sin lane o sin efectivo debido a OPEN no dispara este gate por sí sola. Las métricas separadas conservan `minimum_equity`, `minimum_available_cash`, `peak_reserved_exposure`, `maximum_drawdown`, `expired_capacity`, `policy_termination_reason`, `depletion_confirmed_at`, `final_equity_after_all_open_settlement`, `ever_below_floor_while_open`, `pause_entry/exit`.

**Gate C — actividad demostrable, guardrail de producto, no prueba estadística:** en **cada** uno de los tres lags, al menos `max(1,ceil(0.02×1877))=38` posiciones efectivamente **PLACED**, de al menos tres competiciones y al menos cuatro semanas Lima distintas. `NO_BET`, Kelly `ZERO_STAKE`, `PENDING_CAPACITY` sin placement y `EXPIRED_CAPACITY` **no** cuentan. Los thresholds son deliberadamente mínimos: evitan una política prácticamente inactiva con una o dos apuestas afortunadas; **no garantizan** inferencia estable ni rentabilidad, que se reportan por separado. El denominador común permanece 1.877, incluidos NO_BET. Si se desea otro mínimo de actividad debe aprobarse/recongelarse **antes** de la primera observación FS-021, jamás ajustarlo después de ver quién sobrevive.

### 5.2 Score y desempate — sólo entre gates A/B/C aprobados

```text
score(candidate) = min(TOTAL_RETURN_120,
                       TOTAL_RETURN_130,
                       TOTAL_RETURN_150)

sort by:
  1 score DESC
  2 TOTAL_RETURN_150 DESC
  3 max(MAX_DRAWDOWN_120/130/150) ASC
  4 min(PLACEMENTS_120/130/150) DESC
  5 max(PEAK_RESERVED_EXPOSURE_120/130/150) ASC
  6 canonical integrated_index ASC
```

Todas las magnitudes económicas de elección son Decimal exactas del runner; `TOTAL_RETURN=(final_equity−100)/100`. No se mezcla `ROI/total_staked`, log-loss, GLOBAL_PPO, utilidad, valor del bookmaker, precisión ni retorno de otra cohorte como *tie-break* oculto. En caso de igualdad Decimal exacta, seguir hasta identidad canónica única. `NO_BET` conserva la cobertura; no cuenta como actividad ni genera P&L ficticio.

Si el ganador práctico tiene pérdidas en los tres lags pero pasó los gates, se puede publicar como **baseline experimental simulada con aviso `HISTORICALLY_LOSS_MAKING`**, no como técnica aprobada para apuestas reales. El veto 5u es estricto; pueden existir pérdidas graves **sin** cruce a <=5, de modo que el reporte debe mostrar la magnitud completa y FS-022 decidir límites/continuidad prospectiva por separado. El producto no interpretará la elección como rentabilidad.

### 5.3 Contingencias y fallback tipado

```text
if physical/scientifically_material_evidence_not_integral:
    result = TECHNICAL_STOP_RESTORE_REQUIRED
    no GLOBAL_STRATEGY_V1 publication

elif at_least_one_candidate_passes_gates_A_B_C:
    selected = deterministic_maximin_survivor
    practical_state = PRACTICAL_BASELINE_SIMULATION_ONLY
    new_simulation_stakes_in_FS021 = false  # research only; FS-022 handles activation
    scientific_state = independently_computed_150m_disposition

else:
    # all 231 were validly evaluated but all fail risk/activity
    selected_diagnostic = first candidate from ALL structurally valid,
      ordered by same maximin/secondary keys and canonical ID,
      INCLUDING observed failures but displaying their cause
    practical_state = DIAGNOSTIC_ONLY__NO_NEW_STAKES
    operational_activation = false
    no suggestion that diagnostic path is economically eligible
```

`selected_diagnostic` puede ser un path que agotó la banca; el sistema debe mostrar `OPERATIONAL_DEPLETION`, la razón de veto, los resultados de las otras 230 y un **STOP de nuevas colocaciones** para esa baseline diagnóstica. Si todas pierden las 100u o violan algún veto, **nunca** se inventa una candidata “segura”; el componente seleccionado se conserva sólo para investigación, auditoría o seguimiento pasivo. El antiguo control integrado de E2.3 (`MARKET_CONSENSUS+MODAL_ALL+FLAT_UNIT`) **no** se fuerza artificialmente como elegido práctico: es un **control histórico** obligatorio. El control de autoridades locales al cierre FS-020 (`MARKET_CONSENSUS+MODAL_ALL+FRACTIONAL_KELLY 0.25/10`) también debe recalcularse sobre los 1.877 idénticos para una comparación directa; ninguno recibe prioridad por ser control.

Publicar en `GLOBAL_STRATEGY_V1` **campos separados** `practical_selection` y `scientific_evidence`/`scientific_scope`. Si el esquema actual sólo tolera `PROMOTE/NO_PROMOTION`, F008 debe reconciliarlo expresamente: `PRACTICAL_BASELINE_SIMULATION_ONLY` no falsifica el antiguo `NO_PROMOTION` científico de E2.3. La selección práctica se predeclara *antes del nuevo score FS-021*, pero usa datos históricos 2026 ya examinados en las capas anteriores: es una elección **histórica condicionada** y necesita validación futura.

---

## 6. Inferencia científica de FS-021 (150m únicamente)

### 6.1 Unidad, métrica, bootstrap y familia

Población emparejada idéntica 1.877; 10 ligas; 36 semanas calendario Lima continuas desde 2026-01-12, incluidas seis semanas vacías; pertenencia semanal por `kickoff−30m` en Lima. Tres diseños **separados**, `L∈{1,2,4}` semanas; 5.000 réplicas cada uno; matriz de arranques generada con `numpy.random.Generator(PCG64(SeedSequence([21092026,L])))`, bloques semanales contiguos globales, arranques con reemplazo, `ceil(W/L)` bloques y truncado final a 36 semanas. Todas las 231 combinaciones consumen **la misma secuencia de bloques en cada réplica**, construyen calendario sintético coherente con ocurrencias duplicadas renombradas y **replay stateful desde 100u** por réplica, incluyendo el 5u nuevo; no remuestrear P&L realizados ni reciclar una banca entre réplicas.

Guardar el **algoritmo y la serialización** elegidos antes de la corrida: FS-020 ya declaró `C_ORDER_LITTLE_ENDIAN_INT64_BLOCK_STARTS` para sus matrices RNG; los hashes más antiguos E2.3 (`e631…`, `1bbed…`, `d069…`) no tienen una codificación idéntica demostrada por el run FS-020 y no se deben identificar como bytes iguales sin prueba. Congelar nuevos hashes FS-021 de arrays y semantic spec tras los hooks, sin retocar la semilla. Períodos parciales y semanas vacías cuentan en W. Dos mitades cronológicas del mismo calendario (18+18 para W=36) y 10 leave-one-competition-out: 12 slices, **cada uno con 100u frescas y Event-Time reejecutado**, nunca restando P&L de una liga a la trayectoria global.

Métrica por candidato `TOTAL_RETURN_150`; dirección DESC. **Familia conceptual íntegra** M=231, pares canónicos `(i,j)` con `i<j`, `M(M−1)/2=26.565`. Pueden compartirse eventos/calendarios y optimizar el runner, nunca compartir estado mutable Capital ni podar candidatos por sus scores, su agotamiento observado o su banda P×D previa. La estructura ideal de scores para un bloque es `(5.000,231)` `float64` (~9,24 MB), tres bloques ~27,72 MB; pares procesados por chunks para evitar tensor `(5.000,26.565)` persistente.

### 6.2 Contrato exacto all-pairs max-t, incluido `se==0`

Para cada par `(i,j)`, con retornos primarios observados `theta_i`,`theta_j`, `d_ij=theta_i−theta_j`; por réplica `b`, `d_ij^(b)=theta_i^(b)−theta_j^(b)`. Orden de réplicas congelado y conversión para inferencia a `numpy.float64`. `se_ij=numpy.std(deltas_bootstrap_ij,ddof=1)` y **cero exacto float64** `se_ij == 0.0`, sin tolerancia ni reestimación pos hoc. Si `se_ij>0`: `z_b,ij=abs(d_ij^(b)−d_ij)/se_ij`; `M_b=max(z_b,ij)` de **todos** los pares canónicos con SE positivo; `q95=numpy.quantile(M,0.95,method="linear")`; intervalo `[d_ij−q95*se_ij,d_ij+q95*se_ij]`.

Si `se_ij==0.0`, **no dividir por cero, no formar z y no incluir el par en M_b**. Persistir intervalo puntual **`[d_ij,d_ij]`**, `deterministic_se_zero=true`, **incluso** si su único delta bootstrap constante difiere numéricamente del delta observado; no inventar pseudo-SE ni tolerancia. Un par puntual participa en la comparación determinista si existe **al menos un** par con SE positivo que permite estimar la familia. Si **todos los 26.565** SE requeridos fueran cero: `q95=0.0` sólo para registro, `DEGENERATE_ALL_SE_ZERO`, diseño NO ESTIMABLE, disposición `INSUFFICIENT_EVIDENCE`, prohibido `CLEAR_SUPERIORITY`.

Intervalo orientado top `T−c`: si el orden canónico almacena T−c, usar sus `[LB,UB]`; si almacena c−T, invertir exactamente `[-UB,-LB]`; los puntos `[d,d]` pasan a `[-d,-d]`. Superioridad estricta de T frente a **cada** otro candidato sólo si **todos** los `LB(T−c)>0`, nunca `>=0`. El mismo control simultáneo se exige en L=2 primaria y L=1/4 sensibilidad. No se reemplaza max-t por inferencia sin multiplicidad ni se elige un top-N tras ver scores.

### 6.3 Disposición científica en 150m, independiente del producto

Definir `T_150` líder de retorno observado en los 231; un empate puntual impide `unique_leader` (identidad canónica sólo para presentación). Para cada una de las 12 slices, replay de 231 paths frescos y comparar `T_150−c` para **todos** los `c` restantes. Slice faltante/no estimable: `INSUFFICIENT_EVIDENCE`; cualquier delta negativo: `UNSTABLE`; si ningún negativo pero existe igualdad: `NON_STRICT`; si todos estrictamente positivos: `PASS`. Orden de prelación:

```text
missing/invalid mandatory scientific evidence or degenerate required design
→ INSUFFICIENT_EVIDENCE

else any negative required 150m slice delta
→ UNSTABLE

else unique observed leader
 + stability PASS
 + 2w strict all-pairs top-vs-all PASS
 + 1w strict all-pairs top-vs-all PASS
 + 4w strict all-pairs top-vs-all PASS
→ CLEAR_SUPERIORITY_150M_CONDITIONAL

else
→ NO_CLEAR_SUPERIORITY_150M_CONDITIONAL
```

Los vetos de agotamiento 5u controlan el producto, no borran al candidato de las 231 trayectorias/intervalos. Si el líder científico T_150 falla el gate económico, la ciencia conserva su identidad y el producto **no** lo selecciona salvo modo diagnóstico. La composición práctica maximin podría ser otra; su intervalo T+150 frente a todos se reporta cuando existe, pero no se le atribuye la prueba del líder T_150.

**Limitación de reutilización de datos:** FS-018/019/020 y la preferencia de umbral 5u se determinaron conociendo parte del histórico 2026. Aunque FS-021 congele ahora su familia/rule antes de puntuar 231, el histórico **no se vuelve un holdout virgen**. La cobertura simultánea se interpreta **condicionada al diseño elegido y al modelo de resampling**, no como una prueba independiente de rentabilidad, superioridad global descubierta sin búsqueda ni generalización prospectiva. Una confirmación genuina exige períodos futuros y congelación previa del challenger/baseline; White (2000) y Hansen (2005) tratan precisamente riesgos de búsqueda múltiple, no validan una victoria in-sample por decreto.

### 6.4 `SETTLEMENT_SIGNATURE_x`: contrato histórico transportado, no falsamente calculado

Para un programa que efectivamente compute **los tres lags con toda la inferencia** E2.2/E2.4, conservar exactamente:

```text
PRIMARY_150M_LEADER = OBSERVED_LEADER_150m
SETTLEMENT_SIGNATURE_x = (
    OBSERVED_LEADER_x,
    WITHIN_LAG_DISPOSITION_x,
    WITHIN_LAG_PROMOTION_x,
    HARD_RISK_x(OBSERVED_LEADER_x),
    HARD_RISK_x(PRIMARY_150M_LEADER),
    HARD_RISK_x(FLAT_UNIT),
    WITHIN_LAG_FALLBACK_x,
)
```

Identidades/enum strings canónicos y orden exacto de siete campos. Ningún campo consulta `settlement_time_stability`, `FINAL_CAPITAL_SCIENTIFIC_DISPOSITION`, `FINAL_PROMOTION_PERMISSION` ni `FINAL_PROMOTION_TARGET`. Se construyen **tres** firmas lag-locales completas **antes** de compararlas. Si algún lag/firma requerido es no estimable: final `INSUFFICIENT_EVIDENCE/NO_PROMOTION`; si difieren las firmas respecto de 150: `UNSTABLE/NO_PROMOTION`; sólo si las tres son idénticas la conclusión final adopta disposición/promoción lag-local 150. En FS-021 **no** se fabrican `WITHIN_LAG_DISPOSITION_120m/130m` ni firmas E2.2 basadas en la sola pantalla observada: publicar `CROSS_LAG_INFERENCE=NOT_EVALUATED_BY_FS021_V1`. El criterio práctico min3 observado sigue siendo válido como **regla de producto**, no como certificado cross-lag.

---

## 7. FS-021: plan de ejecución, observabilidad y parada

### 7.1 Preflight mínimo, no una nueva fase de investigación

Consumir el handoff final de FS-020 como decisión aceptada, no como sustituto de los logs del host. Autenticar `FS-020_global_capital_v1.json`, `run.json`, research byte SHA `808f5ca4339382de986a285e22fb55d4d64165969befddf36c5ab0861049e61b`, `FS-020_e2_4_v2r_reconciliation.json`, sus 12 fixtures y `football/experiments/capital_events.py` CURRENT por versión/hash. Restaurar `FS018_E1_PHASE3` verificado (SHA de archive `8776ff4e91bdbc93d5e3f7826e9b6b28a1128b65220f2dbdaf0475992c577db6`) y el binding de FS-019: 33 streams con exactamente los mismos 1.877 Matches y 61.941 filas, hashes e identidades de las 33 variantes. Verificar el retain index de FS-020/FS-018 y su derecho de consumo sin borrado.

F008/F009 deben realizar tres gates separados y con resultado persistido: `INPUT_AND_ARTIFACT_INTEGRITY`, `SEMANTIC_CONFORMANCE` y `RUNNER_EQUIVALENCE`. La nueva regla de depletion se prueba junto a la referencia V2R lane-first; no confundir el éxito de un hash con la semántica de la pausa/stop. Si falta físicamente un archivo recuperable: recuperar del archive/producer y revalidar; no reinterpretarlo como exclusión estadística.

### 7.2 Etapas de cómputo SIN dividir la familia en rankings parciales

1. **Spec y oracles previos a scores:** congelar la matriz conceptual 231, cohort 1.877, nuevo gate de 5u, orden de lags, calendario, seed, 1w/2w/4w, selección práctica y alcance científico de 150m. Congelar reglas de ledger expandible por sufijo y pruebas D01–D14. Exigir `scalar_full_scan == fast_stop`, `full_shard == split_shards` y `restart/recompute` exactos en fixtures, sin una elección basada en scores observados.
2. **Una sola pantalla observada integral:** ejecutar cada combinación en los tres lags, 231×3=**693 paths observados**, no 693 candidatos ni un torneo extra. Conserva todos los resultados y los tres ledgers por candidato/lag, con stop/pause. Publica hashes de los paths completos y los dos controles recalculados en esta **misma** cohorte 1.877.
3. **Medir presupuesto una sola vez sobre código FS-021 real:** usar wall/RSS/CPU/eventos simulados y fracción de paths/sufijos terminados de esa pantalla; medir referencia optimizada con un shard **pequeño y técnico, no de selección**, si fuese necesario. No repetir una prueba térmica completa por rutina. Proyectar horas usando únicamente medición FS-021/V2R pertinente y declarar incertidumbre. Ni el anterior benchmark V1 de ~24h ni el microbenchmark V2R son ETA garantizada.
4. **Bootstrap 150m para toda la familia:** 5.000 réplicas emparejadas por cada diseño de 1, 2 y 4 semanas: **3.465.000 replays conceptuales** de 231 caminos. Shards inmutables `(lag=150, block_length, replicate_start, replicate_stop)` con hash de spec/runner/stream/calendario. Recuperar shards íntegros sin recomputarlos y reconstruir sólo el faltante; excluir shards corruptos y reejecutarlos con nueva identidad/documentación, nunca sobrescribir prueba inválida sin registrar motivo.
5. **Inferencia/estabilidad T+150:** 12 slices ×231 = **2.772** recorridos stateful adicionales sobre la cohorte comparable; después all-pairs 26.565 pares, FWER 95%, `se==0` ejecutable y reglas originales de estabilidad T_150 vs todos.
6. **Publicación y evidencia:** combinar `3.468.465` paths conceptuales observados+bootstrap+stability (693+3.465.000+2.772), sin contar UAT técnico ni materializaciones. Publicar dos salidas separadas: selección práctica reproducible y conclusión científica condicionada a 150m; mantener `CROSS_LAG_INFERENCE=NOT_EVALUATED_BY_FS021_V1`. Ninguna publicación activa routing ni apuestas reales.

Los shards pueden usar toda la máquina CPU de forma determinista sin ordenar ni posponer candidatos por resultado económico. No usar como benchmark el `studies._run_path` antiguo; reutilizar el runner Event-Time lane-first CURRENT, preservando `Decimal`, siete policies y estados individuales. RAM objetivo de score matrices `(5000,231)` float64 (~9,24 MB por diseño, ~27,72 MB para tres), inferencia por parejas en chunks y no tensor `(5000,26565)` por diseño. El índice de sufijos evita esperar eventos posteriores a stop, pero no se descuentan réplicas de la matriz inferencial.

### 7.3 Condiciones de parada del TICKET, no del path

`STOP_TECHNICAL` para lineage/restore incompleto recuperable, conformance FAIL, cohort no emparejada, hash mutado tras hooks o determinismo de shard no reproducible. `PAUSE_RESOURCE` para recursos insuficientes tras optimización sin podar candidatos; guardar índice de shards y reanudar. Si el primer observado detecta que el nuevo contrato produce invariantes contradictorias, no usar la observación para improvisar otra regla: parar y reconciliar el spec mediante F008 antes de continuar. Una técnica que termina por 5u **nunca** provoca el STOP general del torneo.

---

## 8. Evidencia durable mínima para futuras técnicas múltiples

La intención de recopilar evidencia contextual **no** autoriza crear un selector multitécnica dentro de FS-021, ni acceder a información post-kickoff para producir predicciones as-of. La unidad maestra durable es el Match/competición/temporada/fecha, con `match_id` canónico, equipos, kickoff UTC y Lima, estado de resultado reglamentario, timestamps de conocimiento, cohort flag `COMMON_1877` y/o `LOCAL_1906` y razón de exclusión; preservar diferencias de cohorte y nunca comparar saldos de poblaciones distintas.

### 8.1 Tabla fuente/as-of y precios — material irreemplazable

Por evento de origen guardar los *features reales* disponibles antes de kickoff en la medida permitida por licencia: estadísticas anteriores, ratings/previsiones, historial de forma, disponibilidad temporal de datos, corte del proveedor, fuente/endpoint, timestamp de observación/ingesta, revisiones/versión de parser y hash/identificador del raw permitido. Una predicción anterior sin sus inputs **no garantiza** que un modelo nuevo se pueda entrenar o retrocalcular honestamente; si no se retuvieron, marcar `NEW_MODEL_HISTORICAL_FEATURES_UNAVAILABLE`, no inventar retrospectivos.

Cuotas/precios: bookmaker canónico, mercado/outcome 1X2, cuota cruda y desvigorizada si aplica, selección de precio, timestamp observado/reconstruido, latencia/edad al decidir, proveedor, raw hash permitido, fuente, desfase frente a kickoff, comisión/spread si se conoce y razón de ausencia cuando no haya tripleta. `ODDSPAPI_RECONSTRUCTED_T30_V1` es **histórico/reconstruido**, no prospectivo. No generar un T-30 falso desde Football-Data closing o la DB actual. Conservar el contrato de derechos/licencias de cada proveedor, no redistribuir raw sin autorización.

### 8.2 Streams completos, no sólo las apuestas que ganaron

Por cada Prediction: versión de código/config/feature schema, 1X2 completo `p_home/p_draw/p_away`, fecha as-of, calibración, cobertura y motivo de indisponibilidad. Por cada Decision: versión/config/threshold, `BET`/`NO_BET`, outcome, probabilidad usada, precio y bookmaker elegidos, edge, causa y precio inaccesible si procede. En FS-021 la tabla completa `33×1.877=61.941` filas P×D se retiene o restaura por referencia verificable; ninguna fila desaparece después del stop Capital.

Por cada P×D×Capital/lag/replica: `candidate_id`, `common_cohort_hash`, `event_time`, `event_type`, `input_opportunity_id`, `policy.request`/reason/zero, `stake_requested/applied`, equity/reservas/available_cash antes/después, OPEN/lane count, estado recovery, PENDING/expiry, settlement, P&L, drawdown/tiempo, `AWAITING_FINAL_OPEN_SETTLEMENT` y `OPERATIONAL_DEPLETION`, bandera `ever_nonpositive_equity`, ledger SHA y `unprocessed_suffix` expandible. Los estados `OPEN/PENDING_CAPACITY/EXPIRED_CAPACITY/ZERO_STAKE/NO_BET/PATH_STOPPED_OP_DEPLETION/NOT_EXECUTED_AFTER_OP_DEPLETION` no deben colapsarse en una etiqueta genérica de no apuesta. Las 231 combinaciones tienen bankroll/policy_state **independientes** y no pueden heredar P&L de otro upstream.

### 8.3 Contexto exploratorio para futuros pesos multitécnica

Derivar **sobre las mismas oportunidades observables**, por Match y técnica: liga/competición/temporada, local/visitante, favorito/no favorito, tramo de cuota (registrando el número crudo para que los cortes sean futuros), probabilidad/calibración, edge, incertidumbre histórica y calidad de features, bookmaker y edad del precio, fase de temporada, simultaneidad de eventos, reservas/lanes y `NO_BET`/caducidad. Las tablas derivadas pueden calcularse después desde los raw/streams congelados sin sumar miles de variantes especulativas al experimento FS-021. Generar cortes exploratorios con denominador, cobertura, n/intervalos y advertencias por búsqueda múltiple; no elegir pesos dinámicos ni ligas tras ver los resultados y llamarlo confirmatorio. Si un contexto no era conocible as-of, no podrá activar una combinación prospectiva bajo ese criterio.

### 8.4 Retención operativa/experimental

Compactos en `docs/research/FS-021_*`: autoridad versionada `GLOBAL_STRATEGY_V1`, spec/hash, matriz/eligibilidad 231, cohort/stream manifest, summary 231 y reporte, contexto de selección práctica/ciencia, índice externo, sha de restore. Evidencia pesada bajo `/home/ljarufe/Documents/finsport/research-evidence/FS-021/<execution_id>/`: ledgers observados expandibles, índices/streams de sufijos, shard matrices, RNG draws/versiones, paths de estabilidad, tablas de contexto, logs de conformance, `SHA256SUMS` y `RETENTION_INDEX.tsv` con `producer`, `consumers`, `delete_when`, versión, license class, restore command validado. `tmp/FS-021_01_...` etc. sigue **descartable** y nunca es autoridad cross-ticket. Mantener `FS018_E1_PHASE3` y evidencia FS-019/FS-020 en `PRESERVE_ACTIVE` hasta verificar que FS-021 y sus futuros consumidores regeneran exactamente lo necesario sin el raw upstream; borrar sólo con autorización expresa y condiciones de retención satisfechas.

No conservar credenciales, tokens ni datos personales innecesarios en research; minimizar raw bajo derechos restringidos, con inventario de qué es regenerable y qué era observación irrecuperable. Eliminar duplicados sólo tras verificar identidad semántica y conservar los 231 conceptos científicos.

---

## 9. Plan prospectivo baseline/challenger — FUERA del torneo FS-021

FS-021 es retrospectivo sobre 2026 **ya examinado indirectamente**; por ello aun el max-t 231 tiene alcance condicionado al diseño/histórico y no prueba rentabilidad futura. Conservar tres clases de evaluación: (A) **replay exacto** de los algoritmos actuales con raw/stream/cohorte inmutable, (B) **retrospectiva de un modelo nuevo** sólo cuando sus features realmente as-of fueron retenidos, (C) **validación prospectiva auténtica** con predicción/cuota capturada antes de kickoff y reglas congeladas antes del período futuro. Una técnica futura puede compararse con `GLOBAL_STRATEGY_V1` y otras challengers sobre la **misma cohorte futura**, calendario y banca 100u independiente por alternativa, con mismo criterio de settlement y capital-cash/lanes y sin aprovechar resultados anticipados.

FS-022 decide explícitamente si activa un único camino simulado de manera prospectiva, usa shadow temporal de alternativas o reejecución manual/on-demand; puede dejar de ejecutar técnicas alternativas continuamente **sin detener captura mínima de inputs as-of** necesaria para posteriores comparaciones. Asegurar recuperación tras apagar el host: si ya había una posición simulada, recuperar y liquidar con `result_known_at` auténtico; si no se hizo la decisión T-30, no fabricar una colocación retrospectiva ni la cuota. No convertir un backtest reconstruido en P&L prospectivo.

Un posible selector multitécnica futuro necesitará su propia matriz versionada de contextos, función de routing/pesos y validación walk-forward con datos nunca utilizados para descubrir los pesos, seguida de seguimiento prospectivo monitorizado. FS-021 sólo preserva la evidencia necesaria para estudiar esa posibilidad, sin entrenarlo ni promocionarlo ahora.

---

## 10. `GLOBAL_STRATEGY_V1`: autoridad de investigación, no activación

El publicador debe emitir una autoridad conceptual versionada en `docs/research/FS-021_global_strategy_v1.json` más su reporte, ambos SHA-bound tras hooks/índice Git. El mínimo contrato de autoridad es:

```json
{
  "schema": "FS021_GLOBAL_STRATEGY_AUTHORITY_V1",
  "experiment": {
    "spec_id": "<hash FS021 spec including depletion V2>",
    "run_id": "<real immutable run id>",
    "cohort_id": "<verified common 1877 id>",
    "pd_matrix_id": "<verified 33 matrix id>",
    "integrated_family_count": 231,
    "settlement_observed_lags_min": [120, 130, 150],
    "scientific_bootstrap_lags_min": [150],
    "depletion_rule": "FS021_OPERATIONAL_DEPLETION_5U_AFTER_ALL_OPEN_V2",
    "risk_policy": "FORMAL_RUIN_AND_OPERATIONAL_DEPLETION_TRACKED_SEPARATELY",
    "code_commit": "<verified Git HEAD>",
    "runner_version": "<new bound code identity>",
    "reference_v2r_sha256": "fa55e297ec2b334b6b8cf2aa70bd62974f98f1994a951446d59d9047c1e8e833",
    "input_manifest_sha256": "<hash>",
    "rng_manifest_sha256": "<hash>"
  },
  "practical_selection": {
    "rule": "FS021_INTEGRATED_MAXIMIN_LAG_5U_V1",
    "selected_integrated_id": "<determined after run or null on technical STOP>",
    "mode": "PRACTICAL_BASELINE_SIMULATION_ONLY | DIAGNOSTIC_ONLY__NO_NEW_STAKES | TECHNICAL_STOP",
    "threshold": "5",
    "depletion_veto_all_observed_lags": true,
    "activity_gate_id": "MIN_38_PLACEMENTS_3_COMPETITIONS_4_LIMA_WEEKS_PER_LAG",
    "candidate_summary_manifest_sha256": "<hash>",
    "control_integrated_local_id": "MARKET_CONSENSUS|MODAL_ALL|FRACTIONAL_KELLY|0.25|10",
    "control_pre_e2_3_id": "MARKET_CONSENSUS|MODAL_ALL|FLAT_UNIT"
  },
  "scientific_evidence": {
    "primary_lag": 150,
    "blocks_weeks": [1, 2, 4],
    "replicates_per_design": 5000,
    "all_pairs_family_size": 26565,
    "disposition": "CLEAR_SUPERIORITY_150M_CONDITIONAL | UNSTABLE | NO_CLEAR_SUPERIORITY_150M_CONDITIONAL | INSUFFICIENT_EVIDENCE",
    "cross_lag_inference": "NOT_EVALUATED_BY_FS021_V1",
    "methodology_supersession": "BOOTSTRAP_150_ONLY_AND_AFTER_ALL_OPEN_DEPLETION"
  },
  "activation": {"automatic_operational_routing": false, "real_betting": false},
  "artifacts": {"report_sha256": "<hash>", "retained_evidence_sha256": "<hash>", "retention_index_sha256": "<hash>"}
}
```

Los literales `<...>` son **campos obligatorios a completar con valores auténticos del run**, no artefactos existentes ni hashes inventados. Si existe sólo una composición diagnóstica y ninguna viable para nuevas apuestas, publicarla con modo `DIAGNOSTIC_ONLY__NO_NEW_STAKES`, no como promoción económica. Ninguna publicación en FS-021 activa Beat, operacional, apuestas reales, ni ejecuta nuevas colocaciones sin un contrato posterior de FS-022.

El reporte compacto FS-021 incluye una fila por las 231 identidades con los tres saldos/retornos observados, máximos drawdowns, cobertura y actividad, `OPERATIONAL_DEPLETION`/ruin/termination flags, instantes stop/pause y motivos, ciencia 150m, incertidumbre, comparabilidad, controles recomputados en 1.877, calidad temporal histórica y limitaciones. Cualquier diagnostic-only debe explicar por qué no hay candidato económico práctico admisible en la muestra, manteniendo el histórico completo.

---

## 11. Contrato de consumo FS-022 y límites de producto

FS-021 entrega **resultados, autoridad y artifacts**; FS-022 decide interfaz, prospective shadow/cutover, ejecución continua y, bajo un gate posterior separado, cualquier propuesta de apuestas reales. FS-021 puede definir campos del read model, no implementar frontend o activar nuevas rutas como efecto colateral.

Proponer para FS-022 eventos mínimos `PREDICTION_COMPUTED`, `DECISION_BET/NO_BET`, `CAPITAL_REQUESTED`, `POSITION_OPENED`, `PENDING_CAPACITY`, `PENDING_RETRIED`, `POSITION_SETTLED`, `EXPIRED_CAPACITY`, `AWAITING_FINAL_OPEN_SETTLEMENT`, `OPERATIONAL_DEPLETION` y `PATH_STOPPED`, con `match_id`, UTC/Lima event time, técnica/versiones, market evidence ID, equity/reserved/available, lane occupancy, reason, input/run hashes y dato `AS_OF` frente a `RESULT_KNOWN_AT`. Un read model agrupable por fecha/semana/mes, competición, periodo y total muestra bankroll/equity/drawdown, apuestas simuladas abiertas/liquidadas, stakes, exposición, W/L, acierto/errores, `NO_BET`, pending, expired, depletion/termination y tasa de cobertura; todo histórico se etiqueta distinto del prospectivo.

FS-022 sólo puede proponer un camino continuo tras aprobar contrato prospectivo sin T-30 retrospectivo, reconciliación de fuentes, continuidad post-apagado, pruebas shadow baseline-vs-challenger con capital independiente, alerta por desfase/latencia/outage/proveedor, rollback reversible, y elección explícita de qué técnicas alternativas ejecutar de forma continua o sólo on-demand. Conservar la **captura mínima** de inputs necesaria para futuros challengers aunque se deshabilite el cómputo continuo de alternativas. Ninguna técnica/resultado simulado da autorización para dinero real: hacerlo requiere otro gate legal/regulatorio de la jurisdicción aplicable, titularidad/responsabilidad, moneda real, riesgo y límites, controles operativos y aprobación expresa.

---

## 12. Matriz de trazabilidad, reconciliación y handoff F010 → F008

| Obligación material | Estado FS-021 | Consecuencia concreta |
|---|---|---|
| FS-018 Prediction authority/model versions, cohort temporal y retención | PRESERVED | conservar todas las alternativas, raw/feature provenance as-of y bundle `PRESERVE_ACTIVE` |
| FS-019 Decision authority y 33 P×D elegibles | PRESERVED | 33 exactos × siete, NO_BET incluido, Market×VALUE inelegible |
| FS-020 Capital-local publicado y disposición científica `UNSTABLE` | PRESERVED | local no reescrito; recomputar el control concatenado en los 1.877 con contrato FS-021 |
| V2R lane-first, Decimal, pending, retry/recompute, same-wake settle-before-place | PRESERVED | conformance C01–C12 + D01–D14 obligatoria |
| E2.3 familia 231, cohorte 1.877, métricas, 1/2/4 semanas, 5000, all-pairs max-t, estabilidad H1/H2+10 LOO | PRESERVED para T+150 | ningún top-N económico ni sharing de Capital state |
| E2.3 9 celdas (3 lags×3 bloques) y firmas completas cross-lag | EXPLICITLY_SUPERSEDED en FS-021 v1 | 3 celdas a 150m + 3 recorridos observados; no fingir `settlement_time_stability=PASS` |
| E2.3 hard-risk original como único veto / fallback local-control | EXPLICITLY_SUPERSEDED como política práctica FS-021 | nuevo gate 5u sólo tras cerrar OPEN + mínimo de actividad + regla maximin 3 lag; controles diagnósticos retenidos |
| E2.4 `se==0`, `SETTLEMENT_SIGNATURE_x` no circular, fuente autónoma | PRESERVED | sección 6 ejecutable; no reescribir firmas si no hay inferencia 120/130 |
| FS-020 incidente V1→V2R y hook SHA mismatch | PRESERVED | conformance independiente de hashes y verificación tras todos los hooks del índice Git |
| FS-020/F018 large evidence e índices de retención | PRESERVED | consumidor FS-021 y futuro FS-022; no borrar mientras haya dependencia |
| Dinero real / runtime cutover / frontend | NOT_RELEVANT TO FS-021 EXECUTION | contrato FS-022, no activación indirecta |

**Dependencias ACTIVE:** F001 v1.8/F003 v1.12/F006 v1.11 todavía describen Capital como futuro desde el corte post-FS-019: se requiere reconciliar el hecho nuevo de FS-020 antes de que F008 formalice FS-021, **una fuente cada vez**. F006/F008/F010 además reflejan la inferencia original de nueve celdas y fallback científico E2.3: la elección nueva de tres celdas a 150m, regla práctica maximin 3 lag y `FS021_OPERATIONAL_DEPLETION_5U_AFTER_ALL_OPEN_V2` son `PENDING_SOURCE_RECONCILIATION` hasta que el chat principal los acepte y actualice de forma dirigida. F000 al final. No editar aquí fuentes permanentes ni asumir que handoff nuevo sustituye automáticamente ACTIVE.

**F010 handoff:** investigación FS-021 **completa para decisión del producto**, sin evidencia económica nueva; fuente única autosuficiente con candidatos, umbral tras todas las OPEN, política de pausa/reanudación, norma estadística, alcance de lag, regla práctica, retención, tests y contrato FS-022. `RESEARCH_COMPLETE__PENDING_SOURCE_RECONCILIATION`; F008 puede definir el ticket una vez cierre las contradicciones ACTIVE y compruebe el DoR. No declarar `FS-021 READY` desde research: necesita aceptación de esta sustitución explícita, source-reconciliation, IDs/hash de spec y conformance ejecutable en preflight. Si falta material físico recuperable en el futuro ticket, su disposition será `TECHNICAL_STOP_RESTORE_REQUIRED`, no un candidato descartado.

**No ejecutado en esta investigación:** torneo FS-021, bootstrap, replays económicos, candidatos de resultado, provider calls, DB writes, modificación de CURRENT, apuestas reales, publish authority, modificaciones de fuentes permanentes.
