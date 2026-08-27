import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from football.capital.contracts import CapitalInputError
from football.capital.service import run_capital_experiment
from football.models import PredictionExperiment


class Command(BaseCommand):
    help = "Evaluate simulation-only capital policies over one FS-003 Decision stream."

    def add_arguments(self, parser):
        parser.add_argument("--prediction-experiment", required=True, type=int)
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument("--model-code")
        source.add_argument("--comparator-code")
        parser.add_argument("--model-variant", default="")
        parser.add_argument("--decision-policy", required=True)
        parser.add_argument("--decision-variant", default="")
        parser.add_argument("--config", required=True)

    def handle(self, *args, **options):
        try:
            prediction_experiment = PredictionExperiment.objects.get(
                pk=options["prediction_experiment"]
            )
        except PredictionExperiment.DoesNotExist as error:
            raise CommandError("PredictionExperiment does not exist.") from error
        try:
            config = _load_config(options["config"])
            experiment = run_capital_experiment(
                prediction_experiment=prediction_experiment,
                source_model_code=options.get("model_code") or "",
                source_model_variant=options["model_variant"],
                source_comparator_code=options.get("comparator_code") or "",
                decision_policy_code=options["decision_policy"],
                decision_policy_variant=options["decision_variant"],
                config=config,
            )
        except (CapitalInputError, json.JSONDecodeError, OSError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            self.style.SUCCESS(
                f"capital_experiment={experiment.id} mode={experiment.mode} "
                f"input={experiment.input_count} hash={experiment.input_hash}"
            )
        )
        self.stdout.write(json.dumps(experiment.summary, indent=2, sort_keys=True))


def _load_config(value):
    if value.lstrip().startswith("{"):
        return json.loads(value)
    return json.loads(Path(value).read_text())
