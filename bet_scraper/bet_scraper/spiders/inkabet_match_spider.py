# -*- coding: utf-8 -*-

from datetime import datetime
from scrapy import Spider

from bet_scraper.bet_scraper.items import MatchItem


class InkabetMatchSpider(Spider):
    name = "inkabet"
    start_urls = ['https://www.inkabet.pe/es-ES/sportsbook/eventpaths/240']

    def parse(self, response):
        # TODO: cambiar todo esto
        table = response.css(
            'div.today_weekend_coupon_container table tbody tr')
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
                if 'date_time' in td.xpath("@class").extract()[0]:
                    start_datetime = datetime.strptime(
                        td.css('time::text').extract_first().strip(),
                        '%d-%m-%y %H:%M')
            if not len(factors) > 3:
                continue
            if len(match.split(' - ')) < 2:
                continue
            factors = list(map(lambda x: float(x), factors[:3]))

            yield MatchItem(
                local_team=match.split(' - ')[0],
                visitor_team=match.split(' - ')[1],
                league=league,
                local_factor=factors[0],
                draw_factor=factors[1],
                visitor_factor=factors[2],
                start_datetime=start_datetime
            )
