# FS-017 — feedback final de implementación, UAT y proceso

**Rama:** `FS-017-mvp-runtime-continuity-quota-reconciliation`
**Base:** `4d009136921a1526b3440a40c70a5d0a1cd4f7f1`
**PR:** #23
**Fecha:** 2026-09-16

## Resultado técnico

FS-017 implementó el MVP de continuidad de runtime, reconciliación de resultados y gobierno dinámico de cuota para Finsport.

El runtime automático quedó concentrado en `football.pipeline.wake` con una cadencia de 300 segundos. El stack de desarrollo conserva Beat deshabilitado. La adquisición de fixtures cubre el horizonte protegido de hoy+mañana y la cuota se gobierna a partir de headers realmente observados, intentos físicos persistidos y una reserva dinámica para obligaciones críticas.

Capital conserva la propiedad de la deuda OPEN, settlement y capacidad pendiente. Capture conserva discovery, odds y completion no-bet opcional. Football-Data conserva la reconciliación histórica/current-season no-bet y no adquiere autoridad para liquidar posiciones Capital OPEN.

La adquisición de fixtures API-Football quedó centralizada en formas físicas soportadas:

* `fixtures?date=YYYY-MM-DD&timezone=America/Lima`;
* `fixtures?id=<fixture_id>`.

El mecanismo `fixtures?ids=` fue falsificado mediante evidencia live del plan actual y fue eliminado de los caminos automáticos. Las respuestas amplias por fecha se filtran a fixtures Finsport conocidos antes de sincronizar dominio.

La deuda OPEN inicia su primer intento en kickoff +130 minutos, con reintento normal +30 minutos, SUSP +60 minutos y PST transferido a reconciliación de fixture. Un date sweep puede liquidar incidentalmente otro OPEN terminal de la misma fecha y cancelar su deuda futura; un Match incidental no terminal conserva su programación. El fallback dirigido usa únicamente `id=` singular y está limitado por cuota.

La liquidación ocurre antes de la reconciliación de capacidad pendiente dentro del mismo wake, permitiendo reutilizar lanes/capital liberados sin reconstruir retrospectivamente una apuesta.

`R_open_result` representa oportunidades físicas reales mediante `(fecha Lima, wake efectivo de 300 segundos)` y no sólo fechas. Las obligaciones que comparten la misma oportunidad se coalescen; las oportunidades futuras distintas permanecen protegidas hasta que verdad terminal observada las haga desaparecer. La prioridad permanece:

`fixture > T30 > OPEN`

sin reserva fija 10/12 como autoridad normal.

Los date sweeps OPEN y non-bet auditan el número de fixtures Finsport realmente representados por la llamada, no el número global de filas devuelto por el proveedor. El fallback singular representa un fixture.

## Correcciones finales derivadas del review del PR #23

El review del PR encontró cuatro problemas válidos que fueron corregidos de forma consolidada.

### 1. Audit de llamadas manuales API-Football

Los comandos `sync_football_*` podían consumir cuota y observar headers sin crear `ProviderCallAudit`.

La corrección se realizó en el boundary común `_sync_base.SyncCommand`, antes de la primera llamada física. Las llamadas manuales API-Football quedan ahora incluidas en la misma autoridad persistida de cuota utilizada por el runtime automático.

Los tests verifican:

* persistencia de cada intento físico;
* headers de límite/remanente;
* pagination/retry exactos;
* incorporación del consumo manual en `quota_state()`;
* ausencia de doble contabilización.

### 2. Reserva T-30 sólo para captura realmente ejecutable

`R_t30` podía proteger cuota para Matches que el planner nunca iba a capturar por:

* coverage de odds ausente;
* identidad API-Football no resuelta;
* mercado Match Winner inexistente.

Se extrajo `football/capture_eligibility.py` como frontera compartida de prerrequisitos de captura.

Planner y quota utilizan ahora la misma definición para:

* coverage;
* fixture identity resuelta;
* mercado Match Winner válido.

Esto elimina una duplicación que podía volver a divergir y evita bloquear OPEN/maintenance con obligaciones T-30 físicamente imposibles.

### 3. Maintenance revalida reserva antes de cada llamada física

Catalogue/season maintenance verificaba la reserva dinámica al inicio de la operación, pero no nuevamente entre llamadas.

Ahora cada intento físico:

* conserva el bound máximo de operación;
* vuelve a consultar la autoridad de cuota persistida;
* vuelve a calcular la reserva crítica dinámica;
* sólo procede si después de esa llamada continúa existiendo margen por encima de la reserva.

Un header más bajo recibido en la primera request puede por tanto impedir correctamente una segunda request.

La semántica stale-epoch continúa fail-closed.

### 4. Fallo de catch-up posterior a Capital degrada correctamente el pipeline

Si Capital liquidaba posiciones y el posterior `settle_prospective_predictions()` fallaba, el error quedaba persistido pero `RESULT_SETTLEMENT` podía conservar un estado exitoso.

El phase object se reconstruye ahora correctamente:

* un catch-up fallido degrada `RESULT_SETTLEMENT`;
* un phase previamente FAILED permanece FAILED;
* el pipeline completo deja de poder reportarse SUCCESS en ese escenario;
* el camino exitoso conserva RESULT_SETTLEMENT SUCCESS.

## Evidencia final

La corrección consolidada del review ejecutó:

* **151 focused tests PASS**;
* **644 tests PASS** en `make check`;
* **85.05% coverage**;
* Black PASS;
* Ruff PASS;
* Django checks PASS;
* migration drift PASS;
* dependency/security gates PASS;
* `git diff --check` PASS;
* **0 llamadas live API-Football** durante la corrección.

La revisión limitada de callers no identificó otro constructor API-Football sin audit dentro del alcance. Capture y Capital ya configuraban audit context, catalogue y season maintenance atraviesan el guard corregido y el estado global del pipeline deriva del phase corregido.

R45, R45 Capital e Inkabet automático permanecen deshabilitados. No se introdujeron acciones de apuesta real ni side effects financieros externos.

---

# Feedback de proceso

FS-017 tenía research, scope y decisiones de producto suficientemente definidos antes de implementación. La cantidad de iteraciones que terminó requiriendo no debe interpretarse como una consecuencia inevitable de la complejidad del ticket. Una parte material del costo provino de fallos de ejecución y revisión del proceso.

## 1. El preflight externo no cerró todos los contratos físicos antes de Codex

El maintainer había autorizado llamadas GET acotadas para validar API-Football.

Se asumió que `fixtures?ids=` estaba disponible sin probar exactamente esa forma física antes del desarrollo. El UAT live demostró posteriormente que el plan actual la rechazaba tanto para uno como para múltiples IDs.

Una cantidad mínima de requests read-only habría eliminado esa premisa antes de escribir el código.

### Regla recomendada

Todo contrato externo nuevo o modificado debe cerrar antes del primer pass:

* endpoint;
* parámetros exactos;
* acceso del plan;
* campos requeridos;
* pagination;
* retry;
* costo físico.

Cuando una llamada read-only es segura y suficientemente barata, su ejecución temprana tiene prioridad frente a dejar incertidumbre material para UAT.

## 2. Se optimizó el recurso equivocado

La ejecución intentó conservar unas pocas requests API-Football y terminó consumiendo recursos más caros:

* tiempo del maintainer;
* múltiples passes Codex;
* tokens;
* ciclos repetidos de UAT/review;
* agotamiento completo de la cuota disponible de Codex;
* interrupción forzada del trabajo durante varias horas.

### Regla recomendada

Optimizar costo total del ticket, no una cuota aislada.

Un pequeño número de requests seguras que elimina una incertidumbre arquitectónica suele ser más barato que una nueva pasada de implementación.

## 3. Una premisa falsificada no disparó inmediatamente un blast-radius review

Cuando `ids=` fue falsificado, la primera corrección se concentró en OPEN.

No se buscó inmediatamente todo consumidor productivo del mismo contrato físico. Por eso el camino non-bet que todavía generaba `ids=` sobrevivió hasta una pasada posterior.

### Regla recomendada

Cualquier contrato falsificado dispara:

`premisa → búsqueda global → callers → tests → acceptance → docs/config → corrección consolidada`

antes de otro pass.

## 4. Acceptance permaneció PASS después de caer su premisa

A37 continuó temporalmente marcado PASS aunque su mecanismo físico dependía de `ids=`, que ya había sido falsificado live.

### Regla recomendada

Acceptance debe expresar dependencias.

Si una premisa necesaria cae, cualquier criterio dependiente vuelve inmediatamente a PENDING hasta que exista evidencia del mecanismo sustituto.

Los tests fake que codifican la premisa antigua no conservan por sí solos el PASS.

## 5. La revisión completa utilizada en el recovery llegó demasiado tarde

La preparación de Pass 6 revisó:

* branch completo contra master;
* código original relacionado;
* todos los callers de provider;
* duplicación de fronteras;
* quota;
* scheduler;
* persistencia;
* acceptance;
* documentación.

Ese método encontró problemas que revisiones más locales no habían detectado.

### Regla recomendada

Ese review no debe reservarse para Pass >=5.

Debe convertirse en el **Pass Review Gate normal después de cada pass**, incluido Pass 1:

`Codex pass`
→ verificar base/master
→ revisar full branch diff acumulado
→ revisar código original relacionado fuera del diff
→ revisar producer/consumer blast radius
→ revisar contratos externos
→ revisar shared-boundary/refactor opportunities
→ scheduler/ownership
→ quota/accounting
→ persistence/idempotence
→ configuration surfaces
→ acceptance invalidation
→ UAT independiente
→ decidir siguiente estado.

## 6. El review debe incluir código original, no sólo archivos cambiados

El contrato de fixtures estaba distribuido entre Capture, Capital y comandos manuales. Parte de esa estructura provenía de código heredado de master y no aparecía necesariamente como novedad del pass.

### Regla recomendada

Cada cambio material debe revisar también productores y consumidores relacionados en el código original.

La unidad de revisión es el sistema afectado, no exclusivamente las líneas nuevas.

## 7. Fronteras externas duplicadas deben activar una pregunta de refactor

Capture, Capital y sync componían independientemente formas equivalentes de adquisición de fixtures.

Corregir cada caller por separado habría dejado abierta otra divergencia.

El recovery centralizó los query shapes físicos mientras preservó separados los owners de dominio.

La corrección del PR repitió la misma lección en otra frontera: planner y `R_t30` necesitaban compartir los prerrequisitos estáticos de captura.

### Regla recomendada

Cuando varios subsistemas implementan la misma regla o request física, el review debe preguntar:

`¿estamos arreglando varios callers porque falta una frontera compartida?`

Preferir helpers pequeños y estables; no fusionar dominios que tienen ownership diferente.

## 8. Invariantes dinámicos deben revisarse durante la operación, no sólo al admission

Maintenance respetaba la reserva al inicio, pero no revalidaba el nuevo estado entre requests.

Un header recibido después de request 1 podía cambiar materialmente la cuota disponible.

### Regla recomendada

Los invariantes que dependen de estado externo mutable deben verificarse en el boundary físico relevante, no únicamente al planificar el batch.

En cuota:

`header nuevo → autoridad nueva → reserve nuevo → nueva decisión antes de request siguiente`.

## 9. Toda llamada física que comparte una cuota debe pertenecer a la misma contabilidad

Los comandos manuales podían consumir la misma cuota que el runtime automático sin alimentar `ProviderCallAudit`.

El resultado era una autoridad local incompleta.

### Regla recomendada

Una cuota compartida exige accounting compartido independientemente del trigger:

* scheduler;
* maintenance;
* command manual;
* recovery explícito.

El trigger puede cambiar capability/provenance, pero no puede quedar fuera de la contabilidad física.

## 10. Error persistido y estado de fase deben ser coherentes

El post-Capital catch-up registraba un error sin degradar la fase que representaba esa operación.

Eso permitía una inconsistencia entre observabilidad y status global.

### Regla recomendada

Cada catch/exception path debe revisar conjuntamente:

* error persistence;
* phase state;
* overall status;
* reporting;
* observability.

No basta con guardar el error.

## 11. Los findings independientes deben acumularse antes del siguiente pass

Durante FS-017 se enviaron algunas correcciones demasiado pronto.

Pass 4 fue un ejemplo claro: se interrumpió la fase de UAT independiente para corregir antes de haber terminado de reunir todos los findings.

### Regla recomendada

Ante un finding:

* continuar todo UAT/review independiente que siga siendo válido;
* acumular findings;
* enviar una sola corrección consolidada.

Sólo interrumpir si el finding bloquea físicamente evidencia posterior.

## 12. El harness de UAT debe minimizar infraestructura artificial

Se copió un módulo de tests a `tmp/` y falló por imports relativos y por una expresión `-k`, generando una iteración que no produjo evidencia de producto.

Los mismos tests ejecutados desde su paquete real funcionaron correctamente.

### Regla recomendada

Prioridad:

1. tests reales existentes;
2. pequeño diagnóstico autocontenido;
3. harness especial sólo cuando sea indispensable.

No copiar suites completas fuera de su package sin necesidad.

## 13. Un pass excepcional debe ser un recovery, no otro parche

La quinta/sexta pasada no debería comportarse como una corrección local adicional.

Pass 6 fue efectivo cuando comenzó por reconstruir:

* root cause;
* base/master;
* full diff;
* contratos;
* blast radius;
* acceptance;
* frontera compartida;
* UAT restante.

### Regla recomendada

Pass >=5 activa automáticamente un Recovery Gate.

El objetivo pasa a ser cierre técnico completo de los findings conocidos.

## 14. Configuration surfaces forman parte del review

El código había adoptado nuevos defaults, pero `.env.dist` todavía conservaba valores anteriores. El runtime dev también reveló overrides locales heredados.

Una suite completamente verde no detecta necesariamente esa divergencia.

### Regla recomendada

El Pass Review Gate incluye:

* `.env.dist`;
* effective `.env` sin exponer secretos;
* Compose;
* Django settings;
* scheduler flags;
* defaults y overrides efectivos.

La configuración puede derrotar una implementación correcta sin modificar el código.

## 15. No repetir pasos que el maintainer ya ejecutó

Durante el cierre se volvieron a indicar comandos/correcciones que ya habían sido ejecutados porque no se conservó correctamente el estado conversacional.

Esto añadió trabajo sin aportar evidencia.

### Regla recomendada

Cuando se entrega un paso al maintainer y éste continúa sin reportar fallo, asumir que ese paso se ejecutó correctamente.

Sólo repetirlo si aparece evidencia que lo invalida.

## 16. Se intentó modificar artefactos temporales prohibidos durante el cierre

La orquestación intentó regenerar/editar acceptance ledger, snapshot y otros artefactos `tmp/**` cuando el flujo acordado prohibía hacerlo como parte del cierre.

Fue un error recurrente y consumió iteraciones de corrección del propio proceso.

### Regla recomendada

Distinguir:

* evidencia temporal de ejecución, que puede existir bajo el `tmp/` convencional cuando corresponde;
* artefactos temporales de acceptance/snapshot cuyo refresh está prohibido en la fase de cierre.

Nunca convertirlos nuevamente en pasos ceremoniales.

## 17. El feedback final fue intentado demasiado pronto

Se intentó actualizar `docs/process/FS-017_feedback.md` antes del momento acordado.

El contrato del proyecto establece que el feedback final se incorpora una sola vez en el último commit del PR, inmediatamente antes del merge.

### Regla recomendada

Durante passes/reviews se acumulan notas en contexto.

El archivo de feedback se actualiza sólo en su checkpoint final.

## 18. El pass no dejó automáticamente un delta revisable

La corrección del PR terminó con un resumen textual y tests verdes, pero sin entregar inmediatamente el diff completo de esa corrección para revisión independiente.

Esto obligó al maintainer a ejecutar una extracción adicional antes de poder revisar el código.

Además, una extracción con `git diff` no incluyó el nuevo helper untracked, por lo que la revisión requirió recuperar esa pieza separadamente.

### Regla recomendada

Cada pass debe terminar proporcionando explícitamente un **review artifact del delta real**, incluyendo tracked y untracked, antes de cualquier commit.

Flujo recomendado:

`Pass`
→ focused gates
→ full gate cuando corresponda
→ delta completo tracked + untracked
→ independent review
→ corrección si existe finding
→ cierre.

Un resumen textual de Codex nunca sustituye el diff.

## 19. Las rutas de artefactos temporales deben respetar la convención del proyecto

Durante la revisión final se indicó generar un artefacto temporal en `~/` en lugar del `tmp/` del repositorio usado por Finsport.

Esto añadió confusión innecesaria y rompió consistencia con las guías operativas.

### Regla recomendada

Cuando realmente sea necesario materializar evidencia temporal:

`repo/tmp/FS-<ticket>_*`

No usar rutas improvisadas en home ni directorios globales, salvo requerimiento explícito.

Esto no modifica la prohibición específica de regenerar artefactos temporales de acceptance durante el cierre.

## 20. El review del PR debe formar parte del mismo ciclo de calidad

El review automático del PR encontró cuatro problemas válidos incluso después de un recovery exhaustivo:

* llamadas manuales fuera del audit compartido;
* T30 reserve desalineado con eligibility real;
* reserve no revalidado entre requests maintenance;
* error de catch-up no reflejado en phase status.

Esto demuestra que PR review sigue aportando una perspectiva útil, pero no debe utilizarse como sustituto deliberado del pre-PR review.

### Regla recomendada

El objetivo pre-PR continúa siendo:

`known findings = 0`

El PR funciona como una última revisión independiente capaz de detectar hechos nuevos, no como una fase planificada para completar trabajo conocido.

## 21. Costo del proceso

FS-017 agotó la cuota disponible de Codex y forzó una interrupción de varias horas. Además consumió múltiples rondas de ejecución y revisión del maintainer.

El scope del ticket estaba previamente definido; por ello este costo es evidencia directa de que la ejecución del proceso puede mejorarse materialmente.

La principal conclusión no es aumentar la cantidad de ceremonias, sino mover la evidencia y revisión al lugar correcto:

* probar contratos antes;
* revisar blast radius antes;
* inspeccionar el branch completo después de cada pass;
* compartir fronteras repetidas;
* consolidar findings;
* producir el diff revisable automáticamente;
* evitar repetir pasos y artefactos prohibidos.

## Conclusión de proceso

El patrón recomendado que emerge de FS-017 es:

`Research cerrado`
→ `External Contract Matrix`
→ `Codex pass`
→ `Pass Review Gate completo`
→ `UAT independiente acumulado`
→ `corrección consolidada sólo si existe finding`
→ `delta completo revisable`
→ `PR review`
→ `feedback final único`.

La calidad del proceso debe medirse por cuántas incertidumbres relevantes se eliminan antes del siguiente pass, no por cuántos gates o documentos se ejecutan ceremonialmente.

## Cierre final post-review PR #23

El review independiente del PR #23 encontró cuatro findings válidos adicionales y todos fueron corregidos en una única pasada consolidada.

### Correcciones derivadas del review

1. Los comandos manuales `sync_football_*` podían consumir cuota API-Football sin alimentar `ProviderCallAudit`. El audit quedó habilitado en el boundary común `_sync_base.SyncCommand`, de modo que llamadas, páginas, retries y headers observados participan de la misma autoridad de cuota que el runtime automático.

2. `R_t30` podía reservar cuota para Matches cuya captura era físicamente inejecutable por ausencia de coverage, identidad API-Football resuelta o mercado Match Winner. Planner y quota comparten ahora `football/capture_eligibility.py` como definición común de esos prerrequisitos.

3. Maintenance comprobaba la reserva dinámica al admitir una operación, pero no antes de cada llamada física posterior. Catalogue y season maintenance recalculan ahora autoridad de cuota y reserva crítica antes de cada request, de modo que un header más bajo recibido en la primera llamada puede bloquear correctamente la siguiente.

4. Un fallo en `settle_prospective_predictions()` posterior a un settlement Capital podía persistir un error sin degradar `RESULT_SETTLEMENT`. El phase state ahora refleja el fallo y el pipeline ya no puede terminar SUCCESS en ese escenario; un estado FAILED previo permanece FAILED.

La pasada consolidada terminó con 151 focused tests PASS, `make check` con 644 tests PASS y 85.05% de coverage, `git diff --check` PASS y cero llamadas live API-Football.

### Lecciones adicionales de orquestación

Durante el cierre aparecieron errores recurrentes de ejecución del propio proceso que añadieron trabajo sin aportar evidencia:

- Si un comando o corrección ya fue entregado al maintainer y éste continúa sin reportar un fallo, debe asumirse que fue ejecutado. Volver a ordenar el mismo paso genera duplicación y riesgo de cambios repetidos.
- Se intentó regenerar o modificar artefactos temporales de acceptance/snapshot en `tmp/**` durante una fase en la que el flujo lo prohibía. Los artefactos temporales de cierre no deben convertirse en pasos ceremoniales.
- Se intentó actualizar `docs/process/FS-017_feedback.md` antes de su checkpoint correcto. El feedback final debe incorporarse una sola vez, en el último commit del PR inmediatamente antes del merge.
- La última corrección de Codex devolvió inicialmente un resumen textual pero no un delta completo revisable. Un pass no debe considerarse listo para commit hasta que exista un diff real de sus cambios, incluyendo archivos untracked.
- La extracción manual del delta fue indicada inicialmente en `~/` en lugar de respetar la convención `repo/tmp/FS-<ticket>_*` cuando se necesita materializar evidencia temporal. Las rutas temporales deben seguir la convención del proyecto.
- El review posterior a cada pass debe abarcar branch-vs-master, código original relacionado, blast radius, contratos externos, configuración efectiva, shared-boundary/refactor opportunities y acceptance afectado antes de decidir una nueva pasada.
- Los cuatro findings válidos encontrados por el review del PR confirman que PR review es una última capa independiente útil, pero no debe utilizarse como sustituto deliberado del pre-PR review.

El patrón recomendado que deja FS-017 es:

`research cerrado`
→ `external contract matrix`
→ `implementation pass`
→ `full pass review gate`
→ `UAT independiente`
→ `delta completo revisable`
→ `corrección consolidada si existe finding`
→ `PR review`
→ `feedback final único`.
