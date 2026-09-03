import json

from django.core.management.base import BaseCommand

from football.capital.longitudinal import recompute_longitudinal_capital


class Command(BaseCommand):
    help = "Recompute the DB-only FS-010 longitudinal Capital snapshot."

    def handle(self, *args, **options):
        del args, options
        result = recompute_longitudinal_capital()
        self.stdout.write(json.dumps(result.as_dict(), sort_keys=True))
