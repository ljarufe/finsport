# FS-010 — Final Reconciled Feedback

**Status:** FINAL / TECHNICAL ACCEPTANCE PASS / OPERATIONAL CLOSE PENDING
**Ticket:** FS-010 — Construir evidencia longitudinal comparable de CapitalPolicies con resultados reales
**Branch:** `FS-010-longitudinal-capital`
**Pull Request:** #15

## 1. Resultado

FS-010 implementa evidencia longitudinal comparable de las siete familias `CapitalPolicy` sobre un único stream prospectivo real de:

```text
DIXON_COLES
+
MODAL_ALL
```

La comparación utiliza un bankroll simulado de investigación compartido de `100u`, orden cronológico por `Decision.decision_time`, semántica de lote para timestamps iguales y el máximo prefijo cronológico completo desde el epoch congelado.

La implementación conserva estrictamente:

```text
Prediction
!=
Decision
!=
CapitalPolicy
!=
real bet
```

FS-010 no selecciona una política ganadora, no modifica las fórmulas de Prediction/Decision/Capital, no introduce un scheduler adicional y no incorpora bookmaker authentication, apuestas reales ni escrituras financieras externas.

## 2. Persistencia longitudinal

Se añadió `CapitalLongitudinalSeries` como identidad durable de la serie longitudinal primaria.

La serie persiste:

```text
evidence class
source comparator
Decision policy
frozen competition cohort
cohort hash
fixed epoch
evaluation mode
initial bankroll
reference CapitalPolicy configuration
current snapshot pointer
```

`CapitalExperiment` admite ahora ownership exclusivo mediante:

```text
source_experiment
XOR
longitudinal_series
```

La migración `0008` introduce esta estructura de forma aditiva y mantiene válidos los experimentos Capital anteriores.

La corrección de PR añade la migración aditiva `0009`, que incorpora:

```text
CapitalExperiment.semantic_identity
```

`semantic_identity` identifica el basis longitudinal comparable.

`logical_identity` continúa siendo globalmente único e identifica cada intento concreto.

Las filas Capital legacy mantienen:

```text
semantic_identity = ""
```

y conservan su comportamiento anterior.

## 3. Cohorte, epoch y basis

La serie primaria congela exactamente una vez la cohorte no vacía de `Competition.enabled`.

Una base fresca sin competiciones habilitadas devuelve:

```text
UNAVAILABLE
NO_ENABLED_COMPETITIONS
```

sin evento ERROR y sin persistir un singleton con cohorte vacía.

Cuando posteriormente existe una cohorte habilitada, la siguiente ejecución inicializa y congela esa cohorte; cambios posteriores de `Competition.enabled` no alteran su identidad.

El epoch longitudinal queda fijado en:

```text
2026-08-26T21:34:33.795715Z
```

La selección utiliza evidencia `PROSPECTIVE / DIXON_COLES / MODAL_ALL` y:

```text
decision_time ASC
same decision_time = one economic batch
```

El watermark es el final del máximo prefijo cronológico completo.

`NO_BET` permanece en el stream con exposición de capital cero.

Un Decision accionable incompleto detiene el watermark; no se salta para consumir evidencia posterior.

Los precios provienen exclusivamente del `selected_odds_observation` persistido y deben preceder al `decision_time`. Nunca se sustituye una cotización posterior o current.

## 4. Replay, identidad y currentness

El source of truth continúa siendo el basis canónico de Decisions.

Ante una modificación semántica:

```text
canonical basis changes
→ full deterministic REPLAY from epoch
```

No existe un bankroll mutable irreversible.

Un snapshot sólo puede ser reutilizado como current si:

```text
completed
+
seven required CapitalPolicy arms present
+
every arm is PRODUCED or UNAVAILABLE
+
no arm is FAILED
```

`UNAVAILABLE` es evidencia válida de dominio y permanece idempotente.

Un snapshot con cualquier brazo `FAILED` permanece persistido para auditoría, no se presenta como current y no bloquea un retry posterior sobre la misma `semantic_identity`.

Un retry sano crea otro intento con distinto `logical_identity`, conserva el intento fallido histórico y pasa a ser el snapshot vigente.

A partir de entonces una nueva ejecución sin cambio del basis retorna:

```text
NO_WORK
```

sin producir otro intento.

## 5. Concurrencia

El recompute de una misma `CapitalLongitudinalSeries` queda serializado mediante transacción PostgreSQL y:

```text
select_for_update
```

El lock cubre:

```text
basis construction
→ semantic lookup
→ attempt creation
→ current pointer transition
```

Dos recomputes concurrentes de la misma serie no pueden crear dos snapshots equivalentes ni permitir que el proceso perdedor invalide el snapshot correcto del ganador.

La regresión con dos conexiones PostgreSQL confirma convergencia a:

```text
one PRODUCED
+
one NO_WORK
+
same CapitalExperiment
+
zero false operational failures
```

## 6. Siete brazos

FS-010 reutiliza el motor FS-004 y exactamente la configuración de referencia aprobada:

```text
FLAT_UNIT
unit = 1

FIXED_FRACTION_BANKROLL
fraction = 0.05

FIXED_TARGET_PROFIT_NO_RECOVERY
target_profit = 1

LEGACY_RECOVERY
initial_stake = 1

LEGACY_CAPPED
initial_stake = 1
max_absolute_stake = 5

LEGACY_PARTIAL
target_profit = 1
alpha = 0.5

FRACTIONAL_KELLY
lambda = 0.25
```

Todos los brazos consumen el mismo manifest.

Los brazos recovery permanecen explícitamente:

```text
UNAVAILABLE_CONCURRENT_RECOVERY_STEP
```

cuando un mismo lote contiene más de un Decision accionable y no existe una secuencia recovery independiente canónica.

No se serializa artificialmente el lote y no se reduce el sample de esos brazos.

Fractional Kelly recibe el mismo stream y puede legítimamente producir exposición cero cuando el edge modelado no es positivo.

## 7. Correcciones y cancelaciones

Una corrección de outcome o provenance cambia la identidad semántica y provoca replay completo desde el epoch.

La higiene de `CANC` invalida evidencia longitudinal cuando el Decision cancelado aparece en:

```text
decision_ids
first_gap.decision_id
first_gap.batch_decision_ids
```

No convierte una cancelación en un `NO_BET` sintético.

El snapshot afectado deja de ser current y la evidencia corregida puede avanzar posteriormente cuando el basis canónico lo permite.

## 8. Pipeline y observabilidad

El recompute longitudinal se ejecuta una vez por ciclo dentro de la fase existente:

```text
CAPITAL
```

después de hygiene/settlement y junto al baseline Capital ya existente.

No se añadió un scheduler independiente.

La ruta automática es exclusivamente:

```text
REPLAY
```

`MONTE_CARLO` y `STRESS` continúan siendo capacidades manuales/on-demand separadas.

Failures inesperadas de Capital generan un único traceback causal en la capa propietaria.

El pipeline conserva siempre su evento terminal de liveness sin duplicar el traceback ya emitido por Capital.

Estados normales:

```text
NO_WORK
UNAVAILABLE
first gap
```

no generan incidentes.

## 9. Reporting

La home histórica muestra la evidencia longitudinal como un grupo separado de los CapitalExperiments independientes.

El bloque muestra de forma acotada:

```text
snapshot
input sample
manifest hash
engine
DIXON_COLES + MODAL_ALL
REPLAY
100u simulated research bankroll
frozen cohort/hash
epoch
watermark
temporal provenance
```

La lista completa de Decision IDs permanece en el manifest técnico pero no se imprime en la UI humana.

`PRODUCED`, `UNAVAILABLE` y `FAILED` se muestran explícitamente.

Un run `FAILED` con `metrics={}` no recibe métricas inventadas: los campos no disponibles se representan neutralmente.

No existe ranking ni declaración de política ganadora.

## 10. Evidencia automatizada final

Después de las correcciones de PR:

```text
FS-010 longitudinal tests
21 passed

focused affected set
104 passed

full repository gate
317 passed

coverage
86.85%

minimum required coverage
80%

makemigrations --check --dry-run
No changes detected

git diff --check
PASS
```

No se modificó la investigación `REFERENCE_ONLY`.

## 11. UAT real

La UAT real previa validó la serie longitudinal sobre PostgreSQL persistente.

Resultado:

```text
series
fs010-primary-prospective-dixon-coles-modal-all

evidence class
PROSPECTIVE

frozen cohort
12 competitions

epoch
2026-08-26T21:34:33.795715Z

current snapshot
12

engine
fs004-v1

input Decisions
6

Decision IDs
10623
10656
10689
10722
10767
10801

watermark
2026-08-29T00:01:19Z

first gap
Decision 10903

reason
MISSING_SELECTED_ODDS_OBSERVATION
```

La procedencia temporal de los seis precios seleccionados fue validada contra sus OddsObservations persistidas.

Los siete CapitalPolicy arms estuvieron presentes.

Los cuatro brazos evaluables fueron `PRODUCED`.

Los tres brazos recovery fueron honestamente `UNAVAILABLE_CONCURRENT_RECOVERY_STEP`.

Fractional Kelly produjo cero exposición para este sample.

Dos recomputes consecutivos sobre el mismo basis devolvieron `NO_WORK` y reutilizaron el mismo snapshot.

El GET de reporting devolvió HTTP 200 y los contadores antes/después fueron idénticos.

La UAT visual desktop y 390px fue aprobada.

Pass 3 no cambió metodología ni reporting; la única superficie invalidada fue persistencia/lifecycle. La delta-UAT posterior aplicó la migración `0009` sobre la DB local persistente y confirmó que el snapshot longitudinal existente continúa siendo compatible e idempotente después del cambio de identidad semántica.

## 12. PR review

El primer review de PR #15 encontró tres findings reales:

```text
FAILED snapshot was not retryable
concurrent recomputes were not serialized
empty cohort could freeze permanently
```

Los tres fueron corregidos en una única Pass 3 consolidada.

La corrección preserva evidencia fallida histórica, introduce separación semantic-attempt identity, serializa el recompute por serie y evita persistencia de cohortes vacías.

No fue necesaria Pass 4 local.

La reconciliación remota final de CI/threads se realizará sobre el commit que contiene conjuntamente estas correcciones y este feedback final.

## 13. Acceptance final

```text
A01–A30
PASS

blocking technical PENDING
0

technical acceptance
PASS
```

Los estados `UNAVAILABLE` de recovery y el gap de Decision 10903 son evidencia válida prevista por el contrato, no blockers.

## 14. Safety

FS-010 permanece:

```text
local/demo/research only
```

Durante implementación, tests y UAT:

```text
provider calls required by FS-010 = 0
bookmaker authentication = 0
real betting = 0
external financial writes = 0
```

## 15. Limitaciones factuales

El stream real disponible sigue siendo pequeño y está detenido actualmente por la falta de provenance de precio seleccionada para Decision 10903.

Por ello FS-010 genera evidencia longitudinal comparable pero no intenta decidir qué CapitalPolicy es superior.

La selección, sample sufficiency, estabilidad, tests estadísticos, PROMOTE/DROP y evaluación integrada Prediction + Decision + Capital permanecen fuera de FS-010 y corresponden al horizonte posterior de evaluación.

## 16. New Work Discovered

Ninguno.

## 17. Cierre

FS-010 queda técnicamente aceptado.

Después del último commit/push sólo quedan pasos de cierre operativo:

```text
latest GitHub CI
+
review reconciliation
→ squash merge
→ sync master
→ branch cleanup
→ tmp cleanup
→ Planka Review → Done
→ final handoff / durable source reconciliation
```
