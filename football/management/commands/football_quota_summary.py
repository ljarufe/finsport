import json
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from football.quota import quota_summary


class Command(BaseCommand):
    help = "Show the provider-free FS-017 API-Football quota/reserve summary."

    def add_arguments(self, parser):
        parser.add_argument("--at", help="Aware ISO-8601 planning instant.")

    def handle(self, *args, **options):
        at = timezone.now()
        if options["at"]:
            try:
                at = datetime.fromisoformat(options["at"])
            except ValueError as error:
                raise CommandError("--at must be an ISO-8601 datetime.") from error
            if timezone.is_naive(at):
                raise CommandError("--at must include an explicit timezone offset.")
        self.stdout.write(json.dumps(quota_summary(at=at), indent=2, sort_keys=True))
