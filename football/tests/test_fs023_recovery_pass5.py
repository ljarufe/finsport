"""Recovery Pass 5: fresh T10 convergence, reporting, and bounded BSD rebind."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.test import Client, override_settings

from football.models import (
    BSDEventBinding,
    BSDTeamMapping,
    CapitalDeployment,
    CapitalRuntimeConfig,
    CaptureWorkItem,
    Competition,
    CompetitionResultRoute,
    CompetitionSourceRef,
    ReconciliationStatus,
    Season,
    StrategyBinding,
    StrategyEpoch,
    StrategySwitch,
)
from football.providers.bsd import BSDError
from football.providers.bsd_identity import rebind_stale_event
from football.reporting.selectors import match_detail
from football.result_routing import process_due_bsd
from football.strategy.authority import resolve_authority
from football.strategy.deployment import provision
from football.strategy.fs023_bootstrap import NOT_READY, _mapping
from football.sync import get_api_football_source
from football.tests.test_fs022_strategy import capture
from football.tests.test_fs023_contracts import _match

pytestmark = pytest.mark.django_db
AT = datetime(2026, 9, 29, 15, tzinfo=UTC)


def canonical_28(*, limit=28):
    _, rows, _ = _mapping()
    source = get_api_football_source()
    for row in rows[:limit]:
        competition = Competition.objects.create(
            pk=row["local_competition_id"],
            name=f"Frozen {row['local_competition_id']}",
            country=row["country"],
            competition_type="League",
            enabled=False,
        )
        CompetitionSourceRef.objects.create(
            source=source,
            competition=competition,
            external_id=str(row["api_football_league_id"]),
            reconciliation_status=ReconciliationStatus.RESOLVED,
        )
    return rows, source


def test_fresh_migrated_database_converges_only_after_complete_canonical_data():
    assert provision(at=AT) == ()
    deployment = CapitalDeployment.objects.get(pk=1)
    assert deployment.state == NOT_READY and not deployment.entry_enabled
    assert not CompetitionResultRoute.objects.exists()
    assert not StrategyEpoch.objects.exists()
    assert not CapitalRuntimeConfig.objects.filter(automatic=True).exists()

    rows, source = canonical_28(limit=27)
    assert provision(at=AT + timedelta(minutes=1)) == ()
    assert not CompetitionResultRoute.objects.exists()
    assert not StrategyBinding.objects.exists()
    last = rows[27]
    competition = Competition.objects.create(
        pk=last["local_competition_id"],
        name=f"Frozen {last['local_competition_id']}",
        country=last["country"],
        competition_type="League",
    )
    ref = CompetitionSourceRef.objects.create(
        source=source,
        competition=competition,
        external_id="wrong-league",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    with pytest.raises(RuntimeError, match="FS023_API_F_LEAGUE_IDENTITY_MISMATCH"):
        provision(at=AT + timedelta(minutes=2))
    assert not CompetitionResultRoute.objects.exists()
    ref.external_id = str(last["api_football_league_id"])
    ref.save(update_fields=["external_id"])

    (config,) = provision(at=AT + timedelta(minutes=3))
    deployment.refresh_from_db()
    epoch = deployment.active_epoch
    routes = list(CompetitionResultRoute.objects.order_by("competition_id"))
    assert len(routes) == 28
    assert sum(bool(route.bsd_league_ids) for route in routes) == 23
    assert sum(not route.bsd_league_ids for route in routes) == 5
    assert {
        route.competition_id: (route.api_football_league_id, route.bsd_league_ids)
        for route in routes
    } == {
        row["local_competition_id"]: (
            row["api_football_league_id"],
            row["bsd_league_ids"],
        )
        for row in rows
    }
    assert Competition.objects.filter(enabled=True).count() == 28
    assert config.strategy_epoch_id == epoch.pk
    assert epoch.binding.contract["capture_window"] == "market-t10m"
    assert epoch.binding.contract["wake_seconds"] == 180
    assert epoch.binding.contract["real_betting"] is False
    assert (
        deployment.selection["prospective_prediction_effective_config"][
            "capture_window"
        ]
        == "market-t10m"
    )
    assert config.initial_bankroll == config.bankroll_equity == Decimal("100")
    assert config.reserved_exposure == 0
    assert deployment.real_betting is False and deployment.state == "ACTIVE"
    assert not CaptureWorkItem.objects.exists()
    assert StrategyBinding.objects.count() == StrategyEpoch.objects.count() == 1
    assert StrategySwitch.objects.count() == 0
    assert provision(at=AT + timedelta(minutes=4))[0].pk == config.pk
    assert provision(at=AT + timedelta(minutes=5))[0].pk == config.pk
    assert CompetitionResultRoute.objects.count() == 28
    assert CapitalRuntimeConfig.objects.filter(automatic=True).count() == 1
    assert StrategyBinding.objects.count() == StrategyEpoch.objects.count() == 1
    assert StrategySwitch.objects.count() == 0
    assert list(deployment.events.values_list("reason", flat=True)) == [
        "CANONICAL_PREREQUISITES_INCOMPLETE",
        "FS023_FRESH_T10_EPOCH",
    ]


def test_populated_fs022_migration_backfills_t30_then_drains_to_t10():
    rows, _ = canonical_28()
    authority = resolve_authority()
    pd = authority["winner_candidate"]["prediction_decision"]
    capital = authority["winner_candidate"]["capital"]
    old = CapitalRuntimeConfig.objects.create(
        identity="fs022:fs021-economic-209:prospective-v1",
        runtime_version="fs022-global-simulation-v1",
        execution_version="fs022-prospective-t30-v2",
        mode=CapitalRuntimeConfig.Mode.CURRENT,
        automatic=True,
        current=True,
        entry_enabled=True,
        source_model_code=pd["prediction_code"],
        decision_policy_code=pd["decision_policy"],
        decision_policy_variant=pd["decision_variant"],
        policy_code=capital["code"],
        policy_version=capital["version"],
        policy_config=capital["config"],
        max_lanes=capital["max_lanes"],
        initial_bankroll=Decimal("100"),
        bankroll_equity=Decimal("75"),
        reserved_exposure=Decimal("0"),
        peak_equity=Decimal("100"),
        started_at=AT,
    )
    deployment = CapitalDeployment.objects.create(
        pk=1,
        config=old,
        selection=authority,
        state="ACTIVE",
        entry_enabled=True,
        activated_at=AT,
    )
    migration = import_module("football.migrations.0019_fs023_live_binding_backfill")
    migration.forwards(apps, None)
    old.refresh_from_db()
    deployment.refresh_from_db()
    source_epoch = deployment.active_epoch
    assert old.strategy_epoch_id == source_epoch.pk
    assert source_epoch.binding.contract["capture_window"] == "market-t30m"
    assert source_epoch.initial_bankroll == Decimal("100")
    assert old.bankroll_equity == Decimal("75")
    assert CompetitionResultRoute.objects.count() == len(rows) == 28

    (new,) = provision(at=AT + timedelta(minutes=1))
    deployment.refresh_from_db()
    old.refresh_from_db()
    source_epoch.refresh_from_db()
    assert source_epoch.state == "DRAINED"
    assert new.pk != old.pk and new.strategy_epoch_id != source_epoch.pk
    assert new.strategy_epoch.binding.contract["capture_window"] == "market-t10m"
    assert new.initial_bankroll == new.bankroll_equity == Decimal("100")
    assert old.bankroll_equity == Decimal("75") and not old.entry_enabled
    assert StrategySwitch.objects.count() == 1 and StrategyEpoch.objects.count() == 2
    assert provision(at=AT + timedelta(minutes=2))[0].pk == new.pk
    assert StrategySwitch.objects.count() == 1 and StrategyEpoch.objects.count() == 2
    assert deployment.real_betting is False


def test_current_t10_capture_is_visible_in_match_detail():
    from football.market_identity import (
        reconcile_bookmaker_identity,
        reconcile_market_identity,
    )
    from football.models import Bookmaker, OddsMarket

    rows, source = canonical_28()
    market = OddsMarket.objects.create(
        source=source, external_id="1", name="Match Winner"
    )
    reconcile_market_identity(market)
    books = []
    for external_id, name in (("4", "Pinnacle"), ("8", "Bet365")):
        book = Bookmaker.objects.create(
            source=source, external_id=external_id, name=name
        )
        reconcile_bookmaker_identity(book)
        books.append(book)
    (config,) = provision(at=AT)
    competition = Competition.objects.get(pk=rows[0]["local_competition_id"])
    season = Season.objects.create(competition=competition, year=2026)
    work = capture(
        (source, market, books, competition, season),
        901,
        at=AT + timedelta(hours=1),
    )
    work.match.kickoff = work.executed_at + timedelta(minutes=10)
    work.match.save(update_fields=["kickoff", "modified"])
    work.intended_window = "market-t10m"
    work.not_after = work.executed_at + timedelta(minutes=8)
    work.save(update_fields=["intended_window", "not_after"])
    assert config.strategy_epoch.binding.contract["capture_window"] == "market-t10m"
    detail = match_detail(work.match_id)
    assert len(detail["captures"]) == 1
    assert detail["captures"][0]["window"] == "T−10 min"
    assert len(detail["captures"][0]["quotes"]) == 2
    response = Client(HTTP_HOST="localhost").get(f"/partidos/{work.match_id}/detalle/")
    assert response.status_code == 200
    assert "T−10 min" in response.content.decode()


def test_cross_midnight_stale_rebind_fetches_previous_day_and_fails_ambiguity():
    match = _match()
    match.kickoff = datetime(2026, 10, 1, 0, 5, tzinfo=UTC)
    match.save(update_fields=["kickoff", "modified"])
    route = CompetitionResultRoute.objects.create(
        competition=match.season.competition,
        api_football_league_id=1,
        bsd_league_ids=[1],
        bsd_state="BSD_SHADOW_VALIDATION",
        provenance={"bsd_season_ids": {"1": 2026}},
    )
    for team, provider_id in ((match.home_team, 11), (match.away_team, 12)):
        BSDTeamMapping.objects.create(
            route=route,
            canonical_team=team,
            bsd_team_id=provider_id,
            bsd_league_id=1,
            approval="EXACT_UNIQUE",
        )
    binding = BSDEventBinding.objects.create(
        match=match, bsd_league_id=1, bsd_event_id=100
    )
    replacement = {
        "id": 101,
        "league_id": 1,
        "home_team_id": 11,
        "away_team_id": 12,
        "event_date": "2026-09-30T23:55:00Z",
    }

    class ClientStub:
        def __init__(self, *, ambiguous=False):
            self.ambiguous = ambiguous
            self.paths = []
            self.collection_params = []

        def get(self, path, **kwargs):
            self.paths.append(path)
            if path == "events/100/":
                raise BSDError("BSD_IDENTITY_UNRESOLVED", status=404)
            if path == "events/":
                params = kwargs["params"]
                self.collection_params.append(params)
                events = [
                    replacement,
                    {**replacement, "id": 102, "event_date": "2026-09-30T23:49:00Z"},
                    {**replacement, "id": 103, "league_id": 2},
                    {**replacement, "id": 104, "away_team_id": 99},
                ]
                if self.ambiguous:
                    events.append({**replacement, "id": 105})
                return {"results": events, "next": None}
            assert path == "events/101/"
            return {
                **replacement,
                "status": "finished",
                "home_score": 2,
                "away_score": 1,
            }

    client = ClientStub()
    with override_settings(BSD_API_TOKEN="fake-only"):
        handled, _, errors = process_due_bsd(
            [SimpleNamespace(match=match, result_refresh_error="")],
            at=match.kickoff + timedelta(hours=3),
            client_factory=lambda: client,
        )
    binding.refresh_from_db()
    assert handled == set() and errors == []
    assert client.collection_params[0]["date_from"] == "2026-09-30"
    assert client.collection_params[0]["date_to"] == "2026-10-02"
    assert client.paths == ["events/100/", "events/", "events/101/"]
    assert binding.bsd_event_id == 101
    assert binding.provenance["state"] == "BOUND_REPLACEMENT"
    ambiguous = ClientStub(ambiguous=True)
    assert (
        rebind_stale_event(
            match,
            route,
            binding,
            client=ambiguous,
            at=match.kickoff + timedelta(hours=4),
        )
        == "BSD_IDENTITY_AMBIGUOUS"
    )
    binding.refresh_from_db()
    assert binding.bsd_event_id == 101
    assert binding.provenance["state"] == "STALE_404"
