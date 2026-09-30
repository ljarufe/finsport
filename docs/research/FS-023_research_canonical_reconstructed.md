# FS-023 — Investigación final canónica reconstruida: 28 LIVE, T−10, ResultProvider BSD/API-F, StrategyBinding/epochs y Experiment Lab subset

**Estado:** `FINAL / CANONICAL / RECONSTRUCTED`
**Fecha de cierre canónico:** 2026-09-29
**Research owner:** F010
**Proyecto:** Finsport
**Destino:** F008 → definición de FS-023 → F009/Codex
**Research disposition:** `CLOSED`
**Handoff:** `READY_FOR_F008`
**Durable evidence host gate:** `PASS`
**Apuestas reales:** `FORBIDDEN`
**Experimento final [209,216,223]:** `NOT RUN`
**Promotion:** `NOT PERFORMED`

## 0. Autoridad de este documento

Este archivo es la **única autoridad narrativa de research para FS-023**. Sustituye íntegramente tanto la investigación larga inicial como la versión corregida compacta. La reconstrucción aplica la siguiente regla de precedencia ya validada:

1. las correcciones posteriores mandan cuando modifican una decisión o resuelven una ambigüedad;
2. los contratos ejecutables de la investigación larga que no fueron contradichos se reincorporan aquí y vuelven a ser normativos;
3. los artifacts machine-readable autenticados mandan para identidades, hashes, mappings, corpus y evidencia empírica;
4. F001/F002/F003/F004/F006/F008/F009/F010 conservan autoridad durable en las materias que FS-023 no sustituye explícitamente.

No hay que reconstruir precedencia entre documentos anteriores durante F008, F009, implementación o experimentos: **este archivo es autocontenido**.

La verificación durable de evidencia ya fue completada por el maintainer en el host bajo `/home/ljarufe/Documents/finsport/research-evidence/FS-023/final/`; `sha256sum -c SHA256SUMS` devolvió `OK` para todos los artifacts compactos enumerados. El archive entregado `FS-023_final_evidence.tar.xz` también fue revalidado en el entorno de entrega con SHA-256 `156e335d831f9f7d244bb4ca83bb61a4bee84ac7c1fe47897081486c32b31f92` y `SHA256SUMS` completo en PASS.


---

# 1. Resumen ejecutivo y pregunta de research

La pregunta final de FS-023 fue:

> ¿Cómo ampliar el runtime simulado de Finsport desde las diez ligas actuales hasta un universo LIVE fijo de 28 ligas, mover la evidencia económica prospectiva a T−10, sostener esa cobertura bajo la cuota disponible, desacoplar resultados de API-Football, eliminar hardcodings de #209 y permitir una comparación posterior restringida de estrategias sin retuning ni pérdida de reproducibilidad?

Preguntas secundarias cerradas:

1. ¿Qué universo histórico usar para la siguiente comparación?
2. ¿Qué ventana económica debe sustituir T−30?
3. ¿Cómo operar 28 ligas sin prometer cobertura perfecta en días extremos?
4. ¿Cómo reducir la deuda de resultados sobre la cuota de API-Football?
5. ¿Cómo separar LIVE readiness de historical readiness?
6. ¿Cómo hacer sustituible una estrategia sin mezclar capital ni posiciones?
7. ¿Cómo permitir que Experiment Lab ejecute sólo candidatos concretos?
8. ¿Cómo preservar el selector económico de FS-021 sin retunearlo?
9. ¿Cómo parametrizar el benchmark de oportunidad?
10. ¿Qué artifacts deben sobrevivir para que el experimento post-implementación sea reproducible?

Todas quedan respondidas por este informe.

## 1.1 Resultado congelado

F008 puede definir un ticket implementable sin volver a investigar:

```text
LIVE universe               = 28 competiciones congeladas
prospective market window   = T−10 only
pipeline wake               = 180 s
result sources              = BSD + API-Football
historical primary corpus   = 2,605 Matches / 16 competiciones
restricted challenge        = [209,216,223]
default current candidate   = #209 hasta promoción explícita distinta
real betting                = false
```

El ticket puede introducir las persistencias/migrations necesarias, pero Codex no debe rediseñar las semánticas de proveedor, selección, epochs, drain, corpus, OLV o experimento.

---

# 2. Outcome del incremento y no objetivos

El objetivo único del incremento es:

```text
28 LIVE competitions
+ T−10 como única captura automática de mercado
+ wake 180 s
+ quota scheduling / OLV
+ ResultProvider BSD + API-Football
+ historical readiness desacoplada de LIVE
+ StrategyBinding + StrategyEpoch genéricos
+ switch/drain restart-safe
+ Experiment Lab por subset
+ capacidad posterior para [209] evaluation-only y [209,216,223] selection
```

La población histórica primaria permanece independiente del universo LIVE.

## 2.1 No objetivos

FS-023 **no debe crecer** para incluir:

- rediseño de frontend;
- nueva Home o `/daily/`;
- React/SPA;
- optimización GPU/native;
- trabajo general de performance;
- nuevas técnicas Prediction;
- R45/MAGI u otros challengers;
- nuevos thresholds de Decision;
- nuevas políticas Capital;
- Portfolio Kelly;
- aumento de `max_lanes`;
- routing de estrategia por rentabilidad de liga;
- selección de ligas por ROI;
- expansión LIVE más allá de las 28 congeladas;
- expansión histórica más allá de los 2,605 Matches congelados;
- tercera API de resultados para completar artificialmente 28/28;
- recuperación ficticia de capturas prospectivas perdidas;
- reejecución ceremonial de backfills ya completados;
- reejecución de Quality Gate;
- repetición de la comparación T30/T10/T5;
- ejecución de los 231 candidatos para poder ejecutar tres;
- apuestas reales;
- login/escritura en bookmaker;
- transferencia de dinero;
- promoción o activación automática de un ganador.

Los cambios visuales anteriores pertenecen a FS-022 y no se reabren aquí.

---

# 3. Baseline previo, autoridades y fases completadas

## 3.1 Baseline modificado

El baseline anterior conserva:

```text
Django
PostgreSQL
Redis/Celery
un único Celery Beat
Capital Runtime/Event-Time v2
PENDING_CAPACITY
OPEN continuity
same-wake settlement → placement
ProviderCallAudit
dynamic API-F quota authority
T+130 first result hint
+30m result retries
simulation-only
```

FS-023 cambia específicamente:

```text
300 s wake
→ 180 s

T−6h / T−60m / T−30m automatic market acquisition
→ T−10 only

10 LIVE competitions
→ 28 LIVE competitions

API-Football hardcoded OPEN result source
→ ResultProvider abstraction

#209 / market-t30m assumptions in runtime
→ immutable active StrategyBinding

single historically fixed integrated-run shape
→ optional candidate subset execution
```

Hasta que FS-023 se implemente y despliegue, los textos ACTIVE de F003/F004 que todavía describen 300 s, T6/T60/T30 y API-Football como result authority siguen describiendo el runtime anterior. Este informe especifica el delta; no debe fingirse que ya está desplegado.

## 3.2 Autoridades históricas preservadas

Las autoridades previas siguen preservadas:

```text
GLOBAL_PREDICTION_V1
→ MARKET_CONSENSUS / fs013-market-consensus-v2

GLOBAL_DECISION_V1 local
→ MODAL_ALL / fs003-modal-all-v1

GLOBAL_CAPITAL_V1 local
→ FRACTIONAL_KELLY(lambda=0.25, max_lanes=10)

FS-021 economic baseline
→ integrated candidate 209
→ MARKET_CONSENSUS × SELECTIVE_CONFIDENCE(0.45)
→ FRACTIONAL_KELLY(0.25,10)
```

`candidate 209` no es desde esta corrección una identidad suficiente para un runtime strategy binding.

## 3.3 Fases de investigación completadas

## 5.1. Local baseline / checkout

Se inspeccionaron:

- scheduler;
- Capture;
- Prediction/Decision;
- Capital;
- quota planner;
- provider adapters;
- Experiment Lab;
- strategy deployment;
- historical readiness;
- result lifecycle.

Se localizaron acoplamientos materiales a:

```text
market-t30m
candidate 209
API_FOOTBALL_CANONICAL
Competition.enabled ↔ historical coverage
231-candidate runner assumptions
```

## 5.2. Provider/capacity research

Se probaron:

- API-Football plan/acceso;
- catálogo de ligas;
- fixtures;
- odds;
- límites físicos;
- calendario;
- OddsPapi tournaments/fixtures/historical odds;
- Football-Data reconciliation;
- BSD leagues/events/live.

## 5.3. Local empirical research

Se ejecutaron:

- capacity baseline;
- T5 timing decomposition;
- historical reconstruction;
- corrected latest-state semantics;
- freshness sensitivity;
- T30/T10/T5 Capital replay;
- expansión SC/RO/CN;
- Quality Gate;
- primary population contract.

Ninguna de esas ejecuciones es el experimento final de selección.

---

# 4. Corpus histórico congelado y semántica histórica

La autoridad científica sigue siendo compuesta:

```text
A = state_corrected_common_T30_T10_T5.jsonl.gz
rows = 2059
SHA256 = f4e841ab89c303198b31e307b2fd7a76ffe65a9751a9908b131e6a2c1bbf15e8

B = eligible_common_T30_T10_T5.jsonl.gz
rows = 546
SHA256 = f15554f3180bbecc89bf17947f30ff2a075aaf92d5893cabd94160f94784151e

PRIMARY = A ∪ B by fixture_id
```

Validación ejecutada en esta corrección:

```text
rows(A)                    = 2059
rows(B)                    = 546
union                      = 2605
duplicates inside A        = 0
duplicates inside B        = 0
A/B fixture_id overlap     = 0
historical competitions    = 16
```

No se fabrica un tercer corpus para obtener una identidad; `ExperimentSpec` debe ligar ambos hashes + merge rule + 2605.

El contrato histórico continúa:

```text
16 competitions
2026-01-14 → 2026-09-27
257 days
37 ISO weeks
```

## 4.1 Distribución y contrato de población detallado

Artifact:

```text
tmp/FS-023_07c8/primary_population_contract.json
SHA-256:
e14501ed069e212bec3e4489bafaf12598c0bae5fd72254b9bfad7c71dd5f305
```

Distribución:

| País | Matches |
|---|---:|
| AT | 123 |
| BE | 150 |
| CH | 151 |
| CN | 199 |
| DK | 135 |
| FI | 141 |
| GR | 130 |
| IE | 150 |
| JP | 72 |
| MX | 84 |
| NO | 166 |
| PL | 210 |
| RO | 216 |
| SC | 131 |
| SE | 176 |
| US | 371 |
| **Total** | **2,605** |

Rango:

```text
first kickoff = 2026-01-14T19:30:00Z
last kickoff  = 2026-09-27T23:00:00Z
calendar span = 257 days
ISO weeks     = 37
competitions  = 16
```

El experimento post-implementación **debe consumir esta identidad**, no “lo que exista en DB ese día”.

## 4.2 Historical odds semantics

Para cada bookmaker/cutoff:

```text
1. states timestamp <= cutoff
2. choose latest timestamp
3. resolve same-timestamp conflicts
4. require active=true
5. require complete valid canonical 1X2 triplet
```

Prohibido filtrar `active=true` antes de elegir latest-state.

Histórico:

```text
freshness_cap = null
```

Una quote vieja puede ser válida si es el último state válido previo al cutoff; `active=false` invalida la reutilización de una activa anterior.

Market Consensus histórico requiere al menos dos tripletas 1X2 completas/activas.

## 4.3 Quality Gate histórico

El Quality Gate se ejecutó antes de observar una selección final de estrategia y no utiliza P&L como criterio de admisión.

Artifact:

```text
tmp/FS-023_07c7/league_quality_gate.json

SHA-256:
b04803256e2c4c39e0ee389aa7bde6bafb4406df7c813a596eb3e9a5b68bdbca
```

Conclusión añadidas:

```text
Scotland → PASS
China    → PASS
Romania  → PASS_WITH_NOTE
```

La nota de Rumania deriva principalmente de overround superior al envelope previo, sin anomalía equivalente que justifique exclusión en dispersión de books, favoritismo, margins, scores extremos o balance competitivo.

Regla:

```text
posterior poor strategy P&L in league X
!=
permission to remove league X
```

No puede hacerse cherry-picking de ligas después de ver resultados.

## 4.4 Evidencia T30/T10/T5 que justifica T10

Artifact:

```text
tmp/FS-023_07c5d/T30_T10_T5_capital_replay.json

SHA-256:
18b1aa792a8fb9e912fd1c309b7fc700d9ab5af108af31b8d0f35143b4080e9a
```

Este replay se ejecutó sobre los 2,059 Matches del corpus original corregido.

Capital:

```text
FRACTIONAL_KELLY
version = fs004-fractional-kelly-v1
lambda = 0.25
max_lanes = 10
```

T5 frente a T10:

```text
#209:
T5 − T10 equity ≈ −0.9833u

#216:
T5 − T10 equity ≈ −3.0938u

#223:
T5 − T10 equity ≈ −0.6639u
```

No hubo hard-risk failure ni operational depletion en T10/T5.

Interpretación:

```text
T5
→ no demuestra mejora que compense perder 5 minutos operacionales

T10
→ suficientemente cercano al kickoff
→ más margen operacional
→ target elegido
```

Esto es **timing research**, no elección final entre #209/#216/#223.

---

# 5. Contrato prospectivo T−10, scheduler y discovery

Después de FS-023:

```text
T−6h  → no future automatic calls
T−60m → no future automatic calls
T−30m → no future automatic calls
T−10m → only active prospective market window
T−5m  → diagnostic research only
```

Target:

```text
capture key       = market-t10m
offset            = 10m
normal late       = 3m
hard late         = 8m
post-kickoff      = never valid
wake              = 180 s
```

PENDING_CAPACITY del nuevo epoch congela T10; stake se recalcula con el Capital state actual si se libera capacidad pre-kickoff.

## 5.1 Contrato temporal completo

Después de FS-023:

```text
T−6h  → RETIRED for future automatic provider calls
T−60m → RETIRED
T−30m → RETIRED
T−10m → ONLY ACTIVE PROSPECTIVE MARKET WINDOW
T−5m  → NOT IMPLEMENTED; research diagnostic only
```

Timing normativo:

```text
capture key       = market-t10m
offset            = 10m
before tolerance  = 0m
normal late       = 3m
hard late         = 8m
earliest valid    ≈ T−10
normal zone       ≈ T−10 ... T−7
hard limit        ≈ T−2
kickoff+          = NEVER VALID
```

Toda evidencia económica prospectiva usada por Decision/Capital debe haber sido físicamente observada antes del kickoff. No se reconstruye retrospectivamente un `OddsObservation` faltante.

## 5.2 Discovery físico

La meta lógica sigue siendo:

```text
Lima today + tomorrow
```

La request física es la intersección entre ese horizonte lógico y las fechas accesibles por el plan efectivo del proveedor. No se amplía el horizonte por tener 28 ligas y no se usa `season sweep` como dependencia LIVE. Los contratos verificados siguen siendo:

```text
GET /fixtures?date=YYYY-MM-DD&timezone=America/Lima
GET /fixtures?id=<fixture_id>
```

No usar productivamente `ids=` sólo porque documentación genérica lo mencione.

## 5.3 Season-start smoke

`current_odds=true` en catálogo no es garantía eterna.

Para cada temporada:

```text
competition enters relevant season
→ bounded fixture smoke
→ bounded odds smoke when a representative fixture exists
```

Resultado:

```text
works
→ VERIFIED_CURRENT_SEASON

not currently available
→ TEMPORARILY_UNAVAILABLE
```

Una liga temporalmente indisponible:

```text
does not disable the other 27
does not reopen FS-023 research
```

El smoke debe usar request shapes realmente permitidos por el plan vigente.

---

# 6. Universo LIVE, capacidad y continuidad anual

| País | Competición | Local ID | API-F | BSD ID(s) | Route post-validation | Season interval observed |
|---|---|---:|---:|---|---|---|
| EN | Premier League | 1273 | 39 | 1 | BSD primary | 2026-08-21 → 2027-05-30 |
| FR | Ligue 1 | 1270 | 61 | 6 | BSD primary | 2026-08-21 → 2027-05-29 |
| BR | Serie A | 1272 | 71 | 9 | BSD primary | 2026-01-28 → 2026-12-02 |
| DE | Bundesliga | 1274 | 78 | 5 | BSD primary | 2026-08-28 → 2027-05-22 |
| NL | Eredivisie | 1276 | 88 | 10 | BSD primary | 2026-08-07 → 2027-05-23 |
| PT | Primeira Liga | 1277 | 94 | 2 | BSD primary | 2026-08-07 → 2027-05-16 |
| JP | J1 League | 1400 | 98 | 49 | BSD primary | 2026-08-07 → 2027-06-06 |
| NO | Eliteserien | 1480 | 103 | 54 | BSD primary | 2026-03-14 → 2026-12-13 |
| PL | Ekstraklasa | 1667 | 106 | 25 | BSD primary | 2026-07-24 → 2027-05-22 |
| SE | Allsvenskan | 1483 | 113 | 26 | BSD primary | 2026-04-04 → 2026-11-29 |
| DK | Superliga | 1288 | 119 | 84 | BSD primary | 2026-07-24 → 2027-03-21 |
| AR | Liga Profesional Argentina | 1459 | 128 | 85 | BSD primary | 2026-01-22 → 2026-11-08 |
| IT | Serie A | 1275 | 135 | 4 | BSD primary | 2026-08-22 → 2027-05-30 |
| ES | La Liga | 1278 | 140 | 3 | BSD primary | 2026-08-15 → 2027-05-30 |
| BE | Jupiler Pro League | 1271 | 144 | 14 | BSD primary | 2026-08-07 → 2027-05-22 |
| GR | Super League 1 | 1350 | 197 | 24 | BSD primary | 2026-08-22 → 2027-03-20 |
| TR | Süper Lig | 1325 | 203 | 11 | BSD primary | 2026-08-14 → 2027-05-23 |
| CH | Super League | 1489 | 207 | 15 | BSD primary | 2026-07-25 → 2027-02-07 |
| AT | Bundesliga | 1374 | 218 | 96 | BSD primary | 2026-07-31 → 2027-02-27 |
| CO | Primera A | 1492 | 239 | 80 | BSD primary | 2026-01-16 → 2026-11-12 |
| US | Major League Soccer | 1432 | 253 | 18 | BSD primary | 2026-02-21 → 2026-11-08 |
| MX | Liga MX | 1518 | 262 | 19, 20 | BSD primary | 2026-07-17 → 2026-11-23 |
| CL | Primera División | 1672 | 265 | — | API-F primary | 2026-01-30 → 2026-12-06 |
| UY | Primera División | 1434 | 268 | — | API-F primary | 2026-02-06 → 2026-10-05 |
| PE | Primera División | 1524 | 281 | — | API-F primary | 2026-01-30 → 2026-11-14 |
| KR | K League 1 | 1534 | 292 | 50 | BSD primary | 2026-02-28 → 2026-10-24 |
| CZ | Czech Liga | 1652 | 345 | — | API-F primary | 2026-07-25 → 2027-04-24 |
| IE | Premier Division | 1860 | 357 | — | API-F primary | 2026-02-06 → 2026-10-30 |

No añadir una liga 29 en este ticket.

Las 23 rutas BSD de la tabla son `BSD primary` **sólo después de bootstrap + shadow validation**. Antes de superar ese gate se comportan como API-F primary con BSD shadow, tal como se define más adelante.

## 6.1 Capacidad cuantitativa

## 8.1. Límite de la evidencia

`FS-023_07d2` intentó obtener fixture calendars de las 28 mediante consultas de temporada y el plan Free respondió `provider_access_denied` para las temporadas actuales. Por tanto:

```text
NO exact observed 28-league fixture-level daily distribution exists
```

Este informe no la inventa.

Se usa un **planning projection**, no una medición, calibrado contra evidencia real ya generada.

## 8.2. Calibración

Baseline de 10 ligas:

```text
observed 2025 matches = 3578
current-format season volume estimate = 3565
error = -0.36%
```

La coincidencia permite usar el volumen de temporada como factor de escala operacional.

Para las 28:

```text
23 BSD-mapped season/stage totals = 7191
5 API-F-only format-derived planning counts = 1262
--------------------------------------------------
planning full-season opportunities = 8453

scale vs baseline 10 = 8453 / 3565 = 2.3711
```

Los cinco planning counts son:

```text
CL 240
UY 296
PE 306
CZ 240
IE 180
```

Son valores de planificación por formato, no un fixture dump. Una sensibilidad ±10% sobre esos cinco modifica el factor total sólo ±1.5%, por lo que no cambia la conclusión de cuota.

## 8.3. Distribución T10 proyectada

La forma diaria empírica de una sola window para las 10 ligas fue:

```text
mean 9.81
p50  4
p90  35
p95  39
p99  47
max  57
```

Escalada por 2.3711:

| Métrica | T10 opportunities (planning projection) |
|---|---:|
| mean/day | 23.3 |
| p50 | 9.5 |
| p90 | 83.0 |
| p95 | 92.5 |
| p99 | 111.4 |
| max planning envelope | 135.2 |

Interpretación correcta:

```text
p90/p95/p99/max
= planning projection for 28
!= observed 28-league fixture distribution
```

Debe validarse operacionalmente una vez el nuevo runtime vea calendario real.

## 8.4. API-F total — escenarios

El plan vigente es ~100 requests/day. El scheduler protege discovery y T10; result work puede diferirse.

Los allowances no-T10 son budgets de planificación:

```text
NORMAL = 6/day
  ~2 discovery date calls
  + grouped result/recovery allowance
  + small operational margin

HIGH_CONCURRENCY = 10/day
  more recovery/fallback activity

CONSERVATIVE_BSD_FALLBACK = 20/day
  temporary shadow/degraded-BSD stress
```

| Scenario | Non-T10 API-F allowance | T10 budget | mean total | p90 total | p95 total | p99 total | max total | Miss planning band |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| NORMAL | 6 | 94 | 29.3 | 89.0 | 98.5 | 117.4 | 141.2 | ~1–5% tail days; use ~4% for planning |
| HIGH_CONCURRENCY | 10 | 90 | 33.3 | 93.0 | 102.5 | 121.4 | 145.2 | ~5–10%; use ~7% for planning |
| CONSERVATIVE_BSD_FALLBACK | 20 | 80 | 43.3 | 103.0 | 112.5 | 131.4 | 155.2 | ~10–15% |

Headroom normal:

```text
average: ~70.7 calls
p90:     ~11 calls
p95:     ~1.5 calls
p99:     quota exceeded by ~17 calls
```

Por tanto 28 **no promete 100% T10 coverage**. Es una frontera donde la mayoría de días tiene margen, mientras una cola pequeña exige degradación explícita.

## 8.5. `MISSED_STRATEGY_WINDOW`

Cuando el protected T10 budget se agota:

```text
eligible Match
+ no admitted physical T10 call before hard deadline due only to quota
→ MISSED_STRATEGY_WINDOW
```

No es `NO_BET` y no degrada Q de OLV.

Planning magnitude:

```text
NORMAL:
  miss days ≈ 1–5% tail band (use ~4% for capacity planning)
  p99 excess ≈ 17 T10 opportunities
  max envelope excess ≈ 41

HIGH_CONCURRENCY:
  ≈ 5–10% (use ~7%)
  p95 excess ≈ 2
  p99 excess ≈ 21

CONSERVATIVE_BSD_FALLBACK:
  ≈ 10–15%
  p90 excess ≈ 3
  p95 excess ≈ 12
  p99 excess ≈ 31
```

Estas frecuencias son interpolaciones de planning quantiles, no tasas observadas.

OLV determina qué T10 sobreviven al shortage; nunca elimina permanentemente una liga.

## 8.6. Throughput intradía

API-F Free también tiene límite aproximado de 10/min. El adapter existente ya usa minimum interval ~6 s.

El modelo 2025 de baseline + siete ligas seleccionadas mostró, para un subset incluido completamente dentro de las 28:

```text
max odds calls/day = 84
observed non-odds max = 14
max total = 98
longest inactive gap = 4 days
```

Otros subsets exactos mostraron same-minute peaks de hasta 15, drenables en ~84 s a 6 s/request.

No existe exact same-minute distribution de las 28; acceptance debe verificar que la queue deadline-aware no genere post-kickoff calls. La falta de ese fixture-level distribution no es permiso para elevar el rate limit.

## 6.2 Solapamiento anual y continuidad

## 9.1. Evidencia de continuidad ya existente

Baseline 10 en el modelo 2025:

```text
active days = 257
inactive days = 108
longest no-match gap = 28 days
2025-06-13 → 2025-07-10
```

Al añadir sólo siete ligas que forman parte de las 28 finales:

```text
AT, BE, IE, JP, NO, SE, US
```

el mismo modelado produjo:

```text
active days = 289
inactive days = 76
longest gap = 4 days
```

Como las 28 finales son un **superset** de ese conjunto de 17 ligas, en el mismo soporte de calendarios 2025 añadir las restantes no puede aumentar el gap. Por tanto:

```text
historical schedule-model upper bound for longest no-match gap
<= 4 days
```

No se declara el valor exacto de las 28 porque no se obtuvo el fixture calendar completo.

## 9.2. Principal overlap current/upcoming

Con los season intervals catalogados, las 28 latest seasons están simultáneamente activas desde:

```text
2026-08-28
through
2026-10-05
```

Es el período de mayor superposición y principal zona de riesgo de quota.

## 9.3. Menor actividad / off-season europeo

En junio y comienzos de julio, cuando las grandes ligas europeas tradicionales reducen actividad, el universo seleccionado conserva especialmente:

```text
Argentina
Brazil
Colombia
United States / MLS
Chile
Uruguay
Peru
South Korea
Ireland
Norway
Sweden
```

y Liga MX vuelve en julio.

Estas ligas fueron parte de la razón operacional para no construir un universo centrado únicamente en Europa.

## 9.4. Precaución temporal

El artifact `latest_season` tomado en septiembre de 2026 apunta principalmente a 2026/27 para Europa y no representa las temporadas 2025/26 ya terminadas. Por eso no se usa para fabricar estadísticas mensuales enero-junio. La continuidad se apoya en el schedule-model 2025 ya existente y en los intervals actuales sólo para overlap futuro.

---

# 7. Providers y contratos de fuente

## 7.1 Roles

## API-Football

Después de FS-023:

```text
fixture/discovery authority
prospective T10 odds source
result primary for 5 BSD-unsupported competitions
result fallback for BSD failures/shadow
```

Current physically accepted forms:

```text
GET /fixtures?date=YYYY-MM-DD&timezone=America/Lima
GET /fixtures?id=<fixture_id>
GET /odds?fixture=<fixture_id>  # with canonical pre-match 1X2 filters as existing adapter supports
```

No productive `ids=` assumption.

Free plan: ~100/day; season access remains plan-limited and must not be inferred from generic docs.

## Football-Data

Historical/reconciliation only; never OPEN settlement authority or prospective OddsObservation source.

## OddsPapi

Research historical market source only. Raw/cache remains external restricted evidence and is not copied into Git/final compact package.

## BSD

Result provider only in FS-023; no market/prediction dependency is added.

## 7.2 API-Football — autoridad y límites físicos

```text
fixture/discovery authority
prospective T10 odds source
result primary for BSD-unsupported competitions
result fallback where BSD fails/shadow
```

Contratos productivos:

```text
GET /fixtures?date=YYYY-MM-DD&timezone=America/Lima
GET /fixtures?id=<fixture_id>
GET /odds?fixture=<fixture_id>
```

El plan Free observado es aproximadamente 100 requests/day y ~10/min. La autoridad operacional es el estado persistido/observado de quota y headers, no un reset inventado por reloj. La evidencia física del plan local manda sobre documentación genérica cuando difieren.

## 7.3 Football-Data

Rol FS-023:

```text
historical sporting/result source
historical reconciliation input
research lineage
```

No se convierte en:

```text
prospective OddsObservation provider
OPEN Capital settlement provider
```

Los CSV y aliases que construyeron la población histórica permanecen research evidence.

## 7.4 OddsPapi

Rol:

```text
RESEARCH ONLY
historical fixture/market evidence
read-only
no operational scheduler
```

Usado para:

- tournament catalog;
- fixture reconciliation;
- bookmaker states;
- historical T30/T10/T5 reconstruction.

No puede:

- crear una falsa `OddsObservation` prospectiva;
- convertirse incidentalmente en provider automático de runtime;
- ser fuente de resultado canónico;
- justificar apuestas reales.

Raw/cache continúa `EXTERNAL_RESTRICTED`.

## 7.5 BSD — evidencia de preflight

El preflight físico demostró autenticación, catálogo, retrieval de eventos `finished`, endpoint live, estructura útil, IDs estables, score reglamentario separado de ET/penalties y rate-limit independiente. La muestra fue:

```text
physical requests       = 4
finished events sampled = 315
API-Football calls      = 0
DB mutations            = 0
local_terminal_matches  = 0
matched                 = 0
score_agreements        = 0
score_disagreements     = 0
```

Por tanto la concordancia local original quedó `INCONCLUSIVE_NO_COMPARISON_SAMPLE`; no se convierte en evidencia positiva. La mitigación normativa es el shadow-validation contract de este mismo documento.


---

# 8. BSD mapping, bootstrap, shadow validation y topology

## 8.1 Mapping congelado

`FS-023_bsd_league_mapping.json` is the machine-readable research artifact.

```text
LIVE selected = 28
BSD-mapped    = 23
API-F-only    = 5
```

México usa el set BSD Apertura/Clausura; event identity debe resolver a exactamente una competición/evento efectivo.

Runtime no fuzzy-matchea nombres de ligas.

## 8.2 Bootstrap de team/event identity

La versión previa exigía TeamSourceRef/alias pero no definía cómo nacían. Se congela así.

## 13.1. Competition mapping

Se instala desde el artifact explícito de 28; no se descubre por fuzzy names en runtime.

## 13.2. Bootstrap command/process

FS-023 debe disponer de una operación idempotente de bootstrap/reconcile BSD. El nombre exacto del management command lo decide Codex.

Para cada BSD league/season:

```http
GET /api/v2/teams/?league_id=<bsd_league_id>&season_id=<bsd_season_id>&in_competition=true&limit=200&offset=0
```

y:

```http
GET /api/v2/events/?league_id=<bsd_league_id>&season_id=<bsd_season_id>&date_from=<UTC date>&date_to=<UTC date+14>&limit=200&offset=0
```

seguir pagination `next`/`offset` si existe.

## 13.3. Team mapping automation

Puede auto-proponerse/auto-aceptarse sólo cuando:

```text
canonical local Team
and BSD Team
→ exact unique match after deterministic normalization of Unicode/case/whitespace/punctuation
```

No eliminar tokens semánticos ni aceptar similarity score.

Todo caso no exacto:

```text
→ proposal only
→ human review required
→ explicit approved alias/source mapping
```

La revisión registra:

```text
local_team_id
bsd_team_id
provider name
approved alias if needed
mapping version
approved_at / provenance
```

Los nombres pueden sugerirse automáticamente; la decisión no exacta no.

## 13.4. Event bootstrap

Con team mappings ya aprobados:

```text
mapped BSD league
+ mapped home_team_id
+ mapped away_team_id
+ abs(kickoff difference) <= 15 min
→ exactly one event required
```

Si único:

```text
persist BSD event_id / MatchSourceRef
```

Después de persistido, el runtime usa ID; no vuelve a resolver por nombres.

## 13.5. 0 / >1 candidatos

```text
0  → BSD_IDENTITY_UNRESOLVED
>1 → BSD_IDENTITY_AMBIGUOUS
```

No guess.

## 13.6. Readiness de liga

Una liga no se considera efectivamente `BSD primary` sólo porque exista competition mapping.

Estados conceptuales:

```text
BSD_NOT_CONFIGURED
BSD_BOOTSTRAP_PENDING
BSD_SHADOW_VALIDATION
BSD_PRIMARY_VALIDATED
BSD_DEGRADED
```

Una competición puede arrancar:

```text
BSD_BOOTSTRAP_PENDING
→ API-F result authority
```

hasta que los teams relevantes tengan mapping y event bootstrap sea utilizable.

Esto evita un deployment “BSD primary” nominal con cero mappings.

## 8.3 Shadow validation

El preflight observó:

```text
finished events = 315
local terminal comparison sample = 0
score agreements = 0
score disagreements = 0
```

Disposición permanece:

```text
INCONCLUSIVE_NO_COMPARISON_SAMPLE
```

No se declara concordancia.

## 14.1. Fase SHADOW

Al desplegar FS-023:

```text
BSD observations are collected
BUT
API-F remains settlement authority for BSD-supported competitions
```

hasta superar el gate de validación.

BSD durante shadow no puede afectar P&L.

## 14.2. Generación de muestra

Usar Matches Finsport que:

- tengan BSD event_id resuelto;
- lleguen a terminal;
- tengan observación terminal BSD;
- tengan también resultado terminal API-F obtenido por lifecycle normal.

No hacer per-match API-F calls sólo para llenar rápidamente la muestra.

Si el muestreo no avanza, se permite como máximo:

```text
1 extra API-F date sweep per Lima day
```

sólo con **surplus** después de discovery/T10 reserves, escogiendo un día con múltiples BSD terminal candidates para maximizar matches/request.

## 14.3. Gate inicial

Para promover provider state de SHADOW a PRIMARY_VALIDATED:

```text
>= 30 comparable terminal matches
>= 5 BSD-supported competitions
>= 7 distinct Lima dates
100% H/D/A agreement
100% regulation-time score agreement
0 confirmed material conflicts
```

No se exige que todas las 23 ligas hayan producido muestra antes de provider validation; cada competition sí debe tener identity/bootstrap ready antes de usar BSD allí.

## 14.4. Métricas

Persistir/mostrar:

```text
sample_count
competition_count
distinct_dates
identity_resolution_success/failure
regulation_score_agreements
outcome_agreements
status agreement
disagreements
bsd_observed_at
api_f_observed_at
latency_delta
confirmed_conflicts
```

## 14.5. Qué constituye conflicto

Una diferencia inicial no se declara material mientras pueda ser feed lag.

Confirm conflict sólo si:

```text
BSD terminal
+ API-F terminal
+ scores/outcome differ
+ BSD detail re-check >=30m after first BSD terminal still differs
```

Durante shadow API-F sigue siendo settlement authority, por lo que ese conflicto no contamina P&L.

## 14.6. Después del gate

`BSD_PRIMARY_VALIDATED` permite:

```text
BSD finished valid
→ settle without mandatory same-match API-F call
```

## 14.7. Sentinel validation

Tras validación:

**Probation:**

```text
1 surplus API-F date sweep per ISO week
until cumulative comparable sample >=100
and >=10 BSD competitions represented
and 0 confirmed conflicts
```

Comparar todos los BSD-settled Matches que caigan en ese sweep.

Después:

```text
STEADY
→ 1 surplus cross-check date sweep per calendar month
```

No dedicated per-match polling.

## 14.8. Degradation

```text
1 confirmed conflict
→ affected competition BSD_DEGRADED
→ API-F primary there

>=2 confirmed conflicts in distinct competitions within rolling 30d
→ provider-global BSD_DEGRADED
→ API-F primary for all until explicit review/revalidation
```

Un conflict descubierto después de settlement no reescribe silenciosamente P&L; crea durable conflict y exige reconciliación explícita.

## 8.4 Physical topology

Official base/auth:

```text
Base URL: https://sports.bzzoiro.com/api/v2/
Authorization: Token <secret>
```

Pagination:

```text
limit default 50
max 200
offset
follow next until null
```

All dates UTC ISO-8601.

## 15.1. Bootstrap operations

| Operation | Method / endpoint | Params | Expected requests |
|---|---|---|---:|
| catalog verification | `GET /leagues/` | `limit=200&offset=0` | 1 for observed 88 catalog |
| team bootstrap | `GET /teams/` | `league_id`, `season_id`, `in_competition=true`, `limit=200`, `offset` | normally 1 per BSD league ID |
| event prebind | `GET /events/` | `league_id`, `season_id`, `date_from`, `date_to`, `limit=200`, `offset` | normally 1 per league/window |

México puede implicar dos BSD league IDs.

Bootstrap completo esperado, sin pagination extraordinaria:

```text
~1 catalog + ~24 team calls + ~24 event-window calls
≈49 one-time BSD requests
```

No se ejecutan cada wake.

## 15.2. Runtime bound result

```http
GET /api/v2/events/<event_id>/
```

Expected:

```text
1 physical BSD request per due logical attempt
```

## 15.3. Missing/stale event_id recovery

Un solo collection lookup:

```http
GET /api/v2/events/?league_id=<id>&date_from=<kickoff_UTC_date-1>&date_to=<kickoff_UTC_date+1>&limit=200&offset=0
```

Local filter con team IDs + ±15 min.

Si no produce exactamente uno:

```text
→ unresolved/ambiguous
→ API-F fallback
```

No repetir collection scan en cada wake sin state change.

## 15.4. `/events/live/`

```text
NOT used by automatic FS-023 settlement lifecycle
```

Puede usarse manualmente en UAT/diagnóstico. El result lifecycle es event-by-ID para evitar polling global innecesario.

## 8.5 Timeout, retry, backoff y circuit breaker

## 16.1. Client timeout

```text
connect timeout = 3 s
read timeout    = 10 s
```

## 16.2. Network / timeout / 5xx / 503

Si circuit cerrado:

```text
attempt 1
→ fixed 2 s backoff
→ at most one same-logical-attempt retry
```

Si todavía falla:

```text
same-wake API-F fallback allowed if API-F quota admits
```

Circuit:

```text
3 consecutive provider logical failures within 10 min
→ open 15 min

half-open failure
→ 30 min
then 60 min max

successful half-open request
→ close/reset circuit
```

Mientras open:

```text
0 BSD calls
→ API-F routing/fallback
```

## 16.3. HTTP 400

Programming/config contract error:

```text
no retry
visible error
fallback API-F
counts toward provider/config incident
```

No loop por wake.

## 16.4. HTTP 401

```text
BSD_AUTH_FAILED
no retry
persistent provider circuit open
until secret/config generation changes or explicit health recheck
API-F fallback
```

No hacer un 401 cada 180 s.

## 16.5. HTTP 402

```text
BSD_ENTITLEMENT_FAILED
no retry
persistent disable until explicit operator/config review
API-F fallback
```

FS-023 result endpoints deberían ser free; 402 se trata como contract/config error, no transient outage.

## 16.6. HTTP 404 on bound event

```text
mark bound event stale/unresolved
no retry of same event_id
allow one collection rebind lookup same wake
if no unique replacement → API-F fallback
```

## 16.7. HTTP 429

BSD distingue:

```text
rate_limited      # IP burst
taster_exhausted  # daily quota
```

`rate_limited`:

```text
respect Retry-After
if <=5s → at most one retry
if >5s  → set backoff_until, no blocking loop, API-F fallback
```

`taster_exhausted`:

```text
open global BSD circuit until Retry-After / UTC reset
no early retry
API-F fallback
```

## 16.8. Malformed payload

```text
no same-wake retry of identical response path
record RESULT_PROVIDER_MALFORMED
API-F fallback
counts toward consecutive-provider-failure circuit
```

## 16.9. Identity failure

`UNRESOLVED`/`AMBIGUOUS` es competition/match identity failure, no provider outage global. Fallback API-F sin abrir circuit global.

## 8.6 Configuración y credenciales

BSD requiere token externo.

Semántica operacional:

```text
secret injected through host/runtime secret environment
same security class as other provider keys
NOT stored in Git
NOT printed
NOT copied to research artifacts
```

El nombre final de la variable lo decide la implementación, pero debe ser un secret operacional explícito.

## 17.1. Ausencia de credential

Decisión congelada:

```text
BSD credential absent
→ Finsport startup SUCCEEDS
→ BSD state = BSD_NOT_CONFIGURED
→ zero BSD calls
→ API-F result route becomes effective fallback/primary
```

No bloquear todo Finsport por un provider auxiliar no configurado.

Esto puede aumentar deuda API-F y `MISSED_STRATEGY_WINDOW`, pero es degradación visible, no startup failure.

## 17.2. Distinción de estados

```text
BSD_NOT_CONFIGURED   = no secret supplied
BSD_AUTH_FAILED      = secret supplied but 401
BSD_ENTITLEMENT_FAILED = 402/contract access
BSD_BACKOFF          = temporary network/5xx/429 circuit
BSD_BOOTSTRAP_PENDING = secret/provider works, identity not ready
BSD_SHADOW_VALIDATION = identity ready, provider not yet settlement-authoritative
BSD_PRIMARY_VALIDATED = normal primary state
BSD_DEGRADED         = conflict/validation downgrade
```

## 17.3. Post-deploy verification

Health/management output sólo debe mostrar:

```text
configured: true/false
provider state
last successful observed_at
last HTTP class/status
sanitized endpoint family
RateLimit / RateLimit-Policy metadata
circuit/backoff_until
bootstrap coverage counts
shadow-validation counters
```

Nunca token/prefix suficiente para reconstruirlo.

---

# 9. ResultProvider, routing y settlement

## 9.1 Boundary único

Un solo boundary:

```text
ResultProvider
├── BSD
└── API-Football
```

Un solo settlement engine:

```text
provider observation
→ reconcile canonical Match
→ CapitalResultObservation
→ settle_observation()
→ release exposure / simulated P&L
```

`CapitalResultObservation` debe preservar conceptualmente provider, external ref, provider_observed_at, result_known_at, status, regulation score/outcome, provenance, fallback reason y conflict state.

1X2 sigue siendo 90 min + stoppage; extra time/penalties excluidos.

## 9.2 Routing por estado de validación

## Durante bootstrap/shadow

```text
23 BSD-mapped competitions:
BSD = observer/shadow
API-F = settlement authority

5 unsupported:
API-F = settlement authority
```

## Después de BSD_PRIMARY_VALIDATED

```text
23 mapped + identity-ready:
T+130 → BSD event detail
finished valid → settle, no mandatory API-F
nonterminal → +30m normal retry
second due still nonterminal → API-F fallback may run if quota permits
provider/error/malformed/identity failure → same-wake API-F fallback if admitted

5 unsupported:
API-F existing lifecycle
```

Result work es posterior al partido y se puede diferir si la cuota debe proteger T10.

## 9.3 Semántica completa de resultado

Finsport 1X2:

```text
90 minutes
+
stoppage time
```

Nunca:

```text
extra-time winner
penalty winner
```

BSD presenta separadamente:

```text
home_score
away_score
extra_time_score
penalty_shootout
```

Por tanto el settlement debe utilizar el score reglamentario.

Estados:

```text
CANC / ABD
→ VOID
→ P&L 0
→ release exposure

AWD / WO
→ settle only if explicit reliable H/D/A exists
→ otherwise unresolved
```

Postponed:

```text
→ fixture recovery
→ not terminal settlement
```

## 9.4 Conflicto entre providers

Nunca:

```text
provider B
→ silently overwrite terminal provider A
```

Si un resultado terminal observado entra en conflicto con otro resultado canónico:

```text
persist both provenance contexts
→ mark durable conflict
→ fail closed
→ explicit reconciliation required
```

Si ya hubo settlement:

```text
do not silently mutate historical P&L
```

Una corrección posterior requiere un lifecycle explícito/auditable.

## 9.5 Invariante de settlement

Existe un solo motor de settlement. La introducción de BSD no crea un segundo lifecycle económico. Toda observación de proveedor se reconcilia primero con `Match` canónico, luego con `CapitalResultObservation`, y sólo después puede llegar a `settle_observation()`. Settlement debe ser idempotente y un restart no puede duplicar observación, liberación de exposure ni P&L.


---

# 10. ProviderCallAudit, budgets, quota priority y OLV

## 10.1 Budgets independientes y audit compartido

Los budgets son independientes:

```text
API-Football
≈ 100/day under current Free plan

BSD
≈ 7,500/day observed in preflight
```

Nunca:

```text
100 + 7500
→ one synthetic shared quota
```

Sí comparten estructura de observabilidad:

```text
provider
capability/logical identity
endpoint family
physical request
HTTP status
represented Matches
rate-limit headers
attempt/retry
fallback reason
run/correlation
sanitized params
```

No secrets.

## 10.2 OLV completo

## 27.1. OLV no es un modelo económico

OLV sólo ordena **adquisición T10 bajo escasez**.

No puede usar:

- ROI;
- P&L;
- strike rate;
- “esta liga gana más”;
- resultado del experimento;
- identidad de estrategia ganadora.

## 27.2. Fórmula primaria

```text
OLV
=
0.60 E
+
0.25 Q
+
0.15 C
```

Donde:

```text
attempts_w
=
attempts_current_season
+
0.25 * attempts_previous_season

successes_w
=
successes_current_season
+
0.25 * successes_previous_season
```

Exploration:

```text
E
=
1 / sqrt(1 + attempts_w)
```

Input-quality probability con Beta(1,1):

```text
Q
=
(1 + successes_w)
/
(2 + attempts_w)
```

Cold start:

```text
Q = 0.50
```

Coverage:

```text
C
=
1
/
(1 + successful_T10_captures_same_competition_day)
```

`day`:

```text
America/Lima
```

## 27.3. Attempt

Un attempt cuenta cuando:

```text
eligible T10 opportunity
+
>=1 admitted physical API-F odds request
+
request happens before hard T10 deadline
```

## 27.4. Success

Cuenta cuando, antes del hard deadline:

```text
T10 physical acquisition
→ persists usable 1X2 evidence
→ satisfies MARKET_CONSENSUS input completeness
```

## 27.5. Failure

Cuenta cuando una oportunidad admitida llega a su hard deadline sin input T10 utilizable por:

- mercado ausente;
- 1X2 incompleto;
- latest state inactive;
- provider response válido sin evidencia suficiente;
- error provider legítimamente intentado y no recuperado dentro de ventana.

## 27.6. Quota miss

Si nunca se admitió request físico únicamente por escasez de quota:

```text
MISSED_STRATEGY_WINDOW
```

No debe incrementar `Q` failure.

No debe hacer parecer que una liga ofrece mercados de peor calidad sólo porque Finsport no pudo consultarla.

## 10.3 Orden total de trabajo y mutable quota authority

El orden lógico de clases queda:

```text
CLASS 1
indispensable fixture discovery/recovery

CLASS 2
due T10 opportunities

CLASS 3
due API-F result fallback debt

CLASS 4
optional / gaps / surplus
```

Dentro de CLASS 2:

```text
1. urgency_bucket ASC
2. OLV DESC
3. exact not_after ASC
4. kickoff ASC
5. stable Match/fixture identity ASC
```

con:

```text
urgency_bucket
=
floor(
  max(0, not_after - now)
  / 180 seconds
)
```

Esto hace que la expiración temporal domine y OLV ordene principalmente oportunidades que compiten dentro de una ventana de wake comparable.

Antes de **cada physical API-F request**:

```text
re-read quota authority
→ recompute reserve/priority
→ execute only if still admitted
```

No basta la admisión al inicio de una operación larga.

## 10.4 Sensibilidad OLV

UAT debe calcular, sobre la misma secuencia:

```text
50 / 30 / 20
60 / 25 / 15
70 / 20 / 10
```

Propósito:

```text
diagnostic sensitivity only
```

Producción FS-023 permanece:

```text
60 / 25 / 15
```

La sensibilidad no puede cambiar automáticamente pesos ni convertirse en optimización por P&L.

## 10.5 Revalidación antes de cada request físico

Antes de **cada** request físico API-Football:

```text
re-read quota authority
→ recompute reserve/priority
→ execute only if still admitted
```

No basta la admisión al principio de una operación larga. API-F y BSD mantienen presupuestos independientes; nunca se suman en una cuota sintética común.


---

# 11. Historical readiness y LIVE participation

```text
Competition.enabled
→ LIVE/operator participation

HistoricalCoverage/readiness
→ independent capability
```

#209/#216/#223:

```text
requires_live_market_odds = true
requires_historical_experiment_backing = false
requires_sporting_history = false
requires_sporting_model_readiness = false
```

No deshabilitar una de las 28 por ausencia de histórico que esta estrategia no requiere.

El corpus histórico primario `H_PRIMARY` (16 competiciones / 2,605 Matches) y el universo `L_SELECTED` (28 LIVE) son conjuntos deliberadamente distintos. Ausencia de histórico no deshabilita una competición cuando el binding no lo requiere. Una estrategia futura que sí requiera sporting history debe gatear únicamente esa estrategia/competición, no deshabilitar globalmente la liga.


---

# 12. Strategy identity, cutover, epochs y rollback

## 12.1 Candidate identity != StrategyBinding identity

## 2.1. Candidate 209

`candidate 209` identifica **sólo la composición experimental canónica**:

```text
Prediction = MARKET_CONSENSUS / fs013-market-consensus-v2
Decision   = SELECTIVE_CONFIDENCE(0.45)
Capital    = FRACTIONAL_KELLY(lambda=0.25,max_lanes=10)
canonical_integrated_index = 209
```

No codifica:

- capture window;
- scheduler cadence;
- provider topology;
- epoch;
- activation time;
- initial bankroll;
- source/corpus identities.

Por tanto puede existir más de un binding cuya composición sea candidate 209.

## 2.2. Binding FS-022/T30

La identidad lógica del binding heredado se congela como:

```text
FS022_BINDING_209_T30_V1
composition_candidate = 209
capture_window         = market-t30m
prospective_basis      = T−30
```

El digest físico debe derivarse de la representación inmutable que implemente F009/Codex; el nombre lógico anterior es autoridad humana, no una obligación de nombre de tabla/campo.

## 2.3. Binding FS-023/T10

FS-023 debe crear un binding distinto:

```text
FS023_BINDING_209_T10_V1
composition_candidate = 209
capture_window         = market-t10m
wake_seconds           = 180
prospective_basis      = T−10
```

Como `capture_window` forma parte de la semántica del binding:

```text
T30 binding digest != T10 binding digest
```

aunque `composition_candidate == 209` en ambos.

## 2.4. Consecuencia

El deployment inicial FS-023 **obliga** a:

```text
new immutable T10 binding
+
new StrategyEpoch
```

No se permite conservar el epoch FS-022 como si nada hubiese cambiado.

## 12.2 Cutover inicial FS-022/T30 → FS-023/T10

El primer cutover es una migración de era temporal, no una simple configuración.

## 3.1. Estado previo

```text
epoch A
binding = FS022_BINDING_209_T30_V1
state   = ACTIVE
```

Sus OPEN/PENDING/history pertenecen exclusivamente a la era T30.

## 3.2. Deployment de código

El deploy instala capacidad FS-023 pero **no crea retroactivamente posiciones T10**.

Desde el deploy puede comenzar la captura global T10 como evidencia prospectiva para Matches futuros; esto mantiene Capture activo durante el drain. Sin embargo:

```text
T10 observation before epoch B activated_at
→ may be retained as prospective market evidence
→ MUST NOT create a Capital Position for epoch B retroactively
```

A partir del deploy se retiran nuevas obligaciones automáticas T6/T60/T30. Las posiciones ya creadas con T30 conservan su evidencia congelada.

## 3.3. Switch request

Crear de manera idempotente:

```text
source_epoch          = A
target_binding_digest = digest(FS023_BINDING_209_T10_V1)
initial_bankroll       = 100u
```

Entonces:

```text
A: ACTIVE → DRAINING
```

## 3.4. OPEN del epoch A

Toda Position ya abierta:

```text
remains OPEN
→ result lifecycle continues
→ settles under epoch A
→ preserves frozen T30 evidence
→ P&L belongs to epoch A only
```

No se reinterpreta con T10.

## 3.5. PENDING_CAPACITY del epoch A

Al comenzar `DRAINING`:

```text
old T30 pending
→ MUST NOT become a new Position
→ no stake
→ no lane
→ no P&L
→ terminal reason = STRATEGY_DRAIN / equivalent explicit state
```

Si ya había sido colocado antes del switch, ya es OPEN y se liquida normalmente.

Esto resuelve la ambigüedad de “resolve pending”: durante drain se **terminaliza** el pending antiguo sin crear exposición adicional.

## 3.6. Condición DRAINED

A sólo puede llegar a `DRAINED` cuando:

```text
OPEN positions            = 0
PENDING_CAPACITY           = 0
unresolved result debt     = 0
reserved exposure          = 0
```

Capture no se detiene.

## 3.7. Activación T10

Sólo después de `A = DRAINED`:

```text
revalidate FS023_BINDING_209_T10_V1
→ create epoch B
→ initial_bankroll = exactly 100u
→ persist activated_at
→ B = ACTIVE
```

No se transfiere implícitamente:

```text
A.final_equity
A.available_cash
A.P&L
A.reserved_exposure
```

al nuevo epoch.

`100u` es una decisión explícita de comparabilidad con el Capital baseline; si en el futuro se desea otro capital inicial, será otro switch request explícito. FS-023 no infiere el valor a partir de la banca vieja.

## 3.8. Match/era eligibility

Para epoch B:

```text
Match T10 cutoff < B.activated_at
→ no retroactive B placement

Match T10 cutoff >= B.activated_at
→ eligible under B, subject to normal T10 rules
```

No reconstruir una posición sólo porque una T10 Observation global exista de antes.

## 3.9. Historia FS-022

Preservar siempre:

```text
FS-022 epoch A
binding T30
100u initial bankroll
all positions/results/P&L
T30 evidence
activation/deactivation timestamps
```

La nueva era:

```text
FS-023 epoch B
binding T10
100u new bankroll
separate positions/results/P&L
```

Nunca unir ambas curvas de equity como si fueran una misma banca.

## 3.10. Restart safety

Switch identity:

```text
source_epoch
+ target_binding_digest
+ initial_bankroll
```

Tras crash/restart:

- si A sigue DRAINING, continuar el mismo drain;
- no crear otro epoch B;
- no volver a terminalizar dos veces un PENDING;
- no duplicar settlement;
- si B ya fue creado/activado, devolver el estado existente.

## 3.11. KEEP #209 y ALREADY_ACTIVE

Después del experimento post-implementación:

```text
KEEP #209
```

significa:

> La composición ganadora/retendida sigue siendo 209 **y el binding completo actualmente ACTIVE ya es exactamente `FS023_BINDING_209_T10_V1`**.

En ese caso no hay switch ni nuevo epoch.

`ALREADY_ACTIVE` sólo se devuelve ante un request explícito cuyo **target binding digest completo** coincide con el binding activo.

No significa:

```text
same candidate number
→ automatically same binding
```

Un futuro candidate 209 con otra ventana/version/provider requirement sería otro binding y exigiría drain.

## 12.3 Binding/Epoch general

Cada binding inmutable incluye conceptualmente:

```text
Prediction identity/version
Decision identity/version/config
Capital identity/version/config
max_lanes
capture_window
capability requirements
promotion lineage
scientifically material hashes/ids
real_betting=false
binding digest
```

Changing any semantic field creates a new binding.

Epoch states:

```text
ACTIVE
DRAINING
DRAINED
```

Future rollback = new switch request to a previously approved binding, producing a **new epoch**, never resurrection/mutation of an old epoch object.

## 12.4 Capital semantics heredadas que FS-023 no modifica

El binding T10 cambia la ventana y la era, **no** la política Capital de la composición 209. Para el epoch FS-023/T10 se preserva:

```text
Capital = FRACTIONAL_KELLY
lambda = 0.25
max_lanes = 10
initial_bankroll = 100u compartidas
no sub-bankroll per lane
real_betting = false
```

La frontera de agotamiento operacional heredada de FS-022/FS-021 permanece normativa:

```text
DEPLETION_FLOOR = 5u
trigger = equity <= 5u
scope = combinación/epoch completo
never = lane alone
never = available_cash alone
```

Orden por wake:

```text
1. settle all due OPEN
2. update equity / reserved exposure / policy state
3. evaluate depletion threshold
```

Si `equity <= 5u` y queda al menos una OPEN, bloquear nuevas entradas en un estado equivalente a `AWAITING_FINAL_OPEN_SETTLEMENT` y continuar liquidando **todas** las OPEN. Un saldo intermedio >5u no reactiva mientras quede una OPEN de esa pausa. Tras la última liquidación:

```text
equity > 5u  → puede reanudar sólo oportunidades todavía pre-kickoff
equity <= 5u → OPERATIONAL_DEPLETION; no abre nuevas posiciones
```

Si no hay OPEN y `equity <= 5u`, detener antes de otro placement. Ledger, resultados, posiciones y evidencia se conservan. Esta regla es distinta de `PENDING_CAPACITY`, `EXPIRED_CAPACITY`, zero-stake, falta temporal de cash y ruina matemática.

Acceptance debe preservar explícitamente el borde `equity == 5u` y el caso D05 heredado: tres OPEN con estados intermedios 3u → 6u con una OPEN restante → 9u; sólo puede reanudarse después de liquidar la tercera.

## 12.4 Promotion no equivale a activation

Experiment Lab:

```text
experiment
→ publication
→ activation=false
```

Un winner publicado no cambia el runtime.

Flujo:

```text
publication
→ human/maintainer review
→ explicit PROMOTE
→ immutable approved StrategyBinding
```

Incluso después de PROMOTE:

```text
open old positions
→ require drain
```

No existe hot-swap inmediato.

## 12.5 Rollback

Rollback es un nuevo switch request cuyo target es un `StrategyBinding` previamente aprobado. Nunca se reactiva/muta un epoch histórico. Cada rollback crea un epoch nuevo y conserva bankroll/P&L separados.

## 12.6 Idempotencia

La identidad mínima del switch es:

```text
source_epoch
+ target_binding_digest
+ initial_bankroll
```

Repetir el mismo request tras crash/restart reanuda la misma transición; no crea un segundo epoch objetivo. Si el binding objetivo completo ya está ACTIVE, la respuesta es `ALREADY_ACTIVE` sin side effect.


---

# 13. Experiment Lab y elección restringida post-implementation

## 13.1 Subset execution

Debe soportar:

```bash
--candidate-ids 209
--candidate-ids 209,216,223
```

sin ejecutar los otros 228.

Preservar:

```text
canonical_integrated_index
```

y usar un `local_index` denso sólo internamente cuando el selector lo necesite.

No renumerar 209→0 en artifacts durables.

Fail closed ante ID desconocido, duplicado, inelegible o subset vacío.

## 13.2 Restricted challenge

```text
209 → SELECTIVE_CONFIDENCE 0.45
216 → SELECTIVE_CONFIDENCE 0.50
223 → SELECTIVE_CONFIDENCE 0.55

Prediction for all:
MARKET_CONSENSUS / fs013-market-consensus-v2

Capital for all:
FRACTIONAL_KELLY / 0.25 / max_lanes=10
```

No añadir thresholds.

Activity gate:

```text
placements >=53
competitions >=5
active weeks >=5
```

## 13.3 Experimentos post-implementation

Primero:

```text
[209]
result-mode=evaluation-only
selection_authority=false
promotion_eligible=false
activation=false
```

Después, sólo si implementation/UAT está validado:

```text
[209,216,223]
result-mode=selection
selection_authority=true
promotion_eligible=true
activation=false
```

El winner no activa runtime.

## 13.4 Economic Selector completo

No se crea un selector nuevo.

Se reutiliza:

```text
FS021_SINGLE_ECONOMIC_SELECTOR_V1
```

Incluye la metodología ya implementada de FS-021:

- structural/integrity checks;
- activity;
- economic ruin/depletion;
- return;
- drawdown;
- bootstrap downside/tail loss;
- chronological halves;
- leave-one-competition-out;
- stability;
- robust tiers;
- Pareto;
- deterministic tie-breaking.

Dimensiones Pareto:

```text
maximize R
minimize D
minimize L
```

Donde conceptualmente el implementation existente conserva:

```text
R = worst observed return across settlement scenarios
D = worst relevant drawdown
L = tail-loss/CVaR diagnostic used by FS-021
```

No reimplementar estas fórmulas desde prosa si el código FS-021 ya es la autoridad ejecutable.

Orden de selección existente debe preservarse.

Regla productiva previamente aceptada:

```text
if no candidate meets risk references
but one or more candidates have R > 0
→ best positive candidate may remain selected
→ elevated-risk condition visible

if all candidates have R <= 0
→ DIAGNOSTIC_ONLY / NO_NEW_STAKES
→ no new automatic promotion
```

La disposición científica y el fallback económico continúan siendo cosas distintas.

El histórico `UNSTABLE` de FS-021 no se reescribe.

## 13.5 Multiplicity / exploratory boundary

Los tres challengers se congelan **antes** del experimento post-implementación.

Por tanto:

```text
candidate set
→ preregistered restricted challenge

threshold exploration
→ forbidden
```

No se introduce en FS-023 una nueva corrección estadística ad hoc.

Sí deben ejecutarse los diagnósticos existentes de:

- bootstrap;
- stability;
- halves;
- leave-one-competition-out;
- activity.

Un winner histórico no equivale a prueba de superioridad prospectiva ni a promesa de rentabilidad.

## 13.6 Activity gate

Antes de observar el resultado final, el gate permanece preregistrado:

```text
minimum placements    = 53
minimum competitions  = 5
minimum active weeks  = 5
method                 = PROPORTIONAL_TRANSFER_FROM_FS021
```

No se modifica después de mirar qué candidato gana.


---

# 14. Benchmark de costo de oportunidad

FS-023 **NO implementa cliente HTTP, scraper ni scheduler de MEF/SBS**.

El maintainer obtiene el dato desde la fuente oficial y lo entrega como input congelado del `ExperimentSpec`.

El código sólo:

```text
validates
persists
hashes/binds
uses
```

los campos.

No hace provider calls para “refrescar” el benchmark durante el experimento.

## 26.1. Financial benchmark

```text
source = MEF / Letras del Tesoro Público
currency = PEN
standard tenors = 3 / 6 / 9 / 12 months
select tenor closest to horizon days
exact tie → shorter tenor
rate = latest official weighted-average auction yield with auction_date <= freeze_at
```

Para 257 días:

```text
9 months / ~273 days
```

Input mínimo:

```text
annual_rate
as_of / auction_date
source identifier
source locator
currency=PEN
tenor_months
horizon_days
freeze_at
```

Horizon conversion:

```text
(1 + annual_rate_decimal)^(days/365) - 1
```

Si falta dato oficial:

```text
UNAVAILABLE
```

no valor inventado.

## 26.2. Practical benchmark

Manual input desde SBS:

```text
Sistema Bancario
Moneda Nacional
Depósitos a Plazo
Personas Naturales
bucket containing horizon
latest official observation <= freeze_at
```

Para 257 días: `181–360 días`.

Es diagnóstico; no decide winner.

Codex no está autorizado a crear integración MEF/SBS sin otro ticket/research explícito.

El benchmark es input congelado de `ExperimentSpec`; no se implementa cliente HTTP/scraper de MEF o SBS en FS-023. Si el dato financiero primario oficial no está disponible a `freeze_at`, el benchmark es `UNAVAILABLE` y no puede afirmarse que una selección lo superó.


---

# 15. Persistencia esperada y observabilidad

## 15.1 Persistencia

FS-023 probablemente requiere migrations/persistencias para representar:

- BSD source references;
- result provider provenance;
- explicit competition→BSD mappings;
- immutable StrategyBinding;
- StrategyEpoch;
- StrategySwitchRequest;
- drain state;
- capability requirements;
- active binding/epoch ownership;
- provider conflict/audit context cuando no exista estructura reusable.

Research no prescribe tablas/columnas exactas.

Regla para Codex:

> Elegir la forma Django más pequeña que satisfaga exactamente estas semánticas y reutilice entidades existentes; no crear una segunda arquitectura paralela.

## 15.2 Observabilidad

Deben quedar distinguibles:

```text
BET
NO_BET
NOT_EVALUATED
MISSED_STRATEGY_WINDOW
PENDING_CAPACITY
OPEN
VOID
BSD_IDENTITY_UNRESOLVED
BSD_IDENTITY_AMBIGUOUS
RESULT_PROVIDER_ERROR
RESULT_CONFLICT
TEMPORARILY_UNAVAILABLE
DRAINING
DRAINED
ALREADY_ACTIVE
```

`MISSED_STRATEGY_WINDOW` no es `NO_BET`.

`provider unavailable` no es una señal económica.

El P&L sigue siendo simulado.

A esa taxonomía se añaden los estados BSD operacionales de la corrección:

```text
BSD_NOT_CONFIGURED
BSD_AUTH_FAILED
BSD_ENTITLEMENT_FAILED
BSD_BACKOFF
BSD_BOOTSTRAP_PENDING
BSD_SHADOW_VALIDATION
BSD_PRIMARY_VALIDATED
BSD_DEGRADED
```

`MISSED_STRATEGY_WINDOW` no es `NO_BET`; un provider unavailable no es una señal económica; todo P&L sigue siendo simulado.


---

# 16. Durable evidence, artifacts, restore y retention

## 16.1 Package durable — PASS

La corrección materializó y verificó un paquete compacto en el entorno de entrega:

```text
/mnt/data/FS-023_final_evidence/
```

Archive:

```text
/mnt/data/FS-023_final_evidence.tar.xz
SHA256 = 156e335d831f9f7d244bb4ca83bb61a4bee84ac7c1fe47897081486c32b31f92
```

Contiene:

```text
FS-023_RESEARCH_EVIDENCE_MANIFEST.json
SHA256SUMS
corpus A/B
semantic audit
T30/T10/T5 replay
reconciliation/aliases
07c6g manifest/summary/traffic audit
Quality Gate
primary population contract
LIVE inventory/exhaustiveness
BSD catalog/preflight artifacts
FS-023_bsd_league_mapping.json
FS-023_capacity_28_model.json
research-evidence-list.txt
```

Validado:

```text
A rows = 2059
B rows = 546
union = 2605
fixture overlap = 0
historical competitions = 16
LIVE mapping = 28
BSD routes = 23
API-F-only routes = 5
all SHA256SUMS in generated package = PASS
```

No se copió ningún directorio raw/cache OddsPapi al package `final/`.

La evidencia pesada continúa referenciada por sus `RETENTION_INDEX.sha256` en:

```text
/home/ljarufe/Documents/finsport/research-evidence/FS-023/oddspapi-historical/
/home/ljarufe/Documents/finsport/research-evidence/FS-023/oddspapi-historical/07c4/
/home/ljarufe/Documents/finsport/research-evidence/FS-023/oddspapi-historical/07c6g/
/home/ljarufe/Documents/finsport/research-evidence/FS-023/oddspapi-tournaments/
```

## 27.1. Host materialization — PASS

El maintainer materializó el package en:

```text
/home/ljarufe/Documents/finsport/research-evidence/FS-023/final/
```

y ejecutó `sha256sum -c SHA256SUMS`. Todos los artifacts enumerados devolvieron `OK`. El gate de materialización durable queda **cerrado** y F008 no debe tratarlo como acción pendiente.

### Host durable verification

El maintainer materializó el archive en:

```text
/home/ljarufe/Documents/finsport/research-evidence/FS-023/final/
```

y ejecutó:

```text
sha256sum -c SHA256SUMS
```

Resultado: **todos los archivos `OK`**. Por tanto el antiguo `PRE-READY MATERIALIZATION ACTION` queda cerrado y no debe reaparecer como blocker.

## 16.2 Artifact inventory

| Artifact | SHA-256 | Role |
|---|---|---|
| `state_corrected_common_T30_T10_T5.jsonl.gz` | `f4e841ab89c303198b31e307b2fd7a76ffe65a9751a9908b131e6a2c1bbf15e8` | A — 2,059 original corrected corpus |
| `eligible_common_T30_T10_T5.jsonl.gz` | `f15554f3180bbecc89bf17947f30ff2a075aaf92d5893cabd94160f94784151e` | B — 546 SC/RO/CN expansion |
| `state_semantics_audit.json` | `a635ac8b858b09d73a26b6460da2794d693ee3d7e3335e939d29ed74d2f6d5e1` | latest-state/inactive semantics |
| `T30_T10_T5_capital_replay.json` | `18b1aa792a8fb9e912fd1c309b7fc700d9ab5af108af31b8d0f35143b4080e9a` | window timing replay evidence |
| `reconciled_matches_v3.json` | `84ded60136491bfe1fe7647188594ed8fca0cadecb859acb85351f05dc38ca70` | SC/RO/CN final reconciliation |
| `learned_aliases.json` | `568b8e29f841dd9cf76598166df67f100c63f5b08ee32d5916e3bab72cb92598` | SC/RO/CN historical aliases |
| `manifest.json` | `cc3334296aa3e83bbaa778f71b204f22c24c8f2b93071340c29f6155e9cae59a` | 07c6g historical acquisition manifest |
| `summary.json` | `3ec64b4893ed4c510cd74e1072f1f19673704b7c5fa363fa157ad17102709ec5` | 07c6g acquisition summary |
| `traffic-audit.json` | `acf9944d326d8015a07ada15eab14d16a5dbf18fa2655b9c778a662f6e464573` | 07c6g traffic audit |
| `league_quality_gate.json` | `b04803256e2c4c39e0ee389aa7bde6bafb4406df7c813a596eb3e9a5b68bdbca` | historical league quality gate |
| `primary_population_contract.json` | `e14501ed069e212bec3e4489bafaf12598c0bae5fd72254b9bfad7c71dd5f305` | 2,605 primary population contract |
| `FS-023_07d1_live_candidate_inventory.txt` | `44fb0fd10226d737dffdde8864401ecfb6b0e849342db92201a7b112d83ea4b1` | LIVE 28 inventory evidence |
| `FS-023_07d1b_live_catalog_exhaustiveness.txt` | `700a29e8ab865a64f17e4163e6977c4fac02d8dd22c593ee390295ad9d87c068` | catalog exhaustiveness evidence |
| `leagues.json` | `a1d93fd140b3bcea15031206d2eca8e2856c173bdcc9d249ba78b46528b76f7d` | BSD league catalog snapshot |
| `finished_last_7d.json` | `1bcb9ffff15a106532210c51c6866d1513b77a0bd1b28bf29506deef9d108043` | BSD finished-event preflight sample |
| `audit.json` | `2d7ae8a9230e420ccd3220a918f2c738740270daed0c7629f24041110ea314c6` | BSD traffic/preflight audit |
| `local_result_comparison.json` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | BSD comparison artifact; empty sample |
| `FS-023_bsd_league_mapping.json` | `7c0b4b38e3fd6f9ddeb4b7ae61315b628a6fc71cf47b6a11d8b795fbad2b6941` | frozen 28 mapping / 23+5 result routing |
| `FS-023_capacity_28_model.json` | `4e1d98ec4f1506c97d7d0a7531ce12cabb043aeee7f0a732ec158f3cb0654fda` | 28-league capacity planning projection |

El manifest generado es la autoridad del package y contiene consumer, retention/deletion rule, corpus identity y heavy-evidence references.

## 16.3 Restore contract

Consumer posterior:

```text
1. resolve durable artifact
2. verify SHA-256
3. fail closed on mismatch
4. copy/restore exact file into repo tmp/
5. bind exact identity in ExperimentSpec
6. execute analysis
7. publish new compact outputs
```

`tmp/` vuelve a ser sólo workspace.

## 16.4 Retention/deletion condition

Mantener FS-023 evidence mientras sea necesaria para:

```text
FS-023 implementation
+
post-implementation [209] evaluation
+
post-implementation [209,216,223] selection
+
publication/promotion audit
```

Sólo puede considerarse borrado/reducción cuando:

- todos los downstream consumers tengan su propia autoridad durable;
- hashes/restores ya no dependan del artifact;
- restricciones de provider permitan la retención/eliminación elegida;
- maintainer autorice la limpieza.

Raw provider evidence sigue las restricciones de licencia/privacidad existentes.

---

# 17. External contracts y configuration boundaries

## 17.1 External Contract Matrix

| Boundary | Exact contract | Retry/fallback | Evidence/acceptance |
|---|---|---|---|
| API-F fixture | `GET /fixtures?date=...&timezone=America/Lima`; directed `id=` | existing quota-aware behavior | bounded UAT |
| API-F odds | `GET /odds?fixture=<id>` with existing canonical 1X2 filtering | deadline-aware; no post-kickoff | T10 UAT |
| API-F plan | ~100/day, ~10/min current Free | dynamic headers authority | runtime audit |
| BSD auth | API v2 + `Authorization: Token` | 401 persistent AUTH_FAILED | config/UAT |
| BSD catalog | `GET /leagues/?limit=200&offset=0` | pagination | bootstrap |
| BSD teams | `GET /teams/?league_id=&season_id=&in_competition=true&limit=200&offset=` | pagination | bootstrap |
| BSD event list | `GET /events/?league_id=&season_id=/date_from=/date_to=/limit=/offset=` | pagination; no fuzzy runtime | bootstrap/rebind |
| BSD bound event | `GET /events/<id>/` | one retry network/5xx; status-specific circuit | result UAT |
| BSD live | `/events/live/` | manual UAT only; not automatic settlement | optional |
| BSD quota | 7,500/day observed + documented; 25 req/s IP cached endpoints | honor `Retry-After`; circuit | ProviderCallAudit-like evidence |
| Football-Data | historical/reconciliation only | no OPEN settlement | existing |
| OddsPapi | historical research only | no runtime | retained evidence |
| MEF | manual frozen ExperimentSpec input | no HTTP client | validation only |
| SBS | manual frozen diagnostic input | no HTTP client | validation only |

Official BSD docs confirm v2 base/auth, list pagination max 200, event filters, stable team/event IDs, result score semantics and distinct 429 modes. API-F official pricing confirms current Free allowance of 100 requests/day; physical FS-023 probes remain authority where generic documentation differs from the actual plan.

## 17.2 Configuration surfaces

F008/F009 debe verificar al menos las superficies que materialmente cambian:

```text
Django settings/defaults
.env.dist / local secret/runtime overrides
Celery Beat schedule / cadence
effective Docker/Compose runtime configuration
provider configuration and kill/degrade state
management commands for BSD bootstrap/reconciliation
Experiment Lab CLI/subset flags
StrategyBinding/epoch activation state
```

Distributed/default y effective runtime configuration deben ser coherentes. La ausencia del secret BSD no impide startup: deja BSD en `BSD_NOT_CONFIGURED`, produce cero llamadas BSD y mantiene API-F como ruta efectiva de resultados.


---

# 18. Acceptance y UAT

## 18.1 Acceptance consolidada de la corrección

F008/F009 deben exigir al menos:

## Cutover

- T30 binding and T10 binding have different digests;
- deployment enters T30 epoch DRAINING;
- old PENDING cannot place;
- old OPEN settles normally;
- new epoch starts only after drain invariants;
- new bankroll exactly 100u;
- no implicit equity transfer;
- restart does not duplicate switch/epoch;
- T10 pre-activation observations cannot create retroactive B positions;
- `KEEP #209` only means no switch when full active digest already equals target.

## Capacity/T10

- only T10 automatic market window;
- wake 180s;
- deadline-aware queue;
- quota miss => MISSED_STRATEGY_WINDOW;
- OLV deterministic ordering;
- no post-kickoff call;
- provider-free NO_WORK where nothing due.

## BSD bootstrap

- 28 competition mapping imported exactly;
- 23/5 routing count verified;
- exact-normalized unique team mapping can auto-accept;
- non-exact requires human approval;
- event identity exact by mapped team IDs + ±15m;
- zero/multiple fail closed;
- unprepared BSD league uses API-F, not fake BSD primary.

## BSD shadow

- BSD cannot settle during SHADOW;
- API-F settles during validation;
- sample counters stored;
- 30/5/7 gate enforced;
- confirmed conflict rule enforced;
- probation weekly and steady monthly sentinel behavior;
- degradation routing works.

## BSD retries

Unit/integration tests for 400/401/402/404/429 rate_limited/429 taster_exhausted/5xx/network/malformed payload and open circuit must prove no every-wake retry storm.

## Credentials

- absent token does not fail startup;
- state is BSD_NOT_CONFIGURED;
- zero BSD calls;
- API-F route works;
- invalid token opens persistent AUTH_FAILED;
- health output never prints secret.

## Experiment Lab

- default 231 behavior preserved where intentionally invoked;
- `--candidate-ids 209` executes only 209;
- `209,216,223` executes only three;
- canonical IDs preserved;
- subset identity in ExperimentSpec;
- selector accepts N=1/N=3.

No real-money UAT.

## 18.2 T10 adversarial

FS-023 no está aceptado si no se demuestra:

```text
T6/T60/T30 future automatic calls disabled
T10 automatic obligation exists
wake = 180s
no valid capture at/post kickoff
T10 successful evidence closes obligation
missed hard deadline is explicit
old evidence remains intact
PENDING_CAPACITY freezes T10, not T30
```

Tests adversariales deben cubrir:

- capture exactamente antes de hard deadline;
- capture posterior a hard deadline;
- wake después de kickoff;
- restart durante T10 obligation;
- duplicate wake/idempotency;
- insufficient 1X2 books;
- provider error before deadline;
- quota miss.

## 18.3 Quota/OLV

Probar:

```text
cold start Q = 0.5
season weighting current=1 / previous=.25
OLV primary 60/25/15
same-day coverage in America/Lima
quota miss does not lower Q
provider failure after admitted attempt can lower Q
urgency dominates across expiry buckets
OLV breaks ties within comparable urgency
stable identity final tie-break
```

Ejecutar sensibilidad 50/30/20 y 70/20/10 como diagnóstico, sin cambiar producción.

## 18.4 ResultProvider/settlement mínimo adicional

Además del shadow contract de §8 y §9, UAT debe demostrar:

1. durante `BSD_SHADOW_VALIDATION`, BSD nunca liquida Capital y API-F sigue siendo autoridad;
2. tras `BSD_PRIMARY_VALIDATED`, `finished` válido puede liquidar sin llamada API-F obligatoria para ese Match;
3. BSD nonterminal en T+130 mantiene debt y retry; si sigue nonterminal en la siguiente due, API-F fallback puede ejecutarse si quota lo admite;
4. error/malformed/identity unresolved/ambiguous permite fallback sin guess;
5. competición API-F-only conserva lifecycle actual;
6. conflicto terminal persiste ambos contexts, falla cerrado y nunca sobrescribe P&L silenciosamente;
7. ET/penalties nunca determinan 1X2;
8. CANC/ABD → VOID/P&L 0/release exposure;
9. AWD/WO sólo se liquida con outcome canónico explícito y fiable;
10. PST/postponed vuelve a fixture recovery;
11. restart no duplica observación ni settlement.

## 18.5 Historical/LIVE separation

Probar:

```text
historical incomplete
→ does not disable Competition.enabled

strategy requiring no history
→ remains LIVE eligible

strategy explicitly requiring history
→ capability gate can block only that strategy/competition combination
```

No global disabling por histórico.

## 18.6 StrategyBinding / epochs

Probar:

```text
active binding resolved generically
no `candidate==209` routing requirement
binding immutable
promotion publication does not activate
switch enters DRAINING
new exposure blocked while draining
Capture continues
OPEN continues settlement
PENDING resolves/expires without old-path new exposure
activation waits for all drain obligations = 0
new epoch gets explicit bankroll
old equity not transferred
same switch request after restart resumes
duplicate target epoch not created
rollback creates new epoch
already-active returns ALREADY_ACTIVE
```

## 18.7 Experiment Lab

Probar:

```text
default all-candidate execution still works

--candidate-ids 209
→ only 209 physically executed

--candidate-ids 209,216,223
→ only those three physically executed

canonical ids preserved
local dense indices valid
subset identity hashed
unknown ID rejected
duplicate ID rejected
selector works with N=1 and N=3
```

No 231-arm physical run as hidden prerequisite.

## 18.8 Real provider UAT

Real external UAT debe ser:

```text
GET-only
bounded
quota-aware
secret-safe
no intentional 429 exhaustion
no financial side effect
```

No es necesario llamar las 28 ligas individualmente para aceptar la arquitectura.

Mínimo material cuando haya muestra:

- una competición BSD-supported con evento resoluble;
- una competición API-F-only o fallback;
- una captura API-F T10/fixture representativa;
- validación de headers/audit;
- mapping/config completo de las 28 sin llamadas individuales ceremoniales.

Si no existe terminal match BSD comparable durante UAT:

```text
NO_SAMPLE
```

no `PASS` ficticio ni `FAIL`.

La concordancia real debe acumularse operacionalmente después.

---

# 19. Negative findings, falsification y STOP boundaries

## 19.1 Null/negative findings preservados

1. T5 no mejoró consistentemente T10.
2. Tres ventanas consumían demasiada cuota.
3. `07d2` season-based current-plan capacity probe fue método no utilizable bajo el plan físico observado.
4. La primera heurística BSD fuzzy dejó falsos no-matches y no es apta para runtime.
5. BSD local score concordance no pudo medirse por muestra cero.
6. Un catálogo API-F con muchas ligas de odds no justifica aumentar el scope por encima de 28.
7. Histórico adicional no es requisito para que una liga participe LIVE con #209/#216/#223.
8. El winner histórico futuro no demostrará rentabilidad prospectiva.

## 19.2 Falsificación

Las principales conclusiones cambiarían sólo si nueva evidencia demuestra:

### T10

```text
T10 materially unavailable operationally
or
cannot be acquired pre-kickoff at acceptable coverage
```

Eso requeriría nuevo research; no autoriza volver silenciosamente a T30.

### BSD

Si UAT demuestra:

```text
unreliable identity
material score conflicts
unacceptable availability
contract/access lost
```

el sistema debe degradar a API-F fallback y abrir research dirigido; no inventar resultados.

### LIVE 28

Si una competición no soporta fixtures/odds en su temporada efectiva:

```text
TEMPORARILY_UNAVAILABLE
```

No se reemplaza automáticamente por una liga 29.

### Restricted selection

Si ninguno cumple criterios económicos/actividad:

```text
NO_PROMOTION / diagnostic disposition
```

No buscar un threshold nuevo.

## 19.3 Stop conditions para F009

STOP y devolución a main chat/research dirigido si ocurre alguno de estos casos materiales:

- el plan efectivo contradice una request shape indispensable no cubierta por fallback aceptado;
- T10 demuestra ser materialmente inaccesible antes del kickoff con cobertura operativa aceptable;
- BSD pierde acceso/contrato o produce identidad/conflictos materiales fuera del shadow/degradation contract;
- se requiere fuzzy runtime matching para operar;
- la implementación exige una liga #29 o ampliar el corpus histórico para cerrar el ticket;
- se necesita cambiar OLV, candidatos, thresholds, activity gate, economic selector o benchmark después de observar resultados;
- se propone volver silenciosamente a T30;
- se necesita transferir equity entre epochs;
- se cruza la frontera `real_betting=false`;
- no puede preservarse provenance/temporal identity/corpus hash.

No usar STOP para detalles ordinarios de nombres de campos, migration number, indexes o helpers internos.


---

# 20. Source hierarchy y contradicciones reconciliadas

## 20.1 Source hierarchy

Para FS-023:

```text
1. accepted Finsport product/domain/process contracts
2. exact checkout/current runtime for implementation facts
3. FS-023 retained empirical artifacts
4. physically verified provider behavior
5. official provider documentation
6. secondary explanatory material
```

Cuando documentation y plan físico difieran para una request shape:

```text
physical current-plan proof
→ implementation authority
```

## 20.2 Contradicciones ya reconciliadas

## 59.1. F003/F004 dicen T30/300s

No es una contradicción sin resolver.

Son CURRENT pre-FS-023.

Este research propone:

```text
after FS-023 merge/deploy:
T10 / 180s
```

Actualizar fuentes durables después de implementación aceptada, no antes.

## 59.2. API-F documentation vs plan físico

Documentación genérica puede mostrar request shapes o season access más amplio.

Physical plan evidence manda para la implementación local.

Por eso:

- `ids=` no se usa productivamente;
- no season sweep como requisito;
- discovery se limita a fechas realmente permitidas.

## 59.3. BSD catálogo 88 vs cobertura web mutable

`88` es snapshot del artifact.

No se convierte en una constante universal.

Lo duradero es la tabla explícita de 28 mappings y season/runtime verification.

## 59.4. BSD score comparison = 0

No se convierte en evidencia positiva.

Se conserva:

```text
INCONCLUSIVE_NO_COMPARISON_SAMPLE
```

y se mitiga mediante UAT/observación posterior.

## 59.5. Historical 16 vs LIVE 28

Intencional.

No resolver fabricando histórico adicional.

A esas reconciliaciones se añade la corrección crítica ya incorporada en este documento:

```text
candidate 209 composition
!=
StrategyBinding identity
```

Por tanto `FS022_BINDING_209_T30_V1` y `FS023_BINDING_209_T10_V1` son bindings diferentes aunque compartan candidate 209.


---

# 21. Implementation risk map

| Boundary | Principal risk | Required protection |
|---|---|---|
| schema | partial epoch/provider migration | reversible migration + tests |
| temporal evidence | post-kickoff quote | hard pre-kickoff invariant |
| quota | 28-league peak | priority + OLV + explicit miss |
| results | provider conflict | fail closed |
| BSD identity | wrong event match | explicit IDs + no fuzzy runtime |
| Capital | duplicate settlement | idempotent observation/settlement |
| switch | duplicate epoch after crash | idempotent switch identity |
| historical evidence | corpus drift | two hashes + merge contract |
| Experiment Lab | ID renumbering | canonical index preserved |
| economics | stale hardcoded rate | frozen benchmark input |
| safety | simulated→real leakage | real betting forbidden |

Riesgos adicionales congelados por la corrección:

| Boundary | Principal risk | Required protection |
|---|---|---|
| BSD shadow | convertir provider no validado en settlement authority | API-F settlement hasta gate 30/5/7 |
| BSD credentials | retry storm por 401/402 | persistent state/circuit + zero repeated calls |
| BSD bootstrap | provider nominal sin identities | readiness states + API-F route until ready |
| T30→T10 cutover | mezclar eras/equity | new binding + drain + new 100u epoch |
| capacity projection | tratar estimate como observación | etiquetar projection + runtime measurement |
| benchmark | cliente externo accidental | manual frozen input only |


---

# 22. Ticket packaging y fronteras F008/F009

## 22.1 Packaging recommendation

```text
ONE COHESIVE FS-023 TICKET
```

Razón:

Los cambios forman una misma transición operacional:

```text
28 leagues
→ T10/quota
→ ResultProvider
→ active strategy abstraction
→ safe switching
→ subset experiment capability
```

Separar BSD de la ampliación de ligas obligaría a implementar temporalmente una topology de cuota que ya sabemos que queremos retirar.

F008 sólo debería dividirlo en tickets enlazados si descubre una necesidad **puramente de delivery**, no porque falte research.

Si se divide físicamente:

```text
same frozen research contract
same final outcome
no independent semantic redesign
```

## 22.2 F008 Definition of Ready

El gate durable de evidencia ya está PASS, por lo que los ítems de materialización/hash se consideran cerrados. El resto del checklist normativo es:

```text
[x] exact outcome/scope frozen
[x] 28 LIVE mapping frozen
[x] 23 BSD / 5 API-F routing frozen
[x] T10 timing frozen
[x] 180s wake frozen
[x] OLV formula/ranking frozen
[x] ResultProvider/fallback frozen
[x] historical-vs-LIVE separation frozen
[x] candidate-vs-binding identity frozen
[x] initial T30→T10 drain/new epoch/100u frozen
[x] BSD bootstrap/shadow/retry/config frozen
[x] StrategyBinding semantics frozen
[x] epoch/drain/switch semantics frozen
[x] Experiment Lab subset semantics frozen
[x] [209,216,223] candidate set frozen
[x] 2605 composite corpus identity frozen
[x] activity gate 53/5/5 frozen
[x] FS021 economic selector reuse explicit
[x] MEF/SBS benchmark manual-input contract frozen
[x] artifact final directory materialized on host
[x] SHA256SUMS verified on host
[x] raw restricted evidence remains outside Git
[x] provider GET UAT budget bounded
[x] no real-financial side effect
[x] no frontend scope
[x] no new technique/model scope
```

**Research/F008 blocker remaining: NONE.**

## 22.3 F009/Codex boundary

Codex **sí decide**:

- exact Django model fields;
- migration numbering;
- internal class/function names;
- reusable adapter structure;
- transaction boundaries;
- indexes;
- management command naming;
- minimal refactor needed;
- tests implementation.

Codex **no decide**:

- cuáles son las 28;
- T10 vs T5/T30;
- 180s vs otro cadence;
- BSD vs third API;
- 23/5 routing;
- fuzzy matching;
- OLV formula;
- OLV weights;
- qué candidatos comparar;
- nuevos thresholds;
- activity gates;
- benchmark semantics;
- automatic promotion;
- bankroll transfer;
- drain conditions;
- historical corpus;
- si real betting está permitido.

---

# 23. Expected post-implementation sequence

```text
FS-023 code implemented
→ make check
→ make ci-check
→ migrations/UAT
→ bounded provider UAT
→ deploy verification

THEN

restore + verify frozen 2605 corpus

→ run [209] evaluation-only

if structurally valid:
→ run [209,216,223] selection

→ economic publication
→ activation=false

maintainer reviews publication

if KEEP #209:
→ current binding remains / ALREADY_ACTIVE

if explicit PROMOTE different binding:
→ StrategySwitchRequest
→ drain
→ new epoch
```

No automatic final step.

La primera activación T10 forma parte del deployment/cutover de FS-023 y debe ocurrir mediante el drain especificado en §12, no mediante mutación in-place del epoch FS-022. La posterior publicación del restricted selection mantiene `activation=false`; sólo una decisión humana explícita puede solicitar otro binding.


---

# 24. Question coverage e integrity audit final

## 24.1 Question coverage

| Research question | Status |
|---|---|
| Historical population | ANSWERED |
| Historical odds semantics | ANSWERED |
| Freshness | ANSWERED |
| T30/T10/T5 | ANSWERED |
| Scheduler cadence | ANSWERED |
| LIVE league universe | ANSWERED |
| Capacity/quota | ANSWERED |
| OLV | ANSWERED |
| API-F contract | ANSWERED |
| BSD suitability | ANSWERED WITH LIMITATION |
| BSD league mapping | ANSWERED |
| BSD event reconciliation | ANSWERED |
| Result fallback | ANSWERED |
| Regulation-time settlement | ANSWERED |
| historical/LIVE decoupling | ANSWERED |
| StrategyBinding | ANSWERED |
| epochs/drain/rollback | ANSWERED |
| Experiment Lab subset | ANSWERED |
| restricted challenge | ANSWERED |
| Economic Selector | ANSWERED BY REUSE |
| benchmark | ANSWERED |
| durable evidence contract | ANSWERED |
| real betting | OUT OF SCOPE / FORBIDDEN |

No blocking research question remains.

## 24.2 Integrity audit canónico

```text
primary question answered                PASS
secondary questions answered             PASS
historical/prospective separated          PASS
research vs final experiment separated   PASS
candidate set preregistered               PASS
retuning prohibited                       PASS
latest-state semantics preserved          PASS
provider limitations preserved            PASS
negative findings preserved               PASS
quota uncertainty preserved               PASS
strategy/P&L not used for league gate     PASS
real betting boundary preserved           PASS
implementation semantics executable       PASS
candidate-vs-binding identity              PASS
T30→T10 cutover/restart                     PASS
BSD bootstrap/shadow/validation             PASS
BSD topology/retry/config                    PASS
capacity claim honesty                       PASS
annual continuity evidence                   PASS_WITH_LIMITATION
corpus/hash validation                        PASS
compact package generated                     PASS
host durable package installed                PASS
host sha256 verification                       PASS
```

La única limitación explícita —no blocker— es que la concordancia BSD original tuvo muestra local cero. Esto queda controlado por SHADOW → gate 30/5/7 → PROBATION → STEADY, con API-F como settlement authority hasta la validación.


---

# 25. What can close / what remains

## 25.1 Cerrado por research

Se consideran cerrados:

- búsqueda de más ligas;
- expansión histórica;
- Quality Gate;
- comparación T30/T10/T5;
- T10 y wake 180 s;
- capacidad planning y degradación por quota;
- OLV;
- universo LIVE 28;
- BSD provider selection;
- BSD mapping/bootstrap/shadow/retry/config;
- result routing y ResultProvider semantics;
- historical/LIVE decoupling;
- candidate-vs-binding identity;
- StrategyBinding/StrategyEpoch/drain/rollback;
- Experiment Lab subset;
- restricted challenge 209/216/223;
- activity gate;
- Economic Selector reuse;
- benchmark methodology/input mode;
- artifact identity;
- durable materialization/hash gate.

## 25.2 Lo que queda es implementación

```text
F008 ticket construction
→ F009 technical preflight against actual checkout
→ implementation
→ tests
→ UAT
→ deployment/cutover T30→T10
→ post-implementation [209] evaluation-only
→ post-implementation [209,216,223] selection
→ publication activation=false
→ explicit human promotion only if desired
```

Nada de esto autoriza ampliar FS-023.


---

# 26. Stable bibliography y retained evidence

## 26.1 Finsport

- F001 — Contexto de producto Finsport, baseline durable aplicable.
- F002 — Contexto de dominio, reglas, privacidad y seguridad.
- F003 — Contexto técnico y arquitectura.
- F004 — Operación y entornos.
- F006 — Roadmap/backlog.
- F008 — Guía de definición y secuenciación de tickets.
- F009 — Guía de ejecución y seguimiento.
- F010 — Guía de investigación y handoff.
- FS-022 handoff/feedback final — baseline productivo previo.
- FS-023 compact evidence package y hashes especificados en §16.

## 26.2 External authoritative contracts usados por research

BSD official documentation, retrieved 2026-09-29:

- `https://sports.bzzoiro.com/docs/football/`
- `https://sports.bzzoiro.com/docs/football/events/`
- `https://sports.bzzoiro.com/docs/football/teams-players/`
- `https://sports.bzzoiro.com/docs/conventions/`

Contratos verificados allí: API v2, `Authorization: Token`, `/events/`, `/events/live/`, `/events/{id}/`, `/teams/`, `league_id/season_id/date_from/date_to`, `limit/offset` max 200, regulation-time scores, status values, 7,500/day free quota, separate burst/daily 429 semantics and `Retry-After`.

API-Football official pricing/usage, retrieved 2026-09-29:

- `https://www.api-football.com/pricing`

Free plan ~100 requests/day; physical FS-023 probes remain authority for actual season access/request forms.

MEF:

- official Letras del Tesoro material; 3/6/9/12-month reference tenors.

SBS:

- official passive-rate tables; PEN time-deposit buckets including 181–360 days.

No new external client is part of FS-023.

La implementación no debe volver a investigar estos contratos por ceremonia; F009 sólo revalida de forma bounded aquello que depende de estado externo mutable o del checkout efectivo.


---

# 27. Final disposition

```text
FS-023 RESEARCH
= CLOSED / CANONICAL / RECONSTRUCTED

this document
= SINGLE NARRATIVE AUTHORITY
= supersedes prior long + compact research versions

scientific/product blockers
= NONE

provider-contract blockers
= NONE

candidate/method blockers
= NONE

durable evidence host gate
= PASS

recommended packaging
= ONE COHESIVE FS-023 TICKET

next
= F008 ticket construction
→ F009/Codex
→ implementation/UAT
→ deployment/cutover
→ [209] evaluation-only
→ [209,216,223] selection
→ publication activation=false
→ explicit human promotion only if desired

real betting
= FORBIDDEN
```

La investigación no debe ampliarse de nuevo salvo que F009 encuentre una contradicción física material que invalide uno de los contratos congelados. Un hallazgo de implementación ordinario no reabre la metodología ni autoriza cambiar ligas, ventana, OLV, candidatos, thresholds, benchmark, corpus, provider authority o fronteras financieras.
