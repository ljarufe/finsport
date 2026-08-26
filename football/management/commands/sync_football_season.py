from django.conf import settings

from football.models import (
    Competition,
    CompetitionSourceRef,
    ReconciliationStatus,
    Season,
)
from football.sync import FootballSyncError, sync_fixture_payloads

from ._sync_base import SyncCommand


class Command(SyncCommand):
    help = "Sync one enabled Competition season from API-Football fixtures."

    def add_arguments(self, parser):
        parser.add_argument("competition", type=int, help="Local Competition ID")
        parser.add_argument("season", type=int, help="Provider season year")

    def run_sync(self, client, **options):
        try:
            competition = Competition.objects.get(pk=options["competition"])
        except Competition.DoesNotExist as error:
            raise FootballSyncError(
                "API-Football Competition was not found."
            ) from error
        if not competition.enabled:
            raise FootballSyncError(
                "Competition must be explicitly enabled before season synchronization."
            )
        competition_ref = CompetitionSourceRef.objects.filter(
            competition=competition,
            source__code="api_football",
            reconciliation_status=ReconciliationStatus.RESOLVED,
        ).first()
        if competition_ref is None:
            raise FootballSyncError(
                "API-Football Competition mapping is missing; "
                "run sync_football_catalog first."
            )
        year = options["season"]
        if not Season.objects.filter(competition=competition, year=year).exists():
            raise FootballSyncError(
                f"Season {year} is missing for Competition {competition.id}; "
                "run sync_football_catalog first."
            )
        fixtures = client.get_all(
            "fixtures",
            {
                "league": competition_ref.external_id,
                "season": year,
                "timezone": settings.TIME_ZONE,
            },
        )
        stats, _ = sync_fixture_payloads(
            fixtures, {competition_ref.external_id: competition}, expected_year=year
        )
        self.stats = stats
        return stats
