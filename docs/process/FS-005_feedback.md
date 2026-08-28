# FS-005 — Feedback de implementación

**Estado del documento:** `IMPLEMENTATION SNAPSHOT — MAY BECOME STALE`

Este documento es una fotografía factual del Pass 1 de implementación y de su único
Pass 2 consolidado pre-UAT. Puede quedar stale después de UAT o PR review. **No es
`FINAL RECONCILED FEEDBACK`**, no declara cerrado FS-005 y no afirma que el ticket esté
UAT-ready. El execution chat reconciliará el feedback final después de implementation
+ corrections + UAT + PR review.

## Identidad y alcance

- Ticket: `FS-005 — Implementar captura temporal de odds quota-aware`.
- Branch: `FS-005-odds-capture-planner`.
- Base post-FS-004: `1e93e97c81888c688f0955927f3ea43dc818286c`.
- Modo de producto: local-only, demo-only y research-oriented.
- Research: `docs/research/FS-005_odds_cadence_quota_research.md`, clasificado
  `REFERENCE ONLY` y no modificado durante Pass 1 ni Pass 2.
- Passes documentados: Pass 1 de implementación y un Pass 2 consolidado de corrección
  pre-UAT.

El alcance entregado es:

```text
canonical fixtures
→ quota-aware planning
→ kickoff-relative windows
→ bounded provider execution
→ append-only OddsObservation
→ protected result refresh
→ durable capture audit
→ optional default-off Celery wake
```

No se implementó ni se reclama optimización de cadence, rentabilidad, estrategia de
apuestas o verdad de producto sobre el mejor cutoff.

## Arquitectura entregada

- `football/capture/contracts.py` define ventanas, configuración, cuota, plan, trabajo
  y resultado estructurados.
- `football/capture/planner.py` construye planes deterministas desde fixtures
  canónicos, identidad, ventanas y evidencia local de cuota; el planner hace cero
  provider calls.
- `football/capture/executor.py` revalida bajo lock, ejecuta trabajo acotado, persiste
  auditoría y delega la ingestión a `sync_odds_payloads` y
  `sync_fixture_payloads`.
- `football/capture/locks.py` implementa single-flight con el advisory lock PostgreSQL
  `finsport:fs005:api_football`.
- `football/capture/service.py` y `football/capture/__init__.py` exponen el entrypoint
  Python reusable `run_capture(...)` compartido por operación manual, task y tests.
- `football/management/commands/run_football_capture.py` ofrece el comando manual con
  `--dry-run`, `--at`, filtros de match/purpose/window y límites que sólo estrechan la
  ejecución.
- `football/tasks.py` define la task segura `football.capture.wake`; sólo despierta al
  servicio común y conserva fallos pre-executor en auditoría.
- `finsport/settings.py` y `.env.dist` contienen ventanas, horizon, reserve, discovery,
  result refresh y bounds configurables con automatización default-off.
- `football/admin.py` registra runs y work items para inspección operativa.

## Correcciones consolidadas de Pass 2

El único Pass 2 pre-UAT corrigió cuatro findings sin cambiar schema, offsets, query
shape ni semántica de producto:

1. En `BOUNDED_BOOTSTRAP`, un `ODDS_CAPTURE` sin `allow_bootstrap=True` queda
   `QUOTA_RESERVE` con razón explícita y cero calls, independientemente del reserve. La
   regla se aplica en planning y otra vez durante la revalidación bajo lock. Result y
   fixture refresh obligatorios conservan el bootstrap bounded existente.
2. La precedencia determinista es result debt primero, odds due ordenadas
   lexicográficamente por expiración/coverage/freshness/kickoff/ID después, y discovery
   due al final. Discovery conserva cadence/config propia pero no desplaza odds due.
3. Cualquier `actual_attempts > 0` no fulfilled reclama esa misma
   `logical_identity` como `PROVIDER_BACKOFF`. Un guard de budget/quota disparado
   después de un attempt ya no se presenta como skip pre-call; una identidad temporal
   posterior sigue siendo válida.
4. El stratum competition/day convierte kickoff aware a `settings.TIME_ZONE`
   (`America/Lima`). La identidad absoluta de kickoff y el epoch de cuota UTC no
   cambiaron.

## Persistencia y contrato dry-run

La migración `football/migrations/0004_capturerun_captureworkitem.py` crea:

- `CaptureRun`: trigger/status, planning/start/completion, snapshot de configuración,
  base/límite/remaining/timestamp de cuota, reserve, attempts/pages/retries, efectos,
  skips/failures, summary y error sanitizado.
- `CaptureWorkItem`: purpose/status, source/match/market, identidad lógica, ventana,
  `target_at`, `not_before`, `not_after`, prioridad, costes esperados, attempts/pages/
  retries reales, efectos, cuota antes/después, `executed_at`, `completed_at`, lateness
  y error sanitizado.

La identidad exitosa de odds equivale a provider + fixture canónico + market + intended
window + `target_at`. Una `UniqueConstraint` condicional sobre `logical_identity` evita
más de una fila fulfilled (`SUCCESS`, `SUCCESS_EMPTY` o `LATE_CAPTURE`) para la misma
unidad lógica. El modo dry-run no crea `CaptureRun`, `CaptureWorkItem`,
`OddsObservation` ni ningún otro dato, y tampoco instancia el cliente del proveedor.

## Contrato de proveedor y cuota

API-Football es la fuente primaria y Match Winner/1X2 H-D-A es el baseline actual. La
captura usa `/odds?fixture=<external fixture id>&bet=<market external id>`; el valor
preflight del market es `1`. No se reabrió research ni se compararon shapes alternativos.

Cada HTTP attempt, incluidas páginas y retries, se presupuesta conservadoramente como
posible consumo. Los daily headers observados reconcilian el estado local y son la
autoridad de runtime; minute-only o ausencia de daily headers no inventan cuota diaria.
El epoch diario es UTC. Cuando faltan headers, sólo existe bootstrap acotado y
acumulado dentro del epoch UTC: odds opcionales requieren autorización explícita y el
trabajo obligatorio permanece sujeto al mismo bound. La reserva obligatoria protege el
trabajo canónico frente a odds opcionales.

El planner exige que el worst case de una operación quepa antes de admitirla. El
`attempt_guard` vuelve a admitir cada página/attempt antes de enviarlo. Pages, retries,
attempts por run, coste máximo por operación y bootstrap tienen bounds independientes;
un fallo o parcialidad detiene el resto del run con estado explícito en vez de abrir un
bucle de rescate.

## Ventanas y semántica temporal

La configuración exige `early` + `middle` y soporta como máximo un candidate adicional
cuyo nombre empiece por `near`. Los offsets incluidos actualmente son defaults de
research, no product truth ni una afirmación sobre el cutoff óptimo.

El modelo separa `target_at`, `not_before`, `not_after`, `executed_at`, `observed_at` y
`lateness_seconds`. Una ejecución dentro de tolerancia tardía pero fuera de tolerancia
normal queda `LATE_CAPTURE`; una ventana vencida antes del executor queda
`MISSED_WINDOW`. `OddsObservation.observed_at` conserva el momento real de ingestión:
no existe backdating hacia el target nominal.

## Idempotency y concurrencia

La misma intended window se cumple como máximo una vez. Una ventana posterior con otro
target conserva una identidad legítima distinta, incluso si el precio observado no
cambió; por tanto puede producir otra observación temporal válida. Cualquier estado no
fulfilled con attempts reales queda en backoff para esa identidad, mientras errores o
skips previos a un attempt no fabrican cumplimiento ni bloquean una replanificación
todavía válida.

El executor toma el advisory lock PostgreSQL y, bajo él, vuelve a evaluar cuota,
identidad, hora real, kickoff, status y outcome antes de cualquier call. El perdedor
concurrente registra `CONCURRENT_EXECUTOR` y realiza cero provider calls.

## Fixture discovery y result refresh

Existe discovery reusable por fecha local con cadence y número de días futuros
configurables. `FOOTBALL_CAPTURE_DISCOVERY_ENABLED=False` es el default, por lo que no
se repite discovery en cada wake ni en cada candidate de odds.

Result refresh está protegido y bounded. Consulta cada fixture por
`/fixtures?id=<external fixture id>`, reutiliza `sync_fixture_payloads` y mantiene
`Match.outcome` como autoridad canónica. Un outcome ya resuelto se clasifica
`ALREADY_FULFILLED`; un fixture final o cancelado/abandonado sin outcome canónico se
clasifica `STATUS_INELIGIBLE` para evitar loops. Si el kickoff cambió entre plan y
executor, el trabajo de odds actual queda `NOT_DUE` y debe replanificarse contra el
nuevo kickoff; otros cambios fuera de pre-match quedan explícitamente ineligibles.

## Lifecycle del scheduler

`FOOTBALL_CAPTURE_ENABLED=False` es el default. Con esa configuración `make up` puede
levantar worker y Beat, pero FS-005 no añade schedule; una invocación directa de la task
devuelve `DISABLED` y cero attempts. Al habilitarlo y reiniciar `make up`, settings
añade el wake periódico de Beat; el wake delega a `run_capture`, y un wake por sí solo
no implica provider call porque un plan sin trabajo due no instancia el cliente.

El runtime soportado requiere PostgreSQL, Redis, Django, el worker aislado
`finsport.local.safe` y Beat. Beat conserva el file scheduler; no usa schedules
persistidos de base de datos. La validación manual del lifecycle disabled/enabled y la
inspección Admin siguen pendientes.

## Disposición de Inkabet y seguridad financiera

Inkabet permanece secondary, read-only, GET-only y fail-soft dentro del flujo manual
existente. FS-005 no lo invoca ni agenda, y no extrapola hacia Inkabet quota headers,
reserve, reset ni cadence de API-Football. En Pass 2 pasaron 45 tests de comandos,
reconciliation y cliente Inkabet; el gate completo también pasó, por lo que A27 queda
PASS.

La implementación no autentica bookmakers, no coloca apuestas reales, no ejecuta el
Selenium histórico de betting y no realiza mutaciones financieras externas. Esas
acciones permanecen prohibidas.

## Evidencia automatizada

Las autoridades persistidas son `tmp/FS-005_focused_evidence.txt` para Pass 1 y
`tmp/FS-005_pass2_evidence.txt` para Pass 2.

Pass 1 dejó Black/Ruff, migration drift, Django check, `git diff --check` y 41 tests
enfocados en PASS. Pass 2 añadió esta evidencia:

- 29 tests de captura: PASS.
- 16 tests de cliente e inventario: PASS.
- 45 tests de comandos, reconciliation y cliente Inkabet: PASS.
- Combinación enfocada final: Black/Ruff PASS y 90 tests PASS.
- `make check`, ejecutado una sola vez: Black sobre 85 archivos, Ruff, Django check y
  197 tests PASS. Se observaron seis warnings de deprecation dentro de `penaltyblog`;
  no son fallos del gate ni fueron absorbidos por FS-005.
- `makemigrations --check --dry-run`: PASS, `No changes detected`.
- `git diff --check`: PASS, exit code 0.

Las nuevas regresiones cubren el opt-in obligatorio de bootstrap con reserve 0 y bajo
lock, result → odds → discovery bajo budget limitado, backoff de la misma identidad
después de un único attempt real bloqueado antes del retry, y el boundary UTC-midnight
del día calendario `America/Lima`. Toda interacción de proveedor se simuló con
fakes/mocks o un opener local que lanza timeout sin acceder a red.

## Estado de acceptance

El ledger contiene **40 PASS, 7 PENDING y 3 N/A**. El technical close continúa
bloqueado por estos required PENDING:

- dry-run UAT con identidad frozen (A38);
- captura real de odds con ceiling de un attempt (A39);
- rerun real same-window a cero calls adicionales (A40);
- result refresh real bounded o evidencia explícita de no aplicabilidad (A41);
- lifecycle manual disabled/enabled con `make up` (A42);
- inspección manual Admin/operator (A43);
- `Final FS-005 feedback` reconciliado (A48).

Los N/A son: no provocar live 429/timeout/5xx (se usaron fakes/mocks), failed-call quota
probe cerrado como `NOT PLANNED`, y toda autenticación/apuesta/Selenium/mutación
financiera real por estar expresamente prohibida.

## UAT frozen facts pendientes

No se ejecutó UAT en esta continuación. Quedan preparados, no validados:

- Odds: match `1158`, fixture API `1570362`, Sevilla–Atletico Madrid, kickoff
  `2026-08-29T19:30:00+00:00`, ceiling de un provider attempt.
- Result refresh: match `1142`, fixture API `1570336`, Celta Vigo–Osasuna, kickoff
  `2026-08-27T18:30:00+00:00`, ceiling de un provider attempt si sigue aplicable.
- Ceiling live total: dos attempts como máximo (uno odds + uno result refresh); el
  failed-call probe no está planificado.
- Evidencia preflight de cuota: daily remaining observado `98` después de discovery del
  fixture 2026-08-29; este valor es sólo la fotografía de preflight, no cuota actual.
- Probe del advisory lock PostgreSQL `finsport:fs005:api_football`: PASS.

## Pass, diff review y trabajo diferido

Se usaron Pass 1 de implementación y el único Pass 2 consolidado de corrección pre-UAT.
El budget normal de código pre-UAT quedó agotado; no corresponde un tercer pass salvo
un STOP/exception genuino. Este documento permanece snapshot y no es feedback final.

El complete-diff review está en `tmp/FS-005_diff_review.txt`. El artifact regenerado
tiene 4.938 líneas e incluye tracked unstaged, staged si existiera y
relevant untracked: feedback, migration, código/tests nuevos y research
maintainer-owned. El review cubre el conjunto completo y presta atención específica a
orden del planner, bootstrap, revalidación bajo lock, idempotency por attempts, día
local, tests y consistencia documental.

No se descubrió un finding material nuevo ni un ticket nuevo durante el Pass 2. Los
seis warnings externos de `penaltyblog` quedan sólo como advertencia factual. El trabajo
diferido real es exactamente el conjunto PENDING del ledger; no se decide roadmap desde
este snapshot.

## Estado al devolver control

El snapshot factual de Pass 1 + Pass 2 queda completo y el gate automatizado general
está verde. Los UAT requeridos y el feedback final reconciliado siguen pendientes. No
se ejecutaron provider calls ni UAT. El feedback final será reconciliado después de
implementation + corrections + UAT + PR review.
