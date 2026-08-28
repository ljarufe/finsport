import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from football.capture import run_capture
from football.models import CaptureWorkItem


class Command(BaseCommand):
    help = "Plan or execute bounded quota-aware temporal football capture."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--at", help="Aware ISO-8601 datetime; defaults to current time"
        )
        parser.add_argument("--match-id", type=int)
        parser.add_argument(
            "--purpose",
            choices=[value for value, _ in CaptureWorkItem.Purpose.choices],
        )
        parser.add_argument("--window")
        parser.add_argument("--max-provider-attempts", type=int)
        parser.add_argument(
            "--allow-bootstrap",
            action="store_true",
            help="Allow the configured bounded first call without a current UTC header",
        )

    def handle(self, *args, **options):
        del args
        at = timezone.now()
        if options["at"]:
            at = parse_datetime(options["at"])
            if at is None or timezone.is_naive(at):
                raise CommandError("--at must be an aware ISO-8601 datetime.")
        maximum = options["max_provider_attempts"]
        if maximum is not None and maximum < 1:
            raise CommandError("--max-provider-attempts must be positive.")
        try:
            result = run_capture(
                at=at,
                dry_run=options["dry_run"],
                match_id=options["match_id"],
                purpose=options["purpose"],
                window=options["window"],
                max_provider_attempts=maximum,
                allow_bootstrap=options["allow_bootstrap"],
            )
        except (ValueError, LookupError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps(result.as_dict(), indent=2, sort_keys=True))
