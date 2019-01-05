# -*- coding: utf-8 -*-

import scrapy


class InkabetSpider(scrapy.Spider):

    name = "inkabet"
    start_urls = ['https://www.inkabet.pe/es-ES/sportsbook/eventpaths/240']

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


class InkabetHalfTimeSpider(scrapy.Spider):

    name = "inkabet-halftime"

    def __init__(self, *args, **kwargs):

        self.start_urls = kwargs.pop('urls', [])
        super(InkabetHalfTimeSpider, self).__init__(*args, **kwargs)

    def parse(self, response):

        table = response.css('div#main .coupon')
        # matches = []
        for t in table.css('.single_event'):
            # print("t: ", t)
            title = t.css('h2.market_type_title::text').extract_first()
            # print("TEXT: ", title)
            if 'Ganador (1-X-2) - Primer Tiempo' in title:
                # print("TEXT SEGUNDO TIEMPO: ", title)
                halftime_factors = []
                css_factors = t.css(
                    'div.market_type-content tr.event a span.formatted_price')
                for factor in css_factors:
                    halftime_factors.append(factor.css(
                        '::text').extract_first())
                print("factors: ", halftime_factors)

                teams = []
                teams_css = t.css(
                    'div.market_type-content tr.event a span.name')
                for team in teams_css:
                    teams.append(team.css('::text').extract_first())
                print("team: ", teams)

                # matches.append({
                #     'halftime_factors': halftime_factors,
                #     'local_team': teams[0],
                #     'visitor_team': teams[2],

                # })
                yield {
                    'halftime_factors': halftime_factors,
                    'local_team': teams[0],
                    'visitor_team': teams[2],
                }
