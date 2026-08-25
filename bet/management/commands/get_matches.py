from django.core.management.base import BaseCommand
from scrapy.crawler import CrawlerProcess

from bet_scraper.bet_scraper.spiders.inkabet_match_spider import InkabetMatchSpider


class Command(BaseCommand):
    help = "Update or create matches"

    def handle(self, *args, **options):
        process = CrawlerProcess()
        process.crawl(InkabetMatchSpider)
        process.start()
