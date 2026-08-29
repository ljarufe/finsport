from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from football.models import Match, Prediction, PredictionExperiment
from football.sync import FINISHED_STATUSES

from .evaluation import refresh_experiment_summary


@dataclass(frozen=True)
class SettlementResult:
    status: str
    prediction_ids: tuple[int, ...] = field(default_factory=tuple)
    experiment_ids: tuple[int, ...] = field(default_factory=tuple)
    evaluated_at: object | None = None
    dry_run: bool = False

    def as_dict(self):
        return {
            "status": self.status,
            "prediction_ids": list(self.prediction_ids),
            "prediction_count": len(self.prediction_ids),
            "experiment_ids": list(self.experiment_ids),
            "experiment_count": len(self.experiment_ids),
            "evaluated_at": (
                self.evaluated_at.isoformat() if self.evaluated_at else None
            ),
            "dry_run": self.dry_run,
        }


@transaction.atomic
def settle_prospective_predictions(*, competition_ids=None, dry_run=False):
    valid_outcomes = [value for value, _ in Match.OUTCOMES]
    queryset = Prediction.objects.filter(
        experiment__mode=PredictionExperiment.MODE_PROSPECTIVE,
        actual_outcome__isnull=True,
        match__status_short__in=FINISHED_STATUSES,
        match__outcome__in=valid_outcomes,
    ).select_related("match")
    if competition_ids is not None:
        queryset = queryset.filter(experiment__competition_id__in=competition_ids)
    if not dry_run:
        queryset = queryset.select_for_update()
    predictions = list(queryset.order_by("id"))
    prediction_ids = tuple(row.pk for row in predictions)
    experiment_ids = tuple(sorted({row.experiment_id for row in predictions}))
    if not predictions:
        return SettlementResult(status="NO_WORK", dry_run=dry_run)
    if dry_run:
        return SettlementResult(
            status="SKIPPED",
            prediction_ids=prediction_ids,
            experiment_ids=experiment_ids,
            dry_run=True,
        )

    evaluated_at = timezone.now()
    for prediction in predictions:
        prediction.actual_outcome = prediction.match.outcome
        prediction.evaluated_at = evaluated_at
    Prediction.objects.bulk_update(predictions, ["actual_outcome", "evaluated_at"])
    for experiment in PredictionExperiment.objects.filter(pk__in=experiment_ids):
        refresh_experiment_summary(experiment)
    return SettlementResult(
        status="SUCCESS",
        prediction_ids=prediction_ids,
        experiment_ids=experiment_ids,
        evaluated_at=evaluated_at,
    )
