import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from football.historical_market.current_season import recover_current_season
from football.models import Competition


class Command(BaseCommand):
    help = "Plan or apply additive Football-Data recovery for current-season gaps."

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument("--competition-id", action="append", type=int)
        scope.add_argument("--all-enabled", action="store_true")
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
        summaries = []
        for competition in competitions:
            seasons = list(competition.seasons.filter(is_current=True).order_by("id"))
            if len(seasons) != 1:
                raise CommandError(
                    f"Competition {competition.pk} needs exactly one current Season."
                )
            summaries.append(
                recover_current_season(
                    competition,
                    seasons[0],
                    apply=options["apply"],
                    cache_only=options["cache_only"],
                    cache_root=options["cache_root"],
                )
            )
        payload = {
            "mode": "APPLY" if options["apply"] else "DRY_RUN",
            "competitions": summaries,
        }
        rendered = json.dumps(payload, indent=2, sort_keys=True)
        if options["output"]:
            Path(options["output"]).write_text(rendered + "\n", encoding="utf-8")
        self.stdout.write(rendered)
