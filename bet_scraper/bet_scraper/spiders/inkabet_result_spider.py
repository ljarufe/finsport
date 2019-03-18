# -*- coding: utf-8 -*-

import itertools

from scrapy import Spider, Selector

from bet_scraper.bet_scraper.items import ResultMatchItem


class InkabetResultSpider(Spider):
    name = "inkabet_result_spider"
    start_urls = ['https://www.inkabet.pe/es-ES/account/history']
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
        return itertools.chain(
            self.yield_items(InkabetResultSpider.LOST),
            self.yield_items(InkabetResultSpider.WON))

    def yield_items(self, result_type):
        rows = self.selector.css(
            'table#history_table .%s' %
            InkabetResultSpider.RESULT_TYPE[result_type])
        for tr in rows:
            result = tr.xpath('td[6]/span/span/text()').extract()[1]
            teams = [y.strip().split("  ")[0] for y in result.split("-")]

            yield ResultMatchItem(
                local_team=teams[2],
                visitor_team=teams[3],
                result=result_type)
