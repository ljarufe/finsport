"""Explicit bounded BSD identity bootstrap for later operator UAT."""

import json

from django.core.management.base import BaseCommand, CommandError

from football.models import CompetitionResultRoute
from football.providers.bsd import BSDClient, BSDError
from football.providers.bsd_bootstrap import bootstrap
from football.result_routing import effective_bsd_state


class Command(BaseCommand):
    help = "Inspect or explicitly bootstrap the frozen BSD result identities."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        if not options["execute"]:
            routes = CompetitionResultRoute.objects.order_by("competition_id")
            rows = [
                {
                    "competition_id": route.competition_id,
                    "bsd_league_ids": route.bsd_league_ids,
                    "bsd_state": route.bsd_state,
                    "effective_bsd_state": effective_bsd_state(route),
                }
                for route in routes
            ]
            self.stdout.write(json.dumps({"status": "DRY_RUN", "routes": rows}))
            return
        try:
            rows = bootstrap(client=BSDClient())
        except (BSDError, ValueError) as error:
            raise CommandError(str(error)) from None
        self.stdout.write(json.dumps({"status": "COMPLETE", "routes": rows}))
