# FS-003 — Investigación focalizada sobre selección de empates, estrategia legacy y action space HOME / DRAW / AWAY / NO_BET

## Alcance, conclusión central y clasificación de la evidencia

Esta investigación toma como contrato técnico el brief de FS-003: Finsport dispone de histórico canónico de partidos y resultados, múltiples cuotas 1X2 actuales provenientes de API-Football e Inkabet, pero `OddsSnapshot` conserva únicamente el último valor por `Match / Source / Bookmaker / Market`; por tanto, hoy no existe una serie temporal que permita reconstruir de forma fiable qué cuota estaba disponible en un instante histórico previo al kickoff. El propio brief también establece que la estrategia antigua debe tratarse como **evidencia histórica**, no como una regla aprobada. fileciteturn0file0

El contrato de producto de esta investigación cambia además un punto importante respecto del brief original: el espacio de acciones que debe investigarse pasa a ser:

\[
\boxed{\text{HOME / DRAW / AWAY / NO\_BET}}
\]

Eso obliga a separar dos problemas que a menudo se mezclan incorrectamente:

\[
\textbf{forecasting}:\quad
P(H),P(D),P(A)
\]

frente a

\[
\textbf{decision/value}:\quad
\text{elegir una acción solamente si su precio produce EV suficiente.}
\]

Una predicción probabilística puede, por ejemplo, ser:

\[
P(H)=0.45,\qquad P(D)=0.31,\qquad P(A)=0.24
\]

y aun así la acción óptima de betting ser `DRAW` si la cuota ejecutable del empate es suficientemente alta. La clase con mayor probabilidad y la apuesta con mayor valor esperado son conceptos distintos.

La conclusión principal de la revisión es la siguiente:

> **No encontré una técnica publicada que sea equivalente al algoritmo `R45-refund-stop` como combinación de `|home_odd-away_odd|`, banda fija de draw odds, mínimo de draw-rate de liga, exclusión por cuota del favorito, top-1 y ventana temporal.**

Sí existen, en cambio, **fundamentos estadísticos publicados para varias intuiciones individuales**: la probabilidad de empate tiende a aumentar cuando las fuerzas de los equipos son similares; hay modelos específicamente diseñados para corregir la probabilidad de resultados empatados; existen sesgos favorite–longshot y de outcome en algunos mercados; las tasas de empate difieren entre competiciones; y el rechazo/abstención es un problema formalmente estudiado en teoría de decisión y selective prediction. Pero las constantes concretas y la suma de reglas de R45 no reciben validación por asociación con esos conceptos. Maher mostró que la estructura de fortalezas ofensivas y defensivas bajo Poisson describe razonablemente los scores; Dixon–Coles introdujo una corrección explícita de scores bajos y dinámica temporal; Karlis–Ntzoufras mostró que la dependencia bivariada y la inflación diagonal pueden mejorar específicamente la predicción de empates; Davidson formuló un modelo de comparaciones con ties cuya probabilidad de empate depende estructuralmente de la similitud de fortalezas. citeturn17view0turn17view1turn17view2turn20search2

La literatura de mercados tampoco permite convertir un sesgo histórico en ley universal. Cain, Law y Peel encontraron favorite–longshot bias en fútbol británico; Deschamps y Gergaud reportaron además un patrón distinto en las draw odds y mejores retornos relativos en empates en su muestra; pero un estudio posterior de más de 16.000 partidos ingleses y 51 bookmakers encontró que las cuotas agregadas eran generalmente no sesgadas por tipo de resultado o favorite–longshot, aunque cada bookmaker individual no incorporaba toda la información disponible en sus competidores. En 11 ligas europeas, Angelini y De Angelis también encontraron heterogeneidad: utilizando mejores cuotas, algunos mercados mostraban oportunidades y otros no. citeturn21view3turn21view2turn18search0turn18search1

Una publicación particularmente relevante y muy reciente, Lezana 2026, reporta oportunidades anormales concentradas especialmente en draws y away wins usando datos de Premier League y un enfoque con procesos de Markov y ordered logit, con verificaciones adicionales en otras grandes ligas. Es evidencia de que un residual específico del empate **puede** existir; por ser un resultado muy reciente y no una regularidad largamente replicada, no debería utilizarse para aprobar ninguna constante de R45 ni para asumir que actualmente Finsport puede explotar el mismo fenómeno. citeturn21view4

Para evitar ambigüedad, en el resto del informe uso esta taxonomía:

| clasificación | significado para FS-003 |
|---|---|
| **Técnica publicada equivalente** | Hay un método formal publicado que hace esencialmente la misma operación y puede estudiarse como método reconocido. |
| **Concepto estadístico relacionado** | La intuición tiene un fundamento formal, pero la formulación legacy no es la técnica publicada. |
| **Intuición plausible** | Existe un mecanismo razonable, pero no evidencia suficiente para convertirlo en feature/regla sin validación Finsport. |
| **Regla legacy sin respaldo** | No se encontró justificación para la forma o constante concreta; sólo debe preservarse para reproducir el comportamiento histórico. |

Aplicando esa taxonomía al algoritmo completo:

| componente legacy | clasificación | veredicto preliminar |
|---|---|---|
| HOME/AWAY odds parecidas | **concepto estadístico relacionado** | Conservar la idea, pero reemplazar diferencia de odds por una medida de paridad probabilística. |
| `draw_odd` entre `2.8` y `4.2` | **intuición plausible / regla legacy** | No conservar como gate productivo; sí reproducir en `LEGACY_R45`. |
| draw-rate de liga ≥ 25% | **concepto relacionado + threshold legacy** | Probar draw-rate rolling/shrunk como feature; descartar el 25% como universal. |
| rechazar favorito con odd < 1.5 | **concepto relacionado + threshold legacy** | Probar régimen de desequilibrio como ablation, no hard gate. |
| rankear y tomar sólo uno | **selectividad relacionada; top-1 legacy** | No conservar top-1 como regla estadística. |
| sólo cerca del kickoff | **concepto de price discovery relacionado** | Conservar “usar snapshot pre-kickoff definido”; no conservar 5–65 min por autoridad. |
| no apostar si nada califica | **técnica equivalente en espíritu a reject option** | Conservar como principio central mediante `NO_BET`. |
| siempre apostar DRAW al seleccionado | **regla legacy** | Sólo comparator; incompatible con el nuevo action space como política general. |

La recomendación final de esta investigación será por ello conservar `LEGACY_R45` como **comparator explícito**, no como baseline productivo; conservar algunas de sus intuiciones en una variante modernizada y falsable; y usar un modelo probabilístico independiente del mercado —preferentemente Dixon–Coles con Independent Poisson como ablation natural— para separar señal futbolística de señal ya incorporada en las cuotas.

## Paridad, probabilidad de empate, draw priors y regímenes de mercado

La primera intuición de R45 —“equipos con precios HOME/AWAY parecidos son mejores candidatos a DRAW”— es la parte con fundamento matemático más claro, aunque la formulación mediante diferencia de cuotas crudas es deficiente.

Bajo el Independent Poisson clásico, sean los goles locales y visitantes:

\[
X\sim\operatorname{Poisson}(\lambda_H),
\qquad
Y\sim\operatorname{Poisson}(\lambda_A),
\]

independientes. Maher formalizó precisamente esta familia usando parámetros de ataque y defensa de los equipos y encontró que un modelo Poisson independiente constituía una descripción razonablemente precisa del score, aunque con pequeñas discrepancias sistemáticas. citeturn17view0

La probabilidad de empate es:

\[
P(D)=P(X=Y)
 =\sum_{k=0}^{\infty}
     P(X=k)P(Y=k)
\]

\[
=
e^{-(\lambda_H+\lambda_A)}
\sum_{k=0}^{\infty}
\frac{(\lambda_H\lambda_A)^k}{(k!)^2}.
\]

Equivalentemente:

\[
P(D)=
e^{-(\lambda_H+\lambda_A)}
I_0\!\left(2\sqrt{\lambda_H\lambda_A}\right),
\]

donde \(I_0\) es la función de Bessel modificada de primera especie.

Ahora fijemos la intensidad total de goles:

\[
s=\lambda_H+\lambda_A.
\]

El producto \(\lambda_H\lambda_A\) es máximo cuando:

\[
\lambda_H=\lambda_A=s/2.
\]

Como \(I_0(z)\) es creciente para \(z>0\), **para una intensidad total de goles fija, la probabilidad de empate alcanza su máximo cuando las tasas esperadas de gol son iguales**.

Eso ofrece un fundamento formal a la intuición “paridad → mayor probabilidad de empate”. Pero la condición **“para intensidad total fija”** es esencial. Dos equipos equilibrados en un entorno de muchos goles no tienen necesariamente la misma probabilidad de draw que dos equipos igualmente equilibrados en un entorno de pocos goles. La diferencia de fuerzas no es por sí sola suficiente; la escala de scoring importa.

El modelo Davidson ofrece una confirmación conceptual independiente desde la teoría de paired comparisons. En su extensión de Bradley–Terry para permitir ties, las probabilidades son proporcionales a:

\[
\pi_H,\qquad
\nu\sqrt{\pi_H\pi_A},\qquad
\pi_A,
\]

para HOME, DRAW y AWAY respectivamente. Por tanto:

\[
P(D)=
\frac{\nu\sqrt{\pi_H\pi_A}}
{\pi_H+\pi_A+\nu\sqrt{\pi_H\pi_A}}.
\]

La contribución del término de empate depende de la media geométrica de las fortalezas y es relativamente mayor cuando ambas están próximas; Davidson introdujo formalmente este modelo de ties en 1970. citeturn20search2turn20search0

**Evidencia:** hay entonces al menos dos familias formales, score-based Poisson y paired-comparison Davidson, que vinculan paridad de fuerzas con mayor propensión al empate. citeturn17view0turn20search2

**Inferencia para Finsport:** esto respalda estudiar una variable de “paridad”, pero no respalda:

\[
|\text{home odd}-\text{away odd}|\le 3.
\]

Las cuotas decimales son una transformación no lineal de probabilidades. Por ejemplo, pasar de cuota 2 a 3 no representa el mismo cambio probabilístico que pasar de 6 a 7. El espacio natural para medir paridad de mercado es el de probabilidades, idealmente después de retirar el margen.

Para cada bookmaker \(b\):

\[
q_{b,H}=\frac{1}{O_{b,H}},
\quad
q_{b,D}=\frac{1}{O_{b,D}},
\quad
q_{b,A}=\frac{1}{O_{b,A}},
\]

con overround:

\[
R_b=q_{b,H}+q_{b,D}+q_{b,A}-1.
\]

Con de-vig multiplicativo:

\[
p_{b,i}^{M}
=
\frac{q_{b,i}}
{q_{b,H}+q_{b,D}+q_{b,A}}.
\]

El candidato moderno de paridad sería entonces:

\[
\Delta_{HA}=|p_H^M-p_A^M|.
\]

No `abs(home_odd-away_odd)`.

### ¿Aporta \(|p_H-p_A|\) algo después de controlar por \(p_D\)?

Esta es una pregunta especialmente importante porque puede desmontar o reivindicar la principal intuición legacy.

Como:

\[
p_H+p_D+p_A=1,
\]

si definimos:

\[
\delta=p_H-p_A,
\]

entonces:

\[
p_H=\frac{1-p_D+\delta}{2},
\qquad
p_A=\frac{1-p_D-\delta}{2}.
\]

Y usando sólo la magnitud de la asimetría:

\[
\max(p_H,p_A)
=
\frac{1-p_D+|\delta|}{2}.
\]

Por tanto, **\(p_D\) y \(|p_H-p_A|\) contienen información distinta sobre la forma del vector 1X2**: \(p_D\) indica cuánto mass asigna el mercado al empate; \(|p_H-p_A|\) indica cuán desequilibradas están las dos alternativas de victoria.

Pero hay una distinción crítica.

Si el mercado fuera condicionalmente calibrado:

\[
P(Y=D\mid p_H^M,p_D^M,p_A^M)=p_D^M,
\]

entonces, una vez conocido \(p_D^M\), ninguna transformación adicional del mismo vector debería mejorar sistemáticamente la predicción del draw. Que \(|p_H-p_A|\) sí mejore la estimación implicaría una de estas posibilidades:

1. el mercado está mal calibrado de forma estructurada;
2. el método de de-vig introduce distorsión;
3. el feature captura algún régimen no reflejado correctamente por \(p_D\);
4. la mejora observada es sampling noise/overfit.

La literatura revisada contiene evidencia de sesgos de odds y de resultados específicos en algunas muestras, pero **no encontré evidencia robusta y general que establezca que \(|p_H-p_A|\) mejora persistentemente la predicción de draws una vez controlado el propio \(p_D\) de mercado**. Los estudios modernos de eficiencia incluso encuentran resultados contradictorios entre países, periodos y bookmakers. citeturn18search0turn18search1turn21view2

La forma correcta de convertir esta cuestión en una prueba falsable es un modelo nested:

\[
M_0:
\quad
\operatorname{logit}P(D)
=
\alpha+\beta\operatorname{logit}(p_D^M)
\]

frente a

\[
M_1:
\quad
\operatorname{logit}P(D)
=
\alpha+
\beta\operatorname{logit}(p_D^M)
+
\gamma|p_H^M-p_A^M|.
\]

Bajo una hipótesis de mercado perfectamente calibrado:

\[
\alpha=0,\qquad\beta=1,\qquad\gamma=0.
\]

La pregunta útil para FS-003 no es primordialmente “¿\(\gamma\) resulta significativo in-sample?”, sino:

\[
\text{¿reduce }M_1
\text{ el log loss/Brier de DRAW fuera de muestra?}
\]

y, por separado:

\[
\text{¿produce decisiones de betting con mejor retorno fuera de muestra?}
\]

**Recomendación:** `abs(de_vig_p_home - de_vig_p_away)` merece sobrevivir únicamente como **feature/ablation experiment**, no como filtro aprobado.

### Draw odds de 2.8 a 4.2

La banda histórica:

\[
2.8\le O_D\le4.2
\]

corresponde, antes de quitar el margen, aproximadamente a:

\[
23.8\%\le\frac1{O_D}\le35.7\%.
\]

Eso significa que R45 seleccionaba una zona relativamente intermedia de draw probability/price; no buscaba ni draws considerados extremadamente improbables ni precios de empate excepcionalmente cortos.

**Plausibilidad:** sí. Es razonable que una estrategia legacy pudiera haber encontrado empíricamente una región donde existía mejor combinación de frecuencia y payout.

**Evidencia universal:** no. La cuota cruda mezcla probabilidad, margen del bookmaker y posibles sesgos de pricing. Štrumbelj mostró que distintas transformaciones de odds a probabilidades pueden producir resultados materialmente distintos y que la normalización básica puede ser sesgada. Clarke, Kovalchik e Ingram compararon normalización, Shin, additive y power, señalando explícitamente que la normalización proporcional no corrige favorite–longshot bias y obteniendo mejores resultados con el método power en sus datasets. citeturn21view1turn21view0

La banda `2.8–4.2` debe por tanto permanecer **sólo dentro de `LEGACY_R45`**. Una versión moderna no debería decir “DRAW si odd está en esta zona”; debería estimar \(P(D)\), observar el precio actual y calcular EV.

### Draw percentage histórico por liga

La idea “algunas ligas empatan más que otras” tiene plausibilidad y soporte empírico. Yildizparlak estudió más de 10.000 encuentros de siete ligas europeas y encontró diferencias entre ligas en parámetros relevantes de modelos de outcomes con draws, incluyendo home bias, retorno al talento y desigualdad competitiva. Eso respalda modelar heterogeneidad por competición, pero no demuestra que un simple threshold de draw-rate histórico produzca alpha adicional frente a mercado y modelos de equipo. citeturn16search15

Hay además un problema estadístico importante con la regla:

\[
\widehat r_{\text{league}}
=
\frac{\text{draws acumulados}}{\text{matches acumulados}}.
\]

Al principio de temporada tiene alta varianza. Y si para predecir un fixture de marzo se utiliza el porcentaje **final** de la temporada, se produce leakage porque ese agregado incluye partidos disputados después.

La versión correcta debe estar indexada temporalmente:

\[
\widehat r_{L,t}
=
\frac{
\sum_{m:\,t_m<t}\mathbf 1(y_m=D)
}{
N_{L,t}
}.
\]

Aún mejor, puede usarse shrinkage:

\[
\widehat r_{L,t}^{\,\text{shrunk}}
=
\frac{D_{L,t}+a}
{N_{L,t}+a+b},
\]

donde \(a,b\) provienen exclusivamente de información previa —por ejemplo, temporadas anteriores dentro del training fold—. Así se evita que cinco fixtures iniciales determinen una supuesta “liga de draws”.

**Evidencia:** la propensión a resultados y el competitive balance pueden variar entre ligas. citeturn16search15

**Inferencia:** una estimación rolling/shrunk puede funcionar como prior/context feature.

**No demostrado:** que un umbral de 25% sea óptimo, estable o aporte algo incremental una vez incluidos \(p_D^{market}\), fortalezas de equipos y home advantage.

**Recomendación:** eliminar el hard gate `draw_rate >= 25%` del baseline productivo. Preservar `rolling_league_draw_rate` como feature de la variante modernizada y hacer una ablation explícita.

### Favorite/longshot y la exclusión de favoritos fuertes

El filtro:

\[
O_H<1.5
\quad\text{o}\quad
O_A<1.5
\Rightarrow\text{reject}
\]

también tiene una intuición estadística razonable: un favorito muy fuerte representa una contienda muy asimétrica, y la estructura Poisson/Davidson predice, ceteris paribus, menor propensión al empate cuando las fuerzas se separan. citeturn17view0turn20search0

Pero hay dos cuestiones diferentes:

**Probabilidad de DRAW.** Una contienda muy desigual suele ser menos favorable al draw.

**Value de DRAW.** Eso no implica que apostar al draw sea malo, porque el bookmaker también reduce \(p_D\) e incrementa la cuota. La pregunta económica es si el precio compensa el menor probability mass.

En betting research se ha documentado favorite–longshot bias en diferentes periodos y deportes. Cain, Law y Peel lo encontraron en football fixed odds británico. Sin embargo, Elaad, Reade y Singleton no encontraron un favorite–longshot u outcome bias significativo en el agregado moderno de más de 16.000 partidos ingleses y 51 casas; Angelini y De Angelis encontraron heterogeneidad entre 11 ligas europeas. Por tanto, “evitar favoritos fuertes” puede ser útil como descriptor de régimen, pero no debe asumir un edge de mercado universal. citeturn21view3turn18search0turn18search1

Además, una vez que tenemos \(p_D\) y \(|p_H-p_A|\), un `favorite_probability` es algebraicamente redundante:

\[
p_{\text{fav}}
=
\max(p_H,p_A)
=
\frac{1-p_D+|p_H-p_A|}{2}.
\]

Por ello, introducir simultáneamente `p_draw`, `abs(p_home-p_away)` y `p_favorite` en una regresión lineal/logística simple no añade grados de información y puede generar colinealidad.

**Recomendación:** el threshold `1.5` queda sólo en `LEGACY_R45`. En el experimento modernizado basta con \(|p_H-p_A|\), o alternativamente \(p_{\text{fav}}\), pero no ambos salvo una transformación no lineal explícitamente justificada.

### Draw bias y elección del método de de-vig

No debe interpretarse:

\[
p_i = \frac{1/O_i}{\sum_j 1/O_j}
\]

como “la probabilidad verdadera”. Es una forma simple y reproducible de repartir proporcionalmente el overround.

Štrumbelj mostró que las probabilidades inferidas pueden cambiar materialmente con el método de normalización y que la normalización básica puede inducir bias. Clarke et al. compararon multiplicative, additive, Shin y power y encontraron mejor rendimiento del método power en sus tres grandes datasets; su conclusión relevante para Finsport no es que power sea universalmente correcto, sino que **la distribución del margen entre outcomes es un problema empírico real**. citeturn21view1turn21view0

Esto importa especialmente para DRAW porque algunos estudios han encontrado sesgos outcome-specific. Deschamps y Gergaud reportaron un “draw bias” y un patrón de longshot distinto para las draw odds en fútbol inglés; Cain et al. hallaron favorite–longshot bias en resultados 1X2; en contraste, Elaad et al. no observaron un sesgo agregado por outcome en datos ingleses más modernos. citeturn21view2turn21view3turn18search0

Por tanto, el experimento debería pre-registrar:

\[
\text{de-vig primary}=\text{multiplicative}
\]

por simplicidad y ausencia de parámetros, y al menos una sensibilidad:

\[
\text{de-vig sensitivity}=\text{power}
\]

o Shin si existe una implementación confiable. Si la conclusión sobre draws cambia radicalmente entre métodos de de-vig, eso es una señal de que el supuesto edge está demasiado cerca del margen metodológico para ser considerado robusto.

No recomiendo introducir un “draw correction factor” manual. Debe observarse directamente la calibration curve del mercado para DRAW.

## Abstención, ranking, selección por value y momento de las odds

La idea legacy más sólida a nivel de decisión no es “apostar empates”, sino **permitir no actuar**.

La literatura de clasificación con reject option se remonta al trabajo de Chow sobre el trade-off óptimo entre error y rechazo y continúa en selective classification, donde el predictor opera solamente sobre una fracción de observaciones y se evalúa conjuntamente el riesgo y la cobertura. citeturn17view5turn5search4turn5search13

Pero betting cambia la función de utilidad. Para un clasificador, abstenerse tiene sentido cuando la confianza es baja. Para una estrategia de value, incluso una predicción muy incierta puede ofrecer value si el precio es suficientemente favorable, mientras que una predicción de alta confianza puede no ser apostable si la cuota ya refleja esa probabilidad.

Para una cuota decimal ejecutable \(O_i\) y una probabilidad del modelo \(p_i\):

\[
EV_i
=
p_i(O_i-1)-(1-p_i)
=
p_i O_i-1.
\]

Así:

\[
EV_i>0
\iff
p_i>\frac1{O_i}.
\]

Puede expresarse también un “probability edge” contra el break-even raw:

\[
e_i=p_i-\frac1{O_i}.
\]

Para comparar forecasting model vs market sin mezclar bookmaker margin, conviene además observar:

\[
e_i^{fair}
=
p_i-p_i^{market,de\text{-}vig}.
\]

Ambas cantidades sirven a propósitos distintos:

* \(p_i-p_i^{market}\) mide discrepancia de probabilidades respecto del consenso fair estimado;
* \(p_iO_i^{exec}-1\) determina el retorno esperado al **precio realmente ejecutable**.

La política general del nuevo action space debería ser:

\[
i^\*=\arg\max_{i\in\{H,D,A\}} EV_i,
\]

y:

\[
action=
\begin{cases}
i^\*, & EV_{i^\*}>\tau \\
NO\_BET, & \text{en otro caso}.
\end{cases}
\]

Aquí \(\tau\) **no debe fijarse por literatura como 5 percentage points ni como 5% EV**. No existe en la evidencia revisada un threshold universal de ese tipo. \(\tau=0\) es la frontera matemática de break-even bajo probabilidades conocidas sin error, pero en la práctica \(p_i\) es estimada y puede estar descalibrada; por ello un margen positivo puede ser necesario. Su valor debe calibrarse exclusivamente en folds cronológicos de entrenamiento/validation y luego congelarse para el test externo.

Esto produce directamente la conducta exigida en el nuevo contrato:

\[
p_H>p_D
\]

no impide una acción DRAW. Por ejemplo:

\[
EV_D>EV_H
\]

puede hacer que:

\[
action=DRAW
\]

aunque HOME sea la clase modal. Ésta es exactamente la separación que debe existir entre **predictive classification** y **betting decision**.

### Selective prediction frente a top-1 legacy

“Elegir solamente el mejor candidato” se parece superficialmente a selective prediction, pero no son equivalentes.

Selective prediction pregunta qué subconjunto aceptar para alcanzar cierto perfil riesgo/cobertura. El legacy añade una restricción operacional particular:

\[
k=1
\]

por ejecución/ventana temporal.

No encontré fundamento académico que convierta **“una sola apuesta entre todos los próximos fixtures”** en una propiedad estadística óptima del problema DRAW. Elegir top-1 puede aumentar precision simplemente reduciendo coverage, pero puede igualmente desechar un segundo evento con EV independiente y superior a cero.

Debe medirse una curva:

\[
\text{risk/value}
\quad \text{vs}\quad
\text{coverage}.
\]

Por ejemplo, ordenar fixtures por:

\[
\widehat{EV}_{max}
\]

y evaluar top 1%, 5%, 10%, 25%, etc., es un experimento válido. Hardcodear top-1 no lo es.

**Recomendación:** `top-1` permanece únicamente en `LEGACY_R45`. La implementación productiva debe evaluar cada fixture individualmente y devolver `NO_BET` cuando ningún outcome supera el criterio.

### Odds cercanas al kickoff

Hay buenas razones para esperar que una cuota más próxima al inicio incorpore más información de mercado, porque entre opening y cierre pueden llegar lesiones, alineaciones, información privada o señales generadas por betting flow. En otros mercados deportivos, cambios entre opening y closing lines han demostrado contener nueva información predictiva. Los bookmakers también actualizan precios a partir de la información y del flujo observado. citeturn10search12turn11search11

Pero “más tarde siempre es mejor” no es una ley. Estudios de dinámica intradía en otros deportes han observado trayectorias no monotónicas de calidad del forecast, y evidencia futbolística sobre opening/closing, margins y market structure tampoco justifica una ventana universal. citeturn10search3turn11search17

Por consiguiente:

**Evidencia:** el momento del precio importa y los mercados actualizan información.

**Intuición plausible:** el último precio válido antes del kickoff es un benchmark atractivo.

**Regla legacy sin respaldo universal:** `now + 5m … now + 65m`.

La regla moderna debe definir un **prediction cutoff reproducible**, por ejemplo:

\[
t_{\text{decision}}=kickoff-\Delta
\]

y utilizar solamente odds observadas:

\[
timestamp\le t_{\text{decision}}.
\]

El valor de \(\Delta\) —5, 15, 30, 60 minutos— sólo puede estudiarse cuando Finsport conserve odds history. El almacenamiento actual latest-value destruye esa dimensión temporal, de modo que no es posible comprobar retrospectivamente si 15 minutos, 60 minutos o closing fueron mejores utilizando solamente la tabla actual. fileciteturn0file0

Éste es un argumento fuerte para comenzar a persistir odds snapshots históricos ahora, aunque no sea necesario bloquear el backtest de Dixon–Coles, Poisson o Elo sobre resultados.

### Mercado como predictor frente a precio de ejecución

Las odds de bookmakers son un benchmark difícil de superar. Forrest, Goddard y Simmons compararon cerca de 10.000 partidos ingleses y encontraron que las forecasts implícitas en las odds mejoraron en el tiempo y que su modelo estadístico benchmark no las superó. Más recientemente, Elaad et al. observaron que las odds agregadas de 51 bookmakers eran generalmente eficientes/no sesgadas, aunque bookmakers individuales no incorporaban toda la información de sus competidores. citeturn18search9turn18search0

Eso tiene dos consecuencias de arquitectura:

\[
\boxed{\text{market consensus probability}\neq\text{executable price}}
\]

El **consenso** sirve como forecast/benchmark y referencia de fair probability.

La **best available odd** sirve para calcular EV de una acción realmente ejecutable.

Para cada bookmaker:

\[
q_{b,i}=1/O_{b,i}
\rightarrow
p_{b,i}^{fair}
\]

mediante de-vig. Luego se construye el consenso sobre probabilidades, no promediando odds crudas.

No existe evidencia suficiente para afirmar a priori que “mediana + mínimo tres bookmakers” sea la combinación óptima. En datos limpios y homogéneos, una media utiliza toda la información; una mediana es más robusta a quotes anómalas/stale. La evidencia de Elaad et al. de que bookmakers individuales contienen información no completamente aprovechada por otros favorece el uso de múltiples fuentes, pero no prescribe un estimador robusto específico. citeturn18search0

Para el experimento recomiendo:

\[
p_i^{consensus}
=
\frac1B\sum_{b=1}^{B}p_{b,i}^{fair}
\]

como baseline transparente, y:

\[
\operatorname{median}_b(p_{b,i}^{fair})
\]

seguida de renormalización como **sensitivity check** ante outliers.

La cobertura mínima no debería hardcodearse antes de inspeccionar Finsport. En vez de inventar “3 bookmakers”, se debe reportar desempeño por strata de \(B\): uno, dos, tres a cinco y más de cinco books, y escoger posteriormente el minimum coverage donde la calibración/dispersion se vuelva suficientemente estable.

Para el comparator `market consensus` cuando además se calcula value contra un bookmaker concreto, una versión metodológicamente limpia es el **leave-one-bookmaker-out consensus**:

\[
p_{-b,i}^{market}
=
\operatorname{aggregate}
\{p_{j,i}:j\ne b\}.
\]

Así la misma cuota anómala que se quiere explotar no participa íntegramente en la estimación de su “fair probability”. Si después se elige el mejor precio entre casas, este procedimiento reduce una forma de circularidad.

La distinción también ayuda con Inkabet: no hay fundamento para otorgarle peso “sharp” o “recreational” por nombre. Mientras no exista evidencia Finsport de calibration, freshness y error rate por source/bookmaker, Inkabet debe ser otra observación de mercado con metadata de fuente. La posibilidad de distinguir sharp de recreational puede evaluarse posteriormente mediante calibration histórica y capacidad de anticipar el consenso posterior; no debe codificarse a priori.

## Modelos específicamente sensibles al empate y su relación con R45

Para determinar si R45 encontró de forma empírica una estructura real del fútbol o solamente una regularidad temporal del mercado, el experimento necesita modelos que lleguen a \(P(D)\) por mecanismos independientes de la propia cuota de DRAW.

### Independent Poisson

El baseline score-based más limpio modela:

\[
X_H\sim Pois(\lambda),
\qquad
X_A\sim Pois(\mu),
\]

con:

\[
\log\lambda
=
\alpha_H+\beta_A+\gamma,
\]

\[
\log\mu
=
\alpha_A+\beta_H.
\]

Aquí:

* \(\alpha_i\): fuerza ofensiva del equipo \(i\);
* \(\beta_i\): fuerza defensiva;
* \(\gamma\): home advantage.

Maher estableció esta familia y encontró buen ajuste general, con pequeñas desviaciones sistemáticas y potencial mejora mediante dependencia bivariada. citeturn17view0

La distribución completa produce:

\[
P(H)=\sum_{x>y}P(X_H=x,X_A=y),
\]

\[
P(D)=\sum_{x=y}P(X_H=x,X_A=y),
\]

\[
P(A)=\sum_{x<y}P(X_H=x,X_A=y).
\]

No necesita bookmaker odds. Es por eso especialmente valioso: permite preguntar si hay señal histórica futbolística independiente de lo que el mercado ya sabe.

### Dixon–Coles

Dixon–Coles conserva la estructura de intensidades de gol pero modifica localmente la joint probability de scores bajos, que son precisamente los resultados que afectan de forma importante a DRAW:

\[
P(X=x,Y=y)
=
\tau(x,y;\lambda,\mu,\rho)
Pois(x;\lambda)Pois(y;\mu).
\]

La corrección estándar actúa sobre:

\[
(0,0),\ (0,1),\ (1,0),\ (1,1),
\]

mientras los demás resultados mantienen \(\tau=1\). La propuesta original se construyó sobre regresión Poisson, dinámica de fortalezas y una evaluación sobre datos ingleses; los autores obtuvieron retorno positivo en su muestra de betting, un resultado históricamente interesante pero que no debe extrapolarse a mercados actuales. citeturn17view1

Una parametrización convencional de la corrección es:

\[
\tau(0,0)=1-\lambda\mu\rho
\]

\[
\tau(0,1)=1+\lambda\rho
\]

\[
\tau(1,0)=1+\mu\rho
\]

\[
\tau(1,1)=1-\rho
\]

y:

\[
\tau(x,y)=1
\]

en los demás scores.

Cuando el \(\rho\) estimado adopta el signo habitual que aumenta masa en draws bajos, el modelo corrige precisamente una deficiencia que Independent Poisson puede mostrar en esos outcomes. El valor y el signo efectivos de \(\rho\) deben estimarse con datos Finsport, no fijarse mediante una constante copiada.

La likelihood ponderada temporalmente puede escribirse:

\[
\ell(\theta)
=
\sum_{m}
w_m
\log
P_\theta(x_m,y_m),
\]

con una forma de decay como:

\[
w_m=\exp(-\xi\Delta t_m).
\]

Dixon–Coles introdujo explícitamente la necesidad de manejar la naturaleza dinámica de las performances; trabajos posteriores desarrollaron modelos dinámicos de ataque/defensa sobre la misma familia. citeturn17view1turn13search0

Para el experimento FS-003 hay una decisión de diseño muy conveniente:

\[
\boxed{\text{Independent Poisson = mismo pipeline DC con }\rho=0}
\]

y, preferiblemente, el mismo tratamiento temporal.

Así la comparación:

\[
DC\quad vs\quad IP
\]

es una **ablation casi pura de la corrección de low scores**, en vez de comparar dos implementaciones con distinta ventana, distinto decay y distinta optimización. Si Dixon–Coles no mejora log loss/Brier/calibration de DRAW frente a \(\rho=0\), Finsport obtiene una señal clara de que esa complejidad adicional no está justificada.

### Bivariate Poisson

Karlis y Ntzoufras reemplazaron la independencia de scores mediante una estructura bivariada. Una construcción clásica es:

\[
X=U_1+U_3,
\qquad
Y=U_2+U_3,
\]

donde:

\[
U_1\sim Pois(\lambda_1),\quad
U_2\sim Pois(\lambda_2),\quad
U_3\sim Pois(\lambda_3).
\]

Entonces:

\[
Cov(X,Y)=\lambda_3.
\]

Su trabajo concluyó que incluso una dependencia moderada puede mejorar el fit y la predicción del número de draws; además introdujo extensiones con inflación sobre la diagonal para mejorar explícitamente la estimación de empates y permitir mayor dispersión marginal. citeturn17view2

Esto es muy relevante científicamente para R45: confirma que **“DRAW necesita un tratamiento especial”** no es una invención de Finsport.

No obstante, para FS-003 bivariate Poisson es un excelente candidato **posterior**, no necesariamente el primer implementation baseline. Añade parámetros y complejidad de estimación, mientras Dixon–Coles ofrece una corrección pequeña y muy interpretable sobre la misma arquitectura Poisson. La evidencia comparativa moderna tampoco muestra que más complejidad produzca automáticamente mejores forecasts: estudios que comparan múltiples modelos de strengths han encontrado Independent y Bivariate Poisson competitivos entre sí y frente a otras familias. citeturn17view4

### Elo-logit

Elo por sí solo no produce correctamente un vector H/D/A; es un rating de fuerza. Hvattum y Arntzen propusieron utilizar Elo como información para modelos de resultados futbolísticos y compararon el enfoque estadística y económicamente con múltiples alternativas. citeturn17view3

Para este experimento, el comparator más claro sería:

\[
d_t=R_{home,t}-R_{away,t}+h
\]

y después una regresión multinomial:

\[
P(Y=k\mid d_t)
=
\frac{\exp(a_k+b_kd_t)}
{\sum_{j\in\{H,D,A\}}\exp(a_j+b_jd_t)}.
\]

Conviene preferir multinomial a ordered logit para el comparator centrado en DRAW: literatura posterior sobre outcome forecasting en fútbol señala que la estructura proportional-odds de los modelos ordinales puede tener problemas para explotar predictors con información específicamente relacionada con draws, aunque las diferencias empíricas de accuracy no siempre resulten grandes. citeturn8search0

Así, `Elo-logit` será un benchmark de outcome-model simple, barato y no basado en score.

### Market consensus

El mercado merece ser tratado como **modelo probabilístico externo**, no como ground truth. La literatura demuestra que las odds pueden ser forecasts muy competitivos y que agregar información de múltiples casas tiene sentido, pero también que existen ineficiencias y heterogeneidad entre bookmakers y ligas. citeturn18search9turn18search0turn18search1

Esto hace que el test más exigente para cualquier modelo Finsport no sea:

\[
\text{¿supera al league draw-rate?}
\]

sino:

\[
\boxed{\text{¿aporta información incremental más allá del mercado?}}
\]

### Variante modernizada de la intuición R45

Para probar las ideas legacy sin copiar sus thresholds, propongo un comparator explícitamente interpretable.

Primero:

\[
(p_H^M,p_D^M,p_A^M)
\]

es el market consensus de-vigged.

Definimos:

\[
z_1=\operatorname{logit}(p_D^M),
\]

\[
z_2=|p_H^M-p_A^M|,
\]

\[
z_3=\widehat r_{league,t}^{shrunk}.
\]

Luego:

\[
\widehat p_D
=
\sigma(
\beta_0+\beta_1z_1+\beta_2z_2+\beta_3z_3
).
\]

Para obtener un vector completo H/D/A sin inventar un segundo directional model, se conserva el ratio HOME:AWAY del mercado:

\[
\widehat p_H
=
(1-\widehat p_D)
\frac{p_H^M}{p_H^M+p_A^M},
\]

\[
\widehat p_A
=
(1-\widehat p_D)
\frac{p_A^M}{p_H^M+p_A^M}.
\]

Entonces:

\[
\widehat p_H+\widehat p_D+\widehat p_A=1.
\]

Este modelo responde exactamente a la pregunta:

> “¿Las ideas de paridad y draw-rate que inspiraban R45 permiten corregir el \(P(D)\) del mercado?”

sin fingir que las odds 2.8–4.2, el threshold 1.5 o el 25% son constantes científicas.

Debe probarse en forma incremental:

\[
M_0:\ p_D^M
\]

\[
M_1:\ p_D^M+\text{parity}
\]

\[
M_2:\ p_D^M+\text{league draw prior}
\]

\[
M_3:\ p_D^M+\text{parity}+\text{league draw prior}.
\]

Si \(M_3\) no mejora \(M_0\) fuera de muestra, las intuiciones legacy no aportan señal incremental y deben descartarse del predictor moderno.

La siguiente tabla resume la situación de los seis candidatos pedidos:

| método | produce H/D/A probabilities | utiliza odds | tratamiento del DRAW | función en experimento |
|---|---:|---:|---|---|
| `LEGACY_R45` | No; produce DRAW/NO_BET | Sí | hard rules + ranking | Comparator histórico de selección |
| `MODERNIZED_R45` | Sí | Sí | recalibra \(p_D^{market}\) con paridad + prior rolling | Test directo de si sobreviven las intuiciones |
| Dixon–Coles | Sí | No | corrección explícita de low scores | **Baseline model recomendado** |
| Independent Poisson | Sí | No | draw emerge de score matrix | Ablation esencial de Dixon–Coles |
| Elo-logit | Sí | No | clase explícita en multinomial logit | Comparator outcome/rating |
| Market consensus | Sí | Sí | \(p_D\) implícito de bookmakers tras de-vig | Benchmark externo principal |

La razón para recomendar **Dixon–Coles** como baseline primario no es que esté probado como ganador universal. Es que combina cinco propiedades favorables para este problema: utiliza sólo datos que Finsport ya conserva; es interpretable; produce una distribución completa de score y H/D/A; incorpora explícitamente el tipo de desviación low-score que importa al DRAW; y puede falsarse limpiamente contra Independent Poisson poniendo \(\rho=0\). La evidencia original de Dixon–Coles y la posterior de Karlis–Ntzoufras justifican investigar dependencia de draws; la evidencia de Maher y comparaciones posteriores impide asumir que esa complejidad necesariamente vencerá al Poisson independiente. citeturn17view1turn17view2turn17view0turn17view4

## Experimento reproducible para Finsport

El experimento debe separar estrictamente **forecast quality**, **draw-specific quality**, **selective decisions** y **economic value**. Evaluar los seis métodos con una sola métrica produciría conclusiones engañosas.

### Unidad temporal y prevención de leakage

Para cada fixture objetivo \(m\) con kickoff \(t_m\), se define un cutoff:

\[
c_m<t_m.
\]

Cualquier feature del fixture sólo puede usar registros que hubieran estado disponibles en \(c_m\).

Esto implica:

\[
\text{training matches}=
\{j:t_j<c_m,\ status_j=finished\}
\]

y nunca:

* resultado del propio fixture;
* score del fixture;
* standings recalculados incluyendo el fixture;
* aggregates finales de temporada;
* draw-rate de partidos posteriores;
* odds observadas después de \(c_m\);
* provider prediction generada/revisada después del cutoff.

Para un rolling league draw rate:

\[
D_{L,c_m}
=
\sum_{j\in L:t_j<c_m}
\mathbf1(y_j=D).
\]

Para attack/defense/Elo, la actualización del match \(j\) sólo ocurre **después** de haber emitido su forecast. Este orden debe estar codificado en el test harness:

```text
predict fixture j
→ persist/evaluate forecast
→ reveal result j
→ update model state
→ move to next chronological fixture
```

No debe calcularse una tabla completa de “season aggregates” y luego hacer `join` retrospectivo.

### Walk-forward

Un split aleatorio es inapropiado porque permitiría que información de una fecha posterior influya en el modelo que predice el pasado.

La evaluación debería seguir rolling origin:

```text
training history up to T0
→ predict next block
→ reveal block results
→ extend training set
→ refit/update
→ predict next block
→ ...
```

El bloque puede ser matchweek o un intervalo cronológico corto; la elección debe respetar matches pospuestos y calendarios irregulares usando timestamps, no sólo round numbers.

Los hiperparámetros —por ejemplo \(\xi\) de time decay, Elo \(K\), home-advantage treatment, regularización de `MODERNIZED_R45` y threshold de value— sólo pueden seleccionarse mediante **inner walk-forward dentro del training period**.

Estructura:

```text
OUTER TRAIN
    INNER chronological validation
        fit candidate hyperparameters
        compare
    select hyperparameters
    refit on entire OUTER TRAIN
OUTER TEST
    freeze everything
    predict
```

No debe elegirse un threshold mirando el ROI final.

### Reproducción de `LEGACY_R45`

La versión legacy debe conservar exactamente las reglas del commit/versión Git identificada, aunque sepamos que son arbitrarias:

```text
reject if abs(home_odd - away_odd) > 3
reject if draw_odd < 2.8 or draw_odd > 4.2
reject if league historical draw % < 25
reject if home_odd < 1.5 or away_odd < 1.5
rank eligible candidates with original scoring
take top-1
only original near-kickoff window
eligible candidate → DRAW
none → NO_BET
```

No debe “mejorarse” al mismo tiempo que se llama `LEGACY_R45`, porque perderíamos el comparator histórico.

Hay, sin embargo, una limitación material: el Finsport actual no conserva históricamente cuál era el set de odds/candidatos disponible en cada ventana pre-kickoff. Por ello, salvo que Git/DB legacy conserve esas observaciones antiguas en otra estructura, **un backtest histórico fiel de R45 no puede reconstruirse con `OddsSnapshot` actual**. fileciteturn0file0

La evaluación honesta tiene dos opciones:

\[
\text{legacy archive existente}
\rightarrow
\text{replay histórico}
\]

o:

\[
\text{sin archive}
\rightarrow
\text{prospective shadow evaluation desde ahora}.
\]

No se deben sustituir las odds históricas por el “latest value” que casualmente exista hoy.

Además, `LEGACY_R45` **no produce probabilidades H/D/A**. Por eso no debe recibir artificialmente un Brier o log loss fingiendo que “DRAW seleccionado = 100% DRAW”. Su comparación válida es:

* selected-draw hit rate;
* coverage;
* número de oportunidades;
* realized flat-stake P&L/ROI donde el precio sea históricamente válido;
* comparación de la selección con los candidatos que habría elegido la variante moderna.

### Evaluación de predictive accuracy

Para cada modelo que emita:

\[
\mathbf p_m=(p_H,p_D,p_A),
\]

la métrica primaria debería ser multiclass log loss:

\[
LL=
-\frac1N
\sum_m
\log p_{m,y_m}.
\]

Y multiclass Brier:

\[
BS=
\frac1N
\sum_m
\sum_{k\in\{H,D,A\}}
(p_{m,k}-\mathbf1[y_m=k])^2.
\]

Los proper scoring rules están diseñados para incentivar la emisión de la distribución probabilística verdadera; log score y Brier pertenecen a esta familia. La descomposición clásica del Brier separa componentes asociados a reliability/calibration, resolution y uncertainty. citeturn15search0turn15search4

Dado el foco especial en DRAW, además se reportará un Brier one-vs-rest:

\[
BS_D=
\frac1N
\sum_m
(p_{m,D}-\mathbf1[y_m=D])^2
\]

y log loss binario del empate.

La accuracy modal será secundaria:

\[
\widehat y_m=\arg\max_k p_{m,k}.
\]

Es útil para comunicar cuántos outcomes se aciertan, pero ignora la calidad de las probabilidades. Un modelo que diga 0.34/0.33/0.33 y otro que diga 0.90/0.05/0.05 reciben el mismo “correct/incorrect” si HOME ocurre, pese a que sus forecasts son radicalmente distintas.

### Calibration

Debe trazarse una reliability curve separada para:

\[
P(H),\quad P(D),\quad P(A).
\]

Para DRAW, por ejemplo, fixtures con forecast alrededor de 0.30 deberían empatar aproximadamente 30% a largo plazo. La literatura sobre probabilistic forecasting considera calibration/reliability una propiedad central, y Murphy formalizó su relación con el Brier score. citeturn15search4turn15search8

Los bins deben incluir intervalos de incertidumbre y número de observaciones; no recomiendo tomar un único ECE como criterio decisivo porque depende de la discretización. La reliability curve y Brier/log loss contienen más información.

También hay que calibrar **market consensus**. Si los bookmakers ya son mejores en \(p_D\) que todos los modelos locales, eso es un hallazgo valioso, no un fracaso del experimento.

### Prueba directa de las intuiciones legacy

El análisis `MODERNIZED_R45` debe reportar:

\[
\Delta LL =
LL(M_1)-LL(M_0)
\]

para parity, y equivalentes para league prior.

Además:

\[
\Delta BS_D.
\]

La evidencia incremental debe medirse en outer test, no en training.

Una forma robusta de cuantificar incertidumbre es re-muestrear bloques temporales —por ejemplo matchweeks o bloques de calendario— y construir un intervalo para:

\[
LL_A-LL_B.
\]

El objetivo no es perseguir un \(p<0.05\) aislado, sino verificar que la mejora:

* tenga el signo correcto;
* sea consistente entre folds;
* no dependa de una sola liga/temporada;
* persista bajo métodos de de-vig razonables;
* sobreviva al mercado como benchmark.

### Betting value

Para cada método probabilístico \(M\), resultado \(i\) y fixture \(m\):

\[
EV_{m,i}^{M}
=
p_{m,i}^{M}O_{m,i}^{best}-1.
\]

La acción:

\[
a_m^M=
\begin{cases}
\arg\max_i EV_{m,i}^M,
& \max_i EV_{m,i}^M>\tau\\
NO\_BET,
& \text{otherwise}.
\end{cases}
\]

Se reportará:

\[
coverage=
\frac{\#\{a_m\ne NO\_BET\}}{N},
\]

frecuencias de `HOME/DRAW/AWAY`, average estimated EV, hit rate por action y flat-stake return:

\[
PnL
=
\sum_{\text{bets}}
\begin{cases}
O_i-1,& y=i\\
-1,&y\ne i.
\end{cases}
\]

\[
ROI=
\frac{PnL}{N_{\text{bets}}}.
\]

Es esencial usar flat stake de 1 unidad únicamente como instrumento de evaluación. No se necesita Kelly, Martingale ni bankroll management para FS-003.

Debe reportarse la incertidumbre del ROI, porque una estrategia altamente selectiva puede aparentar resultados enormes con pocos eventos. El problema es especialmente serio para el legacy top-1.

El estudio de Angelini y De Angelis es relevante aquí: las conclusiones de eficiencia cambiaban cuando se consideraba la mejor cuota entre muchos bookmakers, y sólo algunas ligas exhibían oportunidades, lo que ilustra por qué forecast accuracy y economic profitability no son equivalentes. citeturn18search1

### Threshold de NO_BET

En vez de decretar una cifra, el experimento debe producir una curva:

\[
\tau\rightarrow
(\text{coverage},\text{ROI},\text{PnL},\text{hit rate}).
\]

Por ejemplo, \(\tau\) puede explorarse en validation sobre una grilla razonable de EV, pero cualquier valor finalmente elegido se congela antes del outer test.

Otra variante posterior, estadísticamente más conservadora, sería apostar sólo cuando un lower confidence bound de EV sea positivo:

\[
LCB(EV_i)>0.
\]

No considero necesario incluir esa estimación de incertidumbre como requisito del primer baseline; sí conviene diseñar la interfaz para que `decision_reason` pueda incorporar posteriormente uncertainty.

### Mercado de-vigged vs best price

Para evitar un error conceptual muy frecuente:

```text
market consensus de-vigged
        ↓
benchmark / estimate of market belief

best executable decimal odd
        ↓
payout used in EV
```

No debe calcularse EV con una “fair odd” de-vigged; la fair probability es referencia predictiva, mientras el payout es el precio real.

Asimismo, conviene guardar en cada decisión:

```text
model_probability
market_consensus_probability
bookmaker
executed/reference_odd
raw_implied_probability
overround
de_vig_method
estimated_EV
decision_cutoff_timestamp
model_version
```

Eso permitirá auditar por qué un `DRAW` fue seleccionado aunque no fuera la clase más probable.

### Qué puede y qué no puede responderse hoy por la limitación de odds history

La situación actual permite tres clases diferentes de evaluación.

| pregunta | con histórico actual de resultados | con latest-only odds actual | necesita odds history |
|---|---:|---:|---:|
| ¿DC predice mejor que Poisson? | Sí | No necesario | No |
| ¿Elo predice mejor H/D/A? | Sí | No necesario | No |
| ¿DC está calibrado para DRAW? | Sí | No necesario | No |
| ¿league draw-rate añade señal al modelo futbolístico? | Sí | No necesario | No |
| ¿market \(p_D\) estaba bien calibrado hace dos temporadas? | No, salvo archive externo | No | **Sí** |
| ¿R45 habría escogido este partido en 2024? | No, salvo archive legacy | No | **Sí** |
| ¿un edge histórico era rentable a la cuota disponible entonces? | No | No | **Sí** |
| ¿60 min antes era mejor que 5 min antes? | No | No | **Sí** |
| ¿qué bookmaker anticipa mejor el cierre? | No | No | **Sí** |
| ¿desde hoy las decisiones shadow generan value? | Sí prospectivamente | Sí | Conviene persistir |

Por esto mi recomendación para el problema histórico sigue una variante de **A + B simultáneas** del brief:

\[
\boxed{\text{A: backtest predictivo histórico}}
\]

para DC/IP/Elo y,

\[
\boxed{\text{B: empezar inmediatamente a conservar odds history}}
\]

para market/value/legacy shadow evaluation.

No recomiendo hacer de un dataset histórico completo de odds un prerequisite absoluto de la implementación del modelo futbolístico; bloquearía preguntas que sí pueden responderse ahora. Pero **sí es prerequisite para afirmar retrospectivamente que R45 o cualquier value policy hubiera ganado dinero a precios históricos**. Esta distinción debe quedar escrita en el ticket. fileciteturn0file0

### Criterio de falsación

El baseline debe considerarse sin señal incremental útil si se observa consistentemente que:

\[
LL_{DC}\ge LL_{market}
\]

y:

\[
BS_{DC}\ge BS_{market},
\]

sin mejora estable en calibration de ninguna clase, especialmente DRAW; y si una combinación mercado + modelo:

\[
P(Y\mid p^{market}, p^{DC})
\]

no obtiene mejora out-of-sample frente a usar solamente \(p^{market}\).

Más directamente, para un residual model:

\[
\operatorname{logit}P(D)
=
\alpha+\beta\operatorname{logit}p_D^{market}
+\gamma z_{DC}
\]

un \(\gamma\) inestable y ausencia de reducción de log loss en outer folds significaría que el model score no está aportando draw information que el mercado no posea.

Para value, la señal debería cuestionarse si:

* las oportunidades positivas desaparecen al usar un método alternativo de de-vig;
* el retorno depende de una casa concreta o de quotes obviamente stale;
* el ROI se vuelve no positivo fuera del período usado para calibrar \(\tau\);
* la ganancia proviene de uno o muy pocos outliers;
* el modelo produce “edge” principalmente en zonas donde está peor calibrado;
* market consensus con la misma política de best-price iguala o supera a Finsport;
* los resultados no se replican en folds cronológicos o ligas independientes.

La importancia de revisar outliers no es académica: estudios de betting han mostrado que aparentes profits pueden ser extremadamente sensibles a errores de odds o a apuestas aisladas, por lo que una pipeline seria necesita validación y saneamiento de quotes antes de interpretar ROI. citeturn16academia33

## Decisiones recomendadas para FS-003

La recomendación respecto de la estrategia histórica es inequívoca:

\[
\boxed{\texttt{LEGACY\_R45 debe ser comparator en FS-003, no selector productivo.}}
\]

Su valor es científico y de producto: permite contestar si la estrategia que motivó Finsport era mejor que una regla moderna defendible. El comparator debe ser fiel, con sus thresholds originales, porque modificarlo destruiría esa pregunta. Pero ninguna constante legacy debe heredarse al baseline por autoridad histórica.

La parte que más merece sobrevivir es la idea de **abstención**, transformada en `NO_BET` basado en value. La segunda es la idea de **paridad**, transformada de diferencia de odds a diferencia de probabilidades de-vigged. La tercera es el **contexto de draw-rate de liga**, pero sólo como estimador rolling/shrunk y ablation. La cuarta es la noción de **decision-time cercano al kickoff**, reformulada como timestamp/cutoff reproducible y objeto de evaluación prospectiva. El rango fijo de draw odds, el threshold 1.5, el threshold 25%, top-1 y “siempre DRAW” no deben formar parte de la política moderna.

El diseño recomendado de FS-003 queda así:

```text
historical finished matches
        ↓
leakage-safe chronological state
        ↓
Dixon–Coles
  ├─ attack strength
  ├─ defense strength
  ├─ home advantage
  ├─ time decay
  └─ low-score rho correction
        ↓
P(HOME), P(DRAW), P(AWAY)
        ↓
current pre-kickoff bookmaker 1X2 quotes
        ↓
validate quote sets + compute overround
        ↓
de-vig each bookmaker
        ↓
market consensus P(H/D/A)
        ↓
best executable price by outcome
        ↓
EV_HOME / EV_DRAW / EV_AWAY
        ↓
argmax EV subject to validated threshold
        ↓
HOME / DRAW / AWAY / NO_BET
        ↓
probabilistic evaluation
+
calibration
+
coverage
+
prospective value/ROI
```

Independent Poisson debería reutilizar el mismo pipeline con:

\[
\rho=0,
\]

lo que lo hace el ablation técnicamente más valioso de Dixon–Coles. Maher justifica el baseline independiente; Dixon–Coles justifica la low-score correction; Karlis–Ntzoufras confirma que la estructura de draws puede requerir dependencia adicional. citeturn17view0turn17view1turn17view2

El experimento ampliado solicitado en esta investigación debería contener seis brazos, aunque no todos necesitan convertirse en componentes productivos:

```text
LEGACY_R45
MODERNIZED_R45
DIXON_COLES
INDEPENDENT_POISSON
ELO_MULTINOMIAL_LOGIT
MARKET_CONSENSUS
```

La tabla siguiente recoge las decisiones concretas:

| decisión | recomendación | evidencia | confianza | requiere validación con datos Finsport |
|---|---|---|---|---|
| Rol de `LEGACY_R45` | **Comparator de FS-003; nunca baseline productivo** | No existe equivalente publicado de la fórmula completa; sólo componentes conceptualmente relacionados. | Alta | Sí, especialmente capacidad de replay histórico |
| Acción permitida | **HOME / DRAW / AWAY / NO_BET** | Forecasting probabilístico y betting EV son problemas diferentes. | Muy alta | No para arquitectura; sí para thresholds |
| DRAW no modal | **Debe poder seleccionarse** si tiene mayor EV | \(EV_i=p_iO_i-1\); maximizar probability ≠ maximizar expected return. | Muy alta | Sí, desempeño económico |
| Baseline probabilístico | **Dixon–Coles** | Poisson interpretable + corrección específica de low scores + dinámica temporal. citeturn17view1 | Alta | **Sí** |
| Ablation principal | **Independent Poisson con misma pipeline y \(\rho=0\)** | Maher muestra buen baseline Poisson; permite aislar la utilidad de DC. citeturn17view0 | Muy alta | Sí |
| Comparator rating | Elo + multinomial logit | Elo ha sido estudiado para outcome prediction; multinomial evita imponer proportional odds al DRAW. citeturn17view3turn8search0 | Media-alta | Sí |
| Benchmark externo | Market consensus de-vigged | Odds de bookmakers son forecasts competitivos y múltiples books contienen información complementaria. citeturn18search9turn18search0 | Muy alta | Sí |
| Diferencia HOME/AWAY legacy | Sustituir por \(|p_H-p_A|\) de-vigged; **ablation**, no gate | Poisson/Davidson dan fundamento a parity→draw; raw odds no están en escala probabilística lineal. citeturn17view0turn20search2 | Alta | **Sí, crucial** |
| Valor incremental de parity después de \(p_D\) | No asumirlo; probar `pD` vs `pD + |pH-pA|` | No se encontró regularidad publicada robusta que garantice señal residual. Estudios de eficiencia son heterogéneos. citeturn18search0turn18search1 | Alta | **Sí** |
| Draw odds 2.8–4.2 | Mantener sólo en `LEGACY_R45` | Es una banda de precio arbitraria; de-vig y outcome biases complican su interpretación. citeturn21view1turn21view0 | Alta | No para descartar como universal; sí para comparar legacy |
| Draw-rate de liga | Rolling + shrinkage como feature/ablation; eliminar threshold 25% | Hay heterogeneidad entre ligas, pero no evidencia del threshold. citeturn16search15 | Alta | **Sí** |
| Favorito <1.5 | Sólo legacy; no hard gate moderno | Paridad tiene fundamento, pero favorite–longshot bias no es universal. citeturn21view3turn18search0 | Alta | Sí |
| Siempre apostar DRAW | Descartar para modelo moderno | Nuevo value policy debe considerar H/D/A. | Muy alta | No |
| Top-1 | Mantener sólo en comparator; evaluar coverage/value continuo | Reject/selective prediction está formalizado, pero top-1 específico no. citeturn17view5turn5search13 | Alta | Sí |
| Abstención | **Conservar como principio central `NO_BET`** | Reject option/selective prediction + decisión económica. citeturn17view5turn5search13 | Muy alta | Threshold sí |
| Ventana 5–65m | Eliminar como constante moderna | Price discovery respalda usar información reciente, no esa ventana universal. citeturn10search12turn10search3 | Alta | **Sí**, requiere odds history |
| Prediction cutoff | Establecer timestamp pre-kickoff explícito y persistirlo | Necesario para reproducibilidad y leakage control. | Muy alta | Valor de \(\Delta\), sí |
| De-vig inicial | Multiplicative como baseline; power/Shin como sensitivity | Métodos de de-vig pueden producir probabilidades distintas y BN puede presentar bias. citeturn21view1turn21view0 | Alta | Sí |
| Consensus entre bookmakers | Media de probabilidades de-vigged como baseline; mediana como sensitivity | Múltiples bookmakers aportan información; no hay fundamento universal para “mediana + 3”. citeturn18search0 | Media-alta | **Sí** |
| Minimum bookmaker coverage | No hardcodear a priori; evaluar por strata de cobertura | La literatura favorece diversidad de books pero no fija un número universal. citeturn18search0turn18search1 | Alta | **Sí** |
| “Sharp” vs “recreational” | No etiquetar sin evidencia propia | Bookmakers individuales difieren en eficiencia, pero eso debe estimarse, no asumirse. citeturn18search0 | Alta | Sí |
| Inkabet | Tratar como fuente/bookmaker independiente hasta medir freshness/calibration | El brief la define como fuente secundaria read-only, no como ground truth. fileciteturn0file0 | Alta | Sí |
| Price para EV | Best valid executable odd | El retorno depende del precio realmente disponible; best-price cambia resultados de eficiencia. citeturn18search1 | Alta | Sí |
| Threshold de value | **No adoptar 5 pp ni otro número universal**; calibrar walk-forward | No existe soporte universal; el error probabilístico obliga a validación. | Muy alta | **Sí** |
| Primary forecast metrics | Log loss + multiclass Brier | Proper scoring rules evalúan la distribución, no sólo la clase modal. citeturn15search0 | Muy alta | No |
| Calibration | Curvas H/D/A, especial énfasis DRAW | Reliability es componente fundamental de evaluación probabilística. citeturn15search4 | Muy alta | Sí |
| Accuracy | Secundaria | Pierde información sobre confidence/probability quality. | Muy alta | No |
| Betting metrics | Coverage, action mix, flat-stake P&L, ROI e incertidumbre | Profitability es distinta de forecast accuracy; resultados de market efficiency varían con precios/ligas. citeturn18search1 | Muy alta | Sí |
| Validation | Nested chronological walk-forward | Necesario para evitar usar futuro en selección de hyperparameters. | Muy alta | Bloque exacto, sí |
| Historical value backtest | No fingirlo con latest odds | Finsport actual no guarda temporal odds history. fileciteturn0file0 | Muy alta | Requiere inspección de archivos legacy |
| Odds history desde ahora | **Sí, comenzar a conservarla** | Necesaria para comparar cutoffs y realizar shadow/value evaluation reproducible. | Muy alta | Diseño de schema/repositorio |
| Bivariate Poisson | Fuera del baseline, challenger posterior | Puede mejorar draws y diagonal fit, con más complejidad. citeturn17view2 | Alta | Posterior |
| Evidencia reciente de draw inefficiency | Considerar sólo como motivación, no como regla | Lezana 2026 reporta retornos anormales en draws/away, pero es evidencia muy reciente. citeturn21view4 | Media | **Sí, absolutamente** |

En términos estrictos de scope de implementación, propondría que **FS-003 sí incluya**:

```text
1. interfaz probabilística H/D/A;
2. Dixon–Coles;
3. Independent Poisson como configuración/ablation rho=0;
4. walk-forward evaluation sin leakage;
5. Brier, log loss, calibration y accuracy secundaria;
6. market de-vig / consensus abstraction;
7. EV por HOME/DRAW/AWAY;
8. NO_BET;
9. soporte de comparator LEGACY_R45 donde los datos permitan replay;
10. MODERNIZED_R45 como research comparator, no como producción;
11. market consensus benchmark;
12. logging de prediction cutoff y datos usados;
13. shadow evaluation prospectiva;
14. inicio de persistencia temporal de odds, si el preflight confirma que
    el cambio de storage es compatible con el ticket.
```

Y **dejaría explícitamente fuera**:

```text
bivariate/diagonal-inflated Poisson como producción
large ensembles
XGBoost / GPU / neural networks
stake sizing
Kelly
Martingale
loss recovery
bankroll optimization
arbitrage
bookmaker automation
real betting
sharp-bookmaker hardcoded taxonomy
manual draw correction factors
hardcoded 5 pp edge
hardcoded 2.8–4.2 moderno
hardcoded 25% draw league threshold
hardcoded 1.5 favourite threshold
hardcoded top-1
hardcoded legacy kickoff window
```

No hay evidencia en esta revisión que haga necesaria una GPU, XGBoost o una neural network para tomar la decisión del baseline actual. La pregunta pendiente más importante no es si una arquitectura más compleja puede aumentar capacidad, sino si **algún modelo local simple conserva señal fuera de muestra después de compararlo con un mercado de bookmakers fuerte**. La literatura histórica advierte precisamente que el mercado puede ser un predictor difícil de superar. citeturn18search9turn18search0

## Preguntas aún no resolubles sin consultar el repositorio/DB Finsport

Antes de convertir este informe en el ticket definitivo, el preflight técnico debe resolver cuestiones que la literatura no puede contestar porque dependen del estado real de Finsport.

| pregunta de preflight | por qué importa |
|---|---|
| ¿Cuál commit/tag implementa exactamente `R45-refund-stop` y cuál fue su scoring completo? | El comparator debe ser bit-for-bit o semánticamente fiel; no debe reconstruirse de memoria. |
| ¿El threshold de draw-rate de esa versión era exactamente 25%, mientras otra versión preservada usaba 20%? | Debe quedar versionado; el brief conserva una variante de thresholds y la investigación actual identifica R45 con otra. fileciteturn0file0 |
| ¿Qué representan exactamente `local_factor`, `visitor_factor` y `draw_factor` en aquella revisión? | Es necesario confirmar que eran directamente decimal odds y de qué source/bookmaker. |
| ¿Cómo se calculaba históricamente `league.draw_percentage`? | Hay que comprobar si contenía sólo partidos previos o si el cálculo histórico tenía leakage. |
| ¿Existe aún algún histórico de `BetTable`, `BetRow`, logs, snapshots, dumps o eventos que preserve las odds originales? | Determina si `LEGACY_R45` puede tener backtest histórico fiel o sólo shadow prospective. |
| ¿Qué timestamp posee hoy `OddsSnapshot`: provider observation time, fetched-at, updated-at o sólo DB timestamp? | Sin semántica temporal fiable no puede definirse correctamente el prediction cutoff. |
| ¿El update de `OddsSnapshot` sobrescribe realmente el registro in-place o existe audit log/event log fuera de la tabla? | Puede haber odds history recuperable que el brief no expone. |
| ¿Existe un identificador estable del bookmaker entre API-Football e Inkabet? | Imprescindible para evitar duplicar la misma casa o tratar aliases como fuentes independientes. |
| ¿Qué bookmakers y cuántos suelen estar disponibles por competición/fixture? | Define si mean/median/leave-one-out consensus son operacionalmente viables. |
| ¿Qué porcentaje de fixtures posee 1, 2, 3, 5, 10+ books válidos? | Debe sustituir cualquier minimum coverage arbitrario. |
| ¿Qué tasa de campos nulos, zero odds, malformed values y partial 1X2 markets existe? | Las tres cuotas deben ser coherentes para calcular overround/de-vig. |
| ¿Existen cuotas extremadamente antiguas que permanecen como “latest” aunque otros books se hayan actualizado? | Necesario para política de stale quotes. |
| ¿Es posible conocer el provider timestamp de Inkabet y compararlo con API-Football? | Permite evaluar freshness en vez de asumir que una fuente es inferior/superior. |
| ¿Inkabet representa una casa que también aparece bajo otro nombre en API-Football? | Duplicarla sesgaría market consensus. |
| ¿Qué competitions poseen historial de resultados completo y desde qué temporada? | Necesario para estimar attack/defense, home advantage y time decay con suficiente información. |
| ¿Hay fixture duplicados, cambios de kickoff, abandonados, awarded matches o postponements? | Afectan orden temporal y definición de training data. |
| ¿Cómo se representan promoted/relegated teams y cambios de Competition/Season? | DC/Elo necesitan una política de inicialización consistente. |
| ¿Los IDs canónicos de Team permanecen estables entre Seasons? | Sin continuidad, los ratings/strengths históricos podrían fragmentarse. |
| ¿Hay scores de tiempo reglamentario separados de extra time/penalties? | 1X2 pre-match normalmente se liquida según reglas específicas del market; no debe mezclarse un cup outcome decidido en penalties con un league-style H/D/A sin verificar. |
| ¿El dataset inicial será sólo domestic leagues o también cups/international? | La estructura estadística de draws, home advantage, rotations y knockout rules puede diferir. |
| ¿Cuántos partidos por competition/season están realmente finalizados y completos? | Debe decidirse sample suitability con datos reales, no “≥2 temporadas” arbitrariamente. |
| ¿Hay un servicio/repository abstraction ya preparado para queries “state as of timestamp”? | Determina la implementación anti-leakage. |
| ¿El pipeline de sync puede persistir cada cambio de odds sin aumentar llamadas a API-Football? | Idealmente odds history debe guardar observaciones de llamadas que ya se realizan, no multiplicar quota. |
| ¿Qué quota real del plan API-Football y qué frecuencia de sync existen hoy? | Determina cuántos cutoffs prospectivos pueden observarse. |
| ¿Existe posibilidad de almacenar `observed_at`, `provider_updated_at` y `ingested_at` por snapshot? | Es la base de un estudio posterior de closing odds/freshness. |
| ¿Puede reconstruirse el conjunto de bookmakers disponible **en el mismo instante** para un fixture? | Imprescindible para un replay económico válido. |
| ¿Cuál es el convention actual de odds decimales y existen mercados suspendidos? | Necesario antes de calcular implied probability/EV. |
| ¿El `Match.outcome` canónico corresponde exactamente a HOME/DRAW/AWAY tras 90 minutos para todas las competitions? | Es un requisito para construir labels consistentes. |
| ¿Qué mecanismo de experiment/version metadata existe? | Cada forecast debe ser reproducible con `model_version`, training cutoff y parámetros. |
| ¿Existe infrastructure para almacenar predictions shadow? | Sin persistencia de forecasts emitidos antes del match es fácil reintroducir hindsight leakage. |
| ¿Qué tests del repositorio pueden garantizar que nunca se consulta un `Match` posterior al cutoff? | La política anti-leakage debe ser verificable, no sólo documentación. |

La cuestión de mayor prioridad durante ese preflight es localizar cualquier rastro de odds históricas o logs legacy. Si no existen, la conclusión debe quedar registrada de forma explícita:

\[
\boxed{
\text{FS-003 puede validar históricamente forecasting,}
\atop
\text{pero no puede afirmar historical betting profitability.}
}
\]

A partir de ese punto, la arquitectura correcta es empezar a acumular una serie temporal prospectiva y mantener los dos tracks separados:

```text
TRACK PREDICTIVO
historical results
→ DC / IP / Elo
→ H/D/A probability evaluation

TRACK ECONÓMICO
timestamped prospective odds
→ market consensus
→ EV
→ HOME / DRAW / AWAY / NO_BET
→ shadow P&L / ROI
```

Esta separación evita el error metodológico más peligroso para FS-003: convertir datos actuales o resultados conocidos en una simulación retrospectiva que parezca demostrar que una estrategia habría tenido value.

En definitiva, la heurística histórica **sí merece sobrevivir en FS-003 como comparator** porque representa una hipótesis de producto real y contiene intuiciones estadísticamente interesantes. Pero la investigación no respalda revivirla como fórmula de producción. La hipótesis que realmente merece conservarse es más estrecha y más científica:

\[
\boxed{
\text{¿Existe señal residual de DRAW asociada a paridad y contexto de liga}
\atop
\text{que no esté ya reflejada en }p_D^{market}\text{?}
}
\]

`MODERNIZED_R45` permite responder directamente esa pregunta; Dixon–Coles e Independent Poisson permiten comprobarla desde un modelo futbolístico independiente; Elo aporta un baseline de strength/outcome; y market consensus establece el estándar que cualquiera de ellos debe superar o complementar. Sólo después de ese walk-forward, y no antes, Finsport tendrá evidencia para decidir si la intuición histórica era alpha reutilizable, una aproximación rudimentaria a conceptos estadísticos legítimos o simplemente una regla que funcionó circunstancialmente en el sistema anterior.
