# FS-023 — Feedback final de implementación y aceptación

**Ticket:** FS-023 — Runtime LIVE de 28 ligas, T−10, ResultProvider y estrategia versionada
**Branch:** `fs023-live28-t10-result-provider`
**Fecha:** 2026-09-30
**Disposition:** `FINAL IMPLEMENTATION / ACCEPTED`
**Modo financiero:** simulación exclusiva
**Real betting:** `false`

## 1. Resultado final

FS-023 transforma el runtime prospectivo de Finsport en un flujo versionado y auditable con:

- universo LIVE congelado de **28 competiciones**;
- **23** rutas con soporte BSD y **5** rutas API-Football-only;
- captura prospectiva automática de mercado exclusivamente en **T−10**;
- `football.pipeline.wake` con cadencia de **180 segundos**;
- scheduling de cuota y OLV con política productiva **60/25/15**;
- ResultProvider con BSD + API-Football;
- LIVE readiness desacoplada de historical readiness;
- `StrategyBinding` inmutable;
- `StrategyEpoch` con drain, switch, rollback y restart-safe;
- nuevo epoch T10 con banca inicial independiente de **100u**;
- Experiment Lab capaz de ejecutar los subsets `[209]` y `[209,216,223]`;
- publicación experimental sin activación automática (`activation=false`);
- ausencia de side effects financieros externos.

No se habilitó login de bookmaker, escritura externa, movimiento de dinero ni apuesta real.

## 2. Runtime LIVE y captura T−10

El mapping productivo queda fijado en exactamente 28 competiciones, sin sustitución automática por una liga número 29.

La adquisición futura T−6h / T−60m / T−30m deja de ser una obligación automática. `market-t10m` es la única ventana prospectiva automática de mercado.

La prueba real de T−10 utilizó:

- Match local: `55447`;
- fixture API-Football: `1549493`;
- target: `2026-09-30T19:50:00Z`;
- ejecución: `2026-09-30T19:51:10Z`;
- estado del trabajo: `SUCCESS`;
- observaciones creadas: **7**;
- intentos lógicos: **1**;
- provider retries: **0**;
- respuesta de odds: HTTP **200 / SUCCESS**.

La ejecución ocurrió dentro de la ventana normal T−10 y demostró planificación, admisión, persistencia de observaciones y auditoría real.

## 3. Cuota y OLV

El runtime revalida cuota antes de cada request físico y conserva las prioridades de discovery, T10, resultados y obligaciones protegidas.

La política OLV productiva queda en:

`60 / 25 / 15`

Las sensibilidades alternativas permanecen únicamente diagnósticas y no modifican los pesos productivos.

Una falta de cuota sin llamada admitida se distingue de una decisión económica mediante `MISSED_STRATEGY_WINDOW`.

## 4. ResultProvider BSD + API-Football

Se incorporó una frontera de ResultProvider sin crear un segundo settlement engine ni una segunda verdad canónica de Match.

BSD aporta:

- catálogo;
- bootstrap de equipos;
- identidad exact-unique;
- binding de eventos;
- shadow validation;
- probation/steady state;
- degradación y fallback;
- auth/backoff/circuit;
- normalización de estados y resultado reglamentario;
- preservación de conflictos.

API-Football continúa disponible como autoridad/fallback donde corresponde.

La evidencia real incluyó acceso a catálogo/equipos/eventos BSD, rutas reales, mappings y un binding real verificado para fixture `1549849` → BSD event `220285`.

## 5. Identidad y normalización BSD

El UAT encontró que la normalización BSD eliminaba puntuación y podía transformar:

`St. Louis City` → `st louis city`

pero:

`St.Louis City` → `stlouis city`

La corrección convierte puntuación Unicode en separador antes del colapso de espacios.

Se preservan:

- casefold;
- eliminación de diacríticos;
- exact-unique;
- fail-closed ante colisiones;
- ausencia de fuzzy matching;
- ausencia de similarity matching.

`Internacional de Bogota` y `Internacional de Bogotá` siguen normalizando a la misma identidad.

## 6. Auditoría de fallos de red BSD

El UAT demostró que dos `ConnectionError` consecutivos respetaban el retry bounded, pero el segundo `ProviderCallAudit` podía quedar en `STARTED`.

La corrección garantiza:

- exactamente dos intentos físicos como máximo en ese path;
- una sola espera de 2 segundos;
- ambos intentos fallidos terminan como `RESULT_PROVIDER_ERROR`;
- fallo cerrado mediante `BSDError`;
- ausencia de retry storm;
- metadata sin secretos.

## 7. StrategyBinding, StrategyEpoch y cutover

FS-022/T30 y FS-023/T10 son bindings distintos pese a compartir candidate 209.

El upgrade desde un runtime existente conserva el epoch T30 real y su historia.

El cambio:

1. bloquea nuevas entradas del epoch anterior;
2. permite liquidar OPEN correctamente;
3. impide que PENDING antiguo cree nueva exposición;
4. espera OPEN=0, PENDING=0, result debt=0 y reserved exposure=0;
5. activa un nuevo epoch T10;
6. inicia el epoch nuevo con exactamente **100u**;
7. no transfiere equity, P&L, cash ni reservas del epoch anterior;
8. es idempotente ante restart.

Rollback y `ALREADY_ACTIVE` siguen sujetos a identidad completa del binding.

## 8. Fresh-install convergence

El review del PR identificó que una base vacía podía ejecutar la migración 0019 antes de que existieran datos canónicos y luego no converger automáticamente a FS-023.

La solución conserva la migración existente y añade convergencia post-migración idempotente.

Mientras falten prerequisitos canónicos:

`FS023_NOT_READY`

El estado es fail-closed:

- no crea rutas parciales;
- no crea config automática;
- no fabrica un epoch T30;
- no inventa evidencia histórica.

Cuando existen las 28 Competition y sus API-F SourceRefs resueltas:

- valida hash y topología congelada;
- crea exactamente 28 rutas;
- crea 23 BSD + 5 API-F-only;
- crea el binding T10 aprobado;
- crea un único StrategyEpoch activo;
- crea una config automática T10 independiente de 100u;
- mantiene `real_betting=false`.

Provisioning repetido devuelve la misma autoridad sin duplicar route, binding, epoch, config ni switch.

El camino de upgrade poblado sigue siendo distinto y conserva la historia T30 real.

## 9. Reporting de T−10

El Match detail ahora reconoce un deployment con epoch FS-023 validado y conserva compatibilidad con la evidencia histórica FS-022.

La lista de capturas incluye:

- T−6 h histórica;
- T−60 min histórica;
- T−30 min histórica;
- **T−10 min** actual.

Una captura T10 persistida aparece tanto en el selector como en la página visible de detalle del partido.

## 10. Rebind BSD cross-midnight

El review detectó que un evento corregido dentro de ±15 minutos podía caer en el día UTC anterior y quedar fuera de la consulta del rebind.

El rebind ahora calcula la envolvente de fechas UTC tocada por:

`kickoff ± 15 minutos`

y mantiene después los filtros estrictos existentes:

- misma liga BSD;
- mismo home team mapeado;
- mismo away team mapeado;
- tolerancia temporal ±15m;
- exactamente un candidato.

Un reemplazo único previo a medianoche puede vincularse correctamente.

Cero candidatos o múltiples candidatos continúan fallando cerrados.

## 11. Experiment Lab

FS-023 permite ejecución por subset manteniendo IDs canónicos:

- `[209]` para evaluación-only;
- `[209,216,223]` para selección restringida.

El corpus congelado permanece en **2605 Matches**.

La publicación experimental no cambia el runtime automáticamente:

`activation=false`

No se añadieron nuevas técnicas, thresholds, políticas Capital ni retuning posterior a resultados.

## 12. Validación y gates

### UAT previo al PR

- mapping/config de 28 ligas: PASS;
- T10 timing y restart: PASS;
- quota/OLV: PASS;
- BSD auth/backoff/circuit: PASS;
- identidad de equipos/eventos: PASS;
- ResultProvider/status/conflict: PASS;
- Capital drain/cutover/epoch: PASS;
- Experiment Lab subset/corpus: PASS;
- U28 real provider bounded: PASS;
- U29 secret safety: PASS;
- U30 frontend regression: PASS.

### Pass 4

Correcciones consolidadas:

- normalización BSD;
- terminal audit de network failure.

Evidencia:

- tests focalizados: **4 passed**;
- subset afectado: **13 passed**;
- `make check`: **1013 passed**;
- `make ci-check`: **1013 passed**.

### Recovery Pass 5

Correcciones del review del PR:

- fresh-install convergence;
- Match detail T10;
- cross-midnight BSD stale-event rebind.

Evidencia:

- nuevos tests recovery: **4 passed**;
- suites afectadas: **139 passed**;
- fixture histórico + recovery: **9 passed**;
- `make check`: **1017 passed**;
- `make ci-check`: **1017 passed**;
- cobertura: **80.58%**;
- Black: PASS;
- Ruff: PASS;
- Django system check: PASS;
- `makemigrations --check --dry-run`: sin cambios;
- pip check: PASS;
- pip-audit: sin vulnerabilidades conocidas;
- `git diff --check`: PASS.

No se añadió ni modificó una migración en Recovery Pass 5.

## 13. Seguridad y operación

Durante las correcciones finales no hubo:

- llamadas nuevas a proveedores;
- escritura sobre la base operativa;
- side effects financieros;
- experimentos económicos nuevos;
- modificación de metodología;
- ampliación del universo LIVE;
- reactivación de R45;
- reactivación automática de Inkabet.

`real_betting=false` permanece como invariante.

## 14. Evidencia durable

Research/evidencia científica durable de FS-023:

`/home/ljarufe/Documents/finsport/research-evidence/FS-023/final/`

El paquete fue previamente validado con:

`sha256sum -c SHA256SUMS`

Los artefactos temporales de implementación/UAT permanecen bajo `tmp/` y no sustituyen la autoridad científica durable.

Recovery Pass 5:

- `tmp/TFS-023_42_pass5_handoff.md`
- `tmp/TFS-023_42_pass5_recovery_complete.diff`
- `tmp/TFS-023_42_pass5_make_check.txt`
- `tmp/TFS-023_42_pass5_ci_check.txt`

## 15. Deuda técnica registrada

Se conserva como deuda técnica separada de FS-023 la revisión de normalizadores/reconciliadores equivalentes entre proveedores.

La recomendación futura es evaluar:

- reuse-first de primitivas comunes;
- normalización Unicode/case/whitespace/punctuation compartida;
- exact-unique compartido cuando la semántica sea realmente equivalente;
- fixtures de conformidad comunes para diacríticos, puntuación adyacente, casing, espacios y colisiones;
- preflight explícito de ownership/reuse antes de introducir un helper nuevo.

No se realizó ese refactor dentro de FS-023.

## 16. Disposición final

La implementación de FS-023 queda técnicamente aceptada con:

- runtime LIVE de 28 ligas;
- captura económica T−10;
- wake 180s;
- quota/OLV;
- ResultProvider BSD/API-F;
- StrategyBinding/StrategyEpoch;
- cutover restart-safe;
- fresh-install convergence fail-closed e idempotente;
- reporting T10;
- rebind BSD cross-midnight;
- Experiment Lab por subsets;
- publicación sin activación automática;
- `real_betting=false`.

Los findings de UAT y del review del PR fueron incorporados en correcciones consolidadas y los gates finales quedaron verdes.

**Disposition técnica:** `ACCEPTED`.
