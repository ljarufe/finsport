# FS-003 — Feedback de implementación

**Ticket:** FS-003 — Construir baseline predictivo multi-modelo y evaluar HOME/DRAW/AWAY/NO_BET
**Branch:** `FS-003-predictive-baseline`
**Pass:** implementation
**Producto:** local-only / demo-only / research-oriented

## Outcome

FS-003 añade un pipeline reproducible y auditable que separa estrictamente:

```text
Prediction → P(HOME), P(DRAW), P(AWAY)
Decision   → HOME / DRAW / AWAY / NO_BET
```

Se implementaron modelos locales Dixon-Coles, Poisson independiente y Elo con logit multinomial; benchmark de consenso de mercado; comparadores Legacy y Modernized R45; policies modal, confidence y value; métricas predictivas/económicas; walk-forward diario conservador; persistencia y Admin; y comandos históricos/prospectivos sin llamadas a providers ni side effects financieros.

## Dependencias y library-first

Pins directos añadidos:

- `penaltyblog==1.12.0`
- `scikit-learn==1.9.0`

Matriz validada en Python 3.13.15:

| Capability | Library | Resultado | Reuse |
| --- | --- | --- | --- |
| Dixon-Coles | `penaltyblog.models.DixonColesGoalModel` | fit/predict H/D/A finito, no negativo, suma 1 | Sí |
| Poisson independiente | `penaltyblog.models.PoissonGoalsModel` | fit/predict H/D/A en tests sintéticos | Sí |
| Time decay | `penaltyblog.models.dixon_coles_weights` | weights por cutoff | Sí |
| De-vig | `penaltyblog.implied.calculate_implied` | multiplicative por bookmaker | Sí |
| Elo | `penaltyblog.ratings.Elo` | estado secuencial con rating inicial 1500 | Sí |
| Multinomial/binary logit | sklearn `LogisticRegression` | H/D/A y DRAW-vs-NOT_DRAW | Sí |
| Métricas | sklearn metrics + agregaciones finas | log loss, accuracy, confusion; Brier/RPS/calibration | Sí |

No se reimplementaron optimizadores, de-vig, Elo ni regresión logística. Pandas, NumPy y SciPy no se añadieron como dependencias directas ni se importan por conveniencia en código Finsport.

## Configuración exacta

- Engine: `fs003-v1`.
- Dixon-Coles: xi grid `0.0, 0.001, 0.002`; selección por menor log loss 2022→2023 y tie-break por xi menor; versión `fs003-dixon-coles-v1`.
- Poisson: reutiliza el xi elegido por Dixon-Coles; versión `fs003-independent-poisson-v1`.
- Elo-logit: K `10, 20, 40`; C `0.1, 1.0, 10.0`; initial rating 1500; home advantage 100; `StandardScaler`; `lbfgs`; `max_iter=1000`; versión `fs003-elo-multinomial-logit-v1`.
- Market consensus: multiplicative de-vig por book + mean + renormalización; versión `fs003-market-consensus-v1`.
- Modernized R45: M0–M3; C `0.1, 1.0, 10.0`; prior strength `10, 20, 40`; epsilon `1e-6`; versión `fs003-modernized-r45-v1`.
- Legacy R45: `R45-refund-stop@ef861a4897e4bfdff938e8541e8185f731ddaa5c`; sin probabilidades falsas.
- Confidence thresholds: `0.40, 0.45, 0.50, 0.55, 0.60`.
- Minimum EV: `0.00, 0.02, 0.05`, con comparación estricta `max EV > threshold`.
- Prospective fallback, sólo si aún no existe backtest completado: xi `0.001`; Elo K `20`, C `1.0`; queda auditado en Experiment como fallback, no como threshold/config productivo elegido.

## Schema y migración

Migración aditiva `football/0002`:

- `OddsObservation`: append-only, unique por Match/Source/Bookmaker/Market/observed_at e índices de consulta as-of;
- `PredictionExperiment`;
- `Prediction` con vector probabilístico validado y identity por experiment/match/model/variant;
- `Decision`, con Prediction nullable para Legacy R45 y referencia exacta a OddsObservation/precio cuando existe economics.

No existe backfill de OddsSnapshot. `OddsSnapshot` conserva su semántica latest/current. El boundary compartido `upsert_current_odds` añade una Observation con la misma respuesta ya recibida; no produce provider calls adicionales. El mismo `observed_at` se deduplica y una observación posterior con precios idénticos coexiste.

## Contrato temporal y anti-leakage

El backtest agrupa por fecha local America/Lima:

```text
TRAIN: sólo días locales anteriores
PREDICT: batch diario con estado congelado
REVEAL/UPDATE: después de persistir todo el batch
```

El target, futuros, non-FT, AET/PEN/AWD/WO y resultados del mismo día quedan excluidos. Elo captura features antes de actualizar ratings y lee probabilidades por `classifier.classes_`. Las odds usan selección estricta `observed_at < cutoff`; OddsSnapshot nunca actúa como histórico.

## Dataset sintético

- 1 League doméstica;
- 3 Seasons;
- 8 equipos por Season;
- Season 3 conserva 6 e introduce 2 nuevos;
- double round-robin: 56 FT por Season, 168 total;
- scores deterministas con HOME/DRAW/AWAY, 0-0, 1-1 y otros resultados bajos/altos;
- 4 bookmakers × 3 timestamps (T-24h, T-3h, T-30m) por match cubierto, 12 Observations;
- casos de no-market, invalid tuple, post-cutoff, provider timestamp nullable, quote idéntica en timestamps distintos, duplicate lógico mismo timestamp, best H/D/A en books distintos, DRAW value no modal, NO_BET y overround variable.

El dataset sintético sólo demuestra correctness/integration; no se usa como evidencia de rendimiento real.

## Piloto real inventariado (read-only)

Competition `1278 — La Liga`, `League`, `ES`, enabled:

- 2022: 380 FT;
- 2023: 380 FT;
- 2024: 380 FT;
- total: 1,140 FT;
- rango: 2022-08-12 → 2025-05-25;
- 24 teams;
- HOME 518 / DRAW 293 / AWAY 329.

La configuración concreta ganadora para el piloto no se inventó: será persistida por `evaluate_football_predictions` cuando el maintainer ejecute el UAT real.

## Disponibilidad real esperada

- Dixon-Coles: disponible.
- Independent Poisson: disponible.
- Elo multinomial logit: disponible.
- Market consensus histórico 2024: unavailable hasta existir OddsObservation temporal legítima.
- Modernized R45 histórico: `INSUFFICIENT_HISTORICAL_MARKET_OBSERVATIONS`.
- Legacy R45 histórico: `UNAVAILABLE_FOR_REPLAY` por `MISSING_HISTORICAL_PREKICKOFF_R45_ODDS` y `MISSING_HISTORICAL_LEAGUE_DRAW_PERCENTAGE`.

No se sustituyeron estas ausencias con OddsSnapshot actual, odds modernas, draw rate final ni datos sintéticos.

## Evidencia automatizada

- Build `django-web` con los pins nuevos: PASS.
- Focused final: 73 passed.
- `make check`: PASS; 126 passed, Black/Ruff/Django check verdes.
- Warnings: 6 DeprecationWarning internas de penaltyblog por asignación de shape con NumPy 2.5; no afectan las aserciones ni requieren custom math.
- `git diff --check`: se registra en el handoff final.
- `makemigrations --check --dry-run`: se registra en el handoff final.

## UAT y límites

No ejecutado, por ser maintainer-owned:

- aplicación de `football/0002` a PostgreSQL persistente;
- sync real posterior a la migración para acumular OddsObservation;
- backtest real La Liga 2024;
- prospective day real;
- inspección manual en Django Admin.

No se ejecutó betting, autenticación de bookmaker, Selenium, provider calls predictivos, commit, push, PR ni Planka.

## Findings disposition

- **DEFER — penaltyblog/NumPy deprecation:** evidencia: warnings internos al construir matrices de score; impacto actual: ninguno funcional; recomendación: reevaluar cuando penaltyblog publique compatibilidad limpia con NumPy 2.5, sin reemplazar la librería ni pinnear transitivas por ceremonia.
- **DEFER — simultaneous-event streak ordering:** evidencia: v1 ordena kickoff + match.id; impacto: tie-break técnico suficiente para métricas flat-unit, no para capital/recovery; recomendación: revisar sólo antes de un futuro modelo financiero.
- **DEFER — advanced models/calibration/market timing/bookmaker weighting/capital:** fuera de FS-003; no absorbidos.

Manual UAT permanece pendiente y no se declara PASS.
