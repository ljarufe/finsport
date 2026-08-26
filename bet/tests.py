import pytest
from django.conf import settings


def test_legacy_betting_cycle_is_not_scheduled():
    scheduled_tasks = {
        entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()
    }
    assert "bet.tasks.run_betting_cycle" not in scheduled_tasks


@pytest.mark.parametrize(
    "module_name",
    [
        "bet.tasks",
        "bet.selenium_bots.selenium_bot",
        "bet.selenium_bots.inkabet_selenium_bot",
    ],
)
def test_legacy_betting_execution_modules_are_removed(module_name):
    with pytest.raises(ModuleNotFoundError):
        __import__(module_name)
