## Final PR review and closure

El review del PR #18 detectó dos findings P1 válidos sobre la frontera temporal de `MARKET_CONSENSUS v2`.

### P1 — policy prices must respect the capture batch lower bound

La Prediction de Market Consensus ya aplicaba correctamente el `not_before` del lote de captura, pero las decisiones derivadas mediante `persist_standard_policies()` consultaban `best_prices_as_of(match, cutoff)` sin ese mismo límite inferior.

Eso permitía que una Prediction T-60 usara exclusivamente evidencia T-60 mientras una decisión modal/selective asociada seleccionara un precio proveniente de una observación anterior, por ejemplo T-6h.

La corrección:

```text
best_prices_as_of(...)
→ acepta not_before

persist_standard_policies(...)
→ acepta price_not_before

MARKET_CONSENSUS v2
→ propaga el not_before del mismo capture batch hasta la selección de precios
```

Resultado:

```text
Prediction evidence window
==
Decision price evidence window
```

Las decisiones derivadas ya no pueden mezclar precios de ventanas anteriores.

### P1 — prospective MARKET_CONSENSUS v2 requires capture evidence

El camino genérico soportado por:

```text
predict_football_day
→ predict_day()
→ predict_competition_day()
```

seguía solicitando todos los modelos por defecto.

Después de FS-013 eso permitía producir `fs013-market-consensus-v2` sin:

```text
market_evidence_identity
market_evidence_not_before_by_match
```

y por tanto fuera de la semántica definida para Market Consensus v2:

```text
completed real capture batch
→ versioned prospective Market Consensus Prediction
```

La corrección mantiene el comportamiento genérico de los modelos deportivos, pero excluye Market Consensus cuando no existe evidencia de capture batch.

Además, si un caller solicita explícitamente `MARKET_CONSENSUS`, ahora debe aportar:

```text
non-empty market_evidence_identity
+
one market evidence lower bound per target Match
```

El pipeline automático FS-013 ya proporciona ambos valores, por lo que su ruta operativa no cambia.

### Regression adjustment

Un test heredado de pipeline esperaba todavía que Market Consensus fuese solicitado por el camino genérico y apareciera como `UNAVAILABLE`.

Esa expectativa quedó obsoleta por la corrección anterior.

El test fue actualizado para verificar la nueva semántica:

```text
generic prospective call without capture evidence
→ MARKET_CONSENSUS not requested
→ no MARKET_CONSENSUS Prediction
→ no synthetic MARKET_CONSENSUS unavailable entry
```

### Final validation

La corrección de PR review se valida mediante la suite focalizada:

```text
football/tests/test_fs013_market_consensus.py
football/tests/test_prediction_market.py
football/tests/test_prediction_evaluation_commands.py
football/tests/test_pipeline.py
```

y:

```text
git diff --check
```

No se repite `make check` porque no existe un nuevo delta transversal que justifique repetir el full gate y ya existe un finding heredado conocido de FS-011/FS-012 sensible al rollover UTC/America-Lima.

No se repite UAT real ni se realizan nuevas llamadas a providers: los cambios de review endurecen las fronteras de evidencia ya demostradas durante el UAT automático y quedan cubiertos por regresiones locales.

### Real automatic UAT retained as acceptance evidence

El UAT automático real de FS-013 queda como evidencia de cierre:

```text
match_id=53551
Moreirense vs Benfica

T-60
→ SCHEDULER
→ 1 attempt
→ 1 page
→ 0 retries
→ 14 OddsObservation

T-30
→ SCHEDULER
→ 1 attempt
→ 1 page
→ 0 retries
→ 14 OddsObservation
```

Ambas ventanas produjeron Predictions reales:

```text
model_version
→ fs013-market-consensus-v2

canonical bookmakers
→ 14

de-vig
→ multiplicative

consensus
→ equal_weight_arithmetic_mean
```

La recuperación T-30 devolvió los mismos precios observados en T-60:

```text
14 new OddsObservation
snapshots_changed=0
identical_response=True
```

confirmando que una recuperación real posterior e idéntica continúa siendo evidencia auditable sin fabricar movimiento del mercado.

La similitud T-60/T-30 se conserva como evidencia prospectiva y no provoca un cambio de parámetros después de un solo fixture.

Configuración inicial retenida:

```text
T-6h
T-60m
T-30m
```

Una auditoría futura podrá determinar si conviene eliminar una de las dos ventanas near-kickoff cuando exista evidencia suficiente.

### Non-blocking operational findings

Durante el UAT real, Inkabet agotó su timeout de transporte y dejó los ciclos `PARTIAL` / `DEGRADED`.

Esto no impidió:

```text
API-Football acquisition
→ OddsObservation persistence
→ canonical reconciliation
→ MARKET_CONSENSUS v2 Prediction
```

Por tanto se conserva como finding operacional secundario y no como blocker de FS-013.

Los siete fallos previamente observados en el full `make check`, relacionados con tests heredados FS-011/FS-012 sensibles al rollover temporal, permanecen fuera del scope de FS-013.

### Process learnings

No se modificaron artefactos `tmp/**` para fabricar un estado final de aceptación.

Los artefactos temporales conservan el estado histórico que tenían cuando fueron generados; la evidencia posterior de UAT y PR review se registra en este feedback durable.

También queda registrado un problema repetido en la aplicación de pequeñas correcciones locales:

```text
git apply
```

no debe utilizarse con hunks abreviados del tipo:

```text
@@
```

generados manualmente desde chat.

`git apply` requiere unified diffs reales con rangos completos:

```text
@@ -x,y +x,y @@
```

Para modificaciones pequeñas entregadas desde chat se debe preferir:

```text
exact-context replacement
+
assert expected occurrence count
+
abort before writing on mismatch
```

No instalar `apply_patch` ni herramientas adicionales para resolver este caso.

### Final acceptance

Con el UAT automático real y las dos correcciones P1 del PR review:

```text
A01–A18
→ PASS

MARKET_CONSENSUS operational
→ YES

normal automatic pipeline
→ YES

completed capture batch required for v2
→ YES

Prediction/Decision temporal batch consistency
→ YES

manual activation required
→ NO

continuous polling
→ NO

future empirical calibration
→ DEFERRED / NOT BLOCKING

real betting
→ FORBIDDEN
```

FS-013 queda listo para merge una vez que la suite focalizada final y `git diff --check` estén verdes y el PR review no presente nuevos findings materiales.
