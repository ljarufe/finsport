from django.core.management.base import BaseCommand
from scrapy.crawler import CrawlerProcess

from bet_scraper.bet_scraper.spiders.livescore_spider import LivescoreResultsSpider


class Command(BaseCommand):
    help = "Update or create matches"

    def handle(self, *args, **options):
        process = CrawlerProcess()
        process.crawl(LivescoreResultsSpider)
        process.start()
