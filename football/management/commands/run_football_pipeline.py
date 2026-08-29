import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from football.pipeline import run_pipeline


class Command(BaseCommand):
    help = "Run the local-only FS-006 prospective football research pipeline."

    def add_arguments(self, parser):
        parser.add_argument(
            "--at",
            required=True,
            help="Aware ISO-8601 pipeline cutoff",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--max-provider-attempts", type=int)

    def handle(self, *args, **options):
        del args
        at = parse_datetime(options["at"])
        if at is None or timezone.is_naive(at):
            raise CommandError("--at must be an aware ISO-8601 datetime.")
        maximum = options["max_provider_attempts"]
        if maximum is not None and maximum < 1:
            raise CommandError("--max-provider-attempts must be positive.")
        try:
            result = run_pipeline(
                at=at,
                dry_run=options["dry_run"],
                max_provider_attempts=maximum,
            )
        except (ValueError, LookupError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps(result.as_dict(), indent=2, sort_keys=True))
