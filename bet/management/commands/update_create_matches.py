# -*- coding: utf-8 -*-

import json
import os

from scrapy.crawler import CrawlerProcess

from django.core.management.base import BaseCommand
from django.conf import settings

from accounts.models import Account, BetPage
from football.utils import save_match


class Command(BaseCommand):
    help = 'Update or create matches'

    def handle(self, *args, **options):
        bet_pages = BetPage.objects.filter(active=True)
        for bet_page in bet_pages:
            matches_data_path = "{path}/spider-data.json".format(
                path=settings.SPIDER_DATA_PATH)
            os.system("rm -rf {path}".format(path=matches_data_path))
            process = CrawlerProcess({
                'USER_AGENT':
                    'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)',
                'FEED_URI': matches_data_path, })
            process.crawl(bet_page.get_spider())
            process.start()
            with open(matches_data_path) as f:
                url_matches = []
                accounts = Account.objects.filter(bet_page=bet_page)
                favorite_team = accounts[0].favorite_team if len(
                    accounts) else None
                data = json.load(f)
                for match in data.get('matches', None):
                    match_url = save_match(match, favorite_team)
                    if match_url:
                        match_url = '%s%s' % (bet_page.domain, match_url)
                        url_matches.append(match_url)
