# FS-013 — Feedback de implementación

## Resultado

`MARKET_CONSENSUS` queda operativo en el pipeline prospectivo normal con:

```text
football.pipeline.wake
→ FOOTBALL_MARKET_CONSENSUS_WINDOWS (T-6h/T-60m/T-30m)
→ un CapturePlanner/CaptureExecutor y límites bounded
→ OddsObservation real y durable
├─ MARKET_CONSENSUS v2 por lote completado
└─ MODERNIZED_R45 + Decision consumers reutilizan evidencia DB
```

No existe comando, calibración, perfil aprendido ni activación específica de Market Consensus. La habilitación del pipeline continúa siendo la configuración operativa genérica existente de Finsport.

## Arquitectura implementada

- `CanonicalBookmaker` y `CanonicalOddsMarket` representan las unidades estadísticas.
- `BookmakerCanonicalRef` y `OddsMarketCanonicalRef` preservan la fila raw, estado de reconciliación, versión, razón y contexto.
- `fs013-governed-v1` resuelve por `source + external_id`; el nombre sólo es diagnóstico. Los IDs desconocidos permanecen `PENDING` y no votan.
- La migración `0012_fs013_market_consensus_identity` crea el esquema y reconcilia los bookmakers API-Football presentes en el checkout, Inkabet y los mercados API-Football Match Winner / Inkabet MW3W hacia `1x2`.
- La selección usa como máximo una observación válida por bookmaker canónico. Prefiere la observación real válida más reciente y usa source/external IDs/PK como desempate estable.
- `CaptureConfig.windows` tiene una sola autoridad: `FOOTBALL_MARKET_CONSENSUS_WINDOWS`. La configuración histórica local `FOOTBALL_CAPTURE_WINDOWS` ya no se lee y no puede activar `early/middle`.
- El planner produce únicamente tres identidades de adquisición actuales por fixture: `market-t6h`, `market-t60m`, `market-t30m`. No existen roles, colecciones paralelas ni namespace dual.
- La predicción MC prospectiva nace sólo de trabajo actual `SUCCESS`, `SUCCESS_EMPTY` o `LATE_CAPTURE` durable. Su intervalo de evidencia va desde `CaptureWorkItem.executed_at` hasta el cutoff estricto `CaptureRun.completed_at`.
- R45 se evalúa desde la misma ventana actual debida y reutiliza `OddsObservation` persistido; no posee un schedule ni una adquisición propios. El candidato MC contiene exclusivamente `MARKET_CONSENSUS`; Dixon-Coles, Poisson y Elo continúan con sus candidatos deportivos independientes.
- El `PredictionExperiment.logical_identity` y el hash `Prediction.evidence_identity` hacen idempotente el lote. Una ventana posterior crea evidencia nueva sin modificar la anterior.
- Una respuesta real posterior con precios idénticos sigue insertando `OddsObservation`; `OddsSnapshot` permanece como proyección current separada.

## Versiones

- Canonicalización: `fs013-governed-v1`.
- Modelo: `fs013-market-consensus-v2`.
- Versión histórica preservada: `fs003-market-consensus-v1`.
- Único schedule de adquisición: exactamente `market-t6h`, `market-t60m`, `market-t30m`.

## Evidencia automatizada

- Focused Pass 4: 61 pruebas relevantes PASS. Prueban bootstrap automático con una adquisición falsa, transición a headers autoritativos y reserva, fallo headerless consumido durablemente sin repetición, y comportamiento manual conservador.
- Focused Pass 3: 66 pruebas relevantes PASS; incluye exactamente tres adquisiciones con proveedor falso para un fixture, reutilización MC+R45 sin llamadas extra y `makemigrations --check --dry-run` sin cambios.
- Focused Pass 2: 69 pruebas relevantes PASS y `makemigrations --check --dry-run` sin cambios.
- `make check` Pass 2 se ejecutó una sola vez: Black, Ruff, Django check, migration check, dependency check, security audit y cobertura 87.10% PASS; la suite terminó 431 PASS / 7 FAIL por pruebas FS-011/FS-012 dependientes de la hora UTC/local (hallazgo documentado abajo). El gate general, por tanto, no se declara verde.
- `python manage.py check`: PASS.
- `python -m pip check`: PASS.
- `pip-audit --local`: sin vulnerabilidades conocidas.
- `git diff --check`: PASS.
- Prueba de migración disposable: 0011 → creación de raw Bet365/Match Winner → 0012 → refs `RESOLVED` a `bet365`/`1x2`, PASS.
- Configuración y planner probados sin provider call: tres ventanas exactas, ningún trabajo `early/middle`, un único Beat owner `football.pipeline.wake` y ningún incremento de adquisiciones al agregar consumidores MC+R45.

## UAT manual

El primer UAT automático real ejecutado por execution chat alcanzó correctamente Beat → `football.pipeline.wake` → `run_pipeline(trigger=SCHEDULER)` y creó `CaptureWorkItem id=3578` para `match_id=53550`, fixture `1552142`, ventana `market-t60m`. Terminó `QUOTA_RESERVE`, con cero intentos/páginas/retries/observaciones, porque el pipeline no habilitaba el bootstrap bounded al no existir todavía un header de cuota del epoch UTC.

Pass 4 corrige exclusivamente ese límite: el pipeline pasa `allow_bootstrap=True` a `run_capture` cuando el trigger es `SCHEDULER`. El allowance existente continúa limitado por `FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS`; los intentos headerless quedan contabilizados durablemente y los headers recibidos cambian la autoridad a `HEADER_CURRENT_UTC_EPOCH`, tras lo cual vuelve a aplicar la reserva normal. El camino manual sigue conservador por defecto.

Codex no repitió el UAT real. A15 y A16 quedan `PENDING_UAT_RETEST` para que execution chat verifique la corrección en runtime real. El hallazgo original se conserva en `tmp/FS-013_uat_quota_reserve_finding.txt`.

La migración no fue aplicada a la PostgreSQL persistente del maintainer. Su comportamiento se validó exclusivamente en la DB disposable de pytest.

## Seguridad financiera

- Provider HTTP calls reales: 0.
- Autenticación a bookmaker: 0.
- Escrituras a bookmaker/apuestas/movimiento de dinero: 0.
- Ejecución de `run_betting_cycle`, Selenium histórico o `make_bets`: 0.
- Commits, push, PR y Planka: 0.

## Hallazgos y recomendaciones

### Pruebas históricas sensibles al cambio de día local

**Evidencia:** el único `make check` de Pass 2 se ejecutó a las 15:04 UTC / 10:04 America/Lima. Seis pruebas en `test_fs011_dixon_coles.py` construyen un target con `timezone.now() + 12h` pero llaman `predict_competition_day()` con `target.kickoff.date()` en UTC; a esa hora, ese día UTC no coincide con el día local usado por producción. La prueba multitarget FS-012 añade dos horas al segundo target y cruza el mismo límite. Esos archivos no tienen diff FS-013.

**Impacto:** siete fallos no relacionados impiden declarar verde el gate general aunque los 69 tests focalizados y todos los subgates no-pytest pasen.

**Recomendación:** estabilizar esas pruebas en su ticket propietario usando un instante fijo y `local_day(target.kickoff)`. No se absorbió esa corrección en FS-013.

### Registro gobernado extensible

**Evidencia:** los raw IDs soportados actuales quedan resueltos por el registro `fs013-governed-v1`; un ID futuro desconocido queda `PENDING` con `UNMAPPED_SOURCE_EXTERNAL_ID`.

**Impacto:** un bookmaker nuevo del proveedor no participa silenciosamente hasta ser revisado; no puede duplicar votos por heurística de nombre.

**Recomendación:** ampliar el registro mediante cambio versionado y review cuando aparezcan IDs nuevos. No es trabajo pendiente para los refs actualmente soportados.

## Estado de aceptación

A01–A18: 16 PASS, 2 PENDING_UAT_RETEST, 0 otros. A15 y A16 requieren el retest real del ciclo automático/proveedor. El detalle y la evidencia están en `tmp/FS-013_acceptance_ledger.md`.
