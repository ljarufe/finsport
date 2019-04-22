# -*- coding: utf-8 -*-

import logging

from scrapy import Spider
from django_countries import countries

from bet_scraper.bet_scraper.items import LeagueItem

logger_leagues = logging.getLogger('leagues')


class LeaguesSpider(Spider):
    name = "leagues"
    start_urls = ['https://www.progressivebetting.co.uk/statistics/'
                  'football_statistics/leagues_by_draws/']

    def parse(self, response):
        for league in response.css(".lgdraws tbody tr"):
            country_league = league.css("td:nth-child(2) a::text").get().split()
            for i, w in enumerate(country_league):
                country_name = " ".join(country_league[:i + 1])
                country = countries.by_name(country_name, language="en")
                if country:
                    name = " ".join(country_league[i + 1:])
                    percentage = league.css(
                        "td:nth-child(3)::text").get().strip()[:-1]
                    yield LeagueItem(
                        name=name,
                        country=country,
                        percentage=percentage,
                    )
                    break
            else:
                logger_leagues.info("Country not found: %s" % country_league)
