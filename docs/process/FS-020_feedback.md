# FS-020 — Feedback final

**Ticket:** FS-020 — Global Capital Baseline
**Branch:** `fs020-global-capital-baseline`
**PR:** [#26 — feat(experiments): FS-020 Global Capital Baseline](https://github.com/ljarufe/finsport/pull/26)
**Fecha:** 2026-09-23
**Estado técnico pre-merge:** implementación y elección terminadas; UAT de publicación e integridad económica aceptado; corrección P1 del review incluida en el último delta y sujeta al gate local y al CI del nuevo HEAD.
**Estado del feedback:** final pre-merge; si aparece un cambio sustantivo después del último review, actualizar este mismo archivo.

---

## 1. Resultado y autoridad publicada

FS-020 incorporó el runner autoritativo Event-Time de Capital al Experiment Lab y cerró una elección local sobre la baseline secuencial congelada:

```text
GLOBAL_PREDICTION_V1 = MARKET_CONSENSUS / fs013-market-consensus-v2
GLOBAL_DECISION_V1   = MODAL_ALL / fs003-modal-all-v1
GLOBAL_CAPITAL_V1    = FRACTIONAL_KELLY / lambda=0.25 / max_lanes=10
promotion            = PROMOTE
disposition          = UNSTABLE
selection_policy     = FS020_MAXIMIN_LAG_RETURN_V1
```

`PROMOTE` representa la elección práctica aprobada por el responsable del producto para entregar una baseline ejecutable a la siguiente capa experimental. `UNSTABLE` conserva el resultado científico del torneo original. **No se demostró superioridad estadística ni rentabilidad futura.** No se introdujeron estados de promoción nuevos ni se reescribió el experimento original.

El ticket entrega el camino local `Prediction → Decision → Capital` completo para simulación e investigación. No activa automáticamente la técnica elegida en el runtime operacional ni habilita apuestas reales.

## 2. Implementación y contratos

Se incorporaron `capital_events.py`, `capital_runner.py`, `capital_analysis.py`, `capital_artifacts.py`, `run_capital_experiment.py`, pruebas específicas y documentación del Experiment Lab. El runner respeta las políticas CURRENT de Capital, aritmética Decimal, event-time, reserva de capital, capacidad de lanes, `PENDING_CAPACITY`, reintento anterior al kickoff, expiración, liquidaciones y actualización del estado de recuperación. Se verificaron equivalencias de ejecución y recuperación por shards bajo el contrato corregido V2R.

El comando incorpora `--publish-existing EXECUTION_ID`: busca el `run.json` histórico por su identificador, verifica los bindings y publica sin volver a ejecutar el torneo. Se impide `--run --promote`, que podía iniciar inadvertidamente otra ejecución si cambiaba el hash del código. La publicación repetida es idempotente; las autoridades incompatibles fallan cerradas. Un ajuste posterior hizo determinista el orden del informe tanto al publicar el resultado en memoria como al recargar el run almacenado.

## 3. Identidad congelada

```text
opportunities      = 1,906
competitions       = 10
calendar weeks     = 36 (6 vacías)
starting bankroll  = 100u
capital candidates = 7
settlement lags    = T+120m / T+130m / T+150m
bootstrap          = 5,000 réplicas emparejadas por cada lag × bloque 1/2/4 semanas

run_id             = aa93332a114f5e0aaaad8c59b9b60048b15c02d40e380b5deae41e8f32e08701
execution_id       = 77d6db0a93ad357f5eda92a858dc6f8d885553d43b53dd021be84ea39b43b9d7
run.json SHA-256   = a552ac781ab13d170f5cd8960167a2dbf5c2d505b2433f524a17c305342eae33
research SHA-256   = 808f5ca4339382de986a285e22fb55d4d64165969befddf36c5ab0861049e61b
```

El upstream `GLOBAL_DECISION_V1` y su selected Decision stream de 1.906 oportunidades fueron autenticados antes de la elección. No se repitieron las 5.000 réplicas para aplicar el criterio práctico de publicación ni para corregir el CLI o el informe.

## 4. Resultados económicos y decisión de producto

| Capital final, desde 100u | T+120 | T+130 | T+150 |
|---|---:|---:|---:|
| FRACTIONAL_KELLY | 179,62u | 179,97u | 179,95u |
| LEGACY_PARTIAL | 158,73u | 160,47u | 126,93u |
| LEGACY_CAPPED | 144,29u | 143,33u | 110,84u |
| LEGACY_RECOVERY | 5,07u | 5,07u | 395,84u |
| FLAT_UNIT | 63,16u | 63,16u | 67,48u |
| FIXED_TARGET_PROFIT_NO_RECOVERY | 35,94u | 35,94u | 32,03u |
| FIXED_FRACTION_BANKROLL | 1,14u | 1,02u | 1,27u |

El resultado científico congelado fue `UNSTABLE`: `FRACTIONAL_KELLY` encabezó T+120 y T+130, mientras que `LEGACY_RECOVERY` encabezó T+150. Fallaron condiciones de estabilidad por segmentos y/o superioridad simultánea en los bloques de bootstrap; la disposición científica no se alteró.

**Cambio aprobado durante ejecución:** el contrato inicial exigía superar simultáneamente todas las barreras científicas para promocionar una técnica, lo que dejaba al producto sin baseline de Capital pese a contar con datos válidos. Se adoptó una regla *práctica y posterior a la observación*: entre candidatas con trayectorias completas y `HARD_RISK=PASS` en los tres lags, seleccionar la de mayor retorno en su **peor lag**; desempatar por retorno T+150, menor peor drawdown y orden canónico. Con la evidencia congelada selecciona `FRACTIONAL_KELLY` (peor saldo 179,62u; máximo drawdown aproximado 21,71%).

Se conservan en la autoridad y el informe las métricas, pruebas de estabilidad y resultados económicos adversos. La nueva regla no debe presentarse como una prueba confirmatoria pre-registrada ni reinterpretar `UNSTABLE` como superioridad.

## 5. Incidente grave de Pass 1: fallo de proceso de tres filtros

**Severidad:** alta; se produjo un STOP real, no una diferencia cosmética de referencia.

Caso mínimo: 10 lanes ocupadas y 11.ª oportunidad `FRACTIONAL_KELLY` sin edge. El contrato congelado CURRENT/event-time aplicaba **lane-first**, por lo que la oportunidad debía esperar como `PENDING_CAPACITY`, reintentarse si se liberaba una lane antes del kickoff y caducar como `EXPIRED_CAPACITY` de lo contrario. La referencia inicial de Phase-3 calculaba el stake antes de comprobar capacidad y clasificaba la misma oportunidad como `ZERO_STAKE`.

La contradicción atravesó tres filtros antes de ser detectada: (1) investigación/Phase-3 declaró una exactitud más fuerte que la realmente probada; (2) Definition of Ready mantuvo convenciones estadísticas insuficientemente ejecutables, incluidas `se==0` y las firmas `SETTLEMENT_SIGNATURE_x`; (3) preflight autenticó identidades y hashes, pero no demostró conformidad semántica del orden lane/stake. El STOP de Pass 1 evitó aceptar como equivalente una implementación con semántica distinta.

**Resolución:** preservar la referencia original como evidencia de incidente; producir y versionar V2R con lane-first; incorporar fixtures de capacidad saturada, liberación anterior al kickoff con recomputación y coincidencia temporal settlement/release/state update/retry; repetir la exactitud técnica afectada, no reabrir fases ajenas. Se aceptó la reconciliación V2R antes de proseguir con la elección económica. Ninguna decisión posterior debe ocultar este fallo de proceso en el handoff.

## 6. Auditoría causal de LEGACY_RECOVERY

El extremo 5,07u a T+120/T+130 frente a 395,84u a T+150 motivó una auditoría de solo lectura sobre los ledgers existentes. La primera divergencia de colocaciones ocurrió después de dos apuestas compartidas: la liquidación de `17294` libera la única lane a tiempo para colocar `23399` en T+120 y T+130, pero en T+150 se liquida tras su kickoff y `23399` expira. La divergencia altera oportunidades y la secuencia posterior de pérdidas y stakes de recuperación; se reproduce también la oportunidad `23401`, tomada y perdida en los lags cortos, pero expirada con T+150.

La auditoría reprodujo los tres hashes de ledger, mantuvo `peak_lanes=1` y no encontró defecto material en la primera divergencia. **No prueba robustez económica** de `LEGACY_RECOVERY`; su extrema dependencia del orden de liquidación queda registrada para FS-021 y estudios futuros. No se corrigió el algoritmo ni se repitió el bootstrap por este hallazgo.

## 7. Review de PR #26: investigación modificada por un hook

El review automático del commit original `36637a306b` produjo un hallazgo **P1**: la investigación versionada en Git tenía SHA-256 `589e53d1…`, distinto del `808f5ca4…` vinculado por `run.json` y `GLOBAL_CAPITAL_V1`. En esas condiciones, un checkout limpio rechazaba `--publish-existing` con `INPUT_INTEGRITY_FAIL:FROZEN_BINDING_CHANGED`, aunque la copia local usada en las UAT previas coincidiera con el run.

**Causa:** el hook `trailing-whitespace` eliminó ocho secuencias de doble espacio al final de líneas Markdown durante la preparación del commit. Los bytes del archivo vinculado por SHA cambiaron sin que cambiaran los bindings del run; el CI inicial pasó, pero no detectó esa discrepancia.

**Corrección dirigida para el último commit:** restaurar los bytes exactos de la investigación con SHA-256 `808f5ca4339382de986a285e22fb55d4d64165969befddf36c5ab0861049e61b`; añadir una exclusión **sólo para ese documento** al hook `trailing-whitespace`. No modificar autoridad, run, investigación semántica, código económico ni hashes de la elección. El commit final incorpora esta corrección y este feedback; **el CI del nuevo HEAD debe quedar verde antes del merge**. La validación requerida es el hash de archivo local e índice Git, los hooks aplicables, `--publish-existing` en dev y ausencia de mutación posterior al commit.

Este hallazgo añade una regla de proceso: un archivo congelado por hash debe verificarse **después de ejecutar todos los formatters/hooks y sobre los bytes efectivamente incorporados al commit**. El éxito del CI general no sustituye esa comprobación de integridad cruzada.

## 8. Pruebas y UAT

- Pruebas específicas FS-020, runner, paridad, idempotencia, conflicto y publicación de run existente: PASS. Antes de los parches correctivos finales se registraron 56 tests FS-020 y 862 tests generales, cobertura 84,97%; el último `make check` tras la corrección del orden del informe fue reportado verde. No se atribuye ese recuento inicial a un commit posterior sin evidencia nueva.
- Auditoría independiente del torneo y UAT-4: PASS; 181 shards conservados, nueve matrices de bootstrap y tres ledgers; identidad y resultados económicos congelados.
- UAT-5: publicación real repetida con `--publish-existing` devolvió el mismo `execution_id`, `run_id`, `PROMOTE`, `FRACTIONAL_KELLY`, `UNSTABLE` y `PUBLISHED_EXISTING`; no ejecutó shards nuevos.
- Gate obligatorio del último commit: verificar el SHA del documento tanto en el workspace como en el índice Git después de ejecutar los hooks, comprobar la publicación `--publish-existing` desde `finsport-dev` y verificar CI/review del nuevo HEAD antes del merge. El resultado de CI del commit original no certifica la corrección P1.

No se introdujeron proveedores nuevos ni llamadas durante la elección, migrations, Beat adicional, cambios de configuración operacional, escrituras a la DB operacional, apuestas ni activación automática del ganador.

## 9. Evidencia durable y retención

**Repositorio:**

```text
docs/research/FS-020_global_capital_methodology_research.md
docs/research/FS-020_e2_4_v2r_reconciliation.json
docs/research/FS-020_global_capital_v1.json
docs/research/FS-020_global_capital_report.md
docs/research/FS-020_capital_baseline_evidence/aa93332a114f5e0a/run.json
docs/process/FS-020_feedback.md
```

**Fuera de Git, en el host de investigación:**

```text
/home/ljarufe/Documents/finsport/FS-020_e2_4_v2r/
/home/ljarufe/Documents/finsport/FS-020_uat4/
  77d6db0a93ad357f5eda92a858dc6f8d885553d43b53dd021be84ea39b43b9d7/
```

El audit pre-PR de retención pasó con 12/12 archivos V2R, 198/198 de UAT-4 y 9/9 de cierre; verificó spec y run originales, los ledgers, matrices, upstream FS-019 y `RETENTION_INDEX.tsv` (SHA-256 `b632fe0253450971a60cabfc20c2ed6e35a468d865bf39233e6f00d1b001bd10`). Estos archivos no deben borrarse al limpiar `tmp/` ni al destruir `finsport-dev`. Conservarlos hasta que FS-021 cierre su consumo y exista autorización explícita de eliminación.

FS-018 `FS018_E1_PHASE3` permanece `PRESERVE_ACTIVE` para el torneo acumulativo; **la auditoría de FS-020 no verificó su ruta física**, por lo que FS-021 deberá hacerlo antes de consumirla.

## 10. Límites científicos y handoff hacia FS-021

La elección Capital-local empleó únicamente `MARKET_CONSENSUS + MODAL_ALL`. FS-021 evaluará de forma independiente las combinaciones acumulativas elegibles Prediction × Decision × Capital (matriz prevista de 33 × 7 = 231). **No debe inferirse que unir las tres autoridades locales maximiza la estrategia integrada.**

Conservar como resultados diagnósticos los rendimientos negativos de `FLAT_UNIT` y ambas técnicas fijas, la sensibilidad de `LEGACY_RECOVERY` y la inestabilidad de Kelly en la segunda mitad y algunas exclusiones de ligas. No descartar silenciosamente familias del torneo acumulativo sólo por su desempeño condicionado a la baseline local; cualquier reducción debe tener regla y justificación explícitas.

La equivalencia de ciertos hashes RNG históricos de codificación no especificada sigue sin demostrarse. Los manifiestos, scores y replay propios del paquete aceptado sí están verificados. La evaluación es histórica con liquidaciones sintéticas; no constituye promesa de rentabilidad prospectiva.

## 11. Recomendaciones durables de proceso y fuentes

1. **F010 / F008 — Exactness ejecutable:** la investigación y el Definition of Ready deben incluir conformance fixtures capaces de detectar contradicciones entre el runner de referencia y CURRENT, además de convenciones matemáticas exactas para `se==0` y firmas de liquidación. Un hash correcto no certifica semántica correcta.
2. **F009 — Integridad tras packaging:** verificar SHA-256 de research/spec/run/autoridad contra el contenido del **índice Git** después de formatters y hooks, no sólo contra el workspace o el archivo anterior al commit. Un artefacto científicamente congelado debe disponer de una excepción estrecha cuando un formatter destruya los bytes autorizados.
3. **F006 / F008 / F010 — Continuidad de baselines:** distinguir la prueba confirmatoria de superioridad de una regla práctica y reproducible para elegir una baseline utilizable. Cuando ambas discrepen, preservar el diagnóstico científico completo y documentar explícitamente la decisión posterior a los resultados; no alterar el histórico congelado.
4. **F006 / F010 — Capa acumulativa:** conservar la autoridad Capital-local para diagnóstico y ejecutar en FS-021 el torneo integrado sobre la matriz elegible; considerar los resultados negativos como evidencia para diseños futuros, no como un filtro ad hoc que silenciosamente sesgue el torneo.
5. **F009 — Retención cross-ticket:** artefactos pequeños e identidades en `docs/research/`; ledgers, shards, score matrices y conformance bundles fuera de Git con SHA-256, índice de retención, consumidor y condición de borrado. Verificar `PRESERVE_ACTIVE` de FS-018 antes de cualquier limpieza que pudiera afectarlo.

## 12. Cierre pre-merge

```text
GLOBAL_CAPITAL_V1             = FRACTIONAL_KELLY / lambda=0.25 / max_lanes=10
publication                  = PROMOTE
scientific disposition       = UNSTABLE
frozen economic run          = PRESERVED
V2R reconciliation           = ACCEPTED
UAT-4 and UAT-5              = PASS
retention FS-020             = PASS
PR #26 P1 research hash      = ADDRESSED BY FINAL CORRECTION; VERIFY FINAL COMMIT + CI
operational routing          = UNCHANGED
real bets / provider calls   = 0
```

Después del último commit de corrección y feedback: esperar CI/review sobre el nuevo HEAD; si ambos están verdes y no aparecen nuevos findings, merge manual y continuar F009 con `make dev-destroy`, sincronización de `master`, deploy local, aceptación operacional, handoff al chat principal y Planka Done. **Este feedback no sustituye el handoff posterior al deploy.**
