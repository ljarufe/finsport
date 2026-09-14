import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from football.historical_market.contracts import HistoricalMarketScopeError
from football.historical_market.service import (
    authoritative_market_seasons,
    ingest_completed_season,
)
from football.models import Competition


class Command(BaseCommand):
    help = "Plan or apply the bounded Football-Data completed-season 1X2 backfill."

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument("--competition-id", action="append", type=int)
        scope.add_argument("--all-enabled", action="store_true")
        parser.add_argument("--season-year", action="append", type=int)
        parser.add_argument("--cache-only", action="store_true")
        parser.add_argument("--cache-root")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--output")

    def handle(self, *args, **options):
        competitions = Competition.objects.order_by("id")
        if options["all_enabled"]:
            competitions = competitions.filter(enabled=True)
        else:
            competitions = competitions.filter(pk__in=options["competition_id"])
            found = set(competitions.values_list("id", flat=True))
            missing = sorted(set(options["competition_id"]) - found)
            if missing:
                raise CommandError(f"Unknown Competition IDs: {missing}")
        requested_years = set(options["season_year"] or [])
        plans = []
        for competition in competitions:
            try:
                authoritative = authoritative_market_seasons(competition)
            except HistoricalMarketScopeError as error:
                raise CommandError(f"Competition {competition.pk}: {error}") from error
            authoritative_years = {season.year for season in authoritative}
            invalid_years = sorted(requested_years - authoritative_years)
            if invalid_years:
                raise CommandError(
                    "Competition "
                    f"{competition.pk}: SEASONS_OUTSIDE_AUTHORITATIVE_REQUIRED_SCOPE:"
                    f"{invalid_years}"
                )
            selected = [
                season
                for season in authoritative
                if not requested_years or season.year in requested_years
            ]
            plans.append((competition, selected))

        summaries = []
        with transaction.atomic():
            for competition, seasons in plans:
                for season in seasons:
                    summaries.append(
                        ingest_completed_season(
                            competition,
                            season,
                            cache_only=options["cache_only"],
                            cache_root=options["cache_root"],
                        )
                    )
            if not options["apply"]:
                transaction.set_rollback(True)
        payload = {
            "mode": "APPLY" if options["apply"] else "DRY_RUN",
            "seasons": summaries,
        }
        rendered = json.dumps(payload, indent=2, sort_keys=True)
        if options["output"]:
            Path(options["output"]).write_text(rendered + "\n", encoding="utf-8")
        self.stdout.write(rendered)
