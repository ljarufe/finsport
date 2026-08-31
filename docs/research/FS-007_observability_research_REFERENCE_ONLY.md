# Finsport — investigación profunda pre-ticket para FS-007: observabilidad y auditoría operacional

**Estado:** `REFERENCE ONLY`
**Proyecto:** Finsport
**Candidato:** FS-007
**Research brief:** Finsport — Deep Research pre-ticket para FS-007
**Fecha:** 30 de agosto de 2026
**Modelo operativo:** `local-only / demo-only / research-oriented`
**Alcance:** arquitectura y requisitos; no implementación, no ticket, no branch, no migraciones, no automatización externa y no real betting.

> Este documento es un informe de research. Recomienda; **F008 decide y promueve**.
> Las restricciones de producto, dominio y seguridad ya cerradas por Finsport conservan su autoridad propia.
> Las decisiones de stack, esquema de eventos, retención y sizing de este documento son **RECOMMENDATION FOR F008 PROMOTION**, no autoridad automática del ticket.

---

## 1. Executive summary

El problema de FS-007 es **diagnosticabilidad operacional local**, no construir una plataforma general de observabilidad. Finsport ya conserva en PostgreSQL la auditoría funcional de ejecuciones y resultados de dominio. La nueva capa debe explicar **qué se rompió, dónde, cuándo, por qué y con qué excepción/contexto**, y debe correlacionar esa evidencia con los objetos ya persistidos sin duplicarlos.

### RECOMMENDATION FOR F008 PROMOTION

La arquitectura mínima recomendada es:

```text
Grafana OSS
+
Loki monolithic / single-node
+
Grafana Alloy
+
structured low-noise Finsport operational events
+
existing PostgreSQL/Django Admin for domain audit
+
Incident Packet derived from structured incident evidence
```

La correspondencia entre requisito y componente es directa:

| Componente | Función estrictamente necesaria |
|---|---|
| **Grafana OSS** | Interfaz humana para descubrir, filtrar, buscar, abrir detalle, inspeccionar traceback/campos, copiar JSON y representar el estado de `PIPELINE_OVERDUE`. |
| **Loki monolítico** | Storage consultable y retenible de los pocos eventos operacionales; LogQL permite búsqueda, agregación, conteos y detección de ausencia. |
| **Grafana Alloy** | Desacopla Finsport de Loki, recolecta y procesa el stream de eventos, añade metadata estable y aporta una segunda barrera de sanitización. |
| **PostgreSQL + Django Admin existentes** | Conservan la auditoría de dominio y permiten drill-down a `PipelineRun`, `CaptureRun`, experimentos y SourceRefs. |
| **Incident Packet** | Forma de entregar a un humano o agente técnico evidencia autosuficiente derivada del evento estructurado y, cuando haga falta, agregados por fingerprint. |

Grafana cubre el flujo humano requerido mediante Logs Drilldown/Explore, incluyendo búsqueda, detalle, contexto y exportación de logs [R2][R3][R4]. Loki favorece labels de baja cardinalidad y dispone de structured metadata para datos de alta cardinalidad, lo que encaja con separar `service_name`, `severity` y `event_code` de IDs de ejecución [R6][R7]. Alloy puede leer y procesar fuentes de archivos y escribir en Loki [R14][R15][R16].

### Componentes explícitamente fuera de FS-007

```text
Prometheus
OpenTelemetry Python SDK
Tempo
Sentry self-hosted
Flower
Promtail
Docker Loki logging plugin
Docker socket access in Alloy by default
Alertmanager
custom observability frontend
generic APM
cloud observability SaaS
external notifications
email
webhooks
GitHub / Planka / ChatGPT automation
```

Prometheus queda **DEFER / FUTURE ONLY** si aparecen requisitos reales de métricas continuas. OpenTelemetry/tracing queda **DEFER / FUTURE ONLY** si la complejidad causal o distribuida lo justifica. Docker lifecycle discovery queda **DEFER / FUTURE ONLY** si UAT demuestra que `service_name` y la identidad de proceso no alcanzan. Las notificaciones futuras pueden consumir las interfaces de Loki/Grafana sin ser implementadas ahora.

### Heartbeat corregido

FS-006 reconoce resultados terminales de pipeline:

```text
SUCCESS
DEGRADED
FAILED
```

Los tres demuestran que el pipeline **sí se ejecutó**. Por ello:

```text
last_attempted
→ latest terminal pipeline execution
→ SUCCESS | DEGRADED | FAILED

last_success
→ latest SUCCESS

last_degraded
→ latest DEGRADED

last_failed
→ latest FAILED
```

`PIPELINE_OVERDUE` significa:

```text
automation enabled
+
no expected terminal pipeline execution
within cadence + grace
→ overdue
```

No significa:

```text
no SUCCESS
→ overdue
```

Una ejecución `DEGRADED` es actionable evidence y **debe impedir un falso `PIPELINE_OVERDUE`**. Estados de fase como `NO_WORK`, `SKIPPED` o `UNAVAILABLE` no son failures automáticamente.

### Retención y storage

La política inicial continúa como:

```text
~30 días
→ recommended retention target

~2 GiB
→ planning / emergency storage target
```

La clase epistemológica es:

```text
HYPOTHESIS + RECOMMENDATION
```

No es un mandato rígido. El outcome obligatorio para F008 es:

```text
bounded storage
+
verified retention
+
no unlimited disk growth
```

El mecanismo físico exacto depende de F009 preflight, del host/filesystem soportado y de UAT.

---

## 2. Decisions this research enables

F008 puede evaluar FS-007 sin nueva investigación tecnológica amplia.

| Decisión | Resultado del research | Clase |
|---|---|---|
| Stack | Grafana OSS + Loki monolítico + Alloy | **RECOMMENDATION FOR F008 PROMOTION** |
| Loki deployment | single-node, filesystem/TSDB | **RECOMMENDATION FOR F008 PROMOTION** |
| Collector | Grafana Alloy | **RECOMMENDATION FOR F008 PROMOTION** |
| Structured operational stream | JSON low-noise, bounded | **RECOMMENDATION FOR F008 PROMOTION** |
| Domain audit | conservar PostgreSQL/Django Admin | **PROJECT CONSTRAINT ALREADY CLOSED** |
| Docker socket | OUT por defecto | **RECOMMENDATION FOR F008 PROMOTION** |
| Prometheus | OUT en FS-007; futuro sólo con nuevos requisitos | **RECOMMENDATION** |
| OpenTelemetry Python SDK | OUT | **RECOMMENDATION** |
| Tempo | OUT | **RECOMMENDATION** |
| Sentry self-hosted | OUT | **RECOMMENDATION** |
| Flower | OUT | **RECOMMENDATION** |
| Custom frontend | OUT | **RECOMMENDATION** |
| Normal success evidence | un evento terminal pequeño | **RECOMMENDATION** |
| Heartbeat | ausencia de actividad terminal `SUCCESS/DEGRADED/FAILED`, gated por enabled state | **RECOMMENDATION corregida** |
| Retention | ~30 días | **HYPOTHESIS + RECOMMENDATION** |
| Emergency storage target | ~2 GiB, mecanismo host-dependent | **HYPOTHESIS + RECOMMENDATION** |
| Correlation | IDs de dominio en evento, no como labels de Loki | **RECOMMENDATION** |
| Grouping | `incident_fingerprint` estable + queries, sin nueva tabla | **RECOMMENDATION** |
| Incident Packet | JSON del evento + agregados opcionales de recurrencia | **RECOMMENDATION** |
| Reconciliation | WARNING agregado por run/source | **RECOMMENDATION compatible con reglas existentes** |
| Schema drift | forma/error + metadata HTTP + extracto sanitizado y acotado | **RECOMMENDATION** |
| `UNAVAILABLE` legítimo | no incident | **PROJECT CONSTRAINT ALREADY CLOSED** |
| Future integration | interfaces de Loki/Grafana, sin integración ahora | **DEFER / FUTURE ONLY** |

---

## 3. Current Finsport constraints

### PROJECT CONSTRAINT ALREADY CLOSED

El baseline relevante post-FS-006 es:

```text
Capture
→ Prediction
→ Decision
→ canonical settlement
→ normalized research Capital
→ cancellation hygiene
→ fs006-report-v1
```

La auditoría funcional existente incluye conceptualmente:

```text
CaptureRun / CaptureWorkItem
PipelineRun
PredictionExperiment
Prediction
Decision
CapitalExperiment
```

El modelo operativo sigue siendo:

```text
local-only
demo-only
research-oriented
single maintainer/operator
```

y:

```text
real betting
→ FORBIDDEN
```

La automatización está diseñada para ser default-safe mediante:

```text
FOOTBALL_PIPELINE_ENABLED=False
```

FS-007 no debe convertir ese estado deshabilitado en una alarma.

El research original no congeló paths, clases o wiring exactos del checkout. Ese detalle continúa perteneciendo al preflight de F009.

Otros constraints preservados:

- `UNAVAILABLE != FAILED`.
- Fail-soft no puede convertirse en fail-silent.
- La auditoría funcional permanece en PostgreSQL/Admin.
- Logs no deben copiar SourceRefs, Predictions, Decisions, experimentos ni payloads completos.
- Engineering warnings de Python, pytest, lint o dependencias no forman parte del incident stream.
- No side effects financieros.
- No host-down monitoring fuera de la frontera definida por el brief.

---

## 4. Requirements distilled

| Capacidad | Must have | No debe convertirse en |
|---|---|---|
| Detección | warnings, errors, degradations y pipeline silence | generic host monitoring |
| Diagnóstico | exception, traceback cuando aporta valor, contexto seleccionado | dumps de locals/env/payloads |
| Correlación | IDs de run, task y provider cuando existan | segunda copia del dominio |
| Investigación humana | filtros, búsqueda, detalle y tiempo | frontend custom |
| Handoff técnico | JSON autosuficiente para ChatGPT/Codex | expediente manual grande |
| Retención | edad + storage bounded | histórico indefinido |
| Extensibilidad | API/query interface | notificaciones ahora |
| Heartbeat | actividad terminal `SUCCESS/DEGRADED/FAILED` | success-only health check |
| Reconciliation | conteos agregados accionables | un warning por row |
| Provider drift | evidencia de shape/parser | full response por defecto |

Los requisitos negativos son igualmente obligatorios:

```text
handled + contract fulfilled
→ no operational incident

legitimate UNAVAILABLE
→ no operational incident

same exception propagates layers
→ one operational traceback

engineering warning
→ engineering workflow, not operational storage
```

---

## 5. Evidence classification

La clasificación preserva la del informe original.

| Claim / decisión evaluada | Evidencia original | Clasificación | Fiabilidad |
|---|---|---|---|
| Finsport ya conserva auditoría funcional | Brief FS-007 | **OBSERVED** | Media-alta para intención; exact checkout queda para preflight |
| Grafana cubre búsqueda, detalle, filtros, contexto y JSON/export | Docs oficiales Grafana [R2][R3][R4] | **ESTABLISHED** | Alta |
| Loki favorece labels low-cardinality y metadata para IDs | Docs oficiales Loki [R6][R7] | **ESTABLISHED** | Alta |
| Loki permite alerting derivado de logs | Docs oficiales Grafana/Loki [R11] | **ESTABLISHED** | Alta |
| Filesystem Loki no ofrece por sí solo byte-cap de almacenamiento | Docs oficiales Loki [R8][R9] | **ESTABLISHED** | Alta |
| Alloy puede leer archivos y procesarlos | Docs oficiales Alloy [R14][R15][R16] | **ESTABLISHED** | Alta |
| Docker discovery aporta metadata y requiere acceso al daemon | Docs oficiales Alloy/Docker [R17][R23] | **ESTABLISHED** | Alta |
| Prometheus no es necesario en FS-007 | Heartbeat batch puede resolverse con actividad terminal en Loki/Grafana | **RECOMMENDATION** | Alta para este scope |
| OpenTelemetry no compensa ahora | Instrumentación extra sin requisito causal actual | **RECOMMENDATION** | Alta para FS-007 |
| Sentry self-hosted es desproporcionado | Requisitos oficiales de recursos [R30][R31] | **ESTABLISHED → RECOMMENDATION** | Alta |
| ~30 días / ~2 GiB es sizing inicial razonable | Estimación, no medición Finsport | **HYPOTHESIS + RECOMMENDATION** | Media |
| RAM de Loki/Alloy | Planning envelope | **HYPOTHESIS** | Baja-media hasta UAT |
| `DEGRADED` cuenta como actividad terminal | Semántica FS-006 dada como constraint de corrección | **PROJECT CONSTRAINT ALREADY CLOSED** | Alta para FS-007 |

---

## 6. Technology/status assessment

Este bloque conserva la foto temporal documentada en el research original; no se ha revalidado durante esta durableización.

| Fecha/estado observado en el research original | Hecho relevante | Implicación FS-007 |
|---|---|---|
| Loki 3.x | structured metadata disponible | IDs únicos no necesitan ser labels [R7] |
| 2 mar 2026 | Promtail EOL | no iniciar diseño nuevo con Promtail [R19] |
| 26 mar 2026 | Loki 3.7.0 | línea observada durante research [R13] |
| 13 may 2026 | Loki 3.7.2 | release observada en repo durante research [R12][R13] |
| ago 2026 | Grafana 13.2 self-managed | Logs Drilldown/alerting disponibles según research original |
| ago 2026 | Celery 5.6 docs | eventos de task failure/worker disponibles; no justifican Flower [R28][R29] |
| ago 2026 | OTel Python: traces/metrics stable, logs Development | no introducir SDK sólo para logging [R24][R25] |

F008/F009 deberían pinnear versiones estables probadas; este report no congela un patch concreto.

---

## 7. Technologies/options evaluated

### Grafana OSS

Cumple el requisito humano: Logs Drilldown/Explore permiten descubrir, filtrar, buscar, expandir campos, inspeccionar contexto y copiar/descargar resultados [R2][R3][R4]. Evita construir una UI propia.

### Loki

Cumple almacenamiento temporal, consultas, agregación y base para alerting. El modelo de labels obliga a distinguir dimensiones pequeñas y estables de IDs de alta cardinalidad [R6][R7]. Para el uso local, el modo monolítico evita una topología distribuida innecesaria [R12][R13].

### Grafana Alloy

Aporta una frontera de ingestión mantenida. Puede leer archivos, aplicar procesamiento y enviar a Loki [R14][R15][R16]. Puede descubrir Docker, pero esa capacidad exige acceso al daemon y no se selecciona por defecto [R17][R18][R23].

### Docker Loki logging plugin

Reduce el número de servicios, pero aumenta el acoplamiento al daemon y requiere plugin/upgrade propios. El research original concluyó que el balance operativo favorece Alloy [R20][R21]. **OUT.**

### Prometheus

Es una opción sólida para batch metrics y dispone de retención por tiempo/tamaño [R26][R27]. Sin embargo, los requisitos actuales pueden expresarse mediante eventos terminales y consultas/alertas de Loki. **OUT para FS-007; DEFER future-only si aparecen métricas continuas reales.**

### OpenTelemetry Python SDK

Es técnicamente válido, pero añade instrumentación y contrato sin resolver un requisito actual que JSON + Alloy + Loki no cubra. **OUT.** Una futura complejidad distribuida puede reabrir la decisión.

### Tempo

No existe necesidad demostrada de tracing distribuido. La correlación por `PipelineRun`, `CaptureRun`, experimentos y task/provider IDs es más directa para el producto actual. **OUT.**

### Sentry self-hosted

Su issue grouping es útil para exceptions, pero el footprint/maintenance observado en la documentación self-hosted es desproporcionado y no cubre de manera natural reconciliation, silence y otros eventos no-excepción [R30][R31]. **OUT.**

### Flower

Celery ya dispone de eventos de task failures y worker monitoring [R28]. Persistir ese stream o añadir otra UI duplicaría señales que FS-007 ya cubre mediante boundary events y overdue. **OUT.**

---

## 8. Full comparison table

| Opción | Componentes | Search/detail + traceback | Container metadata | Heartbeat | Incident Packet | Retention/cap | Footprint/burden | Future integration | Resultado |
|---|---|---|---|---|---|---|---|---|---|
| **A — Grafana + Loki + Docker Loki plugin** | 2 servicios + plugin | Excelente | buena metadata Compose | Sí | Sí | edad sí; cap externo | menos containers, más daemon coupling | Loki API | **OUT** |
| **B — Grafana + Loki + Alloy** | 3 servicios | **Excelente** | `service` estático sin privilegios; dinámico sólo si luego se autoriza Docker discovery | **Sí** | **Sí** | edad sí; cap externo | pequeño/moderado | Loki/Grafana APIs | **SELECT / RECOMMENDED** |
| **C — B + Prometheus** | 4 servicios | Igual a B | igual a B | métricas nativas | Sí | metrics time+size; logs cap externo | mayor RAM/disk/config | alta | **OUT / DEFER FUTURE** |
| **D — OTel Python + Alloy + Loki + Grafana** | 3 servicios + SDK | Excelente | buena | posible | Sí | igual a B | instrumentación extra | alta | **OUT** |
| **D ampliada — OTel + Tempo + Prometheus** | 5+ | máxima | máxima | máxima | Sí | varios stores | alta | alta | **OUT** |
| **E — Sentry self-hosted** | plataforma multi-componente | excelente para exceptions | buena vía tags/context | no cubre elegantemente todo el caso | excelente para errors | configurable | muy alto para este proyecto | API amplia | **OUT** |

---

## 9. Recommended minimal stack

```text
Grafana OSS
        ↓ queries / alert rules
Loki monolithic
        ↑
Grafana Alloy
        ↑
bounded Finsport operational JSON event sources
```

La ruta predeterminada recomendada es un stream explícito de eventos operacionales JSON, separado del chatter normal de consola. Alloy puede recolectarlo desde archivos/event sources bounded [R15][R16].

```text
operational event stream
→ Grafana / Loki

ordinary console / development chatter
→ bounded Docker local logs / engineering workflow
```

Docker ofrece un logging driver local con rotación y compresión para esa segunda categoría [R22].

FS-007 no debe convertirse en:

```text
ship every stdout/stderr line to Loki
```

---

## 10. Why every selected component is necessary

| Componente | Requirement que resuelve | Qué ocurre si se elimina |
|---|---|---|
| Grafana | vista humana, Drilldown, detalle, export y alert state | habría que usar terminal/API o construir UI |
| Loki | storage temporal consultable, LogQL, grouping y absence queries | Grafana queda sin backend de incident evidence |
| Alloy | ingestión, parsing, metadata, sanitización secundaria y desacoplamiento | app tendría que hablar con Loki o usar plugin Docker |
| PostgreSQL/Admin existentes | domain audit y drill-down | duplicar dominio en logs sería incorrecto |
| Incident Packet derivado | handoff autosuficiente a humano/agente | triage dependería de investigación manual extensa |

No existe un componente adicional con requirement suficiente para entrar en FS-007.

---

## 11. Explicitly rejected/deferred components

| Tecnología/capacidad | Estado FS-007 | Razón |
|---|---|---|
| Prometheus | **OUT / DEFER FUTURE** | no requisito actual de continuous metrics |
| OpenTelemetry Python SDK | **OUT** | instrumentación extra sin valor material actual |
| Tempo | **OUT** | tracing distribuido no demostrado |
| Sentry self-hosted | **OUT** | footprint/maintenance desproporcionados |
| Flower | **OUT** | boundary events + overdue cubren el caso |
| Promtail | **OUT** | EOL observado en el research [R19] |
| Docker Loki logging plugin | **OUT** | daemon coupling/plugin burden [R20][R21] |
| Docker socket en Alloy | **OUT BY DEFAULT / DEFER FUTURE** | privilegio amplio para metadata no esencial [R17][R23] |
| Alertmanager | **OUT** | no external notifications |
| Custom observability frontend | **OUT** | Grafana cubre UX |
| Generic APM | **OUT** | scope excesivo |
| Cloud observability SaaS | **OUT** | contradice local-only |
| External notifications | **OUT / FUTURE ONLY** | no email/webhooks/automation ahora |
| Kubernetes | **OUT OF SCOPE** | no forma parte del modelo operativo |
| Mandatory internal TLS/OAuth2/LDAP/reverse proxy | **OUT OF SCOPE** | no necesidad para localhost single-operator |
| Object storage | **OUT OF SCOPE** | no necesidad para Loki local monolítico |

---

## 12. Architecture diagram

```text
┌───────────────────────────────────────────────────────────────────┐
│ Finsport application                                              │
│                                                                   │
│ Pipeline / Celery tasks                                           │
│        │                                                          │
│        ├──────────────► PostgreSQL                                │
│        │                domain audit                              │
│        │                PipelineRun / CaptureRun / experiments     │
│        │                                                          │
│        ▼                                                          │
│ Operational boundary                                              │
│        │                                                          │
│        ▼                                                          │
│ structured low-noise event emitter                                │
│ finsport.observability.v1                                         │
└────────┬──────────────────────────────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────────────────────────────┐
│ Collection layer                                                  │
│                                                                   │
│ bounded JSONL/event sources per service/process                    │
│        │                                                          │
│        ▼                                                          │
│ Grafana Alloy                                                     │
│ parse + sanitize + stable service metadata                         │
│                                                                   │
│ ordinary console chatter ──► separately bounded local Docker logs  │
└────────┬──────────────────────────────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────────────────────────────┐
│ Loki monolithic                                                   │
│ age retention + bounded host storage                              │
└────────┬──────────────────────────────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────────────────────────────┐
│ Grafana OSS                                                       │
│ Logs Drilldown / Explore / alert state                            │
└───────┬───────────────────────────────┬───────────────────────────┘
        │                               │
        │ domain IDs                    │ Copy JSON / query aggregate
        ▼                               ▼
Django Admin                      Incident Packet
        │                               │
        ▼                               ▼
PostgreSQL                       Luis → ChatGPT/Codex ticket

Future only:
Loki/Grafana query interface
        │
        └──► later notification/integration consumer
             NOT part of FS-007
```

No Docker daemon access is required by the default design.

---

## 13. Structured-event contract

El stream debe tener un schema versionado pequeño y estable. Ejemplo conceptual:

```json
{
  "schema": "finsport.observability.v1",
  "timestamp": "2026-08-30T19:42:31.284Z",
  "event_id": "unique-event-id",
  "event_code": "PIPELINE_FAILED",
  "severity": "ERROR",
  "service_name": "celery-worker",
  "component": "capture",
  "operation": "provider_fetch",
  "outcome": "FAILED",
  "failure_kind": "PROVIDER_SCHEMA",
  "human_summary": "Capture failed because provider response was incompatible with the expected schema.",
  "correlation": {
    "pipeline_run_id": 481,
    "capture_run_id": 912,
    "celery_task_id": "..."
  },
  "provider": {
    "name": "api-football",
    "endpoint_family": "fixtures",
    "request_id": "...",
    "http_status": 200,
    "content_type": "application/json",
    "response_size_bytes": 18472
  },
  "exception": {
    "type": "ProviderSchemaError",
    "message": "Expected list at $.response",
    "stacktrace": "..."
  },
  "context": {
    "competition_id": 39,
    "expected_object": "fixture-list",
    "schema_error_path": "$.response",
    "actual_type": "object"
  },
  "incident_fingerprint": "provider_schema|api-football|fixtures|response-list",
  "git_commit": "abc123...",
  "runtime": {
    "process": "celery-worker",
    "pid": 27
  }
}
```

Esto es contrato conceptual de research, no microarquitectura ni nombres obligatorios de clases.

Para un evento terminal de pipeline, `outcome` debe admitir la semántica ya cerrada:

```text
SUCCESS
DEGRADED
FAILED
```

---

## 14. Labels vs fields/cardinality

Loki debe usar labels sólo para dimensiones pequeñas y estables [R6][R7].

| Campo | Representación recomendada |
|---|---|
| `environment=local` | label |
| `service_name` | label |
| `severity` | label |
| `event_code` | label |
| `component` / `phase` | label si vocabulario cerrado |
| `provider` | label opcional si conjunto pequeño |
| `event_id` | JSON / structured metadata |
| `incident_fingerprint` | JSON / structured metadata |
| `pipeline_run_id` | JSON / structured metadata |
| `capture_run_id` | JSON / structured metadata |
| `prediction_experiment_id` | JSON / structured metadata |
| `capital_experiment_id` | JSON / structured metadata |
| `celery_task_id` | JSON / structured metadata |
| `container_id` | metadata si se obtiene |
| `provider_request_id` | metadata |
| `git_commit` | JSON / metadata |
| traceback | body/JSON, nunca label |

No convertir IDs de cada ejecución en labels.

---

## 15. Event taxonomy

La taxonomía recomendada separa:

```text
event_code
→ qué resultado operacional ocurrió

failure_kind
→ qué clase de causa produjo el resultado
```

Vocabulario inicial:

```text
PIPELINE_COMPLETED
PIPELINE_DEGRADED
PIPELINE_FAILED
RECONCILIATION_PENDING
TASK_FAILED
RUNTIME_DEPENDENCY_FAILURE
UNEXPECTED_EXCEPTION
```

El nombre exacto del evento terminal puede ajustarse en F008/preflight siempre que preserve la semántica:

```text
terminal pipeline activity
→ SUCCESS | DEGRADED | FAILED
```

Componentes posibles, con vocabulario cerrado:

```text
capture
prediction
settlement
capital
report
scheduler
database
redis
```

Clases causales:

```text
PROVIDER_REQUEST
PROVIDER_SCHEMA
PROVIDER_RATE_LIMIT
PROVIDER_AUTH_CONFIG
DATABASE
REDIS
CELERY
CONFIGURATION
UNEXPECTED
```

Se debe evitar emitir cuatro eventos redundantes para una sola excepción causal.

---

## 16. Exception/traceback policy

Regla central:

> Log en el boundary donde el fallo adquiere significado operacional.

| Situación | Evidencia operacional |
|---|---|
| Error resuelto completamente y contrato cumplido | nada |
| Retry transitorio resuelto sin impacto | nada |
| Error manejado pero resultado incompleto | un `WARNING` |
| Contrato no cumplido | un `ERROR` |
| Exception inesperada | un `ERROR` con traceback completo sanitizado |
| Misma exception propagada por varias capas | un solo traceback |
| Error interno convertido a error de dominio | conservar causalidad en Python; registrar en boundary |
| Pipeline terminal ya representa la causa | no repetir traceback en parent |

No:

```text
provider
→ ERROR traceback

executor
→ ERROR same traceback

service
→ ERROR same traceback

task
→ ERROR same traceback
```

Los eventos nativos de Celery pueden contener exception/traceback [R28], lo que refuerza la decisión de no incorporar un monitor persistente adicional sólo para repetir esa señal.

Para unexpected exceptions:

```text
full traceback
→ yes

locals
→ no
```

El mensaje de la excepción también debe pasar sanitización defensiva.

---

## 17. Correlation strategy

No hace falta inventar un correlation ID distribuido si Finsport ya posee identidades funcionales mejores.

Prioridad:

```text
PipelineRun.id
    ↓
CaptureRun.id / PredictionExperiment.id / CapitalExperiment.id
    ↓
Celery task ID / provider request ID
```

Cuando existe `pipeline_run_id`, debe ser la principal correlation key funcional del ciclo. Si todavía no existe un `PipelineRun`, puede usarse `celery_task_id` o una identidad efímera de operación.

Ejemplo:

```text
observability:
pipeline_run_id=481
capture_run_id=912
RECONCILIATION_PENDING
match_pending=4

Django Admin:
CaptureRun #912
→ SourceRefs concretas
```

No se copian esas filas a Loki.

---

## 18. Container/service metadata strategy

### Default recomendado

```text
event source:
  /finsport-events/web/...
  /finsport-events/worker/...
  /finsport-events/beat/...

Alloy target metadata:
  service_name=web
  service_name=celery-worker
  service_name=celery-beat
```

La capa de colección aporta `service_name`. El evento puede incluir `process`, PID o hostname si ya están disponibles sin consultar el daemon.

### Deliberate omission

El default no garantiza un Docker container ID dinámico. Para un stack local single-replica es aceptable.

Alloy sí dispone de Docker discovery [R17][R18], pero requiere acceso al daemon. Docker documenta que proteger el acceso al daemon es un boundary de seguridad importante [R23].

### Future-only trigger

Si UAT demuestra que es material distinguir réplicas/restarts o lifecycle arbitrario independientemente del efecto funcional, F008 puede abrir una decisión futura sobre discovery restringido. No se monta el Docker socket por comodidad.

---

## 19. Human incident workflow

```text
Grafana
→ Logs Drilldown / Explore
→ filtrar service_name
→ filtrar severity
→ opcional component / event_code / texto
→ abrir línea
→ inspeccionar fields + traceback + metadata
→ obtener pipeline_run_id / capture_run_id
→ abrir Django Admin cuando corresponda
→ Copy log contents as JSON
```

La UX de Grafana cubre filtro, detalle, contexto y export [R2][R3][R4].

El operador debe poder contestar:

```text
¿hay problemas?
¿qué gravedad tienen?
¿cuándo empezaron?
¿siguen ocurriendo?
¿qué componente está afectado?
¿qué run está relacionado?
¿necesito abrir un ticket ahora?
```

---

## 20. Agent workflow

```text
Luis
→ copia el JSON del incidente
→ abre nuevo chat/ticket
→ pega el Incident Packet
→ agente recibe:
   qué ocurrió
   dónde
   cuándo
   exception/traceback
   run IDs
   provider/operation
   git commit cuando exista
   contexto seleccionado y seguro
```

El objetivo es evitar una primera investigación manual extensa de terminales.

---

## 21. Incident Packet contract

### Core packet

| Campo | Requerido |
|---|---|
| schema version | sí |
| event_code / incident type | sí |
| severity | sí |
| timestamp | sí |
| human_summary | sí |
| service | sí |
| component/phase | cuando aplica |
| operation | cuando aplica |
| failure_kind | para incidents |
| pipeline/capture/experiment IDs | cuando existen |
| provider + endpoint family | en provider failures |
| exception type/message | cuando existe |
| full sanitized traceback | unexpected exceptions |
| selected structured context | sí |
| git commit/version | fuertemente recomendado |
| task/process identity | cuando aplica |
| event_id | sí |
| incident_fingerprint | para recurrencia |

### Recurrence envelope derivado

Cuando el operador necesite resumir recurrencia:

```json
{
  "incident_fingerprint": "...",
  "first_seen": "...",
  "last_seen": "...",
  "occurrence_count": 12,
  "query_window": "...",
  "representative_event": {}
}
```

No requiere nueva tabla ni frontend. Grafana/Loki pueden derivar la recurrencia mediante consultas; el evento individual sigue siendo la unidad primaria.

---

## 22. Repeated-error/fingerprint strategy

El fingerprint debe construirse con dimensiones causales estables:

```text
event_code
+ component
+ failure_kind
+ provider
+ operation
+ exception type
+ normalized diagnostic key
```

Para schema drift:

```text
provider
+ endpoint family
+ schema error path
+ expected category/type
```

Excluir:

```text
pipeline_run_id
capture_run_id
timestamp
HTTP request ID
match ID
elapsed milliseconds
```

Loki conserva ocurrencias individuales. `count_over_time` puede derivar frecuencia; first/last se obtienen por ventana temporal. No se recomienda coalescing source-side en la primera versión porque introduce estado nuevo. Si un failure storm real consume el storage de forma material, esa evidencia puede promover coalescing más adelante.

---

## 23. Full operational signal table

| Failure/event | Severity | Signal | Contexto requerido | Traceback | Acción humana | Domain drill-down | Dedup/grouping |
|---|---|---|---|---|---|---|---|
| Provider request failure | `ERROR` si impide contrato; `WARNING` si sólo degrada | terminal outcome + `failure_kind=PROVIDER_REQUEST` | provider, operation, status/timeout, content type si existe, request ID, run IDs | si aporta diagnóstico; obligatorio si unexpected | revisar provider/config/network | run/capture | provider+operation+failure |
| Provider schema/parse failure | `ERROR` o `WARNING` según impacto | terminal outcome + `PROVIDER_SCHEMA` | HTTP 200 posible, media type, size, schema path, expected/actual type, bounded shape evidence | si parser falla inesperadamente | comparar contract/provider | CaptureRun/SourceRefs | provider+endpoint+schema path |
| Reconciliation pending | `WARNING` | `RECONCILIATION_PENDING` | source, counts, oldest age, run IDs | no | inspeccionar pendientes | SourceRefs/Admin | una línea agregada por source/run |
| Phase degradation | `WARNING` | `PIPELINE_DEGRADED`, `component=<phase>` | phase, reason, run IDs, affected counts | sólo causa inesperada | decidir si requiere ticket | run/experiment | phase+cause |
| Phase failure | `ERROR` | `PIPELINE_FAILED`, `component=<phase>` | phase, cause, run IDs | cuando existe exception útil | investigar | run | phase+cause |
| Pipeline terminal SUCCESS | `INFO` | terminal activity con `outcome=SUCCESS` | run ID, duration, timestamp | no | ninguna | PipelineRun opcional | no grouping requerido |
| Pipeline terminal DEGRADED | `WARNING` | terminal activity con `outcome=DEGRADED` | run ID, degraded components/reason, duration | sólo causa inesperada | inspeccionar degradación | PipelineRun | fingerprint causal cuando aplica |
| Pipeline terminal FAILED | `ERROR` | terminal activity con `outcome=FAILED` | run ID, phase/cause, duration | una vez cuando aporta | ticket/debug | PipelineRun | run + causal fingerprint |
| Pipeline overdue | `ERROR` después de grace | Grafana-managed derived alert; no app log adicional | enabled state, expected cadence, grace, latest terminal activity | no | revisar Beat/worker/Redis/pipeline | latest PipelineRun | un alert state |
| PostgreSQL unavailable | `ERROR` cuando impide operación | `RUNTIME_DEPENDENCY_FAILURE`, `failure_kind=DATABASE` | operation, service, safe DB alias, run/task | si útil; nunca DSN | revisar DB | run si existe | dependency+operation |
| Redis unavailable | `ERROR` cuando impide Celery/runtime | `RUNTIME_DEPENDENCY_FAILURE`, `failure_kind=REDIS` | operation, broker role, task/run | cuando existe exception | revisar Redis/Celery | run/task | dependency+operation |
| Celery task failure | `ERROR` | `TASK_FAILED` o terminal pipeline outcome | task name/type, task ID, worker/service, run IDs | sí si es evidencia causal | investigar task | domain run | task+exception |
| Unexpected exception | `ERROR` | `UNEXPECTED_EXCEPTION` o terminal outcome con `failure_kind=UNEXPECTED` | boundary, IDs, selected context, commit | **sí, completo y sanitizado** | ticket inmediato | donde aplique | exception+boundary |
| `NO_WORK` / `SKIPPED` phase state | no incident por sí mismo | domain/phase state | razón cuando sea útil | no | ninguna salvo inconsistencia | run | no |
| Legitimate `UNAVAILABLE` | no incident por sí mismo | analytical state | reason en dominio existente | no | ninguna | experiment/Admin | no |

**Corrección obligatoria preservada:** una ejecución terminal `DEGRADED` cuenta como actividad del pipeline y **debe impedir un falso overdue**.

---

## 24. Reconciliation treatment

Evento conceptual:

```json
{
  "event_code": "RECONCILIATION_PENDING",
  "severity": "WARNING",
  "provider": "Inkabet",
  "pipeline_run_id": 481,
  "capture_run_id": 912,
  "context": {
    "competition_pending": 0,
    "team_pending": 2,
    "match_pending": 4,
    "oldest_pending_seconds": 7312
  }
}
```

No:

```text
source_ref_rows=[...]
full provider payloads
one warning per SourceRef
```

La granularidad vive en Django Admin.

El diseño debe contar **pending operacionalmente accionable**, de modo que una futura semántica equivalente a `IGNORED_BY_MAINTAINER` pueda excluirse sin cambiar el contrato global de observabilidad.

---

## 25. `UNAVAILABLE != FAILED`

Distinguir:

| Estado | Ejemplo | Operational incident |
|---|---|---|
| `LEGITIMATELY_UNAVAILABLE` | no existe sample resuelto suficiente | **No** |
| `ACQUISITION_BROKEN` | provider esperado no entrega datos | **Sí** |
| `RUNTIME_FAILURE` | exception, DB o parse defect | **Sí** |

Regla:

```text
analytical result honestly unavailable
→ no alert

expected acquisition broken
→ incident

unexpected code failure
→ incident
```

Estados `NO_WORK` y `SKIPPED` tampoco son failures automáticamente.

---

## 26. Provider/schema-drift treatment

Caso principal:

```text
HTTP 200
≠
usable provider response
```

Evidencia recomendada:

```text
provider
endpoint_family
operation
HTTP status
content-type
response_size_bytes
provider request ID
expected root/object category
actual root/object category
validation/parser error
JSON path del fallo
top-level key names cuando sean inocuos
bounded sanitized excerpt sólo si es imprescindible
```

Ejemplo de shape evidence:

```json
{
  "root_type": "object",
  "top_level_keys": ["errors", "response", "results"],
  "schema_error_path": "$.response",
  "expected_type": "array",
  "actual_type": "object"
}
```

No guardar por defecto:

```text
raw URL con secrets
Authorization
cookies
full request
full response
full provider payload
```

---

## 27. Corrected heartbeat/pipeline-overdue strategy

Este bloque reemplaza únicamente la semántica defectuosa del heartbeat del primer informe.

### Terminal activity

FS-006 puede finalizar un pipeline como:

```text
SUCCESS
DEGRADED
FAILED
```

Los tres son **terminal pipeline activity**.

```text
last_attempted
= latest terminal pipeline execution
= max timestamp among SUCCESS | DEGRADED | FAILED

last_success
= latest SUCCESS

last_degraded
= latest DEGRADED

last_failed
= latest FAILED
```

### Overdue rule

```text
if automation_enabled is false:
    no overdue

if automation_enabled is true:
    if no terminal pipeline event
       within expected cadence + grace:
        PIPELINE_OVERDUE
```

No:

```text
if no SUCCESS:
    PIPELINE_OVERDUE
```

Una ejecución `DEGRADED` puede exigir atención, pero prueba que el scheduler/worker/pipeline alcanzó un estado terminal y por tanto reinicia el reloj de `last_attempted`.

Una ejecución `FAILED` también cuenta como intento terminal; el error ya es visible por su propio evento. Si después deja de existir actividad terminal durante la siguiente ventana esperada, entonces aparece overdue.

### Phase-state semantics

```text
NO_WORK
SKIPPED
UNAVAILABLE
```

no se convierten automáticamente en `ERROR`. El estado terminal global del pipeline continúa siendo la señal de actividad.

### Configuration consistency

Cadence y grace deben provenir de una fuente coherente con la automatización real. El research no congela números.

---

## 28. Metrics recommendation

### FS-007

```text
Prometheus
→ NOT REQUIRED
```

Se puede derivar desde Loki:

```text
last_attempted
→ latest terminal SUCCESS/DEGRADED/FAILED

last_success
→ latest SUCCESS

last_degraded
→ latest DEGRADED

last_failed
→ latest FAILED

failure/degradation counts
→ log queries by event/fingerprint

phase duration
→ terminal event fields when useful

pipeline overdue
→ absence of any terminal pipeline activity
```

Prometheus sigue siendo técnicamente válido para batch jobs [R26][R27], pero instalar una segunda base de series temporales sería redundante para los requirements actuales.

### Future trigger

Reconsiderar Prometheus sólo si aparecen requisitos de:

```text
continuous resource metrics
queue depths
latency histograms
high-frequency counters
SLOs
capacity trends
```

No añadirlo preventivamente.

---

## 29. Celery/scheduler treatment

No se selecciona Flower ni un event consumer persistente.

Principio:

```text
application operational boundary
→ task/pipeline failure evidence

scheduler/worker silence
→ absence of expected terminal pipeline activity
→ PIPELINE_OVERDUE after grace
```

Celery dispone de task/worker monitoring events [R28], pero almacenarlos de forma continua no es necesario para FS-007.

Beat no puede registrar su propia muerte. Precisamente por eso el overdue se evalúa fuera de Beat, desde Loki/Grafana.

`FOOTBALL_PIPELINE_ENABLED=False` debe suprimir la regla de overdue.

---

## 30. Container/service failure boundary

FS-007 no detecta:

```text
host apagado
operador que no inició el stack
entorno intencionalmente fuera de servicio
```

La frontera comienza cuando el entorno local fue iniciado y debería ejecutar Finsport.

Debe poder evidenciar:

```text
Django/runtime exception
PostgreSQL unavailable
Redis unavailable
Celery task failure
pipeline activity missing
service identity for emitted incident
```

Sin Docker socket, un container arbitrario que muere y no afecta el pipeline puede no producir evidencia. Esto es una limitación deliberada.

Si UAT demuestra que esa identidad/lifecycle es requisito material, se reabre como future-only discovery decision.

---

## 31. Retention/storage table — 14/30/60 days

No existen mediciones reales de Finsport para este stream. Los envelopes originales se conservan como hipótesis:

```text
Normal low-noise:
200 events/day × 3 KB/event ≈ 0.6 MB/day raw

Incident-burst planning case:
2,000 events/day × 6 KB/event ≈ 12 MB/day raw
```

Son tamaños raw pre-compresión, no predicción exacta de Loki.

| Retention | Normal raw estimate | Burst-envelope raw estimate | Evaluación | Planning/emergency target | Complejidad |
|---|---:|---:|---|---|---|
| **14 días** | ~8.4 MB | ~168 MB | poco disco, pero puede perder un incidente antes de una ventana cómoda de investigación | ~2 GiB | baja |
| **30 días** | **~18 MB** | **~360 MB** | **mejor equilibrio recomendado** | **~2 GiB** | baja |
| **60 días** | ~36 MB | ~720 MB | viable, pero duplica historia cuya corrección durable debería vivir en ticket/PR/handoff | ~2 GiB | baja-media |

Clasificación:

```text
30 days
→ HYPOTHESIS + RECOMMENDATION

~2 GiB
→ HYPOTHESIS + RECOMMENDATION
→ planning/emergency target
→ not rigid ticket mandate
```

---

## 32. Rotation/cap behavior

Dos niveles:

```text
normal cleanup
→ Loki age-based retention
→ target ~30 days

emergency safety
→ bounded underlying storage
→ planning target ~2 GiB
```

El research original estableció que filesystem retention no debe confundirse con un hard byte cap [R8][R9].

El ticket debe exigir:

```text
bounded storage
verified retention
no unlimited disk growth
```

El mecanismo exacto queda a:

```text
F009 preflight
+
supported host/filesystem
+
UAT
```

Si el host ofrece un mecanismo más simple y seguro que un hard quota exacto de 2 GiB, puede cumplir el outcome.

Al alcanzar el límite, la observabilidad debe fallar de forma **bounded** antes que consumir disco ilimitadamente. Esto puede implicar pérdida de nueva evidencia; es un trade-off aceptable frente a disk exhaustion. El límite es un safety fuse, no la rotación normal.

Los console logs ordinarios también deben estar acotados por su propio mecanismo [R22], sin mezclarlos con la retención operacional.

---

## 33. Security/redaction/privilege model

### Structured allowlist

Cada `event_code` debe admitir sólo campos seleccionados.

No:

```text
vars(...)
locals()
request.__dict__
settings
os.environ
```

Sí, cuando corresponda:

```text
provider
endpoint_family
status
content_type
response_size
competition_id
match_id
schema_error_path
sample_size
policy
```

### Central sanitization

Sanitizar defensivamente keys/patterns como:

```text
authorization
cookie
api_key
apikey
token
access_token
password
passwd
secret
database_url
dsn
```

### Alloy as second barrier

Alloy puede aplicar procesamiento antes de Loki [R16], pero la aplicación sigue siendo responsable de no crear un evento peligroso.

### URLs

No registrar raw URLs con query secrets. Preferir:

```text
provider
endpoint_family
operation
```

### Payloads

No full request/response. Un extracto excepcional debe ser:

```text
bounded
redacted
allowlisted
small
```

### Tracebacks

No locals. Exception message y diagnostic detail pasan por sanitización.

### Network exposure

El modelo requerido es local-only y single-operator:

```text
host → Grafana on localhost
Grafana → Loki on internal network
Alloy → Loki on internal network
host -X→ Loki
host -X→ Alloy
LAN -X→ observability services
```

Grafana debe usar autenticación local adecuada y no anonymous access. No se introduce como requirement:

```text
mandatory internal TLS
OAuth2
LDAP
reverse proxy
enterprise RBAC
multi-user deployment
```

### Docker privilege

```text
Docker socket in Alloy
→ OUT by default
```

---

## 34. Resource footprint

No existe un mínimo oficial específico de Loki/Alloy para este workload diminuto; una cifra exacta sería falsa precisión.

El planning envelope del informe original se conserva:

| Componente | RAM planning envelope | CPU planning envelope | Disk propio | Clasificación |
|---|---:|---:|---:|---|
| Grafana | 512–768 MiB | 0.25–1 core | decenas/cientos MB | mínimo citado por research + envelope **HYPOTHESIS** [R5] |
| Loki monolithic | 512–768 MiB | 0.25–1 core | bounded data volume, planning ~2 GiB | **HYPOTHESIS** |
| Alloy | 128–256 MiB | ~0.1–0.5 core | pequeño state/positions | **HYPOTHESIS** |
| **Total planning** | **~1.15–1.8 GiB** | **~0.6–2.5 cores no necesariamente simultáneos** | **~2–2.5 GiB bounded** | **UAT target, no vendor guarantee** |

Falsification:

> Si el stack necesita de forma sostenida alrededor de 2 GiB o más de RSS en idle/light-load para este caso, debe revisarse la configuración o la elección del stack.

Sentry self-hosted conserva la comparación original como opción desproporcionada [R30][R31].

---

## 35. Full UAT implications

FS-007 debería considerarse incompleto sin una UAT end-to-end.

| Prueba | Resultado esperado |
|---|---|
| Real healthy API-Football + Inkabet pipeline | terminal `SUCCESS`, IDs reales y casi ningún otro evento |
| Controlled recoverable degradation | terminal `DEGRADED` + WARNING accionable |
| `DEGRADED` seguido de ventana normal | **no** false `PIPELINE_OVERDUE` |
| Controlled pipeline failure | terminal `FAILED`, causa/phase visible |
| `FAILED` como ejecución esperada | cuenta para `last_attempted`; no overdue inmediato por falta de success |
| `FOOTBALL_PIPELINE_ENABLED=False` | cero overdue false positive |
| Enabled + ninguna actividad terminal dentro de cadence+grace | `PIPELINE_OVERDUE` |
| Controlled provider network/request failure | incident visible, safe context, run correlation |
| HTTP 200 + incompatible schema fixture | `PROVIDER_SCHEMA`, path/shape, no full payload |
| Unexpected exception at boundary | un solo traceback completo sanitizado |
| Phase state `NO_WORK` | no error automático |
| Phase state `SKIPPED` | no error automático |
| Legitimate `UNAVAILABLE` | no warning/error |
| Reconciliation fixtures | un warning agregado, sin row spam |
| Stop Redis in bounded test | dependency/task evidence o ausencia terminal posterior |
| Stop Celery worker | overdue tras cadence+grace |
| Stop Beat | overdue tras cadence+grace |
| Restart worker/Beat | sistema vuelve a normal sin incident storm |
| Incident search | filtro por severity/service/component |
| Incident detail | traceback/context/run IDs visibles |
| Admin correlation | run ID lleva al objeto funcional correcto |
| Incident Packet | Copy JSON aporta evidencia suficiente |
| Same exception repeated | fingerprint permite count + first/last |
| Secret canary | no aparece en evento, traceback, URL o excerpt |
| Oversized diagnostic input | evento sigue bounded |
| Retention | age cleanup demostrado |
| Storage safety | bounded storage demostrado en host soportado |
| Engineering warning | no entra al operational incident stream |
| Real betting | **NO ejecutado y NO implementado** |

Los controlled failures deben ser locales, reversibles y bounded. No deben depender de que un provider falle casualmente.

---

## 36. Future integration boundary

Loki dispone de HTTP API [R10]. El diseño puede conservar una frontera futura:

```text
Loki query API
and/or
Grafana alert state/API
        ↓
future consumer
```

Future-only possibilities:

```text
email
webhook
GitHub
Planka
agent/ChatGPT-compatible workflow
```

FS-007 no implementa:

```text
notification service
event bus
Alertmanager
GitHub integration
Planka integration
ChatGPT automation
```

No hace falta diseñar ahora la arquitectura de esas integraciones.

---

## 37. Risks/trade-offs

| Riesgo / trade-off | Evaluación | Mitigación |
|---|---|---|
| Grafana/Loki/Alloy son 3 servicios | real | cada uno resuelve un requirement distinto |
| No Docker socket | menos metadata dinámica | aceptar service/process; reabrir sólo con evidencia |
| Loki no aporta hard byte-cap por sí solo | real | storage bounded externo, mecanismo de preflight |
| Storage safety puede cortar nueva observabilidad | real | preferible a disk growth ilimitado |
| Failure storm conserva ocurrencias | real | fingerprint + bounded events; coalescing futuro si UAT/operación lo exige |
| Packet no trae automáticamente first/last/count en una sola línea | aceptable | derivar por fingerprint cuando sea necesario |
| El stack de observabilidad puede fallar | real | no añadir self-monitoring platform; operador local puede diagnosticar/reiniciar |
| Arbitrary container crash puede no detectarse si no afecta pipeline | deliberado | overdue cubre critical path; Docker lifecycle queda future-only |
| File/event source requiere rotation | real | spool bounded + Alloy positions |
| Schema excerpt puede filtrar secrets | material | shape-first + allowlist + redaction + size bound |
| Cadence y alert config pueden divergir | material | una fuente coherente y UAT |
| Success-only heartbeat produciría falsos overdue ante `DEGRADED` | **corregido** | usar cualquier terminal `SUCCESS/DEGRADED/FAILED` para `last_attempted` |

---

## 38. Falsification criteria

La recomendación debe modificarse si evidencia futura demuestra cualquiera de estos puntos:

```text
Grafana + Loki + Alloy consume recursos locales desproporcionados

Loki/Grafana no permiten recuperar con facilidad
service + severity + component + run ID

Incident Packet copiado no permite iniciar diagnóstico técnico

enabled/disabled state no puede distinguirse de forma fiable para overdue

storage bounded no puede demostrarse en el host soportado

file/event source pierde evidencia o agrega complejidad mayor
que una alternativa ya evaluada

failure storms llenan el storage en horas

traces demuestran valor diagnóstico material

requirements se expanden a:
resource metrics
queue depths
latency histograms
SLOs

Sentry-like issue grouping se vuelve requisito dominante
y el footprint se vuelve aceptable

observability comienza a duplicar payloads / SourceRefs / domain rows

legitimate UNAVAILABLE produce false positives

engineering warnings contaminan Loki

one exception produces multiple operational tracebacks

DEGRADED produce false PIPELINE_OVERDUE
```

Nueva evidencia y posible consecuencia:

| Nueva evidencia | Cambio probable futuro |
|---|---|
| continuous metrics materially required | evaluar Prometheus |
| causalidad real entre servicios | evaluar OTel traces y luego backend si procede |
| Docker lifecycle/identity material | evaluar discovery restringido |
| failure storms frecuentes | evaluar coalescing/rate summarization |
| Incident Packet manual incómodo | helper pequeño |
| stack demasiado pesado | reevaluar backend/UI más ligero |
| exception grouping domina | reevaluar una solución especializada |
| modelo operativo deja de ser local single-operator | nueva decisión de seguridad/operación fuera de FS-007 |

---

## 39. Open questions / preflight-only unknowns

No quedan preguntas tecnológicas suficientemente grandes como para impedir que F008 defina FS-007.

| Open question | Estado |
|---|---|
| Cadencia real del pipeline automático | **UNKNOWN / UNSPECIFIED** |
| Grace aceptable antes de `PIPELINE_OVERDUE` | **UNKNOWN; derivar de cadence** |
| Si `FOOTBALL_PIPELINE_ENABLED` cambia dinámicamente o exige restart | **UNKNOWN** |
| Host OS/filesystem y mecanismo disponible para storage bound | **UNKNOWN; F009 preflight** |
| Paths/logging framework/services exactos del checkout | **F009 preflight** |
| Si arbitrary container lifecycle detection es must-have | **PARTIALLY UNKNOWN; validar UAT** |
| Payload schemas/secret-bearing fields concretos de cada provider | **UNKNOWN hasta preflight/fixtures** |
| Patch versions exactos de Grafana/Loki/Alloy | **F009 preflight; pin stable tested versions** |

Ningún punto justifica instalar componentes extra “por si acaso”.

---

## 40. Q1–Q20 coverage matrix

| Pregunta | Estado | Respuesta |
|---|---|---|
| **Q1 — Stack mínimo** | **ANSWERED** | Grafana + Loki monolítico + Alloy |
| **Q2 — Component justification** | **ANSWERED** | UI / storage-query / collection-processing |
| **Q3 — Smaller alternative** | **ANSWERED** | Docker plugin reduce service count pero aumenta daemon coupling; OUT |
| **Q4 — Human workflow** | **ANSWERED** | Drilldown/Explore → filtros → detalle → Admin |
| **Q5 — Agent workflow** | **ANSWERED** | packet-ready JSON + recurrence envelope opcional |
| **Q6 — Structured logging** | **ANSWERED** | schema versionado, labels low-card, IDs metadata/JSON |
| **Q7 — Exception policy** | **ANSWERED** | un traceback en operational boundary |
| **Q8 — Correlation** | **ANSWERED** | domain run IDs + Celery/provider identity |
| **Q9 — Container metadata** | **PARTIALLY ANSWERED** | service/process sin Docker socket; dynamic container ID omitido |
| **Q10 — Heartbeat** | **ANSWERED — CORRECTED** | absence alert sobre terminal pipeline activity `SUCCESS/DEGRADED/FAILED`, gated por enabled state; `DEGRADED` impide false overdue |
| **Q11 — Metrics** | **ANSWERED** | Prometheus no requerido en FS-007 |
| **Q12 — OpenTelemetry** | **ANSWERED** | no SDK ahora |
| **Q13 — Reconciliation** | **ANSWERED** | aggregate warning por source/run |
| **Q14 — Schema drift** | **ANSWERED** | safe shape/error evidence, no full payload |
| **Q15 — Repeated errors** | **ANSWERED** | stable fingerprint + query count/first/last |
| **Q16 — Retention** | **PARTIALLY ANSWERED** | ~30d + ~2 GiB como HYPOTHESIS + RECOMMENDATION; mecanismo exacto host-dependent |
| **Q17 — Security** | **ANSWERED** | allowlisting, redaction, bounded context, localhost, no Docker socket |
| **Q18 — UAT** | **ANSWERED** | healthy + degraded + failed + controlled failures + diagnosis + secrets + corrected overdue |
| **Q19 — Future integration** | **ANSWERED** | Loki/Grafana query boundary |
| **Q20 — Explicit exclusions** | **ANSWERED** | Prometheus/OTel/Tempo/Sentry/Flower/Promtail/custom UI/etc. fuera |

---

## 41. Implementation consequences for F008 — requirements only

F008 debe promover únicamente requirements, no microarquitectura.

### Stack requirement

FS-007 debe usar:

```text
Grafana OSS
Loki monolithic
Grafana Alloy
```

con versiones estables pinneadas y probadas.

### Exposure requirement

Sólo Grafana debe ser accesible desde el host y debe quedar en localhost. Loki y Alloy permanecen en red interna. Anonymous access no debe habilitarse. No se requiere arquitectura enterprise.

### Storage requirement

Exigir:

```text
bounded storage
verified retention
no unlimited disk growth
```

Targets iniciales de research:

```text
~30 days
~2 GiB planning/emergency boundary
```

ambos como **HYPOTHESIS + RECOMMENDATION**. El mecanismo físico exacto se cierra en F009 preflight/UAT.

### Collection requirement

Debe existir un canal low-noise de eventos Finsport JSON, bounded y separable de console/development chatter. Alloy lo recolecta/procesa y lo envía a Loki. Default sin Docker socket.

### Structured-event requirement

Schema versionado con, según aplique:

```text
timestamp/event ID
event_code
severity
service
component/operation
outcome
failure_kind
human summary
correlation IDs
provider context
exception fields
selected bounded context
git/version identity
incident fingerprint
```

### Cardinality requirement

IDs de run/task/request/container no son Loki labels.

### Boundary-logging requirement

Una causa operacional no debe producir tracebacks repetidos al cruzar capas.

### Healthy terminal activity requirement

```text
SUCCESS
→ one small terminal event

DEGRADED
→ one actionable terminal event

FAILED
→ one terminal failure event
```

No success chatter phase-by-phase.

### Heartbeat requirement — corrected

Cuando automation esté enabled:

```text
last_attempted
→ latest terminal SUCCESS | DEGRADED | FAILED
```

Grafana detecta overdue sólo por ausencia de **cualquier terminal pipeline activity** durante cadence + grace.

```text
DEGRADED
→ MUST prevent false PIPELINE_OVERDUE
```

Cuando automation esté disabled, no hay overdue.

No hacer success-only heartbeat.

### Phase-state requirement

```text
NO_WORK
SKIPPED
UNAVAILABLE
```

no se convierten automáticamente en failures.

### Reconciliation requirement

```text
pending actionable reconciliation
→ one aggregate WARNING
```

sin duplicar SourceRefs.

### Unavailable requirement

`UNAVAILABLE` analítico legítimo no genera warning/error.

### Schema-drift requirement

HTTP 200 + payload incompatible debe dejar evidencia explícita de shape/parser sin guardar respuestas completas por defecto.

### Celery requirement

No Flower ni event monitor persistente. Task failures se observan en boundary; worker/scheduler silence mediante overdue.

### Incident Packet requirement

Cada failure/degradation debe ser suficientemente autocontenido para que copiar el JSON produzca el núcleo del packet. First/last/count se pueden derivar por fingerprint.

### Secret-safety requirement

Allowlist + sanitizador central + segunda barrera en collector. Nunca auth headers, cookies, env/settings completos, credenciales o payloads completos. UAT con secret canaries.

### Engineering-warning requirement

Deprecation/future/test/lint warnings quedan en ingeniería.

### Future-ticket rule

Desde FS-007, todo ticket que introduzca nuevos runtime failure modes debe declarar:

```text
failure mode
detection
severity
selected diagnostic context
correlation
traceback policy
observability path
test/UAT evidence
```

Si no introduce failure mode:

```text
Observability / audit impact: none
```

---

## 42. Final architectural decision record

```text
REFERENCE ONLY

RECOMMENDATION FOR F008 PROMOTION

SELECT
  Grafana OSS
  Loki monolithic / single-node
  Grafana Alloy
  structured low-noise Finsport operational events
  existing PostgreSQL / Django Admin for domain audit
  Incident Packet derived from structured incident evidence
  Grafana-managed pipeline-overdue rule based on terminal activity
  stable incident fingerprint
  correlation to existing domain audit

HEARTBEAT
  terminal activity = SUCCESS | DEGRADED | FAILED
  last_attempted = latest terminal activity
  last_success = latest SUCCESS
  last_degraded = latest DEGRADED
  last_failed = latest FAILED
  DEGRADED prevents false PIPELINE_OVERDUE
  overdue = enabled + no terminal activity within cadence + grace

RETENTION / STORAGE
  ~30 days = HYPOTHESIS + RECOMMENDATION
  ~2 GiB planning/emergency target = HYPOTHESIS + RECOMMENDATION
  mandatory outcome = bounded storage + verified retention + no unlimited growth

DO NOT ADD TO FS-007
  Prometheus
  OpenTelemetry Python SDK
  Tempo
  Sentry self-hosted
  Flower
  Promtail
  Docker Loki logging plugin
  Docker socket access in Alloy by default
  Alertmanager
  custom observability frontend
  generic APM
  cloud observability SaaS
  external notifications
  email
  webhooks
  GitHub / Planka / ChatGPT automation

DEFER / FUTURE ONLY
  Prometheus if continuous metrics become material
  OpenTelemetry/tracing if causal/distributed complexity becomes material
  Docker lifecycle discovery if UAT proves identity insufficient
  future integrations consuming Loki/Grafana interfaces

PROJECT CONSTRAINT ALREADY CLOSED
  local-only / demo-only / research-oriented
  single maintainer/operator
  real betting forbidden
  PostgreSQL/Admin domain audit remains canonical
  UNAVAILABLE != FAILED
  no secret exposure
  no duplication of domain audit

DESIGN PRINCIPLE
  PostgreSQL = what happened in the domain
  Loki       = what broke operationally
  Grafana    = how the operator finds it
  Incident Packet = how evidence is handed to ChatGPT/Codex
```

---

## DECISION PRESERVATION AUDIT

| Decision | Required state | Final report state | PASS/FAIL |
|---|---|---|---|
| Grafana OSS | SELECT | SELECT / recommended for F008 promotion | **PASS** |
| Loki monolithic | SELECT | SELECT / single-node | **PASS** |
| Grafana Alloy | SELECT | SELECT | **PASS** |
| structured low-noise events | SELECT | SELECT | **PASS** |
| PostgreSQL/Django Admin domain audit | SELECT/retain | retained; no duplicate audit | **PASS** |
| Incident Packet | SELECT | derived from structured evidence | **PASS** |
| Prometheus | OUT/DEFER | OUT in FS-007; future only with continuous metrics | **PASS** |
| OpenTelemetry SDK | OUT | OUT | **PASS** |
| Tempo | OUT | OUT | **PASS** |
| Sentry | OUT | OUT | **PASS** |
| Flower | OUT | OUT | **PASS** |
| Promtail | OUT | OUT | **PASS** |
| Docker Loki logging plugin | OUT | OUT | **PASS** |
| Docker socket by default | OUT | OUT by default; future trigger only | **PASS** |
| Alertmanager | OUT | OUT | **PASS** |
| custom observability frontend | OUT | OUT | **PASS** |
| generic APM | OUT | OUT | **PASS** |
| cloud observability SaaS | OUT | OUT | **PASS** |
| external notifications | FUTURE | not implemented; future consumer boundary only | **PASS** |
| heartbeat `DEGRADED` semantics | terminal activity | corrected; prevents false overdue | **PASS** |
| ~30d retention | recommendation | HYPOTHESIS + RECOMMENDATION | **PASS** |
| ~2 GiB target | planning recommendation | HYPOTHESIS + RECOMMENDATION; not rigid mandate | **PASS** |

---

## REPORT COMPLETENESS AUDIT

| Check | Result |
|---|---|
| Q1–Q20 present | **PASS** |
| comparison table present | **PASS** |
| signal table present | **PASS** |
| retention table present | **PASS** |
| architecture diagram present | **PASS** |
| Incident Packet present | **PASS** |
| heartbeat correction present | **PASS** |
| falsification present | **PASS** |
| open questions present | **PASS** |
| stable bibliography present | **PASS** |
| decision preservation audit present | **PASS** |
| research remains REFERENCE ONLY | **PASS** |
| no technology reconsideration introduced | **PASS** |
| no enterprise scope creep introduced | **PASS** |
| ephemeral citation scan = PASS | **PASS** |

Literal durableization checks performed on the generated artifact:

```text
ephemeral chat-reference identifiers
→ none

ephemeral citation markup
→ none

legacy file-reference citation markup
→ none
```

---

## 43. Stable durable bibliography

Las referencias siguientes son las fuentes del primer research, convertidas a identificadores estables. Esta correction pass no añadió investigación ni nuevas fuentes.

**[R1] Finsport — Deep Research pre-ticket para FS-007.** Proyecto Finsport. Documento interno `RESEARCH BRIEF — PRE-TICKET`. Fecha del brief: 30 de agosto de 2026. Sin URL pública.

**[R2] Logs in Explore.** Grafana Labs, documentación oficial de Grafana. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/grafana/latest/visualizations/explore/logs-integration/

**[R3] Grafana Logs Drilldown.** Grafana Labs, documentación oficial. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/grafana/latest/visualizations/simplified-exploration/logs/

**[R4] View logs — Grafana Logs Drilldown.** Grafana Labs. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/grafana-cloud/learn-and-build/visualizations/simplified-exploration/logs/view-logs/

**[R5] Install Grafana — Hardware recommendations.** Grafana Labs. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/grafana/latest/setup-grafana/installation/

**[R6] Grafana Loki documentation — Understand labels.** Grafana Labs. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/loki/latest/get-started/labels/

**[R7] What is structured metadata.** Grafana Loki documentation, Grafana Labs. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/loki/latest/get-started/labels/structured-metadata/

**[R8] Filesystem object store — Retention and deletion.** Grafana Loki documentation, Grafana Labs. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/loki/latest/operations/storage/filesystem/

**[R9] Write Ahead Log.** Grafana Loki documentation, Grafana Labs. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/loki/latest/operations/storage/wal/

**[R10] Loki HTTP API.** Grafana Labs. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/loki/latest/reference/loki-http-api/

**[R11] Loki alerting.** Grafana Labs. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/grafana/latest/datasources/loki/alerting/

**[R12] Grafana Loki repository.** Grafana Labs / GitHub. Consultado el 30 de agosto de 2026; el research original registró Loki 3.7.2 como release del 13 de mayo de 2026.
https://github.com/grafana/loki

**[R13] Grafana Loki Releases.** Grafana Labs / GitHub. Consultado el 30 de agosto de 2026.
https://github.com/grafana/loki/releases

**[R14] Grafana Alloy documentation.** Grafana Labs. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/alloy/latest/

**[R15] `loki.source.file`.** Grafana Alloy documentation. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.file/

**[R16] `loki.process`.** Grafana Alloy documentation. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/grafana-cloud/observe-and-act/send-data/alloy/reference/components/loki/loki.process/

**[R17] `discovery.docker`.** Grafana Alloy documentation. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/alloy/latest/reference/components/discovery/discovery.docker/

**[R18] `loki.source.docker`.** Grafana Alloy documentation. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.docker/

**[R19] Promtail agent — End of Life notice.** Grafana Loki documentation. EOL registrado por el research original: 2 de marzo de 2026.
https://grafana.com/docs/loki/latest/send-data/promtail/

**[R20] Docker driver client.** Grafana Loki documentation. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/loki/latest/send-data/docker-driver/

**[R21] Docker driver client configuration.** Grafana Loki documentation. Consultado el 30 de agosto de 2026.
https://grafana.com/docs/loki/latest/send-data/docker-driver/configuration/

**[R22] Local file logging driver.** Docker Inc., documentación oficial Docker Engine. Consultado el 30 de agosto de 2026.
https://docs.docker.com/engine/logging/drivers/local/

**[R23] Protect the Docker daemon socket.** Docker Inc., documentación oficial. Consultado el 30 de agosto de 2026.
https://docs.docker.com/engine/security/protect-access/

**[R24] Python — OpenTelemetry.** OpenTelemetry Project / CNCF. Estado registrado en el research original de agosto de 2026: Traces Stable, Metrics Stable, Logs Development.
https://opentelemetry.io/docs/languages/python/

**[R25] Language APIs & SDKs — OpenTelemetry.** OpenTelemetry Project / CNCF. Consultado el 30 de agosto de 2026.
https://opentelemetry.io/docs/languages/

**[R26] Instrumentation — Batch jobs.** Prometheus Project / CNCF. Consultado el 30 de agosto de 2026.
https://prometheus.io/docs/practices/instrumentation/

**[R27] Storage — Prometheus 2.55 documentation.** Prometheus Project / CNCF. Consultado el 30 de agosto de 2026.
https://prometheus.io/docs/prometheus/2.55/storage/

**[R28] Monitoring and Management Guide — Celery 5.6.** Celery Project. Consultado el 30 de agosto de 2026.
https://docs.celeryq.dev/en/stable/userguide/monitoring.html

**[R29] Backends and Brokers — Celery.** Celery Project. Línea de documentación consultada durante el research original.
https://docs.celeryq.dev/en/latest/getting-started/backends-and-brokers/

**[R30] Self-Hosted Sentry — Recommended system resource.** Sentry, documentación oficial de desarrollo/self-hosted. Consultado el 30 de agosto de 2026.
https://develop.sentry.dev/self-hosted/

**[R31] Sentry self-hosted repository.** Sentry / GitHub. Consultado el 30 de agosto de 2026.
https://github.com/getsentry/self-hosted

---

**Conclusión de research:** `REFERENCE ONLY — sufficient for F008 to decide/promote FS-007 requirements without a new broad observability investigation.`
