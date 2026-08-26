from football.sync import sync_catalog_payloads

from ._sync_base import SyncCommand


class Command(SyncCommand):
    help = "Refresh API-Football competitions, seasons, and Match Winner market."

    def run_sync(self, client, **options):
        leagues = client.get_all("leagues")
        bets = client.get_all("odds/bets")
        stats, _ = sync_catalog_payloads(leagues, bets)
        self.stats = stats
        return stats
