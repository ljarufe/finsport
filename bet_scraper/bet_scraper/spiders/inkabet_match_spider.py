# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from urllib.parse import urljoin

from scrapy import Selector

from bet.selenium_bots.selenium_bot import SeleniumBot
from bet_scraper.bet_scraper.items import MatchItem
from bet_scraper.bet_scraper.spiders.err_back_spider import ErrbackSpider


class InkabetMatchSpider(ErrbackSpider):
    name = "inkabet"
    start_urls = ['https://www.inkabet.pe']

    def __init__(self, bet_page):
        self.bet_page = bet_page
        self.bet_selenium = SeleniumBot()
        page_source = self.bet_selenium.get_page_source(
            urljoin(InkabetMatchSpider.start_urls[0], "/sportsbook/240"))
        if page_source:
            self.selector = Selector(text=page_source)
        else:
            self.selector = None

    def __del__(self):
        self.bet_selenium.clean_driver()

    def parse(self, response):
        yield from self.parse_items("Hoy")
        if datetime.now().hour >= 23:
            yield from self.parse_items("Mañana")

    def parse_items(self, date_selector):
        if not self.selector:
            return
        items = self.selector.xpath(
            f'//div[./preceding-sibling::h3[1]="{date_selector}"]')
        for item in items:
            url = item.css('a::attr(href)').extract_first()
            page_source = self.bet_selenium.get_page_source(
                urljoin(InkabetMatchSpider.start_urls[0], url), sleep_time=4)
            if not page_source:
                return
            selector = Selector(text=page_source)
            try:
                country, league = selector.css(
                    '.osg-coupon__breadcrumbs a::text').getall()[2:4]
                local_team, visitor_team = selector.xpath(
                    '//*[@id="osg-app"]/div/div[1]/div/div[2]/div[2]/div[1]/h1/'
                    'text()').get().split(' - ')
            except(ValueError, AttributeError):
                continue
            hour, minute = selector.xpath(
                '//*[@id="osg-app"]/div/div[1]/div/div[2]/div[2]/div[1]/span/'
                'text()').get().split()[1].split(':')
            start_datetime = datetime.now().replace(
                hour=int(hour), minute=int(minute), second=0, microsecond=0)
            if date_selector == "Mañana":
                start_datetime = start_datetime.replace(
                    day=start_datetime.day + 1)
            if start_datetime > datetime.now() + timedelta(hours=1):
                return
            try:
                local_factor = float(selector.xpath(
                    '//*[@id="osg-app"]/div/div[1]/div/div[2]/div[2]/div[2]/'
                    'div[2]/div[2]/div/div[1]/div/div[2]/div/text()').get())
                draw_factor = float(selector.xpath(
                    '//*[@id="osg-app"]/div/div[1]/div/div[2]/div[2]/div[2]/'
                    'div[2]/div[2]/div/div[2]/div/div[2]/div/text()').get())
                visitor_factor = float(selector.xpath(
                    '//*[@id="osg-app"]/div/div[1]/div/div[2]/div[2]/div[2]/'
                    'div[2]/div[2]/div/div[3]/div/div[2]/div/text()').get())
            except TypeError:
                continue

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
