# FS-012 — Feedback provisional pre-PR

Estado: implementación y UAT técnicamente aceptados. PR/CI/review todavía pendientes.

## Outcome implementado

FS-012 generaliza el lifecycle de readiness para Dixon-Coles, Independent Poisson y
Elo Multinomial Logit, preservando provenance y separación Prediction/Decision.

Independent Poisson y Elo quedan automáticamente utilizables en las 10 competiciones
actuales mediante 20 perfiles versionados y current, sin activación manual.

Phase A congelada:

- calibration strategy: `fs012-phase-a-season-block-v2`;
- 20/20 perfiles utilizables;
- 20 `NO_ADDITIONAL_STATISTICAL_GATE_JUSTIFIED`;
- `requirements={}` para los 20 perfiles;
- Poisson selecciona su propio `xi`;
- Elo selecciona sólo candidatos K/C finitos.

## Implementación

Incluye:

- readiness compartida y versionada;
- migración `0011_shared_model_readiness`;
- provisioning automático e idempotente;
- revalidación DB-only por cambio material de sporting/model/profile basis;
- currentness Poisson/Elo independiente de cambios exclusivamente de cuotas;
- Poisson independiente de Dixon-Coles para selección de `xi`;
- Elo all-inf → `UNAVAILABLE`, nunca ganador artificial;
- integración prospectiva Poisson/Elo con `bet_eligible`;
- Decision lifecycle preservado;
- mapping humano de `APPROVED_READINESS_PROFILE_PASSED`;
- observabilidad de CREATED/UPDATED/NO_WORK, insufficiency y unexpected failure.

## Performance finding resuelto

Pass 2 corrigió el cálculo repetido del sporting basis.

Antes:

- prospective 2 targets × 2 modelos → 4 builds;
- maintenance Poisson/Elo → 2 builds.

Después:

- prospective → 1 sporting-basis build por competition/operation;
- maintenance → 1 build compartido para Poisson/Elo.

El contexto es efímero por operación; no hay Redis, cache persistente ni cache global stale.

## Evidencia automatizada

- Pass 2 focused/regression: 79 passed.
- Full gate: 426 passed.
- Coverage: 87.07%.
- Black/Ruff/Django/migration-check/pip-check/pip-audit: PASS.
- `git diff --check`: PASS.
- Product finding de performance: RESOLVED.
- Findings materiales nuevos: ninguno.

## Migración y UAT persistente

Antes de migrar se creó:

`tmp/FS-012_pre_uat.dump`

Migración persistente:

`football.0011_shared_model_readiness` → PASS.

UAT:

- 20/20 perfiles Poisson/Elo activos/current;
- configuraciones congeladas exactas verificadas;
- provisioning automático sin Admin;
- initial full calibrations = 0;
- segunda maintenance = 20 `NO_WORK`, 0 full calibrations;
- Elo all-inf controlado → `UNAVAILABLE:NO_FINITE_ELO_HYPERPARAMETER_CANDIDATE`;
- low-evidence controlado → producible pero no bet-eligible;
- target prospectivo real: match 53550, Twente vs Telstar;
- Independent Poisson: `PRODUCED`, `bet_eligible=true`,
  `APPROVED_READINESS_PROFILE_PASSED`;
- Elo Multinomial Logit: `PRODUCED`, `bet_eligible=true`,
  `APPROVED_READINESS_PROFILE_PASSED`;
- Dixon-Coles regression: PASS;
- 10 perfiles Dixon-Coles activos/aprobados;
- `/daily/`: PASS visual para los tres arms;
- reason humano: `Perfil de preparación aprobado y satisfecho`;
- sin `Motivo no clasificado`.

El UAT de readiness fue provider-free. Para obtener un fixture prospectivo real almacenado,
Luis autorizó posteriormente una captura normal de fixtures/odds de 2026-09-08/09 mediante
los entry points existentes; esto no forma parte de calibration/revalidation y no cambia el
contrato de cero provider calls de readiness.

## Acceptance

A01–A30:

- PASS: 30
- PENDING: 0
- BLOCKED: 0

## Safety

- no bookmaker authentication;
- no wager placement;
- no real-money side effects;
- Prediction sigue separado de Decision;
- Decision sigue separado de Capital.

## Estado de cierre

Technical close: PASS.

Pendiente de cierre operativo:

- commit/push;
- PR;
- CI;
- GitHub review;
- final feedback reconciliation si aparece evidencia nueva;
- squash merge;
- cleanup;
- Planka Done;
- handoff final.
