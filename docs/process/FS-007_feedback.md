# FS-007 — FINAL IMPLEMENTATION / UAT FEEDBACK

> **IMPLEMENTATION + POST-UAT CORRECTION + EXECUTION-CHAT RE-UAT COMPLETE**
> **PR REVIEW CORRECTION INCLUDED; FINAL REVIEW / MERGE STILL PENDING**

Este documento reconcilia acumulativamente el estado de FS-007 después de la
implementación, la UAT original y la corrección post-UAT. No declara el ticket
merged ni completado, y no presume GitHub CI o review.

## 1. Estado de aceptación actual

```text
implementation: complete
post-UAT causal correction: complete
original UAT B–J: complete
execution-chat re-UAT: complete
technical acceptance: 58/58 PASS
blocking pending: 0
GitHub PR review: one P2 Alloy rotated-spool finding corrected
final PR re-review / merge: pending
```

La UAT histórica A reveló una pérdida causal real en el boundary de
API-Football. La corrección post-UAT amplió de forma material los diagnostics de
providers, captura, pipeline, tasks y sincronización. La re-UAT posterior
demostró un pipeline real saludable, adquisición real de odds, Inkabet read-only
y propagación de un fallo de transporte controlado hasta Loki.

Durante el review de GitHub apareció además un finding P2 localizado en la
discovery de spools rotados de Alloy. La corrección forma parte del estado actual
del ticket y se documenta en la sección dedicada al review.

## 2. Implementación acumulativa

La arquitectura operacional local implementada es:

```text
Finsport structured JSONL
→ Alloy 1.19.0
→ Loki 3.7.6
→ Grafana OSS 13.2.0
```

- Grafana sólo se expone en `127.0.0.1:3000` y requiere autenticación.
- Loki y Alloy permanecen internos a la red de Compose.
- Ningún servicio monta el Docker socket.
- PostgreSQL y Django Admin continúan como audit canónico del dominio.
- El watchdog calcula liveness desde la base de datos y no depende de Redis.
- Los servicios normales y el perfil de observabilidad usan logging Docker
  `json-file` acotado a 10 MiB por archivo y tres archivos.
- El spool JSONL vive en el volume nombrado `logs_volume`, bajo
  `/app/logs/observability`; Alloy monta el mismo volume read-only.
- Loki conserva datos durante 720 horas, limita ingress a 0.0005 MB/s con burst
  de 1 MiB y usa almacenamiento local persistente.
- El evento serializado tiene un máximo de 16 KiB; cada spool rota a 1 MiB con
  cuatro backups. El envelope esperado del source spool es aproximadamente
  20 MiB para cuatro identidades.
- El envelope de planificación total es aproximadamente 2 GiB. No es una cuota
  física del filesystem.
- El smoke inicial estabilizado de Grafana, Loki y Alloy midió aproximadamente
  354.4 MiB RSS combinado. Una captura UAT posterior midió aproximadamente
  388.62 MiB para observabilidad. Ambas mediciones quedan muy por debajo del
  envelope de aceptación de 2 GiB; la segunda es la observación más reciente.
- No se añadieron Prometheus, OpenTelemetry, Tempo, Sentry, Flower ni APM.

La interfaz operacional host-only quedó en el `Makefile`; `.env.dist` documenta
los toggles seguros y exige que la contraseña local de Grafana se defina fuera
del repositorio. La guía del operador es
`docs/operations/observability_incident_triage.md` y el README enlaza esa ruta.

No hubo cambios de modelos, esquema Django ni migrations.

## 3. Contrato, labels, taxonomía y bounds

El contrato de eventos es:

```text
schema = finsport.observability.v1
```

Los labels Loki exactos son:

```text
schema
service_name
severity
event_code
component
```

Los run IDs, task/request IDs, provider, operation, failure kind, fingerprint,
excepción, traceback y contexto permanecen como campos JSON, no como labels. El
fingerprint usa campos estables y excluye timestamps e IDs efímeros.

Taxonomía final de runtime:

- `PIPELINE_SUCCEEDED`
- `PIPELINE_DEGRADED`
- `PIPELINE_FAILED`
- `PIPELINE_TASK_FAILED`
- `CAPTURE_DEGRADED`
- `CAPTURE_FAILED`
- `CAPTURE_TASK_FAILED`
- `PROVIDER_DEGRADED`
- `PROVIDER_OPERATION_FAILED`
- `SYNC_OPERATION_FAILED`
- `DJANGO_RUNTIME_FAILED`
- `RECONCILIATION_PENDING`
- `RECONCILIATION_CHECK_FAILED`
- `PIPELINE_OVERDUE`
- `OBSERVABILITY_WATCHDOG_FAILED`

`OBSERVABILITY_SMOKE_SUCCEEDED` existe sólo para validar transporte. `NO_WORK`,
`SKIPPED` y un `UNAVAILABLE` legítimo no generan automáticamente un incidente.

El traceback pertenece al boundary donde la excepción adquiere significado
operacional. La causa se transporta entre capas sin producir un traceback por
cada layer. El contexto es allowlist-only; mensajes, URLs y valores se sanitizan
centralmente; las claves secret-like se excluyen; no se guardan payloads completos,
headers/cookies completos, env, settings ni locals. El contexto, los summaries y
el evento completo tienen límites explícitos.

## 4. Semántica de liveness

```text
last_attempted
→ latest completed SUCCESS | DEGRADED | FAILED
→ any trigger

last_scheduler_activity
→ latest completed scheduler
   SUCCESS | DEGRADED | FAILED | NO_WORK
```

- `NO_WORK` prueba liveness del scheduler, pero no reemplaza `last_attempted`.
- Una ejecución manual no oculta un Beat muerto.
- Con el pipeline deshabilitado nunca se emite overdue.
- Cadencia: 900 segundos.
- Grace: 900 segundos.
- Threshold: sólo overdue después de 1,800 segundos; el borde exacto no lo es.

La corrección de monitoring epoch evita que actividad legítima de un episodio
anterior vuelva stale a un pipeline recién habilitado:

```text
reference_at = max(
    monitoring_since,
    last_scheduler_activity.completed_at,
)
```

si ambos valores existen; si sólo existe uno se usa ése. Actividad scheduler
posterior al enablement sí pasa a ser la referencia. Las regresiones cubren los
cuatro estados terminales de scheduler, `NO_WORK`, ejecución manual, disabled y
los bordes 1800/1801.

## 5. Workflow humano y operador

El flujo demostrado es:

```text
Grafana incident row
→ human structured drill-down
→ copy Incident Packet JSON
→ correlate run IDs in Django Admin
→ follow quick guide
→ ticket/chat handoff
```

El Incident Packet contiene lo necesario para iniciar diagnóstico sin entregar
payloads ni secretos. La guía incluye filtros, interpretación, drill-down al
audit canónico, fallback, redacción antes de compartir y plantilla compacta de
handoff.

## 6. UAT original B–J

Los escenarios B–J fueron ejecutados y completados; no se sustituyeron por
resultados unitarios:

- **UAT B — controlled DEGRADED:** confirmó el terminal degradado, la correlación
  con audit y el ownership operacional sin spam por fase.
- **UAT C — controlled FAILED/unexpected exception:** confirmó el incidente
  terminal con traceback único, el drill-down humano en Grafana y el transporte
  JSONL → Alloy → Loki → Grafana. Durante este escenario apareció el finding
  real de Alloy documentado en la sección siguiente; el retry posterior pasó.
- **UAT D — HTTP-200 provider schema drift:** confirmó que el operador recibe
  endpoint, metadata HTTP y shape/path seguros sin payload completo.
- **UAT E — reconciliation:** confirmó eventos agregados por `Source`, sin un
  evento por cada `SourceRef`, y el vínculo con el audit de reconciliación.
- **UAT F — scheduler/overdue:** confirmó `last_attempted`, actividad scheduler,
  `NO_WORK`, ejecución manual, disabled, cadence/grace/threshold y monitoring
  epoch.
- **UAT G — runtime dependencies:** ejercitó los drills controlados de DB, Redis,
  Celery y Beat, distinguiendo liveness DB-only del watchdog, fallas de task y
  silencio del scheduler.
- **UAT H — workflow:** un humano localizó el incidente en Grafana, abrió el
  detalle, copió el Incident Packet, correlacionó IDs en Django Admin y recorrió
  la guía operacional.
- **UAT I — seguridad/bounds:** validó canaries, redacción, ausencia de secretos
  y payloads completos, ruido saludable acotado, rotación, retención,
  almacenamiento y envelope de recursos.
- **UAT J — safety:** confirmó pipeline default OFF, providers read-only y
  ausencia de apuestas, login de bookmaker o mutación financiera.

## 7. Finding de UAT C — falso drop en Alloy

UAT C detectó un finding de producto real: Alloy descartaba una línea que ya
contenía `access_token=[REDACTED]`. La expresión de defensa en profundidad tenía
un matcher de valor demasiado amplio y clasificaba el sentinel de redacción como
si fuera un secreto residual.

La corrección restringió el alfabeto aceptado para un valor credential-like, de
modo que `[REDACTED]` ya no coincide, mientras un valor canary real sí se descarta.
La validación/retry posterior recorrió correctamente JSONL → Alloy → Loki →
Grafana. El finding no se reclasifica como error del harness.

## 8. UAT A histórica — pérdida causal demostrada

Identidad exacta de la ejecución:

```text
PipelineRun: 15
CaptureRun: 38
CaptureWorkItem: 356
Match: 1554
API-Football fixture: 1550103
purpose/window: ODDS_CAPTURE / middle
pipeline terminal: DEGRADED
capture terminal: FAILED
work item: FAILED_PROVIDER
exception: APIFootballResponseError
provider attempts/pages/retries: 1 / 0 / 0
```

El audit de CaptureRun 38 y WorkItem 356 sólo conservó:

```text
APIFootballResponseError
API-Football returned a provider error response.
```

El provider había devuelto `errors` dentro de JSON válido, pero Finsport descartó
la causa de aplicación. La causa histórica exacta es irrecuperable y no se
infiere ni inventa.

## 9. Root cause post-UAT

La auditoría causal confirmó estas pérdidas:

1. La rama `payload["errors"]` descartaba `response_metadata`.
2. Esa misma rama descartaba la causa reportada por el provider y, con ella, su
   categoría, claves y summary seguros.
3. `attempts` se capturaba antes de la actualización final del contador, por lo
   que el evento podía mostrar cero después de una llamada real.
4. Algunas ramas HTTP/transport carecían de contexto estructurado suficiente.
5. El parser MW3W de Inkabet podía escapar del boundary fail-soft ante drift.
6. Boundaries externos de tasks podían reemplazar metadata de provider por una
   clasificación inesperada genérica.

La pérdida principal nació en API-Football, pero el audit encontró gaps
secundarios en capture accounting, Inkabet y propagación de tasks. Las capas
superiores no podían reconstruir información ya descartada por el provider
boundary.

## 10. Corrección post-UAT — estado final

### API-Football

Las ramas materiales ahora son distinguibles mediante excepción, mensaje seguro,
`failure_kind` y contexto acotado:

- `provider_configuration` para configuración ausente/inválida;
- `provider_authentication`, `provider_rate_limit` y `provider_http` para auth,
  rate y otros estados HTTP;
- `provider_transport` con categoría timeout/unreachable;
- `provider_application_error` para `errors` en JSON válido;
- `provider_access_denied` para denegaciones conocidas de plan/fecha/temporada;
- `provider_schema_drift` para JSON inválido o shape/path inesperado;
- `provider_pagination`, `provider_quota` y `provider_budget` para sus límites.

Cuando existen, sobreviven `endpoint_family`, `http_status`, `content_type`,
`response_size` y `provider_request_id`. Los errores reportados por el provider
se reducen a `provider_error_category`, `provider_error_keys` y
`provider_error_summary`: sólo escalares acotados, claves no sensibles y texto
sanitizado. No se conserva el payload arbitrario.

### Inkabet

El cliente conserva diagnósticos estructurados para configuración, HTTP,
timeout/unreachable, JSON inválido y schema/interface drift. Reconciliación de
categories y MW3W validan shapes y precios; los drift se convierten en
`provider_schema_drift` con path/shape seguros. El comando captura parse/sync
MW3W dentro del boundary `InkabetError`, por lo que Inkabet continúa read-only y
fail-soft respecto del provider primario.

### Propagación

- `CaptureExecutor` calcula `attempts` después de la llamada y adjunta el delta
  real a la causa operacional.
- `CaptureResult.operational_cause` transporta provider, operation, failure kind,
  excepción y `diagnostic_context` seguro.
- El terminal de pipeline recibe esa causa junto con PipelineRun/CaptureRun IDs.
- Los boundaries Celery y sync conservan metadata causal en vez de convertirla
  automáticamente en unexpected failure.
- Una misma causa conserva un único ownership operacional y un traceback, sin
  eventos/tracebacks duplicados por cada capa.

## 11. Validación real post-UAT

### API-Football y pipeline

La corrección reportó dos llamadas reales de API-Football. La última cuota
observada fue 83/100 remaining.

```text
PipelineRun: 16 / SUCCESS
CaptureRun: 39 / SUCCESS
CaptureWorkItem: 370
Match: 1555
API-Football fixture: 1570358
purpose/window: ODDS_CAPTURE / middle
provider calls/pages/retries: 1 / 1 / 0
OddsObservations: 13
PredictionExperiment IDs: [9, 10] (reused)
Capital/decision evidence IDs: [8, 9, 10, 11]
```

Prediction terminó `NO_WORK` porque reutilizó identidades existentes; los
experimentos y decisiones ya existían, no por un fallo de la fase. El probe
read-only del fixture histórico 1550103 ahora fue `SUCCESS`, devolvió un
resultado y consumió una llamada. Por ello no reapareció naturalmente un error
de aplicación después de la corrección y la causa histórica continúa siendo
irrecuperable.

### Inkabet

Se hicieron dos llamadas reales read-only: categories y MW3W. Se encontró
Osasuna–Getafe, evento `f-DgPyBTXq9UqXpaT_0V0s1Q`, con MW3W válido y precios
2.15 / 2.85 / 3.95. No hubo auth, login, apuesta ni mutación financiera.

### Observabilidad causal

El evento `PIPELINE_SUCCEEDED` de PipelineRun 16/CaptureRun 39 quedó visible en
el named volume y exactamente una vez en Loki. Una falla representativa
controlada demostró que el Incident Packet conserva:

```text
endpoint_family
http_status
content_type
response_size
provider_request_id
provider_error_category
provider_error_keys
provider_error_summary
attempts
```

El canary, payload completo y secretos no aparecieron; PipelineRun/CaptureRun IDs
fueron correctos y hubo un solo traceback causal.

### Re-UAT final del execution chat

La re-UAT independiente posterior a la correction confirmó:

```text
PipelineRun 16 → SUCCESS
CaptureRun 39 → SUCCESS
CaptureWorkItem 370 → SUCCESS
provider attempts/pages/retries → 1 / 1 / 0
OddsObservations creadas → 13
Loki PIPELINE_SUCCEEDED para pipeline_run_id=16 → exactamente 1
```

Inkabet volvió a ejercitarse de forma real y read-only con dos GET: categories y
MW3W. Osasuna–Getafe fue localizado y el mercado MW3W volvió válido. No hubo
login, auth de bookmaker, apuesta ni mutación financiera.

También se ejercitó un fallo de transporte determinista redirigiendo únicamente
el proceso UAT de API-Football a un endpoint local cerrado. El resultado fue:

```text
APIFootballTransientError
failure_kind=provider_transport
endpoint_family=fixtures
transport_category=unreachable
SOURCE_EVENT_COUNT=1
LOKI_EVENT_COUNT=1
same event_id in source and Loki
```

La primera consulta inmediata a Loki devolvió cero porque Alloy ingiere de forma
asíncrona. Un recheck con espera acotada encontró el mismo evento una vez en el
source JSONL y una vez en Loki. Se clasifica como **HARNESS RACE / EVENTUAL
CONSISTENCY**, no como defecto de producto.

Un probe adicional que anteriormente reproducía una denegación de plan ya no la
reprodujo: API-Football respondió normalmente y no se emitió
`PROVIDER_OPERATION_FAILED`, que fue el comportamiento correcto. Las failure
classes que no dependen de una coincidencia externa quedan cubiertas por tests y
controlled UAT determinista.

## 12. Disposición de EVENT_COUNT=0

```text
HARNESS MISTAKE
```

El script anterior inspeccionó el path host `./logs/observability`, pero los logs
viven en el named volume `logs_volume` montado en `/app/logs`. La verificación en
la ubicación real encontró exactamente un JSONL para PipelineRun 15/CaptureRun
38, y Loki contenía exactamente un `PIPELINE_DEGRADED` para PipelineRun 15.

Ese evento histórico sí se emitió y transportó; su contexto seguía siendo
genérico porque la causa ya se había perdido en el provider boundary. No se
cambió producto para resolver el falso `EVENT_COUNT=0`.

## 13. Evidencia automatizada y gates actuales

```text
affected/focused suite → 146 passed
make check → PASS
full pytest suite → 261 passed
Black → PASS (103 files unchanged)
Ruff → PASS
Django check → PASS (0 issues)
git diff --check → PASS
```

La suite completa conserva seis warnings conocidos de Penaltyblog/NumPy. No se
demostró impacto funcional y quedan fuera del alcance de FS-007.

La corrección causal post-UAT original no modificó Alloy ni Compose. La re-UAT
posterior sí confirmó nuevamente el transporte JSONL → Alloy → Loki para el
pipeline saludable y para `provider_transport`. Posteriormente, el review de
GitHub introdujo un delta localizado únicamente en la discovery de archivos de
Alloy para incluir backups rotados; ese delta exige validación nativa de Alloy y
un UAT específico de recuperación de rotated spool antes del push/merge. Compose
no cambió por ese finding.

## 14. Seguridad y defaults

```text
FOOTBALL_PIPELINE_ENABLED=False
CELERY_BEAT_SCHEDULE={}
providers used read-only
no real betting
no bookmaker authentication/login
no financial mutation
```

`make_bets` permanece fail-closed. No se usaron credenciales de bookmaker, no se
ejecutó el path histórico Selenium y no se purgó estado persistente de Redis,
PostgreSQL ni volúmenes.

## 15. New Work Discovered

- **Evidencia:** la suite completa emite seis warnings de deprecación de
  Penaltyblog/NumPy. **Impacto:** ruido sin impacto funcional demostrado.
  **Recomendación:** mantenimiento separado de dependencias.
- **Evidencia:** Grafana mostró warnings de startup por plugins duplicados/API de
  alerting mientras provisioning y dashboard funcionaron. **Impacto:** no se
  demostró impacto funcional. **Recomendación:** investigar sólo si reaparece con
  efecto observable; no ampliar FS-007 preventivamente.
- **Candidato futuro de refactor:** propagación de contexto causal mediante un
  `causal_trail` estructurado y acotado. El estado actual transporta una causa
  primaria rica desde provider → capture → pipeline → evento terminal y conserva
  un único traceback operacional. Sin embargo, si un ciclo contiene varias
  causas independientes, el terminal prioriza la primera causa completa y las
  restantes pueden quedar representadas sólo por conteo/audit de dominio. Un
  futuro refactor podría conservar `primary_cause` + una lista compacta de 3–5
  causas secundarias (`component`, `operation`, `failure_kind`, `provider`,
  `exception_type`, `safe_summary`) sin duplicar tracebacks ni introducir
  OpenTelemetry salvo que tracing distribuido se vuelva un requisito demostrado.

No se inventan tickets ni prioridades para estos hallazgos. El candidato de
`causal_trail` se entrega al roadmap/handoff para evaluación futura.

## 16. Aprendizajes del proceso

1. El estado terminal del provider no basta: los datos causales deben originarse
   en el boundary más bajo que todavía conoce la causa concreta.
2. Las capas superiores enriquecen contexto; no deben reconstruir información
   que una capa inferior descartó.
3. Una misma causa debe tener un único owner operacional y, cuando corresponda,
   un solo traceback. Evitar provider → capture → pipeline → task duplicando la
   misma excepción.
4. La UAT real puede invalidar confianza sintética: FS-007 encontró una pérdida
   causal que los tests iniciales no habían detectado.
5. La calidad del Incident Packet debe probarse tanto con happy paths reales como
   con failures controladas representativas.
6. Las failures controladas deben ser deterministas cuando sea posible; no se
   debe depender de que un provider externo reproduzca casualmente un error
   histórico.
7. La cuota real de providers es un recurso de diagnóstico cuando el maintainer
   autoriza su uso. Debe usarse de forma acotada y útil, no minimizarse por
   ceremonia ni gastarse sin objetivo.
8. Cualquier comando con salida potencialmente larga debe redirigir a `tmp/`
   desde el comienzo. No se repite una operación cara sólo para recuperar output
   perdido.
9. Los artefactos `tmp/**` son efímeros. No se reconstruyen ni mantienen mediante
   pasadas exclusivas de Codex, y nunca justifican una pasada de código adicional.
10. Toda pasada real de Codex que cambie código debe entregar en esa misma pasada
    el diff actual, el estado UAT correspondiente y el acceptance ledger si éste
    sigue siendo útil durante desarrollo. Pass 1 crea el ledger para tickets
    materiales; las pasadas posteriores lo reconcilian mientras exista.
11. El presupuesto normal es de hasta cuatro pasadas de código Codex:
    implementation, correction pre-UAT, correction post-UAT y correction PR/CI.
    Una pasada puramente documental está prohibida.
12. La documentación versionable que pertenece a una implementación/correction se
    genera en esa misma pasada. El feedback final versionado se entrega al final
    desde execution chat, sin gastar Codex únicamente para documentación.
13. Una corrección material invalida sólo las UAT/gates de las superficies que
    cambió. Debe hacerse delta-UAT; no repetir toda la ceremonia.
14. Antes de UAT deben declararse explícitamente servicios, perfiles, credenciales,
    env vars, estado persistente y cualquier otra precondición.
15. Hay que entender la topología Docker real antes de declarar evidencia ausente:
    en FS-007 el spool vive en un named volume, no en `./logs/observability` del
    host.
16. JSONL → Alloy → Loki es eventualmente consistente. Un query inmediatamente
    posterior a la emisión puede devolver cero; el harness correcto espera/pollinea
    con timeout acotado antes de clasificar una pérdida de ingestión.
17. Debe distinguirse siempre **Product Finding** de **Harness Finding**. FS-007
    tuvo ambos: pérdida causal y regex Alloy fueron producto; path host incorrecto
    y query demasiado temprano fueron harness.
18. Mediciones sucesivas no se reemplazan silenciosamente: registrar smoke inicial
    y UAT posterior, usando la medición más reciente para claims de estado actual.
19. Una corrección post-UAT material obliga a que el diff y el feedback versionable
    representen el comportamiento nuevo antes del shipping; esto no implica crear
    una pasada documental separada.
20. El cierre mantiene la secuencia: UAT → gates invalidados → stage explícito →
    commit → push → PR/CI/review → correction localizada si aparece → feedback
    final/handoff → merge → sync/cleanup → Planka Done.

## 17. Finding de GitHub review — rotated spools no descubiertos por Alloy

GitHub review detectó un finding P2 válido en `config/alloy/config.alloy`. La
discovery original sólo incluía:

```text
/app/logs/observability/*.jsonl
```

pero la rotación de Finsport renombra backups retenidos como:

```text
<service>.jsonl.1
<service>.jsonl.2
<service>.jsonl.3
<service>.jsonl.4
```

Si Alloy permanecía detenido o suficientemente rezagado mientras el spool
rotaba, al reiniciar descubría el archivo corriente pero no los backups que
contenían backlog aún retenido. `tail_from_end=false` sólo podía ayudar para
archivos que Alloy efectivamente descubriera.

La corrección amplía la discovery para incluir current + backups y excluye los
lock files:

```alloy
local.file_match "finsport_events" {
  path_targets = [{
    "__path__"         = "/app/logs/observability/*.jsonl*"
    "__path_exclude__" = "/app/logs/observability/*.jsonl.lock"
  }]
  sync_period = "5s"
}
```

El cambio mantiene la política de rotación existente y no añade Docker socket,
nuevo storage ni cambios de runtime Python. El shipping gate específico de este
delta es validar la config de Alloy y demostrar recuperación de un evento que
existe únicamente en un backup rotado durante un periodo con Alloy detenido.

Este finding debe preservarse como aprendizaje: **storage bounded y collector
discovery deben diseñarse conjuntamente**. Retener backups no garantiza
observabilidad si el collector no puede redescubrirlos después de downtime.

## 18. Disposición actual

```text
implementation complete
post-UAT causal correction complete
execution-chat re-UAT complete
technical acceptance 58/58 PASS
0 blocking pending
GitHub review P2 rotated-spool correction included in current worktree
final PR re-review / merge pending
```

No se declara todavía merge ni Planka Done. El posible `causal_trail` queda como
New Work Discovered para roadmap futuro, no como blocker de FS-007.
