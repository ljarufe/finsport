# FS-022 — Investigación integral final para F008: estrategia global prospectiva, operación y frontend

**Proyecto:** Finsport · **Consolidación:** 27 de septiembre de 2026 · **Destino:** F008, definición de FS-022.
**Estado:** FS-021 **CLOSED / MERGED / DEPLOYED**, por confirmación del responsable. Los handoffs adjuntos tienen un corte documental premerge; no se trasladan sus casillas pendientes como tareas abiertas.
**Alcance:** research pre-ticket, sin cambios de código/ACTIVE, sin llamadas nuevas a proveedores y sin apuestas reales. Este documento **reemplaza íntegramente** las versiones anteriores de investigación y el handoff visual separado: no requiere adendas.

## 1. Objetivo único

Consumir la selección económica #209 de FS-021 y convertirla en **el único camino automático prospectivo de simulación**, `Prediction → Decision → Capital`. Capturar y preservar datos de **todos los partidos de las ligas activas**, independientemente de si se apuestan; retirar del ciclo continuo las demás técnicas sin borrarlas del Experiment Lab; realizar un cutover seguro, reversible mediante drenaje, y sustituir totalmente el frontend antiguo por las dos páginas acordadas: **Inicio** y **Partidos**.

No reabrir el torneo científico, añadir estrategias online, ampliar el horizonte gratuito hoy+mañana ni conectar apuestas de dinero real.

## 2. Qué entregó FS-021: dos autoridades distintas

| Plano | Autoridad/resultado | Consumo en FS-022 |
|---|---|---|
| Resultado original | `GLOBAL_STRATEGY_V1`, **#60**: `DIXON_COLES × VALUE(0.05) × LEGACY_CAPPED`; disposición científica `UNSTABLE`. | Autoridad histórica inmutable, **no** el deployment prospectivo nuevo. |
| Selección económica posterior | `FS021_SINGLE_ECONOMIC_SELECTOR_V1`, **#209**: `MARKET_CONSENSUS/fs013-market-consensus-v2 × SELECTIVE_CONFIDENCE(0.45) × FRACTIONAL_KELLY(lambda=0.25,max_lanes=10)`. | **Estrategia que FS-022 activa en simulación prospectiva**. |
| Modo de #209 | `PRACTICAL_BASELINE_SIMULATION_ONLY`; publicación con `automatic_operational_routing=false` y `real_betting=false`. | FS-022 crea autorización y estado operacional **separados** para empezar a simular en vivo; no reescribe el resultado del experimento ni autoriza apuestas reales. |

FS-021 completó 231 combinaciones conceptuales, 693 trayectorias observadas sobre T+120/130/150 y bootstrap T+150 sobre 1.877 partidos de 10 ligas. Para #209: retorno mínimo retrospectivo entre lags **+66,6712 %**, drawdown máximo observado **12,2285 %**, pérdida de cola **17,5961 %**; 11/12 slices positivos pero H2 ≈−8,75 % y concentración de ~73 % del P&L positivo en cinco oportunidades. **La selección económica es post hoc sobre el mismo universo:** no valida rentabilidad prospectiva ni revierte `UNSTABLE`. No importar sus ganancias retrospectivas a la banca del nuevo deployment.

La banca del experimento fue **100u únicas por combinación**, compartidas entre hasta 10 lanes y todas las ligas. No hay sub-banca ni transferencias entre lanes.

## 3. Regla de Capital congelada: `equity <= 5u`

La instrucción antigua que decía reemplazar `<=5` por `<5` queda **sin efecto** por decisión posterior del usuario. FS-022 debe conservar el contrato **realmente ejecutado por FS-021**:

```text
DEPLETION_FLOOR = Decimal('5')  # fuente/configuración central única
trigger = equity <= DEPLETION_FLOOR
scope = combinación completa, nunca lane ni available_cash
```

Cada wake liquida primero **todas las OPEN vencidas**, actualiza equity/reservas/política y sólo entonces comprueba el umbral. Si equity ≤5u y queda al menos una OPEN, pausa nuevas solicitudes y placements en `AWAITING_FINAL_OPEN_SETTLEMENT`, pero sigue liquidando **todas** las posiciones; un saldo intermedio >5u no reactiva mientras quede OPEN de la pausa. Tras la última: equity >5u permite reanudar sólo oportunidades aún pre-kickoff; equity ≤5u establece `OPERATIONAL_DEPLETION` y no abre más apuestas. Si no había OPEN y equity ≤5u, el brazo se detiene antes de un nuevo placement. Conservar ledger, resultados y universo lógico aun tras la terminación. Distinguir esta regla de `PENDING_CAPACITY`, `EXPIRED_CAPACITY`, cero stake, falta transitoria de cash y ruina matemática.

UAT obligatoria: **equity exactamente 5u SÍ activa la regla**; caso FS-021 D05 de tres OPEN con liquidaciones sucesivas a 3u, 6u con una OPEN restante y 9u: sólo reanuda después de la tercera.

## 4. CURRENT y frontera de cambio

| CURRENT | Hecho conocido | FS-022 |
|---|---|---|
| Scheduler | `football.pipeline.wake` cada 300 segundos, pipeline integrado activo; wake Capture independiente desactivado. | Conservar único owner; seleccionar sólo #209 para ejecución automática. |
| Discovery | Hoy + mañana (`DAYS_AHEAD=1`) por presupuesto de API gratuita. | **No ampliar**; navegar otras fechas sólo muestra los datos existentes. |
| Prediction/Decision | Técnicas y políticas históricas pueden ejecutarse de forma prospectiva en paralelo. | Apagar alternativas **sólo del runtime continuo**; preservarlas en Experiment Lab manual. |
| Capital | Siete bancas automáticas antiguas independientes `DIXON_COLES × MODAL_ALL`. | Retirarlas de apertura mediante drenaje; preservar su historia/OPEN hasta settlement. |
| UI | Django + Bootstrap; `/` informe comparativo y `/daily/` todas las técnicas con detalle abundante. | Sustituir físicamente reporting viejo por dos páginas rápidas; conservar Django y Bootstrap. |
| Observabilidad | Grafana/Loki, `PIPELINE_OVERDUE` durante apagados y `RECONCILIATION_PENDING` reiterado. | Mantener Grafana separado, reducir ruido sin ocultar fallos. |

La inspección operacional de **24/09/2026** observó servicios sanos al completar el arranque, HTTP 200, las diez ligas habilitadas, Beat/pipeline activos y siete configs Capital sin OPEN en esa instantánea. **No** usar ese cero histórico como garantía de que en el cutover futuro no existirán posiciones abiertas.

## 5. Capture general ≠ estrategia global ≠ Experiment Lab

```text
CAPTURE: todas las ligas habilitadas / todos sus partidos dentro del contrato
       fixture, status, resultado 90', 1/X/2, observaciones/timestamps
             ├──→ EXPERIMENT LAB manual: técnicas y challengers
             └──→ ESTRATEGIA AUTOMÁTICA ÚNICA #209
                       Prediction → Decision → Capital simulado
```

`NO_BET`, PC apagada, ventana perdida, inputs incompletos o banca agotada **no detienen Capture general**. Preservar observaciones inmutables de odds con tiempo real, tres patas 1/X/2, fuente/bookmaker, primer momento conocido de resultados, estados y canonical IDs. Para features deportivas futuras, preservar los datos prospectivos disponibles dentro del presupuesto; no fingir que una feature adquirida posteriormente existió as-of. Las técnicas alternativas siguen disponibles en Experiment Lab pero **no figuran en la cabecera del frontend**, que no es una consola científica.

## 6. Comprobar ejecución prospectiva honesta de #209

La evidencia de FS-021 usó `ODDSPAPI_RECONSTRUCTED_T30_V1` histórico y una ejecución sintética a kickoff−30m. CURRENT usa captura operativa diferente. **No presumir equivalencia** de proveedor, cobertura, edad de cuota, bookmakers o disponibilidad temporal. FS-022 debe comprobar sólo compatibilidad de implementación, **sin repetir selección científica**: motor Market Consensus versionado, política Selective Confidence 0,45, Capital Fractional Kelly 0,25/10 lanes, probabilidades as-of pre-kickoff, tres cuotas observadas y precio de ejecución genuinamente disponible. Nunca usar resultado ni cuota post-kickoff, nunca fabricar T−30 y nunca caer silenciosamente a Dixon-Coles/Modal-All si falta una pieza. Si la ruta viva no produce los inputs, **fail closed** y corrección dirigida de capture/implementación.

La nueva instancia productiva empieza con **100u simuladas** como configuración propuesta coherente con FS-021, a congelar expresamente en F008 antes de la primera activación. No suma los saldos de las siete bancas previas ni hereda sus posiciones. El resultado histórico #209 permanece exclusivamente en las superficies de investigación.

## 7. Separar resultado de FS-021 del estado operacional mutable

**No** renombrar ni sobrescribir el `GLOBAL_STRATEGY_V1` histórico #60 para hacerlo apuntar a #209. Una representación de producto mínima, por ejemplo `ActiveStrategyDeployment`, resuelve la autoridad económica versionada #209 y registra aparte lo que puede cambiar durante la operación:

| Campo | Regla |
|---|---|
| `selection_source` | `FS021_SINGLE_ECONOMIC_SELECTOR_V1`, resultado #209 y versiones completas de sus tres capas, sin hardcodear un índice como única identidad. |
| `mode` | `PRACTICAL_BASELINE_SIMULATION_ONLY`, sin apuestas reales. |
| `state` | `ACTIVE`, `DRAINING`, `DRAINED`, `STOPPED`, `DEPLETED` o equivalentes sencillos. |
| `activated_at` | Instante UTC persistido **al activar por primera vez**; inmutable durante reinicios y deploys ordinarios. |
| `entry_enabled` | Una única compuerta de nuevas posiciones. |
| `initial_bankroll` | 100u propuestas; valor explícito e inmutable por instancia. |
| `cutover_id` | Exclusividad e idempotencia al cambiar de estrategia. |

Así, detener, reemplazar o reiniciar el producto no modifica el resultado científico ni la selección económica publicada. Una edición documental de research no bloquea el runtime por un checksum cosmético; sólo importa la autenticidad de **inputs científicos efectivamente consumidos**.

## 8. Cutover, parada manual, replacement y rollback de estrategia

La misma máquina de estados se usa para introducir #209 y para futuros reemplazos:

```text
OLD_ACTIVE → DRAINING → DRAINED → NEW_ACTIVE
```

**DRAINING:** deshabilitar inmediatamente nuevas oportunidades y placements del path viejo; impedir simultáneamente aperturas prematuras del nuevo; continuar Capture general y recuperación/settlement. Los PENDING/PENDING_CAPACITY ya registrados del path antiguo deben adquirir una disposición terminal o causal que **no permita un placement posterior** al inicio de DRAINING. Las OPEN ya colocadas se liquidan normalmente. La barrera de admisión persistente evita doble apuesta de un Match durante el cambio.

**DRAINED:** `OPEN=0`, ninguna PENDING capaz de colocar y deuda relevante resuelta. Estimar la liberación desde el **último kickoff + horizonte de settlement efectivo**; T+150 minutos es referencia de planificación, a contrastar con los settings CURRENT. La hora estimada **no** es deadline que autorice settlement ficticio. Si la PC se apaga o el resultado tarda, el drenaje continúa cuando el sistema vuelve a funcionar.

**NEW_ACTIVE:** cerrar la antigua instancia de forma auditable, crear la banca simulada nueva y `activated_at`, activar sólo partidos aún elegibles **hacia adelante**. No reconstruir apuestas que habrían ocurrido antes del cutover. No transferir posiciones ni capital previo. Un deployment normal o reinicio **sin cambio de estrategia** no hace drenaje ni restablece saldos. Un rollback estratégico no equivale a hacer `git rollback` directo: debe respetar el mismo drain; rollback meramente técnico sin cambio de autoridad mantiene el contrato operativo habitual.

Caso futuro `DIAGNOSTIC_ONLY`: bloquear todas las entradas automáticas después de drenar las existentes; Capture y settlement continúan, Lab intacto, frontend indica ausencia de estrategia activa. **No es la disposición de #209**, que sí es baseline práctica de simulación.

## 9. Arranque tras máquina apagada y taxonomía de partidos

Orden seguro de startup: iniciar dependencias; recuperar posiciones OPEN y deuda de resultados; liquidar lo ya conocido; reanudar únicamente trabajos de Capture y apuestas prospectivas todavía válidas dentro del horizonte hoy+mañana. Si una ventana de 30 minutos pre-kickoff se perdió mientras la PC estaba apagada, **no** simular una apuesta retrospectiva. Un resultado histórico puede recuperarse sólo como dato.

| Caso | Estado semántico | Interpretación en la UI |
|---|---|---|
| Match anterior a `activated_at` | `PRE_GLOBAL` | Historia, experimento previo o antigua banca; nunca P&L de #209. |
| Evaluado y rechazado por la política | `GLOBAL_NO_BET` | Mostrar probabilidades, cuotas y motivo breve; sin dinero ni contabilidad. |
| Evaluado y colocado | `GLOBAL_BET` → `GLOBAL_SETTLED` | Elección, tres cuotas, stake y resultado/P&L real del simulador. |
| PC apagada durante la oportunidad | `GLOBAL_NOT_PROCESSED_HOST_OFFLINE` | Sin evaluación; **no** equivale a `NO_BET`. |
| Datos necesarios ausentes | `GLOBAL_BLOCKED_INPUT_MISSING` | Sin evaluación válida, no inventar probabilidades. |
| Ventana ya vencida | `GLOBAL_MISSED_WINDOW` | Sin apuesta, pero resultado/fixture retenidos. |
| Draining o depleted | `GLOBAL_PATH_STOPPED` o equivalente | No ejecutado; no equivale a descarte predictivo. |

Los nombres finales se adaptan a los modelos CURRENT, pero estas distinciones son obligatorias. El Match debe mantenerse en datos de investigación aunque su tarjeta esté plegada en producto.

## 10. Tiempos separados y fórmulas de rendimiento

Conservar o derivar honestamente: `fixture_discovered_at`, `scheduled_kickoff_at`, `strategy_evaluated_at`, `simulated_position_opened_at`, `match_started_at`, `match_finished_at`, `result_known_at`, `simulated_position_settled_at`. No crear artificialmente timestamps que el origen no proporciona. Las marcas de ejecución futura con dinero real son materia de otro ticket.

| Métrica | Tiempo/denominador |
|---|---|
| Partidos de una fecha | Kickoff en zona `America/Lima`; resultado final de **90 minutos reglamentarios**, no descanso ni prórroga. |
| Apostados | Posiciones realmente abiertas después de `activated_at`. |
| Ganados / perdidos | Posiciones `SETTLED_WIN` / `SETTLED_LOSS`; OPEN y VOID no cuentan como ninguna. |
| P&L diario, semana y mes | `simulated_position_settled_at` en Lima. No adelantar beneficios al kickoff. |
| Porcentaje de un período | `P&L_realizado_en_período / equity_total_al_inicio_del_período`, considerando activación a mitad del período. |
| Rentabilidad acumulada | `(equity_actual − initial_bankroll) / initial_bankroll`, sin aportaciones/retiros en FS-022. |
| Capital actual | **Equity total**, incluido el dinero reservado en posiciones OPEN. |
| Disponible | Equity − reserved exposure. |
| Apostado actualmente | Reserved exposure de posiciones OPEN, sin mostrar otra cifra redundante de «pendientes». |
| Gráfico | Evolución diaria del **equity total**, desde activación, más último valor actual. Nunca capital disponible. |
| Observados | Match únicos descubiertos/capturados de ligas habilitadas dentro de la era de activación, incluidos no evaluados. |
| Porcentaje de actividad | Cada contador / **partidos observados**; Observados = 100 %. |

Una posición abierta cerca de la medianoche puede liquidarse al día siguiente; su ficha permanece bajo la fecha de kickoff y su P&L pertenece al **día de liquidación**. Cuando no exista denominador válido, mostrar `—` en lugar de `0 %`. Sin posición NO_BET, ni ganancia ficticia ni derrota económica por acertar/fallar el pronóstico.

## 11. Diagnóstico de fixtures 21–24 septiembre: conclusión delimitada

La inspección local constató diez ligas habilitadas, cinco partidos registrados el 21/09 Lima y cero Matches los días 22–25, junto con descubrimientos `SUCCESS_EMPTY`. **DB vacía + SUCCESS_EMPTY no demuestra por sí solo que no existieran fixtures reales**. Al menos una referencia de partido argentino mostraba kickoff `22/09 00:15 UTC` —**21/09 19:15 Lima**— compatible con un partido ya incluido, pero la correspondencia exacta entre las filas y todos los encuentros argentinos citados no se autenticó una por una. Tampoco se verificó el payload bruto del proveedor para todas las fechas. Por ello, no declarar avería demostrada ni cobertura perfecta.

El usuario ratificó que el horizonte **hoy+mañana es deliberado por cuota gratuita**; conservarlo. El preflight acotado de FS-022 verificará un día con partido conocido, uno vacío legítimo, el mapping provider→Competition/Season/Match y los días hoy/mañana del UAT. A nivel UI, un día sin filas fuera de ese horizonte no debe identificarse como «confirmado vacío» si nunca fue consultado. Distinciones útiles: `CONFIRMED_NO_FIXTURES`, `DATA_PENDING`/`NOT_CHECKED`, `PIPELINE_ERROR`, `PROVIDER_ERROR`, `STALE_DATA`, presentadas con textos breves.

## 12. Plan de preflight externo acotado — **no ejecutado en research**

Antes de consultar, anotar proveedor/plan, endpoint, parámetros, intento máximo, cuota libre y reserva dinámica; realizar llamadas sólo con autorización y presupuesto disponibles. Propuesta: **cuatro GET obligatorios y uno opcional**, aprovechando cada respuesta para varios checks:

| Caso | Endpoint API-Football | Parámetros | Máximo |
|---|---|---|---:|
| Fecha con fixture conocido de liga activa | `GET /v3/fixtures` | `date=AAAA-MM-DD&timezone=America/Lima` | 1 |
| Fecha verificada realmente vacía | `GET /v3/fixtures` | `date=AAAA-MM-DD&timezone=America/Lima` | 1 |
| Hoy al ejecutar UAT | `GET /v3/fixtures` | `date=<today Lima>&timezone=America/Lima` | 1 |
| Mañana al ejecutar UAT | `GET /v3/fixtures` | `date=<tomorrow Lima>&timezone=America/Lima` | 1 |
| Resultado ya terminado, **sólo si el primero no basta** | `GET /v3/fixtures` | `id=<fixture id conocido>` | 1 opcional |

Presupuesto preliminar: **4–5 solicitudes físicas**, sólo si el proveedor realmente cobra una llamada por GET y se verifica cuota/coste del plan actual antes del probe. Revisar status HTTP, errores, cardinalidad/paginación, timezone, league/season external IDs, filtro de ligas activas, dedup, fixture refs, resultado 90', cuota reportada y reconciliación; no barrer temporadas ni registrar API keys. No ejecutar el quinto si una de las cuatro respuestas ya demuestra resultado terminal. Si falta headroom o el plan difiere, detenerse y replanificar, no improvisar retries.

## 13. Frontend CURRENT: inventario exacto y retiro

CURRENT se renderiza con Django templates/Bootstrap dentro del repositorio principal, **no** con el antiguo repositorio React. `/` usa `templates/reporting/historical.html`, `historical_view` y el selector `historical()`; `/daily/` usa `templates/reporting/daily.html`, `daily_view` y el selector `daily()`; navegación compartida en `templates/reporting/base.html`, rutas en `finsport/urls.py`.

| Pantalla CURRENT | Sección/componente | Modelos/selector y propósito | Disposición FS-022 |
|---|---|---|---|
| `/` histórica | Filtro liga, desde y hasta | `historical()`, Competition y períodos | **REMOVE** de producto. |
| `/` histórica | Cobertura y readiness Dixon-Coles | Season/HistoricalCoverage; diagnóstico técnico | **REMOVE** de producto, preservar datos. |
| `/` histórica | Evidencia general, comparativas y calibración Prediction | PredictionExperiment/Prediction; torneo descriptivo | **MOVE_TO_LAB**; sin página antigua oculta. |
| `/` histórica | Políticas Decision, cruces P×D y acuerdo entre técnicas | Decision y agregados históricos | **MOVE_TO_LAB**. |
| `/` histórica | Siete bancas automáticas de Capital | CapitalRuntimeConfig/CapitalPosition | **REPLACE** con banca única #209. |
| `/` histórica | Capital legacy, replay, Monte Carlo, stress y backtests | Experiment Lab/CapitalExperiment | **REMOVE** de UI; conservar motores y evidencia de investigación. |
| `/daily/` | Fecha, liga, día anterior y siguiente | `daily()` sobre Match con kickoff Lima | **KEEP/REPLACE** con selector de fecha y navegación anterior/hoy/siguiente. |
| `/daily/` | Liga, equipos, kickoff, estado, score | Match/Season/Competition | **KEEP** resumido, 90 minutos reglamentarios. |
| `/daily/` | Readiness y evidence identity Dixon-Coles | PredictionExperiment | **REMOVE** de UI de producto. |
| `/daily/` | Tabla de todas las Prediction y configuraciones | Prediction | **REPLACE** con probabilidades relevantes de #209. |
| `/daily/` | Tabla de todas las Decision y P&L teórico | Decision | **REPLACE** por elección o NO_BET único; retorno sólo de Capital **realmente simulado y colocado**. |
| Global | Admin/Grafana | Django admin y observabilidad | **KEEP** en cabecera. |
| Global | Link Experiment Lab | No hay interfaz web Lab CURRENT; se usa por CLI/manual | **NO LINK** en cabecera; Lab permanece utilizable externamente. |

**Limpieza acordada:** sustituir o borrar físicamente plantillas, selectors de reporting, CSS exclusivo y tests obsoletos de estas pantallas; evitar conservar el dashboard viejo en otra ruta o consultas redundantes. **No borrar** Git history, modelos históricos, OddsObservation, posiciones antiguas, fuentes, reportes experimentales durables, Admin, Grafana ni Experiment Lab. Reutilizar Django, Bootstrap y CSS mínimo actualizado.

## 14. Frontend aprobado: especificación completa y bocetos revisados con el usuario

**Decisión de producto definitiva:** exactamente dos pantallas —Inicio y Partidos—; cabecera `Finsport | Inicio | Partidos | Admin | Grafana`. Sin Experiment Lab en la cabecera, sin tercera pantalla de comparativas, sin fecha en Inicio, sin metodología ni parámetros de la estrategia visibles. Se trabaja con Django, Bootstrap y CSS mínimo. La interfaz es privada, por lo que no requiere avisos repetitivos explicando que los números no deben sumarse dos veces.

Los siguientes wireframes son **ilustrativos, no capturas de una implementación ni cifras reales**. Los ejemplos se conservan íntegros por ser el contrato visual concreto aprobado, incluyendo las tres cuotas en apuestas y las tres probabilidades en los no apostados.

#### 14.1. Estructura y navegación

**Exactamente dos páginas de producto: Inicio y Partidos.** Cabecera común:

```text
FINSPORT                 Inicio    Partidos       Admin    Grafana
```

- Sin fecha en Inicio.
- Sin Experiment Lab en la cabecera. Sigue disponible manualmente y fuera del frontend de producto.
- Sin nombres de modelos, parámetros internos, identidades experimentales ni información técnica de la estrategia.
- Django server-rendered + Bootstrap + CSS limpio y mínimo; reemplazo físico del reporting anterior, sin mantenerlo oculto ni conservar consultas antiguas.
- Admin y Grafana conservan sus enlaces en la cabecera.

#### 14.2. Pantalla Inicio — cinco secciones

#### Wireframe orientativo (datos exclusivamente ficticios)

```text
FINSPORT                   Inicio   Partidos             Admin  Grafana
───────────────────────────────────────────────────────────────────────

CAPITAL
┌────────────────────────────┐  ┌──────────────────────────────┐
│ CAPITAL ACTUAL TOTAL       │  │ CAPITAL INICIAL              │
│ 112,40 u                   │  │ 100,00 u                     │
└────────────────────────────┘  └──────────────────────────────┘
Disponible: 109,40 u              Apostado actualmente: 3,00 u

RESULTADOS
┌────────────────┬────────────────┬────────────────┬────────────────┐
│ HOY            │ SEMANA         │ MES            │ TOTAL          │
│ +1,80 u        │ −2,10 u        │ +7,30 u        │ +12,40 u       │
│ +1,63 %        │ −1,84 %        │ +6,95 %        │ +12,40 %       │
└────────────────┴────────────────┴────────────────┴────────────────┘

EVOLUCIÓN DEL CAPITAL TOTAL
  Capital, u
  115 ┤                                          ●
  110 ┤                                 ●───────╯
  105 ┤                  ●─────●────────╯
  100 ┼────●─────────────╯
      └──────────────────────────────────────────────
      Activación                               Actual

ACTIVIDAD TOTAL
┌────────────────┬────────────────┬────────────────┬────────────────┐
│ OBSERVADOS     │ APOSTADOS      │ GANADOS        │ PERDIDOS       │
│ 428            │ 63             │ 38             │ 24             │
│ 100 %          │ 14,7 %         │ 8,9 %          │ 5,6 %          │
└────────────────┴────────────────┴────────────────┴────────────────┘

LIGAS ACTIVAS                                           10 habilitadas
┌──────────────────────┬───────────────────────┬────────────────────┐
│ Liga                 │ Fechas                │ Estado             │
├──────────────────────┼───────────────────────┼────────────────────┤
│ Premier League       │ [inicio] – [fin]      │ ● En curso         │
│ Liga de ejemplo      │ [próx. inicio–fin]    │ ○ Próxima temporada│
│ Liga sin calendario  │ Por confirmar         │ ! Sin calendario  │
└──────────────────────┴───────────────────────┴────────────────────┘
```

#### Contrato de contenido

| Orden | Sección | Requisitos |
|---|---|---|
| 1 | Capital | Capital total actual (incluye reservas), capital inicial; debajo, disponible y apostado actualmente. No duplicar pendientes ni añadir avisos contables. |
| 2 | Resultados | Hoy, semana, mes y total; P&L en u y rentabilidad respecto al capital al inicio de cada período. |
| 3 | Gráfico | Serie temporal **del capital total global**, nunca del efectivo disponible. |
| 4 | Actividad total | Observados, apostados, ganados, perdidos. Cada cifra acompañada de su porcentaje sobre **todos los observados**. |
| 5 | Ligas activas | Cantidad habilitada; liga, fechas y estado. Temporada en curso verde. Fuera de temporada, fechas de la **próxima** temporada, nunca de la anterior. Si no consta, `Sin calendario`. Aviso compacto si ninguna está en curso. |

*Ejemplo de actividad:* 63 apostados = 38 ganados + 24 perdidos + 1 abierto. Sólo ganados/perdidos efectivamente liquidados entran en esas columnas; un pronóstico correcto sin apuesta no cuenta.

#### 14.3. Pantalla Partidos — cuatro grupos

**Controles:** selector de fecha específica, día anterior, hoy, día siguiente y filtro por liga. Mostrar una única fecha y liga/alcance cada vez.

**Orden:** terminados apostados → apostados en curso o próximos → terminados no apostados → próximos no apostados. Los no evaluados deben encontrarse sin confundirlos con `NO_BET`.

#### Wireframe orientativo (datos ficticios)

```text
PARTIDOS                   [◀] [26/09/2026 ▾] [HOY] [▶] [Liga: Todas ▾]
───────────────────────────────────────────────────────────────────────

1. TERMINADOS · APOSTADOS

Premier League                                     FINALIZADO · GANADA
Arsenal 2–1 Chelsea                              10:00 → 12:00
Decisión: Arsenal (1)                   Resultado: Arsenal
         Local 1          Empate X          Visitante 2
         [1,90]             3,40               4,20
Apostado: 2,00 u                                    +1,80 u (VERDE)
                                                    [Más información ▾]

Detalle opcional:
  Probabilidad estimada: 56,4 %
  Cuota evaluada antes de apostar: 1,90
  Motivo: sólo si es específico y útil.

2. EN CURSO / PRÓXIMOS · APOSTADOS

Bundesliga                                               PENDIENTE
Bayern – Dortmund                                          14:30
Decisión: Bayern (1)
         Local 1          Empate X          Visitante 2
         [1,82]             3,85               4,60
Apostado: 3,00 u                                     PENDIENTE (AMARILLO)
                                                    [Más información ▾]

3. TERMINADOS · NO APOSTADOS

Serie A                                              NO APOSTADO
Milan 1–1 Roma                                      FINALIZADO
Pronóstico más probable: Milan (local)              FALLÓ (ROJO)
                         Local 1      Empate X      Visitante 2
Cuotas                    2,00          3,20            4,10
Probabilidades             44 %          29 %            27 %
Motivo: cuota insuficiente.                 [Más información ▾]

La Liga                                              NO APOSTADO
Sevilla 0–2 Villarreal                              FINALIZADO
Pronóstico: Villarreal                              ACERTÓ (VERDE)
                         Local 1      Empate X      Visitante 2
Cuotas                    2,80          3,10            2,65
Probabilidades             31 %          28 %            41 %
Motivo: no alcanzó el criterio.           [Más información ▾]

SIN importe apostado, SIN P&L y SIN retorno para NO_BET.

4. PRÓXIMOS · NO APOSTADOS

Ligue 1 · 15:00       Lyon – Lille                NO APOSTADO (GRIS)
Cuotas: 2,10 / 3,20 / 3,60
Probabilidades: 46 % / 29 % / 25 %
Motivo breve cuando exista.                [Más información ▾]
```

#### Reglas generales para tarjetas y tablas

- Liga, equipos, estado, kickoff, hora final cuando exista, marcador reglamentario final de 90 minutos.
- **Apostados:** elección, las tres cuotas coherentes 1/X/2 observadas para la evaluación, stake y P&L simulado si la posición ya está liquidada. En curso: importe reservado y etiqueta pendiente; no mostrar una ganancia no realizada.
- **No apostados evaluados:** tres cuotas, tres probabilidades estimadas, resultado y acierto/fallo **del pronóstico** sin ninguna repercusión monetaria.
- **No evaluados:** etiquetar `Sin evaluación` (por ejemplo, PC apagada o inputs ausentes). Nunca presentarlos como si la estrategia hubiera rechazado una apuesta.
- Detalle oculto: probabilidad estimada, cuota evaluada antes de apostar, motivo de selección/rechazo **sólo si aporta información concreta**. Nada de IDs, configuración científica, método o indicadores irrelevantes.
- No inventar cuotas ni probabilidades retrospectivas cuando faltaron las capturas.

#### 14.4. Lenguaje visual

| Color | Significado |
|---|---|
| Verde | Ganancia liquidada, apuesta ganada, pronóstico correcto, temporada en curso |
| Rojo | Pérdida liquidada, apuesta perdida, pronóstico incorrecto |
| Amarillo | Apuesta pendiente, advertencia o calendario desconocido |
| Gris | No apostado / neutral / información secundaria |

Fondos blancos, márgenes generosos, bordes finos. Aplicar color principalmente a **cifras y etiquetas**, no a tarjetas completas. Pocas columnas visibles y distribución responsive en móvil.

#### 14.5. Rendimiento y sustitución del frontend anterior

- **Inicio:** cargar sólo métricas agregadas de la instancia productiva activa, puntos compactos del gráfico de equity total y ligas/temporadas.
- **Partidos:** consultar únicamente fecha y liga seleccionadas, y el camino global activo. No cargar todas las técnicas ni toda la historia; evitar consultas N+1 y precargas profundas.
- Los detalles ocultos se pueden consultar bajo demanda si ahorran carga.
- Eliminar físicamente plantillas, selectors, CSS exclusivo y tests antiguos del reporting sustituido. **No** borrar modelos, hechos históricos, resultados, posiciones, Experiment Lab, Admin, Grafana ni el historial Git.
- Seguir con Django + Bootstrap + CSS; no introducir React ni SPA.


### 14.6 Correspondencia exacta con el código CURRENT conocido

| Ruta/componente previo | Fuente conocida | Actuación de FS-022 | Riesgo de rendimiento que elimina |
|---|---|---|---|
| `/` → `historical_view` | `templates/reporting/historical.html`, `football.reporting.selectors.historical` | Reemplazar por Inicio; eliminar informe histórico antiguo del producto, sin conservar una ruta oculta que lo siga ejecutando. | Carga desmedida de todos los modelos/políticas/evidencias retrospectivas. |
| `/daily/` → `daily_view` | `templates/reporting/daily.html`, `football.reporting.selectors.daily` | Reemplazar por Partidos con fecha y liga seleccionadas, sólo la instancia global activa. Puede conservar la URL si ayuda a los enlaces. | Prefetch completo de todas las Prediction y Decision para cada Match. |
| Navegación y layout | `templates/reporting/base.html` | Cuatro enlaces aprobados; sin Lab. | No incorporar UI técnica pesada a todas las pantallas. |
| CSS de reporting antiguo | Estáticos exclusivos de las pantallas anteriores | Eliminar reglas muertas y sustituir estilos específicos, manteniendo Bootstrap. | Evitar una segunda implementación visual mantenida en paralelo. |
| Admin y observabilidad | Django admin, Grafana externo | Mantener enlaces en cabecera, sin importar sus métricas a Inicio. | Evitar queries adicionales o carga de paneles externos. |

**Retiro limpio del código anterior:** borrar o sustituir las plantillas, consultas, CSS y tests **exclusivos del viejo reporting**; actualizar rutas/tests; eliminar importaciones y referencias muertas. Mantener intactos modelos, migraciones, datos históricos, evidencia de experimentos y Git history. Evitar `DROP TABLE`, borrado de snapshots o eliminación física de resultados por confundir «frontend anterior» con datos del dominio.

### 14.7 Contrato de consulta y aceptación del rendimiento

| Pantalla | Estrategia de lectura | Regla de acotación |
|---|---|---|
| Inicio | Obtener una única instancia de estrategia activa y su snapshot actual; agregar posiciones/settlements desde `activated_at` con cálculos reproducibles; leer serie diaria compacta de equity total. | Nada de escanear todos los experimentos, versiones o siete configuraciones heredadas. |
| Inicio: actividad | Usar Match de la era global realmente observados, un agregado de posiciones colocadas y estados de settlement; no sumar duplicados por cada wake. | Cada Match cuenta una sola vez como observado; una posición por identity si el contrato de estrategia lo permite. |
| Inicio: ligas | Leer sólo `Competition.enabled` y `Season.start_date/end_date`; resolver actual y siguiente fecha real, si existe. | No inferir fechas de calendarios anteriores ni consumir provider extra. |
| Partidos | Una fecha Lima, filtro de liga opcional, joins acotados con la decisión/precio/posición del deployment. | Ni all-time, ni todas las técnicas, ni all seven Capital configs. |
| Detalle desplegable | Datos concretos de la fila, cargados con prefetch selectivo o endpoint privado bajo demanda si el coste lo justifica. | Un detalle desplegado no ejecuta una consulta masiva por cada fila visible. |

F008 fijará en el ticket un presupuesto SQL y de latencia medible en hardware local real después de obtener una línea base. El research no inventa cifras de rendimiento que no se midieron. La UAT debe instrumentar consultas SQL, tiempo servidor y memoria para Inicio, un día vacío, un día con muchos partidos y detalles abiertos; verificar ausencia de N+1 y consistencia tras reinicio.

### 14.8 Precisión funcional en la UI

1. El gráfico siempre representa **equity total**, que incluye stakes reservados en posiciones OPEN; nunca la curva de cash disponible.
2. Los cuatro porcentajes de actividad utilizan como denominador **todos los Matches observados desde la activación**: observados 100%, apostados, ganados y perdidos. Un VOID puede formar parte de apostados pero no de ganados/perdidos. Un OPEN no cuenta como ganada ni perdida.
3. En apuestas, la tabla 1/X/2 corresponde a un trío coherente de cuotas observadas. Resaltar la elección y presentar stake/P&L sólo si existe posición realmente colocada. Distinguir cuota de evaluación y precio de ejecución si difieren.
4. En NO_BET terminado, mostrar 1/X/2 y tres probabilidades **as-of**, pronóstico más probable, resultado reglamentario y acierto/fallo predictivo. Sin stake, sin retorno monetario y fuera de contadores de apuestas ganadas/perdidas.
5. Un Match capturado pero no evaluado porque la PC estaba apagada, faltaban datos o la ventana expiró no es un NO_BET. Debe conservar una etiqueta distinta y los datos disponibles sin inventar probabilidades/cuotas.
6. Si existe fecha de término real del Match en el proveedor y el dato fue retenido, mostrarla. Si no, no inventarla como `kickoff + 90m` ni confundir resultado conocido con hora real de finalización.
7. No mostrar información técnica de método, configuración, identity, provenance, readiness o estados internos salvo texto de indisponibilidad realmente útil para el responsable.
8. Colores: verde ganancia/acierto/temporada vigente, rojo pérdida/error, amarillo apuesta pendiente/advertencia, gris neutro/NO_BET. Usar también texto/etiquetas para que la información no dependa sólo del color.

## 15. Observabilidad y manejo de apagados

Grafana/Loki permanecen accesibles desde cabecera; no volcar su detalle en Inicio. `PIPELINE_OVERDUE` durante una PC apagada/reiniciándose no demuestra por sí solo avería; tras startup, exigir que el pipeline retome el ciclo real. `RECONCILIATION_PENDING` repetido cada wake en períodos sin partidos genera ruido y merece un ajuste acotado de condición/frecuencia sin suprimir fallos genuinos.

Eventos mínimos correlacionables: estrategia resuelta/activada/bloqueada; start/complete de drain; Match evaluado/NO_BET/sin input/ventana perdida; posición abierta/liquidada; deuda de settlement; depletion ≤5u y eventual recuperación al terminar todas las OPEN. No registrar claves ni payloads de proveedor. El frontend puede mostrar un estado operacional breve **sólo cuando afecte al usuario**.

## 16. UAT consolidada y aceptación

| ID | Prueba verificable |
|---|---|
| U01 | Resolver **#209 económica** con identidad y versiones completas; **#60/UNSTABLE** originales permanecen inmutables; no apuestas reales. |
| U02 | Sólo #209 produce nuevas posiciones automáticas; las otras técnicas siguen funcionando en Lab on-demand. |
| U03 | Capture preserva fixtures, resultados y odds de **todos** los Match habilitados, incluso NO_BET, PC apagada o banca depleted. |
| U04 | Probes GET acotados: fecha con partido, fecha vacía, today/tomorrow, mapping/provider/season y resultado si hace falta, dentro de presupuesto. |
| U05 | Cuota T−30 auténtica y antes de kickoff; tres patas as-of, diferencia evaluación/colocación y cero apuesta retroactiva. |
| U06 | Cutover bloquea antiguas/nuevas aperturas durante DRAINING; PENDING queda sin reintento de colocación y OPEN antigua liquida hasta cero. |
| U07 | Apagado/reinicio durante DRAINING y con OPEN: estado persistente y settlement posterior, sin duplicar exposición. |
| U08 | Deploy ordinario/reinicio **sin** cambio de estrategia no drena, no reinicia bankroll ni modifica `activated_at`. |
| U09 | `equity == 5u` **activa** regla; caso FS-021 D05 tres OPEN con 3→6→9u no reanuda hasta última liquidación. |
| U10 | Inicio: equity actual = disponible + reservado; gráfico equity **total**; cuatro % sobre observados; cifras de resultados no duplicadas. |
| U11 | Inicio: cinco secciones; ligas verdes dentro de temporada, **próxima** temporada fuera, `Sin calendario` si no existe. |
| U12 | Partidos: fecha específica + navegación, cuatro grupos, final 90', horas, tres cuotas apostados y tres cuotas + tres probabilidades NO_BET. |
| U13 | NO_BET acertado/fallido jamás modifica capital ni suma a apuestas ganadas/perdidas; offline ≠ NO_BET. |
| U14 | Caso kickoff antes de medianoche y settlement después: partido bajo kickoff-day, P&L bajo settlement-day, sin doble atribución. |
| U15 | Las plantillas, consultas y CSS antiguos obsoletos se eliminan del nuevo código, pero datos científicos/Capital históricos se conservan. |
| U16 | Con BD representativa, medir consulta inicial, fecha con muchos Match, lazy details, N+1 y memoria; no escanear todas las técnicas. |
| U17 | Stop/replacement/rollback estratégico por el mismo drain; ninguna de las siete bancas antiguas se reactiva inadvertidamente. |
| U18 | Una autoridad futura `DIAGNOSTIC_ONLY` falla cerrada sin entries, manteniendo Capture y settlement. |

Agrupar hallazgos en **una pasada de UAT consolidada** salvo dependencia auténtica. No volver a ejecutar el torneo FS-021 ni auditar hashes de documentos Markdown.

## 17. Seguridad, rollback y frontera de dinero real

Separa el bloqueo de **nuevas entradas** del servicio que debe liquidar posiciones existentes. Un rollback de estrategia sigue el drenaje y la frontera de exclusividad; un rollback de código sin cambio de autoridad mantiene el deploy ordinario. No borrar la base operacional, sus volúmenes ni la evidencia histórica. Las cifras presentadas son **capital interno simulado**, no saldo del bookmaker. Un futuro ticket de ejecución real deberá definir órdenes aceptadas, saldo/cash real, errores, límites, reconciliación y liquidación; FS-022 sólo deja la separación lógica y **no** implementa conectores de casas de apuestas.

## 18. Paquete para F008 y secuencia de implementación

| Pass propuesto | Entregables y frontera |
|---|---|
| P1 — Autoridad + preflight | Consumir #209 sin sobrescribir #60, resolver versiones y estado operacional; definir 100u, `activated_at`, exclusión de entradas; enumerar/autorización de GET acotados. |
| P2 — Runtime | Selección automática única, inputs as-of, Capture independiente, migración siete configs, PENDING/OPEN drain, regla ≤5u idéntica a FS-021. |
| P3 — UI limpia | Reemplazar completamente reporting viejo por Inicio y Partidos acordados; performance y temporadas futuras; conservar Admin/Grafana. |
| P4 — Recuperación | Apagados, idempotencia del cutover/restart, logging mínimo, rollback estratégico sin nueva exposición prematura. |
| P5 — UAT | U01–U18, rendimiento con histórico, correcciones agrupadas, despliegue local según F004/F009. |

No crear aún el ticket, no rehacer el experimento, no copiar outputs científicos voluminosos a `docs/research/`, no exigir checksum de prosa ni introducir cambios ajenos. Ticket aprobado fuera de Git; research aceptada podrá incluirse como **una única versión vigente** en repositorio.

## 18A. Fronteras ejecutables para el futuro ticket (sin abrir otra investigación)

### 18A.1 Invariantes de activación

| Invariante | Condición comprobable | Conducta en fallo |
|---|---|---|
| Autoridad correcta | La instancia operacional resuelve el resultado económico #209/versiones exactas; el original #60 sigue inmutable. | No activar, registrar causa; no fallback implícito. |
| Elegibilidad prospectiva | Inputs as-of disponibles y Match aún antes de kickoff, con evento de cuota válido según contrato de ventana. | `NO_EXECUTION_PRICE`, `MISSED_WINDOW` o razón causal equivalente; nunca inventar una apuesta. |
| Única entrada | Una sola instancia admite aperturas y la barrera de cutover impide duplicar `(deployment, Match, event)` bajo reintentos. | Bloquear duplicado idempotentemente, conservar evidencia de evaluación. |
| Contabilidad | Equity total, reservado y disponible reconcilian antes/después de apertura y settlement. | Fallo explícito y no nuevas exposiciones hasta investigar. |
| Depletion | Umbral **`<= 5u`**, compartido por 10 lanes y aplicado con semántica de todas las OPEN de FS-021. | Pausar aperturas y continuar settlements. |
| Sin apuestas reales | No existe llamada de colocación a bookmaker; sólo posición simulada interna. | Hard stop ante dependencia de ejecución real accidental. |

### 18A.2 Máquina de estados operativa propuesta

La selección científica/económica es un hecho inmutable; el deployment es la entidad mutable. Un estado operacional mínimo puede ser `ACTIVE`, `DRAINING`, `DRAINED`, `STOPPED` o `DEPLETED`. El flag de admisión es independiente del servicio de settlement. Una transición a `DRAINING` cierra **atómicamente** admisión y reintentos PENDING que todavía podrían colocar; deja que el settlement recorra todas las OPEN. Sólo después de OPEN=0 y deuda relevante resuelta se admite la nueva instancia. Un apagado conserva este estado persistido. Un deploy ordinario con la misma estrategia **no dispara cutover**.

La estimación de la última liberación usa la última posición abierta y su kickoff más el horizonte contractual efectivo. T+150 es referencia experimental de planificación; se debe **leer el parámetro CURRENT** antes de anunciar una hora. Retrasos del proveedor o del PC pueden alargar el drenaje; ninguna estimación autoriza settlement artificial.

### 18A.3 Registro prospectivo independiente de Capture

Para los diez torneos habilitados, mantener capturas de fixture, odds reales (1/X/2, observación/fuente), resultado reglamentario y estados, incluso si #209 devuelve NO_BET, se agota o no pudo ejecutarse porque el host estuvo apagado. Separar los relojes de descubrimiento, evaluación, colocación, kickoff, resultado conocido y settlement. No convertir un resultado reconciliado después en evidencia anterior al kickoff. El pipeline de captura no depende de que una estrategia admita nuevas entradas.

### 18A.4 Coste, autenticidad y plan de proveedor

No ejecutar GET en este documento. En preflight de FS-022, declarar con antelación cuatro GET API-Football (`/v3/fixtures` con date y timezone Lima: un día con partido conocido, uno confirmado vacío, hoy y mañana) y un quinto opcional por fixture ID finalizado. Confirmar primero coste real/cuota restante del plan y comparar mappings por competencia/temporada, zona horaria, paginación, status y score 90'. Un día sin Match en DB y `SUCCESS_EMPTY` **no bastan** como demostración de inexistencia de fixtures; el episodio argentino UTC/Lima sólo explica una discrepancia de fecha posible, no garantiza que todo proveedor funcione.

La comprobación de Market Consensus/Decision/Capital debe utilizar oportunidades vivas elegibles y datos retenidos auténticos; si hoy no hay partidos o cuota suficiente, UAT ejecuta fixtures locales controlados y pospone la única prueba externa que exige un evento real. No gastar cuota repetidamente durante un día vacío para demostrar una imposibilidad de observación.

### 18A.5 Matriz de riesgos y mitigaciones

| Riesgo | Mitigación FS-022 | Aceptación |
|---|---|---|
| Odds históricas reconstruidas ≠ cuotas vivas realmente disponibles | Smoke de captures limitadas + validación de inputs as-of y ejecución real simulada, con fallos clasificados. | Ninguna apuesta nace de quote post-kickoff. |
| Provisión CURRENT recrea siete config por hardcoding al reiniciar | Migration/cutover cambia provisioning y testea restart con configs antiguas retiradas. | Una sola nueva estrategia admite posiciones. |
| PENDING del viejo camino coloca tras el cambio | Barrera persistente de entradas + expiración/no placement causal. | Ningún old/new overlap; cero duplicados. |
| OPEN antiguas quedan huérfanas | Settlement independiente de flag de nuevas entradas y de estado ACTIVE. | Todas terminan o su deuda sigue visible hasta resolution, no se pierden. |
| Equity exactamente 5u se considera erróneamente activa | Fixtures de borde y D05. | Misma semántica `<=5` FS-021. |
| Ausencia de provider parece día vacío | Estado de cobertura diferenciado; no anunciar vacío confirmado sin consulta válida. | UI dice dato desconocido cuando corresponde. |
| Dashboard tarda por consultas ilimitadas | Selectors nuevos, serie compacta, fechas acotadas, medición N+1 y comparación contra base realista. | Umbral de latencia/SQL fijado y cumplido en F008/UAT. |
| Historia experimental contamina curvas globales | Filtrar por deployment + `activated_at`, positions realmente abiertas y settlements correspondientes. | Inicio empieza con nueva banca 100u, no hereda returns históricos. |
| Mala hora del fin del partido | Mostrar sólo hora retenida y correctamente identificada. | No estimar 90 minutos desde kickoff como hecho. |
| Accidente de limpieza frontend elimina datos científicos | Borrado limitado a presentación/selectors/tests obsoletos, sin migraciones destructivas. | Retención intacta en deploy. |

### 18A.6 Aceptación previa a Codex y entrega a F008

F008 recibe este único archivo como investigación vigente. Antes de implementación: leer investigación aprobada y ticket fuera de Git; congelar explícitamente la banca inicial operacional propuesta de 100u; confirmar mapping de autoridad #209 y disponibilidad de inputs con el presupuesto acotado; identificar contrato real de settlement CURRENT; definir presupuesto de queries medible; trazar tests de migración/restart/UAT; mantener prueba de que `real_betting=false`. No abrir de nuevo FS-021, no consultar todas las fuentes F00x sin motivo y no rehacer 3.465.000 paths. Los archivos científicos e índices consumidos sí deben autenticarse según su contrato, **no** calcular hashes ceremoniales de Markdown.

## 19. Definition of Ready y últimas verificaciones técnicas

**Ya cerrados:** selección #209, distinción #60/UNSTABLE, FS-021 desplegado, umbral `equity<=5u`, 100u como convención experimental, horizonte hoy+mañana, captura general, único camino prospectivo, cutover/restart, estructura y contenido del frontend, ausencia de Experiment Lab en cabecera, temporadas vigentes/siguientes y exclusión de dinero real.

**Pendientes sólo de preflight ejecutable, no de otra conversación de diseño:** (1) confirmar inputs y tres cuotas de #209 en captura viva antes de activar; (2) confirmar configuración efectiva del primer horizonte de settlement para planificar el drain; (3) verificar existencia de fechas de temporadas futuras en DB, mostrando `Sin calendario` donde no existan; (4) congelar explícitamente 100u como banca de la **instancia operacional** en F008; (5) fijar y medir presupuesto de SQL/latencia de ambas páginas. Ninguna es motivo para reinterpretar FS-021 ni para volver a discutir el frontend.

**Conclusión:** investigación pre-ticket lista para F008. El ticket FS-022 deberá construir/activar **#209 en simulación prospectiva**, no inferir que ya estaba activa por haberse desplegado FS-021; distinguir desde el primer día resultados de laboratorio y capital realmente simulado después de `activated_at`.

## Fuentes y límites de la investigación consolidada

- `FS-021_handoff_final.md`: dos resultados, #60/UNSTABLE y #209, alcance y resultados históricos; texto preparado antes del merge, estado final suministrado por el usuario.
- `FS-021_feedback.md`: regla final ≤5u, contrato D05, selección económica, limitaciones retrospectivas y límites de activación.
- Inspección local aportada en `FS-022_01_local_runtime(1).txt`, `FS-022_02_diagnostico_web_db.txt`, `FS-022_03_observabilidad.txt`, del 24/09, **no** nueva observación del 26/09.
- `FS-022_research_global_strategy_runtime_frontend.md` v1 y su prompt de corrección; **sustituidos** por este documento v2.
- Decisiones del usuario recogidas en la revisión interactiva de las dos pantallas, umbral ≤5u y horizonte gratuito hoy+mañana.


## Dictamen de cierre de investigación

**Decisiones de producto pendientes: ninguna.** El alcance, la selección #209, la semántica `<=5u`, la arquitectura de una estrategia, el drenaje, el horizonte gratuito hoy+mañana y las dos pantallas están aprobados. **No se requieren nuevos scripts o queries locales para redactar F008.** Quedan verificaciones técnicas delimitadas que deben ejecutarse en preflight/UAT del propio FS-022: disponibilidad/compatibilidad prospectiva de cuotas para #209 bajo cuota autorizada; parámetros de settlement efectivos del nuevo entorno; calendario futuro real cuando exista; medición de latencia/SQL con datos representativos. Esas verificaciones no son una nueva fase de selección científica ni una razón para reabrir FS-021.
