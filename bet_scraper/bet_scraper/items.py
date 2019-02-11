# -*- coding: utf-8 -*-

import scrapy


class MatchItem(scrapy.Item):
    local_team = scrapy.Field()
    visitor_team = scrapy.Field()
    league = scrapy.Field()
    local_factor = scrapy.Field()
    parity_factor = scrapy.Field()
    visitor_factor = scrapy.Field()
    start_datetime = scrapy.Field()
