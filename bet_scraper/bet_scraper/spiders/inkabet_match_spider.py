# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from urllib.parse import urljoin

from scrapy import Spider, Selector

from bet.selenium_bots.selenium_bot import SeleniumBot
from bet_scraper.bet_scraper.items import MatchItem


class InkabetMatchSpider(Spider):
    name = "inkabet"
    start_urls = ['https://www.inkabet.pe']

    def __init__(self, bet_page):
        self.bet_page = bet_page
        self.bet_selenium = SeleniumBot()
        self.selector = Selector(text=self.bet_selenium.get_page_source(
            urljoin(InkabetMatchSpider.start_urls[0], "/sportsbook/240")))

    def __del__(self):
        self.bet_selenium.clean_driver()

    def parse(self, response):
        items = self.selector.xpath('//div[./preceding-sibling::h3[1]="Hoy"]')
        for item in items:
            url = item.css('a::attr(href)').extract_first()
            selector = Selector(text=self.bet_selenium.get_page_source(
                urljoin(InkabetMatchSpider.start_urls[0], url), sleep_time=3))
            country, league = selector.css(
                '.osg-coupon__breadcrumbs a::text').getall()[2:4]
            local_team, visitor_team = selector.css(
                '.osg-coupon__event-header-title::text').get().split(' - ')
            hour, minute = selector.css(
                '.osg-coupon__event-header-time::text'
            ).get().split()[1].split(':')
            start_datetime = datetime.now().replace(
                hour=int(hour), minute=int(minute), second=0, microsecond=0)
            if start_datetime > datetime.now() + timedelta(hours=1):
                raise StopIteration
            local_factor, draw_factor, visitor_factor = map(
                lambda x: float(x),
                selector.css('.osg-outcome__price-arrow::text').getall()[:3])

            yield MatchItem(
                local_team=local_team,
                visitor_team=visitor_team,
                league=league,
                country=country,
                url=url,
                local_factor=local_factor,
                draw_factor=draw_factor,
                visitor_factor=visitor_factor,
                start_datetime=start_datetime,
            )
