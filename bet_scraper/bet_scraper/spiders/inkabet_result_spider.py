# -*- coding: utf-8 -*-

from scrapy import Spider, Selector

from bet_scraper.bet_scraper.items import ResultMatchItem


class InkabetResultSpider(Spider):
    name = "inkabet_result_spider"
    start_urls = ['https://www.inkabet.pe/account/betshistory']
    LOST = 'L'
    WON = 'W'
    RESULT_TYPE = {
        LOST: 'lost_row',
        WON: 'won_row',
    }

    def __init__(self, account):
        self.account = account
        bet_selenium = self.account.bet_page.get_selenium_bot()(self.account)
        bet_selenium.login()
        self.selector = Selector(text=bet_selenium.get_page_source(
            InkabetResultSpider.start_urls[0]))
        bet_selenium.clean_driver()

    def parse(self, response):
        rows = self.selector.css('.osg-bets-history-item--table')
        for tr in rows:
            result = tr.css(".osg-bets-history-item__status span::text").get()
            match = tr.css('.osg-bets-history-item__competitors::text').get()
            local, visitor = match.split(" - ")

            yield ResultMatchItem(
                local_team=local,
                visitor_team=visitor,
                result=result)
