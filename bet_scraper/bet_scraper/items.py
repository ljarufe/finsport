# -*- coding: utf-8 -*-

import scrapy


class MatchItem(scrapy.Item):
    local_team = scrapy.Field()
    visitor_team = scrapy.Field()
    league = scrapy.Field()
    local_factor = scrapy.Field()
    draw_factor = scrapy.Field()
    visitor_factor = scrapy.Field()
    start_datetime = scrapy.Field()


class MatchResultItem(scrapy.Item):
    local_team = scrapy.Field()
    visitor_team = scrapy.Field()
    local_score = scrapy.Field()
    visitor_score = scrapy.Field()


class ResultMatchItem(scrapy.Item):
    local_team = scrapy.Field()
    visitor_team = scrapy.Field()
    result = scrapy.Field()
