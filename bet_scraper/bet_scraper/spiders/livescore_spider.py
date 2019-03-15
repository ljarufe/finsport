# -*- coding: utf-8 -*-

from scrapy import Spider, Selector

from bet.selenium_bots.selenium_bot import SeleniumBot
from bet_scraper.bet_scraper.items import MatchResultItem


class LivescoreResultsSpider(Spider):
    name = "livescore"
    start_urls = ['https://www.livescore.com']

    def __init__(self):
        self.selenium_bot = SeleniumBot()

    def parse(self, response):
        selector = Selector(
            text=self.selenium_bot.get_page_source(response.url))
        self.selenium_bot.clean_driver()
        for match in selector.css('div[data-type="container"] .match-row'):
            yield MatchResultItem(
                local_team=match.css('div.ply span::text')[0].get(),
                visitor_team=match.css('div.ply span::text')[1].get(),
                local_score=match.css('div.sco span.hom::text').get(),
                visitor_score=match.css('div.sco span.awy::text').get()
            )
