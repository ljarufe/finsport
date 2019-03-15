from django.core.management.base import BaseCommand
from scrapy.crawler import CrawlerProcess

from accounts.models import Account
from bet.models import BetRow, BetTable
from bet_scraper.bet_scraper.spiders.livescore_spider import (
    LivescoreResultsSpider
)
from football.models import Match


class Command(BaseCommand):
    help = 'Update or create matches'

    def handle(self, *args, **options):
        process = CrawlerProcess({
            'USER_AGENT':
                'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)',
            'ITEM_PIPELINES': {
                'bet_scraper.bet_scraper.pipelines.LivescorePipeline': 300}})
        process.crawl(LivescoreResultsSpider)
        process.start()
        for account in Account.objects.filter(bet_page__active=True):
            for table in BetTable.objects.filter(state=BetTable.AVAILABLE):
                # TODO: crear una función para esto
                bet_rows = BetRow.objects.filter(
                    bet_table=table,
                    state__in=(BetRow.CURRENT, BetRow.WAITING))
                if bet_rows.exists():
                    bet_row = bet_rows.first()
                    if bet_row.match.state is Match.PLAYING:
                        if bet_row.match.is_suspended():
                            bet_row.remove_match()
                    elif bet_row.match.state is Match.PARITY:
                        table.set_finished(account, bet_row)
                    else:
                        bet_row.set_waiting()
