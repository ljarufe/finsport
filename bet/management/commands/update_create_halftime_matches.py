# -*- coding: utf-8 -*-
import json
import os

from django.core.management.base import BaseCommand
from django.conf import settings

from scrapy.crawler import CrawlerProcess

from spider.spider.spiders.inkabet_spider import (
    InkabetHalfTimeSpider,
)
from football.utils import save_half_match


class Command(BaseCommand):
    help = 'Update or create halftime matches'
    main_page = 'https://www.inkabet.pe'

    def handle(self, *args, **options):

        matches_data_path = '%s/spider-data.json' % settings.SPIDER_DATA_PATH
        matches_half_path = '%s/spider-half.json' % settings.SPIDER_DATA_PATH
        os.system("rm -rf %s" % matches_half_path)
        url_matches = []
        with open(matches_data_path) as f:
            data = json.load(f)
            for match in data.get('matches', None):
                match_url = match.get('url', None)
                if match_url:
                    match_url = '%s%s' % (
                        self.main_page, match_url)
                    url_matches.append(match_url)

        process = CrawlerProcess({
            'USER_AGENT': 'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)',
            'FEED_URI': matches_half_path,
        })
        process.crawl(InkabetHalfTimeSpider, urls=url_matches)
        process.start(stop_after_crawl=True)
        with open(matches_half_path) as f:
            for x in f.readlines():
                data = json.loads(x)
                print("data: ", data)
                save_half_match(data)
