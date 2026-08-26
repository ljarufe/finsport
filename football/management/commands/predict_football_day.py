from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from football.prediction.service import predict_day


class Command(BaseCommand):
    help = "Persist FS-003 predictions and shadow decisions for one local day."

    def add_arguments(self, parser):
        parser.add_argument("--date", required=True)
        parser.add_argument("--cutoff")

    def handle(self, *args, **options):
        try:
            day = date.fromisoformat(options["date"])
        except ValueError as error:
            raise CommandError("Date must use YYYY-MM-DD format.") from error
        cutoff = parse_datetime(options["cutoff"]) if options["cutoff"] else None
        if options["cutoff"] and cutoff is None:
            raise CommandError("Cutoff must be an ISO datetime.")
        experiments = predict_day(day, cutoff)
        totals = {
            "experiments": len(experiments),
            "predictions": sum(item.predictions.count() for item in experiments),
            "decisions": sum(item.decisions.count() for item in experiments),
        }
        self.stdout.write(self.style.SUCCESS(str(totals)))
