import requests

from celery import shared_task
from datetime import datetime

from common.scrapy_runner import run_scrapy_spider
from .models import League, Match


@shared_task
def get_leagues():
    return run_scrapy_spider("leagues")


@shared_task
def get_livescore_matches():
    today = datetime.now().strftime("%Y%m%d")
    response = requests.get(f"https://prod-cdn-mev-api.livescore.com/v1/api/app/date/soccer/{today}/-5?locale=en")
    for stage in response.json().get("Stages", []):
        league_name = stage["Snm"]
        country = stage["CnmT"]
        league = League.objects.get_league(league_name, country, field_name="name_en", language="en")
        if league:
            for match_data in stage.get("Events", []):
                local_team = match_data.get("T1", [{"Nm": None}])[0]["Nm"]
                visitor_team = match_data.get("T2", [{"Nm": None}])[0]["Nm"]
                local_score = match_data.get("Tr1", None)
                visitor_score = match_data.get("Tr2", None)
                state = match_data.get("Eps", None)  # FT: Full Time, HT: Half Time, NS: Not Started, etc.
                Match.objects.update(
                    league=league,
                    local_team__name=local_team,
                    visitor_team__name=visitor_team,
                    defaults={
                        "local_score": local_score,
                        "visitor_score": visitor_score,
                        "state": state,
                    },
                )
    return stages
