# FS-022 — Feedback final

**Proyecto:** Finsport
**Ticket:** FS-022
**Estado:** FINAL / ACCEPTED
**Modo financiero:** simulación exclusiva; `real_betting=false`

---

## 1. Resultado técnico

FS-022 consolidó un único camino prospectivo simulado y gobernado para la estrategia económica global #209:

```text
Match
→ Capture T-30
→ MARKET_CONSENSUS / fs013-market-consensus-v2
→ SELECTIVE_CONFIDENCE(0.45)
→ FRACTIONAL_KELLY(lambda=0.25)
→ banca compartida 100u / max 10 lanes
→ posición simulada
→ settlement
→ reporting de producto
```

Las siete configuraciones Capital anteriores quedaron preservadas como evidencia histórica/auditable y retiradas de nuevas entradas automáticas. Experiment Lab permanece como superficie manual de investigación; el runtime automático dejó de reconstruir historia experimental completa en cada wake.

La estrategia vigente queda ligada a:

```text
Prediction  → MARKET_CONSENSUS
Decision    → SELECTIVE_CONFIDENCE(0.45)
Capital     → FRACTIONAL_KELLY(lambda=0.25)
Bankroll    → 100u compartidas
Max lanes   → 10
Real betting→ false
```

---

## 2. Capture, evaluación y continuidad

La evaluación de #209 consume únicamente evidencia T-30 prospectiva admisible de API-Football, posterior al cutover y dentro de ventana temporal válida. La colocación vuelve a verificar tiempo efectivo y nunca puede ocurrir después del kickoff.

Se conservaron los contratos existentes de captura y continuidad:

- T-6h / T-60m / T-30m;
- T-30 como precio económico de ejecución;
- `PENDING_CAPACITY` y retry mientras el partido siga siendo colocable;
- OPEN result first hint T+130;
- retry normal +30m;
- tratamiento SUSP/PST;
- same-wake settlement → liberación de capital → nueva colocación cuando corresponde;
- quota accounting y reservas dinámicas;
- ausencia de cualquier side effect financiero real.

### Corrección final de review — skips T-30 reintentables

La revisión final detectó una frontera incorrecta entre Capture y la evaluación global: un T-30 terminado sin intento físico como `QUOTA_RESERVE`, `INSUFFICIENT_WORST_CASE_BUDGET` o `PROVIDER_BACKOFF` podía ser evaluado prematuramente como ausencia terminal de precio. Capture todavía permitía reintentar esa identidad lógica, pero Capital ya podía haber clasificado el Match e impedir que una captura válida posterior produjera Prediction/Decision/posición.

La corrección separó explícitamente:

```text
skip sin intento físico
→ sigue siendo reintentable
→ no crea clasificación terminal de #209
```

frente a:

```text
intento físico realmente consumido
→ mantiene la semántica fail-closed existente
→ no habilita retry automático silencioso
```

Se añadieron regresiones que comprueban que un skip sin intento no crea `CapitalEvaluation`, `CapitalExecutionState`, `PredictionExperiment` ni posición y que una captura posterior válida de la misma identidad puede recorrer normalmente Prediction → Decision → Capital.

---

## 3. Capital y comportamiento económico

FS-022 preservó la separación entre señal deportiva y decisión económica. `SELECTIVE_CONFIDENCE(0.45)` puede seleccionar HOME/AWAY, pero Capital sólo abre posición cuando Kelly encuentra edge económicamente admisible.

La UAT histórica local confirmó:

```text
42 partidos observados
25 decisiones HOME/AWAY
17 NO_BET
25 señales con EV <= 0
0 posiciones
```

El cero de apuestas en esa jornada fue correcto: las 25 señales accionables tenían edge económico no positivo.

La UAT sintética complementaria, ejecutada sobre DB aislada y con precios T-30 explícitamente marcados como sintéticos, obligó al pipeline real a recorrer el ciclo económico completo:

```text
42 predicciones MARKET_CONSENSUS
42 decisiones SELECTIVE_CONFIDENCE
4 posiciones Capital
2 SETTLED_WIN
2 SETTLED_LOSS
exposición OPEN observada
0 OPEN al finalizar
reserved_exposure final = 0
```

Conciliación final del escenario:

```text
bankroll inicial = 100u
P&L realizado = -2.61680378u
equity final = 97.38319622u
available_cash = 97.38319622u
reserved_exposure = 0u
```

No hubo posiciones duplicadas por Match y todas las colocaciones ocurrieron antes del kickoff.

---

## 4. Resultados y settlement

La UAT reveló que polls normales de resultados todavía no terminales podían aparecer como ciclos `DEGRADED` sin error real.

Se corrigió la semántica para distinguir:

```text
resultado todavía no terminal
→ OPEN_RESULT_NOT_DUE
→ estado esperado
→ deuda durable
→ retry posterior
```

frente a:

```text
provider / parse / invariant error real
→ DEGRADED o FAILED
→ razón durable
```

La deuda OPEN se conserva correctamente hasta settlement y la reserva se libera al liquidar.

---

## 5. Frontend y reporting de producto

El frontend científico anterior dejó de ser la superficie continua del producto. La interfaz quedó concentrada en:

```text
/                         → Inicio
/partidos/                 → Partidos
/partidos/<id>/detalle/    → detalle bajo demanda
/admin/                    → Django Admin
```

La antigua `/daily/` dejó de ser una ruta de producto.

Se retiraron del camino productivo `historical_view`, `daily_view`, `historical.html`, `daily.html`, los selectores científicos de la portada anterior, `_capital_v2_rows` y `football/reporting/presentation.py` como dependencia de la UI antigua. Los tests propios de ese reporting fueron sustituidos por pruebas del nuevo reporting operacional. Las traducciones aún necesarias por otros contratos se trasladaron a una ubicación neutral bajo Prediction.

Experiment Lab, Admin y Grafana permanecen como superficies independientes para investigación, auditoría y operación.

### Inicio

Inicio muestra exclusivamente el estado económico de #209:

- capital actual;
- capital inicial;
- disponible;
- reservado;
- P&L Hoy / Semana / Mes / Total;
- evolución del equity;
- actividad;
- ligas activas.

La curva de capital se corrigió para representar el capital inicial y los puntos intermedios después de cada settlement persistido. No se fabrica mark-to-market para OPEN ni se reconstruyen backtests científicos.

### Partidos

Partidos muestra por fecha y liga:

- terminados apostados;
- próximos/en curso apostados;
- terminados no apostados;
- próximos/en curso no apostados;
- marcador;
- selección;
- cuota;
- stake;
- P&L;
- motivo de no apuesta;
- detalle Prediction/Decision/Capital;
- cuotas T-30 bajo demanda.

La lista pagina 40 partidos y no consulta cuotas hasta abrir el detalle.

Se corrigió la presentación de Capital para no confundir una evaluación inexistente con `INELIGIBLE / NO_POSITIVE_KELLY_EDGE`; los casos evaluados sin edge muestran un motivo económico explícito en vez de “Evaluación no disponible”.

---

## 6. Rendimiento y aislamiento del reporting

La nueva UI no depende de `PipelineRun.report` ni recorre `PredictionExperiment` para renderizar las páginas principales. Las mediciones de Pass 3 mantuvieron consultas acotadas incluso al añadir cientos de experimentos científicos de fondo.

Esto eliminó el acoplamiento que había permitido que la antigua portada recorriera suficiente historia como para agotar un worker local. El producto continuo consume estado operacional de #209 y su ledger económico; la profundidad científica permanece en Lab.

---

## 7. UAT y evidencia

### UAT histórica offline

Se reprodujo una jornada archivada real del 19/09/2026 con:

```text
42 partidos
10 ligas
267 cuotas T-30 archivadas
```

El replay utilizó reloj virtual, PostgreSQL aislado y provider simulado. No se alteró el reloj del host y no hubo llamadas físicas.

Resultado:

```text
42/42 T-30 procesados
42 Prediction
42 Decision
25 señales HOME/AWAY
17 NO_BET
0 posiciones económicas
```

Los 25 casos accionables tenían EV negativo y fueron rechazados correctamente por Capital.

### UAT económica sintética

Una segunda DB aislada reutilizó equipos, kickoffs y resultados, cambiando únicamente precios T-30 identificados explícitamente para forzar edge positivo. El pipeline real recorrió:

```text
Prediction
→ Decision
→ Capital eligibility
→ OPEN
→ reserved exposure
→ settlement
→ P&L
→ equity
→ frontend
```

La UI de Inicio y Partidos coincidió con el ledger.

### Seguridad de UAT

En todas las reproducciones:

```text
real_betting=false
Capture scheduler OFF
Beat OFF
Inkabet automatic OFF
sin requests físicas
DB dev normal preservada
DB scratch separadas
```

El cierre técnico incluyó la limpieza de los recursos temporales creados específicamente para UAT, incluidos los contenedores `finsport-dev-fs022-uat-web` y `finsport-dev-fs022-synth-web`, las DB scratch, los artefactos `tmp/FS-022_*` ya absorbidos por evidencia durable y el entorno `finsport-dev`. La limpieza no toca el volumen PostgreSQL operacional protegido.

---

## 8. Calidad automatizada

El gate final previo al cierre alcanzó:

```text
188 pruebas focalizadas
957 pruebas en make check
80.69 % de cobertura
Black PASS
Ruff PASS
Django check PASS
migration check PASS
dependency/security checks PASS
```

Los tests retirados correspondían al reporting científico que dejó de ser superficie de producto y fueron sustituidos por pruebas del nuevo reporting, Capital, períodos Lima, OPEN/settled/VOID/NO_BET, filtros, paginación, detalle, performance y ausencia de consultas científicas en las páginas continuas.

La corrección de review sobre skips T-30 añadió regresión específica sobre la frontera Capture → #209.

---

## 9. Hallazgos materiales y resolución

### A. Reporting histórico automático en cada wake

**Problema:** el pipeline automático podía reconstruir demasiado reporting experimental histórico en wakes frecuentes.
**Resolución:** el runtime automático quedó restringido a trabajo prospectivo T-30 admisible de #209; Experiment Lab permanece manual.

### B. Tiempo efectivo de colocación

**Problema:** una evaluación iniciada antes del kickoff podía atravesar trabajo lento concurrente.
**Resolución:** placement y retry consultan tiempo efectivo y fallan cerrados al superar kickoff.

### C. `INELIGIBLE` mostrado como evaluación inexistente

**Problema:** `NO_POSITIVE_KELLY_EDGE` podía aparecer como “Evaluación no disponible”.
**Resolución:** la UI consume estado persistido y distingue no evaluado, NO_BET, INELIGIBLE, capacidad, OPEN y settlement.

### D. Curva económica incompleta

**Problema:** Inicio mostraba esencialmente inicio y saldo final.
**Resolución:** la serie usa settlements reales ordenados y conserva puntos intermedios de equity.

### E. OPEN result poll presentado como incidente

**Problema:** un resultado todavía no terminal podía producir `DEGRADED` vacío.
**Resolución:** `OPEN_RESULT_NOT_DUE` representa el estado esperado; errores reales conservan `DEGRADED`/`FAILED`.

### F. Skip T-30 reintentable bloqueaba una captura válida posterior

**Problema:** un skip sin intento físico podía crear una clasificación terminal de Capital por Match.
**Resolución:** los estados reintentables con `actual_attempts=0` quedan fuera de evaluación global hasta disponer de evidencia válida o una condición final real.

---

## 10. Fallos de proceso y causas raíz

### Harness UAT con import incompleto

Una versión del runner utilizó `Decimal` sin importarlo. La causa fue una modificación incremental del harness sin una compilación mínima previa. Regla durable: todo harness UAT generado fuera del producto debe compilarse/validarse antes de entregarse.

### Replay inicial sin `coverage["odds"]=True`

La primera reproducción no generó odds porque el fixture reconstruido omitió una precondición consumida por el planner real. Regla durable: un replay debe reconstruir prerequisites del producer real, no sólo objetos visibles del escenario.

### Diagnósticos manuales con campos asumidos

Dos comandos ORM usaron inicialmente campos inexistentes (`match_id` sobre `CapitalEvaluation` y `strategy_identity` sobre `CapitalRuntimeConfig`). La causa fue escribir diagnósticos desde el modelo conceptual y no desde el schema exacto. Regla durable: derivar diagnósticos ORM del modelo real antes de entregarlos; un fallo del diagnóstico no es evidencia de fallo del producto.

### Whitespace detectado tarde

`git diff --cached --check` detectó trailing whitespace en un Markdown y `make format` no lo modificaba. La causa fue no aplicar suficientemente temprano el packaging/hook preflight a artefactos no Python. Regla durable: ejecutar temprano `trailing-whitespace` / `end-of-file-fixer`; no usar ceremonias SHA para documentos narrativos sólo por cambios mecánicos de whitespace.

### Residuos de documentación CURRENT del frontend anterior

Tras reemplazar las rutas de producto quedaron referencias operativas que todavía describían `/` como Admin. La causa fue un blast radius inicialmente centrado en views/templates/tests. Regla durable: un cambio de rutas de producto debe revisar conjuntamente `urls`, views, templates, static, tests, README, runbooks CURRENT, enlaces de monitorización y smoke/UAT, preservando aparte la documentación histórica.

---

## 11. Recomendaciones durables

1. Separar evidencia auditable de evidencia consumible: persistir un CaptureWorkItem no significa automáticamente que Prediction/Decision/Capital deba terminalizarlo.
2. Revisar retries en fronteras compartidas: si el producer permite retry de una logical identity, ningún consumer downstream debe cerrarla antes de que ese retry quede resuelto.
3. Usar reloj inyectado + DB scratch + provider fake para UAT temporal; no alterar el reloj del host.
4. Mantener UAT histórica y sintética como clases de evidencia separadas.
5. Mantener la UI continua desacoplada de reconstrucción científica histórica.
6. Tratar motivos persistidos (`NO_POSITIVE_KELLY_EDGE`, `PENDING_CAPACITY`, `OPEN_RESULT_NOT_DUE`, `EXPIRED_CAPACITY`, etc.) como parte del contrato observable de producto.
7. Ejecutar packaging/hook checks temprano para artefactos Markdown y otros archivos no Python.
8. Incluir la limpieza de contenedores UAT, DB scratch y `tmp/FS-###_*` en el mismo boundary de cierre que `make dev-destroy`, después de capturar los hechos útiles en feedback/handoff/evidencia durable y sin tocar `finsport_postgres_data`.

---

## 12. Resultado de producto

FS-022 dejó un camino simulado entendible de extremo a extremo:

```text
partido
→ cuota T-30
→ probabilidad de mercado
→ decisión deportiva
→ filtro económico
→ stake simulado
→ posición
→ resultado
→ P&L
→ capital
→ interfaz
```

El usuario puede inspeccionar qué partidos fueron observados, cuáles generaron señal, cuáles fueron descartados y por qué, qué stake/cuota se utilizaron, el estado OPEN/settled, el P&L y la evolución del capital.

Todo permanece simulation-only y sin side effects financieros reales.

---

## 13. Cierre

FS-022 queda registrado como técnicamente aceptado y cerrado en su alcance.

El incremento consolidó:

```text
#209 prospectiva simulada
+
Capture T-30 gobernada
+
Decision/Capital integrados
+
settlement y continuidad
+
reporting de producto
+
UAT histórica
+
UAT económica sintética
+
review correctivo
+
regresiones
+
evidencia durable
+
limpieza de recursos temporales
```

No se habilitaron apuestas reales ni autenticación de bookmaker.

Los hechos durables de producto, arquitectura, operación y roadmap deben proyectarse selectivamente a sus fuentes F001/F003/F004/F006; este feedback queda como registro histórico del ticket, de sus findings y de las lecciones de proceso que produjo.
