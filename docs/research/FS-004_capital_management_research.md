# FS-004 — Investigación técnica sobre gestión de capital, recuperación de pérdidas, bankroll y riesgo

**Estado:** `REFERENCE ONLY`
**Proyecto:** `Finsport`
**Fecha:** `2026-08-26`
**Contrato de investigación:** `FS-004_research_brief.md`
**Alcance:** simulación local, evaluación de estrategias y diseño experimental; no ejecución de apuestas reales.

Este informe toma `FS-004_research_brief.md` como contrato de investigación y mantiene su frontera de seguridad: **simulación local, evaluación de estrategias y diseño experimental; no ejecución de apuestas reales**. El brief separa explícitamente predicción, decisión y staking, exige no presumir que la recuperación de pérdidas sea útil y deja determinados parámetros bloqueados hasta recibir FS-003. [FS-004 Brief 2026]

## Conclusión ejecutiva y alcance de las decisiones

La conclusión central puede resolverse **antes de FS-003**:

> **Una progresión de recuperación de pérdidas no crea edge.** Si cada apuesta disponible tiene esperanza condicional no positiva dadas las informaciones conocidas antes de apostar, ninguna regla que cambie el stake en función de pérdidas anteriores puede convertir el proceso en uno de esperanza positiva, siempre que se trabaje con horizonte/stop integrable y capital finito. Lo que sí puede hacer una progresión es cambiar radicalmente la **distribución** del resultado: aumentar la frecuencia de beneficios pequeños y concentrar la pérdida esperada en eventos menos frecuentes pero mucho más severos.

Esta conclusión no depende de que los resultados sean IID. Basta formular el edge correctamente como edge **condicional** a la información disponible. Es la distinción fundamental entre *prediction/selection edge* y *staking*. El trabajo clásico de Kelly optimiza crecimiento cuando existe una distribución favorable conocida; Breiman formalizó propiedades óptimas de sistemas de apuesta para juegos favorables, y Ferguson estudió explícitamente sistemas que minimizan probabilidad de ruina. Ninguno proporciona una vía para obtener esperanza positiva simplemente reordenando cuánto se arriesga en juegos desfavorables. [Kelly 1956; Breiman 1961; Ferguson 1965]

Un ejemplo muestra por qué la recuperación resulta psicológicamente atractiva y estadísticamente peligrosa. En un juego a cuota 2.00, una progresión completa que busque ganar 1 unidad y abandone tras seis pérdidas consecutivas produce:

\[
P(\text{+1 unidad})=1-q^6
\]

y, si falla las seis veces, pierde:

\[
1+2+4+8+16+32=63.
\]

Con un juego exactamente justo, \(p=q=0.5\):

\[
P(+1)=98.4375\%,\qquad P(-63)=1.5625\%,\qquad EV=0.
\]

Por tanto, una tasa del **98.44 % de secuencias ganadoras** puede coexistir con **cero ventaja económica**. Con \(p=0.49\), la misma progresión gana la secuencia el 98.24 % de las veces pero su esperanza pasa a aproximadamente \(-0.1262\) unidades por secuencia. El sistema ha hecho que el resultado parezca extremadamente consistente sin rescatar el edge negativo. Esta es una derivación matemática, no una observación empírica.

La literatura moderna sobre Martingales finitas confirma el mismo mecanismo: limitar los pasos hace ejecutable la distribución pero no elimina el crecimiento exponencial de exposición ni altera por sí solo las probabilidades subyacentes. [Lazowski 2026]

**Conclusiones que pueden fijarse ya:**

**Resultado matemático establecido.** La progresión legacy de Finsport debe clasificarse como una **progresión de target-profit/full-loss-recovery ajustada por cuota**, cuyo caso a cuota constante 2.00 coincide con el Martingale de duplicación. No es correcto llamarla simplemente “Martingale” para cuotas arbitrarias.

**Resultado matemático establecido.** `ceil()` no protege capital: aumenta unilateralmente la exposición y, en aritmética exacta, produce sobre-recuperación respecto del objetivo teórico.

**Resultado matemático establecido.** A cuota constante, el full recovery crece geométricamente. En cuotas bajas, el crecimiento puede ser extremo.

**Inferencia fuerte.** La progresión legacy no tiene una justificación económica especial por provenir del sistema histórico. Su único motivo para permanecer en FS-004 es actuar como **control histórico/falsificable**.

**Recomendación.** `FLAT_UNIT` debe ser el benchmark primario porque desacopla la calidad de selección de la gestión de capital. `FIXED_FRACTION_BANKROLL` debe ser el segundo benchmark porque introduce capital preservation y compounding sin estado de recuperación.

**Recomendación condicionada a FS-003.** `FRACTIONAL_KELLY` es conceptualmente la alternativa más fundada cuando existe edge calibrado, pero no debe utilizarse con estimaciones puntuales de \(p\) tomadas al pie de la letra. La literatura documenta que la incertidumbre paramétrica justifica shrinkage de la apuesta Kelly, y existen formulaciones robustas y con restricción explícita de drawdown. [Baker & McHale 2013; Metel 2018; Sun & Boyd 2018; Busseti et al. 2016]

**Recomendación.** La única variante de recuperación que merece entrar al primer experimento como candidata moderna es una derivada **explícitamente risk-bounded** —por ejemplo `LEGACY_CAPPED`— y aun así como hipótesis por falsificar, no como presunción de mejora. `LEGACY_PARTIAL` merece análisis de sensibilidad, pero no hay teoría que sugiera un porcentaje universal de recuperación óptimo.

**Recomendación.** Fibonacci, d'Alembert, Labouchère, Oscar's Grind y progresiones semejantes no justifican un lugar en el primer FS-004. Son variaciones del perfil temporal de stakes sin un mecanismo que produzca edge. En particular, para Labouchère existen resultados donde el déficit máximo y la cantidad total apostada tienen comportamiento patológico en juegos suficientemente desfavorables; no aporta una pregunta distinta que no podamos contestar con legacy/full recovery. [Han & Wang 2019; Zubrilina 2018]

La idea de producto “muchos aciertos + beneficios pequeños + evitar pérdidas grandes” **sí puede ser coherente**, pero sólo con una restricción crucial:

\[
\boxed{\text{alta tasa de acierto} \;+\; \text{EV positivo robusto} \;+\; \text{riesgo de cola aceptable}}
\]

La alta tasa de acierto por sí sola no tiene valor probatorio. En mercados de apuestas deportivas se observan sesgos favorite–longshot en distintos datasets, incluido fútbol europeo, pero la evidencia no es universal: otros estudios encuentran mercados de fútbol sustancialmente eficientes o sesgos insuficientes para producir rentabilidad. Por eso Finsport no debe codificar una creencia estructural del tipo “favoritos bajos son seguros” o “draws altos son mejores”; debe medir el edge con sus propios datos temporalmente válidos. [Angelini & De Angelis 2019; Elaad et al. 2020; Hegarty & Whelan 2025]

## Fundamentos matemáticos: edge, staking, flat, proporcional y Kelly

**El teorema operativo central para FS-004.**

Sea \(\mathcal F_{i-1}\) toda la información disponible antes de la apuesta \(i\). Sean:

\[
p_i=P(\text{win}_i\mid \mathcal F_{i-1}),
\]

\[
o_i=\text{cuota decimal},
\]

\[
s_i\ge 0
\]

un stake decidido usando únicamente \(\mathcal F_{i-1}\), y

\[
X_i=
\begin{cases}
o_i-1,&\text{si gana}\\
-1,&\text{si pierde}.
\end{cases}
\]

Entonces:

\[
E[X_i\mid\mathcal F_{i-1}]
=p_i(o_i-1)-(1-p_i)
=p_i o_i-1.
\]

Definamos el edge verdadero:

\[
e_i=p_i o_i-1.
\]

La ganancia de la apuesta es \(s_iX_i\), por lo que:

\[
E[s_iX_i\mid\mathcal F_{i-1}]
=s_i e_i.
\]

Para un horizonte finito \(N\), o bajo condiciones de integrabilidad apropiadas,

\[
E[W_N-W_0]
=
\sum_{i=1}^{N}E[s_i e_i].
\]

Por tanto:

\[
e_i\le0\quad\forall i
\quad\Longrightarrow\quad
E[W_N]\le W_0
\]

para **cualquier** progresión predecible \(s_i\), aunque \(s_i\) dependa de todas las victorias y derrotas anteriores.

No se requiere independencia para este argumento; se requiere utilizar la probabilidad **condicional correcta**. Ésta es precisamente la forma en que la teoría de martingalas/supermartingalas separa una regla de apuesta de la ventaja del juego. La teoría clásica de gambling systems de Breiman y Ferguson se sitúa en este marco. [Breiman 1961; Ferguson 1965]

Hay una excepción aparente que es importante entender. Si el edge **incondicional** es negativo pero ciertos estados del historial predicen edge condicional positivo, una política que asigne stake sólo en esos estados puede obtener esperanza positiva:

\[
E[s_i e_i]>0.
\]

Pero ahí la ventaja proviene de que el historial contiene **información predictiva sobre el próximo evento**. Es selection/timing edge; no es “recuperación” produciendo edge.

Esto también resuelve el problema de la falacia del jugador. En un proceso IID:

\[
P(W_{i}=1 \mid L_{i-1},L_{i-2},\ldots)=p.
\]

Una secuencia de derrotas no hace más probable el siguiente acierto. Si Finsport detectase empiricamente dependencia de régimen, entonces debe modelarla como dependencia/calibration drift, no disfrazarla de regla de recuperación.

**Optional stopping y la ilusión del Martingale infinito.**

Un full recovery ideal con capital y stake ilimitados parece garantizar que “eventualmente habrá una victoria” y, por tanto, que terminará con \(+T\). Esto no contradice el resultado anterior porque la progresión ilimitada viola precisamente las hipótesis que permiten intercambiar esperanza y stopping: los stakes explotan y el capital total requerido puede tener esperanza infinita. La teoría de optional stopping necesita condiciones; no permite concluir que una estrategia de doubling ilimitada gane dinero en un juego justo o desfavorable. La literatura contemporánea también distingue claramente “martingale” como proceso estocástico de la progresión de casino homónima. [Liu 1999; Dimitrov & Shafer 2025]

**Flat unit.**

Para:

\[
s_i=u,
\]

la esperanza por apuesta es:

\[
E[\Delta W_i]=u(p_io_i-1).
\]

El beneficio esperado total es transparente:

\[
E[P\&L]=u\sum_i e_i.
\]

Por esa razón `FLAT_UNIT` es el benchmark correcto para FS-003/FS-004: no introduce ninguna ponderación basada en resultados anteriores y permite observar si la selección tiene valor económico.

Su desventaja de capital es que \(u\) es fijo. Después de un drawdown, el mismo stake representa una fracción creciente del bankroll restante. En un proceso largo y con bankroll finito puede cruzar un límite práctico de ruina.

Para el caso especial de apuestas even-money con incrementos \(\pm u\), el gambler's ruin tiene fórmulas cerradas. Para cuotas arbitrarias, stakes discretos, límites y probabilidades variables es normalmente más limpio utilizar recurrencia dinámica o Monte Carlo; Ferguson estudia formalmente el problema de sistemas que minimizan ruina. [Ferguson 1965]

**Fixed fraction / proporcional.**

Para:

\[
s_i=fB_i,\qquad 0<f<1,
\]

el bankroll evoluciona como:

\[
B_{i+1}=
\begin{cases}
B_i[1+f(o_i-1)], & W,\\
B_i(1-f), & L.
\end{cases}
\]

Con \(p,o\) constantes:

\[
E[B_{i+1}\mid B_i]
=
B_i[1+f(po-1)].
\]

La exposición disminuye automáticamente tras pérdidas y aumenta tras ganancias. En el modelo ideal continuo, \(f<1\) impide llegar exactamente a cero en un único paso, aunque **no** impide drawdowns extremos ni cruzar un umbral práctico de capital mínimo.

Frente a flat unit, fixed fraction ofrece compounding y exposición relativa estable; frente a recovery, no intenta “pagar” pérdidas históricas con la siguiente apuesta.

**Kelly.**

Para un único resultado binario con cuota decimal \(o\), probabilidad verdadera \(p\) y fracción \(f\), Kelly maximiza:

\[
g(f)
=
p\log[1+f(o-1)]
+
(1-p)\log(1-f).
\]

La solución sin shorting es:

\[
f_K
=
\max\left(
0,
\frac{po-1}{o-1}
\right).
\]

Por tanto la región de no-apuesta es:

\[
po\le1
\iff
p\le\frac1o.
\]

Kelly fue formulado originalmente como criterio de máximo crecimiento exponencial bajo una distribución conocida; trabajos posteriores desarrollaron sus propiedades de crecimiento de largo plazo. [Kelly 1956; Breiman 1961]

El punto crítico para Finsport es que **full Kelly presupone una estimación de probabilidades suficientemente correcta**. MacLean, Thorp y Ziemba destacan simultáneamente la propiedad de máximo crecimiento asintótico y el considerable riesgo de corto plazo de Kelly completo; la estrategia puede atravesar escenarios en los que pierde gran parte del capital. [MacLean et al. 2010]

Con probabilidades estimadas:

\[
\hat f_K=
\frac{\hat p o-1}{o-1},
\]

un error positivo en \(\hat p\) produce directamente overbetting. Baker y McHale muestran analítica y empíricamente que el riesgo paramétrico justifica reducir el stake Kelly; Metel llega a una conclusión análoga para probabilidades estimadas en contextos de apuestas con múltiples outcomes. [Baker & McHale 2013; Metel 2018]

Por eso la versión candidata para Finsport es:

\[
f_{\text{FK}}
=
\lambda f_K,
\qquad 0<\lambda<1,
\]

no full Kelly por defecto. No existe un \(\lambda\) universalmente correcto. El valor deberá depender de calibración, incertidumbre, correlación y tolerancia al drawdown.

Métodos más formales son posibles. Sun y Boyd plantean Kelly robusto maximizando el peor expected log-growth dentro de un conjunto de distribuciones plausibles; Busseti, Ryu y Boyd incorporan una restricción sobre la probabilidad de caer bajo un nivel determinado de riqueza y muestran un trade-off explícito entre crecimiento y drawdown. [Sun & Boyd 2018; Busseti et al. 2016]

Una versión sencilla para el primer experimento no necesita implementar inmediatamente optimization robusta compleja. Puede comparar:

\[
\hat p
\]

contra una probabilidad conservadora

\[
p^-,
\]

o utilizar shrinkage hacia el mercado:

\[
p_{\text{adj}}
=
p_{\text{market}}
+
\rho(\hat p-p_{\text{market}}),
\qquad 0\le\rho\le1.
\]

Entonces:

\[
f
=
\lambda
\max\left(0,
\frac{p_{\text{adj}}o-1}{o-1}
\right).
\]

Esto debe tratarse como **método de robustez por calibrar**, no como fórmula aprobada. La evidencia académica sobre parameter uncertainty sí respalda el principio de reducir exposición cuando la probabilidad es incierta. [Baker & McHale 2013; Metel 2018]

**Fixed target sin recuperación.**

Sea \(T\) el beneficio neto deseado si la apuesta gana:

\[
s_i=\frac{T}{o_i-1}.
\]

Entonces:

\[
s_i(o_i-1)=T.
\]

La esperanza es:

\[
E[\Delta W_i]
=
\frac{T}{o_i-1}(p_io_i-1).
\]

Es una política distinta de flat: **pondera más fuertemente las cuotas bajas**. La literatura de staking deportivo denomina a ideas cercanas *unit-win* frente a *unit-loss/flat* y las compara con Kelly bajo probabilidades desconocidas. [Barge-Gil & Garcia-Hiernaux 2020]

Por esa razón `FIXED_TARGET_PROFIT_NO_RECOVERY` debe formar parte del análisis: permite separar qué parte del comportamiento legacy proviene de “target profit ajustado por cuota” y qué parte proviene específicamente de cargar pérdidas anteriores.

## Legacy Finsport, full recovery, partial/capped recovery y progresiones comparables

El brief recupera una política histórica basada en:

\[
T=
B_0(o_1-1)
\]

y, para apuestas posteriores con `DEVIATION = 1`,

\[
s_n
=
\left\lceil
\frac{T+L_{n-1}}
{o_n-1}
\right\rceil,
\]

donde \(L_{n-1}\) corresponde aproximadamente a la inversión/pérdida acumulada de la secuencia. El settlement ganador era equivalente a comparar el retorno de la apuesta actual contra toda la inversión acumulada. [FS-004 Brief 2026]

Ignorando redondeo:

\[
s_n=\frac{T+L_{n-1}}{o_n-1}.
\]

Si gana:

\[
\text{P\&L final}
=
s_n o_n-(L_{n-1}+s_n)
=
s_n(o_n-1)-L_{n-1}
=
T.
\]

Por tanto la clasificación matemática exacta es:

> **target-profit + full cumulative-loss recovery + odds-adjusted stake progression.**

No es una progresión geométrica pura cuando las cuotas varían. Sí es geométrica a cuota constante.

**Crecimiento a cuota constante.**

Sea:

\[
r=\frac{o}{o-1}.
\]

Después de \(k\) pérdidas:

\[
L_k
=
T(r^k-1),
\]

y el siguiente stake requerido es:

\[
s_{k+1}
=
\frac{T}{o-1}r^k.
\]

Así, el stake crece con ratio:

\[
\boxed{r=\frac{o}{o-1}}.
\]

Ejemplos:

- \(o=1.20\Rightarrow r=6\)
- \(o=1.50\Rightarrow r=3\)
- \(o=2.00\Rightarrow r=2\)
- \(o=3.00\Rightarrow r=1.5\)
- \(o=4.00\Rightarrow r=1.333\ldots\)

El Martingale clásico de duplicación aparece exactamente como el caso:

\[
o=2.00,\qquad r=2.
\]

Por eso “odds-adjusted Martingale” es una analogía razonable, pero **`LEGACY_RECOVERY` debe conservar su propio nombre**.

La siguiente tabla normaliza \(T=1\) y muestra el **próximo stake requerido** después de \(k\) pérdidas consecutivas, suponiendo cuota constante:

| cuota | k=0 | k=3 | k=5 | k=8 | k=10 |
|---:|---:|---:|---:|---:|---:|
| 1.20 | 5.00 | 1,080 | 38,880 | 8,398,080 | 302,330,880 |
| 1.30 | 3.333 | 271.23 | 5,093.18 | 414,434 | 7,782,152 |
| 1.50 | 2.00 | 54.00 | 486.00 | 13,122 | 118,098 |
| 1.80 | 1.25 | 14.24 | 72.08 | 821.05 | 4,156.57 |
| 2.00 | 1.00 | 8.00 | 32.00 | 256.00 | 1,024.00 |
| 2.50 | 0.667 | 3.086 | 8.573 | 39.69 | 110.25 |
| 3.00 | 0.500 | 1.688 | 3.797 | 12.81 | 28.83 |
| 4.00 | 0.333 | 0.790 | 1.405 | 3.330 | 5.919 |

Esto responde cuantitativamente a uno de los riesgos centrales del brief: **la recuperación completa a odds bajas puede hacer explotar el stake en muy pocas pérdidas**, aun cuando el target profit inicial sea modesto.

**Cuotas variables.**

Sin rounding, después de \(k\) pérdidas a cuotas \(o_1,\ldots,o_k\):

\[
T+L_k
=
T\prod_{j=1}^{k}\frac{o_j}{o_j-1}.
\]

Por tanto:

\[
L_k
=
T
\left[
\prod_{j=1}^{k}\frac{o_j}{o_j-1}
-1
\right].
\]

Y para una próxima apuesta a \(o_{k+1}\):

\[
s_{k+1}
=
\frac{
T\prod_{j=1}^{k}\frac{o_j}{o_j-1}
}{
o_{k+1}-1
}.
\]

Dos conclusiones son interesantes.

Primero, el target inicial \(T\) escala **linealmente** todo el riesgo:

\[
T\to cT
\Longrightarrow
s_i,L_i\to c(s_i,L_i).
\]

Segundo, en aritmética exacta el cumulative loss tras un conjunto fijo de cuotas perdedoras depende del **producto** de los ratios y no del orden de esas cuotas. Sin embargo, los stakes individuales, el máximo stake experimentado y el stake de la siguiente apuesta sí dependen de qué cuota esté disponible en cada paso. Además, `ceil()` elimina esta simetría.

**Rounding legacy.**

Sea \(s^*\) el stake exacto y \(s=\lceil s^*\rceil\). Entonces:

\[
s^*\le s<s^*+1.
\]

Tras una victoria:

\[
\text{beneficio}
=
s(o-1)-L.
\]

Como \(s^*\) hubiese producido exactamente \(T\),

\[
T
\le
\text{beneficio}
<
T+(o-1).
\]

Por tanto `ceil()` causa **sobre-recuperación unilateral** de hasta casi \(o-1\) unidades por apuesta bajo granularidad entera. No puede producir under-recovery por sí mismo con aritmética exacta; floats y semánticas históricas pueden introducir discrepancias adicionales.

Python proporciona `Decimal` precisamente para aritmética decimal exacta/control explícito de precisión y rounding, a diferencia de `float` binario, que no representa exactamente muchos decimales usuales. [Python Decimal 3.13]

**Full recovery finito y por qué su EV conserva el signo del edge.**

Supongamos cuota constante \(o\), probabilidad \(p\), \(q=1-p\), target \(T\), y máximo \(m\) apuestas.

Si se logra cualquier victoria antes del límite:

\[
P\&L=T.
\]

Si se pierden las \(m\):

\[
P\&L=-L_m=-T(r^m-1).
\]

La probabilidad de fallo completo es:

\[
q^m.
\]

Así:

\[
E[P\&L]
=
T(1-q^m)
-
q^mT(r^m-1)
\]

\[
=
T[1-(qr)^m].
\]

Pero:

\[
qr=(1-p)\frac{o}{o-1}.
\]

Y:

\[
qr<1
\iff
(1-p)o<o-1
\iff
po>1.
\]

Por tanto:

\[
\boxed{
\operatorname{sign}(EV_{\text{recovery}})
=
\operatorname{sign}(po-1)
}
\]

en este caso.

Ésta es una demostración muy directa de que la progresión **no rescata** una estrategia perdedora.

También explica la tensión draws vs favoritos. En una apuesta exactamente justa:

\[
p=\frac1o,
\qquad
q=\frac{o-1}{o},
\]

por lo que:

\[
qr=1
\]

**para cualquier cuota**.

A cuotas altas, el stake de recovery crece más despacio, pero las derrotas son más probables. A cuotas bajas, las derrotas son menos frecuentes, pero el stake explota mucho más rápido. En un mercado justo, ambos efectos se compensensan exactamente en la esperanza del full recovery ideal. Con vig o edge negativo, \(qr>1\).

Por tanto no existe una respuesta general del tipo “los DRAW son mejores para recovery porque su cuota es alta” ni “los favoritos son mejores porque ganan más”. Todo depende de:

\[
p,\quad o,\quad calibration,\quad \text{dependencia},\quad \text{capital finito}.
\]

**High-hit-rate / low-odds.**

La probabilidad break-even es:

| cuota | \(p_{\text{break-even}}\) | wins netas de igual stake borradas por una pérdida |
|---:|---:|---:|
| 1.20 | 83.33 % | 5.00 |
| 1.30 | 76.92 % | 3.33 |
| 1.50 | 66.67 % | 2.00 |
| 1.60 | 62.50 % | 1.67 |
| 1.80 | 55.56 % | 1.25 |
| 2.00 | 50.00 % | 1.00 |

A 1.20, una estimación \(\hat p=0.85\) implica:

\[
\hat e=0.85(1.20)-1=+2\%.
\]

Pero si el \(p\) real fuese 0.83:

\[
e=0.83(1.20)-1=-0.4\%.
\]

Un error de calibración aparentemente pequeño cambia el signo de la expectativa. Ésta es precisamente la situación en la que utilizar full Kelly o full recovery sobre una confianza nominal alta resulta más peligroso.

La literatura de fútbol encuentra favorite–longshot bias en ciertos mercados, pero también evidencia de mercados relativamente eficientes y diferencias importantes entre formatos; Finsport debe tratar esto como evidencia empírica externa, no como garantía de edge propio. [Angelini & De Angelis 2019; Elaad et al. 2020; Hegarty & Whelan 2025]

**Partial recovery.**

Una definición limpia de investigación es:

\[
s_n
=
\frac{T+\alpha L_{n-1}}{o_n-1},
\qquad
0\le\alpha\le1.
\]

Para \(\alpha=0\) tenemos target profit sin recovery.

Para \(\alpha=1\) tenemos full recovery.

A cuota constante, después de una pérdida:

\[
L_n
=
L_{n-1}
+
\frac{T+\alpha L_{n-1}}{o-1}.
\]

Para \(\alpha>0\):

\[
L_k
=
\frac{T}{\alpha}
\left[
\left(1+\frac{\alpha}{o-1}\right)^k-1
\right].
\]

La ratio de escalamiento cae desde

\[
\frac{o}{o-1}
\]

en full recovery hasta un crecimiento lineal en el límite \(\alpha\to0\).

Pero existe un costo importante: si gana después de haber acumulado \(L\),

\[
P\&L_{\text{secuencia}}
=
T+\alpha L-L
=
T-(1-\alpha)L.
\]

Por tanto partial recovery **ya no garantiza cerrar la secuencia con beneficio positivo**. No es un defecto matemático: es exactamente cómo reduce tail risk, aceptando que parte de las pérdidas quede realizada.

**Capped recovery.**

Una definición recomendable para investigación es preservar primero el stake legacy solicitado:

\[
s^*=
\frac{T+L}{o-1}
\]

y luego aplicar explícitamente:

\[
s=
\min(
s^*,
s_{\max},
cB_{\text{available}}
).
\]

Cuando \(s<s^*\), la política debe registrar:

- `cap_hit = true`;
- `requested_stake`;
- `applied_stake`;
- `recovery_shortfall`;
- si la secuencia continúa, se aborta o se resetea.

No debe simularse que el target se recuperó cuando el cap lo hizo imposible.

Cerrar una secuencia con pérdida **puede reducir drásticamente la cola** aun cuando “realice” el drawdown. No mejora mágicamente el edge: simplemente deja de seguir amplificando exposición. Busseti, Ryu y Boyd muestran de forma más general que crecimiento y probabilidad de drawdown forman un trade-off controlable; minimizar drawdown es un objetivo distinto de maximizar crecimiento. [Busseti et al. 2016]

**Progression comparators.**

| sistema | relación con legacy | ¿crea EV? | crecimiento dominante | disposición FS-004 |
|---|---|---|---|---|
| Martingale | legacy a \(o=2\) | No | geométrico \(2^k\) | Sólo referencia matemática |
| Anti-Martingale / Paroli | aumenta tras wins | No por sí mismo | depende de racha ganadora | No implementar; fixed-fraction responde mejor |
| Fibonacci | escalamiento por secuencia | No | sub-Martingale pero creciente | Rechazar |
| d'Alembert | suma/resta unidades | No | aproximadamente lineal en pérdidas | Rechazar |
| Labouchère | lista/cancelación target | No | path-dependent, cola compleja | Rechazar |
| Oscar's Grind | progresión hasta target | No | más lenta | Rechazar |

Labouchère merece únicamente una nota porque existe análisis matemático específico de su maximal bet y se conocen regímenes donde el volumen apostado y déficit tienen esperanza infinita; esto refuerza, no debilita, la decisión de no ampliar FS-004 con progresiones folclóricas. [Han & Wang 2019; Zubrilina 2018]

**Tabla requerida: clasificación de evidencia legacy.**

| comportamiento legacy | equivalente publicado | concepto matemático relacionado | intuición plausible pero no probada | regla no soportada | disposición recomendada |
|---|---|---|---|---|---|
| `T = first_bet*(first_odd-1)` | target/unit-win staking | target profit | “mantener una ganancia nominal constante” | que ese target sea óptimo | Reproducir sólo en legacy |
| \((T+L)/(o-1)\) | full-loss-recovery ajustado por payoff | stopping + progresión geométrica con \(o\) constante | recuperar en el siguiente win | que recovery mejore EV | Mantener como comparator |
| `ceil()` | sin necesidad matemática | discretización one-sided | asegurar recuperación completa | que proteja riesgo | Reproducir sólo en legacy; no heredar |
| `DEVIATION=1` | target constante | escala lineal en \(T\) | beneficio estable por secuencia | optimalidad del target | No generalizar |
| max iteration observado 14 | evidencia histórica | tail de secuencia | refleja situaciones reales que ocurrieron | que 14 sea máximo futuro | Usar como stress floor, no cap |
| `BetTable` / secuencias | sequence accounting | state machine | aislamiento operativo | independencia estadística | Rediseñar abstracción |
| floats monetarios | ninguna ventaja | error numérico | comodidad histórica | suficiencia para canonical settlement | Sustituir por decimal explícito |
| WON/LOST históricos | etiquetas de backup | outcome semantics | posible fuente auxiliar | profitability ground truth | No usar sin reconciliación |

Los conteos históricos del brief —736 tablas, 2,365 filas, 690 `WON`, 1,671 `LOST`, cuatro `CURRENT` y máximo observado de iteración 14— son evidencia descriptiva de estructura y longitud de secuencias, no una demostración de P&L. El propio brief advierte que settlement, outcomes, odds temporales y constantes históricas no permiten reconstruir limpiamente producción. [FS-004 Brief 2026]

## Riesgo de ruina, drawdown, streaks, correlación y concurrencia

**Ruin debe definirse operacionalmente.**

Con fixed-fraction continuo \(f<1\), el bankroll nunca llega matemáticamente a cero en un paso:

\[
B_{t+1}=B_t(1-f)>0.
\]

Pero eso no significa “sin riesgo de ruina”. Finsport debe definir **ruina práctica** como alguno de:

\[
B_t<B_{\min},
\]

\[
\text{stake requerido}>B_{\text{available}},
\]

\[
\text{drawdown}>D_{\max},
\]

o incapacidad de completar una secuencia según la política.

Esta definición es mucho más relevante para recovery.

Para una secuencia de máximo \(m\) apuestas con \(p\) constante:

\[
P(\text{fallo de secuencia})=q^m.
\]

En \(S\) secuencias independientes idénticas:

\[
P(\text{al menos un fallo})
=
1-(1-q^m)^S.
\]

Y, para cualquier \(q>0\), conforme \(S\to\infty\):

\[
P(\text{algún fallo})\to1.
\]

Ésta es la razón por la que “nunca vi una racha de \(m\)” no sirve como garantía futura. La teoría de longest runs muestra que el máximo de rachas aumenta con el tamaño de la muestra y tiene una distribución extrema, no un límite fijado por el histórico observado. [Gordon et al. 1986]

**Losing streak IID.**

Para un bloque específico de \(k\) apuestas:

\[
P(k\text{ pérdidas consecutivas})=q^k.
\]

Pero la probabilidad de que exista al menos una racha de longitud \(k\) entre \(N\) apuestas **no** es simplemente \(Nq^k\), porque las ventanas se solapan. Para FS-004 conviene obtenerla con:

- dynamic programming exacto para Bernoulli homogéneo;
- Monte Carlo;
- aproximaciones de teoría de runs sólo como chequeo.

La literatura de Gordon, Schilling y Waterman establece la conexión entre el longest run de Bernoulli y distribuciones extremas. [Gordon et al. 1986]

**Probabilidades variables.**

Para una racha concreta:

\[
P(L_i,\ldots,L_{i+k-1})
=
\prod_{j=i}^{i+k-1}(1-p_j)
\]

sólo bajo independencia condicional.

El simulador debe usar los \(p_i\) de FS-003 en orden cronológico; no reemplazarlos por el hit rate medio salvo en un escenario deliberadamente simplificado.

**Cómo construir streak stress prudentemente.**

No debe fijarse “máximo futuro = máximo histórico”. Deben construirse al menos tres niveles:

1. distribución de longest streak usando los \(\hat p_i\) nominales;
2. distribución usando probabilidades deterioradas compatibles con incertidumbre/calibration error;
3. escenario de régimen correlacionado en que un bloque completo reduce sus probabilidades de éxito.

El stress objetivo debe ser un cuántil alto —por ejemplo un cuántil parametrizado `q_stress`— de esa distribución y **no** un multiplicador arbitrario del máximo histórico. El valor numérico de `q_stress` es decisión posterior.

**Correlation y model drift.**

Same league, same matchday, clima, lesiones, cambios de estilo, proveedor de odds o un error compartido del modelo pueden hacer que los fallos se agrupen. En esas condiciones:

\[
P(L_t,L_{t+1})\neq P(L_t)P(L_{t+1}).
\]

La consecuencia para recovery es particularmente severa: la política aumenta stake precisamente durante el cluster adverso.

Para Kelly ocurre algo distinto pero igualmente importante: si hay múltiples apuestas simultáneas, aplicar el Kelly binario de cada una como si fuera independiente puede sobreasignar capital. La formulación correcta es vectorial:

\[
\max_{\mathbf f}
E[\log(W_{t+1}/W_t)]
\]

sobre la **distribución conjunta** de outcomes y sujeto a la restricción de capital. Kelly fue generalizado desde juegos con múltiples resultados; formulaciones modernas risk-constrained también tratan distribuciones generales. [Kelly 1956; Busseti et al. 2016]

**Block bootstrap.**

El bootstrap IID que baraja apuestas individuales destruye dependencia temporal. El stationary bootstrap de Politis y Romano fue precisamente diseñado para re-muestrear series débilmente dependientes mediante bloques de longitud aleatoria, preservando estructura local bajo sus supuestos de estacionariedad/dependencia débil. [Politis & Romano 1994]

Para Finsport, un block bootstrap puede agrupar por:

- ventana temporal;
- jornada;
- competición;
- bloques consecutivos de decisiones.

Pero no puede inventar regímenes que nunca aparecieron en los datos. Por eso debe coexistir con stress paramétrico explícito.

**Drawdown.**

Sea:

\[
M_t=\max_{u\le t}B_u.
\]

El drawdown porcentual es:

\[
D_t=1-\frac{B_t}{M_t},
\]

y:

\[
MDD=\max_t D_t.
\]

También importa la duración:

\[
\text{drawdown duration}
=
t_{\text{recovery}}-t_{\text{peak}}.
\]

Kelly completo puede maximizar crecimiento asintótico y, simultáneamente, presentar fuerte riesgo de corto plazo; fractional Kelly sacrifica crecimiento para reducir exposición, y risk-constrained Kelly incorpora directamente un límite probabilístico de drawdown. [MacLean et al. 2010; Busseti et al. 2016]

**VaR y Expected Shortfall.**

VaR informa un cuántil pero no cuánto se pierde **más allá** de ese cuántil. Expected Shortfall promedia la cola adversa y posee propiedades de coherencia que VaR no tiene en general; Acerbi y Tasche desarrollaron formalmente esta distinción. [Acerbi & Tasche 2002a; Acerbi & Tasche 2002b]

Para FS-004, ES sobre terminal loss o terminal return es preferible a VaR como métrica de cola primaria.

**Minimal risk metric set recomendado:**

| dimensión | métrica |
|---|---|
| solvencia | probability of practical ruin |
| path risk | maximum drawdown |
| path persistence | drawdown duration |
| threshold risk | \(P(MDD>d)\) para varios \(d\) |
| tail terminal | 1 % / 5 % lower terminal-bankroll quantile |
| tail mean | Expected Shortfall |
| concentration | maximum stake / pre-bet bankroll |
| absolute exposure | maximum single stake |
| recovery | incomplete/aborted sequence rate |
| capital contention | maximum % bankroll reserved/in play |
| turnover | total staked / normalized bankroll |
| efficiency | P&L / total staked |

VaR puede conservarse como descriptor secundario, no como único tail metric.

**Selection confidence versus stake.**

Deben permanecer separadas dos decisiones:

\[
\text{¿debo seleccionar esta oportunidad?}
\]

y:

\[
\text{¿qué exposición asigno si ya fue seleccionada?}
\]

El segundo nivel puede usar:

\[
\hat p,\quad o,\quad \hat e,
\]

pero también:

- uncertainty de \(\hat p\);
- calibration band;
- model disagreement;
- competencia;
- correlación con posiciones simultáneas;
- exposure ya comprometida.

Un stake que crece sólo porque “el modelo dice 80 % en vez de 70 %” es incompleto: el valor económico depende de la cuota:

\[
e=po-1.
\]

Kelly refleja exactamente esa relación.

**Concurrencia y secuencias.**

Una arquitectura moderna no debe devolver automáticamente `BetTable` al dominio. Debe distinguir:

```text
Bankroll
PolicyState
SequenceState?      # sólo políticas que lo requieran
OpenExposure
DecisionBatch
Settlement
```

Flat, fixed fraction y Kelly no necesitan un estado de “recuperación”.

Recovery sí necesita:

```text
target_profit
accumulated_loss
step
requested_stake
applied_stake
cap_status
reserved_bankroll
termination_reason
```

Múltiples secuencias con bankroll compartido introducen capital contention. Si dos apuestas empiezan antes de que ninguna liquide, no deben calcularse secuencialmente utilizando beneficios aún inexistentes. Deben formar un batch:

\[
B_{\text{available}}
=
B_{\text{pre-batch}}
-
\sum s_j^{\text{reserved}}.
\]

Todos los stakes del batch deben calcularse a partir de una política de reserva explícita.

Segmentar bankroll por secuencia puede contener contagio pero también inmoviliza capital. No existe razón matemática para presumir que sea superior.

**Recomendación de diseño.** El motor debe ser capaz de representar múltiples exposures concurrentes, pero el número de secuencias recovery simultáneas debe quedar parametrizado y **no congelarse antes de FS-003**.

Persistir una pérdida antigua para “recuperarla” mediante una apuesta futura no relacionada tampoco tiene un fundamento probabilístico. El accumulated loss es una convención contable de la política, no una propiedad económica de la próxima apuesta.

## Simulación, Monte Carlo, precisión y objetivo de optimización

La unidad central del simulador debería ser una decisión cronológica:

```text
Decision {
    id
    timestamp
    competition
    fixture
    model_id
    policy_id

    p_home
    p_draw
    p_away

    selected_outcome
    selected_probability
    selected_decimal_odd
    estimated_edge

    uncertainty_metadata?
    model_disagreement?

    realized_outcome
}
```

Más:

```text
SimulationConfig {
    normalized_initial_bankroll
    staking_policy
    sequence_policy?
    risk_limits
    stake_granularity?
    rounding_mode
}
```

Y estado:

```text
SimulationState {
    bankroll
    peak_bankroll
    reserved_capital
    open_exposures
    policy_state
    sequence_states
}
```

El resultado debe incluir:

```text
bankroll_path
stake_path
drawdown_path
sequence_path
cap_events
ruin_events
metrics
```

**La cronología es obligatoria.** No debe reordenarse una replay histórica para conseguir mejores secuencias. Cualquier reshuffle debe estar etiquetado explícitamente como bootstrap/stress experiment.

**Experimento A — Replay cronológico.**

Utiliza las decisiones FS-003 y outcomes realizados en su orden exacto.

Puede demostrar:

- qué habría hecho cada política sobre ese path;
- qué stakes habría solicitado;
- cuándo habría tocado caps;
- cuál habría sido el drawdown.

No demuestra por sí sola:

- estabilidad fuera de muestra;
- verdadera probabilidad de ruina;
- robustez a otro orden;
- que el edge observado sea estructural.

**Experimento B — Parametric Monte Carlo.**

Para cada decisión:

\[
Y_i\sim\operatorname{Bernoulli}(p_i)
\]

respecto del outcome seleccionado.

Conserva:

- timestamps;
- odds;
- decision mix;
- \(p_i\);
- concurrencia.

Varía outcomes.

Esto estima la distribución inducida por el modelo **si sus probabilidades fueran correctas**. Por ello no es stress de model risk.

**Experimento C — Probability perturbation.**

Ejecutar escenarios como:

\[
p_i'=\operatorname{clip}(p_i-\delta),
\]

o, preferentemente, perturbaciones derivadas de calibration residuals / reliability bands.

También puede emplearse:

\[
p_i'
=
p_{\text{market},i}
+
\rho(p_i-p_{\text{market},i})
\]

para simular shrinkage del edge.

Este experimento es crítico para fractional Kelly y recovery, porque ambos pueden deteriorarse fuertemente cuando un pequeño edge estimado desaparece. La literatura sobre Kelly bajo parameter uncertainty encuentra precisamente que reducir stakes puede mejorar el comportamiento out-of-sample frente al plug-in Kelly. [Baker & McHale 2013; Metel 2018]

**Experimento D — Odds perturbation.**

Reducir payout manteniendo \(p_i\):

\[
o_i'
=
1+(o_i-1)(1-h),
\]

donde \(h\) representa un haircut sobre el net payout.

Esto prueba cuánto del resultado depende de obtener exactamente la cuota registrada. No debe interpretarse como slippage real hasta que exista evidencia para calibrar \(h\).

**Experimento E — Losing-streak stress.**

Forzar rachas que superen el máximo observado y medir:

- stake requerido;
- bankroll requerido;
- cap hits;
- incomplete sequences;
- MDD.

La longitud stress debe provenir de quantiles del longest-run model y escenarios de error, no sólo de “14 + N”. La literatura de runs muestra por qué el máximo crece con el horizonte. [Gordon et al. 1986]

**Experimento F — Correlation / regime stress.**

Opciones de complejidad creciente:

\[
\operatorname{logit}(p_i')
=
\operatorname{logit}(p_i)+\gamma_{r(i)},
\]

donde \(\gamma_r<0\) representa un régimen adverso temporal/competitivo;

o un Markov regime:

```text
NORMAL -> DEGRADED
DEGRADED -> NORMAL
```

con \(p_i\) reducido durante el estado degradado.

No es necesario desplegar modelos sofisticados hasta ver los clusters de FS-003.

**Experimento G — Block/bootstrap.**

Re-muestrear bloques cronológicos de decisiones/outcomes. El stationary/bootstrap literature respalda el uso de bloques para mantener dependencia débil en series temporales. [Politis & Romano 1994]

El resultado debe compararse con parametric stress porque bootstrap sólo reproduce tipos de régimen ya vistos.

**Canonical bankroll representation.**

Recomendación:

\[
B_0=1
\]

internamente como capital normalizado, mostrando opcionalmente:

\[
100\text{ units}
\]

en reportes para legibilidad.

Así:

\[
s/B_0,\quad
T/B_0,\quad
MDD,\quad
s_{\max}/B
\]

son reproducibles y no contienen moneda.

No se está decidiendo aquí un bankroll real de “100”; es sólo una normalización dimensional.

**Canonical numerical representation.**

Para settlement y policy state:

- `Decimal`;
- odds construidas desde strings/decimales, no desde un float ya redondeado;
- precisión explícita;
- ninguna cuantización silenciosa;
- `stake_step` como parámetro separado;
- `rounding_mode` explícito;
- conservar `theoretical_stake` y `applied_stake`.

La documentación oficial de Python especifica que `Decimal` permite representación exacta de decimales y control de reglas de rounding, justamente las propiedades necesarias para auditar recovery. [Python Decimal 3.13]

`LEGACY_RECOVERY` debe reproducir el `ceil()` histórico. Las políticas modernas no deben heredarlo.

**Métricas de output requeridas.**

Return:

\[
\text{total P\&L},
\quad
ROI=\frac{P\&L}{\sum s_i},
\quad
B_T.
\]

CAGR sólo cuando el horizonte temporal tenga sentido comparable.

Risk:

\[
MDD,
\quad
\text{drawdown duration},
\quad
P(\text{ruin}),
\]

\[
P(MDD>x),
\quad
ES_\alpha,
\quad
Q_{1\%}(B_T),
\quad
Q_{5\%}(B_T),
\]

\[
\max s_i,
\quad
\max(s_i/B_{i^-}).
\]

Behavior:

```text
bets
wins / losses
hit rate
average win / loss
longest losing streak
sequence length distribution
incomplete sequences
cap hits
capital reserved/in play
```

Efficiency:

```text
profit per unit staked
turnover
stake concentration
time to drawdown recovery
```

**Objetivo de optimización.**

No recomiendo reducir FS-004 a un único scalar objective. El objetivo del producto contiene simultáneamente crecimiento, frecuencia, drawdown y tail loss.

El resultado correcto es una **Pareto frontier**:

\[
\text{return}
\leftrightarrow
\text{MDD}
\leftrightarrow
P(\text{ruin})
\leftrightarrow
ES
\leftrightarrow
\text{coverage}
\leftrightarrow
\text{stake concentration}.
\]

Después podrán evaluarse formulaciones como:

\[
\max E[\log B_T]
\]

sujeto a:

\[
P(MDD>D^*)\le\alpha,
\]

o:

\[
\max E[B_T]
\]

sujeto a restricciones de ruin/drawdown.

Risk-constrained Kelly demuestra que este tipo de formulación de crecimiento sujeto a riesgo es matemáticamente viable y distinto de full Kelly. [Busseti et al. 2016]

“Maximizar hit rate” es especialmente peligroso como objetivo de staking: con un conjunto fijo de apuestas, cambiar stake **no modifica cuáles outcomes ganan**. Recovery sólo puede inflar una métrica artificial como “secuencias terminadas positivamente”. Esa métrica debe reportarse como comportamiento, nunca optimizarse aislada.

# Inputs pendientes de FS-003

Los siguientes inputs son necesarios para convertir esta investigación en una comparación Finsport-specific. Todos están alineados con el contrato del brief. [FS-004 Brief 2026]

| input FS-003 | flat | fixed fraction | target no recovery | legacy recovery | capped/partial | fractional Kelly |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| model/policy identity | R | R | R | R | R | R |
| sample size | R | R | R | R | R | R |
| prediction coverage | R | R | R | R | R | R |
| decision coverage | R | R | R | R | R | R |
| HOME/DRAW/AWAY mix | R | R | R | R | R | R |
| selected odds distribution | R | R | R | R | R | R |
| hit rate overall | R | R | R | R | R | R |
| hit rate by outcome | R | R | R | R | R | R |
| hit rate by odds band | R | R | R | R | R | R |
| hit rate by confidence band | útil | útil | útil | útil | útil | R |
| calibration/reliability | útil | útil | útil | útil | R | **R** |
| estimated EV distribution | R | R | R | R | R | **R** |
| flat-unit P&L/ROI | **R** | **R** | **R** | **R** | **R** | **R** |
| longest losing streak | R | R | R | **R** | **R** | R |
| losing-streak distribution | útil | útil | útil | **R** | **R** | R |
| loss clusters time/competition | útil | R | útil | **R** | **R** | **R** |
| market coverage | R | R | R | R | R | R |
| timestamp-valid price coverage | **R** | **R** | **R** | **R** | **R** | **R** |
| model disagreement | opcional | opcional | opcional | opcional | útil | R si disponible |
| chronological decision-level handoff | **R** | **R** | **R** | **R** | **R** | **R** |

`R` = required para una comparación seria; **R** marca inputs particularmente críticos.

No basta con un agregado “hit rate = x %”. Para replay y Monte Carlo, el handoff ideal debe ser fila por decisión:

```text
timestamp
competition
fixture_id
model_id
decision_policy_id

p_home
p_draw
p_away

selected_outcome
selected_probability
selected_decimal_odd
estimated_edge

realized_outcome

market_probability?       # si está disponible
model_disagreement?       # si está disponible
```

**Tabla requerida: estado de parámetros.**

| parámetro | restricción teórica | rango respaldado por teoría | ¿calibrar con FS-003? | ¿decisión usuario/producto? | riesgo de mala especificación |
|---|---|---|:---:|:---:|---|
| bankroll económico | \(>0\) | no universal | No | **Sí** | escala de riesgo incorrecta |
| bankroll normalizado | \(>0\) | escala arbitraria | No | No | sólo reporting |
| flat unit \(u/B_0\) | \(>0\) | no universal | **Sí** | Sí | ruin/drawdown |
| target \(T/B_0\) | \(>0\) | no universal | **Sí** | Sí | crecimiento lineal de toda la exposición |
| fixed fraction \(f\) | \(0<f<1\) | dominio matemático | **Sí** | Sí | overbetting |
| Kelly fraction \(\lambda\) | \(0<\lambda\le1\) | fractional Kelly | **Sí** | Sí | overbetting/under-utilization |
| minimum edge | \(e>0\) para EV positivo | no universal | **Sí** | Sí | false positive edges |
| recovery \(\alpha\) | \(0\le\alpha\le1\) | dominio de definición | **Sí** | Sí | tail amplification |
| max stake / bankroll | \(0<c\le1\) | no universal | **Sí** | **Sí** | concentración/ruina |
| max sequence steps | entero \(\ge1\) | no universal | **Sí** | Sí | tail truncation insuficiente |
| max drawdown | \(0<D<1\) | no universal | No | **Sí** | política incompatible con tolerancia |
| ruin threshold | \(0<B_{\min}<B_0\) | no universal | No | **Sí** | métricas sin significado operativo |
| uncertainty haircut | probabilidades en [0,1] | no universal | **Sí** | parcialmente | falsa confianza |
| market shrinkage \(\rho\) | \(0\le\rho\le1\) | dominio natural | **Sí** | No principalmente | edge exagerado o borrado |
| concurrent sequences | entero \(\ge1\) | no universal | **Sí** | Sí | contention/correlated tail |
| stake granularity | \(>0\) si activa | no universal | No | Sí | rounding drift |
| rounding mode | explícito | no óptimo universal | No | Sí | sesgo sistemático |
| MC paths | suficiente para estabilizar tails | depende del quantile | tras diseño | No | ES/ruin imprecisos |
| stress quantile | \(0<q<1\) | no universal | parcialmente | **Sí** | stress demasiado débil/fuerte |

No hay respaldo para inventar ahora valores como “half Kelly”, “5 % bankroll cap” o “tres recovery steps” y declararlos óptimos. La literatura soporta **la familia**, no esos thresholds Finsport-specific. Fractional Kelly está bien fundamentado como reducción de exposición respecto de Kelly completo, pero la fracción adecuada depende del objetivo y de la incertidumbre. [MacLean et al. 2010; Baker & McHale 2013]

**Decisiones posibles ahora.**

Puede congelarse que:

- `FLAT_UNIT` será baseline obligatorio;
- el legacy se denominará `LEGACY_RECOVERY` y conservará exactamente su fórmula cuando se reproduzca;
- el legacy es full-loss-recovery odds-adjusted;
- full recovery no crea edge;
- `ceil()` forma parte únicamente del comparator histórico;
- fixed fraction y fractional Kelly merecen comparación;
- la variante moderna de recovery debe tener riesgo explícitamente bounded;
- `BetTable` no es una abstracción obligatoria;
- las simulaciones deben ser cronológicas;
- correlación y calibration error deben stress-testearse;
- settlement/stake state debe utilizar aritmética decimal explícita;
- Expected Shortfall, MDD, ruin y stake concentration son métricas obligatorias.

**Decisiones que deben esperar FS-003.**

No deben congelarse todavía:

```text
starting economic bankroll
starting unit
target profit
max stake
max stake / bankroll
max recovery iterations
recovery percentage
risk-of-ruin tolerance
maximum acceptable drawdown
minimum edge
confidence threshold
Kelly fraction
number of concurrent recovery sequences
preferred staking policy
claim that legacy is safe/profitable
```

## How to ingest FS-003 results later

El informe puede actualizarse sin repetir la investigación:

1. Validar el handoff a nivel de decisión y su orden temporal.
2. Auditar cobertura de cuotas timestamp-valid.
3. Calcular distribución de \(o_i\), \(\hat p_i\), \(\hat e_i\) y outcome mix.
4. Mapear calibration/reliability por outcome, odds band y confidence band.
5. Caracterizar losing streaks y loss clusters.
6. Ejecutar `FLAT_UNIT` cronológico como ground benchmark.
7. Normalizar bankroll y parameterizar grids, sin elegir aún ganador.
8. Ejecutar `FIXED_FRACTION_BANKROLL`.
9. Ejecutar `FIXED_TARGET_PROFIT_NO_RECOVERY`.
10. Ejecutar `LEGACY_RECOVERY` exacto.
11. Ejecutar `LEGACY_CAPPED`; `LEGACY_PARTIAL` como sensibilidad.
12. Ejecutar `FRACTIONAL_KELLY` sólo con variantes de probabilidad nominal y conservadora.
13. Ejecutar Monte Carlo nominal.
14. Perturbar \(p\).
15. Perturbar odds.
16. Stress-testear streaks.
17. Stress-testear correlation/regime.
18. Ejecutar block bootstrap donde el volumen lo permita.
19. Construir Pareto frontier return–MDD–ES–ruin–turnover.
20. Falsificar políticas dominadas.
21. Sólo entonces congelar decisiones para el ticket FS-004.

Las conclusiones matemáticas sobre EV, crecimiento de recovery, rounding, necesidad de flat baseline y error de estimación **no necesitan revisarse**. Deben revisarse únicamente las decisiones numéricas y la selección final de política.

## Recommended FS-004 experiment after FS-003

El primer FS-004 no debería convertirse en una biblioteca enciclopédica de staking. Debe responder la pregunta causalmente importante: **dada la misma secuencia de decisiones FS-003, ¿qué distribución de capital produce cada familia razonable y qué riesgo adicional compra cualquier mejora de retorno?**

**Tabla requerida: comparación final de políticas candidatas.**

| policy | fórmula | ¿requiere edge positivo para ser rentable? | beneficio principal | riesgo principal | tail behavior | parámetros | inputs FS-003 | complejidad | ¿primer experimento? | confianza |
|---|---|:---:|---|---|---|---|---|---|:---:|---|
| `FLAT_UNIT` | \(s=u\) | Sí | benchmark puro de selección | exposición relativa sube tras DD | aditivo | \(u\) | odds, outcome, chronology | baja | **Sí** | muy alta |
| `FIXED_FRACTION_BANKROLL` | \(s=fB\) | Sí | exposure scaling + compounding | overbet si \(f\) alto | multiplicativo | \(f\) | chronology, odds, outcomes | baja | **Sí** | muy alta |
| `FIXED_TARGET_PROFIT_NO_RECOVERY` | \(s=T/(o-1)\) | Sí | aísla componente target del legacy | overweight de low odds | mayor heteroscedasticidad | \(T\) | odds | baja | **Sí**, como control diagnóstico | alta |
| `LEGACY_RECOVERY` | \(\lceil(T+L)/(o-1)\rceil\) | Sí | fidelidad histórica; falsifica recovery | stake explosion | cola extremadamente concentrada | \(T\), sequence semantics | odds, chronology, streaks | media | **Sí**, sólo comparator | muy alta sobre mecánica; ninguna sobre conveniencia |
| `LEGACY_CAPPED` | \(\min[s^*,cB,s_{\max}]\) | Sí | prueba recovery con hard risk bound | cap deja pérdidas sin recuperar | truncada pero path-dependent | cap, stop/reset | clusters, streaks, odds | media | **Sí** | alta |
| `LEGACY_PARTIAL` | \((T+\alpha L)/(o-1)\) | Sí | reduce escalamiento | puede cerrar win con P&L neto negativo | entre target y full recovery | \(\alpha,T\) | streaks, odds | media | Sensibilidad | alta |
| `FRACTIONAL_KELLY` | \(B\lambda\max[0,(po-1)/(o-1)]\) | **Sí** | vincula stake al edge y capital | probability error/correlation | multiplicativa; DD sensible a \(\lambda\) | \(\lambda,p_{\text{adj}}\) | **calibration, EV, odds** | media | **Sí si FS-003 soporta p** | alta teóricamente; condicionada empíricamente |

La shortlist primaria, por tanto, es:

```text
FLAT_UNIT
FIXED_FRACTION_BANKROLL
LEGACY_RECOVERY
LEGACY_CAPPED
FRACTIONAL_KELLY
```

y como controles:

```text
FIXED_TARGET_PROFIT_NO_RECOVERY
LEGACY_PARTIAL
```

No introduciría Fibonacci, d'Alembert, Labouchère ni Oscar's Grind.

**Experimental state mínimo.**

```text
NormalizedBankroll
PeakBankroll
AvailableBankroll
ReservedBankroll

ChronologicalDecision[]

PolicyConfig

PolicyState {
    only what the policy needs
}

SequenceState? {
    target
    accumulated_loss
    step
    requested_stake
    applied_stake
    cap_hits
}
```

**Safety constraints experimentales.**

Aunque todo sea simulación:

```text
no negative bankroll
no stake > available capital
explicit concurrency reservation
explicit max stake constraint
explicit sequence termination reason
no use of future outcomes
no temporal reshuffling in replay
no implicit float/rounding semantics
no silently missing odds
no treating invalid historical prices as valid
```

**Falsification / rejection criteria.**

Una recovery policy debe rechazarse si ocurre cualquiera de estas clases de resultado:

**Dominancia.** Existe otra política con retorno igual o superior y simultáneamente menor MDD, menor ES, menor probability of ruin y menor stake concentration bajo el mismo dataset/stress.

**Positive-median illusion.** La mediana es positiva o la tasa de secuencias ganadoras es alta, pero la esperanza, ES o lower-tail terminal wealth es inaceptable. El ejemplo de Martingale justo demuestra matemáticamente que esto puede ocurrir con una tasa de secuencias ganadoras superior al 98 %.

**Capital infeasible.** Un streak plausible exige:

\[
s_{\text{requested}}>B_{\text{available}}.
\]

**Cap dependency.** El resultado aparentemente bueno depende de un número de pasos justo por encima del máximo observado y colapsa al stress-testear un longest streak plausible.

**Calibration fragility.** Un deterioro de \(p\) compatible con el error de calibración de FS-003 cambia sustancialmente ROI, ruin o ES.

**Price fragility.** Pequeños deterioros de odds eliminan el edge.

**Correlation fragility.** IID Monte Carlo parece aceptable pero regime/block stress genera tail loss incompatible con el criterio posterior.

**Concentration.** Una fracción pequeña de apuestas consume una parte desproporcionada del turnover o del bankroll total sin compensación clara de retorno.

**Legacy non-value-add.** `LEGACY_RECOVERY` no mejora la Pareto frontier frente a flat/fixed-fraction/fractional-Kelly.

**Recovery non-value-add.** `LEGACY_CAPPED` no mejora la frontier frente a una simple reducción de fixed-fraction.

**Kelly invalidation.** Fractional Kelly debe retirarse como candidato principal si FS-003 no demuestra suficiente calibración/estabilidad para que el signo y magnitud del edge sean confiables. La literatura de parameter uncertainty respalda shrinkage precisamente porque los plug-in estimates pueden sobreapostar out-of-sample. [Baker & McHale 2013; Metel 2018]

**Qué significaría que recovery “funcione”.**

No basta:

```text
más secuencias ganadoras
```

ni:

```text
mayor terminal bankroll en la replay histórica
```

Debe superar una comparación Pareto razonable. Por ejemplo, si `LEGACY_CAPPED` obtiene algo más de retorno que fixed fraction pero aumenta materialmente:

\[
MDD,\quad
ES,\quad
P(\text{ruin}),\quad
\max(s/B),
\]

no puede decirse que sea mejor sin una función de utilidad que justifique ese intercambio.

En cambio, recovery merecería consideración adicional si, bajo replay **y** stress tests:

1. preserva edge positivo;
2. no depende de rachas históricamente truncadas;
3. mantiene cap-hit/ruin bajo los límites posteriormente aprobados;
4. ofrece una Pareto improvement o un trade-off explícitamente deseado;
5. es robusta a probability/odds perturbation;
6. no queda dominada por fixed fraction o fractional Kelly.

Mi expectativa teórica —claramente marcada como **inferencia, no resultado FS-003**— es que full legacy será difícil de justificar por su crecimiento geométrico de stakes, mientras que una capped derivative puede terminar comportándose más como una política de exposure control que como recuperación real. Eso sería una conclusión válida: implicaría que **la parte valiosa es el cap, no el recovery**.

**Historical-data limitations.**

Del backup histórico sí puede aprenderse:

```text
sequence lengths
iteration counts
stake escalation
observed odds
requested/applied stake relationships
frequency de cap/step-like behavior si está presente
```

y puede comprobarse si la ecuación recuperada explica los stakes observados dentro de tolerancia.

No debe inferirse directamente:

```text
true historical ROI
true win probability
true edge
profitability
calibration
risk of ruin
```

a partir de `WON/LOST` sin reconciliar canonical outcome, settlement y odds temporales. El brief documenta expresamente esas limitaciones y la discrepancia entre `MAX_ITERATION` encontrado en código y una iteración mayor observada en backup. [FS-004 Brief 2026]

**Decisión recomendada para cerrar el alcance futuro de FS-004.**

El futuro ticket debería ser un **motor de simulación comparativa**, no un “módulo de recovery”.

Su pregunta de aceptación debería ser:

> Dada una secuencia cronológica FS-003, ¿podemos reproducir deterministicamente las políticas candidatas, medir retorno y riesgo de cola, perturbarlas bajo incertidumbre y demostrar qué estrategias están dominadas?

No:

> ¿Cómo reimplementamos el viejo sistema de recuperación?

Eso preserva correctamente la separación:

```text
Prediction
→ Decision
→ Capital policy
```

y evita contaminar la evaluación de modelos con una progresión histórica que aún no ha demostrado valor.

## Referencias

### Fuentes internas del proyecto

- **[FS-004 Brief 2026]** Finsport. *FS-004 — Research brief: capital management, loss recovery, bankroll and risk*. 2026-08-26. Archivo interno del proyecto: `FS-004_research_brief.md`. `RESEARCH BRIEF — PRE-TICKET`.

### Probabilidad, gambling systems y Kelly

- **[Kelly 1956]** Kelly, J. L., Jr. “A New Interpretation of Information Rate.” *Bell System Technical Journal* 35(4), 1956, pp. 917–926. DOI: `10.1002/j.1538-7305.1956.tb03809.x`. URL estable: https://doi.org/10.1002/j.1538-7305.1956.tb03809.x

- **[Breiman 1961]** Breiman, Leo. “Optimal Gambling Systems for Favorable Games.” In *Proceedings of the Fourth Berkeley Symposium on Mathematical Statistics and Probability*, Vol. 1, University of California Press, 1961, pp. 65–78. DOI: no identificado. URL estable: https://digicoll.lib.berkeley.edu/record/112884

- **[Ferguson 1965]** Ferguson, Thomas S. “Betting Systems Which Minimize the Probability of Ruin.” *Journal of the Society for Industrial and Applied Mathematics* 13(3), 1965, pp. 795–818. DOI: `10.1137/0113051`. URL estable: https://doi.org/10.1137/0113051

- **[Liu 1999]** Liu, Wen. “A Theorem on Gambling Systems for Arbitrary Sequences of Random Variables.” *Bulletin of the London Mathematical Society* 31(5), 1999, pp. 607–615. DOI: `10.1112/S0024609399005913`. URL estable: https://doi.org/10.1112/S0024609399005913

- **[Dimitrov & Shafer 2025]** Dimitrov, Valentin, and Glenn Shafer. “The Martingale Index: A Measure of Self-Deception in Betting and Finance.” *Judgment and Decision Making* 20, 2025, e26, pp. 1–23. DOI: `10.1017/jdm.2025.12`. URL estable: https://doi.org/10.1017/jdm.2025.12

- **[Lazowski 2026]** Lazowski, Andrew. “Investigating Finite Step Martingale Strategies in Roulette.” *The Mathematical Gazette*, published online 2026-01-21, pp. 1–13. DOI: `10.1080/00255572.2025.2604906`. URL estable: https://doi.org/10.1080/00255572.2025.2604906

- **[MacLean et al. 2010]** MacLean, Leonard C., Edward O. Thorp, and William T. Ziemba. “Long-Term Capital Growth: The Good and Bad Properties of the Kelly and Fractional Kelly Capital Growth Criteria.” *Quantitative Finance* 10(7), 2010, pp. 681–687. DOI: `10.1080/14697688.2010.506108`. URL estable: https://doi.org/10.1080/14697688.2010.506108

- **[Baker & McHale 2013]** Baker, Rose D., and Ian G. McHale. “Optimal Betting Under Parameter Uncertainty: Improving the Kelly Criterion.” *Decision Analysis* 10(3), 2013, pp. 189–199. DOI: `10.1287/deca.2013.0271`. URL estable: https://doi.org/10.1287/deca.2013.0271

- **[Metel 2018]** Metel, Michael R. “Kelly Betting on Horse Races with Uncertainty in Probability Estimates.” *Decision Analysis* 15(1), 2018, pp. 47–52. DOI: `10.1287/deca.2017.0359`. URL estable: https://doi.org/10.1287/deca.2017.0359

- **[Sun & Boyd 2018]** Sun, Qingyun, and Stephen Boyd. *Distributional Robust Kelly Gambling: Optimal Strategy under Uncertainty in the Long-Run*. Manuscript / arXiv preprint, 2018; revised version available on arXiv. DOI (arXiv): `10.48550/arXiv.1812.10371`. URL estable: https://arxiv.org/abs/1812.10371

- **[Busseti et al. 2016]** Busseti, Enzo, Ernest K. Ryu, and Stephen Boyd. “Risk-Constrained Kelly Gambling.” *The Journal of Investing* 25(3), 2016, pp. 118–134. DOI: `10.3905/joi.2016.25.3.118`. URL estable: https://doi.org/10.3905/joi.2016.25.3.118

### Progression systems

- **[Han & Wang 2019]** Han, Yanjun, and Guanyang Wang. “Expectation of the Largest Bet Size in the Labouchere System.” *Electronic Communications in Probability* 24, 2019, Article 11. DOI: `10.1214/19-ECP220`. URL estable: https://doi.org/10.1214/19-ECP220

- **[Zubrilina 2018]** Zubrilina, Nina. *On the Expected Value of the Maximal Bet in the Labouchere System*. arXiv preprint, 2018. DOI (arXiv): `10.48550/arXiv.1808.06642`. URL estable: https://arxiv.org/abs/1808.06642

### Riesgo, drawdown y dependencia temporal

- **[Gordon et al. 1986]** Gordon, Louis, Mark F. Schilling, and Michael S. Waterman. “An Extreme Value Theory for Long Head Runs.” *Probability Theory and Related Fields* 72(2), 1986, pp. 279–287. DOI: `10.1007/BF00699107`. URL estable: https://doi.org/10.1007/BF00699107

- **[Politis & Romano 1994]** Politis, Dimitris N., and Joseph P. Romano. “The Stationary Bootstrap.” *Journal of the American Statistical Association* 89(428), 1994, pp. 1303–1313. DOI: `10.1080/01621459.1994.10476870`. URL estable: https://doi.org/10.1080/01621459.1994.10476870

- **[Acerbi & Tasche 2002a]** Acerbi, Carlo, and Dirk Tasche. “Expected Shortfall: A Natural Coherent Alternative to Value at Risk.” *Economic Notes* 31(2), 2002, pp. 379–388. DOI: `10.1111/1468-0300.00091`. URL estable: https://doi.org/10.1111/1468-0300.00091

- **[Acerbi & Tasche 2002b]** Acerbi, Carlo, and Dirk Tasche. “On the Coherence of Expected Shortfall.” *Journal of Banking & Finance* 26(7), 2002, pp. 1487–1503. DOI: `10.1016/S0378-4266(02)00283-2`. URL estable: https://doi.org/10.1016/S0378-4266(02)00283-2

### Sports betting, staking y eficiencia de mercado

- **[Barge-Gil & Garcia-Hiernaux 2020]** Barge-Gil, Andrés, and Alfredo Garcia-Hiernaux. “Staking in Sports Betting Under Unknown Probabilities: Practical Guide for Profitable Bettors.” *Journal of Sports Economics* 21(6), 2020, pp. 593–609. DOI: `10.1177/1527002520921227`. URL estable: https://doi.org/10.1177/1527002520921227

- **[Angelini & De Angelis 2019]** Angelini, Giovanni, and Luca De Angelis. “Efficiency of Online Football Betting Markets.” *International Journal of Forecasting* 35(2), 2019, pp. 712–721. DOI: `10.1016/j.ijforecast.2018.07.008`. URL estable: https://doi.org/10.1016/j.ijforecast.2018.07.008

- **[Elaad et al. 2020]** Elaad, Guy, J. James Reade, and Carl Singleton. “Information, Prices and Efficiency in an Online Betting Market.” *Finance Research Letters* 35, 2020, Article 101291. DOI: `10.1016/j.frl.2019.09.006`. URL estable: https://doi.org/10.1016/j.frl.2019.09.006

- **[Hegarty & Whelan 2025]** Hegarty, Tadgh, and Karl Whelan. “Forecasting Soccer Matches with Betting Odds: A Tale of Two Markets.” *International Journal of Forecasting* 41(2), 2025, pp. 803–820. DOI: `10.1016/j.ijforecast.2024.06.013`. URL estable: https://doi.org/10.1016/j.ijforecast.2024.06.013

### Documentación técnica

- **[Python Decimal 3.13]** Python Software Foundation. “`decimal` — Decimal fixed-point and floating-point arithmetic.” *Python 3.13 Documentation*. URL estable de rama: https://docs.python.org/3.13/library/decimal.html

---

Política teórica resultante para investigación:

\[
\boxed{
\text{edge primero}
\rightarrow
\text{stake después}
\rightarrow
\text{tail risk explícito}
}
\]

y, específicamente para la pregunta principal de FS-004:

\[
\boxed{
\text{loss recovery no mejora por sí sola el valor esperado;}
}
\]

\[
\boxed{
\text{redistribuye los resultados hacia ganancias pequeñas frecuentes y pérdidas raras mayores.}
}
\]

Sólo puede mejorar el resultado esperado cuando el cambio de stake está aprovechando **variación real en el edge condicional futuro**; en tal caso, el beneficio procede de esa información predictiva, no del hecho de estar recuperando una pérdida anterior. Con capital finito, cuotas variables, model error y clusters de derrotas, ésa es la distinción que el futuro experimento FS-004 debe intentar falsificar y medir, no asumir.
