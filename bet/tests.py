from unittest import mock

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError


def test_legacy_betting_cycle_is_not_scheduled():
    scheduled_tasks = {
        entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()
    }

    assert "bet.tasks.run_betting_cycle" not in scheduled_tasks


def test_make_bets_fails_closed_before_legacy_implementation():
    with mock.patch(
        "bet.management.commands.make_bets.Command._legacy_handle"
    ) as legacy_handle:
        with pytest.raises(CommandError, match="Real betting is disabled"):
            call_command("make_bets")

    legacy_handle.assert_not_called()
