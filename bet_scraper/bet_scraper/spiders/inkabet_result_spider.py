from datetime import datetime, timedelta

from scrapy import Selector, Spider

from ..items import ResultMatchItem


class InkabetResultSpider(Spider):
    name = "inkabet_result_spider"
    start_urls = ["https://www.inkabet.pe/account/betshistory"]
    custom_settings = (
        {
            "ITEM_PIPELINES": {"bet_scraper.pipelines.ResultsPipeline": 300},
        },
    )

    LOST = "L"
    WON = "W"
    RESULT_TYPE = {
        LOST: "lost_row",
        WON: "won_row",
    }

    def __init__(self, account, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = account
        self.bet_selenium = self.account.bet_page.get_selenium_bot()(self.account)
        self.error = False
        if self.bet_selenium.login():
            today = datetime.now().strftime("%Y-%m-%d")
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            url = f"{InkabetResultSpider.start_urls[0]}?dateTo={tomorrow}&dateFrom={today}"
            page_source = self.bet_selenium.get_page_source(url, scroll_down=True)
            if page_source:
                self.selector = Selector(text=page_source)
                return
        self.error = True

    def __del__(self):
        self.bet_selenium.clean_driver()

    def parse(self, response):
        if self.error:
            return
        rows = self.selector.css(".osg-bets-history-item--table")
        for tr in rows:
            result = tr.css(".osg-bets-history-item__status span::text").get()
            match = tr.css(".osg-bets-history-item__competitors::text").get()
            local, visitor = match.split(" - ")

            yield ResultMatchItem(local_team=local, visitor_team=visitor, result=result)
