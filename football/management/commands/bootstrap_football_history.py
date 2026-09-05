import json

from django.core.management.base import BaseCommand, CommandError

from football.historical import (
    historical_coverage_is_current,
    process_historical_bootstrap,
    request_historical_bootstrap,
)
from football.models import Competition


class Command(BaseCommand):
    help = "Run the explicit one-shot FS-011 completed-season historical bootstrap."

    def add_arguments(self, parser):
        parser.add_argument("competition_ids", nargs="*", type=int)
        parser.add_argument(
            "--reconcile-enabled",
            action="store_true",
            help="Audit/backfill every currently enabled Competition.",
        )
        parser.add_argument(
            "--request-only",
            action="store_true",
            help="Persist the activation/bootstrap request without provider acquisition.",
        )
        parser.add_argument(
            "--retry",
            action="store_true",
            help="Explicitly retry terminal non-complete coverage.",
        )

    def handle(self, *args, **options):
        ids = set(options["competition_ids"])
        if options["reconcile_enabled"]:
            ids.update(
                Competition.objects.filter(enabled=True).values_list("id", flat=True)
            )
        if not ids:
            raise CommandError("Provide Competition IDs or --reconcile-enabled.")
        competitions = list(Competition.objects.filter(pk__in=ids).order_by("pk"))
        missing = sorted(ids - {competition.pk for competition in competitions})
        if missing:
            raise CommandError(f"Unknown Competition IDs: {missing}")
        rows = []
        for competition in competitions:
            coverage = request_historical_bootstrap(
                competition,
                activate=True,
                reason=(
                    "MANUAL_RETRY_REQUESTED"
                    if options["retry"]
                    else "ACTIVATION_REQUESTED"
                ),
            )
            if not options["request_only"]:
                if (
                    historical_coverage_is_current(competition, coverage)
                    and not options["retry"]
                ):
                    pass
                else:
                    if options["retry"] and coverage.status == coverage.Status.COMPLETE:
                        coverage.status = coverage.Status.NOT_ATTEMPTED
                        coverage.save(update_fields=["status", "modified"])
                    coverage = process_historical_bootstrap(competition)
            competition.refresh_from_db()
            rows.append(
                {
                    "competition_id": competition.pk,
                    "status": coverage.status,
                    "reason": coverage.reason,
                    "required_seasons": coverage.required_seasons,
                    "covered_seasons": coverage.covered_seasons,
                    "unresolved_seasons": coverage.unresolved_seasons,
                    "enabled": competition.enabled,
                    "automatic_retry": False,
                }
            )
        self.stdout.write(json.dumps(rows, sort_keys=True))
