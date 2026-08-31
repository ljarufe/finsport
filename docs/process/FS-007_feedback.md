# FS-007 — FINAL-STATE FEEDBACK BEFORE EXECUTION-CHAT RE-UAT

> **IMPLEMENTATION + POST-UAT CORRECTION COMPLETE**
> **EXECUTION-CHAT RE-UAT AND FINAL SHIPPING DECISION PENDING**

Este documento reconcilia acumulativamente el estado de FS-007 después de la
implementación, la UAT original y la corrección post-UAT. No declara el ticket
merged ni completado, y no presume GitHub CI o review.

## 1. Estado de aceptación actual

```text
implementation: complete
post-UAT correction: complete
technical gates: green
original UAT B–J: complete
UAT A historical degraded finding: documented and corrected
UAT A post-fix real healthy pipeline: demonstrated
execution-chat re-UAT: pending
final shipping decision: pending
GitHub CI/review: not yet claimed
```

La ejecución histórica de UAT A reveló una pérdida causal real. La corrección
resultante cambió materialmente los boundaries de providers, captura, pipeline,
tasks y sincronización. Una segunda ejecución real produjo un pipeline saludable,
pero todavía corresponde al execution chat repetir/reconciliar UAT antes de la
decisión final de shipping.

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
- El smoke inicial/estabilizado de Grafana, Loki y Alloy midió aproximadamente
  354.4 MiB RSS combinado. Un snapshot posterior durante UAT midió
  aproximadamente 388.62 MiB RSS de observabilidad. Ambas mediciones permanecen
  por debajo del criterio de aceptación de 2 GiB; ese envelope continúa siendo
  una referencia de planificación, no una cuota física del filesystem.
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

Alloy y Compose no se modificaron durante la corrección post-UAT, por lo que no
se declara una revalidación nueva de ellos en esa pasada. Sus validaciones y UAT
anteriores siguen siendo la evidencia aplicable al delta sin cambios.

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

No se inventan tickets ni prioridades para estos hallazgos.

## 16. Aprendizajes del proceso

1. El estado de falla del provider por sí solo es insuficiente; los datos causales
   deben originarse en el provider boundary.
2. Las capas superiores no pueden reconstruir información descartada abajo.
3. La UAT real encontró una rama de pérdida diagnóstica que los tests sintéticos
   no habían cubierto.
4. La calidad del Incident Packet debe probarse con fallas reales de provider,
   además de fallas controladas.
5. Las suposiciones sobre paths host son inseguras cuando los logs viven en un
   named Docker volume.
6. La salida UAT larga debe redirigirse a `tmp/` desde el comienzo.
7. Una corrección post-UAT material obliga a regenerar el diff-review y
   reconciliar feedback antes de shipping; no es trabajo ceremonial.

## 17. Disposición actual

```text
implementation + post-UAT correction complete
technical gates green
original UAT B–J complete
historical UAT A degraded finding documented
post-fix real UAT A healthy evidence available
execution-chat re-UAT still pending
final shipping decision still pending
```

No se realizó commit, push, PR, merge ni acción Planka. No se declara todavía
GitHub CI/review.
