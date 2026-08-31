import pytest


@pytest.fixture(autouse=True)
def disable_operational_spool_during_tests(settings):
    settings.OBSERVABILITY_EVENTS_ENABLED = False
