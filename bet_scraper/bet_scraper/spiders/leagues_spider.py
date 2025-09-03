import logging

from django_countries import countries
from scrapy import Spider

from ..items import LeagueItem

logger_leagues = logging.getLogger("leagues")


class LeaguesSpider(Spider):
    name = "leagues"
    start_urls = [
        "https://www.progressivebetting.co.uk/statistics/football_statistics/leagues_by_draws/"
    ]
    custom_settings = {
        "ITEM_PIPELINES": {"bet_scraper.pipelines.LeaguesPipeline": 300},
    }

    def parse(self, response):
        for league in response.css(".lgdraws tbody tr"):
            country_league = (
                league.css("td:nth-child(2) a::text").get(default="").strip().split()
            )
            percentage_text = (
                league.css("td:nth-child(3)::text").get(default="").strip()
            )
            percentage = percentage_text.replace("%", "").strip()

            country = None
            name = None
            for i in range(len(country_league)):
                maybe_country = " ".join(country_league[: i + 1])
                country = countries.by_name(maybe_country, language="en")
                if country:
                    name = " ".join(country_league[i + 1 :])
                    break

            if country and name:
                yield LeagueItem(name=name, country=country, percentage=percentage)
            else:
                logger_leagues.warning(
                    f"Country not found: {' '.join(country_league)} | Row snippet: {league.get()[:80]}..."
                )
