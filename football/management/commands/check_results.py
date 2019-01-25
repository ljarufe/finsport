# -*- coding: utf-8 -*-

import json
import os

from scrapy.crawler import CrawlerProcess
from spider.spider.spiders.results_spider import ResultsSpider

from django.core.management.base import BaseCommand
from django.conf import settings

from football.utils import save_result
from football.models import Match


# TODO: Google results is not working, fix the scraper
def obtain_url(match, urls_dic):
    visitor = match.visitor_team.name.replace(" ", "+")
    local = match.local_team.name.replace(" ", "+")
    url = "https://www.google.com.pe/search?q=%s+%s+%s+%s" % (
        local, visitor, match.start_datetime.day, match.start_datetime.month)
    urls_dic[url] = match

    return url


class Command(BaseCommand):
    help = 'Check and save matches results'

    def handle(self, *args, **options):
        matches_data_path = '%s/spider-score.json' % settings.SPIDER_DATA_PATH
        os.system("rm -rf %s" % matches_data_path)
        process = CrawlerProcess({
            'USER_AGENT': 'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)',
            'FEED_URI': matches_data_path,
        })
        urls = ''
        urls_dic = {}
        for match in Match.objects.filter(state=Match.PLAYING):
            urls += ',' + obtain_url(match, urls_dic)

        if urls:
            process.crawl(ResultsSpider, urls=urls[1:])
            process.start()
            with open(matches_data_path) as f:
                for x in f.readlines():
                    data = json.loads(x)
                    save_result(urls_dic[data["url"]], data["match"])
