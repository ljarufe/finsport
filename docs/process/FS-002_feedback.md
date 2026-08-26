# FS-002 — Feedback final

**Ticket:** FS-002 — Consolidar datos de fútbol en API-Football y retirar legacy
**Proyecto:** Finsport
**Estado del feedback:** final reconciliado de implementation + corrections + UAT
**Base:** `master`
**Branch de ejecución:** `FS-002-consolidate-football-data`

> **Gate de publicación:** este archivo debe entrar al commit sólo después de que el último `make check` y `git diff --check` pasen. En la sección “Evidencia automatizada final” queda un marcador que se reemplaza por `PASS` inmediatamente después de ese gate, antes de `git add`.

---

## 1. Outcome

FS-002 reemplaza el núcleo histórico de datos de fútbol por un core canónico y multi-source preparado para investigación reproducible.

Finsport pasa a poseer la identidad canónica de:

- `Competition`;
- `Season`;
- `Team`;
- `Match`;
- `Bookmaker`;
- `OddsMarket`;
- `OddsSnapshot`.

Las fuentes externas se vinculan mediante:

- `CompetitionSourceRef`;
- `TeamSourceRef`;
- `MatchSourceRef`.

No existe `SeasonSourceRef` en este incremento.

API-Football queda como fuente primaria y autoritativa para creación/actualización de entidades canónicas, kickoff, estado, scores y outcome. Inkabet queda como fuente secundaria read-only de cuotas actuales 1X2 (`MW3W`) y nunca crea entidades canónicas por sí sola.

El flujo legacy de scraping/browser/apuestas reales fue retirado del repositorio y runtime:

- `accounts` eliminado;
- Scrapy eliminado;
- Selenium eliminado;
- spiders/pipelines legacy eliminados;
- comandos legacy de betting eliminados;
- `bet.tasks`/ciclo automático eliminado;
- configuración/dependencias asociadas eliminadas.

Celery y Redis permanecen como infraestructura general. `BetTable` y `BetRow` permanecen sólo como estructuras pasivas de investigación histórica, sin flujo ejecutable de apuestas.

---

## 2. Decisiones de dominio cerradas

### 2.1. Identidad canónica

Los IDs de proveedor no forman parte de la identidad de negocio de Competition, Team, Season o Match.

La reconciliación debe persistir explicitamente la relación entre identidad externa e identidad canónica mediante SourceRefs.

### 2.2. Team y Competition

Para la etapa analítica actual de Finsport, cada `Team` pertenece a una única `Competition` doméstica rastreada. Esto representa el contexto analítico elegido por Finsport, no todas las competiciones reales en las que un club pueda participar.

Esta decisión fue confirmada por el maintainer durante FS-002 y debe reconciliarse en F002/F003 donde todavía exista la recomendación histórica de no asumir esa cardinalidad.

### 2.3. Season

`Season` pertenece a `Competition` y conserva:

- `year`;
- `start_date`;
- `end_date`;
- `is_current`;
- `coverage`.

La metadata viene del catálogo `/leagues`; fixture ingestion no inventa temporadas ni crea una `Season` desconocida.

### 2.4. Match

La identidad canónica de Match se apoya en:

```text
Season / Competition
+ home Team
+ away Team
+ kickoff
```

El modelo separa:

- lifecycle/status del partido;
- outcome deportivo;
- scores;
- cualquier estado histórico de `BetRow`.

### 2.5. Odds

`OddsSnapshot` es, pese al nombre histórico elegido, almacenamiento de **valor actual**, no serie temporal:

```text
1 row
per Match / Source / Bookmaker / Market
```

Una observación posterior actualiza HOME/DRAW/AWAY y timestamps en la misma fila.

La UAT confirmó que las cuotas pueden cambiar entre llamadas; por ejemplo Inkabet HOME pasó de 1.31 a 1.30 mientras DRAW/AWAY permanecieron 5.25/9.70. Ese comportamiento es correcto bajo latest-value storage.

---

## 3. API-Football — contrato implementado

Cliente read-only GET con:

- key sólo en header `x-apisports-key`;
- timeout explícito;
- retries acotados;
- pacing secuencial;
- paginación acotada;
- accounting de llamadas;
- accounting de quota headers;
- manejo explícito 401/403/429;
- error sanitizado para restricciones del plan Free;
- reserva diaria configurable, actualmente default `0`.

No se persiste ni imprime la key.

### 3.1. Comandos

`sync_football_catalog`

- consulta `/leagues`;
- consulta `/odds/bets`;
- actualiza Competition/Season;
- crea refs API-Football resueltas;
- deja nuevas Competitions deshabilitadas;
- resuelve el mercado `Match Winner`.

`sync_football_season <competition-id> <provider-year>`

- exige Competition conocida;
- exige Season previamente conocida por catálogo;
- usa fixtures del proveedor para Team/Match identity;
- no llama rutinariamente `/teams`;
- falla claramente si el plan no cubre esa temporada.

`sync_football_day --date YYYY-MM-DD [--with-odds]`

- hace una consulta global por fecha con `timezone=America/Lima`;
- filtra localmente por `Competition.enabled`;
- crea/actualiza Teams y Matches mediante refs API-Football;
- con odds, consulta Match Winner por fixture relevante cuando la Season declara coverage de odds;
- integra Inkabet sólo después de tener el conjunto canónico de Matches aceptado por la ejecución.

### 3.2. Comportamiento Free observado en vivo

El plan Free observado durante FS-002 no tiene una política uniforme por endpoint/año:

- `/leagues` funciona;
- `/odds/bets` funciona;
- consultas de temporada actual específicas pueden devolver `Free plans do not have access to this season`;
- una consulta global del día actual `/fixtures?date=...&timezone=America/Lima` sí funcionó;
- `/odds?fixture=<id>` para un fixture actual sí funcionó;
- una consulta global de odds por fecha resultó costosa en páginas, por lo que el flujo rutinario usa odds por fixture.

No inferir que “Free no soporta 2026” como regla universal: el acceso depende del endpoint/forma de consulta.

### 3.3. UAT final API-Football

Fixture real usado para UAT:

```text
API fixture: 1570340
Real Madrid vs Real Sociedad
kickoff: 2026-08-26 19:00:00+00:00
```

La llamada final del day sync reportó:

```text
calls=2
daily_remaining=92
error=none
```

Se persistieron cuotas Match Winner de múltiples bookmakers API-Football, entre ellos 10Bet, 1xBet, 888Sport, Bet365, Betano, Betfair, BetVictor, Dafabet, Marathonbet, Pinnacle, SBO, Superbet, Unibet y William Hill.

---

## 4. Inkabet — contrato real descubierto

FS-002 abandona Selenium/Scrapy para Inkabet y usa únicamente JSON read-only del frontend sportsbook.

Endpoints observados:

```text
GET /api/sb/v1/widgets/categories/v2
GET /api/sb/v1/widgets/accordion/v1?eventId=<id>&groupableId=MW3W
```

### 4.1. Diagnóstico CloudFront / Maintenance Page

Durante UAT, Inkabet devolvía intermitentemente:

```text
HTTP 500
server: AmazonS3
body: Maintenance Page
```

mientras el navegador obtenía:

```text
HTTP 200
server: Microsoft-IIS/10.0
CloudFront POP: LIM50-P1
```

Se demostró que:

- no era necesario Selenium;
- no era necesario autenticarse;
- no era necesario un `sessionToken`;
- no era necesaria una cookie;
- no era necesario Sentry context;
- no era necesario hardcodear una IP CloudFront;
- no era necesario copiar todo el set de browser headers.

Un problema reproducible era `Accept-Encoding`: el `requests` default anunciaba `gzip, deflate` y podía seleccionar una variante de CloudFront que devolvía Maintenance Page. El cliente actual suprime `Accept-Encoding` explícitamente.

La investigación de headers, usando cache-busters para evitar falsos positivos, redujo el contrato `x-sb-*` al único header necesario observado:

```text
x-sb-type: b2b
```

Por tanto el contrato mínimo validado del cliente es:

```text
brandId: <config local>
marketCode: <config local>
x-sb-type: b2b
Accept-Encoding: suprimido
```

No deben incorporarse:

- session tokens;
- cookies;
- browser impersonation;
- Referer/User-Agent especiales;
- IPs CloudFront fijadas;
- Selenium/Scrapy.

`brandId` y `marketCode` son configuración local; no son secretos de sesión y sus valores reales no deben documentarse ni commitearse.

### 4.2. Payload real de categories

El payload real demostró que un evento puede aparecer con el ID como **clave del diccionario**, no sólo como campo interno:

```text
"f-...": {
    "label": ...,
    "startDate": ...,
    "participants": ...
}
```

El parser fue corregido para indexar ambos formatos.

También se demostró:

```text
participants.side = 1
→ home

participants.side = 2
→ away
```

No se debe depender de concatenar/splitear el nombre completo del evento para identificar el Match, aunque el label quede persistido como evidencia externa.

### 4.3. MW3W

Sólo se acepta el mercado abierto `MW3W` y las selecciones estrictas:

```text
HOME
DRAW
AWAY
```

Cualquier shape incompleto/inesperado se descarta sin inventar precios.

### 4.4. UAT final Inkabet

Evento real:

```text
f-wE3fnIV1BkqYltgAHLoVhg
Real Madrid - Real Sociedad
```

El cliente real pasó:

```text
categories → HTTP 200
MW3W      → HTTP 200
CALLS     → 2
```

La ejecución final persistió:

```text
source=inkabet
bookmaker=Inkabet
market=Match Winner
HOME=1.3000
DRAW=5.2500
AWAY=9.7000
```

---

## 5. Reconciliación multi-source

### 5.1. Principio

API-Football crea la identidad canónica. Inkabet sólo intenta mapear sus IDs a entidades ya conocidas.

`PENDING` significa:

> el evento/ref es relevante para el conjunto canónico procesado, pero no puede reconciliarse de forma segura/unívoca.

No significa:

> el proveedor devolvió cualquier evento futuro de una competición conocida.

### 5.2. Algoritmo final de Match

La reconciliación final opera como una búsqueda encadenada:

```text
canonical Match set aceptado por sync_football_day
↓
country + kickoff window
↓
CompetitionSourceRef
↓
Competition canónica
↓
home Team dentro de esa Competition
↓
away Team dentro de esa Competition
↓
exact home/away orientation
↓
kickoff ±30 minutos
↓
restringir al accepted Match set
↓
exactamente 1 candidato
→ RESOLVED
```

`external_label` es evidencia; no participa como identidad combinada del partido.

### 5.3. Finding UAT: futuros irrelevantes

La primera implementación pasaba sólo las Competitions relevantes a `reconcile_categories()`.

Consecuencia observada:

- el daily sync tenía un único Match relevante del día;
- `categories/v2` devolvía además futuros partidos de La Liga;
- 12 eventos futuros fueron creados erróneamente como `MatchSourceRef PENDING`.

La corrección final cambia el scope a los **Matches canónicos aceptados por la ejecución actual**.

Eventos fuera del conjunto relevante:

```text
→ ignored
→ no SourceRef
→ no PENDING
```

Un evento realmente relevante pero ambiguo/no resoluble sigue creando `PENDING`, y existe cobertura de regresión para ambos comportamientos.

### 5.4. Resultado final

Después del cleanup de los refs creados por la versión incorrecta y de la UAT final:

```text
INKABET_PENDING_TOTAL=0
```

Para el Match de UAT:

```text
api_football 1570340 RESOLVED
inkabet f-wE3fnIV1BkqYltgAHLoVhg RESOLVED
```

El day sync final reportó:

```text
pending_competitions=0
pending_teams=0
pending_matches=0
inkabet_calls=2
inkabet_errors=0
error=none
```

No apareció `RECONCILIATION_REQUIRED`.

### 5.5. Observabilidad de PENDING

Cuando sí exista reconciliación pendiente, el warning debe incluir:

- counts de Competition/Team/Match;
- el/los modelos concretos del Django Admin;
- instrucción de filtrar por source + reconciliation status.

No imprimir una lista ruidosa de todos los IDs en terminal.

---

## 6. Country mapping y django-countries

FS-002 inicialmente estuvo cerca de volver a implementar una tabla general de países. La revisión brownfield confirmó que `django-countries` ya era una abstracción útil del proyecto y debe seguir siendo la fuente principal.

Dependencia final:

```text
django-countries==9.0.0
```

Responsabilidades:

```text
provider anomaly explícita
→ override mínimo

nombre normal EN/ES
→ django-countries countries.by_name(...)

slug/nombre localizado sin acentos
→ normalización contra nombres traducidos de django-countries

provider/ISO code válido
→ fallback validado
```

Ejemplos probados:

```text
Spain / España / espana → ES
Brazil / Brasil         → BR
Denmark / Dinamarca     → DK
```

Overrides específicos de proveedor conservados:

```text
Congo-DR → CD
Crimea   → ""  (no mapear a canonical country)
```

También se conservan las distinciones domésticas históricas relevantes para fútbol mediante `COUNTRIES_OVERRIDE`, por ejemplo England/Scotland/Wales/Northern Ireland.

Aprendizaje brownfield:

> antes de sustituir una librería/abstracción existente por datos custom, reconstruir qué problema resolvía y quién consume sus semánticas. Equivalencia funcional parcial no demuestra que la abstracción sea prescindible.

---

## 7. Fail-soft de Inkabet

API-Football es autoritativa y sus fallos materiales pueden hacer fallar el comando.

Inkabet es secundaria. Su fallo no debe destruir el valor ya obtenido de API-Football.

Comportamiento final:

```text
categories failure
→ INKABET_DEGRADED
→ detener sólo rama Inkabet
→ preservar fixtures/API odds
→ command error=none

MW3W failure de un evento
→ INKABET_DEGRADED event=<id>
→ continuar otros eventos
→ preservar datos API
→ command error=none
```

El summary expone:

```text
inkabet_calls=<n>
inkabet_errors=<n>
```

sin filtrar payloads sensibles ni HTML completo de error.

La UAT final dio:

```text
inkabet_errors=0
```

---

## 8. Admin

El Django Admin expone superficies operativas para:

- Competition enable/disable;
- Source;
- Season;
- Team;
- Match;
- CompetitionSourceRef;
- TeamSourceRef;
- MatchSourceRef;
- Bookmaker;
- OddsMarket;
- OddsSnapshot.

Los SourceRefs incluyen filtros por:

```text
source
reconciliation_status
```

Esto es la superficie humana para revisar PENDING reales.

No se implementó reconciliación interactiva dentro del comando.

---

## 9. Migraciones y reset brownfield

El ticket adopta un fresh migration graph para football en esta etapa temprana, en vez de intentar transportar la estructura legacy completa.

`football.0001_initial` crea:

- core canónico;
- exactamente tres SourceRef models;
- current-value odds uniqueness;
- `pg_trgm`;
- Sources no secretas `api_football` e `inkabet`.

El app/migration graph de `accounts` se elimina junto con sus consumidores.

El maintainer aprobó y ejecutó un reset destructivo controlado del PostgreSQL local **después de review**, reaplicó migraciones desde cero, recreó el superusuario local y verificó el Admin.

El backup histórico de producción:

- no fue restaurado sobre la DB activa;
- no fue usado como migration source;
- no fue commiteado;
- sólo se inspeccionó offline mediante tooling específico.

`makemigrations --check --dry-run` después de la UAT final reportó:

```text
No changes detected
```

---

## 10. Legacy retirado y semántica salvada

### 10.1. Componentes retirados

- `accounts`;
- credenciales/bookmaker login models;
- mail de tabla finalizada;
- `bet_scraper`;
- ProgressiveBetting spider;
- Inkabet Selenium scraper/bot;
- Livescore scraper/task;
- Scrapy runner común;
- Selenium Compose service;
- betting management commands;
- betting Celery tasks/cycle;
- dependencias Fernet/Selenium/Scrapy/CORS no usadas por el core actual.

### 10.2. Componentes preservados

- Celery;
- Redis;
- Beat con schedule vacío;
- `BetTable`;
- `BetRow`.

`BetTable`/`BetRow` quedan pasivos; no conservan métodos ejecutables de estrategia/apuesta.

### 10.3. Semántica histórica preservada para FS-003

El modelo antiguo calculaba un score de candidato a empate aproximadamente como:

```text
team_difference_score = 5 * (1 - abs(local_factor - visitor_factor) / 3)
draw_score            = 2 * draw_factor - 6
league_score          = 2 * (league.draw_percentage - 20)
                        / (max_league_draw_percentage - 20)
score                 = team_difference_score + draw_score + league_score
```

Reglas históricas de elegibilidad:

```text
reject if abs(local_factor - visitor_factor) > 3
reject unless 2.8 <= draw_factor <= 4.2
reject if league.draw_percentage < 20
reject if local_factor < 1.5 or visitor_factor < 1.5
```

Selección histórica:

```text
Match state NEW
kickoff entre now+5m y now+65m
ordenar por score
usar score mayor
```

Fórmula histórica de progresión:

```text
DEVIATION = 1
first_earn = first_row.bet_amount * (first_row.match.draw_factor - 1)

first row:
    bet_amount = account.start_bet
    inversion_amount = account.start_bet

later row:
    bet_amount = ceil(
        (first_earn * DEVIATION ** iteration + previous.inversion_amount)
        / (current_match.draw_factor - 1)
    )
    inversion_amount = previous.inversion_amount + bet_amount
```

Estas fórmulas son **research evidence**, no reglas aprobadas para el nuevo producto.

Problemas históricos observados:

- mezcla de outcome/processing/settlement en `Match.state`;
- float para dinero;
- sin bankroll/risk bound explícito;
- fuerte acoplamiento a empate;
- price snapshot único;
- no overround normalization;
- no calibration evidence;
- dependencia de ProgressiveBetting + un bookmaker;
- `MAX_ITERATION` del checkout no explica máximos observados en producción histórica.

### 10.4. Evidencia no sensible del backup histórico

Inspección offline recuperó:

| Tabla/estado | Count |
| --- | ---: |
| `football_league` | 189 |
| `football_leaguerelatedname` | 168 |
| `football_team` | 3,143 |
| `football_match` | 25,850 |
| `bet_bettable` | 736 |
| `bet_betrow` | 2,365 |
| BetRow WON | 690 |
| BetRow LOST | 1,671 |
| BetRow CURRENT | 4 |
| Maximum observed iteration | 14 |

De los 690 históricos `WON`, todos se asociaban a old `Match.state=DRAW`, pero sólo 445 tenían score almacenado consistente con empate; 235 no tenían score guardado y 10 tenían score incompatible con empate. Esto confirma que el estado histórico no era una fuente limpia de outcome deportivo.

No reproducir credenciales, cuentas, tokens ni valores privados del dump.

---

## 11. Tooling de dump histórico

`tools/inspect_legacy_dump.py` inspecciona un plain SQL dump de forma offline/textual.

Debe:

- no conectarse a DB;
- no ejecutar SQL;
- no restaurar el dump;
- ignorar secciones de auth/account sensibles;
- producir sólo counts/metadata no sensible necesaria para investigación.

El dump privado nunca debe entrar al repo ni a `tmp` versionado.

---

## 12. Operación local aprendida durante FS-002

### 12.1. Admin/runtime

Flujo heredado y confirmado de FS-001:

```text
http://localhost:8001/
→ Nginx + Django Admin normal, con static

http://localhost:8000/
→ Gunicorn/Django directo, técnico, sin servir collected static

http://localhost:8002/
→ VS Code / Django runserver debug
```

Admin está montado en `/`, no `/admin/`.

### 12.2. Dev Container

Abrir el Dev Container no equivale a levantar el runtime completo.

El override de desarrollo mantiene `django-web` con un proceso de espera; no arranca automáticamente:

- HTTP normal;
- Nginx;
- Celery worker;
- Beat.

Para Admin normal usar `make up`; para debugging usar el launch que ejecuta Django en `8002`.

Este aprendizaje debe quedar reflejado en F004/F009 para evitar diagnosticar como caída de servicio lo que en realidad es el comportamiento deliberado del Dev Container.

### 12.3. `.env`

No usar `source .env` como mecanismo de inspección/ejecución en este proyecto: valores con metacaracteres de shell pueden interpretarse y además aumenta el riesgo de imprimir secretos accidentalmente.

Para probes usar:

- Docker Compose env;
- `django.conf.settings` dentro de `manage.py shell`;
- variables concretas nunca impresas.

---

## 13. Organización de provider code

Durante la última correction se revisó si mover:

```text
football/api_football.py
football/api_inkabet.py
football/inkabet.py
```

hacia un package dedicado de integrations/providers.

No se hizo el refactor.

Motivo:

- transport clients tienen frontera reconocible;
- Inkabet parsing/workflow está separado;
- reconciliation cross-provider ya está separado;
- `sync.py` concentra canonical sync;
- con sólo dos providers, mover ahora agregaba import churn sin reducir materialmente complejidad/riesgo.

Reevaluar cuando aparezca un tercer provider, crecimiento fuerte de cada adapter o necesidad concreta de una API interna común.

No crear abstracciones para providers hipotéticos.

---

## 14. Evidencia automatizada final

Evidencia acumulada relevante:

- focused PostgreSQL tests durante la implementación;
- `django-countries` regression coverage;
- API-Football client tests;
- Inkabet requests client tests;
- real-payload parser regression tests;
- daily reconciliation scope tests;
- relevant-but-unresolvable PENDING test;
- fail-soft Inkabet command tests;
- command/idempotency coverage;
- fresh migration graph sobre PostgreSQL;
- `pg_trgm`;
- package/dependency cleanup;
- residual-path cleanup;
- secret-safe error reporting.

Última suite focalizada después de las corrections manuales:

```text
67 passed in 1.37s
```

Migration drift final:

```text
No changes detected
```

El primer intento del último general gate se detuvo únicamente porque Black pidió reformatear:

```text
football/api_inkabet.py
football/tests/test_commands.py
```

No fue un fallo funcional. Esos dos archivos se formatean y luego se repite el general gate exactamente una vez.

Resultado del gate inmediatamente previo al commit:

```text
FINAL_MAKE_CHECK_RESULT=PASS
FINAL_GIT_DIFF_CHECK_RESULT=PASS
```

No commitear este feedback si cualquiera de esos gates falla.

---

## 15. UAT final

### 15.1. API-Football

PASS.

Se confirmó fixture, MatchSourceRef, Match Winner odds, quotas y ausencia de error.

### 15.2. Inkabet transport

PASS.

Con DNS normal, sin IP forzada:

```text
categories HTTP 200
MW3W HTTP 200
server Microsoft-IIS/10.0
POP LIM50-P1
Accept-Encoding no enviado
```

### 15.3. Inkabet parser/reconciliation

PASS.

El evento real produjo:

```text
external_label='Real Madrid - Real Sociedad'
kickoff=2026-08-26 19:00 UTC
home_name='Real Madrid'
away_name='Real Sociedad'
```

`espana` resolvió a `ES`.

Competition ref y Match ref resolvieron correctamente.

### 15.4. Day sync final

PASS.

```text
created=0
updated=1
unchanged=33
skipped=348
pending_competitions=0
pending_teams=0
pending_matches=0
calls=2
inkabet_calls=2
inkabet_errors=0
daily_remaining=92
error=none
```

### 15.5. DB final

PASS.

```text
MATCH=1 Real Madrid vs Real Sociedad 2026-08-26 19:00:00+00:00

SOURCE_REFS
api_football 1570340 RESOLVED
inkabet f-wE3fnIV1BkqYltgAHLoVhg RESOLVED
```

Se observaron odds actuales de ambas fuentes.

### 15.6. Pending cleanup

PASS.

Los 12 PENDING falsos generados por la implementación anterior fueron limpiados antes de la UAT final.

Verificación final:

```text
INKABET_PENDING_TOTAL=0
```

---

## 16. Seguridad y side effects

Durante FS-002:

- no se realizó una apuesta real;
- no se autenticó contra bookmaker;
- no se usó Selenium para UAT;
- no se reintrodujo un ciclo de betting;
- no se restauró el dump histórico;
- no se commitearon provider keys;
- no se commitearon tokens/cookies/session data;
- IPs CloudFront usadas para diagnóstico no se fijan en código;
- los requests a Inkabet son GET-only;
- los requests a API-Football son GET-only.

El reset de la DB local fue una acción explícita del maintainer, controlada y aprobada por el ticket; no fue ejecutada por Codex.

---

## 17. Findings y corrections relevantes

### 17.1. Timezone / season discipline

Corrections anteriores fijaron:

- `America/Lima` para el day query;
- manejo de medianoche;
- odds sólo si `Season.coverage["odds"]` es true;
- fixture ingestion no crea Season;
- season/day rechazan Season desconocida;
- catálogo sigue siendo authoritative.

### 17.2. django-countries

Se actualizó a 9.0.0 y se eliminó duplicación innecesaria de aliases generales.

### 17.3. Inkabet HTTP

Se reemplazó la hipótesis inicial de “endpoint caído” por un contrato reproducible basado en evidencia:

- variante CloudFront/Accept-Encoding;
- header `x-sb-type=b2b`;
- no browser/session state.

### 17.4. Inkabet payload

Se corrigió:

- event ID como dictionary key;
- `startDate`;
- `participants.side`;
- parsing de label sólo como fallback/evidencia.

### 17.5. Daily reconciliation scope

Se corrigió la creación de PENDING para eventos futuros irrelevantes restringiendo reconciliation al accepted Match set de la ejecución.

### 17.6. Reconciliation warning

Se reemplazó el warning genérico por counts y Admin models concretos.

### 17.7. Secondary-provider fail-soft

Inkabet no aborta el valor primario ya persistido de API-Football.

### 17.8. Summary typo/debt

Se alineó el summary con `inkabet_errors` plural y se añadió regresión para categories/MW3W fail-soft.

---

## 18. New Work Discovered / deferred

### A. Season transition y cadence de catálogo

Decidir en trabajo futuro:

- cuándo refrescar `/leagues`;
- cómo detectar transición de temporada;
- cuándo bootstrappear nueva Season;
- promoted/relegated teams bajo la cardinalidad Team→Competition actual.

No inferir el año por calendario.

### B. Competition suitability

`Competition.enabled` sigue manual.

Investigar antes de automatizar selección de ligas:

- HOME/DRAW/AWAY distributions;
- estabilidad entre temporadas;
- competitive balance;
- sample size;
- provider coverage/completeness;
- bookmaker availability;
- implied-probability calibration;
- variance/upsets.

### C. API quota allocation

El plan Free observado obliga a tratar quota como recurso escaso.

Futuro trabajo puede investigar:

- morning discovery;
- selección de fixtures prioritarios;
- T-60/T-30/T-10/T-2;
- cuándo refrescar odds;
- cuándo conservar quota para resultados/actualizaciones.

No pertenece a FS-002.

### D. Temporal odds history

FS-002 sólo conserva current value.

Agregar historia sólo cuando una pregunta concreta de research/backtest lo requiera.

### E. Scheduler / notifications

Los comandos son manuales.

Un scheduler futuro debe diseñarse junto con:

- cadence;
- quota budget;
- pending reconciliation escalation;
- observabilidad/notificación.

### F. Provider statistics adapters

No cargar estadísticas provider-specific directamente en `Match` sin una necesidad concreta. Evaluar adapters dedicados cuando FS-003/experimentos lo requieran.

### G. Strategy / capital research

Las fórmulas legacy se conservan únicamente como hipótesis comparables.

FS-003 debe investigar, medir y comparar técnicas con el nuevo dataset canónico antes de reintroducir cualquier selección/staking logic.

---

## 19. Aprendizajes de proceso que deben actualizar fuentes

### F002

Actualizar la decisión Team→Competition según la decisión actual del maintainer y conservar la distinción entre domain analytical context y participación real multi-competition.

### F003

Registrar el core canónico multi-source final, autoridad de API-Football, Inkabet secondary odds y la decisión de no introducir todavía un providers package/refactor.

### F004

Registrar:

- flujo manual de sync;
- `.env` provider config;
- Dev Container vs runtime normal;
- endpoints 8000/8001/8002;
- reset DB como operación excepcional y maintainer-owned;
- no `source .env` para probes.

### F006

Reconciliar deferred work:

- season transition;
- competition suitability research;
- quota allocation;
- temporal odds history;
- scheduler/notifications;
- provider statistics;
- FS-003 strategy research.

No crear tickets automáticamente sólo por aparecer aquí.

### F007

Cuando FS-002 complete PR→merge→Done, el lifecycle F009/Planka tendrá una nueva ejecución end-to-end demostrada.

### F008

Mantener la regla de que research externo necesario para cerrar contracts de provider debe resolverse antes de delegar implementación correctiva a Codex cuando pueda evitar trial-and-error.

### F009

Actualizar dos aprendizajes claros:

1. **External contract before Codex correction**

```text
provider failure ambiguity
→ maintainer/chat probes external contract first
→ freeze observed contract
→ Codex receives only remaining repo delta
```

Esto evita gastar passes/tokens en ensayo-error de una API externa que puede inspeccionarse directamente.

2. **Complete diff-review must include untracked**

La guía exige que `tmp/<TICKET>_diff_review.txt` cubra todo el diff relevante, pero:

```text
git diff
```

no incluye archivos untracked.

Patrón recomendado:

```text
tracked diff
+
untracked files rendered as /dev/null → file diffs
→ one complete review artifact
```

No stagear código sólo para poder revisarlo.

3. **Tmp / feedback near close**

- `tmp` no es repo content;
- no pedir a Codex cambios documentales sólo para mantener tmp;
- el feedback final se reconcilia una sola vez después de implementation + corrections + UAT;
- no crear commits documentales intermedios.

---

## 20. Final disposition

Después de sustituir los dos markers del gate por `PASS`, FS-002 queda:

```text
implementation              PASS
brownfield cleanup          PASS
fresh migrations            PASS
API-Football live UAT       PASS
Inkabet live UAT            PASS
reconciliation UAT          PASS
country mapping             PASS
focused tests               PASS
migration drift             PASS
general repo gate           PASS
git diff check              PASS
financial side effects      NONE
```

Siguiente lifecycle:

```text
commit
→ push branch
→ Pull Request to master
→ GitHub CI + Codex review
→ sólo corregir findings reales atribuibles al delta
→ merge
→ cleanup
→ Planka Done
→ handoff al chat principal
```

No quedan blockers de implementación conocidos antes del PR, sujeto a que el último general gate pase después del formatting correction.
