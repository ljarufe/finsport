# FS-003 — Investigación técnica exhaustiva para baseline predictivo, mercado y decisión HOME/AWAY/NO_BET

## Contrato de investigación y criterio de arquitectura

El brief define un problema deliberadamente más estrecho que “predecir fútbol”: para un **fixture futuro**, usando solamente **información que existía antes del kickoff** y **múltiples cuotas 1X2 actuales**, FS-003 debe producir una decisión entre `HOME`, `AWAY` y `NO_BET`, de forma interpretable, medible y comparable con la heurística histórica. También establece restricciones arquitectónicas decisivas: API-Football es la fuente primaria de entidades/resultados, Inkabet es secundaria y read-only; `OddsSnapshot` conserva sólo el último valor por `Match / Source / Bookmaker / Market`; no existe actualmente una serie temporal de odds; y el algoritmo legacy centrado en empates es evidencia histórica, no especificación aprobada. fileciteturn0file0

La conclusión de esta investigación es **recomendar Dixon–Coles como baseline primario**, pero no porque deba asumirse superior: debe entrar a FS-003 como **hipótesis falsable** frente a dos comparadores explícitos —Poisson independiente y Elo + ordered logit— y frente al mercado cuando existan odds pre-kickoff válidas. Maher mostró que un Poisson con fortalezas ofensivas y defensivas ya describe razonablemente scores de fútbol; Dixon y Coles extendieron esa familia para corregir dependencias en resultados bajos y tratar la dinámica temporal; trabajos posteriores han desarrollado modelos bivariados y dinámicos más sofisticados, pero no existe evidencia general de que mayor complejidad garantice mejor forecast fuera de muestra. citeturn15search0turn15search1turn15search9turn18search7turn18search4

Una publicación de 2026 refuerza precisamente esta cautela: comparando diferentes modelos de conteo y esquemas dinámicos en Bundesliga, EPL y La Liga, las diferencias entre modelos de goles pueden ser pequeñas y, en varias ventanas de evaluación, el promedio del mercado obtuvo Brier/RPS mejores que los modelos estadísticos. Eso no demuestra que Dixon–Coles sea inadecuado para Finsport; sí demuestra que **la arquitectura debe estar construida para descubrir que no aporta valor y no para justificarlo después de implementarlo**. citeturn14search9

A lo largo del informe se usan tres niveles deliberadamente separados:

**Evidencia** significa un resultado publicado, documentación primaria o una propiedad matemática del método.

**Inferencia para Finsport** significa una consecuencia razonable de esa evidencia combinada con el contrato del brief.

**Recomendación FS-003** significa la decisión concreta propuesta para implementación. Algunas recomendaciones son deliberadamente parámetros provisionales porque no pueden justificarse universalmente sin medir datos de Finsport.

La arquitectura recomendada se basa en una separación que conviene mantener estricta:

```text
modelo deportivo
    estima P(HOME), P(DRAW), P(AWAY)
        ↓
mercado
    estima una referencia de consenso independiente
        ↓
precio ejecutable
    determina el EV de HOME/AWAY
        ↓
policy
    decide HOME / AWAY / NO_BET
```

No conviene mezclar mercado dentro de Dixon–Coles en la primera implementación. Hacerlo podría mejorar la predicción final, pero impediría contestar la pregunta de producto más importante: **¿el histórico futbolístico local aporta información incremental respecto del mercado?** Las odds de bookmakers son forecasts muy competitivos: un estudio sobre 10.699 partidos de seis ligas europeas encontró diferencias de calidad entre bookmakers y una mejora de su efectividad con el tiempo. citeturn17search0turn17search4

## Comparación profunda de modelos predictivos

La comparación relevante para FS-003 no debe preguntarse solamente “qué modelo tiene mejor paper”, sino qué modelo satisface simultáneamente interpretabilidad, probabilidad 3-way coherente, capacidad de manejar home advantage, recencia y principios de temporada, costo computacional, riesgo de overfitting y compatibilidad con la DB disponible.

| Familia | Cómo produce `P(H/D/A)` | Datos mínimos | Home advantage | Ataque/defensa | Recencia | Inicio de temporada | Complejidad | Rol recomendado |
|---|---|---|---|---|---|---|---|---|
| Poisson independiente | Matriz `P(X=x)P(Y=y)` y suma por `x>y`, `x=y`, `x<y` | equipos, goles, localía, kickoff | parámetro explícito | sí | opcional vía weighting | carry-over o reestimación | baja | comparator |
| Dixon–Coles | Igual que Poisson, con corrección `τ` en 0–0, 0–1, 1–0, 1–1 | mismos datos | explícito | sí | incorporado naturalmente mediante time weighting | carry-over + decay | baja-media | **baseline primario** |
| Bivariate Poisson | Distribución conjunta con término compartido/correlación | goles y equipos | explícito | sí | añadible | igual problema de cold start | media | posterior/challenger |
| Elo + ordered logit | Rating diferencial → regresión ordinal → 3 probabilidades | outcome, equipos, localía, tiempo | bonus/covariable | no separa ataque/defensa | natural por actualización secuencial | carry-over natural | baja | comparator |
| Multinomial/logistic directo | softmax de features para H/D/A | features pre-match + outcomes | feature | sólo si se diseñan features | manual | depende del feature pipeline | media | no prioritario |
| Bradley–Terry-like | fortaleza relativa → probabilidades; draw requiere extensión | outcomes | añadible | normalmente una fortaleza global | actualización/weights | carry-over | baja-media | no necesario si ya hay Elo |
| Bayes/dynamic state-space | estados latentes variables en el tiempo → score model | histórico amplio | sí | sí, dinámicos | explícita en el estado | elegante | alta | fuera de baseline |
| Market-only | odds de-vigged → `P(H/D/A)` | odds | ya incorporado por mercado | implícito | incorporado por mercado | no cold-start | baja | benchmark externo |

**Poisson independiente.** Sea \(X\) la cantidad de goles local y \(Y\) la visitante:

\[
X\sim \text{Poisson}(\lambda),\qquad
Y\sim \text{Poisson}(\mu).
\]

Un modelo log-lineal interpretable puede ser:

\[
\log \lambda =
b + h + a_{\text{home}} + d_{\text{away}},
\]

\[
\log \mu =
b + a_{\text{away}} + d_{\text{home}},
\]

donde \(b\) es la tasa base de goles de la competición, \(h\) es home advantage, \(a_i\) mide fuerza ofensiva y \(d_i\) vulnerabilidad defensiva. El modelo genera una matriz completa:

\[
P(X=x,Y=y)=
\frac{e^{-\lambda}\lambda^x}{x!}
\frac{e^{-\mu}\mu^y}{y!}.
\]

Luego,

\[
P(H)=\sum_{x>y}P(x,y),\qquad
P(D)=\sum_{x=y}P(x,y),\qquad
P(A)=\sum_{x<y}P(x,y).
\]

Maher introdujo precisamente fortalezas ofensivas y defensivas en una familia Poisson y encontró que la versión independiente daba una descripción razonablemente buena, aunque con pequeñas diferencias sistemáticas; también reportó que incorporar correlación mediante una bivariada podía mejorar el ajuste. citeturn15search0

**Ventaja para FS-003:** es extraordinariamente fácil de explicar, probar y usar como control. Si Dixon–Coles no supera a este modelo fuera de muestra, la corrección adicional no está justificando su complejidad.

**Limitación:** la independencia entre scores es una aproximación fuerte y los resultados bajos —especialmente los que determinan muchos draws— son justamente una región donde Dixon–Coles intenta mejorar el modelo original. citeturn15search1

**Dixon–Coles.** Mantiene la misma estructura interpretable de expected goals, pero modifica probabilidades conjuntas de ciertos scores bajos y permite ponderar el histórico según antigüedad. El trabajo original fue ajustado a fútbol inglés de 1992–1995 y evaluado con odds de 1995–1996; los autores mostraron que la estimación por máxima verosimilitud era computacionalmente viable y reportaron retorno positivo en su experimento de betting. Ese resultado histórico no debe extrapolarse como expectativa de rentabilidad actual. citeturn15search1turn15search3

Para FS-003 tiene una propiedad especialmente valiosa: casi toda su sofisticación extra ocurre **sin abandonar una semántica fácil de inspeccionar**. Seguimos teniendo ataque, defensa, home advantage, expected home goals, expected away goals, una matriz de scores y una suma transparente hacia las tres probabilidades.

**Bivariate Poisson.** La alternativa natural es modelar \(X\) y \(Y\) conjuntamente a través de componentes Poisson compartidos. Karlis y Ntzoufras desarrollaron modelos bivariados para datos deportivos y extensiones infladas destinadas, entre otras cosas, a representar mejor la diagonal/draws. citeturn15search9

Es conceptualmente más general que corregir sólo cuatro celdas. Pero esa ventaja tiene costo: agrega una estructura de dependencia que debe estimarse y validarse, y complica la implementación sin evidencia previa de que los datos Finsport requieran esa flexibilidad. Koopman y Lit fueron todavía más lejos con una bivariada dinámica cuyos coeficientes varían estocásticamente en el tiempo. Es una técnica legítima y potente, pero es una segunda fase natural, no un baseline. citeturn18search4turn18search14

**Elo + ordered logit.** Elo resume el histórico de resultados en una fortaleza dinámica por equipo. La actualización canónica tiene forma:

\[
R_i^{new}=R_i + K(S_i-E_i),
\]

donde \(S_i\) puede tomar, por ejemplo, 1/0.5/0 para win/draw/loss, y \(E_i\) es el resultado esperado en función de la diferencia de ratings.

Pero un Elo puro no soluciona por sí solo el problema 1X2: el expected score no es una distribución completa sobre HOME/DRAW/AWAY. Hvattum y Arntzen utilizaron el diferencial Elo como covariable de un **ordered logit**, evaluándolo frente a otros métodos mediante métricas estadísticas y económicas. citeturn16search1turn16search5

Una formulación directa para Finsport, ordenando `AWAY < DRAW < HOME`, sería:

\[
\eta=\beta(R_H-R_A)+h_E,
\]

\[
P(Y\leq k)=\sigma(\theta_k-\eta),
\]

de donde:

\[
P(A)=\sigma(\theta_1-\eta),
\]

\[
P(D)=
\sigma(\theta_2-\eta)-\sigma(\theta_1-\eta),
\]

\[
P(H)=1-\sigma(\theta_2-\eta).
\]

Una publicación posterior de los mismos autores compara nuevamente modelos basados en ratings y confirma que ordered logit puede producir directamente las tres probabilidades pre-match. citeturn16search2turn16search4

**Ventajas:** muy barato, extremadamente robusto, recencia implícita en las actualizaciones y excelente comportamiento conceptual entre temporadas porque el rating puede continuar de una temporada a otra.

**Desventajas:** una sola fortaleza comprime información que el fútbol naturalmente separa en producción ofensiva y capacidad defensiva; tampoco usa el score 3–0 de manera tan rica como un modelo de goles salvo que se modifique la regla de actualización.

Por eso es un **comparador especialmente valioso**: si Elo-logit iguala a Dixon–Coles, Finsport debe preguntarse si los parámetros de ataque/defensa realmente agregan valor.

**Multinomial logit y Bradley–Terry.** Son baselines estadísticamente válidos y pueden modelar directamente el outcome. Sin embargo, en FS-003 añadirlos produciría redundancia: Elo-logit ya representa la familia de ratings/outcome models con una implementación pequeña. Además, modelos directos con identificadores de equipos y múltiples features introducen mayor libertad paramétrica y exigen decisiones de feature engineering que dificultan aislar qué información causa la mejora.

**Modelos dinámicos/Bayesianos.** Rue y Salvesen propusieron un dynamic generalized linear model donde attack/defence evolucionan en el tiempo y utilizaron MCMC para inferencia. Crowder et al. modelaron también fortalezas ofensivas/defensivas variables como procesos estocásticos y observaron que la versión completa con MCMC era sustancialmente más costosa que sus aproximaciones. citeturn18search0turn18search7

Esto responde también a la cuestión implícita de GPU/AI: **no existe evidencia suficiente para que FS-003 necesite GPU, boosting o redes neuronales para establecer el baseline**. La literatura ya ofrece modelos dinámicos estadísticos mucho más sofisticados que Dixon–Coles y que siguen siendo CPU-friendly; antes de aumentar capacidad es necesario demostrar que un modelo simple deja señal predictiva sin explotar. citeturn18search7turn18search4

**Mercado como modelo.** Las probabilidades de-vigged del mercado son probablemente el benchmark práctico más exigente. En 10.699 partidos, Štrumbelj y Robnik-Šikonja encontraron diferencias entre bookmakers y mejoramiento temporal de las odds como forecasts. Un estudio reciente de modelos dinámicos encontró además que el average market fue superior en Brier/RPS a sus modelos estadísticos en varias ventanas de Bundesliga, EPL y La Liga. citeturn17search0turn14search9

Pero Finsport actualmente no tiene histórico temporal suficiente de odds, por lo cual el mercado no puede sustituir retrospectivamente a los comparadores estadísticos.

**Evidencia.** No hay una razón académica fuerte para asumir que Dixon–Coles ganará siempre. La literatura demuestra más bien que Poisson es un baseline sólido, que las dependencias adicionales pueden ayudar y que modelos dinámicos más complejos existen; el mercado puede ser aún más competitivo. citeturn15search0turn15search9turn14search9

**Inferencia para Finsport.** Dixon–Coles ocupa un punto especialmente favorable en el trade-off: incorpora ataque, defensa, home advantage, dependencia de low scores y recencia, pero sigue siendo completamente auditable y utiliza datos que el brief confirma que Finsport ya posee.

**Recomendación FS-003.** Implementar:

```text
PRIMARY
Dixon–Coles

COMPARATOR A
Independent Poisson con misma parametrización de ataque/defensa/home advantage
(rho = 0)

COMPARATOR B
Elo → ordered logit HOME/DRAW/AWAY
```

El mercado de-vigged se considera **benchmark externo**, no cuarto modelo entrenado.

La elección de Dixon–Coles debe revocarse si el walk-forward de Finsport demuestra que no mejora materialmente a los comparadores.

## Diseño completo del baseline Dixon–Coles

La implementación debería diseñarse como un modelo por `Competition`, con datos cruzando límites de temporada cuando corresponda. No debe reiniciarse automáticamente cada Season.

**Parametrización.** Para \(T\) equipos de una competición:

\[
\theta=
\{
b,h,\rho,
a_1,\ldots,a_T,
d_1,\ldots,d_T
\}.
\]

Usando “defence vulnerability” para evitar confusiones de signo:

\[
\log\lambda_{ij}
=
b+h+a_i+d_j,
\]

\[
\log\mu_{ij}
=
b+a_j+d_i.
\]

Interpretación:

- \(b\): baseline log-goals de la competición;
- \(h\): incremento multiplicativo de intensidad para el local;
- \(a_i>0\): equipo \(i\) produce más goles que la media;
- \(d_i>0\): equipo \(i\) concede más goles que la media;
- \(\lambda\): expected home goals;
- \(\mu\): expected away goals;
- \(\rho\): corrección de dependencia para scores bajos.

La literatura Poisson/Dixon–Coles sustenta el uso de fortalezas ofensivas/defensivas y home effect. citeturn15search0turn15search1

Con intercepto y efectos por equipo hay invariancias de escala. Una implementación práctica debe imponer restricciones de identificabilidad, por ejemplo:

\[
\sum_i a_i=0,\qquad \sum_i d_i=0.
\]

Así \(b\) mantiene una interpretación de promedio de liga y los efectos representan desviaciones relativas.

**Corrección de low scores.** La probabilidad conjunta Dixon–Coles es:

\[
P(X=x,Y=y)
=
\tau(x,y;\lambda,\mu,\rho)
\operatorname{Pois}(x;\lambda)
\operatorname{Pois}(y;\mu),
\]

con:

\[
\tau(x,y)=
\begin{cases}
1-\lambda\mu\rho & x=0,y=0 \\
1+\lambda\rho & x=0,y=1 \\
1+\mu\rho & x=1,y=0 \\
1-\rho & x=1,y=1 \\
1 & \text{otherwise}.
\end{cases}
\]

La intención del término es concentrar la corrección donde el modelo independiente presenta su discrepancia más relevante, sin agregar una dependencia general sobre toda la matriz. Dixon–Coles introdujo justamente esta modificación local junto con el tratamiento dinámico del histórico. citeturn15search1turn15search8

No se debe fijar el signo ni el valor de \(\rho\) “porque suele ser aproximadamente X”. **\(\rho\) debe estimarse de los datos Finsport**, y toda predicción debe verificar que los cuatro factores \(\tau\) relevantes sean positivos. Un optimizer que produzca probabilidades no válidas debe marcar el fit como inválido en lugar de corregirlas silenciosamente.

**Likelihood.** Para cada partido histórico \(k\), con goles \(x_k,y_k\), intensidades \(\lambda_k,\mu_k\) y peso temporal \(w_k\):

\[
\ell(\theta)
=
\sum_k
w_k
\left[
\log \tau(x_k,y_k)
+
x_k\log \lambda_k-\lambda_k-\log(x_k!)
+
y_k\log \mu_k-\mu_k-\log(y_k!)
\right].
\]

Se maximiza \(\ell\), o equivalentemente se minimiza negative log-likelihood, respetando constraints.

El Poisson comparator debe usar **exactamente el mismo entrenamiento**, salvo:

\[
\rho=0,\quad \tau=1.
\]

Esto es importante: comparar Dixon–Coles contra un Poisson con ventanas, optimizadores o tratamiento de temporadas diferente confundiría el valor de \(\rho\) con el valor del pipeline.

**Time decay.** Para un target con tiempo \(T\) y un partido histórico en \(t_k\):

\[
w_k=\exp[-\xi(T-t_k)].
\]

Conviene expresar \(T-t_k\) en días y documentar la unidad. \(\xi=0\) significa que toda la historia pesa igual; cuanto mayor \(\xi\), más rápidamente se olvida.

El paper de Dixon–Coles trata explícitamente la naturaleza dinámica de la capacidad de los equipos, y desarrollos posteriores han modelado esa evolución incluso con procesos latentes estocásticos. citeturn15search1turn18search7

No existe un único \(\xi\) académico válido para todas las competiciones y épocas. **Debe elegirse mediante inner walk-forward validation**. Una búsqueda pequeña y predefinida es suficiente; FS-003 no necesita un optimizador de hiperparámetros sofisticado.

Es preferible parametrizar la búsqueda mediante **half-life**, porque resulta interpretable:

\[
w=2^{-\Delta t / H}.
\]

Por ejemplo, una half-life candidata de \(H\) días significa que un partido de hace \(H\) días pesa la mitad. Los valores candidatos concretos deben clasificarse como defaults experimentales, no conocimiento de literatura.

**Ventana histórica.** No recomiendo “últimas dos temporadas” como regla. La unidad correcta es el tiempo y la información efectiva, no el nombre administrativo de Season.

La política debería ser:

```text
usar partidos anteriores de la misma Competition
→ cruzar fronteras de Season
→ aplicar exponential decay
→ opcionalmente imponer max_history_days / max_seasons sólo por estabilidad y costo
→ elegir decay y cap con inner walk-forward
```

Dos temporadas pueden significar cantidades muy distintas de partidos según tamaño, formato y frecuencia de una liga. El weighting continuo hace además innecesario un corte duro en diciembre o junio.

**Inicio de temporada.** Reiniciar todos los parámetros a cero al empezar una Season desperdiciaría información válida. Para equipos que continúan en la misma Competition:

```text
parámetros temporada previa
    ↓ decaídos por tiempo transcurrido
prior/inicialización temporada nueva
```

Esto no implica tratar al club como idéntico eternamente; el decay permite que la información pierda peso.

Para un promoted team o cualquier equipo sin historia suficiente dentro de esa Competition, Dixon–Coles puro enfrenta un cold start real.

**Recomendación para promovidos/nuevos:** inicializar ataque y defensa en el promedio de competición:

\[
a_i=0,\qquad d_i=0,
\]

y clasificar al equipo como `cold_start=true`.

Mientras el equipo no alcance una cantidad suficiente de observaciones efectivas, Finsport puede seguir generando probabilidades —son útiles para evaluar el modelo— pero la policy de value debería poder producir `NO_BET` por insufficient history.

No propongo importar automáticamente la fuerza estimada en una división inferior: la relación entre escalas de ligas debe calibrarse; trasladar el parámetro sin ajuste crea una falsa precisión. Elo podría eventualmente ofrecer un mecanismo más natural de carry-over intercompetición, pero eso debe evaluarse por separado.

El umbral exacto de “historia suficiente” **no tiene un valor universal respaldado por literatura**. Debe ser un parámetro Finsport medido mediante estabilidad del fit y evaluación out-of-sample.

**Estimación y actualización.** El fitting debería seguir este flujo:

```text
1. tomar completed matches estrictamente anteriores al prediction_time
2. construir team index de la Competition
3. obtener parámetros previos como warm-start, si existen
4. calcular pesos temporales
5. optimizar negative weighted log-likelihood
6. verificar convergence
7. verificar constraints / tau positivity / finite parameters
8. producir lambdas del nuevo fixture
9. generar score matrix
10. colapsar a HOME/DRAW/AWAY
```

Warm-start no cambia el modelo; reduce costo y ayuda al optimizer. El baseline es suficientemente pequeño para CPU. No hay justificación para GPU.

**Conversión de score matrix a 1X2.** Para un fixture:

\[
M_{xy}=P(X=x,Y=y).
\]

Entonces:

\[
P(H)=\sum_{x>y}M_{xy}
\]

\[
P(D)=\sum_{x=y}M_{xy}
\]

\[
P(A)=\sum_{x<y}M_{xy}.
\]

No conviene hardcodear arbitrariamente `0..10` goles y asumir que la matriz ya suma uno. La implementación debe aumentar el máximo de goles hasta que la masa Poisson omitida sea menor a una tolerancia numérica, por ejemplo `1e-8`, y luego comprobar:

```text
abs(P_HOME + P_DRAW + P_AWAY - 1) < tolerance
```

La tolerancia es un parámetro numérico de implementación, no un hiperparámetro deportivo.

**Inputs exactos del baseline primario:**

| Input | Uso |
|---|---|
| `Competition` | universo independiente de estimación |
| `Match.id` | exclusión del target y trazabilidad |
| `kickoff` | orden temporal y decay |
| `home_team_id` | ataque local/defensa local |
| `away_team_id` | ataque visitante/defensa visitante |
| `home_score` | likelihood histórica |
| `away_score` | likelihood histórica |
| status final válido | asegurar que el score es usable |
| Season | diagnóstico/segmentación; no reset automático |
| home/away designation | home advantage |

No necesita standings, injuries, lineups, provider predictions, bookmaker odds ni estadísticas avanzadas para producir probabilidades.

**Evidencia.** Dixon–Coles ofrece una extensión parsimoniosa del Poisson, mientras los modelos bivariados/dinámicos demuestran que existen estructuras más flexibles pero más costosas. citeturn15search0turn15search1turn18search0turn18search4

**Inferencia para Finsport.** La escasez de features adicionales deja de ser un problema: la DB canónica existente contiene justamente las variables requeridas.

**Recomendación FS-003.** Implementar la versión completa descrita arriba, pero hacer `rho`, decay, max-history y cold-start eligibility configurables y seleccionables sólo con datos pasados. Nunca fijar valores observados mirando el período test.

## Relectura estadística de la heurística histórica de Finsport

La heurística legacy no debe ser reimplementada literalmente. Sí contiene varias intuiciones que coinciden parcialmente con conceptos estadísticos modernos. El brief preserva sus factores y reglas exclusivamente como research evidence. fileciteturn0file0

| Idea legacy | Equivalente moderno | Plausibilidad | Cómo testearla | Destino recomendado |
|---|---|---|---|---|
| HOME/AWAY odds similares | competitive balance implícito por mercado | alta como descriptor, baja como señal independiente | estudiar draw rate y residual de draw controlando `p_market_draw` según `|pH-pA|` | **ablation/comparator** |
| draw odds 2.8–4.2 | band-pass sobre probabilidad implícita de draw | plausible, rango arbitrario | convertir a de-vigged `p_draw`, bins y reliability | **descartar rango fijo**, conservar variable |
| league draw percentage | prior/base rate de draw | estadísticamente razonable | rolling pre-kickoff draw rate y calibración incremental | **feature/diagnóstico ablation** |
| excluir odds extremas | filtro favorite/longshot | plausible, depende de mercado | performance por deciles de market probability | **ablation**, no regla hardcoded |
| sólo cerca de kickoff | información más madura/frescura del mercado | muy plausible operacionalmente | comparar snapshots T-24h/T-3h/T-60m/T-15m cuando exista history | **future timing experiment** |
| rankear pocos candidatos | selective prediction / top-edge filtering | plausible para controlar coverage | curva performance vs coverage/top-k | **decision-policy experiment** |
| abstenerse | reject option / selective decision | fuertemente defendible | coverage vs forecast quality / ROI | **conservar como principio central** |

**Similitud de HOME/AWAY odds.** Dos probabilidades de mercado similares significan que el mercado considera parecidas las chances de los dos equipos; esto es una forma de competitive balance. Puede correlacionarse con draws, pero hay una distinción crucial: el propio `DRAW` price ya contiene la estimación del mercado sobre el empate. Por tanto, `|p_market_home-p_market_away|` sólo sería información incremental si explica draws **después de condicionar por `p_market_draw`**.

El test apropiado no es reproducir `abs(local_factor - visitor_factor) <= 3`, sino estimar, por ejemplo:

\[
DRAW_i \sim
\beta_0+
\beta_1 p_{D,i}^{market}
+
\beta_2 |p_{H,i}^{market}-p_{A,i}^{market}|.
\]

Y, más importante, verificar fuera de muestra si \(\beta_2\) mejora log loss/Brier.

**Recomendación:** no introducirlo dentro de Dixon–Coles. Conservarlo como ablation de market features cuando exista suficiente odds history.

**Draw odds 2.8–4.2.** Una cuota decimal 2.8 corresponde a `1/2.8 ≈ 35.7%` raw implied probability y 4.2 a `≈23.8%`, antes de remover vig. Es simplemente una banda de probabilidad implícita. El problema es que raw inverse odds mezcla probabilidad + margin; métodos distintos de remover overround pueden producir diferencias suficientes para cambiar conclusiones empíricas. citeturn16search6

**Recomendación:** descartar `2.8 <= draw_factor <= 4.2` como regla. Conservar `p_market_draw` de-vigged como variable para análisis.

**Draw percentage de la liga.** Esto sí representa una idea estadística clara: una tasa base. Un modelo que no conoce nada del fixture debería respetar la prevalencia histórica de outcomes. En Dixon–Coles, la estructura de scoring y los parámetros de competición ya contienen buena parte de esta información. Añadir `league_draw_percentage` directamente puede entonces ser redundante.

Debe construirse sólo con partidos previos:

\[
draw\_rate(T)=
\frac{
\#\{\text{draws con kickoff}<T\}
}{
\#\{\text{completed matches con kickoff}<T\}
}.
\]

Nunca usar la tasa final de la Season para partidos jugados en septiembre.

**Recomendación:** conservar como **diagnóstico/calibration feature ablation**, no como `league.draw_percentage >= 20`.

**Exclusión por odds extremas.** Existe una literatura amplia sobre favorite–longshot bias, pero su magnitud no es universal y el método de de-vig importa. Štrumbelj mostró que algunas conclusiones sobre sesgos cambian según el método utilizado para inferir probabilidades, y Clarke et al. diseñaron su power method precisamente para permitir distribuciones de margin distintas entre favoritos y longshots. citeturn16search3turn16search6

Por eso `local_factor >= 1.5` y `visitor_factor >= 1.5` no tienen justificación universal.

El test útil es estratificar por `p_market` o por best odds y preguntar:

```text
¿se deterioran calibration / edge realization / ROI
en las colas de market probability?
```

Si la respuesta es sí, una exclusión futura puede justificarse empíricamente.

**Selección cerca del kickoff.** Esta intuición tiene especial plausibilidad para **odds**, no necesariamente para el modelo histórico. API-Football documenta que sus pre-match odds se actualizan aproximadamente cada tres horas y que sólo conserva siete días de history; por tanto, distintos instantes contienen snapshots diferentes. citeturn19search1

Una cuota más cercana al kickoff puede incluir nueva información, pero tampoco debe asumirse “mejor” sin medirla. Además, elegir el instante después de conocer resultados sería leakage.

**Recomendación:** FS-003 debe definir un `decision_time` determinista y guardar snapshots. La antigua ventana de `now+5m` a `now+65m` no se conserva por autoridad.

**Ranking de pocos candidatos.** Esto puede reinterpretarse como cambiar **coverage**: en vez de apostar todos los edges positivos, se toma el top-k. Es legítimo, pero produce otra policy y debe evaluarse como tal.

La curva correcta es:

```text
threshold/top-k
→ coverage
→ Brier/calibration de subconjunto
→ realized edge / ROI
```

Seleccionar sólo el “mejor” partido de una tanda puede subir apparent ROI por azar y aumenta riesgo de selection bias si k se optimiza retrospectivamente.

**Posibilidad de abstenerse.** Ésta es probablemente la idea legacy más importante que debe preservarse. `NO_BET` permite separar forecast de decisión. Un buen probabilistic model puede producir una distribución perfectamente útil y al mismo tiempo concluir que ningún precio ofrece valor suficiente.

**Recomendación:** mantener `NO_BET` como output normal y frecuente, pero reemplazar la fórmula legacy con criterios explícitos de market validity + EV/edge.

En síntesis:

```text
SE CONSERVA
NO_BET como concepto

SE CONSERVA PARA ABLATION / DIAGNÓSTICO
market balance
market draw probability
rolling league draw rate
extreme-odds regime
top-k / coverage

SE CONVIERTE EN EXPERIMENTO FUTURO
timing near kickoff

SE DESCARTA
la fórmula legacy, sus coeficientes 5/2/2 y sus thresholds raw
como reglas normativas
```

## Mercado multibookmaker, value, NO_BET, odds históricas y API-Football Predictions

Para cada bookmaker \(b\) y outcome \(c\in\{H,D,A\}\), sea la decimal odd \(o_{b,c}\).

La probabilidad implícita raw es:

\[
q_{b,c}=\frac{1}{o_{b,c}}.
\]

El overround es:

\[
m_b=
\sum_c q_{b,c}-1.
\]

Ejemplo:

```text
HOME 2.00 → 0.500
DRAW 3.40 → 0.294
AWAY 4.00 → 0.250

sum = 1.044
overround = 4.4%
```

No debe compararse directamente `p_model` contra esos valores raw porque no suman uno.

**Métodos de de-vig.**

| Método | Definición conceptual | Ventaja | Problema |
|---|---|---|---|
| Multiplicative/basic normalization | \(p_i=q_i/\sum q_j\) | trivial, estable | asume margin proporcional |
| Additive | resta una fracción igual del overround | simple | puede generar probabilidades negativas |
| Shin | infiere estructura asociada a informed betting | tiene fundamento económico | más compleja; hipótesis específica |
| Power | \(p_i=q_i^k\), con \(k\) tal que \(\sum p_i=1\) | siempre dentro de `[0,1]`, permite margin no proporcional | requiere resolver \(k\) |

Clarke, Kovalchik e Ingram compararon additive, normalization, Shin y power en tres datasets deportivos; reportaron que power superó a multiplicative en esos datos y fue comparable o superior a Shin. citeturn16search3 Štrumbelj mostró separadamente que basic normalization puede producir probabilidades sesgadas y que la elección del método puede cambiar conclusiones empíricas. citeturn16search6

**Evidencia:** hay razones para no tratar normalización multiplicativa como verdad.

**Inferencia:** tampoco existe evidencia de que power deba ser universalmente óptimo en todas las ligas/bookmakers de Finsport.

**Recomendación FS-003:** implementar dos métodos:

```text
primary market de-vig:
POWER

sensitivity comparator:
MULTIPLICATIVE
```

No hace falta Shin en el ticket inicial. Puede añadirse posteriormente si la sensibilidad entre métodos resulta material.

### Construcción del consenso multibookmaker

El orden es importante:

```text
NO:
raw odds → promedio → invert

SÍ:
odds de cada bookmaker
→ implied probabilities
→ de-vig dentro de cada bookmaker
→ validar quote
→ combinar fair probabilities entre bookmakers
```

De-vig antes de agregar evita mezclar casas con margins diferentes.

**Media.** Si cada bookmaker aporta un vector válido \(p_b=(p_H,p_D,p_A)\), el promedio:

\[
\bar p_c=\frac{1}{B}\sum_b p_{b,c}
\]

mantiene automáticamente suma uno y utiliza toda la información.

**Mediana.** La mediana outcome por outcome es robusta frente a un quote extremo:

\[
\tilde p_c=\operatorname{median}_b(p_{b,c}),
\]

pero \(\sum_c\tilde p_c\) no tiene por qué ser exactamente uno; habría que normalizarla al final.

**Weighted consensus.** Puede ser superior si existen weights realmente estimados: por ejemplo, menor out-of-sample log loss, menor staleness o mayor consistencia con un closing reference. Pero un nombre de bookmaker no constituye evidencia suficiente para decidir que es “sharp”.

Hay evidencia de que distintos bookmakers poseen diferente calidad predictiva. Štrumbelj y Robnik-Šikonja encontraron precisamente heterogeneidad entre diez casas. citeturn17search0 Esto justifica investigar pesos; **no justifica inventarlos sin histórico local**.

**Best available price.** El mejor precio para outcome \(c\) es:

\[
o_c^{best}=\max_b o_{b,c}.
\]

Debe distinguirse del consenso. Deschamps, usando hasta 79 bookmakers por match, encontró que las odds promedio no agotaban toda la información y que best available odds contenían señal adicional, además de que acceder a múltiples bookmakers mejoraba el retorno potencial. citeturn17search1

Pero usar el máximo como “probabilidad verdadera del mercado” introduce un sesgo de selección. Su función correcta para FS-003 es:

```text
CONSENSUS
→ benchmark / p_market

BEST AVAILABLE PRICE
→ payoff disponible / EV
```

No son intercambiables.

**Media versus mediana — recomendación.** La literatura disponible no demuestra que “median of bookmakers” sea universalmente superior. Para Finsport, la mediana tiene una ventaja operacional específica: con tres o más casas puede resistir un quote aislado extremo. Por eso propongo **mediana por outcome + renormalización como robust default provisional** mientras no exista historial suficiente para estimar bookmaker quality.

Debe implementarse, sin embargo, de modo que `mean` pueda ejecutarse como sensibilidad. Una vez que exista history, ambas pueden compararse prospectivamente mediante log loss/Brier contra resultados.

### Stale quotes y outliers

Un quote sólo debe entrar al consenso si:

```text
odds HOME/DRAW/AWAY presentes
todas finite
todas > 1
source/bookmaker identificable
timestamp <= decision_time
timestamp < kickoff
overround dentro de un rango de calidad configurado
no está marcado stale
no es duplicado lógico de otro source
```

La definición exacta de stale depende de que Finsport conserve un **timestamp de observación real**. El brief no confirma que `OddsSnapshot` preserve lo suficiente para reconstruirlo, sólo que el valor es latest-value. fileciteturn0file0

Para outliers, una política robusta puede comparar las probabilidades de-vigged con la mediana cross-book. Un filtro basado en MAD puede utilizar:

\[
z_{b,c}^{robust}
=
\frac{|p_{b,c}-\operatorname{median}(p_{\cdot,c})|}
{MAD(p_{\cdot,c})}.
\]

El cutoff no debe elegirse por intuición; debe quedar configurable y validarse prospectivamente. Con tres bookmakers, eliminar un dato sólo porque es diferente puede ser peligroso: podría ser el quote informativo y no el stale. Por eso conviene **loggear anomalías antes de filtrar agresivamente**.

### Sharp versus recreational

Hay evidencia de calidad heterogénea entre bookmakers, pero no suficiente para que FS-003 tenga una tabla hardcoded `sharp=true/false`. citeturn17search0

La clasificación futura defendible sería estimada con los propios snapshots:

```text
bookmaker
→ pre-kickoff probability history
→ de-vig
→ out-of-sample log loss/Brier
→ freshness / deviation from later consensus
→ estimated weight
```

Hasta disponer de esos datos:

```text
all valid independent bookmakers
→ equal weight
```

### Inkabet frente a bookmakers API-Football

Según el brief, Inkabet es una fuente secundaria read-only, mientras API-Football aporta múltiples bookmakers. fileciteturn0file0

No debería existir un “peso por source” que haga:

```text
50% API-Football
50% Inkabet
```

porque API-Football no es una sola opinión; contiene múltiples bookmakers.

La unidad estadística correcta es:

```text
canonical bookmaker quote
```

Inkabet entra como un bookmaker adicional **sólo si** se verifica:

1. que el market realmente es el mismo 1X2 pre-match;
2. que HOME/DRAW/AWAY usan la misma convención;
3. que el snapshot es fresco;
4. que la misma casa no está duplicada también bajo API-Football.

Si Inkabet y API-Football reportan el mismo bookmaker, deben deduplicarse mediante la identidad canónica y conservar el quote que corresponda al `decision_time` establecido; no contar ambas filas como votos independientes.

Esto exige una verificación de repo/DB.

### Minimum bookmaker coverage

No existe una evidencia académica que convierta “3 bookmakers” en umbral universal.

Sin embargo, **tres tiene una justificación matemática operacional si se usa mediana**: con sólo dos observaciones la mediana no ofrece resistencia real a un outlier; con tres, uno de los tres puede desviarse fuertemente sin mover la mediana al extremo.

Por eso recomiendo:

```text
min_valid_books = 3
```

como **default razonable que debe calibrarse**, no como parámetro respaldado por literatura.

Sensitivity:

```text
2 vs 3 vs 5 valid bookmakers
```

debe compararse una vez exista suficiente historical odds history.

Si sólo hay 1–2 casas, el modelo puede seguir produciendo `P(H/D/A)` y participar en evaluación predictiva, pero la **decision policy de value** debe producir `NO_BET` por `INSUFFICIENT_MARKET_COVERAGE`.

### Expected value y edge

Conviene distinguir dos cantidades.

**Probability edge contra consenso:**

\[
edge_c=
p_c^{model}-p_c^{market}.
\]

Ejemplo:

```text
model HOME = 0.47
market HOME = 0.43

edge = +0.04
      = +4 percentage points
```

**Expected value usando el precio realmente disponible:**

para stake 1 y decimal odd \(o\),

\[
EV_c=
p_c^{model}(o_c-1)
-(1-p_c^{model})
\]

y simplificando:

\[
EV_c=p_c^{model}o_c-1.
\]

Así, con \(p=0.47\) y odds 2.30:

\[
EV=0.47\times2.30-1=0.081
\]

o expected return de 8.1% bajo el supuesto de que \(p=0.47\) está bien calibrado.

Ésta es una propiedad matemática del payoff, no evidencia de que el bet sea rentable. La incertidumbre sobre \(p\) puede ser mucho mayor que 8.1%.

**Break-even probability:**

\[
p_{BE}=\frac{1}{o}.
\]

Por tanto, el EV tiene una ventaja conceptual sobre un threshold fijo de “5 percentage points”: ajusta automáticamente por precio.

### Por qué no se debe adoptar un edge fijo de cinco puntos

No encontré evidencia que justifique un threshold universal:

```text
p_model - p_market >= 0.05
```

para apuestas 1X2.

Cinco puntos cerca de \(p=0.20\) no representan la misma incertidumbre relativa que cinco puntos cerca de \(p=0.70\), y el mismo edge produce EV diferente según el precio disponible.

El `5 pp edge` debe, por tanto, quedar clasificado como **parámetro provisional no respaldado** y no entrar al contrato de FS-003 como verdad.

### Policy HOME/AWAY/NO_BET recomendada

Para cada fixture:

```text
1. model → pH, pD, pA

2. market validation
   - >= min_valid_books
   - quotes pre-kickoff
   - no anomalías bloqueantes

3. market consensus
   → qH, qD, qA

4. best prices
   → oH_best, oA_best

5. compute
   edge_H = pH - qH
   edge_A = pA - qA

   EV_H = pH * oH_best - 1
   EV_A = pA * oA_best - 1

6. eligible side:
   EV_side >= ev_min
   AND edge_side >= edge_min
   AND not cold-start-blocked
   AND market valid

7. if neither eligible:
      NO_BET

   if one eligible:
      that side

   if both eligible:
      side with greater EV
```

`DRAW` siempre se modela porque es imprescindible para una distribución coherente y para calibración 3-way, pero **no se emite como acción** porque el contrato del brief es HOME/AWAY/NO_BET. Si el draw domina y ninguna lateral supera los criterios, la decisión correcta es `NO_BET`.

**Defaults iniciales sugeridos para shadow evaluation:**

\[
ev_{\min}=0
\]

\[
edge_{\min}=0.
\]

Esos ceros tienen una justificación teórica: eliminan candidatos con expectativa o diferencial explícitamente negativos. Pero **no deben interpretarse como umbrales suficientemente conservadores para uso económico**. Un modelo estimado contiene error.

El objetivo de acumular shadow data es aprender si hacen falta buffers como 2%, 5%, etc.

### Incertidumbre y statistical significance

Un edge individual de 4% o 5% no es una “diferencia estadísticamente significativa” por sí solo.

Sería posible estimar incertidumbre de parámetros por Hessian o bootstrap y exigir algo como:

\[
P(EV>0 \mid data) > \alpha
\]

o que un lower confidence bound del EV sea positivo. Eso sería metodológicamente más conservador, pero agrega complejidad considerable y puede provocar muy poca coverage.

**Recomendación:** no hacer confidence bounds por fixture obligatorios en FS-003. Evaluar **significancia agregada** en el walk-forward:

```text
edge buckets
→ predicted edge
→ realized outcome
→ realized P&L
→ block-bootstrap CI
```

Luego usar los resultados prospectivos para elegir `ev_min`/`edge_min`.

### Limitación de historical odds: opciones A, B y C

El estado actual es inequívoco: el brief dice que una nueva actualización reemplaza HOME/DRAW/AWAY para una combinación Match/Source/Bookmaker/Market; no existe temporal history. fileciteturn0file0

La limitación externa además es urgente: API-Football documenta en 2026 que su endpoint `/odds` sólo retiene los últimos **siete días**; las odds normalmente están disponibles de uno a catorce días antes y se actualizan aproximadamente cada tres horas. Si no se capturan localmente, no pueden recuperarse meses después. citeturn19search1turn14search0

| Alternativa | Qué permite responder | Qué NO permite responder | Evaluación |
|---|---|---|---|
| **A. Backtest predictivo histórico + value prospectivo** | Brier, log loss, calibration, accuracy, comparar DC/Poisson/Elo con históricos existentes | ROI histórico, edge histórico, closing-line behavior, thresholds económicos históricos | válida pero incompleta |
| **B. Empezar ya odds history + shadow evaluation** | todo A + dataset prospectivo limpio de prices/consensus/value/ROI/timing | no rellena el pasado perdido | **recomendada** |
| **C. Historical odds como prerequisite** | podría habilitar economic backtest retroactivo si se obtiene fuente fiable | depende de conseguir proveedor/backfill, provenance y timestamp comparables | retrasaría innecesariamente el baseline |

**Recomendación clara:** **B, combinada con A**.

El desarrollo del predictor no debe bloquearse por ausencia de historical odds. Se puede medir perfectamente si Dixon–Coles pronostica resultados mejor que Poisson/Elo usando scores históricos.

Pero el comienzo de **append-only odds capture es prácticamente prerequisite para una evaluación económica seria futura**, porque cada día que pasa sigue perdiéndose información no reconstruible desde API-Football. citeturn19search1

Si modificar el storage de odds queda fuera del boundary técnico de FS-003, debe convertirse en un micro-ticket que sea prerequisite de **shadow deployment**, no prerequisite del código del modelo.

Schema conceptual:

```text
OddsObservation
---------------
match
source
bookmaker
market
observed_at
provider_updated_at?   # cuando exista
home_odds
draw_odds
away_odds
ingested_at

UNIQUE / idempotency key:
(match, source, bookmaker, market, provider_updated_at or observed_at/value hash)
```

El latest snapshot existente puede seguir sirviendo al producto; el histórico sería append-only.

### API-Football Predictions como benchmark externo

API-Football documenta que `/predictions` devuelve winner, porcentajes HOME/DRAW/AWAY y comparaciones de attack, defence, Poisson y head-to-head; se actualiza cada hora y no está disponible en todas las ligas. citeturn19search1

Una publicación oficial anterior explica además que su prediction se calcula mediante seis algoritmos, usa forma, partidos previos y otros datos, y afirma explícitamente que **no usa bookmaker odds**. citeturn19search3

Esto lo hace interesante como benchmark porque es parcialmente independiente del mercado.

Pero presenta cuatro limitaciones:

1. el algoritmo exacto y sus parámetros no son reproducibles localmente;
2. puede cambiar sin que Finsport controle versioning;
3. tiene coverage incompleta;
4. cada captura consume quota y debe guardarse pre-kickoff para evitar leakage.

Los porcentajes históricos de “Match Winner” publicados por el proveedor para 2019/20 tampoco deben interpretarse como proof de superioridad: no sustituyen una evaluación reproducible con el mismo universo, timestamps y proper scores que Finsport. citeturn19search3

En agosto de 2026 el proveedor publica planes desde 100 requests/day en Free hasta cuotas mayores en tiers pagos, pero el plan efectivo de Finsport no está especificado en el brief y debe verificarse en configuración. citeturn19search2

**Recomendación:** API-Football Predictions es **benchmark opcional**, no input ni ground truth de FS-003. Capturarlo sólo si la quota real y el sync architecture lo permiten; la implementación del baseline no debe depender de él.

## Evaluación reproducible, anti-leakage, competiciones, datos y falsación

Una evaluación correcta debe separar cinco preguntas que suelen mezclarse:

```text
¿las probabilidades son buenas?
¿están calibradas?
¿qué outcome clasifica?
¿con qué frecuencia decide?
¿las decisiones tienen valor económico?
```

### Walk-forward reproducible

La literatura de forecast evaluation recomienda rolling origins, recalibrar los modelos y usar múltiples períodos test en lugar de un único train/test arbitrario. citeturn18search2turn18search3

La unidad de evaluación debe ser temporal.

Para cada Competition:

```text
sort fixtures by kickoff UTC

for each prediction origin T:

    training_pool =
        matches whose usable information was available strictly before T

    inner-history:
        used only to select hyperparameters
        (decay, max history, Elo K, etc.)

    fit:
        Dixon-Coles
        Poisson
        Elo-logit

    predict:
        every fixture in the next prediction batch

    freeze probabilities

    only after prediction:
        reveal actual outcomes

    advance origin

aggregate all genuine out-of-sample predictions
```

**Partidos simultáneos:** dos fixtures con el mismo kickoff no pueden usar los resultados del otro. Se deben predecir como un batch con el mismo cutoff.

**Refit frequency:** para el research evaluator, refit por matchday/batch es preferible a un único fit de temporada porque reproduce la actualización real. El costo del baseline es suficientemente pequeño.

**Nested model selection:** si se comparan decay values o windows:

```text
outer test
    no se toca para elegir parámetros

inner rolling validation
    elige parámetros

outer forecast
    mide generalización
```

No seleccionar `xi`, `edge_min` o competitions mirando el resultado del outer test.

### Métricas de probabilidades

Log loss:

\[
LL=
-\frac1N
\sum_i \log p_{i,y_i}.
\]

Penaliza especialmente asignar muy poca probabilidad al outcome que ocurre.

Multiclass Brier:

\[
BS=
\frac1N
\sum_i
\sum_{c\in\{H,D,A\}}
(p_{i,c}-y_{i,c})^2.
\]

Brier fue desarrollado como score para probabilistic forecasts, y tanto Brier como log score pertenecen a la familia de proper scoring rules: su diseño incentiva reportar probabilidades honestas en vez de probabilidades artificialmente extremas. citeturn17search5turn16search0

Además recomiendo **Ranked Probability Score (RPS)** como métrica secundaria porque H/D/A posee un orden natural. La literatura futbolística reciente continúa reportando conjuntamente Brier y RPS al comparar modelos con mercado. citeturn14search9

No hace falta declarar un único “winner metric”. Reportar al menos log loss + Brier evita que la selección dependa de peculiaridades de un score.

### Calibration

Un modelo puede tener buena ranking ability y probabilidades mal escaladas. Por eso se debe producir reliability por clase:

```text
HOME forecasts around 0.60
→ ¿HOME ocurrió aproximadamente 60%?

DRAW forecasts around 0.25
→ ¿DRAW ocurrió aproximadamente 25%?

AWAY forecasts around 0.40
→ ¿AWAY ocurrió aproximadamente 40%?
```

Murphy mostró una descomposición del probability/Brier score asociada a conceptos como reliability, resolution y uncertainty. citeturn17search3turn17search2

Output mínimo:

```text
reliability curve HOME
reliability curve DRAW
reliability curve AWAY

calibration by probability buckets
calibration by competition
calibration by season/test period
```

Un `ECE` puede reportarse, pero sólo descriptivamente: su valor depende de binning. La curva completa es más informativa.

### Outcome classification

Sólo como métrica secundaria:

\[
\hat y_i=\arg\max_c p_{i,c}
\]

y medir:

```text
accuracy
confusion matrix
class frequency
recall HOME / DRAW / AWAY
```

Accuracy no debe decidir el modelo. Un predictor que casi siempre elige HOME puede obtener una accuracy aparentemente razonable en una liga con elevada home-win base rate, mientras produce probabilidades pobres.

### Decision coverage

Definir:

\[
coverage=
\frac{\#(HOME+AWAY\ decisions)}
{\#eligible\ fixtures}.
\]

Además:

```text
NO_BET rate
HOME decision rate
AWAY decision rate
reasons for NO_BET
```

Los motivos deben ser estructurados:

```text
NO_POSITIVE_EV
INSUFFICIENT_BOOKMAKER_COVERAGE
STALE_MARKET
COLD_START
MODEL_FIT_INVALID
NO_VALID_ODDS
```

Esto permite distinguir un selector prudente de uno que simplemente falla por falta de data.

### Profitability/value

Sólo cuando exista una quote válida conocida en `decision_time`:

\[
PnL_i=
\begin{cases}
o_i-1 & \text{si side ganó}\\
-1 & \text{si side perdió}.
\end{cases}
\]

\[
ROI=
\frac{\sum_i PnL_i}
{\sum_i stake_i}.
\]

Para FS-003:

```text
stake_i = 1
```

siempre. Nada de Kelly, Martingale ni bankroll optimization; el brief los excluye. fileciteturn0file0

Registrar adicionalmente:

```text
mean predicted EV
realized ROI
ROI by predicted-edge bucket
ROI by competition
ROI by time-to-kickoff
number of bets
```

No debe calcularse ROI histórico con current/latest odds fingiendo que eran prices disponibles en ese momento.

### Incertidumbre de resultados

Para diferencias de Brier/log-loss entre dos modelos:

```text
per-match paired score difference
→ block bootstrap por matchday / semana
→ confidence interval
```

Para ROI:

```text
bets agrupados cronológicamente
→ block bootstrap
→ CI de ROI/P&L
```

El block bootstrap es preferible a tratar cada partido como completamente independiente porque partidos cercanos comparten estado de liga, equipos, shocks temporales y contexto.

### Contrato exacto anti-leakage

Para un fixture objetivo \(f\) y `prediction_time = T`:

\[
training(f,T)=
\{
m:\ kickoff_m<T
\land information_m\ available\ at\ T
\}.
\]

La condición `kickoff < T` es necesaria, pero para resultados también debe verificarse que el match estuviera finalizado y su outcome disponible.

| Riesgo | Regla FS-003 |
|---|---|
| Resultado del propio fixture | `target_match_id` debe estar explícitamente excluido |
| Partidos posteriores | `kickoff >= prediction_time` nunca entra al histórico |
| Fixture simultáneo | ningún resultado del mismo batch entra |
| Season GF/GA totals | recalcular sólo desde históricos previos |
| Standings actuales | no usar snapshot actual para retropredecir |
| League draw % | rolling, sólo partidos anteriores |
| “form last N” | seleccionar N sólo entre fixtures previos |
| final season ranking | prohibido como feature de fixtures de esa Season |
| promoted/relegated status | sólo conocimiento disponible al comienzo del período |
| odds | `observed_at <= decision_time < kickoff` |
| current latest odds para backtest | prohibido salvo prueba de timestamp pre-match exacta |
| API Predictions | sólo snapshot capturado antes de kickoff |
| hyperparameters | no elegir con outer-test |
| competition selection | criterios definidos antes de mirar profitability test |

Un anti-leakage test automatizado debería afirmar, para cada prediction:

```text
max(training_match.information_available_at) < prediction_time

target_match_id not in training_match_ids

all(odds.observed_at <= prediction_time)

all(feature_source_event_time < prediction_time)
```

Es preferible una noción de `information_available_at` a confiar únicamente en `kickoff`: un match iniciado a las 15:00 y terminado 16:50 no puede alimentar una predicción realizada 15:30 sólo porque `kickoff < T`.

### Competition suitability

No recomiendo un criterio como “>= 2 temporadas” porque no controla lo que realmente importa: cantidad de observaciones efectivas, equipos nuevos, formato, missingness ni estabilidad.

**Primera clase de competitions:** ligas domésticas con schedule regular y home/away semánticamente consistente.

**Excluir de la primera implementación:** cups, knockouts, international tournaments, neutral-venue-heavy competitions y formatos cuyo avance de fase altere radicalmente la composición del opposition set. Dixon–Coles puede modelarlos, pero home advantage, team-strength comparability y motivación competitiva dejan de ser homogéneos.

Para cada candidate Competition calcular antes de admitirla:

| Diagnóstico | Razón |
|---|---|
| completed fixtures disponibles | sample size real |
| número de equipos por período | número de parámetros |
| matches efectivos por equipo | identificabilidad/cold start |
| H/D/A distribution por temporada/período | cambio de outcome base rates |
| goals/match home/away | estabilidad del proceso |
| home advantage empírico por período | regime shifts |
| promoted/new teams | cold-start burden |
| missing canonical fixtures | sesgo del histórico |
| bookmaker coverage | aptitud para value evaluation |
| number of distinct books por fixture | calidad de consenso |
| cambio en formato | comparabilidad temporal |

Para Dixon–Coles con \(T\) equipos, hay aproximadamente \(2T\) efectos de equipo más pocos parámetros globales. La cantidad de temporadas es un proxy muy imperfecto de información relativa al número de parámetros.

Propongo como **defaults operacionales, expresamente no académicos**, para el primer screening:

```text
N_effective_training >= 10 × number_of_free_parameters

effective prior matches per non-cold-start team >= 15

outer predictive test fixtures >= 300 por Competition
o agregar competitions sin afirmar significancia league-specific

historical canonical match completeness:
idealmente 100%; cualquier missingness debe auditarse

economic shadow:
min_valid_books = 3 en el fixture evaluado
```

El factor `10×parameters`, el 15 y el 300 **son guardrails iniciales, no umbrales demostrados por papers**. Deben quedar en la categoría “defaults a calibrar”.

Una opción estadísticamente superior para ponderaciones temporales es utilizar effective sample size:

\[
N_{\text{eff}}
=
\frac{(\sum_i w_i)^2}{\sum_i w_i^2}.
\]

De ese modo, 700 partidos antiquísimos con weights casi cero no simulan tener la información de 700 partidos recientes.

**Stability across seasons** no debe ser un filtro binario arbitrario. Reportar por período:

\[
\Delta p_H,\Delta p_D,\Delta p_A,
\]

cambio en goals/match y home advantage. Si existen rupturas grandes, el decay deberá adaptarse o esa competition podrá quedar fuera.

**Competitive balance.** Para el baseline no hace falta convertirlo en feature. Sí debe reportarse como característica del dataset mediante dispersion de ratings/points o distribución de market probabilities una vez existan odds history. Su objetivo es explicar heterogeneidad de performance, no filtrar a posteriori las ligas que dieron ROI positivo.

### Matriz de datos necesaria para FS-003

“Existe” se interpreta estrictamente según el brief; cuando éste no confirma el campo concreto se marca como no confirmado.

| dato | ya existe en Finsport | puede derivarse localmente | requiere nueva ingestión | imprescindible para baseline | sólo fase posterior |
|---|---:|---:|---:|---:|---:|
| `Competition` canónica | Sí | No | No | Sí | No |
| `Season` | Sí | No | No | útil, no imprescindible para score model | No |
| `Team` | Sí | No | No | Sí | No |
| `Match.id` | Sí | No | No | Sí | No |
| home/away team | Sí, implícito en Match | No | No | Sí | No |
| kickoff | Sí | No | No | Sí | No |
| status final | Sí | No | No | Sí | No |
| home/away final score | Sí | No | No | Sí | No |
| 1X2 outcome | Sí | Sí desde score | No | para evaluación | No |
| attack parameters | No | Sí | No | Sí, derivados | No |
| defence parameters | No | Sí | No | Sí, derivados | No |
| home advantage | No persistido como dato base | Sí | No | Sí, estimado | No |
| DC `rho` | No | Sí | No | Sí, estimado | No |
| time weights | No | Sí desde kickoff | No | Sí | No |
| rolling league draw % | No necesariamente | Sí | No | No | ablation |
| Elo rating | No | Sí | No | comparator | No |
| current Match Winner odds | Sí | No | No | no para predictor; sí para decision policy | No |
| bookmaker identity | Sí | No | No | Sí para value | No |
| implied probabilities | No | Sí | No | Sí para market layer | No |
| overround | No | Sí | No | Sí para market layer | No |
| de-vig probabilities | No | Sí | No | Sí para market layer | No |
| consensus market probability | No | Sí | No | Sí para edge | No |
| best available price | No | Sí | No | Sí para EV | No |
| quote observation timestamp fiable | **No confirmado en brief** | No | posiblemente | Sí para leakage-safe value | No |
| temporal odds history | No | No | **Sí: nueva persistencia** | no para predictor; sí para economic evaluation madura | No |
| provider odds update timestamp | no confirmado | No | posiblemente capturable de API | recomendable | No |
| API-Football prediction | no indicado como persistido | No | Sí, opcional | No | benchmark opcional |
| standings | proveedor puede ofrecerlos, pero no requeridos | Sí desde matches | No | No | No |
| explicit promotion/relegation linkage | no confirmado | posiblemente | depende del modelo actual | cold-start management | No |
| bookmaker quality/sharpness weights | No | sólo tras odds history | history prerequisite | No | Sí |
| lineups/injuries | no relevantes al brief actual | no | nueva ingestión/calls | No | Sí |
| xG/event data | No confirmado | No | Sí | No | Sí |
| GPU/ML features | No | — | — | No | Sí |

La tabla revela una conclusión arquitectónica útil: **el modelo deportivo primario no necesita nueva ingestión**. La nueva necesidad de data está casi enteramente en **temporal market evaluation**, no en Dixon–Coles.

### Parámetros: qué está sustentado y qué no

| Categoría | Parámetros/decisiones |
|---|---|
| **Respaldado por literatura/estructura matemática** | Poisson para goals; attack/defence strengths; home effect; DC low-score correction; máxima verosimilitud; time weighting como mecanismo de dinámica; proper probabilistic scoring; rolling out-of-sample evaluation |
| **Defaults razonables que deben calibrarse** | power de-vig primary; median consensus; `min_valid_books=3`; `ev_min=0` para shadow; `edge_min=0` para shadow; min 15 prior team observations; `N_eff >= 10p`; 300 outer fixtures para league-level diagnostic; outlier/MAD policy |
| **Sólo decidibles empíricamente con Finsport** | valor de `rho`; decay/half-life; maximum history; Elo `K`; cold-start cutoff; de-vig ganador real; mean vs median; bookmaker weights; stale threshold; allowed overround range; edge/EV buffer; decision-time; competitions concretas; promoted-team priors; threshold final de coverage |

Esto es especialmente importante para el `5 percentage point edge`: pertenece a la tercera fila, no a la primera.

### Riesgos y falsación

FS-003 debe especificar **antes del backtest** qué evidencia obligaría a abandonar la hipótesis de valor.

Dixon–Coles debe considerarse **no justificadamente mejor que un modelo más simple** si:

```text
outer walk-forward:
DC log loss >= Poisson log loss
y/o
DC Brier >= Poisson Brier
de manera consistente

y Elo-logit iguala o supera DC
```

El baseline local debe considerarse **sin evidencia incremental respecto del mercado** si, una vez acumulado market history:

```text
market consensus
tiene log loss/Brier <= modelo

AND

model-market edge
no muestra calibration/resolution

AND/OR

positive predicted edge
no se traduce en mejor realized return
```

Una prueba especialmente informativa en una fase posterior es construir un blend en validation:

\[
p^{blend}_c
\propto
(p^{market}_c)^{1-w}
(p^{model}_c)^w
\]

y estimar \(w\). Si repetidamente:

\[
w\approx0
\]

y el outer test no mejora al mercado, el resultado práctico es que el histórico local no está añadiendo información útil al consensus.

El modelo también queda falsado como estrategia de value si:

```text
higher predicted edge
does not correspond to higher realized edge/returns

ROI remains <= 0
with confidence interval inconsistent with economically useful performance

performance disappears outside one competition/season

calibration shifts badly over time

apparent profit exists only under one arbitrary de-vig method

profit requires stale or unavailable prices

removing a handful of outlier bets eliminates the result
```

La publicación de 2026 donde market average supera a varios modelos dinámicos en numerosas ventanas hace este riesgo especialmente real, no meramente teórico. citeturn14search9

También hay un riesgo de investigación importante: probar muchas competitions, thresholds, windows, decay values y filtering rules y publicar únicamente la mejor combinación crea multiple-testing/selection bias. El grid inicial debe ser pequeño, los criterios deben congelarse antes del outer test y las variantes exploratorias deben estar etiquetadas como tales.

## Decisiones recomendadas para FS-003

El pipeline exacto recomendado es:

```text
historical canonical matches
        ↓
leakage-safe chronological training set
        ↓
Dixon–Coles fit
[+ Poisson and Elo-logit comparators]
        ↓
P(HOME), P(DRAW), P(AWAY)
        ↓
current pre-kickoff bookmaker quotes
        ↓
per-book implied probabilities
        ↓
per-book overround + de-vig
        ↓
quote validation / dedup / freshness
        ↓
multi-bookmaker market consensus
        +
best available HOME/AWAY prices
        ↓
edge + EV computation
        ↓
eligibility / cold-start / market-quality checks
        ↓
HOME | AWAY | NO_BET
        ↓
walk-forward probability evaluation
        +
prospective shadow value evaluation
```

Los **17 outputs exigidos por el brief** quedan cerrados individualmente así:

| Output del brief | Resolución propuesta |
|---|---|
| **1. Técnica baseline primaria** | Dixon–Coles por Competition, attack/defence + global home advantage + low-score `rho` + time decay |
| **2. Máximo 1–2 comparadores** | Independent Poisson y Elo + ordered logit |
| **3. Inputs exactos** | Competition, Match ID, kickoff, home team, away team, final regulation score/status para training; bookmaker 1X2 sólo después del predictor para value |
| **4. Ventana histórica** | historia de la misma Competition cruzando Seasons, exponencialmente decaída; cap/half-life elegidos por inner walk-forward, no regla fija de temporadas |
| **5. Inicio de temporada** | no reset; carry-over decaído para equipos existentes; league-average initialization + cold-start para nuevos/promovidos |
| **6. Home advantage** | un parámetro global por Competition sobre log-intensity local; no team-specific en v1 |
| **7. Múltiples bookmakers** | validar y de-vig cada book; deduplicar; robust consensus; best price separado |
| **8. Overround normalization** | Power como primary, multiplicative como sensitivity comparator |
| **9. HOME/AWAY/NO_BET** | elegir H/A de mayor EV entre candidates que superan market validity + `EV_min` + `edge_min`; de lo contrario NO_BET |
| **10. Métricas** | log loss, multiclass Brier, calibration/reliability, RPS secundario, accuracy/confusion secundarios, coverage, edge, flat-unit P&L/ROI |
| **11. Validation/backtest** | nested chronological rolling-origin/walk-forward por Competition, múltiples test origins |
| **12. Anti-leakage** | todo feature/result/odd/hyperparameter debe existir y haberse fijado antes del prediction timestamp; explicit assertions |
| **13. Competition suitability** | domestic regular leagues primero; seleccionar por effective sample size, per-team history, completeness, stability, promotion burden y odds coverage; cups fuera |
| **14. Temporal odds history prerequisite** | no prerequisite del predictor; **sí iniciar append-only capture ahora** para shadow/economic evaluation; opción B + A |
| **15. Heurística histórica** | conservar NO_BET; mantener balance de odds, market draw probability, rolling draw rate, extreme-odds regime y top-k sólo como ablations; descartar fórmula/thresholds legacy |
| **16. Fuera de FS-003** | staking, Kelly/Martingale, real betting, scheduler/notifications, arbitrage, GPU/black-box ML, bivariate/dynamic Bayesian models, injuries/xG, sharp-book hardcoding |
| **17. Risks/unknowns** | no incremental value vs market; DC no superior a simpler baselines; cold-start; league regime shifts; missing/stale odds; bookmaker duplication; threshold overfitting; insufficient history |

**Scope exacto del primer ticket de implementación.**

Debe entrar:

```text
Leakage-safe historical match dataset builder

Dixon-Coles model:
- attack/defence
- home advantage
- rho
- time decay
- MLE
- score matrix
- H/D/A probabilities
- convergence/error diagnostics

Independent Poisson comparator

Elo + ordered-logit comparator

Chronological walk-forward evaluator:
- log loss
- Brier
- RPS
- calibration data
- accuracy/confusion
- per-competition/per-period outputs

Market layer:
- 1/odds
- overround
- power de-vig
- multiplicative sensitivity
- quote validation
- bookmaker deduplication hook
- consensus
- best available price

Decision layer:
- edge
- EV
- HOME/AWAY/NO_BET
- explicit NO_BET reason
- configurable eligibility thresholds

Cold-start handling

Configuration with explicit parameter provenance

Tests for anti-leakage and probability invariants
```

Además, **temporal odds persistence debe comenzar antes o junto al shadow rollout de FS-003**. Si tocar esa persistencia hace que el ticket sea demasiado transversal, conviene separarla como prerequisite técnico pequeño, pero no postergarla hasta después de validar el predictor: API-Football borra la posibilidad de recuperación más allá de siete días. citeturn19search1

No debe entrar:

```text
real bet placement
stake sizing
bankroll optimization
Kelly
Martingale / recovery
arbitrage
notifications
scheduler redesign salvo lo mínimo para odds capture
API-Football Predictions como dependencia
xG / injuries / lineups
bivariate Poisson
Bayesian state-space
MCMC
XGBoost
neural networks
GPU
large ensembles
bookmaker "sharp" hardcodes
automatic production threshold optimization
```

Dixon–Coles tampoco debe “graduarse” automáticamente a producción sólo porque sea el baseline elegido. El resultado de FS-003 debe poder ser perfectamente:

```text
DC ≈ Poisson
market > all local models
economic value not yet demonstrated
```

Eso sería un resultado de investigación exitoso porque evita construir producto sobre una señal inexistente.

La tabla de decisión solicitada es:

| decisión | recomendación | evidencia | confianza | requiere validación con datos Finsport |
|---|---|---|---|---|
| Baseline primario | **Dixon–Coles** | extensión parsimoniosa de Poisson con low-score correction y dinámica; paper original + uso continuado en literatura citeturn15search1turn18search7 | Alta como baseline, no como supuesto winner | **Sí** |
| Comparator simple | Independent Poisson | Maher encuentra buen ajuste general; mismo backbone que DC citeturn15search0 | Alta | Sí |
| Comparator rating | Elo + ordered logit | evaluado específicamente para outcome prediction en fútbol citeturn16search1turn16search5 | Alta | Sí |
| Bivariate Poisson ahora | No | puede modelar dependencia más general pero suma complejidad citeturn15search9turn18search4 | Alta | No para v1 |
| Dynamic Bayesian/GPU/AI | Fuera de FS-003 | existen variantes dinámicas más complejas; no hay evidencia de necesidad para establecer baseline citeturn18search0turn18search7 | Alta | No |
| Reset por Season | No | recencia debe modelarse temporalmente, no mediante boundary administrativo | Alta | Sí, evaluar carry-over |
| Historical window | Time-decayed cross-season history | compatible con dinámica DC; longitud/decay son data-dependent | Alta en diseño | **Sí** |
| Promoted teams | league-average initialization + cold-start flag | extrapolar parámetros entre divisiones sin calibración introduce supuestos nuevos | Media-alta | **Sí** |
| Home advantage | global por Competition | estructura estándar de score models | Alta | Sí, estimar valor |
| De-vig primario | Power | evidencia empírica favorable frente a multiplicative en datasets deportivos citeturn16search3 | Media-alta | **Sí** |
| De-vig comparator | Multiplicative | baseline simple y transparente; known limitations citeturn16search6 | Alta como comparator | Sí |
| Market consensus | median fair probability per outcome + renormalización | robustez matemática ante outlier; no paper demuestra universal superiority | Media | **Sí** |
| Mean consensus | sensitivity experiment | suma uno naturalmente y usa toda la información | Alta como comparator | Sí |
| Bookmaker weights | No inicialmente | diferencias entre casas existen, pero requieren historial para estimar calidad citeturn17search0 | Alta | **Sí, posterior** |
| Sharp/recreational labels | No hardcodear | heterogeneidad empírica no equivale a clasificación universal | Alta | Sí, posterior |
| Best available odds | usar sólo como price para EV | múltiples books y best prices tienen valor económico/informativo citeturn17search1 | Alta | Sí |
| Inkabet | una quote al mismo nivel de canonical bookmaker, si pasa validación | arquitectura del brief distingue source de bookmaker fileciteturn0file0 | Alta conceptualmente | **Sí, mapping DB** |
| Minimum bookmaker coverage | default provisional = 3 | con tres la mediana resiste un outlier; no existe threshold universal | Media | **Sí** |
| Legacy HOME/AWAY similarity | ablation | representa market competitive balance | Media | Sí |
| Legacy draw odds 2.8–4.2 | descartar rango; conservar de-vig `p_draw` | raw odds incluyen vig y método de normalización importa citeturn16search6 | Alta | Sí |
| League draw percentage | rolling diagnostic/ablation | base-rate plausible; debe evitar leakage | Alta | Sí |
| Extreme odds exclusion | ablation, no hard threshold | favorite-longshot effects no son universales y dependen de de-vig citeturn16search3turn16search6 | Alta | Sí |
| Near-kickoff legacy window | no conservar 5–65m; estudiar después con temporal history | API odds cambian durante pre-match citeturn19search1 | Alta | **Sí** |
| Ranking few candidates | policy/coverage ablation | cambia selectividad, no el forecast | Alta | Sí |
| NO_BET | salida normal y central | decisión puede separarse de forecasting | Alta | Sí para thresholds |
| Decision criterion | EV + edge + market validity | EV representa payoff real; edge mide divergencia de probabilidad | Alta en estructura | **Sí para thresholds** |
| `5 pp edge` | **no adoptar como constante** | no se encontró fundamento universal | Alta | **Sí** |
| `EV_min=0`, `edge_min=0` | shadow defaults, no production truth | corresponden a frontera teórica de no-negative-value | Media-alta | **Sí** |
| Accuracy | secundaria | no evalúa adecuadamente probabilidades | Alta | No |
| Brier/log loss | primarias | proper probabilistic scores citeturn16search0turn17search5 | Muy alta | No |
| Calibration curves | obligatorias | reliability es componente central de forecast quality citeturn17search3 | Muy alta | No |
| Walk-forward | obligatorio | rolling origins mejoran validez de out-of-sample evaluation citeturn18search2turn18search3 | Muy alta | No |
| Economic historical backtest ahora | No inventarlo | Finsport latest-only y API tiene 7-day retention fileciteturn0file0 citeturn19search1 | Muy alta | No |
| Odds history | **empezar append-only capture ahora** | history perdido no puede recuperarse desde API más allá de siete días citeturn19search1 | Muy alta | Sí, esquema técnico |
| Historical odds prerequisite del predictor | No | H/D/A predictive quality puede medirse sólo con scores históricos | Muy alta | No |
| API-Football Predictions | benchmark externo opcional | 3-way probabilities, hourly updates, proprietary multi-algorithm approach, no bookmaker odds según proveedor citeturn19search1turn19search3 | Alta | Sí, quota/coverage |
| Competitions iniciales | domestic regular leagues con suficiente effective history y data completeness | reduce heterogeneidad estructural; thresholds deben medirse | Alta | **Sí** |
| Market como ground truth | No | odds son forecasts fuertes, no verdad; quality varía entre books/leagues citeturn17search0 | Muy alta | No |
| Criterio de falsación | modelo debe ganar OOS o demostrar señal incremental vs market | literatura reciente muestra market puede superar modelos de goals citeturn14search9 | Muy alta | **Sí** |

## Preguntas aún no resolubles sin consultar el repositorio/DB Finsport

El brief resuelve la estrategia general, pero hay decisiones de implementación que no pueden inferirse responsablemente sin inspeccionar schema, sync code y cobertura real. El preflight técnico posterior debería resolver explícitamente las siguientes cuestiones antes de redactar la versión ejecutable de `FS-003.md`.

| Área | Pregunta que debe resolver el preflight | Por qué bloquea o cambia implementación |
|---|---|---|
| Match timestamps | ¿`Match.kickoff` está almacenado en UTC? ¿qué tipo y timezone semantics tiene? | todas las guarantees anti-leakage dependen de comparaciones temporales correctas |
| Match completion | ¿qué statuses cuentan como final normal: `FT`, `AET`, `PEN`, awarded, cancelled, abandoned? | Dixon–Coles debe saber qué score representa regulación comparable |
| Score semantics | ¿los scores guardados para cups pueden incluir extra time/penalties? | refuerza exclusión de cups o requiere elegir score de 90 minutos |
| Result availability | ¿se conserva cuándo el resultado fue observado/confirmado? | permite un `information_available_at` riguroso |
| Fixture history | ¿cuántos matches completos existen por Competition y Season? | determina qué leagues califican |
| Missing fixtures | ¿hay gaps históricos de partidos que no fueron sincronizados? | un historial incompleto sesga ataque/defensa |
| Team identity | ¿un Team conserva el mismo canonical ID a través de Seasons? | imprescindible para cross-season carry-over |
| Competition membership | dado que no existe `SeasonSourceRef`, ¿cómo se representa que un Team participa en una Competition en una temporada concreta? | promoted/relegated handling |
| Promotion | ¿puede derivarse qué equipos son promoted/new al inicio de una Season sin mirar el final futuro? | cold-start classification |
| Competition format | ¿existe metadata suficiente para distinguir league/cup, regular season/playoffs/groups? | competition suitability |
| Neutral venues | ¿Finsport conoce neutral venue? | home advantage sería incorrecto en esos fixtures |
| Odds timestamp | ¿`OddsSnapshot` tiene `created_at`, `updated_at`, provider update time u otro momento fiable de observación? | crítico para staleness y leakage |
| Odds overwrite | al actualizar latest-value, ¿`updated_at` refleja ingestión o timestamp del proveedor? | determina si current records pueden utilizarse prospectivamente |
| API-Football odds payload | ¿se persiste el `update`/timestamp que API-Football devuelve por bookmaker/fixture? | debería ser parte de append-only history |
| Inkabet timestamps | ¿Inkabet tiene timestamp de quote/origin o sólo momento de scrape? | freshness comparability |
| Bookmaker identity | ¿`Bookmaker` es realmente canónico entre Sources? | necesario para no duplicar Inkabet/API-Football |
| Duplicate books | ¿existen nombres/IDs distintos que representan la misma casa? | sesga consensus |
| Market semantics | ¿`OddsMarket` garantiza que todas las rows usadas son pre-match Match Winner 1X2? | no se deben mezclar mercados parecidos |
| Decimal odds | ¿todos los providers normalizan a decimal antes de persistence? | de-vig y EV lo requieren |
| Suspended/invalid quotes | ¿se guardan flags de suspension/blocked/inactive? | market validation |
| Current book count | ¿cuál es la distribución `#valid bookmakers per future Match`? | verifica si `min_valid_books=3` es operacional |
| Overround distribution | ¿qué margins reales aparecen por bookmaker/source? | permite detectar corrupt/stale data y escoger quality bounds |
| Inkabet overlap | ¿qué bookmaker representa Inkabet y aparece también vía API-Football? | decide deduplication |
| Legacy factors | ¿`local_factor`, `visitor_factor` y `draw_factor` eran exactamente odds decimales o transforms? | necesario para reproducir honestamente legacy comparator |
| Legacy sample | ¿BetTable/BetRow conserva historical decisions y outcomes suficientes? | permite evaluar la heurística sin reinventarla |
| Decision storage | ¿existe entidad/campo para persistir model probability, market probability, EV y NO_BET reason? | trazabilidad de FS-003 |
| Model versioning | ¿hay infraestructura para persistir `model_version`, parameter config y prediction timestamp? | reproducibilidad |
| Runtime dependencies | ¿el stack actual permite SciPy/statsmodels/optimizer equivalente? | define implementación concreta de MLE y ordered logit |
| Numerical conventions | ¿el proyecto tiene librería/estándar para decimal arithmetic en odds? | EV y quote comparison |
| API quota | ¿qué plan/API-Football daily quota usa actualmente Finsport y cuánto consume FS-002? | decide si Predictions benchmark y mayor polling son viables |
| Sync frequency | ¿cada cuánto se refrescan hoy odds antes del kickoff? | define snapshots reales que puede capturar shadow |
| Scheduler | ¿existe ya un sync recurrente del que pueda colgar append-only history sin rediseñar scheduling? | boundary del ticket |
| Data retention | ¿hay políticas de pruning para snapshots? | odds history debe ser verdaderamente temporal |
| Testing | ¿existe fixture factory capaz de crear histories cronológicos reproducibles? | necesario para unit/integration anti-leakage |
| Competition volume | ¿qué competitions cumplen hoy los criterios de effective sample size y completeness? | no se pueden nombrar las primeras ligas sin DB |
| Outcome distribution | ¿qué H/D/A rates reales muestran esas competitions por período? | suitability y calibration baseline |
| Season stability | ¿cuánto cambian goals, home advantage y draw rate entre períodos? | decay y eligibility |
| Provider coverage | ¿qué leagues tienen `coverage.predictions` y bookmaker odds suficientes? | API Predictions benchmark y shadow value |
| Historical provider reach | ¿hay alguna fuente ya sincronizada o backup que contenga odds anteriores no representadas en `OddsSnapshot`? | podría recuperar parte del pasado sin nuevo proveedor |
| Deployment semantics | ¿`HOME/AWAY/NO_BET` será sólo research output, una recommendation persistida o alimentará otra feature? | determina contratos y safety boundaries |

El preflight no debería decidir nuevamente la estrategia estadística desde cero. Su función es transformar estas decisiones en contratos técnicos verificables y, sobre todo, medir los parámetros que **sólo los datos Finsport pueden contestar**: competitions viables, effective sample sizes, calidad temporal de odds, overlap de bookmakers, cold starts, quota y distribución de coverage.

La señal de éxito para FS-003 no debe ser “se implementó Dixon–Coles”. Debe ser que, al terminar el ticket, Finsport pueda responder reproduciblemente:

```text
¿qué sabía el modelo antes de cada kickoff?

¿qué P(HOME/DRAW/AWAY) produjo?

¿fue mejor que Poisson y Elo-logit?

¿estuvo calibrado?

¿qué decía un mercado multi-bookmaker correctamente normalizado?

¿existía realmente un precio con EV positivo en decision_time?

¿por qué decidió HOME, AWAY o NO_BET?

¿con qué coverage?

¿y qué evidencia estadística existe de que esa señal agrega algo
que el mercado no sabía ya?
```

Ése es el contrato técnico que convierte FS-003 de una heurística de selección en un experimento predictivo falsable y una base defendible para decisiones posteriores.
