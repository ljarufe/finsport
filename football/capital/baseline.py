import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from football.models import (
    CapitalExperiment,
    CapitalPolicyRun,
    Decision,
    Match,
    Prediction,
    PredictionExperiment,
)
from football.sync import FINISHED_STATUSES

from .contracts import ENGINE_VERSION, CapitalInputError, RunUnavailable
from .policies import make_policy
from .replay import validate_basis
from .service import (
    build_input_manifest,
    run_capital_experiment,
    select_decision_basis,
)

BASELINE_CONFIG = {
    "mode": CapitalExperiment.MODE_REPLAY,
    "initial_bankroll": "100",
    "policies": [{"code": "FLAT_UNIT", "config": {"unit": "1"}}],
}
BASELINE_LABEL = "FS-006 normalized research comparator; not a product policy"
SOURCE_MODEL_CODE = Prediction.DIXON_COLES
DECISION_POLICY_CODE = "MODAL_ALL"


@dataclass(frozen=True)
class CapitalBaselineResult:
    prediction_experiment_id: int
    status: str
    reason: str = ""
    capital_experiment_id: int | None = None
    created: bool = False
    input_hash: str = ""

    def as_dict(self):
        return {
            "prediction_experiment_id": self.prediction_experiment_id,
            "status": self.status,
            "reason": self.reason,
            "capital_experiment_id": self.capital_experiment_id,
            "created": self.created,
            "input_hash": self.input_hash,
            "mode": CapitalExperiment.MODE_REPLAY,
            "initial_bankroll": "100",
            "policy": "FLAT_UNIT",
            "policy_config": {"unit": "1"},
            "basis": {
                "source_model_code": SOURCE_MODEL_CODE,
                "decision_policy_code": DECISION_POLICY_CODE,
            },
            "label": BASELINE_LABEL,
        }


def _identity(prediction_experiment, input_hash):
    payload = {
        "config": BASELINE_CONFIG,
        "decision_policy_code": DECISION_POLICY_CODE,
        "engine_version": ENGINE_VERSION,
        "input_hash": input_hash,
        "source_model_code": SOURCE_MODEL_CODE,
        "source_prediction_experiment_id": prediction_experiment.pk,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def run_research_baseline(prediction_experiment):
    if not isinstance(prediction_experiment, PredictionExperiment):
        prediction_experiment = PredictionExperiment.objects.get(
            pk=prediction_experiment
        )
    try:
        rows = select_decision_basis(
            prediction_experiment=prediction_experiment,
            source_model_code=SOURCE_MODEL_CODE,
            decision_policy_code=DECISION_POLICY_CODE,
        )
    except CapitalInputError:
        return CapitalBaselineResult(
            prediction_experiment_id=prediction_experiment.pk,
            status="UNAVAILABLE",
            reason="NO_SELECTED_DECISION_BASIS",
        )

    actionable = [row for row in rows if row.action != Decision.ACTION_NO_BET]
    if not actionable:
        return CapitalBaselineResult(
            prediction_experiment_id=prediction_experiment.pk,
            status="UNAVAILABLE",
            reason="NO_ACTIONABLE_DECISION_BASIS",
        )
    valid_outcomes = {value for value, _ in Match.OUTCOMES}
    if any(
        row.match.status_short not in FINISHED_STATUSES
        or row.match.outcome not in valid_outcomes
        for row in actionable
    ):
        return CapitalBaselineResult(
            prediction_experiment_id=prediction_experiment.pk,
            status="UNAVAILABLE",
            reason="UNRESOLVED_CANONICAL_OUTCOME",
        )

    basis, _, input_hash = build_input_manifest(rows)
    try:
        validate_basis(
            basis,
            make_policy("FLAT_UNIT", {"unit": "1"}),
            require_outcome=True,
        )
    except RunUnavailable as error:
        return CapitalBaselineResult(
            prediction_experiment_id=prediction_experiment.pk,
            status="UNAVAILABLE",
            reason=error.reason,
            input_hash=input_hash,
        )

    logical_identity = _identity(prediction_experiment, input_hash)
    existing = (
        CapitalExperiment.objects.filter(
            source_experiment=prediction_experiment,
            source_model_code=SOURCE_MODEL_CODE,
            source_model_variant="",
            source_comparator_code="",
            decision_policy_code=DECISION_POLICY_CODE,
            decision_policy_variant="",
            engine_version=ENGINE_VERSION,
            mode=CapitalExperiment.MODE_REPLAY,
            initial_bankroll=Decimal("100"),
            config=BASELINE_CONFIG,
            input_hash=input_hash,
            policy_runs__policy_code="FLAT_UNIT",
            policy_runs__status=CapitalPolicyRun.STATUS_PRODUCED,
        )
        .order_by("id")
        .first()
    )
    if existing:
        return CapitalBaselineResult(
            prediction_experiment_id=prediction_experiment.pk,
            status="PRODUCED",
            capital_experiment_id=existing.pk,
            created=False,
            input_hash=input_hash,
        )

    experiment = run_capital_experiment(
        prediction_experiment=prediction_experiment,
        source_model_code=SOURCE_MODEL_CODE,
        decision_policy_code=DECISION_POLICY_CODE,
        config=BASELINE_CONFIG,
        logical_identity=logical_identity,
    )
    run = experiment.policy_runs.get(policy_code="FLAT_UNIT")
    if run.status != CapitalPolicyRun.STATUS_PRODUCED:
        # Prevalidation should make this unreachable, but preserve explicit evidence.
        experiment.delete()
        return CapitalBaselineResult(
            prediction_experiment_id=prediction_experiment.pk,
            status="UNAVAILABLE",
            reason=run.reason or "BASELINE_NOT_PRODUCED",
            input_hash=input_hash,
        )
    return CapitalBaselineResult(
        prediction_experiment_id=prediction_experiment.pk,
        status="PRODUCED",
        capital_experiment_id=experiment.pk,
        created=True,
        input_hash=input_hash,
    )
