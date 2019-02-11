import scrapy

from scrapy.selector import Selector
from urllib.parse import unquote


class ResultsSpider(scrapy.Spider):
    name = "result-spider"
    start_urls = ["http://www.google.com/"]
    allowed_domains = ["google.com.pe"]

    def __init__(self, *args, **kwargs):
        urls = kwargs.pop('urls', [])
        if urls:
            self.start_urls = urls.split(',')
        super(ResultsSpider, self).__init__(*args, **kwargs)

    def parse(self, response):
        final = Selector(text=response.selector.xpath(
            '//div[@id="ires"]/ol/div').extract_first())
        try:
            score = final.xpath(
                '//div/div/div/div/text()').extract()[0].split(' - ')
            state = final.xpath('//div/div/div/div/span/text()').extract()
            print("SCORE: ", score)
            if score[0].strip() == 'vs.' or len(score) > 1:
                yield {
                    'match': {
                        'score': score,
                        'state': state[0] if len(state) > 0 else "",
                    },
                    'url': unquote(response.url)
                }
            else:
                yield {
                    'match': {},
                    'url': unquote(response.url)
                }
        except Exception as e:
            print("EXCEPTION %s", e)
            yield {
                'match': {},
                'url': unquote(response.url)
            }
