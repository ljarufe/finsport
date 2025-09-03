from celery import shared_task

from common.scrapy_runner import run_scrapy_spider


@shared_task
def get_leagues():
    return run_scrapy_spider("leagues")
