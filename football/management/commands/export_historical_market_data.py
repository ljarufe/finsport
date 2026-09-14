import json

from django.core.management.base import BaseCommand

from football.historical_market.package import export_package


class Command(BaseCommand):
    help = "Export the scoped FS-015 dev-to-operational data package."

    def add_arguments(self, parser):
        parser.add_argument(
            "--package", default="tmp/FS-015_historical_market_data.dump"
        )
        parser.add_argument(
            "--manifest",
            default="tmp/FS-015_historical_market_data_manifest.json",
        )

    def handle(self, *args, **options):
        manifest = export_package(options["package"], options["manifest"])
        self.stdout.write(json.dumps(manifest, indent=2, sort_keys=True))
