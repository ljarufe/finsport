# FS-021 — Investigación económica complementaria: selector único robusto (propuesta v1)

**Finsport · 25 de septiembre de 2026 · F010 v1.5 · RESEARCH COMPLETE FOR PRODUCT REVIEW / HOST-BINDING PENDING · no aprobado.**

**Decisión que debe resolver:** publicar una única identidad completa Prediction × Decision × Capital desde la evidencia congelada de FS-021, sin una segunda decisión externa entre M1–M4. Si al menos un candidato obtuvo un retorno estrictamente positivo en su peor lag, publicar una composición simulada, aunque su perfil de riesgo sea elevado y se advierta. `DIAGNOSTIC_ONLY__NO_NEW_STAKES` **únicamente** si **todos** los retornos mínimos son estrictamente negativos. Si el mayor retorno mínimo es exactamente cero, distinguir `BREAKEVEN_SIMULATION_ONLY`. Errores de integridad constituyen un estado técnico separado, nunca un diagnóstico económico. Ninguno de estos resultados habilita apuestas reales o altera CURRENT.

Este documento formaliza un **único** selector propuesto: `FS021_SINGLE_ECONOMIC_SELECTOR_V1`. “M4” es un sobrenombre del chat y no crea una familia de selectores operacionales. La variante exacta aquí definida es **una construcción metodológica de Finsport**, fundamentada en conceptos publicados; ningún artículo externo propone exactamente esta combinación de tiers, frontera y jackknife de medianas.

## R0–R2. Pregunta, contrato y jerarquía

- **Población:** 231 composiciones de 33 Prediction×Decision elegibles × siete Capital CURRENT, cohorte fija de 1.877 partidos en diez ligas, 36 semanas Lima incluidas semanas sin encuentros. Banca 100u independiente por composición, compartida por sus lanes. Retornos reglamentarios 1X2 y precios históricamente reconstruidos, nunca liquidez ejecutada.
- **Resultado histórico independiente:** #60 `DIXON_COLES × VALUE(0.05) × LEGACY_CAPPED`, mediante `FS021_INTEGRATED_MAXIMIN_LAG_5U_V1`, `PRACTICAL_BASELINE_SIMULATION_ONLY`; inferencia científica `UNSTABLE`. No reescribir ni los resultados originales ni los bytes de `run.json`.
- **Evidencia:** archivo `FS-021_12_economic_selector_evidence_audit(1).zip`, `FS-021_13_estado_auditoria_para_research.md`, ticket `FS-021.md`, investigación pre-ticket v2, fuentes F001/F002/F003/F008/F009/F010 ACTIVE, `requirements.txt` y `pyproject.toml` del `master` accesible vía GitHub (contrastar con branch FS-021 real antes de Codex).
- **Pregunta primaria:** cuál composición ofrece máximo crecimiento observado *dentro de un intervalo de riesgo comparativamente estable*, sin expulsar automáticamente a todas las que produzcan retorno positivo en escenarios de riesgo elevado.
- **Secundarias:** qué puede calcularse con 693 ledgers; qué requiere bootstrap instrumentado; qué familias demuestran pérdidas sistemáticas *en este histórico*; qué dependencias exige el nuevo módulo reutilizable; cómo impedir que la investigación pos-hoc se presente como verificación independiente.
- **Exclusiones:** llamadas a proveedores deportivos, apuestas reales, cambios operacional/DB, selección por red neuronal, reentrenamiento Prediction, retuning de parámetros congelados, bootstrap inferencial cross-lag no realizado, mezcla de sub-bancas por lane.

## R3A. Integridad del paquete y disponibilidad física

La comprobación independiente de los **1.456 miembros declarados** por su manifest de exportación dio **1.456/1.456 SHA-256 y longitudes correctos**. El ZIP contiene 1.461 entradas físicas; la diferencia corresponde al alcance de su índice de ficheros y no convierte automáticamente los miembros sin entrada de manifest en autoridades verificadas. La auditoría facilitada reporta además **712/712 manifiestos internos correctos**, 12/12 slices, 231 identidades × tres lag y tres matrices `(5000,231)` T+150. Se leyeron y derivaron offline **693/693 ledgers**: en cada uno, `100u + suma de P&L de SETTLEMENT` iguala la banca final y el drawdown máximo calculado desde los eventos de equity coincide con el publicado; **cero discrepancias** a la precisión contrastada. No se ha comprobado su equivalencia contra los streams originales aún ausentes para los 139 hashes lógicos que dependen de sufijos de depletion.

| Evidencia o indicador | Disponible hoy | Límite pendiente |
|---|---|---|
| Retorno/MDD/duración, 3×231 observados | Sí, `observed.json` y 693 ledgers | No reemplaza backtest prospectivo. |
| Serie de equity/reservas/cash/P&L observada | Sí, recuperable de cada ledger | Para atribución por liga y cuota: recuperar ocho ficheros `inputs/` y verificar sus hashes/permiso. |
| CDaR 95% diario, underwater y exposición media observados | Derivados offline para 693 | Son convenciones *nuevas* definidas aquí, no métricas congeladas de FS-021. |
| Tres distribuciones emparejadas bootstrap 5.000×231 | Sí, T+150, bloques 1/2/4 semanas | Sólo retornos **terminales**, no equity intra-réplica, MDD bootstrap o evento real de depletion. |
| 12 slices: H1/H2 y leave-one-league-out | Sí | Comparten el histórico, no constituyen validación prospectiva. |
| 693 ledgers vs sus streams originales / `RETENTION_INDEX.tsv` | Parcial | Ocho inputs y registro de retención faltantes del ZIP: verificar físicamente en el host antes de publicar autoridad. |
| Slippage, stake admisible bookmaker, liquidez real | No | Precios efectivamente obtenibles y restricciones de ejecución futuras; nunca deducirlos de cuotas reconstruidas. |

**Nueva vista observada:** muestrear equity al cierre de cada día Lima durante 252 días, conservando las seis semanas de calendario vacío declaradas por el spec y valor terminal constante después de depletion; calcular curva de drawdown (`1 - equity / peak`), **CDaR95 diario** como promedio del 5% mayor de las 252 observaciones de underwater (13 días, `ceil(0.05×252)`); exposición reservada media como integral temporal de `reserved` sobre los 252 días dividida entre los segundos del horizonte; concentración como suma de los cinco mayores P&L positivos por oportunidad dividida entre el P&L positivo bruto del mismo path. No confundir este último índice *ex post* con un replay contrafactual en el que se eliminan cinco apuestas: las stakes siguientes cambiarían.

`observed_693_enriched_derived.csv` contiene estas 693 observaciones. CDaR, utilización temporal, frecuencia de semanas positivas y concentración son **diagnósticos del selector v1**: no cambian arbitrariamente la regla primaria después de inspeccionarse. Para futuros estudios es recomendable emitirlas automáticamente durante el runner.

## R3B. Literatura externa y transferencia controlada

1. **Portafolios y frontera:** la frontera eficiente/optimización multiobjetivo descarta alternativas dominadas. Aquí no suponemos diversificación por mezcla continua de carteras: las 231 rutas son discretas, stateful, correlacionadas por el mismo calendario y precios.
2. **Expected Shortfall/CVaR:** Rockafellar y Uryasev desarrollan la optimización de pérdidas de cola. En Finsport utilizamos la media exacta de los **250** peores retornos de cada distribución de 5.000, por candidato y bloque. El riesgo de esta métrica es *terminal de T+150*, no drawdown bootstrap ni probabilidad de ruina prospectiva. Referencia: Rockafellar & Uryasev (2000), *Optimization of Conditional Value-at-Risk*, Journal of Risk, DOI `10.21314/JOR.2000.038`.
3. **Kelly sujeto a riesgo:** Busseti, Ryu y Boyd (2016) formalizan crecimiento logarítmico restringido por una probabilidad de drawdown bajo un modelo probabilístico especificado. Aplicación limitada: inspira crecimiento sujeto a riesgo, **sin trasladar sus garantías matemáticas** a probabilidades o cuotas reconstruidas de Finsport. https://web.stanford.edu/~boyd/papers/kelly.html
4. **Riesgo de trayectoria:** Chekhlov, Uryasev y Zabarankin (2005), *Drawdown Measure in Portfolio Optimization*, definen Conditional Drawdown, función de la curva underwater. Nuestra aplicación diaria especifica su malla temporal; no afirmar que una serie diaria es equivalente a CDaR de todos los ticks. https://doi.org/10.1142/S0219024905002767
5. **Estadística robusta:** las medianas y la desviación absoluta mediana (MAD) resisten mejor los extremos que la media y la desviación estándar. Se aplica a un **grupo económicamente relevante** (frontera) para impedir que políticas con quiebras casi totales inflen un umbral de riesgo, sin borrar sus observaciones ni P&L. La operación adicional *leave-one-out* es una prueba de sensibilidad a la composición del grupo, **no** una estimación no sesgada del riesgo futuro. Véase https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.median_abs_deviation.html y Rousseeuw (1984), DOI `10.1080/01621459.1984.10477105`.
6. **Sesgo de selección:** White (2000), *A Reality Check for Data Snooping*, DOI `10.1111/1468-0262.00152`; Hansen (2005), *A Test for Superior Predictive Ability*, DOI `10.1198/073500105000000063`. Redefinir después de ver las 231 rutas **no** es nueva confirmación. Conservar `UNSTABLE`; FS-022 debe fijar regla y luego capturar nuevos partidos prospectivos.

Una red neuronal/HDBSCAN/MCD no decide cuál es el coste de una caída tolerable. Con 231 composiciones correlacionadas (no 231 muestras independientes) añade decisiones de parametrización sin resolver el mandato económico. MCD o clustering pueden servir como **análisis exploratorio de grupos**, sin podar candidatos ni determinar la baseline. La frontera exacta, medianas y jackknife requieren solamente NumPy + biblioteca estándar.

## R3C. Hallazgos numéricos en las 231 composiciones

- **231** rutas; **161** pasan los gates originales de FS-021; **29** obtienen retorno estrictamente positivo en *todos* los lags y **202** no lo consiguen; **168** pierden dinero en los tres tiempos. Hay diez rutas con un retorno mayor al 100% en un escenario y un retorno mínimo negativo (regla exploratoria de detección de picos), tres de ellas (#3, #73 y #115) alcanzaron incluso más del 300% en un escenario por políticas recovery.
- **No confundir dimensión:** para cada candidato, tres lags observados son sensibilidades de *una misma muestra*, y las 15.000 réplicas bootstrap T+150 son secuencias simuladas del *mismo histórico*. Las diferencias originales no prueban margen comercial ni causalidad por política.
- El 7% efectivo anual hipotético equivale a aproximadamente **4,7955%** para 36/52 años, es decir 104,80u aritméticas sobre 100u. Se emplea como preferencia de primer nivel cuando existen candidatos que lo superan; **no** convierte en diagnóstico a una única estrategia positiva que rinda menos de ese benchmark. No convertir u a soles ni equiparar apuestas con depósitos.

### Familias completas: resultados históricos, no juicio universal

| Dimensión / familia | Rutas | Peor lag positivo | Negativo en los tres lags | Lectura |
|---|---:|---:|---:|---|
| Capital `FIXED_FRACTION_BANKROLL(0.05)` | 33 | **0** | **33** | Todo pierde en 3 lags; mejor escenario aislado también negativo. |
| Capital `FIXED_TARGET_PROFIT_NO_RECOVERY` | 33 | **0** | **33** | Todo pierde en 3 lags; mejor escenario aislado también negativo. |
| Capital `FLAT_UNIT` | 33 | 4 | 28 | Mantener controles, no borrar. |
| Capital `FRACTIONAL_KELLY(0.25)` | 33 | 7 | 26 | Varias rutas positivas, incluida región de menor riesgo observada. |
| Capital `LEGACY_CAPPED` | 33 | 7 | 20 | Retornos altos en algunos caminos, riesgo de cola variable. |
| Capital `LEGACY_PARTIAL` | 33 | 8 | 9 | Muchos escenarios aislados positivos pero no todos robustos cross-lag. |
| Capital `LEGACY_RECOVERY` | 33 | 3 | 19 | Hay picos de ganancias enormes y colas próximas a quiebra. |
| Prediction `INDEPENDENT_POISSON` | 63 | **1** | 48 | Sólo una ruta tiene peor retorno positivo, **4,031%**, inferior al benchmark hipotético; **no** toda la familia es negativa. |
| Prediction `DIXON_COLES` | 63 | 8 | 45 | No retirar como clase, aunque #60 presenta grandes drawdowns. |
| Prediction `ELO_MULTINOMIAL_LOGIT` | 63 | 9 | 49 | Incluye #173, cola bootstrap positiva, pero DD cross-lag elevado. |
| Prediction `MARKET_CONSENSUS` | 42 | 11 | 26 | Incluye #195/#202/#209/#216; combinaciones VALUE siguen inelegibles por circularidad. |

**Propuesta de poda future-only:** marcar ambas configuraciones de Capital universalmente negativas en este histórico como `HISTORICALLY_ALL_33_LOSS_MAKING__FUTURE_TOURNAMENT_REVIEW`. Tras la aprobación de producto, se pueden excluir como candidatas *por defecto* de un futuro torneo económico homogéneo y conservar una ruta de control si la metodología futura lo exige. **No borrar las clases Python, registros, tests, streams, hashes o resultados FS-021**. La evidencia actual no demuestra que otros parámetros de esas políticas sean incapaces de producir ganancias ni que deban desaparecer de la plataforma operacional. `INDEPENDENT_POISSON` es candidato a revisión/prioridad inferior, no a eliminación total.

### Alternativas examinadas

| # | Composition | Peor retorno | Peor MDD | Peor CVaR 5% T+150 (1/2/4w) | CDaR95 observado máximo diario | Slices positivos |
|---:|---|---:|---:|---:|---:|---:|
| 60 | Dixon / VALUE .05 / Legacy Capped | 124,26% | 78,51% | −98,68% | 54,58% | 9/12 |
| 31 | Dixon / Confidence .55 / Legacy Recovery | 119,38% | 39,01% | −99,52% | 39,01% | 10/12 |
| 157 | Elo / Confidence .55 / Legacy Recovery | 118,30% | 58,14% | −97,32% | 39,97% | 9/12 |
| 202 | Market / Confidence .40 / Fractional Kelly .25 | 84,87% | 21,54% | −33,91% | 21,15% | 11/12 |
| 195 | Market / Modal / Fractional Kelly .25 | 80,54% | 21,32% | −34,10% | 20,70% | 11/12 |
| 209 | Market / Confidence .45 / Fractional Kelly .25 | 66,67% | 12,23% | −17,60% | 11,82% | 11/12 |
| 216 | Market / Confidence .50 / Fractional Kelly .25 | 65,59% | 8,48% | −17,08% | 8,42% | 11/12 |
| 223 | Market / Confidence .55 / Fractional Kelly .25 | 45,17% | 7,46% | −17,17% | 6,94% | 11/12 |
| 173 | Elo / VALUE .00 / Legacy Partial | 53,53% | 48,01% | **+12,24%** | 26,31% | **12/12** |
| 61 | Dixon / VALUE .05 / Legacy Partial | **−2,06%** | 78,26% | −98,70% | 44,26% | 7/12 |
| 73 | Poisson / Confidence .40 / Legacy Recovery | **−91,82%** | 96,99% | −99,57% | 96,95% | 3/12 |
| 115 | Poisson / VALUE .02 / Legacy Recovery | **−96,88%** | 98,65% | −99,78% | 98,65% | 6/12 |

**#115:** T+150 cierra en **622,303u** después de una ganancia extraordinaria, pero T+120 y T+130 terminan aproximadamente en **3,117u**, de ahí el peor retorno de −96,88%; además hay agotamiento práctico. **#73:** T+130 termina en 481,730u, pero T+150 en 8,184u. No seleccionar por un único lag favorable. **#31** produce retornos altos pero una cola bootstrap casi total y alta exposición pico; **#60** combina mayor peor retorno y caídas del 78,51%. Una simulación que maximiza sólo la ganancia del episodio observado puede ser muy vulnerable a cambiar el orden de los partidos.

**Riesgo de concentración:** la suma de las cinco mayores ganancias de oportunidad representa, en el lag más concentrado de cada composición, aproximadamente **63% del P&L positivo bruto de #202**, **73% de #209** y **83% de #216**. Las frecuencias de apuesta son distintas; estas cifras alertan del peso de pocos aciertos y deben presentarse **junto con** retorno y MDD. No equivalen a atribución causal ni autorizan eliminar esas ganancias de los ledgers.

## R4. Contrato exacto del único selector propuesto

### Convenciones primarias

Para cada brazo `i`:

- `R_i = min_lag((equity_final_lag − 100)/100)` con Decimal original exacto, tres lags.
- `D_i = max_lag(MDD_lag)` con Decimal original exacto.
- `L_i = −min_{w∈{1,2,4}} mean(250 menores retornos bootstrap_{w,i})`. Por ejemplo `CVaR=−0,17596` implica pérdida de cola 17,596%; un CVaR positivo genera `L<0` y **no** se recorta a cero.
- `boot_median_positive`: mediana del retorno final >0 en **cada** tamaño de bloque. Este es un gate práctico exploratorio, no significancia estadística ni inferencia cross-lag.
- `clean`: ninguna ruina, `ever_nonpositive_equity`, terminación explícita ni `OPERATIONAL_DEPLETION` observada en los tres lags; `activity`: 38 apuestas/3 ligas/4 semanas por lag. Si todos los candidatos positivos incumplen alguno, **se relajan por tiers** en vez de devolver `DIAGNOSTIC_ONLY`.

**Paso 0 — Autenticidad/semántica:** 231 identidades canónicas, 693 paths, RNG y matrices `(5000,231)`, manifiestos físicos y consumidor/bindings upstream. Antes de promoción real, verificar en host ocho `inputs/`, `RETENTION_INDEX.tsv`, 139 hashes lógicos con sufijos, versión del runner V2R y status de revisión. Mismatch crítico → `TECHNICAL_STOP_RESTORE_REQUIRED`; no ranking ficticio.

**Paso 1 — Garantía de una salida económica cuando hay crecimiento:** si `max_i R_i > 0`, **descartar del conjunto práctico** todas las rutas con `R_i<=0`; conservarlas en el CSV completo. Separar los supervivientes mediante tiers *fijos* para que el benchmark, el bootstrap débil o una señal de riesgo no impidan una selección positiva:

- **Tier 1:** `R_i>4,7955%`, `clean`, `activity`, tres medianas bootstrap positivas.
- **Tier 2:** `R_i>0`, `clean`, `activity`, tres medianas bootstrap positivas.
- **Tier 3:** `R_i>0`, `clean`, `activity`.
- **Tier 4:** `R_i>0`, `clean`.
- **Tier 5:** restantes con `R_i>0`, aun si su riesgo es elevado. Debe informar exactamente los motivos y etiquetar `HIGH_RISK` cuando proceda, sin habilitar operación.

Elegir el primer tier **no vacío**. La precedencia de tiers es preferencia de confiabilidad operativa y actividad; no presupone superioridad científica.

**Paso 2 — Frontera tridimensional:** mantener sólo puntos **no dominados** en `(max R, min D, min L)`. `A` domina a `B` si A no es peor en las tres dimensiones y es estrictamente mejor en al menos una. No interpolar carteras ni suponer diversificación entre estrategias; no descartar físicamente ninguna trayectoria. Una frontera de un elemento produce ese elemento.

**Paso 3 — Referencias robustas SIN 25/50% ad hoc:** para cada riesgo `r∈{D,L}` y cada miembro `j` de la frontera `F`, calcular la **mediana** de `r` sobre `F\{j}`; definir umbral `T_r=min_j median(r(F\{j}))` (**mediana leave-one-out más exigente**). La perturbación es quitar una composición, no quitar una semana: esto evita que una única estrategia de riesgo elevado aumente el límite relativo con facilidad, sin asegurar estabilidad estadística temporal. Para `|F|=1` usar el valor del único elemento. Una composición supera el presupuesto relativo si `D_i <= T_D+1e-12` **y** `L_i <= T_L+1e-12`; no sumar riesgos heterogéneos en una media de porcentajes.

**Paso 4 — Ganador único:** entre los miembros de la frontera que pasan ambos límites, **maximizar `R`**; desempatar en orden por **menor L**, **menor D**, **más apuestas mínimas** en los tres lags y **menor índice integrado canónico**. CDaR, exposición media, concentración top-5, 12 slices y H1/H2 se publican como diagnóstico y alertas de fragilidad; **no** se introducen pesos ex post tras observar qué composición encabeza cada indicador.

**Paso 5 — Fallback positivo sin intervención humana:** si ningún miembro de la frontera pasa ambas referencias, elegir el que minimice el **máximo exceso de riesgo normalizado** `max(0,(D−T_D)/scale_D,(L−T_L)/scale_L)`; `scale_r=max(IQR_r, MAD_r, 1e−12)` sobre F; desempatar por mayor R, menor L, menor D, más actividad e índice canónico. Publicar `PRACTICAL_BASELINE_SIMULATION_ONLY_HIGH_RISK` y las violaciones precisas. Este fallback sigue escogiendo un positivo, aun cuando todos los riesgos sean grandes.

**Paso 6 — Sin positivos:** `DIAGNOSTIC_ONLY__NO_NEW_STAKES` **sólo si `R_i<0` para todos**; identificar por mayor R (luego menor L, D, índice) una ruta de diagnóstico. Si hay algún `R_i==0` y ninguno positivo: `BREAKEVEN_SIMULATION_ONLY` con menor L, D, índice entre los de cero. El caso de empate exacto queda congelado. No confundir cero con retorno económico positivo ni con integridad fallida.

**Advertencia de alto riesgo (no es un veto):** etiquetar `PRACTICAL_BASELINE_SIMULATION_ONLY_HIGH_RISK` cuando el ganador utilice fallback fuera de los límites robustos, registre algún hard-risk observado o actividad insuficiente, tenga drawdown máximo observado de al menos 50% o una pérdida CVaR peor-bloque de al menos 95%. Estos dos umbrales ilustran una alerta de seguridad fácilmente legible, **no** intervienen en la clasificación ni excluyen candidatos positivos. Publicar los motivos individualmente (`risk_warnings`). Si la única composición positiva cumple los tiers pero tiene DD99%, seguirá siendo seleccionada para SIMULACIÓN con alerta, nunca diagnóstica por su riesgo.

**Salida machine mínima:** `method_version`, `input execution/spec/manifest hashes`, `winner integrated_index`, tres identidades y parámetros/versiones inmutables, tier, R/D/L, umbrales LOO, miembros de F, conjunto que supera ambos, fallback si aplica, P&L, actividad, CDaR/underwater, reserva media y pico, concentración, H1/H2, 12 slices, matrices 1/2/4, motivos de descarte por candidato, advertencia de selección pos-hoc, scientific disposition congelada y `activation=false`. Publicar los 231 diagnósticos, no sólo top 20.

### Resultado observado de prueba (NO baseline aprobada)

En el paquete actual **Tier 1 contiene 20 candidatos**, cuya frontera `(R,D,L)` tiene nueve: **#31, #60, #157, #173, #195, #202, #209, #216, #223**. Sus medianas *sin perturbación* son `D=21,5397%` y `L=33,9088%`: con ellas entrarían #202/#209/#216/#223 y ganaría por R la #202. Con el mínimo de las nueve medianas leave-one-out, `T_D=21,4276%` y `T_L=25,7525%`, pasan sólo **#209, #216, #223**. La mayor rentabilidad mínima entre estas es **#209**: `MARKET_CONSENSUS × SELECTIVE_CONFIDENCE(0.45) × FRACTIONAL_KELLY(0.25, max_lanes=10)`, `R=66,6712%`, `D=12,2285%`, `L=17,5961%`. Sus bancas finales observadas oscilan entre aproximadamente 166,67u, con poca sensibilidad al lag. **Esta diferencia frente a #202 procede de la definición de estabilidad del presupuesto**, no demuestra que #209 sea universalmente más rentable ni seguro.

#202 posee mayor crecimiento puntual (`R=84,8714%`), pero `L=33,9088%` excede el límite robusto de 25,7525%, y `D=21,5397%` excede por ≈0,112 puntos porcentuales el límite robusto de 21,4276%. #195 pasa el límite DD pero no el límite de cola. #216 cede 1,08 puntos porcentuales de retorno a #209 a cambio de menores DD y cola: la regla aprobable da prioridad al mayor crecimiento **una vez dentro del rango robusto**, no a minimizar DD indefinidamente.

Este método es **una propuesta pos-hoc**: la identidad #209 debe reproducirse físicamente por Codex con los inputs/runner autenticados y la adenda aprobada; no divulgarla como confirmación prospectiva. La disposición `UNSTABLE` no cambia.

## R4. Riesgos no resueltos y falsaciones

- **Fragilidad de la referencia:** eliminar un miembro de la frontera original cambia la mediana completa y puede alternar entre #202 y #209. El mínimo leave-one-out reduce esa sensibilidad al coste de escoger un conjunto más conservador; no es una constante financiera universal. En un nuevo histórico, las medianas y el conjunto F pueden ser distintos: eso es normal y debe quedar trazado.
- **Colas bootstrap:** los scores presentan resultados extremos; la media de toda la distribución no debe convertirse en autoridad porque puede estar dominada por unos pocos paths enormes. CVaR de retorno final no capta caídas y recuperaciones *dentro* de una réplica. `equity_final<=5` es proxy terminal, **no** bandera de depletion.
- **Sesgo de crecimiento afortunado:** el 73% de ganancias positivas brutas de #209 se concentra en cinco oportunidades en su lag más concentrado; #216 tiene 83%. Las futuras pruebas de concentración por partido/semana/liga, precio y fuentes físicas son importantes para decidir promoción operacional, no para cambiar subrepticiamente la elección de FS-021 después de ver estos valores.
- **Estabilidad:** #209 obtiene retornos positivos en 11/12 slices, pero **H2 fue negativo (~−8,75%)**, como en #202 (~−8,20%) y #216 (~−6,86%). Los slice tests originales preguntan si el líder científico supera a todos los demás, no si 11/12 son positivos; por tanto la conclusión científica sigue `UNSTABLE`.
- **Provenance/ejecución:** ocho inputs y 139 hashes de streams lógicos pendientes de autenticar en host; odds históricas reconstruidas no equivalen a apuestas que hubieran podido ejecutarse a ese precio y volumen. Comisiones, límites de apuesta, rechazos y liquidez no están medidos; 7% es benchmark aritmético hipotético y de riesgo incomparable.

## R5–R7. Paquetes de software y handoff a F008/F009

**Revisión del `master` remoto al 25/09/2026:** `requirements.txt` (Git blob SHA `f252ee450632126d502c1552ad266256536a6b4f`) declara **`numpy==2.4.6`**, **`scikit-learn==1.9.0`** y **`pytest==9.1.1`**, junto con Django, pytest-django, black y ruff. `pyproject.toml` (Git blob SHA `e401ff2e8646ae53f634a1c7794e2f89aad23274`) configura Python target `py313` y linters. URL: https://github.com/ljarufe/finsport/blob/master/requirements.txt . La branch real FS-021 puede diferir; F009 debe confirmar su fichero antes de instalar.

| Función | Paquete | ¿Añadir dependencia? | Regla |
|---|---|---|---|
| Frontera discreta, bootstrap terminal, CVaR, medianas, MAD/IQR | NumPy 2.4.6 | **No** | No usar pandas en el módulo runtime; es posible con NumPy + stdlib. |
| JSON/GZIP, Decimal, CSV, hash, CLI | Biblioteca estándar Python 3.13 | **No** | Decimal para retornos observados y comparación; NumPy float64 y orden canónico para CVaR bootstrap. |
| Pruebas, mocks, fixtures | pytest 9.1.1, pytest-django 4.14.0 | **No** | Suites aisladas que no puedan llamar proveedores ni tocar DB operacional. |
| Diagnóstico opcional de outliers/clustering | scikit-learn 1.9.0, ya declarado | **No** | No participa en la autoridad del selector; HDBSCAN/MCD sólo para explorar. |
| Visualización opcional | Plotly/matplotlib fuera del motor o frontend existente | No para cerrar el selector | Generar CSV/JSON autocontenidos, vistas de report no bloqueantes. |
| SciPy directo, PyTorch, TensorFlow, `pymoo` o nuevos optimizadores | No necesario | **No instalar** | La frontera exacta para 231 elementos no requiere solver pesado ni aprendizaje. |

**Módulos propuestos, sujetos a preflight del checkout:** `football/experiments/economic_metrics.py` (derivación offline reproducible desde ledgers), `football/experiments/economic_selector.py` (función pura única), `football/experiments/economic_report.py` (salida humano/machine) y comando separado `--analyze-existing EXECUTION_ID`/`--publish-existing EXECUTION_ID`. No recomputar implícitamente miles de paths durante publicación; no reemplazar runner ni políticas Capital.

**Repetición costosa:** NO necesaria para elegir con R, D y L disponibles. Sí se debe instrumentar el runner *para próximos experimentos* con arrays compactos por réplica de MDD, CDaR, mínimo equity/cash, bandera real depletion, pico/medio de reserva y duración. Si F008 acepta opcionalmente recuperar estas métricas para las 15.000 réplicas antiguas, hacer **una única pasada instrumentada** de 3.465.000 paths con mismo seed, pairing, stop 5u y match de los scores originales, después de un benchmark acotado; estimación del audit: 2,5–4 h según equipo. Publicar riesgos como diagnóstico de la versión v1 sin cambiar pesos/criterios sobre la marcha. Si una contradicción material nueva aparece, STOP/revisar adenda, no publicar un líder ficticio.

**Estado R6:** auditoría de integridad de la **copia** y cálculo reproducible completados; auditoría del checkout/streams retenidos pendiente exclusivamente de F009. **R7:** la adenda acompaña este documento; requiere aceptación explícita de Luis antes de que Codex modifique la rama FS-021. **R8 CLOSED:** sólo cuando ticket/acceso físico y UAT del selector se concilien; todavía no declarado.

### Tabla de las primeras veinte (orden explicativo; solo las primeras tres superan ambas referencias robustas)

La posición primera es la única selección del selector propuesto sobre la **copia**. Las posiciones siguientes no son recomendaciones alternativas: 2–3 superan ambos umbrales y las demás documentan por qué se descartaron. La clasificación completa y las métricas originales permanecen en el CSV de 231.

| Puesto | # | Prediction | Decision | Capital | Peor retorno | MDD | Pérdida CVaR peor bloque | Estado |
|---:|---:|---|---|---|---:|---:|---:|---|
| 1 | #209 | MARKET_CONSENSUS | CONF(0.45) | FRACTIONAL_KELLY | 66.67% | 12.23% | 17.60% | Pasa ambos límites |
| 2 | #216 | MARKET_CONSENSUS | CONF(0.50) | FRACTIONAL_KELLY | 65.59% | 8.48% | 17.08% | Pasa ambos límites |
| 3 | #223 | MARKET_CONSENSUS | CONF(0.55) | FRACTIONAL_KELLY | 45.17% | 7.46% | 17.17% | Pasa ambos límites |
| 4 | #202 | MARKET_CONSENSUS | CONF(0.40) | FRACTIONAL_KELLY | 84.87% | 21.54% | 33.91% | Frontera; fuera del rango |
| 5 | #195 | MARKET_CONSENSUS | MODAL_ALL | FRACTIONAL_KELLY | 80.54% | 21.32% | 34.10% | Frontera; fuera del rango |
| 6 | #173 | ELO_MULTINOMIAL_LOGIT | VALUE(0.00) | LEGACY_PARTIAL | 53.53% | 48.01% | -12.24% | Frontera; fuera del rango |
| 7 | #31 | DIXON_COLES | CONF(0.55) | LEGACY_RECOVERY | 119.38% | 39.01% | 99.52% | Frontera; fuera del rango |
| 8 | #157 | ELO_MULTINOMIAL_LOGIT | CONF(0.55) | LEGACY_RECOVERY | 118.30% | 58.14% | 97.32% | Frontera; fuera del rango |
| 9 | #60 | DIXON_COLES | VALUE(0.05) | LEGACY_CAPPED | 124.26% | 78.51% | 98.68% | Frontera; fuera del rango |
| 10 | #194 | MARKET_CONSENSUS | MODAL_ALL | LEGACY_PARTIAL | 22.85% | 21.49% | 75.74% | Dominada o no frontal |
| 11 | #227 | MARKET_CONSENSUS | CONF(0.60) | LEGACY_RECOVERY | 68.53% | 32.45% | 85.94% | Dominada o no frontal |
| 12 | #159 | ELO_MULTINOMIAL_LOGIT | CONF(0.55) | LEGACY_PARTIAL | 26.69% | 49.83% | 55.74% | Dominada o no frontal |
| 13 | #229 | MARKET_CONSENSUS | CONF(0.60) | LEGACY_PARTIAL | 25.75% | 40.94% | 90.79% | Dominada o no frontal |
| 14 | #131 | ELO_MULTINOMIAL_LOGIT | MODAL_ALL | LEGACY_PARTIAL | 16.25% | 25.43% | 92.90% | Dominada o no frontal |
| 15 | #187 | ELO_MULTINOMIAL_LOGIT | VALUE(0.05) | LEGACY_PARTIAL | 36.13% | 52.05% | 9.28% | Dominada o no frontal |
| 16 | #56 | DIXON_COLES | VALUE(0.05) | FLAT_UNIT | 34.76% | 33.10% | 97.35% | Dominada o no frontal |
| 17 | #172 | ELO_MULTINOMIAL_LOGIT | VALUE(0.00) | LEGACY_CAPPED | 61.64% | 58.42% | 92.49% | Dominada o no frontal |
| 18 | #186 | ELO_MULTINOMIAL_LOGIT | VALUE(0.05) | LEGACY_CAPPED | 71.42% | 64.29% | 33.99% | Dominada o no frontal |
| 19 | #53 | DIXON_COLES | VALUE(0.02) | LEGACY_CAPPED | 22.06% | 71.51% | 98.17% | Dominada o no frontal |
| 20 | #46 | DIXON_COLES | VALUE(0.00) | LEGACY_CAPPED | 10.88% | 73.34% | 98.73% | Dominada o no frontal |

### Artefactos adjuntos recomendados

- `FS-021_adenda_selector_unico_v1_PROPUESTA.md` — contrato implementable y criterios de aceptación.
- `FS021_single_economic_selector_reference.py` — referencia de la función pura y auditoría del ZIP, NO código de promoción operacional.
- `FS021_single_selector_full_231.csv`, `FS021_single_selector_top20.csv`, `observed_693_enriched_derived.csv`, `prototype_frontier.csv`, `selector_reference_result.json`, `selector_reference_231_trace.csv` — métricas, trazabilidad y resultado retrospectivo.
- `test_reference_selector.py` — seis tests ilustrativos de casos límite; F009/Codex deben extenderlos a 231×3 y fixtures semánticos completos.
- **Conservar por separado** el ZIP de auditoría de 85 MiB entregado por Luis y los artefactos científicos originales: la entrega complementaria aquí NO los duplica ni autoriza su eliminación.
