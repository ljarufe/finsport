# FS-009 — Final Feedback

Status: FINAL RECONCILED FEEDBACK
Ticket: FS-009 — Crear frontend de reporting histórico y diario de evidencia experimental
Branch: `FS-009-reporting-ui`
PR: `#14`
Base: `master`

## 1. Resultado

FS-009 añade una superficie humana de reporting, server-rendered y estrictamente read-only para inspeccionar la evidencia experimental que Finsport ya persiste.

Superficies finales:

- `/` — reporting histórico, con evidencia prospectiva como población primaria.
- `/daily/` — inspección por fecha y liga de Predictions y Decisions persistidas.
- `/admin/` — Django Admin preservado como superficie de auditoría detallada.
- Grafana permanece separado del reporting de producto y conserva la responsabilidad de diagnóstico operacional.

La implementación mantiene separados los tres conceptos de dominio:

```text
Prediction
!=
Decision
!=
CapitalPolicy
```

FS-009 no selecciona automáticamente ganadores, no promueve modelos/policies, no realiza apuestas, no llama providers y no modifica evidencia de dominio o financiera.

---

## 2. Arquitectura y frontend

El reporting se implementó con:

```text
Django server-rendered templates
+
Bootstrap 5.3.8 compilado y vendorizado localmente
+
CSS pequeño de Finsport
+
<details>/<summary> nativo
```

No se añadió:

```text
JavaScript de aplicación
Node/npm
CDN runtime
HTMX
SPA
DRF/API de reporting
nuevo servicio frontend
nuevo puerto
```

El root de Django pasó de Admin a reporting y Admin quedó explícitamente en `/admin/`.

### Static serving

La UAT humana descubrió que la UI aparecía inicialmente sin estilos.

La causa real fue:

```text
los assets fuente existían en repository/static/
pero Django no tenía ese directorio registrado en STATICFILES_DIRS
```

El lifecycle existente ya era correcto:

```text
entrypoint
→ collectstatic

STATIC_ROOT compartido
→ nginx alias
```

No fue necesario introducir una arquitectura alternativa.

La corrección durable fue registrar el `static/` del repositorio mediante `STATICFILES_DIRS`.

Después de un ciclo normal:

```text
make safe-down
→ make dev-up
```

se verificó:

```text
/                                          → 200 text/html
/daily/?date=2026-08-29                   → 200 text/html
/static/reporting/bootstrap.min.css       → 200 text/css
/static/reporting/finsport.css            → 200 text/css
```

La UI referencia únicamente assets locales.

---

## 3. Layout y UAT visual

La primera versión styled seguía dejando demasiado espacio lateral y comprimía tablas anchas.

La corrección final de layout fue manual y acotada:

```text
container limitado
→ shell fluid compartido

margen lateral
→ aproximadamente 20 px

contenido
→ usa prácticamente todo el ancho disponible
```

No cambió selectors, métricas ni semántica.

La delta-UAT humana posterior pasó en desktop y narrow viewport.

Una posible reorganización visual adicional de Capital puede acompañar el bounded frontend delta de FS-010 cuando exista nueva evidencia longitudinal; no es necesaria para cerrar FS-009.

---

## 4. Prediction reporting

La home histórica presenta Prediction por identidad completa de modelo/configuración.

La comparación preserva:

```text
model_code
variant
model_version
model_config
```

Configuraciones materialmente distintas permanecen separadas y tienen etiquetas compactas deterministas, con detalle completo expandible.

Las métricas utilizan únicamente evidencia resuelta:

```text
sample_count
accuracy
log_loss
multiclass_brier
rps
confusion_matrix
calibration
```

La matriz de confusión se presenta como tabla semántica 1X2 y no como estructura Python cruda.

Calibration se presenta mediante tablas por clase/bin con:

```text
rango
N
probabilidad media
frecuencia observada
```

No se introdujeron nuevas métricas estadísticas ni se reinterpretaron las existentes.

---

## 5. Prospective vs BACKTEST

La evidencia prospectiva histórica y diaria filtra explícitamente:

```text
PredictionExperiment.mode = PROSPECTIVE
```

Los BACKTEST permanecen separados y no contaminan los agregados prospectivos.

Los brazos de backtest sin Prediction rows siguen siendo visibles cuando existe un estado persistido de indisponibilidad.

La UI soporta reason values persistidos como:

```text
scalar
list/tuple
unknown code
unexpected structured shape
```

sin producir 500 ni inventar una causa.

Los backtests se agrupan por su `PredictionExperiment #id` para que experimentos persistidos distintos no parezcan duplicados.

Se muestra contexto suficiente de:

```text
competition
period
engine version
completed_at
```

---

## 6. Decision reporting

Decision permanece separada de Prediction tanto en reporting histórico como Daily.

La identidad de comparación incluye:

```text
source Prediction model/config
+
Decision policy code/variant/version/config
```

Las métricas separan:

```text
evaluated fixtures
actionable Decisions
coverage
NO_BET
resolved actionable sample
hits
losses
economic sample
economic coverage
hit rate
```

### NO_BET

`NO_BET` es una Decision válida y no se contabiliza como pérdida.

### Unresolved Decisions

Una Decision accionable sin resultado canónico resuelto no se contabiliza como hit ni loss.

### Economic provenance

Una Decision sólo entra en la muestra económica cuando existe:

```text
resultado canónico resuelto
+
selected OddsObservation
+
selected price
+
observed_at < decision_time
```

La vista Daily expone el provenance económico conservado:

```text
precio seleccionado
source
bookmaker
observed_at
decision_time
```

### Historical Decision economics

El review del PR detectó que `_decision_metrics()` calculaba:

```text
flat_unit_pnl
roi
```

pero la tabla histórica no los mostraba.

La corrección final presenta:

```text
N económico / Decisions con precio válido
PnL simulado (stake plano 1u)
ROI simulado
```

Sin muestra económica:

```text
PnL → —
ROI → —
```

No se recalcula economía en el template.

---

## 7. Prediction × Decision

La intersección Prediction × Decision permanece descriptiva y neutral.

Se conservan cuatro celdas:

```text
Prediction correcta + Decision accionable
Prediction incorrecta + Decision accionable
Prediction correcta + NO_BET
Prediction incorrecta + NO_BET
```

No se interpreta `Prediction correcta + NO_BET` como pérdida o beneficio perdido.

Los cruces están agrupados por identidad completa de modelo/policy/configuración.

---

## 8. Agreement entre modelos

El agreement se calcula dentro de una instancia válida:

```text
PredictionExperiment
+
Match
```

y preserva la identidad completa de cada modelo/configuración.

Se evita:

```text
self-pair
cross-pair entre configuraciones distintas
inflated N por múltiples instancias
```

La salida es descriptiva:

```text
N conjunto
agreements
agreement rate
disagreements
A correct / B incorrect
B correct / A incorrect
shared errors
```

No produce recomendación de ensemble.

---

## 9. Daily reporting

`/daily/` es prospective-only.

Presenta por partido:

```text
competición
kickoff
estado en castellano
resultado
Predictions
Decisions
```

No utiliza `Team.__str__` como título principal, evitando duplicar la competición.

Cada Prediction muestra identidad/configuración suficiente.

Cada Decision muestra separadamente:

```text
modelo origen
policy
acción
resultado
estado hit/loss/NO_BET
reason
config
economic provenance
```

Los reason codes de Decision poseen un vocabulario de presentación distinto del vocabulario de availability.

Entre los códigos clasificados se incluyen:

```text
MODAL_OUTCOME
CONFIDENCE_THRESHOLD_MET
BELOW_CONFIDENCE_THRESHOLD
VALUE_ABOVE_THRESHOLD
NO_POSITIVE_VALUE_ABOVE_THRESHOLD
NO_VALID_MARKET
EXACT_LEGACY_CONTEXT_UNAVAILABLE
UNAVAILABLE_FOR_REPLAY
```

El fallback de Decision es neutral:

```text
Motivo no clasificado
```

y no afirma incorrectamente que una Decision normal sea “No evaluable”.

---

## 10. Capital reporting

FS-009 reporta únicamente evidencia Capital ya persistida.

No crea un bankroll longitudinal acumulado y no encadena experimentos independientes.

Cada fila mantiene provenance del source:

```text
CapitalExperiment
mode
policy
PredictionExperiment origen
source model/comparator
Decision policy
initial bankroll
input count
```

### REPLAY

`REPLAY` utiliza únicamente su contrato determinista persistido.

Cuando existen, muestra:

```text
terminal_bankroll
total_pnl
roi
maximum_drawdown
practical_ruin
max_stake_pre_bankroll_ratio
stake_concentration
```

La presentación distingue correctamente:

```text
False → No
True  → Sí
0     → 0
missing → —
```

### MONTE_CARLO / STRESS

El review del PR detectó que la implementación inicial aplicaba el schema determinista a todos los modos Capital.

Eso hacía que runs estocásticos válidos aparecieran principalmente como `—`.

La corrección final separa explícitamente:

```text
REPLAY
```

de:

```text
MONTE_CARLO
STRESS
```

Los modos estocásticos muestran únicamente métricas realmente persistidas, entre ellas cuando están disponibles:

```text
path_count
mean_terminal_bankroll
median_terminal_bankroll
terminal_bankroll_quantile_1
terminal_bankroll_quantile_5
mean_pnl
median_pnl
practical_ruin_probability
maximum_drawdown_distribution
max_stake_distribution
max_stake_pre_bankroll_ratio_distribution
stake_concentration
expected_shortfall
```

No se fabrican:

```text
deterministic terminal_bankroll
deterministic practical_ruin
deterministic maximum_drawdown
stochastic ROI
```

La provenance del `PredictionExperiment` origen se conserva también en las filas estocásticas.

### Exact metric semantics

Se mantienen separadas:

```text
max_stake_pre_bankroll_ratio
stake_concentration
```

No se renombran como una métrica genérica de “exposición” ni se interpreta `stake_concentration` como Gini.

---

## 11. Enabled competition scope

El review de PR detectó que el dropdown decía:

```text
Todas las ligas habilitadas
```

mientras los querysets sin filtro podían incorporar evidencia de competiciones deshabilitadas.

La corrección final aplica:

```text
Competition.enabled = True
```

al scope predeterminado de:

```text
historical Prediction
historical Decision
daily Matches
BACKTEST
Capital mediante su source PredictionExperiment
```

No hay IDs hardcodeados.

Como contexto operacional de UAT, el maintainer habilitó:

```text
local 1270 — FR — Ligue 1
local 1276 — NL — Eredivisie
local 1524 — PE — Primera División
```

FS-009 no modificó esos flags ni realizó backfill de evidencia.

---

## 12. Performance

Se añadió una regresión de query count para `/daily/`.

La prueba inicialmente detectó un N+1 provocado indirectamente por `Team.__str__`.

La corrección precarga las competiciones necesarias de los equipos y mantiene el número de queries acotado/constante al aumentar:

```text
matches
Predictions
Decisions
```

Los joins adicionales de provenance económico no reintrodujeron N+1.

No se añadió cache, materialization, background aggregation ni nueva persistencia para conseguirlo.

---

## 13. Read-only / safety boundary

Reporting utiliza únicamente operaciones de lectura.

Durante validación y UAT:

```text
provider calls = 0
task dispatch = 0
domain writes = 0
financial writes = 0
```

Los counts mantenidos antes/después de browser UAT fueron idénticos:

```text
PredictionExperiment  10 → 10
Prediction            2312 → 2312
Decision              21162 → 21162
OddsObservation       321 → 321
CapitalExperiment     5 → 5
CapitalPolicyRun      5 → 5
```

Delta: `0` para cada modelo.

No se introdujeron migrations.

---

## 14. Real UAT findings and corrections

La UAT humana fue material para FS-009.

Detectó y corrigió:

### Runtime failure 1

Persisted unavailable reasons podían ser listas.

El presentation layer inicial asumía un string hashable y `/` fallaba con:

```text
TypeError: unhashable type: 'list'
```

Se introdujo presentación segura para scalar/list/unknown/unexpected shapes.

### Runtime failure 2

Una expresión `default:` del template Capital intentaba resolver una clave alternativa ausente incluso cuando `metrics={}`.

El resultado era:

```text
VariableDoesNotExist
```

en `/`.

La presentación Capital pasó a preparar valores seguros antes del template.

### Percentage presentation

Ratios 0–1 se mostraban inicialmente como si ya fueran porcentajes.

Se añadió un formatter común:

```text
0.5 → 50.0%
-0.335 → -33.5%
```

### Static serving

Los CSS locales estaban versionados pero no registrados como static source de Django.

Se corrigió mediante `STATICFILES_DIRS`.

### Information hierarchy

La UAT detectó:

```text
reason codes mal contextualizados
source-model poco visible
configuraciones distintas visualmente ambiguas
calibration/confusion crudas
Capital False ocultado como missing
backtests aparentemente duplicados
team labels redundantes
copy técnico en inglés
```

Todos fueron corregidos mediante presentation/selectors/templates, sin modificar evidencia persistida.

### Responsive layout

La última delta-UAT detectó compresión innecesaria de tablas.

Se resolvió con un shared fluid shell de aproximadamente 20 px laterales.

La delta-UAT desktop/narrow posterior fue aceptada por el maintainer.

---

## 15. Representative UAT case

Caso congelado y revisado:

```text
Prediction 1181
Match 1156
Competition: Spain — La Liga
Levante vs Real Betis
Kickoff: 2026-08-29 15:00:00+00:00
```

Prediction:

```text
MARKET_CONSENSUS
predicted = AWAY
actual = HOME
→ incorrecta
```

Decision:

```text
Decision 10895
MODAL_ALL
action = AWAY
actual = HOME
selected_price = 2.2800
→ loss
→ -1u simulado
```

Odds provenance:

```text
OddsObservation 197
observed_at = 2026-08-28 23:31:12.043119+00:00
decision_time = 2026-08-29 00:01:19+00:00

observed_at < decision_time
```

La UI mantuvo correctamente separado:

```text
Prediction correctness
!=
Decision hit/loss
```

---

## 16. Automated evidence

Antes de los últimos findings del PR, la suite alcanzó:

```text
294 passed
86.61% coverage
```

La corrección consolidada del review amplió reporting a:

```text
23 focused reporting tests passed
296 full-suite tests passed
86.65% coverage
```

Validaciones reportadas:

```text
Black                         PASS
Ruff                          PASS
Django check                  PASS
pip check                     PASS
pip audit                     PASS
migration drift               PASS — No changes detected
git diff --check              PASS
bounded Daily query count     PASS
```

El output de `make check` se truncó durante la etapa de cobertura en la última pasada; todas sus etapas anteriores pasaron y la cobertura se ejecutó/validó separadamente con:

```text
296 passed
86.65%
```

La corrección manual final de provenance de Capital estocástico modifica sólo presentación y una assertion focalizada. Antes del commit final debe validarse mediante:

```text
pytest -q football/tests/test_reporting.py
git diff --check
```

---

## 17. PR review findings

PR `#14` produjo tres findings materiales y válidos.

### Finding A — P1 — stochastic Capital schema

Problema:

```text
MONTE_CARLO/STRESS
→ tratados como REPLAY
→ evidencia persistida aparecía como missing
```

Corrección:

```text
mode-aware Capital presentation
```

sin aliases falsos ni ROI inventado.

Durante la revisión del correction diff se detectó además que la primera versión de la tabla stochastic había perdido la columna de source provenance.

Se restauró:

```text
PredictionExperiment #id
source model/comparator
Decision policy
```

también para `MONTE_CARLO/STRESS`.

### Finding B — P1 — Decision economic result omitted

Problema:

```text
flat_unit_pnl / roi calculados
pero no presentados
```

Corrección:

```text
N económico
PnL simulado stake plano 1u
ROI simulado
```

### Finding C — P2 — disabled competition leakage

Problema:

```text
selector sólo exponía enabled
pero default aggregates podían incluir disabled
```

Corrección:

```text
enabled-only default scope
```

en las cinco superficies afectadas.

No se identificaron scope expansions ni trabajo adicional fuera de FS-009.

---

## 18. Files / boundaries changed

La implementación final afecta principalmente:

```text
finsport/settings.py
finsport/urls.py

football/reporting/
football/templatetags/reporting.py
football/tests/test_reporting.py

templates/reporting/base.html
templates/reporting/historical.html
templates/reporting/daily.html

static/reporting/bootstrap.min.css
static/reporting/finsport.css
static/reporting/LICENSE-bootstrap.txt

docs/research/FS-009_reporting_ui_research.md
docs/process/FS-009_feedback.md
```

El research fue maintainer-owned y se preservó según el contrato del ticket.

No se añadieron modelos, migrations, provider integrations ni task dispatch.

---

## 19. Limitations / unavailable

FS-009 no pretende demostrar cuál model, Decision policy o CapitalPolicy es definitivamente mejor.

La evidencia actual puede tener:

```text
muestras pequeñas
brazos UNAVAILABLE
configuraciones no comparables
Capital experiments independientes
poca evidencia prospectiva en algunas ligas
```

La UI mantiene esas limitaciones visibles en lugar de rellenarlas mediante inferencias o backfill.

Los valores económicos siguen siendo simulaciones.

---

## 20. FS-010 boundary

FS-009 no implementa evaluación longitudinal de CapitalPolicy.

La secuencia aprobada permanece:

```text
FS-009
→ frontend humano sobre evidencia actual

FS-010
→ longitudinal CapitalPolicy evidence
→ growing real resolved sample
→ bounded later frontend delta

FS-011
→ evaluator de Prediction + Decision + Capital
```

Cuando FS-010 produzca evidencia longitudinal nueva, podrá modificar de forma acotada la sección Capital de este frontend.

No debe reinterpretarse el reporting actual como sustituto de FS-010.

---

## 21. Observability / audit impact

FS-009 no reemplaza observability.

Responsabilidades finales:

```text
Reporting UI
→ evidencia experimental persistida comprensible

Django Admin
→ auditoría detallada de objetos

Grafana/Loki/Alloy/watchdog
→ diagnóstico operacional
```

El reporting no crea background work.

Los failures operacionales siguen investigándose fuera de esta superficie.

---

## 22. Process findings

Aprendizajes materiales de ejecución:

### Browser authority must be explicit

Un HTTP 200 técnico no demuestra que una superficie humana esté correctamente servida.

Para Finsport:

```text
:8000
→ Django/Gunicorn technical smoke

:8001
→ nginx browser surface
→ static serving authority
```

### Static acceptance must verify the actual asset

No basta con que el HTML responda 200.

Para una UI local-static conviene verificar:

```text
asset HTTP status
Content-Type
actual CSS body
normal startup lifecycle
```

### Runtime-shaped persistence must be tested

Los dos 500 reales encontrados provinieron de persisted shapes que los tests iniciales no cubrían:

```text
list-valued reason
empty metrics dict
```

Los fixtures de reporting deben representar formas reales persistidas.

### Query-count regression has high leverage

La prueba de queries descubrió un N+1 indirecto en presentation (`Team.__str__`) que no era obvio leyendo el selector.

Debe conservarse.

### Presentation contracts must be mode/context aware

Dos ejemplos:

```text
Decision reason != availability reason

REPLAY metrics != stochastic Capital metrics
```

Una UI puede ser técnicamente correcta y aun así perder semántica si reutiliza un presentation schema incompatible.

### Review findings remain hypotheses until verified

Los tres comments del PR fueron inspeccionados contra:

```text
actual selector
actual template
actual Capital metrics contract
ticket/research
```

antes de corregirse.

### Ephemeral artifacts are not ceremony

`tmp/**` es efímero.

No debe actualizarse por cada green ni para sincronizar wording.

Sólo se genera un artefacto temporal cuando existe una necesidad real de ejecución/revisión.

Cuando se necesita:

```text
mkdir -p tmp
→ generar dentro del repositorio
→ usar
→ maintainer puede borrarlo
```

No generar documentos temporales del proyecto fuera del repositorio.

---

## 23. Pass / budget disposition

La implementación consumió:

```text
Pass 1 — implementation
Pass 2 — consolidated pre-UAT correction
Pass 3 — real UAT/runtime fix
Pass 4 — consolidated human-UAT correction
```

El PR review produjo posteriormente una corrección excepcional adicional, autorizada tras reassessment porque existían:

```text
2 × P1 valid findings
1 × P2 valid finding
```

Fue consolidada en una única PR-review correction.

No se realizaron pasadas Codex sólo para documentación.

La corrección responsive final fue manual y estrictamente de layout.

---

## 24. New Work Discovered

No se descubrió trabajo nuevo que deba bloquear FS-009.

Trabajo ya conocido y explícitamente posterior:

```text
FS-010
→ longitudinal CapitalPolicy evidence
→ possible bounded Capital frontend delta
```

Las tres ligas adicionales habilitadas por el maintainer amplían la población futura, pero no crean un nuevo requirement de FS-009.

---

## 25. Final disposition

FS-009 queda técnicamente reconciliado con:

```text
implementation
+
automated evidence
+
human UAT
+
PR review findings
+
final review correction
```

La corrección final debe entrar junto con este feedback en el mismo substantive commit del review fix.

Después:

```text
push
→ GitHub CI sobre nuevo SHA
→ Codex/GitHub re-review
```

Si el nuevo SHA queda verde y no aparecen findings materiales nuevos:

```text
no feedback synchronization commit
no tmp ceremony
→ merge
→ sync master
→ cleanup branch
→ Planka Done
→ final handoff to main chat
```

Un evento simplemente verde no requiere volver a modificar este feedback.
