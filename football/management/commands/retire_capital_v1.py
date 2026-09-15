import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from football.capital.retirement import (
    CapitalRetirementScopeError,
    retire_v1_capital,
)


class Command(BaseCommand):
    help = "Dry-run or apply the manifest-bound FS-016 Capital v1 retirement."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--manifest",
            help="Dry-run manifest JSON required by --apply.",
        )

    def handle(self, *args, **options):
        del args
        expected = None
        if options["manifest"]:
            expected = json.loads(Path(options["manifest"]).read_text())
        if options["apply"] and expected is None:
            raise CommandError("--apply requires --manifest from a prior dry-run.")
        try:
            result = retire_v1_capital(
                expected_manifest=expected,
                apply=options["apply"],
            )
        except CapitalRetirementScopeError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps(result, indent=2, sort_keys=True, default=str))
