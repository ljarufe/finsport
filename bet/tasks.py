import logging

from celery import chain, shared_task
from django.core.management import call_command

logger = logging.getLogger("get_matches")


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def check_results_task(self):
    call_command("check_results")
    return "check_results:ok"


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def check_results_inkabet_task(self):
    call_command("check_results_inkabet")
    return "check_results_inkabet:ok"


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def get_matches_task(self):
    call_command("get_matches")
    return "get_matches:ok"


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def fill_tables_task(self):
    call_command("fill_tables")
    return "fill_tables:ok"


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def make_bets_task(self):
    call_command("make_bets")
    return "make_bets:ok"


@shared_task
def run_betting_cycle():
    logger.info("Starting betting cycle chain")
    workflow = chain(
        check_results_task.s(),
        check_results_inkabet_task.s(),
        get_matches_task.s(),
        fill_tables_task.s(),
        make_bets_task.s(),
    )
    async_result = workflow.apply_async()
    logger.info("Betting cycle queued with id=%s", async_result.id)
    return async_result.id
