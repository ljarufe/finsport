import requests

from celery import shared_task
from datetime import datetime

from common.scrapy_runner import run_scrapy_spider


@shared_task
def get_leagues():
    return run_scrapy_spider("leagues")


@shared_task
def get_livescore_matches():
    today = datetime.now().strftime("%Y%m%d")
    response = requests.get(f"https://prod-cdn-mev-api.livescore.com/v1/api/app/date/soccer/{today}/-5?locale=en")
    stages = [stage["Snm"].split(":")[0] for stage in response.json().get("Stages")]
    return response.json()
