from celery import shared_task
from scrapy.crawler import CrawlerProcess

from bet_scraper.bet_scraper.spiders.livescore_spider import LivescoreResultsSpider


@shared_task
def check_results():
    process = CrawlerProcess()
    process.crawl(LivescoreResultsSpider)
    process.start()
