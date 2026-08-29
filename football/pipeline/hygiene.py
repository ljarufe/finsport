from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from football.models import (
    CapitalExperiment,
    Decision,
    Match,
    OddsObservation,
    OddsSnapshot,
    Prediction,
    PredictionExperiment,
)
from football.prediction.evaluation import refresh_experiment_summary


@dataclass(frozen=True)
class CancellationHygieneResult:
    status: str
    reason: str
    match_ids: tuple[int, ...] = field(default_factory=tuple)
    prediction_experiment_ids: tuple[int, ...] = field(default_factory=tuple)
    capital_experiment_ids: tuple[int, ...] = field(default_factory=tuple)
    counts: dict = field(default_factory=dict)
    preserved: dict = field(default_factory=dict)
    dry_run: bool = False

    def as_dict(self):
        return {
            "status": self.status,
            "reason": self.reason,
            "dry_run": self.dry_run,
            "match_ids": list(self.match_ids),
            "prediction_experiment_ids": list(self.prediction_experiment_ids),
            "capital_experiment_ids": list(self.capital_experiment_ids),
            "counts": self.counts,
            "preserved": self.preserved,
            "trigger": "status_short == CANC",
        }


def _manifest_decision_ids(manifest):
    values = manifest.get("decision_ids", []) if isinstance(manifest, dict) else []
    return {str(value) for value in values if isinstance(value, (int, str))}


@transaction.atomic
def cleanup_cancelled_matches(*, match_ids=None, dry_run=False):
    matches = Match.objects.filter(status_short="CANC")
    if match_ids is not None:
        matches = matches.filter(pk__in=match_ids)
    if not dry_run:
        matches = matches.select_for_update()
    matches = list(matches.order_by("id"))
    cancelled_ids = tuple(match.pk for match in matches)

    decisions = Decision.objects.filter(match_id__in=cancelled_ids)
    predictions = Prediction.objects.filter(match_id__in=cancelled_ids)
    decision_ids = tuple(decisions.order_by("id").values_list("id", flat=True))
    decision_id_strings = {str(value) for value in decision_ids}
    prediction_ids = tuple(predictions.order_by("id").values_list("id", flat=True))
    prediction_experiment_ids = tuple(
        sorted(
            set(decisions.values_list("experiment_id", flat=True))
            | set(predictions.values_list("experiment_id", flat=True))
        )
    )
    capital_experiment_ids = tuple(
        experiment.pk
        for experiment in CapitalExperiment.objects.only("id", "input_manifest")
        if _manifest_decision_ids(experiment.input_manifest) & decision_id_strings
    )
    snapshot_count = OddsSnapshot.objects.filter(match_id__in=cancelled_ids).count()
    observation_count = OddsObservation.objects.filter(
        match_id__in=cancelled_ids
    ).count()
    counts = {
        "matches": len(cancelled_ids),
        "odds_snapshots": snapshot_count,
        "odds_observations": observation_count,
        "predictions": len(prediction_ids),
        "decisions": len(decision_ids),
        "capital_experiments": len(capital_experiment_ids),
    }
    preserved = {
        "matches": len(cancelled_ids),
        "match_source_refs": sum(match.source_refs.count() for match in matches),
        "capture_work_items": sum(
            match.capture_work_items.count() for match in matches
        ),
        "capture_runs": len(
            {
                run_id
                for match in matches
                for run_id in match.capture_work_items.values_list("run_id", flat=True)
            }
        ),
    }
    derivative_count = sum(
        counts[key]
        for key in (
            "odds_snapshots",
            "odds_observations",
            "predictions",
            "decisions",
            "capital_experiments",
        )
    )
    if derivative_count == 0:
        return CancellationHygieneResult(
            status="NO_WORK",
            reason="ALREADY_CLEAN",
            match_ids=cancelled_ids,
            counts=counts,
            preserved=preserved,
            dry_run=dry_run,
        )
    if dry_run:
        return CancellationHygieneResult(
            status="SKIPPED",
            reason="DRY_RUN",
            match_ids=cancelled_ids,
            prediction_experiment_ids=prediction_experiment_ids,
            capital_experiment_ids=capital_experiment_ids,
            counts=counts,
            preserved=preserved,
            dry_run=True,
        )

    CapitalExperiment.objects.filter(pk__in=capital_experiment_ids).delete()
    decisions.delete()
    predictions.delete()
    OddsObservation.objects.filter(match_id__in=cancelled_ids).delete()
    OddsSnapshot.objects.filter(match_id__in=cancelled_ids).delete()
    hygiene_record = {
        "cleaned_at": timezone.now().isoformat(),
        "match_ids": list(cancelled_ids),
        "removed": counts,
    }
    for experiment in PredictionExperiment.objects.filter(
        pk__in=prediction_experiment_ids
    ):
        refresh_experiment_summary(
            experiment,
            cancellation_hygiene=hygiene_record,
        )
    return CancellationHygieneResult(
        status="SUCCESS",
        reason="CANC_DERIVATIVES_REMOVED",
        match_ids=cancelled_ids,
        prediction_experiment_ids=prediction_experiment_ids,
        capital_experiment_ids=capital_experiment_ids,
        counts=counts,
        preserved=preserved,
    )
