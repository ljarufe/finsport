# -*- coding: utf-8 -*-

from scrapy import Spider
from scrapy.crawler import CrawlerProcess


class InkabetSpider(Spider):

    name = "inkabet"
    start_urls = ['https://www.inkabet.pe/es-ES/sportsbook/eventpaths/240']

    @classmethod
    def run(cls, matches_data_path):
        process = CrawlerProcess({
            'USER_AGENT': 'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)',
            'FEED_URI': matches_data_path})
        process.crawl(cls)
        process.start()

    def parse(self, response):
        print("response: ", response)
        table = response.css(
            'div.today_weekend_coupon_container table tbody tr')
        matches = []
        for i, tr in enumerate(table, start=10):
            if 'event' not in tr.xpath("@class").extract()[0]:
                league = tr.css('th div span::text').extract_first()
                continue
            factors = []
            for td in tr.css('td'):
                if 'outcome' in td.xpath("@class").extract()[0]:
                    factors.append(td.css('a::text').extract_first())
                if 'event' in td.xpath("@class").extract()[0]:
                    match = td.css('a::text').extract_first().strip()
                    url = td.css('a::attr(href)').extract_first()
                if 'date_time' in td.xpath("@class").extract()[0]:
                    start_datetime = td.css(
                        'time::text').extract_first().strip()
            if not len(factors) > 3:
                continue
            matches.append({
                'local_team': match.split(' - ')[0],
                'visitor_team': match.split(' - ')[1],
                'start_datetime': start_datetime,
                'factors': factors,
                'url': url,
                'league': league,
            })

        yield {'matches': matches}
