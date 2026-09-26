# FS-021 — Feedback final de ejecución, selección integrada y Economic Selector

**Proyecto:** Finsport
**Ticket:** FS-021 — Global Integrated Strategy Baseline
**Rama:** `fs021-global-integrated-strategy` · **PR:** [#27](https://github.com/ljarufe/finsport/pull/27) → `master` · **Autoridad de proceso:** F009 v1.14
**Ubicación canónica de este documento:** `docs/process/FS-021_feedback.md`
**Corte de evidencia:** 26 de septiembre de 2026, antes del merge
**Ejecución científica y económica:** `fcd8ce16950e02589d25ddf6bcd9953cce2e663f2f14c63e7f8a1f4487d97372`
**Estado de trabajo:** implementación, cálculo histórico, publicación y UAT local completados; PR #27 abierto. Un comentario P2 de review se identificó y se preparó su corrección; **su push, CI posterior y resolución formal en GitHub no están acreditados en el material recibido para este documento**. El merge, deploy y aceptación post-deploy son hitos posteriores, no hechos consumados.

> **Disciplina de cierre:** F009 §13 exige que el feedback se incorpore como último paso documental pre-merge, cuando CI y los hallazgos del review estén resueltos. Este es el texto integral preparado para esa incorporación. Antes del commit, completar únicamente las casillas de la sección 19 con los hechos finales de CI/review y corregir cualquier cifra invalidada por un cambio material; **no** cambiar retroactivamente las autoridades experimentales para que el documento parezca cerrado.

---

## 0. Resumen ejecutivo y significado real del resultado

FS-021 completó el primer torneo **acumulativo e integrado** de Finsport sobre las capas Prediction × Decision × Capital, sin confiar en que el ganador aislado de cada capa fuera necesariamente la mejor composición conjunta. El trabajo incluyó la reconstrucción del universo upstream, el diseño y conformidad de una regla de agotamiento a 5u, un runner Event-Time reproducible, ejecución observada exhaustiva, bootstrap pareado, estabilidad, selección histórica, investigación económica posterior, una adenda de selección y la implementación permanente de un único **Economic Selector** para el laboratorio.

El resultado debe interpretarse en **tres planos que no se sustituyen entre sí**:

| Plano | Autoridad y resultado | Significado |
|---|---|---|
| Experimento original | `GLOBAL_STRATEGY_V1`; selección práctica histórica **#60** — `DIXON_COLES × VALUE(0.05) × LEGACY_CAPPED` | Ganador de la regla original `FS021_INTEGRATED_MAXIMIN_LAG_5U_V1`, cuyo criterio maximiza el retorno mínimo observado entre tres lags tras superar sus gates. Se conserva inmutable. |
| Evidencia científica original | `scientific_evidence.disposition = UNSTABLE` | El experimento no demostró superioridad clara y estable en la familia de comparaciones definida para T+150. No se cambia ni se encubre mediante el selector posterior. |
| Selector económico posterior | `FS021_SINGLE_ECONOMIC_SELECTOR_V1`; composición **#209** — `MARKET_CONSENSUS × SELECTIVE_CONFIDENCE(0.45) × FRACTIONAL_KELLY(0.25, max_lanes=10)` | Una sola **baseline económica para la siguiente fase de simulación**, escogida al combinar retorno observado entre lags y control explícito de drawdown y riesgo de cola bootstrap. No es una validación prospectiva ni una promoción de apuestas reales. |

La #209 quedó autenticada de nuevo sobre la ejecución original del host: **20** candidatas en el primer tier, **9** integrantes de la frontera no dominada y **3** que satisfacen simultáneamente ambos límites robustos. El estado de análisis económico publicado es `COMPLETE`, con `winner=209` y `upstream_retention_index=PRESENT`. Se preservan el resultado #60 y `UNSTABLE`. La activación operacional y las apuestas reales permanecen expresamente deshabilitadas.

La contribución arquitectónica es también durable: las futuras ejecuciones compatibles del Experiment Lab pueden completar una corrida, conservarla como autoridad científica original, calcular una selección económica independiente, publicar sus salidas completas en almacenamiento durable, emitir índices compactos de restauración en Git y registrar fallos del selector separadamente del resultado original. No se construyó un conjunto de cuatro selectores alternativos ni se codificó #209 como una constante.

## 1. Alcance aprobado, decisiones heredadas y límites

### 1.1 Autoridades de capas anteriores

El ticket consumió resultados aceptados de FS-018/019/020 sin reabrirlos:

- **FS-018:** `GLOBAL_PREDICTION_V1 = MARKET_CONSENSUS`, versión `fs013-market-consensus-v2`.
- **FS-019:** `GLOBAL_DECISION_V1 = MODAL_ALL`, matriz de 33 combinaciones Prediction × Decision elegibles y cohorte común de 1.877 partidos, con precios, tiempos, resultados e identidades congelados.
- **FS-020:** `GLOBAL_CAPITAL_V1 = FRACTIONAL_KELLY(lambda=0.25,max_lanes=10)` como autoridad local del estudio de Capital, con resultado científico local `UNSTABLE`. Su evaluación original utilizó 1.906 oportunidades; **no** se equipararon sus saldos directamente con los del universo FS-021 de 1.877.
- **FS-020 E2.4/V2R:** precedencia **lane-before-`policy.request`** en Event-Time. Los incidentes previos de conformidad V1→V2R y SHA de research modificado por hooks se trasladaron explícitamente al diseño de gates FS-021.

Estas selecciones locales se conservaron como referencias, no como filtros que eliminaran a las demás combinaciones del nuevo torneo. La selección acumulativa podía diferir de cualquiera de ellas sin que eso reescribiera sus resultados históricos.

### 1.2 Universo integrado completo

La matriz aprobada fue de **33 Prediction × Decision × 7 Capital = 231** brazos, con índice canónico `integrated_index = pd_index * 7 + capital_index`:

- `DIXON_COLES`, `INDEPENDENT_POISSON` y `ELO_MULTINOMIAL_LOGIT`, cruzados con las nueve alternativas Decision autorizadas para cada una: `MODAL_ALL`, cinco umbrales `SELECTIVE_CONFIDENCE(0.40/0.45/0.50/0.55/0.60)` y `VALUE(0/0.02/0.05)`; total **27**.
- `MARKET_CONSENSUS`, cruzado sólo con `MODAL_ALL` y los cinco `SELECTIVE_CONFIDENCE`; total **6**. Se mantuvo fuera `MARKET_CONSENSUS × VALUE` por la circularidad entre la predicción de mercado y la regla de valor basada en precios.
- Cada una de las 33 cruzada con siete Capital CURRENT: `FLAT_UNIT(1u,10 lanes)`, `FIXED_FRACTION_BANKROLL(0.05,10)`, `FIXED_TARGET_PROFIT_NO_RECOVERY(target=1,10)`, `LEGACY_RECOVERY(initial=1,1)`, `LEGACY_CAPPED(initial=1,max_stake=5,1)`, `LEGACY_PARTIAL(target=1,alpha=0.5,1)` y `FRACTIONAL_KELLY(lambda=0.25,10)`.

La población fue una única cohorte de **1.877 Match IDs** de **10 competiciones**, distribuida sobre **36 semanas Lima**, incluidas **seis semanas sin oportunidades**. Las observaciones de precio usan el contrato `ODDSPAPI_RECONSTRUCTED_T30_V1`, con ejecución sintética a `kickoff−30m`, resultado reglamentario y procedencia upstream retenida. Los 33 streams conservan tanto `BET` como `NO_BET` y su orden temporal: no se eliminó una oportunidad porque otra política Capital dejara de apostar.

Cada brazo parte con una **banca independiente de 100u** para todo su conjunto de partidos y competiciones. Dentro de un brazo, las lanes comparten esa única banca. Nunca se multiplicó el bankroll por lane, ni se transfirió capital sobrante desde lanes agotadas a una supuesta lane principal. El estado de cada política y cada réplica es independiente.

### 1.3 Límites mantenidos

Se prohibió el descarte económico top-N antes de cerrar la evidencia, el pruning de candidatos ruinosos fuera del experimento, cambiar una cuota o parámetro para obtener un ganador, utilizar información futura o producir resultados científicos cross-lag no calculados. El ticket no implementó shadow/live betting, no activó CURRENT, no modificó la base operacional ni consumió cuota de proveedores para repetir un experimento que podía ejecutarse con inputs retenidos. La activación prospectiva y el cutover pertenecen a FS-022 o al ticket de producto que los autorice.

## 2. Principal aporte semántico de Capital: agotamiento operacional a 5u

### 2.1 Por qué fue necesario

El estudio FS-020 dejó claro que la simulación debía separar **ruina matemática**, **terminación propia de la política**, **falta temporal de cash o lanes** y **agotamiento operacional de una combinación completa**. Una regla que detuviera el experimento en cuanto el saldo disponible bajara de 5u habría liquidado incorrectamente posiciones todavía abiertas, atribuido un resultado prematuro o perdido información posterior recuperable.

FS-021 congeló la regla `FS021_OPERATIONAL_DEPLETION_5U_AFTER_ALL_OPEN_V2`, con `DEPLETION_FLOOR = Decimal("5")`, exclusivamente para el motor experimental integrado. **El umbral se decide a nivel de combinación completa, nunca por lane**, y se evalúa con `equity`, no con `available_cash`.

### 2.2 Orden Event-Time y máquina de estados

Para cada wake se deben liquidar todas las posiciones `OPEN` vencidas en orden `(settlement_at, position_identity)`, liberar reservas y lanes, actualizar `policy.settle`, equity y los indicadores de riesgo, y sólo entonces comprobar el umbral. También se registra `ever_nonpositive_equity` si se materializa dentro de un batch, aunque liquidaciones posteriores recuperen el saldo.

Cuando `equity<=5u` y quedan posiciones `OPEN`, la combinación entra en `AWAITING_FINAL_OPEN_SETTLEMENT`: no solicita nuevas apuestas ni abre posiciones; continúa liquidando todas las abiertas y registra correctamente la expiración lógica de pendientes. **No vuelve a ACTIVE** porque una liquidación intermedia deje el saldo por encima de 5u si todavía existe alguna OPEN de la pausa. Al liquidarse la última, sólo hay dos transiciones: `equity>5u` permite volver a ACTIVE sobre oportunidades todavía pre-kickoff; `equity<=5u` fija `OPERATIONAL_DEPLETION` y cierra la apertura de apuestas futuras de ese brazo.

Si el umbral se alcanza con cero OPEN, se detiene antes de cualquier retry/placement del wake. `PENDING_CAPACITY`, `EXPIRED_CAPACITY`, `ZERO_STAKE`, `TERMINATED`, ruina económica y depletion conservan causas distintas. Se respetó V2R: controles de kickoff y lane **antes** de `policy.request`; después, precedencia de termination, cero stake, cash insuficiente y colocación.

### 2.3 Fixture D05 y conservación del universo

La investigación contenía una errata editorial: decía «dos OPEN», pero el caso describía tres liquidaciones. F008 aprobó la corrección acotada **sin reescribir la investigación histórica**: tres posiciones OPEN iniciales; la primera deja 3u, la segunda 6u con una OPEN restante, y la tercera 9u. El brazo debe seguir pausado hasta la tercera y sólo entonces reanudar ACTIVE. Fue incorporado al contrato de conformidad ejecutable.

Después de `OPERATIONAL_DEPLETION`, el sistema deja de consumir físicamente futuros wakes costosos, **pero no borra la cohorte ni el registro lógico**. Los futuros BET se expanden como `NOT_EXECUTED_AFTER_OP_DEPLETION`, los NO_BET se conservan y las pendientes restantes cierran con `PATH_STOPPED_OP_DEPLETION`. El saldo terminal se prolonga hasta el mismo horizonte comparable de las demás combinaciones. El camino optimizado `fast_stop` tiene que ser semánticamente idéntico al `scalar_full_scan`, incluyendo ledger lógico, hashes del sufijo indexado, duración y drawdown. Este diseño redujo trabajo sin falsificar la cardinalidad del torneo.

## 3. Del diseño al código: módulos, interfaces y conformidad

La implementación quedó distribuida en módulos acotados de `football/experiments/`: `integrated_inputs` reconstruye y autentica entradas y calendario; `integrated_events` ejecuta el estado Event-Time y las transiciones de capital; `integrated_runner` orquesta los paths observados, shards bootstrap y estabilidad; `integrated_conformance` verifica semántica adversarial; `integrated_analysis` produce la comparación original; `integrated_artifacts` autentica/publica el resultado histórico. `run_integrated_experiment` ofrece freeze/technical/observed/bootstrap/stability/finish/status, recuperación y publicación sobre una ejecución existente. `tools/fs021_supervisor.py` gobierna el host y sus alarmas. Después se incorporaron `economic_metrics`, `economic_selector`, `economic_report`, `economic_diagnostics` y `tools/fs021_cleanup_research.py`.

Antes del torneo costoso se exigieron tres gates **independientes**:

| Gate | Evidencia exigida y observada |
|---|---|
| `INPUT_AND_ARTIFACT_INTEGRITY` | 33 identidades y 61.941 filas originales (33 × 1.877), orden canónico, 231 brazos, 36 semanas/6 vacías, diez ligas, identidad de fuente/precio/resultado y material retenido restaurable. |
| `SEMANTIC_CONFORMANCE` | C01–C12 heredados de FS-020 V2R y D01–D14 de 5u/pausa/agotamiento. D05 utiliza tres OPEN. Se contrasta la referencia contra el motor FS-021, no sólo contra tests que reutilizan las mismas suposiciones. |
| `RUNNER_EQUIVALENCE` | `scalar_full_scan == fast_stop` en significado económico y ledger expandido, hashes del sufijo, mutaciones adversariales, shards enteros/divididos, ejecución con distinto número de workers, restart/readback, rechazo de corrupción/truncados. |

Una mutación concreta cambió el outcome del último Match del stream original en una copia de pruebas. El verificador produjo `STOP_TECHNICAL:PACK_HASH:pd_33_streams.jsonl.gz` con **cero paths económicos** calculados. Esta prueba fue relevante porque un fast-stop podría no visitar físicamente el Match adulterado; el hash del stream completo debe seguir detectándolo.

El Pass 1 registró **892 pruebas PASS y 82,60 % de cobertura** tras corregir un test de inventario que inicialmente desconocía el nuevo management command. Estos números corresponden a **esa versión intermedia**, no al cierre. También documentó que el fixture D13 es adversarial de máquina de estados y no una trayectoria natural generable desde 100u por las políticas CURRENT con conservación de cash. No se manipuló el modelo para fabricar ese caso.

## 4. Supervisor de host, recursos y ejecución larga

La ejecución se diseñó para una PC local de uso prolongado, no para un cluster. El supervisor mantuvo estado y checkpoints, distinguió `COMPLETE`, `PAUSE_RESOURCE` y `STOP_TECHNICAL`, registró heartbeat, permitió control cooperativo, alarma audible y ACK explícito. El ACK **silencia la incidencia**, pero no reanuda automáticamente la ejecución ni convierte un fallo en éxito.

Durante el Pass Review aparecieron defectos reales que se corrigieron antes del cómputo: un monitor sin worker no terminaba limpiamente ante SIGTERM/Ctrl+C; los IDs de alarmas idénticas reutilizaban un ACK anterior y podían silenciar una nueva incidencia; un backend de audio podía fallar sin registrar su `stderr`; y la pausa térmica del bootstrap sólo se comprobaba después de 231 candidatos, con latencia excesiva. La corrección pasó a comprobar control entre candidatos, descartando únicamente la réplica parcial no confirmada y reteniendo los shards completos. `audio_failure.json` y `AUDIO_UNAVAILABLE` proporcionan evidencia cuando el reproductor host no funciona, sin falsear la alarma/ACK.

La UAT original del supervisor también enseñó una lección de orquestación: un helper encadenó procesos sin esperar el ACK y creó alarmas simultáneas; otro comando UAT de Django con `python -` omitió `DJANGO_SETTINGS_MODULE`/`django.setup()` y falló antes de ejercitar el runner. Ninguna de estas salidas se convirtió artificialmente en una regresión del modelo. Se preparó un helper con directorios aislados, ACK y timeouts acotados. **El último material compartido confirma finalización del supervisor (`returncode=0`, `COMPLETE`), pero no contiene un acta separada que certifique la audición humana real del nuevo backend**: ese dato no se inventa en el feedback.

### 4.1 Presupuesto medido, no supuesto

El estudio observado produjo **693 paths físicos** en aproximadamente **105 segundos de pared**, con aproximadamente **2,75 millones de eventos físicos** y **1,10 millones de wakes**. La medición fue de aproximadamente **6,60 paths/s observados**, y el presupuesto inicial extrapolado del observado se etiquetó expresamente como **proyección aritmética, no certificación térmica sostenida**.

Para el bootstrap completo se llegó a trabajar con **ocho workers** en un Intel Core i9-12900KF, 24 CPUs lógicas y 32 GiB de RAM. Existieron intentos interrumpidos: uno a 12 workers se detuvo con Ctrl+C; una configuración inicial a ocho workers provocó `PAUSE_RESOURCE` alrededor del límite preventivo de 80 °C; se reanudó con supervisión y umbral de 85 °C, conservando los shards válidos. La finalización total acumuló aproximadamente **2 h 05 min de tiempo de trabajo bootstrap activo**. En las lecturas periódicas retenidas de ocho workers se registraron CPU mediana **79 °C**, máximo registrado **83 °C**, y NVMe máximo **43,85 °C**. Estas son **muestras, no máximos térmicos continuos ni garantía futura**. No se requirió GPU.

La inferencia operativa del incidente es precisa: dimensionar workers a partir del observado y de muestras térmicas, permitir pausa y recuperación deterministas, no relanzar shards completos por ceremonia y no aumentar el umbral simplemente para alcanzar una fecha. El progreso y los logs deben escribirse fuera de las matrices científicas congeladas; una parada nunca debe dejar una réplica parcialmente válida publicada como completa.

## 5. Torneo histórico realizado y evidencia científica original

### 5.1 Cardinalidad y diseño estadístico

La ejecución completa `fcd8…7372` entregó las siguientes cardinalidades:

| Etapa | Cardinalidad | Alcance científico |
|---|---:|---|
| Observado | 231 candidatos × 3 lags = **693** paths | T+120, T+130 y T+150 como sensibilidad económica observada. |
| Bootstrap pareado | 231 × 5.000 × 3 bloques = **3.465.000** paths | **Sólo T+150**; moving-block global de 1, 2 y 4 semanas. |
| Estabilidad | 231 × 12 slices = **2.772** paths | H1/H2 y diez exclusiones de una liga, T+150. |
| Total conceptual | **3.468.465** paths | El fast-stop ahorra eventos, no borra brazos/réplicas ni reduce inferencia. |

Cada réplica bootstrap empieza con un estado Capital fresco de 100u; el calendario de bloques es común para los 231 candidatos y se genera con `Generator(PCG64(SeedSequence([21092026,L])))` para cada tamaño `L`. Las matrices durables `scores-150-1.npy`, `scores-150-2.npy` y `scores-150-4.npy` tienen cada una forma `(5000,231)` y se conservaron con sus manifiestos. La familia all-pairs contiene **26.565 pares** `i<j` por diseño; el análisis previsto es studentized simultaneous max-t con FWER del 95 %, cuantíl NumPy lineal y el contrato explícito para `se==0`. La estabilidad exige comparar al líder original observado contra todos los demás en cada slice, sin elegir un nuevo líder dentro del slice. No se fingió bootstrap sobre los lags 120/130: `CROSS_LAG_INFERENCE=NOT_EVALUATED_BY_FS021_V1`.

### 5.2 Resultado histórico original: #60

La regla práctica congelada `FS021_INTEGRATED_MAXIMIN_LAG_5U_V1` aplicó integridad, ausencia de hard-risk/depletion en cada lag y actividad mínima **en cada lag** (38 colocaciones, tres ligas y cuatro semanas Lima); entre los elegibles maximizó el retorno observado mínimo entre los tres lags, con sus desempates aprobados.

El resultado fue **integrated #60**, `DIXON_COLES × VALUE(0.05) × LEGACY_CAPPED(initial=1,max_stake=5,max_lanes=1)`. A partir de 100u, su equity final fue **243,404u** en T+120, **224,259u** en T+130 y **237,793u** en T+150. Su retorno mínimo observado fue **+124,2594 %**, con peor máximo drawdown observado de **78,51 %**. Cumplió la regla original, pero ese gran retorno retrospectivo no implicó por sí mismo una exposición o una cola aceptables para un selector económico posterior.

El líder científico observado bajo T+150 fue **#115**, distinto de la selección práctica #60. Sin embargo, la estabilidad por slices no pasó —incluido H2 y múltiples exclusiones de ligas— y `strict_top_vs_all` no pasó en los bloques 1, 2 ni 4. La publicación científica original quedó `UNSTABLE`. El hallazgo demuestra por qué se diseñaron autoridades separadas: una regla práctica determinista puede entregar una composición identificable cuando la evidencia está íntegra sin convertir automáticamente esa composición en un descubrimiento estadístico estable.

### 5.3 Publicación e identidad original

El `run.json` de la ejecución está `COMPLETE`; conserva `practical_selection`, `scientific_evidence`, `activation=false` y sus bindings. El original `spec.json`, `observed.json`, 693 ledgers lógicos, matrices/bootstrap, slices y manifiestos siguen siendo **autoridad histórica inmutable**. Se exige lectura autenticada y semántica cuando un consumidor posterior necesita recomputar resultados. Una exportación de chat o ZIP de auditoría fue útil para diseñar y comprobar, **nunca** sustituto de los ocho inputs físicos retenidos ni de la ejecución del host.

## 6. Segunda investigación: por qué el resultado original no bastaba como baseline económica

La primera elección cumplía el ticket inicial: devolvía exactamente una composición práctica y preservaba el veredicto científico. Sin embargo, las observaciones de la ejecución completa mostraron un problema de producto: **ordenar sólo por retorno mínimo podía preferir trayectorias con drawdowns, concentración o pérdidas extremas de cola que hacían poco útil la baseline para avanzar hacia una evaluación de capital responsable**. El caso #60, con retorno mínimo superior al 124 % pero drawdown cercano al 79 %, motivó una capa posterior explícita. No se alteró el experimento para que eligiera otra cosa.

Se ejecutó una investigación independiente sobre la evidencia retenida: 231 resultados observados completos, 693 ledgers y las tres matrices de retornos terminales de 5.000 réplicas. La investigación distinguió datos físicos, hipótesis, limitaciones y simulaciones post hoc; examinó alternativas metodológicas y propuso **una única función económica determinista** en vez de mantener cuatro métodos M1–M4 como autoridades alternativas y pedir una elección manual al finalizar cada torneo. La propuesta se documentó en `FS-021_economic_selector_research_v1.md` y la adenda específica del ticket; el research es `REFERENCE ONLY` en el repositorio y las decisiones ejecutables quedaron en el método versionado y tests.

La investigación inicial sobre una copia portátil no podía certificar que los ocho inputs upstream originales existieran en el host ni resolver los sufijos lógicos de 139 trayectorias que habían terminado por depletion. El preflight posterior **sí operó sobre el checkout y la ejecución nativa**: 693/693 ledgers físicos, **554** hashes de ledgers sin sufijo más **139** sufijos lógicos sometidos a conformidad nativa, tres matrices `(5000,231)`, 12 slices y ocho inputs originales. Su estado fue `PASS`, cero STOP y dos REVIEW no metodológicos: checkout con cambios en curso e índice de retención aún no encontrado en la raíz. Ambos se trataron como trabajo de publicación/retención, no como excusa para perder el estudio ni cambiar #60.

**Regla de investigación aprendida:** un análisis post hoc puede justificar una regla prospectiva para las próximas ejecuciones, pero su reproducción sobre los mismos 231 datos es **una regresión del algoritmo, no validación out-of-sample**. El selector económico se aceptó como una nueva autoridad práctica para simulación; no se declaró `CLEAR_SUPERIORITY`, y la disposición científica original no se recalculó para favorecer a #209.

## 7. Contrato del único `FS021_SINGLE_ECONOMIC_SELECTOR_V1`

### 7.1 Entradas autenticadas y salidas

El consumidor acepta resultados de un experimento **ya completo y compatible**, lee `spec.json`, `run.json`, observado, 693 ledgers, matrices terminales, estabilidad y ocho inputs upstream retenidos con sus bindings; deriva métricas económicas sin repetir el motor Capital. La instancia histórica FS-021 requiere 231 índices canónicos, tres lags observados y tres matrices T+150, pero el módulo puro se diseñó para recibir un número `N` de candidatos válido y un contrato de dimensiones verificable en futuras ejecuciones compatibles. No incorpora ninguna condición `if index == 209` ni una selección previa escrita por el chat.

La publicación guarda **todos los 231 candidatos**, razones de exclusión o selección, frontera, límites, diagnósticos, resumen top 20 y una sola autoridad económica machine-readable. A falta de un input obligatorio recuperable, el resultado correcto es STOP y restauración, nunca reemplazarlo por otro histórico disponible. Las salidas de la selección y del reporte se versionan de forma separada para conservar los resultados ya publicados.

### 7.2 Métricas decisorias, diagnósticas y benchmark

Para cada candidato se calcula:

- `R = min(retorno_120, retorno_130, retorno_150)`, con retornos observados en `Decimal` sobre el mismo bankroll inicial de 100u.
- `D = max(max_drawdown_120, max_drawdown_130, max_drawdown_150)`, tomando el peor drawdown de los tres caminos observados.
- `CVaR5_L` para `L∈{1,2,4}`: media de los **250 peores retornos terminales** de sus 5.000 réplicas bootstrap T+150. `L_risk = −min(CVaR5_1,CVaR5_2,CVaR5_4)`; es pérdida de cola y puede resultar negativa cuando hasta la cola tiene beneficios. No debe recortarse artificialmente a cero.
- La mediana de retorno bootstrap por bloque, que debe ser estrictamente positiva cuando el tier lo exige.

El benchmark usado es **7 % efectivo anual hipotético**, convertido al horizonte de 36/52 semanas: aproximadamente **4,7955 %** de retorno para ese horizonte. Es una referencia de costo de oportunidad **sin equiparación de riesgos, liquidez o divisa**; no representa una tasa bancaria garantizada observada. No se ajustó a posteriori para hacer ganar a #209.

Se derivaron, además, métricas que **no son pesos ocultos del selector**: reconciliación P&L/equity; 252 observaciones de equity al cierre diario Lima (incluyendo semanas vacías y saldo plano tras depletion); CDaR95 diario como media de los 13 peores drawdowns diarios; duración bajo el máximo y recuperación; exposición reservada media temporal y pico; mínimos de cash/equity; recuentos de posiciones; concentración del P&L positivo en las cinco oportunidades mayores; distribución por competición/semana cuando la procedencia se pudo reconstruir; H1/H2 y leave-one-league-out. Una métrica sin procedencia upstream se marca `UNAVAILABLE_UPSTREAM`, no se estima silenciosamente.

Para el bootstrap **histórico** FS-021 sólo existen scores terminales. Los verdaderos drawdown y depletion **intraréplica** no se reconstruyen a partir del saldo terminal: `terminal_equity<=5u` es únicamente un proxy. Los nuevos acumuladores streaming del runner permiten opcionalmente que futuras ejecuciones congeladas con `FS021_BOOTSTRAP_RISK_V1` publiquen matrices intraréplica de riesgo; no se reejecutaron por este motivo los 3.465.000 caminos históricos. La disponibilidad de estas matrices debe reflejarse literalmente en el reporte: `AVAILABLE` cuando fueron autenticadas; `UNAVAILABLE_UPSTREAM` cuando no existen.

### 7.3 Política de selección en cinco tiers

El selector **siempre elige el primer tier no vacío** y considera, si existe, una combinación con `R>0` antes de cualquier salida de diagnóstico:

| Tier | Criterio, además de `R>0` |
|---|---|
| 1 | `R` supera el benchmark efectivo de 36 semanas; sin hard-risk observado, depletion ni terminación; actividad mínima FS-021 en los tres lags; medianas bootstrap positivas en los tres tamaños de bloque. |
| 2 | Los mismos gates de limpieza/actividad/mediana del Tier 1, pero sólo exige `R>0`, no superar benchmark. |
| 3 | Sin hard-risk y con actividad suficiente en los tres lags; no exige medianas positivas. |
| 4 | Sin hard-risk, aunque falte actividad. |
| 5 | Cualquier `R>0` restante; permite entregar una única composición **sólo para simulación** con advertencias de riesgo, aun si existe depletion o drawdown extremo. |

En el primer tier no vacío se construye la **frontera Pareto** con `R` mayor, `D` menor y `L_risk` menor. Los umbrales de drawdown y pérdida de cola son robustos leave-one-member-out: para cada métrica, el mínimo de las medianas obtenidas al retirar cada miembro de la frontera (o su propio valor si existe un solo miembro). Pasan las composiciones con ambos riesgos dentro de sus umbrales más `1e−12` de tolerancia de redondeo. De las supervivientes se elige `R` mayor y, en empate, `L` menor, `D` menor, mayor actividad y menor índice canónico.

Si nadie supera ambos límites, el fallback minimiza el peor incumplimiento de riesgo normalizado con escala `max(IQR(method=linear), MAD, 1e−12)` y conserva el desempate congelado; **no se introduce otra metodología secreta**. Un fallback fuera de límites, hard-risk, actividad insuficiente, drawdown de al menos 50 % o pérdida de cola de al menos 95 % generan advertencias `HIGH_RISK`, sin veto económico universal que deje el selector sin identidad cuando todas las opciones positivas sean arriesgadas. Si **ninguna** tiene `R>0`, se elige una de `R==0` como `BREAKEVEN_SIMULATION_ONLY`; sólo cuando todas son negativas se emite una identidad `DIAGNOSTIC_ONLY__NO_NEW_STAKES`. Un defecto de integridad no utiliza esos estados para ocultar el problema: `TECHNICAL_STOP_RESTORE_REQUIRED`.

## 8. Resultado económico auténtico y explicación de la #209

La implementación sobre el host reprodujo el check de regresión de la investigación **sin usar su CSV como fuente de ejecución**. Se obtuvieron los 20 candidatos del primer tier, nueve en la frontera `#31, #60, #157, #173, #195, #202, #209, #216, #223`, y tres supervivientes simultáneos de riesgo **#209, #216 y #223**. Los límites fueron aproximadamente `T_D=21,4276 %` y `T_L=25,7525 %`.

La selección final de esa función fue **#209**, `MARKET_CONSENSUS/fs013-market-consensus-v2 × SELECTIVE_CONFIDENCE(threshold=0.45) × FRACTIONAL_KELLY(lambda=0.25,max_lanes=10)`. Resultados observados sobre 100u:

| Magnitud #209 | Resultado |
|---|---:|
| Equity T+120 | 166,6712u |
| Equity T+130 y T+150 | 166,6733u |
| Retorno mínimo entre lags (`R`) | **+66,6712 %** |
| Peor MDD observado (`D`) | **12,2285 %** |
| Pérdida de cola de peor bloque (`L_risk`) | **17,5961 %** |
| CDaR95 diario peor-lag | ≈11,82 % |
| Mínimo de posiciones colocadas entre lags | 111 |
| Stability slices positivos | 11 de 12 |
| H2 | negativo, aproximadamente −8,75 % |
| Concentración top-5 del P&L bruto positivo | aproximadamente 73 % |

La elección no se debe a que #209 tenga mayor retorno histórico que todas las alternativas. La #60 alcanza un retorno mínimo mucho más alto, pero su drawdown y pérdida bootstrap de cola quedan fuera de ambos límites robustos. La #202 también tiene `R≈+84,87 %`, pero su `L≈33,91 %` sobrepasa el umbral de cola ≈25,75 %. Entre las tres supervivientes, #209 presenta mayor `R`: #216 ronda +65,59 % y #223 +45,17 %. Los 231 registros y sus métricas siguen retenidos, incluidos candidatos agotados, negativos y descartados sólo de la banda de selección.

**Limitación material, no nota decorativa:** #209 conserva H2 negativo y alta concentración de ganancias en pocas oportunidades. Que 11 de 12 slices sean positivos no convierte el resultado en prospectivo ni revierte `UNSTABLE`; el selector y sus límites se estudiaron después de observar esta misma muestra. Cualquier decisión posterior sobre despliegue necesita una cohorte prospectiva o shadow, evaluación de oportunidad y riesgo de capital, y autorización explícita separada.

## 9. Implementación permanente, publicación y compatibilidad futura

### 9.1 Automatismo correcto sin confundir estados

La fase económica se engancha a la finalización satisfactoria de una ejecución **compatible** del Experiment Lab, después de que los resultados originales estén completos. El análisis económico se registra con **estado propio**; una incidencia del selector no debe transformar silenciosamente el éxito histórico de `run.json` en un supuesto resultado económico válido, ni obligar a repetir el torneo original. `--analyze-existing` permite consumir una ejecución física ya retenida; `--publish-existing` y `--publish-economic-existing` separan los publicadores. La repetición sobre la corrida cerrada se probó sin replay de bootstrap.

`run_integrated_experiment --status` quedó ampliado para mostrar `economic_analysis_status.json` junto con supervisor, worker y gates. La última salida local entregada por el maintainer muestra `worker=COMPLETE`, `supervisor=COMPLETE`, `INPUT_AND_ARTIFACT_INTEGRITY=PASS`, `RUNNER_EQUIVALENCE=PASS`, `SEMANTIC_CONFORMANCE=PASS` y selector económico `COMPLETE` con `winner=209`, `upstream_retention_index=PRESENT`. El resultado mantiene `automatic_operational_routing=false` y `real_betting=false`.

### 9.2 Corregir top 20 e idempotencia sin reescribir v1

La primera versión del informe económico ordenaba el «top 20» por retorno mínimo bruto: situaba a #60 arriba aunque la función económica hubiera elegido #209. El selector puro era correcto, pero el informe podía inducir a leer otra composición como promovida. Se corrigió el **orden explicativo**: composición seleccionada primero; después las restantes que pasan ambos límites; luego la frontera no superviviente y los demás grupos. `economic_231.csv` conserva el universo íntegro por índice canónico.

Otra discrepancia apareció cuando la primera publicación económica había grabado `upstream_retention_index=MISSING_REVIEW` dentro de una salida inmutable. Al completarse el índice durable, una repetición habría regenerado `PRESENT`, causando un falso conflicto de publicación. Se separó el **estado mutable de retención** del resultado económico científicamente inmutable y se creó la salida corregida **`economic_selection_v1_1/`**, conservando sin sobrescribir `economic_selection_v1/` y la publicación original. Los diagnósticos corregidos residen en `economic_diagnostics_v1_1/`. Los manifiestos históricos y sus hashes publicados se respetan.

En el review de código apareció además la sensibilidad innecesaria de incluir un SHA de los **bytes del archivo Python** como si cada cambio de Black o whitespace fuera cambio de metodología. La regla durable es: un manifest puede contener procedencia del código, pero una fuente Python formateada no debe ser, por sí sola, el gate que invalide una evidencia económica cuyo contrato y datos no han cambiado. El método, contrato ejecutable, versión y hashes de entradas/salidas siguen siendo obligatorios. **La eliminación del pin cosmético fue propuesta en el cierre pre-PR; este feedback no presume su merge ni altera los manifiestos ya publicados.**

### 9.3 PR #27: informe humano dependiente del estado real de riesgo

El review independiente del PR señaló **un comentario P2 válido** en `football/experiments/economic_report.py`: `build_economic_analysis()` ya sabe si las matrices `FS021_BOOTSTRAP_RISK_V1` están `AVAILABLE`, pero el Markdown decía incondicionalmente que drawdown y depletion intraréplica eran `UNAVAILABLE_UPSTREAM`. En la ejecución histórica esa frase es correcta; en una futura corrida con matrices autenticadas sería falsa y contradiría el JSON.

La corrección delimitada propuesta es derivar la oración del campo `bootstrap_intrareplicate_diagnostics.status`. Si es `AVAILABLE`, validar schema/columnas y describir las métricas retenidas; si es `UNAVAILABLE_UPSTREAM`, mantener **literalmente** el mensaje histórico; cualquier estado inesperado debe causar error. Los tests deben cubrir ambos casos, y la UAT afectada sólo necesita las rutas de generación del informe —no repetir 3.465.000 paths—. **Estado documental al corte:** comentario y corrección identificados; no se adjuntó aún confirmación de push/CI verde o review resuelto después de esta corrección. F009 exige confirmarlos antes de incorporar este texto como feedback final en Git.

## 10. Contrato definitivo de ubicación, retención y restauración

El cierre de implementación identificó un problema serio de empaquetado: **resultados generados automáticamente y matrices estaban siendo copiados directamente a `docs/research/`**, carpeta reservada para investigación maintainer-owned. Además de ensuciar el PR y crecer en Git con cada ejecución, esa decisión confundía un estudio científico regenerable/retirable con el documento que lo justifica y mezclaba controles de formato narrativo con hashes de datos.

La solución persistente es la siguiente:

| Ubicación | Propietario y contenido permitido | Política |
|---|---|---|
| `docs/research/` | Investigación metodológica de FS-021, investigación económica y addendum de alcance aprobado. | Tres Markdown de autoridad humana; **no** se vuelcan resultados por ejecución. |
| `~/Documents/finsport/research-evidence/FS-021/<execution_id>/` | `spec.json`, `run.json`, observado, ledgers/índices, matrices, slices, retención, publicación original v1, selección y diagnósticos económicos v1/v1.1. | Fuente física durable del experimento. No borrar ni sobrescribir sin contrato de restauración y condición de retención cumplida. |
| `docs/experiments/FS-021/<execution_id>/` | `original_v1.json`, `economic_v1_1.json`, `diagnostics_v1_1.json`. | **Índices compactos** versionados que señalan archivos y manifests durables autenticados; no sustituyen la evidencia. Los locks de ejecución quedan ignorados por Git. |
| `tmp/FS-021_*` | Preflight, UAT, paquetes para revisión, logs de depuración y copias restauradas temporales. | Descartable sólo cuando las evidencias útiles están autenticadas y retenidas fuera de `tmp/`. |
| `docs/process/FS-021_feedback.md` | Feedback de cierre del ticket. | Documento narrativo de proceso, fuera de research y de la carpeta de resultados por ejecución. |
| `~/Documents/finsport/FS-021/` | Ticket aprobado y material de autorización maintainer-owned que no se versiona en el repositorio. | Permisos y acceso explícitos para Codex; no volver a copiar el ticket a `docs/development/`. |

### 10.1 Limpieza autenticada y conservación histórica

La herramienta `tools/fs021_cleanup_research.py` exigió que existieran y coincidieran los índices originales, económicos y de diagnósticos, verificó los manifiestos durables y el top 20 corregido, rechazó archivos tracked/symlinks y ejecutó primero un **dry-run sin borrado parcial**. El primer intento detectó una sola divergencia: `FS-021_retention_manifest.json` tenía exactamente los **15.728** mismos artefactos y metadatos a ambos lados, pero `durable_root` era `/evidence/<execution_id>` en la copia portable y una ruta absoluta bajo `~/Documents/finsport/...` en la autoridad durable.

Se introdujo una **equivalencia semántica estrictamente limitada** a ese manifiesto, comprobando igualdad de los demás campos e inventarios y las dos rutas esperadas. No se relajó la comparación de todos los archivos ni se reconstruyó el manifiesto original para hacer coincidir un SHA narrativo. El `--apply` posterior informó: **17 duplicados verificados y eliminados**, preservando los tres documentos Markdown de FS-021 en `docs/research/`. El estado Git mostrado después contenía únicamente esos tres documentos y `docs/experiments/` como nuevas rutas de documentación; los grandes outputs ya estaban bajo la ejecución durable.

Se repitieron los comandos de análisis/publicación con la raíz correcta —**el padre `.../research-evidence/FS-021/`, no la carpeta del execution ID**— y se verificó la idempotencia mediante hashes antes/después de las publicaciones. No se ejecutó otra vez el bootstrap. Esta distinción entre raíz y ejecución también queda como lección para la interfaz CLI y la guía de UAT.

### 10.2 Qué debe poder hacer un consumidor posterior

El consumidor FS-022 u otro ticket debe leer el locator Git, resolver la raíz durable configurable, comprobar ejecución/versión/manifests y autenticar únicamente los archivos científicos **realmente consumidos**. Si la evidencia no está montada en la nueva máquina, debe restaurarla desde su paquete retenido y demostrar igualdad de identidad/semántica antes de seguir. Un path absoluto de `/home/ljarufe` no debe quedar codificado como requisito en el software: el Makefile fue corregido para utilizar `$(HOME)` y `FS021_ROOT` configurable. La autoridad científica original #60 y la económica #209 se recuperan por índices **distintos**, nunca reescribiendo uno para que apunte a otro.

Los hashes que siguen siendo necesarios protegen cohortes, streams, scores, ledgers, run/spec/manifests, publicación inmutable e índices compactos de recuperación. No es necesario convertir whitespace de research, formato Black de Python, ruta mutable de host ni estado de retención en condiciones artificiales de identidad científica. Documentos narrativos sujetos a pre-commit sólo deben ser `byte-exact` si una autoridad aprobada exige expresamente ese contrato.

## 11. UAT, pruebas y aceptación observada

La aceptación no se basó únicamente en una salida de `pytest` ni en un `COMPLETE` del supervisor. Se ejercitaron capas distintas: conformance contra referencia, mutaciones de input, equivalencia scalar/fast, lectura de outputs históricos, reproducción del selector sobre el host, retención/restauración, limpieza y repetición de publicaciones. El alcance de las pruebas se redujo **por delta** cuando se corrigieron errores documentales o de presentación, evitando volver a ejecutar el estudio más costoso por fallos que no invalidaban los scores.

### 11.1 Evolución de los gates

| Momento | Resultado comunicado | Alcance y limitación |
|---|---|---|
| Pass 1 técnico | **892 passed; 82,60 %** | Tras añadir el management command al inventario; C01–C12, D01–D14, integridad y equivalencia. No demostraba todavía el torneo histórico final. |
| Implementación inicial del selector económico | **903 passed; 80,91 %** | Resultado reportado por Codex antes de la UAT manual y de los cambios de organización posteriores; no se reutilizó como aceptación del diff final. |
| Pre-PR con organización, idempotencia y correcciones manuales | **905 passed; 80,62 %** | Último `make check` completo proporcionado por el maintainer antes del comentario P2; supera el mínimo exigido del **80 %**. |
| Corrección P2 del informe bootstrap | **Pendiente de confirmación en este documento** | Requiere focused test en ambos estados de disponibilidad y CI del commit correctivo. No se atribuyen pruebas que el usuario todavía no comunicó. |

Los errores de tests intermedios también quedaron explicados. El parche de compatibilidad añadió un test de idempotencia con un `result` simulado sin el campo obligatorio `activation`; el publicador falló con `KeyError('activation')`. La solución fue **arreglar el fixture** para declarar `automatic_operational_routing=False, real_betting=False`, no eliminar la validación de seguridad en producción. Una repetición inicial siguió leyendo un fixture sin el campo en el contenedor de desarrollo; se corrigió la función de test exacta y la suite completa volvió a verde. Esta incidencia refuerza la necesidad de probar fixtures con las mismas invariantes públicas que un resultado nativo.

### 11.2 UAT de datos, publicación y borrado

La UAT final de los outputs existentes autenticó la autoridad original, scores y manifiestos; comprobó `winner=209` del selector, autoridad original `#60`, `UNSTABLE`, ausencia de activación, **693** conciliaciones, **139** sufijos lógicos, **231** filas económicas y top 20 explicativo que empieza por la composición seleccionada. La primera versión del script de limpieza se negó correctamente a borrar por la diferencia de `durable_root`. Tras demostrar equivalencia del inventario de 15.728 entradas y acotar el caso especial, la herramienta eliminó **17** duplicados untracked y dejó las tres investigaciones intactas.

La UAT de **idempotencia** capturó los hashes de las publicaciones original, económica v1, económica v1.1, diagnósticos v1/v1.1 e índices Git, repitió `--analyze-existing`, `--publish-existing` y `--publish-economic-existing`, y comprobó que los archivos no cambiaron. El primer intento de esa repetición falló tres veces por un error de invocación: el Makefile recibió como `FS021_ROOT` la **carpeta de ejecución** y añadió de nuevo `--execution-id`, buscando `<id>/<id>/spec.json`. Con la raíz padre `FS-021` los tres comandos finalizaron y la comparación de hashes pasó. El error de ruta se atribuye a las instrucciones de orquestación, no al experimento.

Se comprobó también que `docs/research/` **no volvía a llenarse** al publicar, que `docs/experiments/.gitignore` ignoraba locks `.FS-021_*.lock` y que el `--status` mostraba explícitamente el resultado económico en vez de ocultarlo detrás de `worker=COMPLETE`. No se atribuye ninguna aceptación posterior al merge: aún no se había ejecutado deploy desde `master` al corte de este documento.

## 12. Incidentes de proceso y causas raíz: registro para evitar reincidencia

Este ticket dejó evidencia de problemas de ejecución y de **fallos de nuestras instrucciones**, además de bugs del código. No deben resumirse como una vaga «necesidad de mejorar tests». Se indican el fallo observable, la causa que el material permite establecer, cómo se resolvió y la regla reusable que debe conservarse.

| Incidente | Observación y causa | Resolución / aprendizaje durable |
|---|---|---|
| **P01 — Research no copiado antes del primer prompt** | Se completó el preflight científico, pero se olvidó comprobar que el research aprobado estuviera en el checkout y que Codex pudiera leer el ticket externo. Código de incidente `FS021_PROCESS_PRECODE_RESEARCH_COPY_OMITTED`. | Check binario `APPROVED_RESEARCH_IN_CHECKOUT_AND_TICKET_ACCESSIBLE_OUTSIDE_GIT` antes de Codex. El research entra en `docs/research/`; el ticket aprobado permanece sólo en `~/Documents/finsport/FS-021/`. No repetir todo el preflight científico para corregir una copia documental. |
| **P02 — Ticket copiado indebidamente a Git** | Un helper inicial intentó usar `docs/development/` para el ticket; Pass 1 recreó después una dependencia física de esa copia para `freeze_spec`. Contradecía la autoridad del maintainer. | Retirar el ticket del repositorio y del runtime; conservar su copia externa. Separar autorización humana, documento de investigación y autoridad machine-readable. |
| **P03 — Incidente FS-020 V2R heredado** | En FS-020 se había detectado una contradicción entre el orden de chequeo de lane y el de `policy.request`, además de una especificación estadística insuficientemente ejecutable en fases previas. | Exigir referencia V2R autenticada y gates C01–C12/D01–D14 antes del costoso observado. Los PASS de etapas documentales no sustituyen conformance de código ejecutable. |
| **P04 — SHA narrativo alterado por hooks** | Research congelado por bytes y formatter/pre-commit interactuaban mal: whitespace o EOF creaban conflictos ajenos al significado científico. El riesgo reapareció al preparar el PR FS-021. | Validar temprano el empaquetado y aplicar SHA a los datos científicos consumidos. No hacer depender una publicación económica de la presentación de un Markdown o de un SHA del archivo Python sólo por formato. |
| **P05 — `git diff` parcial sobre untracked** | El primer diff normal no incluía numerosos módulos nuevos y documentos, de modo que una review ordinaria podía inspeccionar un cambio incompleto. | Paquete por pass con `git diff HEAD` + archivos nuevos relevantes; inventario explícito; revisar también consumidor, configuración y código original afectado. No dar un diff incompleto como prueba de sistema. |
| **P06 — Drawdown post-depletion** | El runner inicial prolongaba duración a partir del último Match incluso cuando `terminal_at` era anterior. | Calcular el horizonte efectivo de una trayectoria detenida desde `terminal_at`; conservar por separado el horizonte comparativo de equity plano y el tiempo de exposición/recovery. Prueba D01 específica. |
| **P07 — Supervisor SIGTERM, ACK y sonido** | Sin worker el monitor podía quedar atrapado esperando ACK; una segunda alarma idéntica heredaba el ACK anterior; `stderr` de audio se descartaba. | Terminación controlada sin cerrar la terminal del usuario, nueva identidad tras ACK, `audio_failure.json` y evento `AUDIO_UNAVAILABLE`; prueba humana de audibilidad sólo si efectivamente se observó. |
| **P08 — Pausa térmica tardía** | La comprobación de `control.json` al final de 231 candidatos prolongaba demasiado la reacción térmica. | Consultar control entre candidatos, desechar réplica parcial y conservar sólo checkpoints completos. Configurar temperatura/recursos a partir de pruebas medibles y supervisadas. |
| **P09 — UAT mal invocada y auxiliares inseguros** | Un script `python -` no inicializó Django; otro encadenó supervisores sin ACK; el patrón `pkill` no identificó siempre el proceso real. | UAT local con Django inicializado cuando corresponde, PID propio, directorio aislado, ACK y timeout; no interpretar errores del harness como defectos científicos. |
| **P10 — No encontrar toda la retención original** | El ZIP portable contenía salidas útiles pero no probaba existencia de ocho inputs upstream en el host; 139 sufijos requerían verificación semántica nativa; faltaba `RETENTION_INDEX.tsv` al primer preflight. | Recuperar/autenticar las ocho entradas, verificar 554 ledgers directos +139 sufijos, producir el índice durable y no tratar la exportación de chat como nueva fuente primaria. |
| **P11 — Research convertido en almacén de ejecución** | Publicadores copiaban JSON, CSV, equity diario y manifiestos directamente a `docs/research/`; el PR acumulaba resultados generados. | Publicación durable por ejecución; `docs/experiments` sólo índices compactos; herramienta de cleanup con verificación, dry-run y fail-closed. 17 duplicados eliminados. |
| **P12 — Informe top 20 contradictorio** | Un reporte ordenaba por `R` bruto y sugería #60 arriba cuando el selector económico ya había elegido #209. | Top 20 explicativo agrupado por ganador, supervivientes y frontera; tabla completa de 231 preservada. El ranking narrativo no es otra autoridad decisoria. |
| **P13 — Retención mutable dentro de publicación inmutable** | `MISSING_REVIEW` se incluyó en un JSON económico fijo; luego `PRESENT` producía conflictos aun con los mismos scores. | V1 histórico intacto, v1.1 separado; estado de retención en `economic_analysis_status.json`; publicación posterior idempotente. |
| **P14 — Diferencia portable/absoluta de manifiesto** | 15.728 entradas idénticas, pero campo `durable_root` distinto bloqueó correctamente el primer cleanup. | Equivalencia JSON restringida al caso probado, conservar ambas procedencias y detenerse ante cualquier diferencia adicional. No desactivar todas las comprobaciones de hash. |
| **P15 — Ruta duplicada en `FS021_ROOT`** | La orquestación entregó al Makefile la ruta `.../FS-021/<id>` y el CLI volvió a añadir `<id>`, provocando tres `spec.json not found`. | Documentar inequívocamente `root = directorio padre` y `execution_id = carpeta hija`. Corregir la llamada, sin tocar datos ni repetir el experimento. |
| **P16 — Mock de UAT sin `activation`** | El test agregado por un parche falló en el publicador con `KeyError: activation`; el fallo era del fixture, no de la validación de seguridad. | Agregar explícitamente `activation=false` al test y mantener en producción el rechazo de salidas que no declaren la prohibición de apuestas reales. |
| **P17 — Packaging tardío, hooks y locks** | Trailing whitespace del research, línea extra al EOF, locks de publicación visibles como untracked, ruta absoluta `/home/ljarufe` y status económico ausente entorpecieron el PR. | Preflight temprano de formato/ubicaciones; `.gitignore` de locks; root configurable por `$(HOME)`; status económico visible. `git diff --cached --check` se aplica al staged final, no se usa como excusa para recalcular resultados. |
| **P18 — Disponibilidad bootstrap mal narrada** | Review P2: los futuros artefactos `FS021_BOOTSTRAP_RISK_V1` permiten `AVAILABLE`, pero el informe decía siempre `UNAVAILABLE_UPSTREAM`. | Generar prosa de los mismos campos semánticos que el JSON; tests de ambos estados; conservar literalmente el mensaje histórico si no existen matrices intraréplica. |
| **P19 — Entrega de artefactos mediante enlaces fallidos** | El cliente del maintainer no abría repetidamente enlaces `sandbox:` para parches; hubo que usar la Biblioteca para entregas descargables. | Cuando la UI falle, entregar el archivo en Biblioteca o un bloque de comandos inline verificable; no consumir rondas de Codex ni fingir que un link no funcional constituye handoff. |

Los incidentes P01–P09 pertenecen mayormente al desarrollo/ejecución original; P10–P18 aparecieron durante el análisis económico y la regularización previa al PR. Documentarlos juntos no significa que todos sigan abiertos: el único hallazgo de review compartido pendiente de acreditación al corte es **P18**. También sería erróneo afirmar que cada fallo atravesó la misma fase: hubo errores de research/DoR, de copia documental, de harness UAT, de código, de publicación y de nuestras instrucciones en chat, con mitigaciones diferentes.

## 13. Fallos de proceso más importantes, analizados por frontera

### 13.1 Entrada a Codex: verificar disponibilidad intelectual además de la física

F009 obliga a autenticar los inputs científicos realmente consumidos antes de implementación, pero aquí se comprobó la evidencia de cálculo **antes** de hacer accesibles el ticket y el research aprobados. Una ejecución puede ser matemáticamente reproducible y a la vez iniciar Codex con un contrato de producto incompleto. El check reusable debe contener tres afirmaciones sencillas: research aceptado presente en la rama; ticket legible fuera de Git; alcance/addendum correctos presentes. Si falla una, restaurar/copiar el documento y continuar desde el estado real del ticket, sin reabrir gates que no quedaron invalidados.

### 13.2 Exactitud: no declarar una autoridad más fuerte que la evidencia

El antecedente FS-020 V2R y el caso de 139 sufijos enseñan lo mismo desde lados distintos. Un hash de un artefacto físico puede estar bien mientras la semántica de un ledger truncado sea insuficiente para el consumidor; a la inversa, la apariencia de un informe correcto no prueba que los inputs existan o conserven su lineage. FS-021 exigió comparar el runner contra referencia, restaurar originales, mutation test, y autenticar el **stream entero** aun si la optimización física deja de visitar una parte del calendario. Una contradicción causal o un input no restaurable debe detener **la nueva selección** sin inventar una baseline.

### 13.3 Inmutabilidad: separar autoridad histórica, reporting y estado mutable

El costo del error inicial fue material: un campo de estado temporal dentro de un JSON económico inmutable impedía repetir operaciones sin conflicto y resultados generados habían quedado mezclados con research. La solución no consistió en hacer mutable todo: conservar las publicaciones históricas, añadir una versión corregida de reporte, mover los estados cambiantes a sus propios archivos y usar índices por ejecución. Esta frontera debe quedar explícita en F003 y en los consumidores futuros para evitar que una mejora cosmética fuerce un replay o que un cambio científico real pase como simple formato.

### 13.4 Rendimiento de interacción: review y UAT consolidadas

Durante FS-021 se prepararon paquetes de revisión completos, se ejecutó la UAT agrupada y se corrigieron defectos puntuales en chat cuando el diff era pequeño. El mayor gasto no fue un paso de investigación adicional sino fallos evitables de orquestación: links que no descargaban, comandos con raíz incorrecta, hashes narrativos frágiles y pruebas repetidas sobre fixtures incompletos. El proceso deseable sigue F009: revisión del pass → un bloque correctivo consolidado → **sólo pruebas invalidadas** → review/CI → feedback final. No elevar automáticamente un comentario de reporte Markdown a una nueva pasada de Codex o a un replay estadístico de horas.

## 14. Contrato de seguridad y límites de promoción

En todas las publicaciones relevantes se conservaron `activation.automatic_operational_routing=false` y `activation.real_betting=false`. Ni #60 ni #209 deben leerse como una apuesta automática ejecutable. La #209 es el resultado práctico elegido por el selector **para el siguiente nivel de simulación**, no una estrategia validada en vivo ni una regla que el scheduler de producción deba adoptar sin otro ticket. No hubo provider calls para fabricar datos durante el cierre, ni mutaciones de la DB operacional, migraciones operacionales o modificación de las políticas CURRENT.

Se deben mantener cuatro distinciones en los siguientes tickets: `PRACTICAL_BASELINE_SIMULATION_ONLY` original, baseline económica posterior, `scientific_evidence.disposition` y estado real de activación. El mismo índice de un candidato no representa necesariamente la misma decisión bajo metodologías diferentes; almacenar `method_version`, parámetros de la combinación, ejecución, cohorte, lags y provenance en cada selección publicada es parte de la API del laboratorio, no una exigencia cosmética.

Los resultados históricos tienen riesgos concretos: odds T−30 reconstruidas, selección y método económico desarrollados con conocimiento del mismo universo, H2 negativa para #209, ganancias concentradas en cinco oportunidades y bootstrap confirmatorio sólo para T+150. Se necesita evaluación temporal independiente/prospectiva, controles de liquidez/exposición y comparación de costo de oportunidad antes de cualquier propuesta de uso operacional. Conservar `UNSTABLE` no bloquea seguir investigando en simulación, pero sí prohíbe presentar el resultado como superioridad científica demostrada.

## 15. Recomendaciones de actualización individual a fuentes permanentes

Estas son **recomendaciones de proyección después del cierre**, no una reescritura masiva automática de F000–F010 ni un requisito para aceptar el PR. F008 ya había autorizado el delta específico del ticket; las fuentes sólo deberían incorporar reglas que sobrevivan a FS-021 como convención reusable.

| Fuente | Recomendación dirigida | No cambiar |
|---|---|---|
| **F001 — Producto** | Registrar que Finsport dispone de baseline integrada simulada #209 y de un selector económico reutilizable, con incertidumbre prospectiva explícita; mantener separadas las autoridades históricas #60 y la disposición `UNSTABLE`. | No activar apuestas reales ni prometer superioridad económica. |
| **F002 — Dominio/seguridad** | Reforzar distinción entre baseline de simulación, diagnóstico y activación, flags `HIGH_RISK`, hard-risk/depletion y no autorización de apuestas. | No confundir `PENDING_CAPACITY` con insolvencia ni modificar las reglas CURRENT sin ticket. |
| **F003 — Arquitectura** | Describir productor del experimento original, consumidor económico post-COMPLETE, estados de error separados, publicación v1/v1.1, índices `docs/experiments/` y restauración desde evidencia externa. | No convertir paths `/home/ljarufe` ni SHA de formato de código en interfaz universal. |
| **F004 — Operación** | Documentar ejecución larga local con supervisor, pausa térmica cooperativa, checkpoints completos, ACK, root/ID correctamente diferenciados y deploy normal post-merge. | No autorizar cambios automáticos en el stack operacional por existir una baseline. |
| **F006 — Roadmap** | Marcar FS-021 como implementado sólo cuando PR/merge/deploy/aceptación se cierren; registrar el siguiente trabajo prospectivo, shadow y frontend de FS-022 sin volver a ejecutar el torneo retrospectivo. | No marcar FS-022 como entregado por disponer de artefactos FS-021. |
| **F008 — Definición** | Para tickets científicos consumidores, exigir fuente de selección versionada, contrato de retención/binding y aclaración explícita de si el resultado es original, económico o operacional. | No imponer uniformemente una metodología de selector a un estudio cuyo research aún no la haya fijado. |
| **F009 — Ejecución** | Añadir check binario pre-Codex para research aprobado + ticket extrarrepositorio accesibles; distinguir hashes científicos de documento editable; ejecutar packaging/pre-commit temprano; conservar batch de review/UAT; evitar raíz/ID duplicados. | No introducir un ritual de checksum de cada F00x ni pasos de confirmación después de cada comando verde. |
| **F010 — Investigación** | Conservar como caso de estudio la diferencia entre elección práctica original, disposición científica inestable y una regla económica posterior post hoc. Exigir provenance y datos nuevos para validar cambios de método. | No convertir el experimento reutilizado en validación prospectiva. |
| **F000 — Catálogo** | Actualizar referencias de las fuentes modificadas **una a una**, después de su aprobación. | No crear una consolidación global de versiones sólo por este cierre. |

## 16. Handoff operativo y de datos para el siguiente ticket

### 16.1 Autoridades que debe recibir el consumidor

- `GLOBAL_STRATEGY_V1` original: **#60**, método `FS021_INTEGRATED_MAXIMIN_LAG_5U_V1`; científico `UNSTABLE`; cross-lag inference `NOT_EVALUATED_BY_FS021_V1`.
- `FS021_SINGLE_ECONOMIC_SELECTOR_V1`: **#209**, Prediction `MARKET_CONSENSUS/fs013-market-consensus-v2`, Decision `SELECTIVE_CONFIDENCE(threshold=0.45)`, Capital `FRACTIONAL_KELLY(lambda=0.25,max_lanes=10)`; modo `PRACTICAL_BASELINE_SIMULATION_ONLY`; activación operacional falsa.
- Ejecución nativa `fcd8ce16950e02589d25ddf6bcd9953cce2e663f2f14c63e7f8a1f4487d97372`, con población común de 1.877 y manifests originales autenticables.
- Locators Git `original_v1.json`, `economic_v1_1.json`, `diagnostics_v1_1.json` bajo `docs/experiments/FS-021/<execution_id>/`, con `FS021_ROOT` configurable que apunta al **padre** de la ejecución.
- Research metodológico y de selector bajo `docs/research/`, maintainer-owned y **no** fuente de bytes para un replay. Ticket aprobado bajo `~/Documents/finsport/FS-021/`.

Identidades de los seis archivos más importantes **de la evidencia original congelada**, útiles para restauración y consumidor; no son checksums de documentación:

| Archivo durable relativo a la ejecución | SHA-256 del artefacto histórico |
|---|---|
| `spec.json` | `1d0fc56634ac964353ade60f858be654c22736e33dd1edc770ee890d6bf4ec4e` |
| `run.json` | `4bdeeca6f3ed9132c182dafc25708e3182593b4c55425aee2795ffa3f94f0226` |
| `observed.json` | `95326c9f54c0f4075f1c681796931767dac60d59cbc440b93210f5901c205214` |
| `scores-150-1.npy` | `18d319e644b4e0cda23a3d02df0a762f4226b663ff4a6308ea9d0b51b0196528` |
| `scores-150-2.npy` | `e7af8cf61ff89304f631a50bde4a94e87e0c0ae276c95002843ed43ffe76cc51` |
| `scores-150-4.npy` | `c5d77893730033e262f4ca825eb8d848052d1d9587fc66621168105d23d9d372` |

El runtime muestra además hashes de **binding semántico** de cohort/calendar/runner/spec/stream, que no tienen por qué coincidir con el SHA físico de un archivo JSON o con el SHA del contenido de una copia portátil. Al restaurar, consultar el manifiesto que declara **qué clase de identidad** representa cada campo y no comparar magnitudes de distinta semántica.

### 16.2 Lo que sí queda fuera de FS-021

El siguiente programa puede consumir la baseline #209 en modo simulado, medir prospectivo/shadow con una cohorte nueva, examinar la concentración y el H2 negativo, comparar costo de oportunidad sobre la misma moneda/horizonte y valorar frontend de resultados/aciertos/rendimiento de técnicas. No está autorizado a reinterpretar los tres lags como tres diseños bootstrap; introducir métricas intraréplica de las réplicas históricas sin nuevo replay autorizado; borrar la evidencia de las 231 alternativas; ni transferir la selección simulada a CURRENT por mera disponibilidad técnica.

Si se necesita enriquecer el bootstrap histórico con drawdown/depletion verdaderos, se requiere **autorización y presupuesto separados**: estimación previa con una shard acotada, una sola pasada de los 3.465.000 paths si se aprueba, igualdad exacta de los scores terminales frente a los ya publicados y persistencia de nuevas matrices bajo schema versionado. No es parte de la aceptación de la baseline económica v1.

## 17. Evidencias consultadas y grado de certeza de este feedback

El documento consolida las siguientes fuentes locales y reportes del maintainer, cada una con su alcance. No reemplaza la documentación de resultados íntegros retenida fuera de Git:

| Fuente | Uso en el feedback |
|---|---|
| `FS-021_ticket_approved.md` y `FS-021_approved_scope_addendum.md` | Scope original, 231 brazos, 5u, inferencia T+150, límites y autoridad F008. |
| `FS-021_integrated_strategy_methodology_research.md` | Investigación pre-ticket y precisiones de Event-Time, selección original y evidencia. |
| `FS-021_02_pass1_report.md`, `FS-021_05_manual_review_findings.md`, patches/correcciones | Gates originales, defectos de supervisor/runner y fallos de proceso tempranos. Los números Pass 1 son históricos. |
| Ejecución auditada `FS-021_10_review_bundle.zip` y `FS-021_12_economic_selector_evidence_audit.zip` | `run.json`, `observed.json`, score manifests, estabilidad, supervisor y métricas térmicas; la copia portátil no sustituye al host. |
| `FS-021_13_estado_auditoria_para_research.md`, `FS-021_20_preflight_for_codex.zip` | Frontera entre auditoría portátil y host auténtico, 139 sufijos, ocho inputs y estado inicial de retención. |
| `FS-021_investigacion_selector_unico_v1_PROPUESTA.md` y `FS-021_adenda_selector_unico_v1_PROPUESTA.md` | Razonamiento post hoc, fórmula versionada, diagnóstico y regresión numérica esperada. Su nombre inicial `PROPUESTA` no constituye por sí mismo aprobación: la implementación/UAT fue autorizada y ejecutada en el flujo del maintainer. |
| `FS-021_23_review_bundle.zip`, `FS-021_24_rutas_reporte_idempotencia.patch`, `FS-021_27_prepr_review.zip` | Código y trazas compartidas para revisión de publicación, top20, idempotencia y organización. |
| Salidas locales aportadas en el chat de UAT y PR #27 | 905 pruebas, 80,62 %, `status=COMPLETE`, winner #209, índice de retención presente, cleanup de 17 copias, repetición idempotente y comentario P2 de review. La última confirmación de CI después del P2 **no** forma parte de esas salidas. |
| F008 v1.8, F009 v1.14 y F010 v1.5 | Reglas de definición, ejecución, feedback y distinción entre research, producto e inferencia. |

No se ha interpretado una copia de ZIP como evidencia de que el host conserva todos los bytes, una salida intermedia de tests como cierre del diff posterior, ni una corrección propuesta de chat como commit subido. Esas distinciones importan precisamente porque FS-021 acumula múltiples fases y versiones de reporting.

## 18. Estado de aceptación y obligaciones restantes

| Gate | Estado al corte | Prueba o condición |
|---|---|---|
| Ticket original y alcance del experimento | **Cerrado en ejecución local** | 33 × 7, cohorte 1.877, regla 5u, lags/slices/boostrap completos; `run.status=COMPLETE`. |
| Integridad y conformidad | **PASS reportado y evidenciado** | Gates `INPUT_AND_ARTIFACT_INTEGRITY`, `SEMANTIC_CONFORMANCE` y `RUNNER_EQUIVALENCE`; mutaciones y lectura autenticada. |
| Selección histórica original | **Publicada** | #60; `UNSTABLE`, sin activación. |
| Adenda de Economic Selector | **Implementada/UAT local** | #209, 20 Tier 1, 9 frontera, 3 supervivientes; 693 métricas, 139 sufijos verificados. |
| Publicación durable y eliminación de duplicados | **PASS local** | Índices compactos, 17 copias borradas tras hash/semántica; research reducido a tres Markdown. |
| Idempotencia `analyze/publish` | **PASS local comunicado** | Repetición con ruta raíz correcta y verificación de hashes antes/después sin replay. |
| `make check` antes del comentario P2 | **905 PASS; 80,62 %** | Última salida completa entregada por el maintainer. |
| Corrección P2 — informe de matrices bootstrap futuras | **Pendiente de acreditación** | Aplicar/confirmar el delta, focused test `AVAILABLE` y `UNAVAILABLE_UPSTREAM`, commit/push y CI de ese commit. |
| Review/CI PR #27 | **Pendiente de confirmación posterior al P2** | Resolver el único comentario y verificar CI del SHA final de código. |
| Feedback final en `docs/process/` | **Preparado, pendiente de incorporación al último commit pre-merge** | Ver sección 19. |
| Merge y deploy | **No ejecutados al corte** | Acciones manuales del maintainer y ciclo obligatorio F009. |
| Aceptación post-deploy y Planka Done | **Posteriores al merge** | Verificar estado operacional limitado, preservar `real_betting=false`, handoff y cierre. |

## 19. Checkpoint de incorporación final y lifecycle posterior

**Antes del último commit pre-merge**, el maintainer debe marcar los hechos ya observados; no requiere otro estudio, sólo validar la corrección acotada del comentario y el estado real del PR:

- [ ] Corrección P2 del informe bootstrap realmente presente en la rama y test de ambos estados PASS.
- [ ] CI verde y comentario de review de PR #27 resuelto sobre el commit correctivo definitivo.
- [ ] Confirmado que no existe otro cambio funcional pendiente que vuelva obsoleto este feedback.
- [ ] Incorporado `docs/process/FS-021_feedback.md` en el **último commit documental pre-merge**, con cualquier ajuste factual imprescindible de las casillas anteriores; push manual del maintainer.

Tras aceptar el PR, el maintainer realiza el merge manual y el orden operacional ya congelado en F009:

```bash
cd ~/Projects/finsport
make dev-destroy
git switch master
git pull --ff-only origin master
make deploy-local
```

Sólo **después** del deploy se verifican health, migraciones esperadas, configuración efectiva, propiedad de scheduler/worker y la superficie experimental publicada, con la comprobación explícita de que no se ha encendido ningún flujo de apuestas reales. No se reejecutan el bootstrap ni la suite completa simplemente por hacer merge si el código y las condiciones no han cambiado. Una vez documentada la verificación operacional, se entrega el handoff al chat principal, se evalúan las actualizaciones individuales de F000–F010 y se mueve Planka a Done.

**Conclusión de cierre:** FS-021 transformó las baselines aisladas de Prediction, Decision y Capital en un estudio integrado completo, conservó un resultado científico negativo/inestable sin maquillar sus límites y añadió una autoridad económica única y reutilizable para la siguiente fase de simulación. Las mejoras más importantes del proceso fueron hacer ejecutable y verificable la regla de 5u, completar el torneo sin pruning, distinguir selección práctica de evidencia científica, separar el estado mutable de las publicaciones inmutables y dejar `research`, datos durables e índices Git con propietarios distintos. La aceptación formal del incremento termina con PR/CI, merge, deploy y verificación operacional, no con el último JSON `COMPLETE`.
