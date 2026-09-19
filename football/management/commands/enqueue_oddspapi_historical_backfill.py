from django.core.management.base import BaseCommand, CommandError

from finsport.celery import app
from football.experiments.provider import OddsPapiClient
from football.experiments.spec import ExperimentSpec
from football.experiments.storage import canonical, local_spec_path, require_dev


class Command(BaseCommand):
    help = "Manually enqueue one research backfill in finsport-dev; never scheduled."

    def add_arguments(self, parser):
        parser.add_argument("--spec")
        parser.add_argument("--pilot", action="store_true")
        parser.add_argument("--allow-network", action="store_true")
        parser.add_argument("--account-only", action="store_true")

    def handle(self, *args, **options):
        try:
            require_dev()
            if not options["allow_network"]:
                raise ValueError("Explicit --allow-network is required")
            if options["account_only"]:
                self.stdout.write(canonical(OddsPapiClient().account()))
                return
            if not options["spec"]:
                raise ValueError("--spec required")
            path = local_spec_path(options["spec"])
            spec = ExperimentSpec.load(path)
            if options["pilot"] and spec.data["competition_ids"] != [1278]:
                raise ValueError("Pilot requires La Liga-only spec")
            result = app.send_task(
                "football.experiments.oddspapi_historical_backfill",
                args=[str(path)],
                kwargs={"pilot": options["pilot"]},
                queue="finsport.local.safe",
            )
            self.stdout.write(
                canonical(
                    {"task_id": result.id, "spec_id": spec.id, "status": "PENDING"}
                )
            )
        except (ValueError, OSError) as error:
            raise CommandError(str(error)) from None
