from django.conf import settings
from django.core.exceptions import ValidationError

from football.api_inkabet import InkabetClient, InkabetError
from football.inkabet import (
    reconcile_categories,
    resolved_match_refs_for,
    sync_mw3w_payload,
)
from football.models import CompetitionSourceRef, OddsMarket, ReconciliationStatus
from football.sync import (
    FootballSyncError,
    sync_fixture_payloads,
    sync_odds_payloads,
    validate_sync_date,
)

from ._sync_base import SyncCommand


class Command(SyncCommand):
    help = "Sync enabled fixtures for one date, optionally including pre-match odds."
    inkabet_client_class = InkabetClient

    def add_arguments(self, parser):
        parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
        parser.add_argument("--with-odds", action="store_true")

    def run_sync(self, client, **options):
        try:
            sync_date = validate_sync_date(options["date"])
        except ValidationError as error:
            raise FootballSyncError(error.message) from error
        api_refs = CompetitionSourceRef.objects.filter(
            source__code="api_football",
            reconciliation_status=ReconciliationStatus.RESOLVED,
            competition__enabled=True,
        ).select_related("competition")
        competitions_by_external_id = {
            ref.external_id: ref.competition for ref in api_refs
        }
        fixtures = client.get_all(
            "fixtures",
            {"date": sync_date.isoformat(), "timezone": settings.TIME_ZONE},
        )
        stats, accepted = sync_fixture_payloads(fixtures, competitions_by_external_id)
        self.stats = stats
        if not options["with_odds"] or not accepted:
            return stats

        api_odds_matches = {}
        for fixture_id, match in accepted.items():
            if (match.season.coverage or {}).get("odds") is not True:
                stats.skipped += 1
                continue
            api_odds_matches[fixture_id] = match
        if api_odds_matches:
            market = OddsMarket.objects.filter(
                source__code="api_football", name__iexact="Match Winner"
            ).first()
            if market is None:
                market = OddsMarket.objects.filter(
                    source__code="api_football", name__iexact="1X2"
                ).first()
            if market is None:
                raise FootballSyncError(
                    "Match Winner market is missing; run sync_football_catalog first."
                )
        for fixture_id, match in api_odds_matches.items():
            payloads = client.get_all(
                "odds",
                {
                    "fixture": fixture_id,
                    "bet": market.external_id,
                },
            )
            stats.merge(sync_odds_payloads(payloads, {fixture_id: match}, market))

        if not settings.INKABET_BRAND_ID or not settings.INKABET_MARKET_CODE:
            stats.skipped += len(accepted)
            self.stdout.write(
                self.style.WARNING(
                    "INKABET_CONFIGURATION_REQUIRED: set local brandId and "
                    "marketCode to synchronize Inkabet odds"
                )
            )
            return stats

        self.inkabet_errors = 0
        self.inkabet_client = self.inkabet_client_class()

        try:
            categories = self.inkabet_client.categories()
        except InkabetError as error:
            self.inkabet_errors += 1
            self.stdout.write(self.style.WARNING(f"INKABET_DEGRADED: {error}"))
            return stats

        discovery_stats = reconcile_categories(
            categories,
            accepted.values(),
        )
        stats.merge(discovery_stats)

        for match_ref in resolved_match_refs_for(accepted.values()):
            try:
                payload = self.inkabet_client.match_winner(match_ref.external_id)
            except InkabetError as error:
                self.inkabet_errors += 1
                self.stdout.write(
                    self.style.WARNING(
                        "INKABET_DEGRADED " f"event={match_ref.external_id}: {error}"
                    )
                )
                continue

            stats.merge(sync_mw3w_payload(payload, match_ref))

        return stats
