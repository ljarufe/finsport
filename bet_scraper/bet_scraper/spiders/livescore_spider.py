from scrapy import Selector, Spider

from bet.selenium_bots.selenium_bot import SeleniumBot
from ..items import MatchResultItem


class LivescoreResultsSpider(Spider):
    name = "livescore"
    start_urls = ["https://www.livescore.com/"]
    custom_settings = {
        "ITEM_PIPELINES": {"bet_scraper.pipelines.LivescorePipeline": 300},
    }

    def __init__(self):
        super().__init__()
        self.selenium_bot = SeleniumBot()

    def __del__(self):
        self.selenium_bot.clean_driver()

    def parse(self, response):
        page_source = self.selenium_bot.get_page_source(response.url, scroll_down=True)
        if not page_source:
            return
        selector = Selector(text=page_source)
        for match in selector.xpath('//*[@data-id[contains(., "_mtc-r")]]'):
            print(match.xpath('.//*[@data-id[contains(., "_mtc-r_hm-tm-nm")]]/text()').get())
            # yield MatchResultItem(
            #     local_team=match.xpath('//*[@data-id[contains(., "_mtc-r_hm-tm-nm")]]'),
            #     visitor_team=match.css("div.ply span::text")[1].get(),
            #     local_score=match.css("div.sco span.hom::text").get(),
            #     visitor_score=match.css("div.sco span.awy::text").get(),
            # )
