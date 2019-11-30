from django.core.management.base import BaseCommand
from scrapy.crawler import CrawlerProcess

from accounts.models import BetPage
from bet_scraper.utils import get_crawler_options


class Command(BaseCommand):
    help = 'Update or create matches'

    def handle(self, *args, **options):
        for bet_page in BetPage.objects.filter(active=True):
            process = CrawlerProcess(get_crawler_options('get_matches'))
            process.crawl(bet_page.get_match_spider(), bet_page)
            process.start()
