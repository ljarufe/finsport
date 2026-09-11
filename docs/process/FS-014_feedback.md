# FS-014 — Final execution feedback

**Ticket:** FS-014 — Operación continua con desarrollo aislado, almacenamiento bounded y backup operacional
**Branch:** `FS-014-concurrent-runtime-dev`
**Base:** `master`
**PR:** #19
**Execution process:** F009 v1.8
**Codex passes used:** 4/4
**Status of repository implementation:** COMPLETE / REVIEWED
**Status of ticket acceptance:** PRE-MERGE; operator-owned post-merge acceptance remains

---

## 1. Resultado

FS-014 deja tres runtimes con responsabilidades separadas:

```text
finsport
→ operación estable
→ PostgreSQL durable existente
→ Redis operacional
→ Django/Celery/Beat desde imágenes desplegadas
→ sin checkout mutable en runtime final

finsport-dev
→ entorno de ticket
→ PostgreSQL/Redis/network/ports aislados
→ DB clonada desde operacional al crear
→ branch source mount
→ worker sí
→ Beat no
→ providers automáticos no
→ se mantiene vivo durante desarrollo + PR + review
→ se destruye únicamente después del merge

finsport-ci-*
→ validación efímera
→ runner-local / ticket-independent
→ PostgreSQL 17 + Redis 7 en tmpfs
→ sin puertos host
→ sin Beat
→ providers automáticos no
→ ejecuta el mismo `make check` dentro del contenedor
→ cleanup scoped obligatorio
```

El volumen operacional protegido continúa siendo:

```text
finsport_postgres_data
```

No fue recreado, reemplazado ni usado por development/CI.

---

## 2. Superficie implementada

### Operacional

- Compose project canónico: `finsport`.
- `finsport_postgres_data` declarado como volumen operacional externo/protegido.
- Django/Celery/Beat configurados para ejecutarse desde imágenes operacionales desplegadas.
- Eliminación de bind mount de checkout en la topología operacional final.
- `/healthz/` constante y DB-independent.
- `make deploy-local` con guard de branch/master limpio.
- Backup validado antes de schema/runtime changes.

### Development

- Compose project canónico: `finsport-dev`.
- Puertos congelados:
  - PostgreSQL `15432`;
  - Redis `16379`;
  - Django `18000`;
  - Nginx `18001`.
- PostgreSQL, Redis, network y volumes independientes.
- `make dev-create`:
  - fail-closed ante residuos;
  - crea stack aislado;
  - clona DB operacional;
  - aplica migraciones;
  - ejecuta `ANALYZE`;
  - verifica identidad/configuración;
  - inicia runtime.
- `make dev-up` reinicia sólo development.
- `make dev-destroy` elimina sólo recursos runtime de `finsport-dev`.
- Development no define Celery Beat.
- Capture/pipeline/Inkabet automáticos deshabilitados.

### CI reusable

Se añadió un contrato durable para todos los tickets futuros:

```text
make ci-check
```

`make ci-check`:

1. valida `FINSPORT_CI_PROJECT`;
2. exige identidad `finsport-ci-*`;
3. rechaza recursos previos del proyecto exacto;
4. construye un target CI-only de la imagen;
5. levanta PostgreSQL 17 + Redis 7 en tmpfs;
6. no publica puertos;
7. no usa `finsport` ni `finsport-dev`;
8. ejecuta el `make check` autoritativo dentro del contenedor;
9. conserva el exit status del gate;
10. limpia siempre sus recursos de forma project-scoped;
11. verifica residuo cero.

GitHub Actions usa ahora `make ci-check` y un `FINSPORT_CI_PROJECT` derivado de `github.run_id` + `github.run_attempt`.

El workflow ya no arranca ni destruye la topología operacional.

---

## 3. Passes Codex

### Pass 1/4 — implementación principal

Implementó la separación operacional/dev, lifecycle, imágenes operacionales, backup, deploy guard, systemd templates y documentación.

Validation inicial:

- focused tests PASS;
- `make check` PASS;
- Compose validation PASS;
- `git diff --check` PASS.

### Pass 2/4 — corrección UAT dev

Primer `dev-create` real expuso dos defects concretos:

```text
pg_restore
→ planner statistics no restauradas
→ ANALYZE requerido

heavy /
→ ~7 s normal
→ incorrecto como healthcheck de 2 s
```

Corrección:

- `ANALYZE` después de restore + migrations sobre DB dev revalidada;
- `/healthz/` constante y DB-independent;
- healthchecks Compose migrados a `/healthz/`.

No se reabrió arquitectura.

### Pass 3/4 — observability test identity

El pre-push full gate expuso un test reproducible acoplado a:

```text
django-web.jsonl
```

pero FS-014 development usa correctamente:

```text
OBSERVABILITY_SERVICE_NAME=django-web-dev
```

Corrección sólo de tests:

- expected JSONL derivado del setting efectivo;
- mismo fix aplicado al equivalente spool-rotation;
- product code sin cambios.

Resultado targeted:

```text
2 passed
Black PASS
Ruff PASS
git diff --check PASS
```

### Pass 4/4 — reusable CI validation contract

PR #19 expuso un P1 válido:

```text
fresh GitHub runner
→ no finsport-dev
→ host make check
→ dev-assert-ready fails
```

La corrección no debilitó el contrato local.

Se creó:

```text
make check
→ local developer gate
→ requiere finsport-dev real

make ci-check
→ CI gate
→ crea runtime disposable propio
→ ejecuta el mismo make check dentro del contenedor
```

Resultado Pass 4:

```text
focused pytest: 26 passed
Black: PASS
Ruff: PASS

real local CI simulation:
464 passed
coverage 84.61% >= 80%

CI residue:
containers=0
networks=0
volumes=0

operational:
container IDs unchanged
HTTP /healthz = 200
DB unchanged
volume = finsport_postgres_data

development:
container IDs unchanged
HTTP /healthz = 200

all Compose config --quiet: PASS
git diff --check: PASS
```

No product/business code fue modificado en Pass 4.

---

## 4. UAT/evidencia cerrada antes del merge

Demostrado en vivo:

- `finsport-dev` puede crearse desde una copia consistente de la DB operacional.
- Operational/dev migration count fue equivalente.
- Planner statistics fueron refrescadas tras restore.
- Dev-only DB mutation no apareció en operational.
- Dev-only Redis marker no apareció en operational.
- Worker/Redis networks operational/dev son distintas.
- Development Beat count = 0.
- `make dev-up` conserva development aislado.
- Operational y development respondieron simultáneamente.
- Rolling backup `latest.dump` validó.
- Restore drill aislado en tmpfs PostgreSQL pasó.
- `make dev-destroy` fue probado y produjo:
  - 0 dev containers;
  - 0 dev volumes;
  - 0 dev networks;
  - operational DB/HTTP preservados.
- Development fue recreado deliberadamente para permanecer disponible durante PR/review.
- Pass 4 CI simulation convivió con `finsport` y `finsport-dev` sin alterar ninguno.

No se realizaron provider calls para esta aceptación.

No hubo betting/auth/financial side effects.

---

## 5. Corrección del acceptance ledger de Pass 4

El ledger generado por Codex marcó prematuramente tres criterios originales como PASS.

La reconciliación correcta del execution chat es:

### A05 — PENDING

El criterio exige demostrar que cambiar source de desarrollo no altera código visible dentro de los **containers operacionales finales**.

La configuración versionada ya elimina el checkout bind, pero los containers operacionales observados durante implementation/review son anteriores al deploy FS-014.

Se cierra después de `make deploy-local` post-merge mediante prueba live de inmutabilidad.

### A10 — PENDING

El criterio exige simultáneamente:

```text
operational Beat
→ exactly one owner

dev Beat
→ absent
```

Se demostró:

```text
dev Beat = 0
```

pero el runtime operacional pre-FS-014 observado tenía `0` Beat separado.

Debe cerrarse después del deploy final comprobando exactamente un `celery-beat` operacional.

### A12 — PENDING

HTTP operacional durante development demuestra coexistencia, pero el criterio exige que el:

```text
operational scheduler/pipeline
→ remains capable of normal automatic work
```

Eso requiere la topología operacional final con Beat/pipeline habilitados.

No requiere una provider call real.

### Estado original correcto pre-merge

```text
PASS    = 11
PENDING = 9
FAIL    = 0
```

PENDING:

```text
A03
A05
A10
A12
A13
A14
A15
A17
A19
```

El sub-ledger específico de Pass 4 CI A–S sí queda:

```text
19 PASS
0 PENDING
0 FAIL
```

---

## 6. GitHub review / CI

PR #19 produjo un único finding material de Codex:

```text
P1 — Keep make check runnable in fresh CI
```

El GitHub check falló por la misma causa.

No eran dos findings independientes.

Disposición:

```text
VALID CI-INTEGRATION FINDING
→ resolved in Pass 4
→ permanent make ci-check contract
```

Después del push de Pass 4 se requiere únicamente el ciclo natural:

```text
GitHub CI
+
Codex review
```

No repetir local `make check`, UAT dev, backup drill ni complete-diff review salvo que aparezca un nuevo delta/material contradiction.

---

## 7. Lifecycle correcto para FS-015+

La secuencia estable queda:

```text
START TICKET
→ make dev-create

DEVELOP
→ use finsport-dev

LOCAL GATE
→ make check

PUSH / PR / CI / CODEX REVIEW
→ keep finsport-dev alive
→ corrections reuse same dev stack

GITHUB CI
→ make ci-check
→ disposable finsport-ci-*
→ zero dependency on developer/operational runtime

MERGE

TICKET END
→ make dev-destroy

SYNC MASTER
→ git switch master
→ git pull --ff-only

DEPLOY
→ make deploy-local
```

No destruir `finsport-dev` antes de que CI/review haya terminado.

No ejecutar cleanup global del host en cada ticket.

La limpieza global de FS-014 fue one-time.

---

## 8. Post-merge closure required

FS-014 no se declara completamente aceptado hasta ejecutar la secuencia de operador siguiente.

### 8.1 Final dev destruction — closes A13/A14

```text
make dev-destroy
→ containers=0
→ volumes=0
→ networks=0
→ operational untouched
```

### 8.2 Sync master

```text
git switch master
git pull --ff-only origin master
```

### 8.3 Real operational deployment — closes A15/A19

```text
make deploy-local
```

Debe demostrar:

```text
pre-deploy latest.dump refreshed + validated
→ before runtime/schema mutation

same finsport_postgres_data
→ preserved

latest master
→ healthy operational runtime
```

### 8.4 Operational immutability — closes A05

Después del deploy:

```text
operational Django/Celery/Beat
→ no checkout bind

temporary host/branch source mutation
→ absent inside running operational container
```

Restaurar inmediatamente el source temporal.

### 8.5 Beat + automatic-operation proof — closes A10/A12

Comprobar:

```text
operational celery-beat count = 1
dev celery-beat count = 0 / dev absent

FOOTBALL_CAPTURE_ENABLED
FOOTBALL_PIPELINE_ENABLED
INKABET_AUTOMATIC_ENABLED
→ effective operational values expected by current product/runtime
```

Demostrar process/queue capability; no provider call real es necesaria.

### 8.6 Docker BuildKit GC — closes A03

Host/operator owned:

```text
/etc/docker/daemon.json
builder.gc.enabled = true
builder.gc.defaultKeepStorage = 30GB
```

Validar config, reiniciar Docker de forma controlada y comprobar daemon/runtime sano después del restart.

No tocar particiones.

### 8.7 Weekly backup timer — closes A17

Instalar/activar user-systemd service/timer versionados.

Esperado:

```text
Monday
20:00
America/Lima
```

Comprobar enabled/active y siguiente trigger.

---

## 9. Storage result

One-time FS-014 host cleanup recuperó espacio suficiente sin tocar el volumen operacional.

Resultado observado:

```text
root free
~93 GiB
→ ~215–217 GiB

BuildKit cache
~196.9 GB
→ 0 B después del cleanup inicial

finsport_postgres_data
→ preserved
```

No se requiere repetir APT/Snap/journal/browser/pip/uv cleanup en tickets siguientes.

BuildKit daemon GC de 30 GB es el mecanismo normal futuro una vez cerrado A03.

---

## 10. Safety

FS-014 mantuvo:

```text
real betting
→ forbidden

bookmaker authentication/write
→ absent

operational DB replacement
→ forbidden

docker volume prune
→ not used

docker system prune --volumes
→ not used

partition modification
→ not used
```

Development y CI tienen automatic provider execution deshabilitado.

---

## 11. Process feedback

### Funcionó

- Máximo 4 passes fue suficiente.
- Complete-diff review detectó problemas que no debían inferirse sólo del resumen.
- UAT live encontró el missing `ANALYZE` y el healthcheck incorrecto.
- El pre-push natural encontró el observability test acoplado.
- GitHub CI + Codex review encontró el missing fresh-runner validation contract.
- Preservar `tmp/` evitó repetir evidencia cara.
- Mantener development vivo durante review evita recreación innecesaria para corrections.

### Corrección durable demostrada por FS-014

El lifecycle de ticket debe distinguir explícitamente:

```text
local development validation
!=
fresh CI validation
```

Por tanto:

```text
local make check
→ uses isolated ticket dev runtime

GitHub make ci-check
→ owns its own disposable runtime
```

También queda demostrado:

```text
dev-destroy
→ ticket END after merge
→ not pre-PR cleanup
```

Este aprendizaje es reutilizable y debe proyectarse a F009/F004 sólo cuando el chat principal haga la reconciliación durable; este feedback no sustituye esas fuentes.

---

## 12. Remaining risk / deferred conditional note

El CI actual usa GitHub-hosted runners, donde cada job dispone de un daemon Docker aislado.

La imagen CI usa un tag reutilizable fijo para evitar acumulación local.

Si en el futuro Finsport adopta runners self-hosted con **builds concurrentes compartiendo el mismo Docker daemon**, conviene revisar la estrategia de image tagging/cleanup para evitar carreras entre checkouts distintos.

No es un blocker del contrato actual ni requiere trabajo en FS-014.

---

## 13. Disposición final pre-merge

```text
repository implementation
→ COMPLETE

Pass 4 CI contract
→ ACCEPTED

complete diff review
→ PASS

known implementation defects
→ NONE

Codex budget
→ 4/4 consumed

development stack
→ KEEP RUNNING through final CI/review

merge
→ WAIT for final GitHub CI + Codex review green

post-merge operator acceptance
→ REQUIRED before FS-014 DONE
```

No debe ejecutarse una quinta pasada Codex por documentación, feedback, handoff o repetición ceremonial de checks.
