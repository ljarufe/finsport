import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import groupby

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from football.models import (
    CapitalExperiment,
    CapitalLongitudinalSeries,
    CapitalPolicyRun,
    Competition,
    Decision,
    Match,
    Prediction,
    PredictionExperiment,
)
from football.observability.events import emit_event

from .contracts import ENGINE_VERSION, CapitalDecision
from .service import run_prepared_capital_experiment

PRIMARY_SERIES_CODE = "fs010-primary-prospective-dixon-coles-modal-all"
PRIMARY_EVIDENCE_CLASS = "PROSPECTIVE"
PRIMARY_EPOCH = datetime.fromisoformat("2026-08-26T21:34:33.795715+00:00")
SOURCE_MODEL_CODE = Prediction.DIXON_COLES
DECISION_POLICY_CODE = "MODAL_ALL"

REFERENCE_POLICY_ARMS = [
    {"code": "FLAT_UNIT", "config": {"unit": "1"}},
    {
        "code": "FIXED_FRACTION_BANKROLL",
        "config": {"fraction": "0.05"},
    },
    {
        "code": "FIXED_TARGET_PROFIT_NO_RECOVERY",
        "config": {"target_profit": "1"},
    },
    {"code": "LEGACY_RECOVERY", "config": {"initial_stake": "1"}},
    {
        "code": "LEGACY_CAPPED",
        "config": {"initial_stake": "1", "max_absolute_stake": "5"},
    },
    {
        "code": "LEGACY_PARTIAL",
        "config": {"target_profit": "1", "alpha": "0.5"},
    },
    {"code": "FRACTIONAL_KELLY", "config": {"lambda": "0.25"}},
]
LONGITUDINAL_CONFIG = {
    "mode": CapitalExperiment.MODE_REPLAY,
    "initial_bankroll": "100",
    "policies": REFERENCE_POLICY_ARMS,
}


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value):
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


@dataclass(frozen=True)
class LongitudinalBasis:
    capital_decisions: tuple
    manifest: dict
    input_hash: str
    watermark: datetime | None
    first_gap: dict | None
    input_count: int
    actionable_count: int
    no_bet_count: int


@dataclass(frozen=True)
class LongitudinalResult:
    status: str
    reason: str = ""
    series_id: int | None = None
    capital_experiment_id: int | None = None
    created: bool = False
    input_hash: str = ""
    input_count: int = 0
    actionable_count: int = 0
    no_bet_count: int = 0
    epoch: str = ""
    watermark: str | None = None
    first_gap: dict | None = None
    policy_states: dict | None = None
    primary_failure_emitted: bool = False

    def as_dict(self):
        return {
            "status": self.status,
            "reason": self.reason,
            "series_id": self.series_id,
            "capital_experiment_id": self.capital_experiment_id,
            "created": self.created,
            "input_hash": self.input_hash,
            "input_count": self.input_count,
            "actionable_count": self.actionable_count,
            "no_bet_count": self.no_bet_count,
            "epoch": self.epoch,
            "watermark": self.watermark,
            "first_gap": self.first_gap,
            "policy_states": self.policy_states or {},
            "primary_failure_emitted": self.primary_failure_emitted,
            "mode": CapitalExperiment.MODE_REPLAY,
            "initial_bankroll": "100",
            "comparator": {
                "source_model_code": SOURCE_MODEL_CODE,
                "decision_policy_code": DECISION_POLICY_CODE,
            },
        }


@transaction.atomic
def initialize_primary_series():
    existing = (
        CapitalLongitudinalSeries.objects.select_for_update()
        .filter(code=PRIMARY_SERIES_CODE)
        .first()
    )
    if existing:
        return existing, False
    competition_ids = list(
        Competition.objects.select_for_update()
        .filter(enabled=True)
        .order_by("id")
        .values_list("id", flat=True)
    )
    if not competition_ids:
        return None, False
    # A concurrent first initializer may have created the singleton while this
    # transaction waited for the enabled cohort lock.
    existing = (
        CapitalLongitudinalSeries.objects.select_for_update()
        .filter(code=PRIMARY_SERIES_CODE)
        .first()
    )
    if existing:
        return existing, False
    series = CapitalLongitudinalSeries.objects.create(
        code=PRIMARY_SERIES_CODE,
        evidence_class=PRIMARY_EVIDENCE_CLASS,
        source_model_code=SOURCE_MODEL_CODE,
        decision_policy_code=DECISION_POLICY_CODE,
        frozen_competition_ids=competition_ids,
        cohort_hash=_sha256(competition_ids),
        epoch=PRIMARY_EPOCH,
        mode=CapitalExperiment.MODE_REPLAY,
        initial_bankroll=Decimal("100"),
        config=LONGITUDINAL_CONFIG,
    )
    return series, True


def _actionable_gap(decision):
    if decision.action == Decision.ACTION_NO_BET:
        return None
    valid_outcomes = {code for code, _ in Match.OUTCOMES}
    if decision.match.outcome not in valid_outcomes:
        return "MISSING_CANONICAL_OUTCOME"
    observation = decision.selected_odds_observation
    if observation is None:
        return "MISSING_SELECTED_ODDS_OBSERVATION"
    if decision.selected_price is None:
        return "MISSING_SELECTED_PRICE"
    if decision.selected_price <= 1:
        return "INVALID_SELECTED_PRICE"
    if observation.match_id != decision.match_id:
        return "SELECTED_ODDS_MATCH_MISMATCH"
    if timezone.is_naive(decision.decision_time):
        return "NAIVE_DECISION_TIME"
    if timezone.is_naive(observation.observed_at):
        return "NAIVE_ODDS_OBSERVED_AT"
    if observation.observed_at >= decision.decision_time:
        return "ODDS_NOT_BEFORE_DECISION"
    if decision.selected_price != getattr(observation, decision.action.lower()):
        return "SELECTED_PRICE_MISMATCH"
    return None


def _manifest_row(decision):
    prediction = decision.prediction
    observation = decision.selected_odds_observation
    probability = (
        Decimal(str(decision.model_probability))
        if decision.model_probability is not None
        else None
    )
    return {
        "decision_id": decision.pk,
        "decision_time": decision.decision_time.isoformat(),
        "match_id": decision.match_id,
        "competition_id": decision.experiment.competition_id,
        "action": decision.action,
        "canonical_outcome": decision.match.outcome or "",
        "model_probability": str(probability) if probability is not None else None,
        "selected_price": (
            str(decision.selected_price)
            if decision.selected_price is not None
            else None
        ),
        "odds_observation_id": decision.selected_odds_observation_id,
        "odds_observed_at": (
            observation.observed_at.isoformat() if observation else None
        ),
        "prediction": {
            "id": prediction.pk,
            "model_code": prediction.model_code,
            "model_version": prediction.model_version,
            "variant": prediction.variant,
            "model_config": prediction.model_config,
            "experiment_id": prediction.experiment_id,
            "experiment_engine_version": decision.experiment.engine_version,
        },
        "decision_policy": {
            "code": decision.policy_code,
            "version": decision.policy_version,
            "variant": decision.policy_variant,
            "config": decision.policy_config,
        },
    }


def build_longitudinal_basis(series):
    if not isinstance(series, CapitalLongitudinalSeries):
        series = CapitalLongitudinalSeries.objects.get(pk=series)
    cohort = sorted(int(value) for value in series.frozen_competition_ids)
    candidates = list(
        Decision.objects.filter(
            experiment__mode=PredictionExperiment.MODE_PROSPECTIVE,
            experiment__competition_id__in=cohort,
            prediction__model_code=series.source_model_code,
            policy_code=series.decision_policy_code,
            decision_time__gte=series.epoch,
        )
        .select_related(
            "experiment",
            "match",
            "prediction",
            "selected_odds_observation",
        )
        .order_by("decision_time", "id")
    )
    included = []
    complete_batches = []
    first_gap = None
    for batch_time, grouped in groupby(candidates, key=lambda row: row.decision_time):
        batch = list(grouped)
        gaps = [
            (row, reason)
            for row in batch
            if (reason := _actionable_gap(row)) is not None
        ]
        if gaps:
            first, reason = gaps[0]
            first_gap = {
                "decision_id": first.pk,
                "decision_time": batch_time.isoformat(),
                "reason": reason,
                "batch_decision_ids": [row.pk for row in batch],
                "match_id": first.match_id,
                "competition_id": first.experiment.competition_id,
                "action": first.action,
                "canonical_outcome": first.match.outcome or "",
                "selected_odds_observation_id": (first.selected_odds_observation_id),
                "selected_price": (
                    str(first.selected_price)
                    if first.selected_price is not None
                    else None
                ),
            }
            break
        included.extend(batch)
        complete_batches.append(
            {
                "decision_time": batch_time.isoformat(),
                "decision_ids": [row.pk for row in batch],
            }
        )
    watermark = included[-1].decision_time if included else None
    manifest_rows = [_manifest_row(row) for row in included]
    manifest = {
        "schema": "fs010-longitudinal-capital-v1",
        "series": {
            "code": series.code,
            "evidence_class": series.evidence_class,
            "source_model_code": series.source_model_code,
            "decision_policy_code": series.decision_policy_code,
            "cohort_hash": series.cohort_hash,
            "frozen_competition_ids": cohort,
            "epoch": series.epoch.isoformat(),
            "watermark": watermark.isoformat() if watermark else None,
        },
        "ordering": [
            "decision_time ASC",
            "id ASC within batch for audit/hash only",
        ],
        "batch_boundary": "equal decision_time",
        "complete_batches": complete_batches,
        "first_gap": first_gap,
        "counts": {
            "input_decisions": len(included),
            "actionable_capital_decisions": sum(
                row.action != Decision.ACTION_NO_BET for row in included
            ),
            "no_bet_decisions": sum(
                row.action == Decision.ACTION_NO_BET for row in included
            ),
        },
        "decision_ids": [row.pk for row in included],
        "rows": manifest_rows,
    }
    input_hash = _sha256(manifest)
    manifest["sha256"] = input_hash
    capital_decisions = tuple(
        CapitalDecision(
            source_id=row.pk,
            decision_time=row.decision_time,
            action=row.action,
            outcome=row.match.outcome or "",
            price=row.selected_price,
            probability=(
                Decimal(str(row.model_probability))
                if row.model_probability is not None
                else None
            ),
            observation_id=row.selected_odds_observation_id,
            observation_time=(
                row.selected_odds_observation.observed_at
                if row.selected_odds_observation
                else None
            ),
        )
        for row in included
    )
    actionable_count = sum(row.actionable for row in capital_decisions)
    return LongitudinalBasis(
        capital_decisions=capital_decisions,
        manifest=manifest,
        input_hash=input_hash,
        watermark=watermark,
        first_gap=first_gap,
        input_count=len(capital_decisions),
        actionable_count=actionable_count,
        no_bet_count=len(capital_decisions) - actionable_count,
    )


def _logical_identity(series, input_hash):
    return _sha256(
        {
            "series_code": series.code,
            "cohort_hash": series.cohort_hash,
            "epoch": series.epoch.isoformat(),
            "input_hash": input_hash,
            "engine_version": ENGINE_VERSION,
            "config": series.config,
            "source_model_code": series.source_model_code,
            "decision_policy_code": series.decision_policy_code,
        }
    )


def _context(series, basis):
    return {
        "capital_series_id": series.pk,
        "cohort_identity": series.cohort_hash,
        "cohort_count": len(series.frozen_competition_ids),
        "epoch": series.epoch.isoformat(),
        "watermark": basis.watermark.isoformat() if basis.watermark else None,
        "input_hash": basis.input_hash,
        "input_count": basis.input_count,
        "comparator": f"{series.source_model_code}+{series.decision_policy_code}",
    }


def _failure_context(series=None, basis=None):
    if isinstance(series, CapitalLongitudinalSeries):
        if basis is not None:
            return _context(series, basis)
        return {
            "capital_series_id": series.pk,
            "cohort_identity": series.cohort_hash,
            "cohort_count": len(series.frozen_competition_ids),
            "epoch": series.epoch.isoformat(),
            "comparator": (f"{series.source_model_code}+{series.decision_policy_code}"),
        }
    return {
        "comparator": f"{SOURCE_MODEL_CODE}+{DECISION_POLICY_CODE}",
        "diagnostic_excerpt": "Primary longitudinal series initialization unavailable.",
    }


def _snapshot_semantic_identity(snapshot):
    # Rows created before 0009 used logical_identity for the semantic basis.
    return snapshot.semantic_identity or snapshot.logical_identity


def _is_reusable_snapshot(snapshot):
    if snapshot.completed_at is None:
        return False
    runs = list(snapshot.policy_runs.all())
    expected_codes = {arm["code"] for arm in REFERENCE_POLICY_ARMS}
    return (
        len(runs) == len(REFERENCE_POLICY_ARMS)
        and {run.policy_code for run in runs} == expected_codes
        and all(
            run.status
            in {
                CapitalPolicyRun.STATUS_PRODUCED,
                CapitalPolicyRun.STATUS_UNAVAILABLE,
            }
            for run in runs
        )
    )


def _set_current_snapshot(series, snapshot):
    snapshot_id = snapshot.pk if snapshot is not None else None
    if series.current_snapshot_id != snapshot_id:
        series.current_snapshot = snapshot
        series.save(update_fields=["current_snapshot", "modified"])


def _matching_semantic_snapshots(series, semantic_identity):
    return list(
        CapitalExperiment.objects.filter(longitudinal_series=series)
        .filter(
            Q(semantic_identity=semantic_identity)
            | Q(semantic_identity="", logical_identity=semantic_identity)
        )
        .prefetch_related("policy_runs")
        .order_by("id")
    )


def _next_attempt_identity(semantic_identity):
    attempt = 1
    while True:
        identity = _sha256({"semantic_identity": semantic_identity, "attempt": attempt})
        if not CapitalExperiment.objects.filter(logical_identity=identity).exists():
            return identity
        attempt += 1


def _result(
    series,
    basis,
    *,
    status,
    reason="",
    experiment=None,
    created=False,
    primary_failure_emitted=False,
):
    states = {}
    if experiment is not None:
        states = {
            run.policy_code: {"status": run.status, "reason": run.reason}
            for run in experiment.policy_runs.all()
        }
    return LongitudinalResult(
        status=status,
        reason=reason,
        series_id=series.pk,
        capital_experiment_id=experiment.pk if experiment else None,
        created=created,
        input_hash=basis.input_hash,
        input_count=basis.input_count,
        actionable_count=basis.actionable_count,
        no_bet_count=basis.no_bet_count,
        epoch=series.epoch.isoformat(),
        watermark=basis.watermark.isoformat() if basis.watermark else None,
        first_gap=basis.first_gap,
        policy_states=states,
        primary_failure_emitted=primary_failure_emitted,
    )


def _recompute_serialized(series, pipeline_run_id):
    pending_error = None
    result = None
    recomputed = None
    with transaction.atomic():
        locked = CapitalLongitudinalSeries.objects.select_for_update().get(pk=series.pk)
        basis = None
        try:
            basis = build_longitudinal_basis(locked)
            semantic_identity = _logical_identity(locked, basis.input_hash)
            current = locked.current_snapshot
            if (
                current
                and _snapshot_semantic_identity(current) == semantic_identity
                and _is_reusable_snapshot(current)
            ):
                result = _result(
                    locked,
                    basis,
                    status="NO_WORK",
                    reason="UNCHANGED_SEMANTIC_BASIS",
                    experiment=current,
                )
            else:
                _set_current_snapshot(locked, None)
                if not basis.capital_decisions:
                    result = _result(
                        locked,
                        basis,
                        status="UNAVAILABLE",
                        reason="NO_COMPLETE_LONGITUDINAL_BASIS",
                    )
                else:
                    snapshots = _matching_semantic_snapshots(locked, semantic_identity)
                    reusable = next(
                        (
                            snapshot
                            for snapshot in snapshots
                            if _is_reusable_snapshot(snapshot)
                        ),
                        None,
                    )
                    if reusable is not None:
                        _set_current_snapshot(locked, reusable)
                        result = _result(
                            locked,
                            basis,
                            status="NO_WORK",
                            reason="REUSED_SEMANTIC_SNAPSHOT",
                            experiment=reusable,
                        )
                    else:
                        failure_emitted = False

                        def policy_failure(error, experiment, run):
                            nonlocal failure_emitted
                            if failure_emitted:
                                return
                            failure_emitted = True
                            context = _context(locked, basis)
                            context["policy_states"] = f"{run.policy_code}:FAILED"
                            emit_event(
                                event_code="CAPITAL_LONGITUDINAL_POLICY_FAILED",
                                severity="ERROR",
                                component="capital",
                                operation="run_prepared_capital_basis",
                                outcome="FAILED",
                                failure_kind="unexpected_policy_failure",
                                human_summary=(
                                    "A longitudinal Capital policy arm failed "
                                    "unexpectedly."
                                ),
                                exception=error,
                                pipeline_run_id=pipeline_run_id,
                                capital_experiment_id=experiment.pk,
                                context=context,
                            )

                        experiment = run_prepared_capital_experiment(
                            basis=basis.capital_decisions,
                            manifest=basis.manifest,
                            input_hash=basis.input_hash,
                            longitudinal_series=locked,
                            source_model_code=locked.source_model_code,
                            decision_policy_code=locked.decision_policy_code,
                            config=locked.config,
                            logical_identity=_next_attempt_identity(semantic_identity),
                            semantic_identity=semantic_identity,
                            policy_failure_callback=policy_failure,
                        )
                        if _is_reusable_snapshot(experiment):
                            _set_current_snapshot(locked, experiment)
                            recomputed = (experiment.pk, _context(locked, basis))
                        result = _result(
                            locked,
                            basis,
                            status="PRODUCED",
                            experiment=experiment,
                            created=True,
                            primary_failure_emitted=failure_emitted,
                        )
        except Exception as error:
            try:
                _set_current_snapshot(locked, None)
            except Exception as invalidation_error:
                error.longitudinal_invalidation_error = invalidation_error
            error.longitudinal_basis = basis
            pending_error = (error, error.__traceback__)

    if pending_error is not None:
        error, traceback = pending_error
        raise error.with_traceback(traceback)
    return result, recomputed


def recompute_longitudinal_capital(*, series=None, pipeline_run_id=None):
    try:
        series, _ = initialize_primary_series() if series is None else (series, False)
        if series is None:
            return LongitudinalResult(
                status="UNAVAILABLE",
                reason="NO_ENABLED_COMPETITIONS",
                epoch=PRIMARY_EPOCH.isoformat(),
            )
        if not isinstance(series, CapitalLongitudinalSeries):
            series = CapitalLongitudinalSeries.objects.get(pk=series)
        result, recomputed = _recompute_serialized(series, pipeline_run_id)
        if recomputed is not None:
            capital_experiment_id, context = recomputed
            emit_event(
                event_code="CAPITAL_LONGITUDINAL_RECOMPUTED",
                severity="INFO",
                component="capital",
                operation="recompute_longitudinal_capital",
                outcome="PRODUCED",
                human_summary="Longitudinal Capital evidence was recomputed.",
                pipeline_run_id=pipeline_run_id,
                capital_experiment_id=capital_experiment_id,
                context=context,
            )
        return result
    except Exception as error:
        basis = getattr(error, "longitudinal_basis", None)
        context = _failure_context(
            series if isinstance(series, CapitalLongitudinalSeries) else None,
            basis,
        )
        invalidation_error = getattr(error, "longitudinal_invalidation_error", None)
        if invalidation_error is not None:
            context["diagnostic_excerpt"] = (
                "Current snapshot invalidation also failed: "
                f"{type(invalidation_error).__name__}."
            )
        emit_event(
            event_code="CAPITAL_LONGITUDINAL_RECOMPUTE_FAILED",
            severity="ERROR",
            component="capital",
            operation="recompute_longitudinal_capital",
            outcome="FAILED",
            failure_kind="unexpected_recompute_failure",
            human_summary="Longitudinal Capital recomputation failed unexpectedly.",
            exception=error,
            pipeline_run_id=pipeline_run_id,
            context=context,
        )
        error.longitudinal_event_emitted = True
        raise
