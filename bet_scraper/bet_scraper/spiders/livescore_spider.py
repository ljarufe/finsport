# -*- coding: utf-8 -*-

from scrapy import Selector

from bet.selenium_bots.selenium_bot import SeleniumBot
from bet_scraper.bet_scraper.items import MatchResultItem
from bet_scraper.bet_scraper.spiders.err_back_spider import ErrbackSpider


class LivescoreResultsSpider(ErrbackSpider):
    name = "livescore"
    start_urls = ['https://www.livescore.com/']

    def __init__(self):
        self.selenium_bot = SeleniumBot()

    def __del__(self):
        self.selenium_bot.clean_driver()

    def parse(self, response):
        page_source = self.selenium_bot.get_page_source(response.url)
        if not page_source:
            return
        selector = Selector(text=page_source)
        for match in selector.css('div[data-type="container"] .match-row'):
            yield MatchResultItem(
                local_team=match.css('div.ply span::text')[0].get(),
                visitor_team=match.css('div.ply span::text')[1].get(),
                local_score=match.css('div.sco span.hom::text').get(),
                visitor_score=match.css('div.sco span.awy::text').get()
            )
