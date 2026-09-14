import json

from django.core.management.base import BaseCommand

from football.historical_market.package import import_package


class Command(BaseCommand):
    help = "Validate or additively import the scoped FS-015 data package."

    def add_arguments(self, parser):
        parser.add_argument(
            "--package", default="tmp/FS-015_historical_market_data.dump"
        )
        parser.add_argument(
            "--manifest",
            default="tmp/FS-015_historical_market_data_manifest.json",
        )
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        result = import_package(
            options["package"], options["manifest"], apply=options["apply"]
        )
        self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
