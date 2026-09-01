import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from football.maintenance import run_periodic_maintenance


class Command(BaseCommand):
    help = "Run pipeline-owned daily/weekly experimental maintenance when due."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force-weekly",
            action="store_true",
            help="Evaluate weekly work now while preserving same-day idempotency.",
        )

    def handle(self, *args, **options):
        result = run_periodic_maintenance(
            at=timezone.now(), force_weekly=options["force_weekly"]
        )
        self.stdout.write(json.dumps(result, indent=2, sort_keys=True, default=str))
