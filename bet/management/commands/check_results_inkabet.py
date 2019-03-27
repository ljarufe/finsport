# -*- coding: utf-8 -*-

import logging

from django.core.management.base import BaseCommand

from scrapy.crawler import CrawlerProcess

from bet.models import BetRow
from bet_scraper.bet_scraper.spiders.inkabet_result_spider import (
    InkabetResultSpider
)
from accounts.models import Account

logger_inkabet_results = logging.getLogger('inkabet_results')


class Command(BaseCommand):
    help = 'Check and save matches results'

    def handle(self, *args, **options):
        for account in Account.objects.filter(bet_page__active=True):
            bet_rows = BetRow.objects.filter(state=BetRow.CURRENT)
            if bet_rows.exists():
                process = CrawlerProcess({
                    'USER_AGENT':
                        'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)',
                    'ITEM_PIPELINES': {
                        'bet_scraper.bet_scraper.pipelines.ResultsPipeline':
                            300},
                    'LOG_ENABLED': False,
                })
                process.crawl(InkabetResultSpider, account)
                process.start()
                for bet_row in bet_rows:
                    if bet_row.match.is_suspended():
                        bet_row.remove_match()
                        logger_inkabet_results.info(
                            "Suspended match: %s" %
                            bet_row.match.get_logger_info())
