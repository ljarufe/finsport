import json
from pathlib import Path

from django.core.management import get_commands

from tools.inspect_legacy_dump import inspect_dump

ROOT = Path(__file__).resolve().parents[2]


def test_only_supported_custom_football_commands_and_legacy_paths_are_absent():
    commands = get_commands()
    assert {name for name, app in commands.items() if app == "football"} == {
        "sync_football_catalog",
        "sync_football_day",
        "sync_football_season",
        "evaluate_football_predictions",
        "predict_football_day",
    }
    for name in (
        "get_leagues",
        "set_inkabet_leagues",
        "get_matches",
        "check_results",
        "check_results_inkabet",
        "execute_commands",
        "fill_tables",
        "make_bets",
    ):
        assert name not in commands
    assert not list((ROOT / "bet_scraper").glob("**/*.py"))
    assert not (ROOT / "common/scrapy_runner.py").exists()
    assert not list((ROOT / "bet/selenium_bots").glob("**/*.py"))
    assert not (ROOT / "bet/tasks.py").exists()
    assert not (ROOT / "football/tasks.py").exists()
    assert not list((ROOT / "accounts").glob("**/*.py"))
    assert not list((ROOT / "bet/management").glob("**/*.py"))


def test_removed_dependencies_and_services_have_no_runtime_configuration():
    requirements = (ROOT / "requirements.txt").read_text().casefold()
    compose = (ROOT / "compose.yml").read_text().casefold()
    settings = (ROOT / "finsport/settings.py").read_text().casefold()
    pytest_configuration = (ROOT / "pytest.ini").read_text()
    assert "scrapy" not in requirements
    assert "selenium" not in requirements
    assert "selenium:" not in compose
    assert "selenium_url" not in settings
    assert "crawler_options" not in settings
    assert "django-fernet-fields" not in requirements
    assert "django-cors-headers" not in requirements
    assert "ipython" not in requirements
    assert "corsheaders" not in settings
    assert '"accounts"' not in settings
    assert "django-countries" in requirements
    assert '"django_countries"' in settings
    assert "DJANGO_SETTINGS_MODULE = finsport.settings" in pytest_configuration
    assert not (ROOT / "finsport/test_settings.py").exists()


def test_offline_dump_inspector_reports_only_safe_research_data(tmp_path):
    dump = tmp_path / "legacy.sql"
    dump.write_text(
        """CREATE TABLE public.football_match (
);
CREATE TABLE public.accounts_account (
);
COPY public.football_match (id, state, local_score, visitor_score) FROM stdin;
1\tR\t1\t1
2\tU\t2\t1
\\.
COPY public.bet_betrow (id, state, iteration) FROM stdin;
1\tW\t14
2\tL\t3
\\.
COPY public.django_migrations (id, app, name, applied) FROM stdin;
1\tfootball\t0025_old\t2020-01-01
2\tbet\t0023_old\t2020-01-01
3\tauth\t0012_other\t2020-01-01
\\.
COPY public.accounts_account (id, username, password, token) FROM stdin;
1\tprivate-user\tprivate-password\tprivate-token
\\.
"""
    )

    report = inspect_dump(dump)
    serialized = json.dumps(report)
    assert report["tables"]["football_match"]["row_count"] == 2
    assert report["tables"]["bet_betrow"]["row_count"] == 2
    assert report["research"]["bet_betrow_states"] == {"L": 1, "W": 1}
    assert report["research"]["bet_betrow_max_iteration"] == 14
    assert report["migration_names"] == {
        "football": ["0025_old"],
        "bet": ["0023_old"],
    }
    assert report["ignored_copy_sections"] == 1
    assert "private-user" not in serialized
    assert "private-password" not in serialized
    assert "private-token" not in serialized
