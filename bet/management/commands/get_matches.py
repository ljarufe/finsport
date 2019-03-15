from django.core.management.base import BaseCommand
from scrapy.crawler import CrawlerProcess

from accounts.models import BetPage


class Command(BaseCommand):
    help = 'Update or create matches'

    def handle(self, *args, **options):
        for bet_page in BetPage.objects.filter(active=True):
            process = CrawlerProcess({
                'USER_AGENT':
                    'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)',
                'ITEM_PIPELINES': {
                    'bet_scraper.bet_scraper.pipelines.MatchPipeline': 300}})
            process.crawl(bet_page.get_match_spider())
            process.start()
