import json

from django.core.management.base import BaseCommand, CommandError

from football.models import Competition, Season
from football.prediction.evaluation import run_backtest


class Command(BaseCommand):
    help = "Run and persist the FS-003 chronological football prediction backtest."

    def add_arguments(self, parser):
        parser.add_argument("--competition", required=True, type=int)
        parser.add_argument("--season", required=True, type=int)

    def handle(self, *args, **options):
        try:
            competition = Competition.objects.get(pk=options["competition"])
            season = Season.objects.get(competition=competition, year=options["season"])
        except Competition.DoesNotExist as error:
            raise CommandError("Competition does not exist.") from error
        except Season.DoesNotExist as error:
            raise CommandError("Season does not exist for this Competition.") from error
        if competition.competition_type != "League" or not competition.country:
            raise CommandError("Competition must be a domestic League.")
        experiment = run_backtest(competition, season)
        self.stdout.write(
            self.style.SUCCESS(
                f"experiment={experiment.id} completed predictions="
                f"{experiment.predictions.count()} decisions="
                f"{experiment.decisions.count()}"
            )
        )
        self.stdout.write(json.dumps(experiment.summary, indent=2, sort_keys=True))
