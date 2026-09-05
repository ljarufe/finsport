import hashlib
import json
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from football.models import (
    CapitalExperiment,
    CapitalLedgerEntry,
    CapitalLongitudinalSeries,
    CapitalPolicyRun,
    Decision,
    Prediction,
    PredictionExperiment,
)

from .contracts import (
    ENGINE_VERSION,
    CapitalDecision,
    CapitalInputError,
    PolicyConfigError,
    RunUnavailable,
)
from .metrics import pareto_compare
from .policies import POLICY_VERSIONS, make_policy
from .replay import replay
from .simulation import simulate


def select_decision_basis(
    *,
    prediction_experiment,
    decision_policy_code,
    decision_policy_variant="",
    source_model_code="",
    source_model_variant="",
    source_comparator_code="",
):
    if bool(source_model_code) == bool(source_comparator_code):
        raise CapitalInputError(
            "Exactly one of source_model_code or source_comparator_code is required."
        )
    queryset = Decision.objects.filter(
        experiment=prediction_experiment,
        policy_code=decision_policy_code,
        policy_variant=decision_policy_variant,
    )
    if source_model_code:
        queryset = queryset.filter(
            prediction__isnull=False,
            prediction__model_code=source_model_code,
            prediction__variant=source_model_variant,
        )
        if source_model_code == Prediction.DIXON_COLES:
            queryset = queryset.filter(prediction__bet_eligible=True)
    else:
        if source_comparator_code != decision_policy_code:
            raise CapitalInputError(
                "Current nullable-Prediction Decisions identify their comparator by "
                "policy_code; comparator and Decision policy must match."
            )
        queryset = queryset.filter(prediction__isnull=True)
    rows = list(
        queryset.select_related(
            "match", "selected_odds_observation", "prediction"
        ).order_by("decision_time", "id")
    )
    if not rows:
        raise CapitalInputError("The selector matched no Decisions.")
    return rows


def build_input_manifest(rows):
    manifest_rows = []
    basis = []
    for decision in rows:
        observation = decision.selected_odds_observation
        probability = (
            Decimal(str(decision.model_probability))
            if decision.model_probability is not None
            else None
        )
        price = decision.selected_price
        outcome = decision.match.outcome or ""
        basis.append(
            CapitalDecision(
                source_id=decision.id,
                decision_time=decision.decision_time,
                action=decision.action,
                outcome=outcome,
                price=price,
                probability=probability,
                observation_id=decision.selected_odds_observation_id,
                observation_time=observation.observed_at if observation else None,
            )
        )
        manifest_rows.append(
            {
                "decision_id": decision.id,
                "decision_time": decision.decision_time.isoformat(),
                "match_id": decision.match_id,
                "prediction_id": decision.prediction_id,
                "action": decision.action,
                "canonical_outcome": outcome,
                "model_probability": (
                    str(probability) if probability is not None else None
                ),
                "selected_price": str(price) if price is not None else None,
                "odds_observation_id": decision.selected_odds_observation_id,
                "odds_observed_at": (
                    observation.observed_at.isoformat() if observation else None
                ),
                "decision_policy_version": decision.policy_version,
            }
        )
    encoded = json.dumps(manifest_rows, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    return (
        tuple(basis),
        {
            "ordering": [
                "decision_time ASC",
                "id ASC within batch for audit/hash only",
            ],
            "batch_boundary": "equal decision_time",
            "decision_ids": [row.id for row in rows],
            "rows": manifest_rows,
            "sha256": digest,
        },
        digest,
    )


def _validate_experiment_config(config):
    if not isinstance(config, dict):
        raise CapitalInputError("Config must be a JSON object.")
    mode = config.get("mode")
    if mode not in dict(CapitalExperiment.MODES):
        raise CapitalInputError("Config mode must be REPLAY, MONTE_CARLO, or STRESS.")
    initial_raw = config.get("initial_bankroll")
    if isinstance(initial_raw, float):
        raise CapitalInputError("initial_bankroll must be a decimal string or integer.")
    try:
        initial_bankroll = Decimal(str(initial_raw))
    except Exception as error:
        raise CapitalInputError("initial_bankroll must be a decimal value.") from error
    if not initial_bankroll.is_finite() or initial_bankroll <= 0:
        raise CapitalInputError("initial_bankroll must be positive and finite.")
    policies = config.get("policies")
    if not isinstance(policies, list) or not policies:
        raise CapitalInputError("Config policies must be a non-empty list.")
    for arm in policies:
        if not isinstance(arm, dict) or not arm.get("code"):
            raise CapitalInputError("Every policy arm requires an explicit code.")
        if not isinstance(arm.get("config"), dict):
            raise CapitalInputError(
                "Every policy arm requires an explicit config object."
            )
    if mode != CapitalExperiment.MODE_REPLAY:
        simulation = config.get("simulation")
        if not isinstance(simulation, dict):
            raise CapitalInputError("Stochastic modes require simulation config.")
        for required in ("seed", "path_count", "tail_level", "mdd_thresholds"):
            if required not in simulation:
                raise CapitalInputError(f"Simulation config requires {required}.")
        if not isinstance(simulation["seed"], int) or simulation["seed"] < 0:
            raise CapitalInputError("Simulation seed must be a non-negative integer.")
        if (
            not isinstance(simulation["path_count"], int)
            or simulation["path_count"] < 1
        ):
            raise CapitalInputError("Simulation path_count must be a positive integer.")
    if mode == CapitalExperiment.MODE_STRESS and not isinstance(
        config.get("stress"), dict
    ):
        raise CapitalInputError("STRESS mode requires an explicit stress config.")
    return mode, initial_bankroll, policies


@transaction.atomic
def run_prepared_capital_experiment(
    *,
    basis,
    manifest,
    input_hash,
    decision_policy_code,
    config,
    prediction_experiment=None,
    longitudinal_series=None,
    decision_policy_variant="",
    source_model_code="",
    source_model_variant="",
    source_comparator_code="",
    logical_identity="",
    semantic_identity="",
    policy_failure_callback=None,
):
    mode, initial_bankroll, policy_arms = _validate_experiment_config(config)
    if bool(prediction_experiment) == bool(longitudinal_series):
        raise CapitalInputError(
            "Exactly one PredictionExperiment or longitudinal series is required."
        )
    if prediction_experiment and not isinstance(
        prediction_experiment, PredictionExperiment
    ):
        prediction_experiment = PredictionExperiment.objects.get(
            pk=prediction_experiment
        )
    if longitudinal_series and not isinstance(
        longitudinal_series, CapitalLongitudinalSeries
    ):
        longitudinal_series = CapitalLongitudinalSeries.objects.get(
            pk=longitudinal_series
        )
    basis = tuple(basis)
    experiment = CapitalExperiment.objects.create(
        source_experiment=prediction_experiment,
        longitudinal_series=longitudinal_series,
        source_model_code=source_model_code,
        source_model_variant=source_model_variant,
        source_comparator_code=source_comparator_code,
        decision_policy_code=decision_policy_code,
        decision_policy_variant=decision_policy_variant,
        logical_identity=logical_identity,
        semantic_identity=semantic_identity,
        engine_version=ENGINE_VERSION,
        mode=mode,
        initial_bankroll=initial_bankroll,
        config=config,
        input_count=len(basis),
        input_hash=input_hash,
        input_manifest=manifest,
    )
    produced_metrics = {}
    statuses = {}
    simulation_config = config.get("simulation", {})
    for arm_index, arm in enumerate(policy_arms, start=1):
        code = arm["code"]
        policy_config = arm["config"]
        run = CapitalPolicyRun.objects.create(
            experiment=experiment,
            policy_code=code,
            policy_version=POLICY_VERSIONS.get(code, "unknown"),
            policy_config=policy_config,
            status=CapitalPolicyRun.STATUS_FAILED,
            seed=(simulation_config.get("seed") if mode != "REPLAY" else None),
            path_count=(
                simulation_config.get("path_count") if mode != "REPLAY" else None
            ),
        )
        run_name = f"{arm_index}:{code}"
        try:
            policy = make_policy(code, policy_config)
            run.policy_version = policy.version
            if mode == CapitalExperiment.MODE_REPLAY:
                result = replay(basis, policy, initial_bankroll)
                run.metrics = result.metrics
                CapitalLedgerEntry.objects.bulk_create(
                    [
                        CapitalLedgerEntry(
                            policy_run=run,
                            source_decision_id=row.source_id,
                            batch_time=row.batch_time,
                            batch_index=row.batch_index,
                            step=row.step,
                            requested_stake=row.requested_stake,
                            applied_stake=row.applied_stake,
                            bankroll_before=row.bankroll_before,
                            bankroll_after=row.bankroll_after,
                            profit_loss=row.profit_loss,
                            action_snapshot=row.action,
                            outcome_snapshot=row.outcome,
                            price_snapshot=row.price,
                            capital_reason=row.capital_reason,
                            policy_state=row.policy_state,
                            cap_hit=row.cap_hit,
                            shortfall=row.shortfall,
                            practical_ruin=row.practical_ruin,
                            termination_reason=row.termination_reason,
                        )
                        for row in result.ledger
                    ]
                )
            else:
                run.metrics = simulate(
                    basis,
                    policy,
                    initial_bankroll,
                    seed=simulation_config["seed"],
                    path_count=simulation_config["path_count"],
                    tail_level=simulation_config["tail_level"],
                    mdd_thresholds=simulation_config["mdd_thresholds"],
                    stress=config.get("stress") if mode == "STRESS" else None,
                )
            run.status = CapitalPolicyRun.STATUS_PRODUCED
            run.reason = ""
            produced_metrics[run_name] = run.metrics
        except RunUnavailable as error:
            run.status = CapitalPolicyRun.STATUS_UNAVAILABLE
            run.reason = error.reason
            run.metrics = {}
        except PolicyConfigError as error:
            run.status = CapitalPolicyRun.STATUS_FAILED
            run.reason = str(error)
            run.metrics = {}
        except Exception as error:  # Preserve required-arm accounting for audit.
            run.status = CapitalPolicyRun.STATUS_FAILED
            run.reason = f"{type(error).__name__}:{error}"[:120]
            run.metrics = {}
            if policy_failure_callback is not None:
                policy_failure_callback(error, experiment, run)
        run.save(
            update_fields=[
                "policy_version",
                "status",
                "reason",
                "metrics",
                "modified",
            ]
        )
        statuses[run_name] = {"status": run.status, "reason": run.reason}

    summary = {"runs": statuses}
    if produced_metrics:
        try:
            summary["pareto"] = pareto_compare(produced_metrics)
        except ValueError as error:
            summary["pareto"] = {"status": "UNAVAILABLE", "reason": str(error)}
    else:
        summary["pareto"] = {
            "status": "UNAVAILABLE",
            "reason": "NO_PRODUCED_POLICY_RUNS",
        }
    experiment.summary = summary
    experiment.completed_at = timezone.now()
    experiment.save(update_fields=["summary", "completed_at", "modified"])
    return experiment


def run_capital_experiment(
    *,
    prediction_experiment,
    decision_policy_code,
    config,
    decision_policy_variant="",
    source_model_code="",
    source_model_variant="",
    source_comparator_code="",
    logical_identity="",
):
    if not isinstance(prediction_experiment, PredictionExperiment):
        prediction_experiment = PredictionExperiment.objects.get(
            pk=prediction_experiment
        )
    source_rows = select_decision_basis(
        prediction_experiment=prediction_experiment,
        decision_policy_code=decision_policy_code,
        decision_policy_variant=decision_policy_variant,
        source_model_code=source_model_code,
        source_model_variant=source_model_variant,
        source_comparator_code=source_comparator_code,
    )
    basis, manifest, input_hash = build_input_manifest(source_rows)
    return run_prepared_capital_experiment(
        basis=basis,
        manifest=manifest,
        input_hash=input_hash,
        prediction_experiment=prediction_experiment,
        decision_policy_code=decision_policy_code,
        config=config,
        decision_policy_variant=decision_policy_variant,
        source_model_code=source_model_code,
        source_model_variant=source_model_variant,
        source_comparator_code=source_comparator_code,
        logical_identity=logical_identity,
    )
