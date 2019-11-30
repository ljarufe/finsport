from django.core.management.base import BaseCommand
from scrapy.crawler import CrawlerProcess

from bet_scraper.bet_scraper.spiders.livescore_spider import (
    LivescoreResultsSpider
)
from bet_scraper.utils import get_crawler_options


class Command(BaseCommand):
    help = 'Update or create matches'

    def handle(self, *args, **options):
        process = CrawlerProcess(get_crawler_options('check_results'))
        process.crawl(LivescoreResultsSpider)
        process.start()
