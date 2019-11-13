from django.conf import settings
from django.core.management.base import BaseCommand
from scrapy.crawler import CrawlerProcess

from bet_scraper.bet_scraper.spiders.livescore_spider import (
    LivescoreResultsSpider
)


class Command(BaseCommand):
    help = 'Update or create matches'

    def handle(self, *args, **options):
        process = CrawlerProcess({
            'USER_AGENT':
                'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)',
            'ITEM_PIPELINES': {
                'bet_scraper.bet_scraper.pipelines.LivescorePipeline': 300},
            'LOG_ENABLED': settings.SCRAPY_LOG,
        })
        process.crawl(LivescoreResultsSpider)
        process.start()
