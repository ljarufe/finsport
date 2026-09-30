"""Deterministic FS-023 contracts; no real provider or scientific run."""

import gzip
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings

from football.capture.contracts import CaptureConfig
from football.capture.olv import PRODUCTION_WEIGHTS, score
from football.experiments import fs023_corpus
from football.experiments.fs023_benchmark import validate_benchmark
from football.experiments.fs023_runner import candidate_ids
from football.models import (
    Competition,
    Match,
    ResultProviderObservation,
    Season,
    StrategyBinding,
    StrategyEpoch,
    StrategySwitch,
    Team,
)
from football.providers.bsd import BSDClient, BSDError
from football.providers.bsd_identity import event_candidates, exact_unique_team_pairs
from football.result_provider import Result, record, shadow_gate

pytestmark = pytest.mark.django_db
NOW = datetime(2026, 9, 29, 15, tzinfo=UTC)


def _match():
    competition = Competition.objects.create(
        name=f"Test League {Competition.objects.count() + 1}",
        country="PE",
        competition_type="League",
        enabled=True,
    )
    season = Season.objects.create(competition=competition, year=2026)
    home = Team.objects.create(competition=competition, name="Atlético Lima")
    away = Team.objects.create(competition=competition, name="Callao FC")
    return Match.objects.create(
        season=season,
        home_team=home,
        away_team=away,
        kickoff=NOW,
        status_short="NS",
        status_long="Not started",
    )


def test_binding_digest_and_epoch_are_immutable():
    t30 = StrategyBinding.objects.create(
        name="T30",
        candidate_id=209,
        contract={
            "name": "T30",
            "candidate_id": 209,
            "capture_window": "market-t30m",
            "real_betting": False,
        },
        approved=True,
    )
    t10 = StrategyBinding.objects.create(
        name="T10",
        candidate_id=209,
        contract={
            "name": "T10",
            "candidate_id": 209,
            "capture_window": "market-t10m",
            "real_betting": False,
        },
        approved=True,
    )
    assert t30.digest != t10.digest
    t30.contract = {
        "name": "T30",
        "candidate_id": 209,
        "capture_window": "market-t10m",
        "real_betting": False,
    }
    with pytest.raises(ValidationError):
        t30.save()
    epoch = StrategyEpoch.objects.create(
        binding=t10,
        state="ACTIVE",
        initial_bankroll=Decimal("100"),
        activated_at=NOW,
    )
    epoch.initial_bankroll = Decimal("99")
    with pytest.raises(ValidationError):
        epoch.save()
    epoch.initial_bankroll = Decimal("100")
    epoch.state = "DRAINING"
    epoch.save(update_fields=["state"])
    switch = StrategySwitch.objects.create(
        source_epoch=epoch,
        target_binding=t30,
        initial_bankroll=Decimal("100"),
        requested_at=NOW + timedelta(minutes=1),
    )
    switch.initial_bankroll = Decimal("99")
    with pytest.raises(ValidationError):
        switch.save()


def test_t10_exact_contract_and_olv_weights():
    config = CaptureConfig.from_settings()
    assert len(config.windows) == 1
    assert config.windows[0].snapshot() == {
        "name": "market-t10m",
        "offset_minutes": 10,
        "before_tolerance_minutes": 0,
        "normal_tolerance_minutes": 3,
        "late_tolerance_minutes": 8,
    }
    assert score(0, 0, 0, 0, 0) == pytest.approx(0.875)
    assert score(4, 2, 4, 4, 2) == pytest.approx(
        0.60 / (6**0.5) + 0.25 * (4 / 7) + 0.15 / 3
    )
    assert PRODUCTION_WEIGHTS == (0.60, 0.25, 0.15)
    assert score(4, 2, 4, 4, 2, weights=(0.50, 0.30, 0.20)) != score(4, 2, 4, 4, 2)
    with override_settings(
        FOOTBALL_MARKET_CONSENSUS_WINDOWS=[
            {
                "name": "market-t30m",
                "offset_minutes": 30,
                "before_tolerance_minutes": 0,
                "normal_tolerance_minutes": 10,
                "late_tolerance_minutes": 15,
            }
        ]
    ):
        with pytest.raises(ValueError, match="market-t10m"):
            CaptureConfig.from_settings()


def test_bsd_missing_secret_makes_zero_calls():
    class Session:
        calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("network must not be used")

    session = Session()
    with override_settings(BSD_API_TOKEN=""):
        client = BSDClient(session=session)
        with pytest.raises(BSDError, match="BSD_NOT_CONFIGURED"):
            client.get("events/1/", logical_identity="test")
    assert session.calls == 0


def test_exact_team_and_event_binding_filters_ambiguity():
    match = _match()
    pairs = exact_unique_team_pairs(
        [match.home_team, match.away_team],
        [{"id": 1, "name": "Atletico Lima"}, {"id": 2, "name": "Callao FC"}],
    )
    assert {local.pk: row["id"] for local, row in pairs} == {
        match.home_team_id: 1,
        match.away_team_id: 2,
    }
    events = [
        {
            "id": 10,
            "league_id": 20,
            "home_team_id": 1,
            "away_team_id": 2,
            "event_date": (NOW + timedelta(minutes=15)).isoformat(),
        }
    ]
    assert len(event_candidates(match, events, [20], 1, 2)) == 1
    events.append(dict(events[0], id=11))
    assert len(event_candidates(match, events, [20], 1, 2)) == 2
    assert event_candidates(match, events, [19], 1, 2) == []


def test_result_conflict_preserves_canonical_match():
    match = _match()
    match.status_short = "FT"
    match.outcome = "HOME"
    match.fulltime_home_score = 2
    match.fulltime_away_score = 1
    match.save()
    assert shadow_gate()["status"] == "NO_SAMPLE"
    record(
        match,
        Result("API_FOOTBALL", "1", "FT", 2, 1, "HOME", NOW, {}),
        authoritative=True,
    )
    candidate, disposition = record(
        match,
        Result("BSD", "7", "FT", 1, 2, "AWAY", NOW + timedelta(minutes=1), {}),
        authoritative=False,
    )
    assert disposition == "PENDING_CONFLICT"
    assert candidate.provenance["pending_conflict"] is True
    assert not candidate.conflict
    confirmed, disposition = record(
        match,
        Result("BSD", "7", "FT", 1, 2, "AWAY", NOW + timedelta(minutes=31), {}),
        authoritative=False,
    )
    assert disposition == "RESULT_CONFLICT" and confirmed.conflict
    match.refresh_from_db()
    assert (match.outcome, match.fulltime_home_score, match.fulltime_away_score) == (
        "HOME",
        2,
        1,
    )
    assert ResultProviderObservation.objects.filter(match=match).count() == 3


def test_corpus_exact_union_and_hash_fail_closed(tmp_path, monkeypatch):
    countries = [f"C{i:02d}" for i in range(16)]
    specs = []
    for number, count in enumerate((2059, 546)):
        name = f"group-{number}.jsonl.gz"
        path = tmp_path / name
        with gzip.open(path, "wt") as stream:
            for i in range(count):
                stream.write(
                    json.dumps(
                        {
                            "fixture_id": f"{number}:{i}",
                            "kickoff_utc": NOW.isoformat(),
                            "country": countries[(number * 2059 + i) % 16],
                        }
                    )
                    + "\n"
                )
        specs.append((name, hashlib.sha256(path.read_bytes()).hexdigest(), count))
    monkeypatch.setattr(fs023_corpus, "ARTIFACTS", tuple(specs))
    assert len(fs023_corpus.authenticated_rows(tmp_path)) == 2605
    (tmp_path / specs[0][0]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        fs023_corpus.authenticated_rows(tmp_path)


def test_restricted_candidates_and_manual_benchmark():
    assert candidate_ids("209") == (209,)
    assert candidate_ids("209,216,223") == (209, 216, 223)
    for value in ("", "209,209", "210", "209,223"):
        with pytest.raises(ValueError):
            candidate_ids(value)
    benchmark = validate_benchmark(
        {
            "horizon_days": 257,
            "freeze_at": "2026-09-29",
            "primary": {
                "status": "AVAILABLE",
                "source": "MEF_LETRAS_TESORO_PEN",
                "currency": "PEN",
                "tenor_months": 9,
                "annual_rate": "0.07",
                "auction_date": "2026-09-28",
                "source_identifier": "official-auction-id",
                "source_locator": "official-record",
            },
            "secondary": {"status": "UNAVAILABLE"},
        }
    )
    assert Decimal(benchmark["primary"]["horizon_return"]) > 0
    assert (
        validate_benchmark(
            {
                "horizon_days": 257,
                "freeze_at": "2026-09-29",
                "primary": {"status": "UNAVAILABLE"},
            }
        )["primary"]["status"]
        == "UNAVAILABLE"
    )


def test_epoch_switch_is_idempotent_and_isolates_one_hundred_unit_bankroll():
    from football.models import CapitalDeployment, CapitalRuntimeConfig
    from football.strategy.epochs import advance, request_switch, target_binding

    contract = {
        "schema": "FS023_STRATEGY_BINDING_V1",
        "name": "FS022_BINDING_209_T30_V1",
        "candidate_id": 209,
        "prediction": {"code": "MARKET_CONSENSUS", "version": "v1"},
        "decision": {"code": "D05", "variant": "default"},
        "capital": {
            "code": "FRACTIONAL_KELLY",
            "version": "v1",
            "config": {"lambda": "0.25"},
            "max_lanes": 10,
        },
        "capture_window": "market-t30m",
        "wake_seconds": 300,
        "required_capabilities": ["LIVE_MARKET_ODDS"],
        "promotion_lineage": {},
        "provider_topology": "API_FOOTBALL_RESULT_PRIMARY",
        "real_betting": False,
    }
    source_binding = StrategyBinding.objects.create(
        name=contract["name"], candidate_id=209, contract=contract, approved=True
    )
    source_epoch = StrategyEpoch.objects.create(
        binding=source_binding,
        state="ACTIVE",
        initial_bankroll=Decimal("100"),
        activated_at=NOW,
    )
    old_config = CapitalRuntimeConfig.objects.create(
        identity="test:source-epoch",
        strategy_epoch=source_epoch,
        runtime_version="test",
        execution_version="fs022-prospective-t30-v2",
        mode="CURRENT",
        automatic=True,
        current=True,
        entry_enabled=True,
        source_model_code="MARKET_CONSENSUS",
        decision_policy_code="D05",
        decision_policy_variant="default",
        policy_code="FRACTIONAL_KELLY",
        policy_version="v1",
        policy_config={"lambda": "0.25"},
        max_lanes=10,
        initial_bankroll=Decimal("100"),
        bankroll_equity=Decimal("75"),
        reserved_exposure=0,
        peak_equity=Decimal("100"),
        policy_state={},
        started_at=NOW,
    )
    deployment = CapitalDeployment.objects.create(
        pk=1,
        state="ACTIVE",
        active_epoch=source_epoch,
        config=old_config,
        activated_at=NOW,
        entry_enabled=True,
        selection={
            "prospective_prediction_effective_config": {"capture_window": "market-t30m"}
        },
    )
    target = target_binding(source_binding)
    status, switch = request_switch(target, at=NOW + timedelta(minutes=1))
    assert status == "DRAINING"
    again, same = request_switch(target, at=NOW + timedelta(minutes=2))
    assert again == "DRAINING" and same.pk == switch.pk
    (new_config,) = advance(at=NOW + timedelta(minutes=3))
    deployment.refresh_from_db()
    source_epoch.refresh_from_db()
    assert source_epoch.state == "DRAINED"
    assert deployment.active_epoch.binding_id == target.pk
    assert new_config.initial_bankroll == new_config.bankroll_equity == Decimal("100")
    assert old_config.pk != new_config.pk
    old_config.refresh_from_db()
    assert old_config.bankroll_equity == Decimal("75") and not old_config.entry_enabled
    assert StrategyEpoch.objects.count() == 2 and StrategySwitch.objects.count() == 1
    assert request_switch(target, at=NOW + timedelta(minutes=4))[0] == "ALREADY_ACTIVE"


def test_bsd_bootstrap_follows_bounded_pagination():
    from football.providers.bsd_bootstrap import _page

    class Client:
        calls = []

        def get(self, endpoint, *, params, logical_identity):
            self.calls.append((endpoint, params["offset"], logical_identity))
            if params["offset"] == 0:
                return {
                    "results": [{"id": 1}],
                    "next": "https://sports.bzzoiro.com/api/v2/leagues/?limit=200&offset=200",
                }
            return {"results": [{"id": 2}], "next": None}

    client = Client()
    assert _page(client, "leagues/", {"limit": 200, "offset": 0}, "catalog") == [
        {"id": 1},
        {"id": 2},
    ]
    assert [offset for _, offset, _ in client.calls] == [0, 200]


@pytest.mark.parametrize(
    "http_status, body, expected",
    [
        (401, {}, "BSD_AUTH_FAILED"),
        (402, {}, "BSD_ENTITLEMENT_FAILED"),
        (429, {"code": "taster_exhausted"}, "BSD_TASTER_EXHAUSTED"),
        (429, {"code": "rate_limited"}, "BSD_BACKOFF"),
    ],
)
def test_bsd_client_fail_closed_statuses(http_status, body, expected):
    from football.models import ProviderCallAudit

    class Response:
        status_code = http_status
        headers = {}

        def json(self):
            return body

    class Session:
        calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            return Response()

    session = Session()
    with override_settings(BSD_API_TOKEN="test-only-token"):
        with pytest.raises(BSDError, match=expected):
            BSDClient(session=session, sleep=lambda seconds: None).get(
                "events/1/", logical_identity="test:status"
            )
    assert session.calls == 1
    audit = ProviderCallAudit.objects.get(logical_identity="test:status")
    assert audit.outcome == expected and audit.http_status == http_status
    assert "test-only-token" not in json.dumps(audit.request_metadata)


def test_bsd_bootstrap_requires_exact_identity_and_is_idempotent():
    from football.models import BSDEventBinding, BSDTeamMapping, CompetitionResultRoute
    from football.providers.bsd_bootstrap import bootstrap

    match = _match()
    first_route = CompetitionResultRoute.objects.create(
        competition=match.season.competition,
        api_football_league_id=1,
        bsd_league_ids=[1],
    )
    for league_id in range(2, 24):
        other = Competition.objects.create(
            name=f"Bootstrap {league_id}",
            country="PE",
            competition_type="League",
        )
        CompetitionResultRoute.objects.create(
            competition=other,
            api_football_league_id=league_id,
            bsd_league_ids=[league_id, 24] if league_id == 23 else [league_id],
        )

    class Client:
        calls = []

        def get(self, endpoint, *, params, logical_identity):
            self.calls.append((endpoint, params, logical_identity))
            if endpoint == "leagues/":
                rows = [
                    {"id": number, "current_season": {"id": 2026}}
                    for number in range(1, 25)
                ]
            elif endpoint == "teams/" and params["league_id"] == 1:
                rows = [
                    {"id": 11, "name": "Atletico Lima"},
                    {"id": 12, "name": "Callao FC"},
                ]
            elif endpoint == "events/" and params["league_id"] == 1:
                rows = [
                    {
                        "id": 100,
                        "league_id": 1,
                        "home_team_id": 11,
                        "away_team_id": 12,
                        "event_date": NOW.isoformat(),
                    }
                ]
            else:
                rows = []
            return {"results": rows, "next": None}

    client = Client()
    first = bootstrap(client=client, at=NOW - timedelta(hours=1))
    second = bootstrap(client=client, at=NOW - timedelta(hours=1))
    first_route.refresh_from_db()
    assert len(first) == len(second) == 23
    assert first_route.bsd_state == "BSD_SHADOW_VALIDATION"
    assert BSDTeamMapping.objects.filter(route=first_route).count() == 2
    assert BSDEventBinding.objects.get(match=match).bsd_event_id == 100
    assert second[0]["exact_teams_new"] == 0
    assert (
        CompetitionResultRoute.objects.exclude(pk=first_route.pk)
        .filter(bsd_state="BSD_BOOTSTRAP_PENDING")
        .count()
        == 22
    )


def test_bsd_shadow_and_primary_use_one_canonical_result_boundary():
    from types import SimpleNamespace

    from football.models import BSDEventBinding, BSDTeamMapping, CompetitionResultRoute
    from football.result_routing import process_due_bsd

    match = _match()
    route = CompetitionResultRoute.objects.create(
        competition=match.season.competition,
        api_football_league_id=1,
        bsd_league_ids=[1],
        bsd_state="BSD_SHADOW_VALIDATION",
    )
    BSDTeamMapping.objects.create(
        route=route,
        canonical_team=match.home_team,
        bsd_team_id=11,
        bsd_league_id=1,
        approval="EXACT_UNIQUE",
    )
    BSDTeamMapping.objects.create(
        route=route,
        canonical_team=match.away_team,
        bsd_team_id=12,
        bsd_league_id=1,
        approval="EXACT_UNIQUE",
    )
    BSDEventBinding.objects.create(match=match, bsd_league_id=1, bsd_event_id=100)
    payload = {
        "id": 100,
        "league_id": 1,
        "home_team_id": 11,
        "away_team_id": 12,
        "event_date": NOW.isoformat(),
        "status": "finished",
        "home_score": 2,
        "away_score": 1,
    }

    class Client:
        calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            return payload

    client = Client()
    due = [SimpleNamespace(match=match, result_refresh_error="")]
    with override_settings(BSD_API_TOKEN="fake-only"):
        handled, settled, errors = process_due_bsd(
            due,
            at=NOW + timedelta(hours=3),
            client_factory=lambda: client,
        )
    assert handled == set() and settled == 0 and errors == []
    match.refresh_from_db()
    assert match.status_short == "NS"
    assert ResultProviderObservation.objects.get(match=match).authoritative is False
    route.bsd_state = "BSD_PRIMARY_VALIDATED"
    route.save(update_fields=["bsd_state"])
    with override_settings(BSD_API_TOKEN="fake-only"):
        handled, settled, errors = process_due_bsd(
            due,
            at=NOW + timedelta(hours=3, minutes=30),
            client_factory=lambda: client,
        )
    match.refresh_from_db()
    assert handled == {match.pk} and settled == 0 and errors == []
    assert match.status_short == "FT" and match.outcome == "HOME"
    assert client.calls == 2


def test_bsd_auth_failure_persists_route_and_falls_back_to_api_f():
    from types import SimpleNamespace

    from football.models import BSDEventBinding, CompetitionResultRoute
    from football.result_routing import process_due_bsd

    match = _match()
    route = CompetitionResultRoute.objects.create(
        competition=match.season.competition,
        api_football_league_id=1,
        bsd_league_ids=[1],
        bsd_state="BSD_PRIMARY_VALIDATED",
    )
    BSDEventBinding.objects.create(match=match, bsd_league_id=1, bsd_event_id=100)

    class Client:
        calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            raise BSDError("BSD_AUTH_FAILED", status=401)

    client = Client()
    due = [SimpleNamespace(match=match, result_refresh_error="")]
    with override_settings(BSD_API_TOKEN="fake-only"):
        assert process_due_bsd(due, at=NOW, client_factory=lambda: client)[0] == set()
        assert (
            process_due_bsd(
                due, at=NOW + timedelta(minutes=3), client_factory=lambda: client
            )[0]
            == set()
        )
    route.refresh_from_db()
    assert route.bsd_state == "BSD_AUTH_FAILED"
    assert client.calls == 1


def test_experiment_subset_execution_stays_offline_and_never_activates(
    tmp_path, monkeypatch
):
    from football.experiments import fs023_runner
    from football.models import CapitalDeployment

    row = {
        "fixture_id": "frozen-fixture-1",
        "country": "EN",
        "kickoff_utc": NOW.isoformat(),
        "windows": {
            "T10": {
                "status": "PRODUCED",
                "book_count": 2,
                "cutoff": (NOW - timedelta(minutes=10)).isoformat(),
                "probabilities": [0.6, 0.2, 0.2],
                "best_prices": ["2.0", "4.0", "5.0"],
            }
        },
        "result": {"home_score": 2, "away_score": 1},
    }
    monkeypatch.setattr(fs023_runner, "authenticated_rows", lambda durable: [row])
    observed_calls = []

    def fake_path(stream, capital, lag):
        observed_calls.append((tuple(o.identity for o in stream), lag))
        return {"metrics": {"structurally_complete": True, "total_return": "0.01"}}

    monkeypatch.setattr(fs023_runner, "run_integrated_path", fake_path)
    monkeypatch.setattr(
        fs023_runner,
        "block_draws",
        lambda weeks, length, replicates: [None] * replicates,
    )
    monkeypatch.setattr(
        fs023_runner, "sampled_path", lambda stream, weeks, starts, length: stream
    )

    def selector(spec):
        assert spec["candidate_ids"] == [209, 216, 223]
        assert len(spec["scores"]["1"]) == 5000
        assert len(spec["scores"]["1"][0]) == 3
        return {"selected_candidate_id": 209}

    monkeypatch.setattr(fs023_runner, "select_economic_baseline", selector)
    benchmark = {
        "horizon_days": 257,
        "freeze_at": "2026-09-29",
        "primary": {"status": "UNAVAILABLE"},
    }
    before = CapitalDeployment.objects.count()
    eval_dir, evaluation = fs023_runner.run_subset(
        ids=(209,),
        benchmark=benchmark,
        output_root=tmp_path,
        durable=tmp_path,
        mode="evaluation-only",
    )
    assert evaluation["candidate_ids"] == [209]
    assert evaluation["activation"] is False
    assert evaluation["selection_authority"] is False
    assert len(observed_calls) == 3
    assert json.loads((eval_dir / "spec.json").read_text())["candidate_ids"] == [209]
    observed_calls.clear()
    selection_dir, selection = fs023_runner.run_subset(
        ids=(209, 216, 223),
        benchmark=benchmark,
        output_root=tmp_path,
        durable=tmp_path,
        mode="selection",
    )
    assert selection["candidate_ids"] == [209, 216, 223]
    assert selection["activation"] is False
    assert {"H1", "H2", "WITHOUT:EN"} <= set(selection["stability"])
    assert set(selection["stability"]["H1"]) == {"209", "216", "223"}
    assert selection_dir != eval_dir
    assert len(observed_calls) > 9
    assert CapitalDeployment.objects.count() == before
    with pytest.raises(ValueError, match="IMMUTABLE_ARTIFACT_CONFLICT"):
        fs023_runner._write_once(eval_dir / "spec.json", {"changed": True})


def test_bsd_status_normalization_and_identity_fail_closed():
    from football.models import BSDEventBinding, BSDTeamMapping, CompetitionResultRoute
    from football.result_provider import normalize_bsd

    match = _match()
    route = CompetitionResultRoute.objects.create(
        competition=match.season.competition,
        api_football_league_id=1,
        bsd_league_ids=[1],
    )
    BSDTeamMapping.objects.create(
        route=route,
        canonical_team=match.home_team,
        bsd_team_id=11,
        bsd_league_id=1,
        approval="EXACT_UNIQUE",
    )
    BSDTeamMapping.objects.create(
        route=route,
        canonical_team=match.away_team,
        bsd_team_id=12,
        bsd_league_id=1,
        approval="EXACT_UNIQUE",
    )
    binding = BSDEventBinding.objects.create(
        match=match, bsd_league_id=1, bsd_event_id=100
    )
    base = {
        "id": 100,
        "league_id": 1,
        "home_team_id": 11,
        "away_team_id": 12,
        "event_date": NOW.isoformat(),
    }
    finished = normalize_bsd(
        match,
        binding,
        base
        | {
            "status": "finished",
            "home_score": 2,
            "away_score": 1,
        },
        observed_at=NOW,
    )
    assert (finished.status, finished.outcome, finished.home, finished.away) == (
        "FT",
        "HOME",
        2,
        1,
    )
    assert (
        normalize_bsd(
            match, binding, base | {"status": "postponed"}, observed_at=NOW
        ).status
        == "PST"
    )
    assert (
        normalize_bsd(
            match, binding, base | {"status": "cancelled"}, observed_at=NOW
        ).status
        == "CANC"
    )
    assert (
        normalize_bsd(
            match, binding, base | {"status": "abandoned"}, observed_at=NOW
        ).status
        == "ABD"
    )
    assert (
        normalize_bsd(
            match, binding, base | {"status": "awarded"}, observed_at=NOW
        ).status
        == "UNRESOLVED_AWARD"
    )
    assert (
        normalize_bsd(
            match,
            binding,
            base
            | {
                "status": "awarded",
                "outcome": "HOME",
                "award_reason": "official",
            },
            observed_at=NOW,
        ).status
        == "AWD"
    )
    with pytest.raises(BSDError, match="BSD_IDENTITY_UNRESOLVED"):
        normalize_bsd(match, binding, base | {"away_team_id": 99}, observed_at=NOW)
    with pytest.raises(BSDError, match="RESULT_PROVIDER_MALFORMED"):
        normalize_bsd(
            match,
            binding,
            base | {"status": "finished", "home_score": None, "away_score": 1},
            observed_at=NOW,
        )


def test_shadow_gate_requires_exact_thirty_matches_five_leagues_seven_days():
    from football.models import CompetitionResultRoute
    from football.result_routing import maybe_promote_shadow

    routes = []
    for i in range(30):
        match = _match()
        match.kickoff = NOW + timedelta(days=i % 7)
        match.save(update_fields=["kickoff", "modified"])
        route = CompetitionResultRoute.objects.create(
            competition=match.season.competition,
            api_football_league_id=i + 1,
            bsd_league_ids=[i + 1],
            bsd_state="BSD_SHADOW_VALIDATION",
        )
        routes.append(route)
        observed = NOW + timedelta(days=i % 7, hours=3)
        record(
            match,
            Result("API_FOOTBALL", str(i), "FT", 2, 1, "HOME", observed, {}),
            authoritative=True,
        )
        record(
            match,
            Result("BSD", str(100 + i), "FT", 2, 1, "HOME", observed, {}),
            authoritative=False,
        )
        if i == 28:
            assert shadow_gate()["status"] == "PENDING"
    gate = maybe_promote_shadow()
    assert gate["status"] == "PASS"
    assert gate["matches"] == 30 and gate["lima_dates"] == 7
    assert gate["competitions"] >= 5 and gate["conflicts"] == 0
    assert (
        CompetitionResultRoute.objects.filter(
            pk__in=[route.pk for route in routes],
            bsd_state="BSD_PRIMARY_VALIDATED",
        ).count()
        == 30
    )


def test_bsd_client_retries_one_server_failure_and_audits_physical_calls():
    from football.models import ProviderCallAudit

    class Response:
        headers = {}

        def __init__(self, status):
            self.status_code = status

        def json(self):
            return {"results": []}

    class Session:
        calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            return Response(503 if self.calls == 1 else 200)

    slept = []
    with override_settings(BSD_API_TOKEN="fake-only"):
        result = BSDClient(session=Session(), sleep=slept.append).get(
            "leagues/",
            logical_identity="test:retry",
        )
    assert result == {"results": []}
    assert slept == [2]
    assert list(
        ProviderCallAudit.objects.filter(logical_identity="test:retry").values_list(
            "attempt_number", "outcome"
        )
    ) == [(1, "RESULT_PROVIDER_ERROR"), (2, "SUCCESS")]


def test_bsd_daily_quota_opens_one_global_circuit_until_reset():
    from types import SimpleNamespace

    from football.models import BSDEventBinding, CompetitionResultRoute
    from football.result_routing import process_due_bsd

    matches = [_match(), _match()]
    routes = []
    for index, match in enumerate(matches, start=1):
        routes.append(
            CompetitionResultRoute.objects.create(
                competition=match.season.competition,
                api_football_league_id=index,
                bsd_league_ids=[index],
                bsd_state="BSD_PRIMARY_VALIDATED",
            )
        )
        BSDEventBinding.objects.create(
            match=match, bsd_league_id=index, bsd_event_id=100 + index
        )

    class Client:
        calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            raise BSDError("BSD_TASTER_EXHAUSTED", status=429, retry_after=3600)

    client = Client()
    due = [SimpleNamespace(match=match, result_refresh_error="") for match in matches]
    with override_settings(BSD_API_TOKEN="fake-only"):
        handled, _, errors = process_due_bsd(
            due,
            at=NOW,
            client_factory=lambda: client,
        )
        process_due_bsd(
            due, at=NOW + timedelta(minutes=3), client_factory=lambda: client
        )
    assert handled == set() and errors == [f"BSD_TASTER_EXHAUSTED:{matches[0].pk}"]
    assert client.calls == 1
    for route in routes:
        route.refresh_from_db()
        assert route.bsd_state == "BSD_BACKOFF"
        assert route.bsd_backoff_until == NOW + timedelta(hours=1)


def test_bsd_bound_event_404_rebinds_only_one_exact_replacement():
    from types import SimpleNamespace

    from football.models import BSDEventBinding, BSDTeamMapping, CompetitionResultRoute
    from football.result_routing import process_due_bsd

    match = _match()
    route = CompetitionResultRoute.objects.create(
        competition=match.season.competition,
        api_football_league_id=1,
        bsd_league_ids=[1],
        bsd_state="BSD_SHADOW_VALIDATION",
        provenance={"bsd_season_ids": {"1": 2026}},
    )
    BSDTeamMapping.objects.create(
        route=route,
        canonical_team=match.home_team,
        bsd_team_id=11,
        bsd_league_id=1,
        approval="EXACT_UNIQUE",
    )
    BSDTeamMapping.objects.create(
        route=route,
        canonical_team=match.away_team,
        bsd_team_id=12,
        bsd_league_id=1,
        approval="EXACT_UNIQUE",
    )
    binding = BSDEventBinding.objects.create(
        match=match, bsd_league_id=1, bsd_event_id=100
    )
    event = {
        "id": 101,
        "league_id": 1,
        "home_team_id": 11,
        "away_team_id": 12,
        "event_date": NOW.isoformat(),
    }

    class Client:
        paths = []

        def get(self, path, **kwargs):
            self.paths.append(path)
            if path == "events/100/":
                raise BSDError("BSD_IDENTITY_UNRESOLVED", status=404)
            if path == "events/":
                return {"results": [event], "next": None}
            assert path == "events/101/"
            return event | {"status": "finished", "home_score": 2, "away_score": 1}

    client = Client()
    with override_settings(BSD_API_TOKEN="fake-only"):
        handled, _, errors = process_due_bsd(
            [SimpleNamespace(match=match, result_refresh_error="")],
            at=NOW + timedelta(hours=3),
            client_factory=lambda: client,
        )
    binding.refresh_from_db()
    assert handled == set() and errors == []
    assert binding.bsd_event_id == 101
    assert binding.provenance["stale_event_id"] == 100
    assert client.paths == ["events/100/", "events/", "events/101/"]


def test_confirmed_bsd_conflict_degrades_route_after_thirty_minutes():
    from football.models import BSDEventBinding, BSDTeamMapping, CompetitionResultRoute
    from football.result_routing import recheck_pending_conflicts

    match = _match()
    route = CompetitionResultRoute.objects.create(
        competition=match.season.competition,
        api_football_league_id=1,
        bsd_league_ids=[1],
        bsd_state="BSD_SHADOW_VALIDATION",
    )
    BSDTeamMapping.objects.create(
        route=route,
        canonical_team=match.home_team,
        bsd_team_id=11,
        bsd_league_id=1,
        approval="EXACT_UNIQUE",
    )
    BSDTeamMapping.objects.create(
        route=route,
        canonical_team=match.away_team,
        bsd_team_id=12,
        bsd_league_id=1,
        approval="EXACT_UNIQUE",
    )
    BSDEventBinding.objects.create(match=match, bsd_league_id=1, bsd_event_id=100)
    record(
        match,
        Result("API_FOOTBALL", "1", "FT", 2, 1, "HOME", NOW, {}),
        authoritative=True,
    )
    record(
        match,
        Result("BSD", "100", "FT", 1, 2, "AWAY", NOW + timedelta(minutes=1), {}),
        authoritative=False,
    )

    class Client:
        calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            return {
                "id": 100,
                "league_id": 1,
                "home_team_id": 11,
                "away_team_id": 12,
                "event_date": NOW.isoformat(),
                "status": "finished",
                "home_score": 1,
                "away_score": 2,
            }

    client = Client()
    with override_settings(BSD_API_TOKEN="fake-only"):
        assert recheck_pending_conflicts(
            at=NOW + timedelta(minutes=30),
            client_factory=lambda: client,
        ) == (0, [])
        calls, errors = recheck_pending_conflicts(
            at=NOW + timedelta(minutes=31),
            client_factory=lambda: client,
        )
    route.refresh_from_db()
    match.refresh_from_db()
    assert calls == 1 and errors == [f"RESULT_CONFLICT:{match.pk}"]
    assert route.bsd_state == "BSD_DEGRADED"
    assert match.outcome == "HOME"
    assert (
        ResultProviderObservation.objects.filter(
            match=match, provider="BSD", conflict=True
        ).count()
        == 1
    )


def test_api_f_regulation_normalization_uses_goals_only_for_ft():
    from football.result_provider import api_football_result

    match = _match()
    match.status_short = "FT"
    match.home_score = 2
    match.away_score = 1
    match.fulltime_home_score = 2
    match.fulltime_away_score = None
    match.outcome = "HOME"
    match.observed_at = NOW
    match.save()
    result = api_football_result(match, "fixture-1")
    assert (result.home, result.away, result.outcome) == (2, 1, "HOME")
    observation, disposition = record(match, result, authoritative=True)
    assert disposition == "RECORDED" and not observation.conflict
    match.status_short = "PEN"
    match.home_score = 4
    match.away_score = 3
    match.outcome = ""
    match.save()
    penalty = api_football_result(match, "fixture-1")
    assert (penalty.home, penalty.away, penalty.outcome) == (None, None, "")
    match.status_short = "CANC"
    match.fulltime_home_score = 2
    match.fulltime_away_score = 1
    match.save()
    cancelled = api_football_result(match, "fixture-1")
    assert (cancelled.home, cancelled.away, cancelled.outcome) == (None, None, "")


def test_api_f_terminal_sweep_preserves_matching_bsd_truth_with_missing_fulltime():
    from football.models import MatchSourceRef, ReconciliationStatus
    from football.sync import get_api_football_source, sync_fixture_payloads
    from football.tests.helpers import fixture_payload

    match = _match()
    match.status_short = "FT"
    match.outcome = "HOME"
    match.fulltime_home_score = 2
    match.fulltime_away_score = 1
    match.save()
    source = get_api_football_source()
    MatchSourceRef.objects.create(
        source=source,
        external_id="1001",
        match=match,
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    record(
        match, Result("BSD", "2001", "FT", 2, 1, "HOME", NOW, {}), authoritative=True
    )
    payload = fixture_payload(
        fixture_id=1001,
        league_id=1,
        year=2026,
        status_short="FT",
        home_score=2,
        away_score=1,
        kickoff=NOW.isoformat(),
        home_name=match.home_team.name,
        away_name=match.away_team.name,
    )
    payload["score"]["fulltime"] = {"home": None, "away": None}
    _, accepted = sync_fixture_payloads([payload], {"1": match.season.competition})
    assert accepted["1001"].pk == match.pk
    match.refresh_from_db()
    assert (match.outcome, match.fulltime_home_score, match.fulltime_away_score) == (
        "HOME",
        2,
        1,
    )
    assert not ResultProviderObservation.objects.filter(
        match=match, conflict=True
    ).exists()
    payload["goals"] = {"home": 1, "away": 2}
    _, accepted = sync_fixture_payloads([payload], {"1": match.season.competition})
    assert accepted == {}
    match.refresh_from_db()
    assert match.outcome == "HOME"
    candidate = ResultProviderObservation.objects.get(
        match=match, provider="API_FOOTBALL"
    )
    assert candidate.provenance["pending_conflict"] is True
    assert not candidate.conflict


def test_fixture_smoke_records_current_season_and_missing_bsd_token_is_effective_state():
    from football.capture.contracts import PlannedWork
    from football.capture.executor import CaptureExecutor
    from football.models import (
        CompetitionResultRoute,
        CompetitionSourceRef,
        ReconciliationStatus,
    )
    from football.result_routing import effective_bsd_state
    from football.sync import get_api_football_source
    from football.tests.helpers import fixture_payload

    match = _match()
    route = CompetitionResultRoute.objects.create(
        competition=match.season.competition,
        api_football_league_id=1,
        bsd_league_ids=[1],
        bsd_state="BSD_BOOTSTRAP_PENDING",
    )
    source = get_api_football_source()
    CompetitionSourceRef.objects.create(
        source=source,
        competition=match.season.competition,
        external_id="1",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    payload = fixture_payload(
        fixture_id=1001,
        league_id=1,
        year=2026,
        status_short="NS",
        home_score=None,
        away_score=None,
        kickoff=NOW.isoformat(),
        home_name=match.home_team.name,
        away_name=match.away_team.name,
    )

    class Client:
        def get_all(self, endpoint, params):
            assert endpoint == "fixtures" and params["date"] == NOW.date().isoformat()
            return [payload]

    item = PlannedWork(
        purpose="FIXTURE_REFRESH",
        status="PLANNED",
        source=source,
        logical_identity="fixture-smoke-test",
        intended_window="fixture-discovery",
        params={"date": NOW.date().isoformat(), "timezone": "America/Lima"},
    )
    CaptureExecutor._perform(Client(), item)
    route.refresh_from_db()
    assert route.season_id == match.season_id
    assert route.season_state == "TEMPORARILY_UNAVAILABLE"
    assert route.provenance["season_fixture_smoke_season_id"] == match.season_id
    with override_settings(BSD_API_TOKEN=""):
        assert effective_bsd_state(route) == "BSD_NOT_CONFIGURED"
    with override_settings(BSD_API_TOKEN="fake-only"):
        assert effective_bsd_state(route) == "BSD_BOOTSTRAP_PENDING"


def test_bsd_shadow_comparison_plans_one_surplus_date_sweep():
    from football.capture.planner import CapturePlanner
    from football.models import (
        CompetitionResultRoute,
        MatchSourceRef,
        ProviderCallAudit,
        ReconciliationStatus,
    )
    from football.sync import get_api_football_source

    match = _match()
    CompetitionResultRoute.objects.create(
        competition=match.season.competition,
        api_football_league_id=1,
        bsd_league_ids=[1],
        bsd_state="BSD_SHADOW_VALIDATION",
    )
    source = get_api_football_source()
    MatchSourceRef.objects.create(
        source=source,
        external_id="1001",
        match=match,
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    row, _ = record(
        match,
        Result("BSD", "2001", "FT", 2, 1, "HOME", NOW + timedelta(hours=3), {}),
        authoritative=False,
    )
    at = NOW + timedelta(hours=4)
    ResultProviderObservation.objects.filter(pk=row.pk).update(result_known_at=at)
    ProviderCallAudit.objects.create(
        capability=ProviderCallAudit.Capability.OTHER_EXPLICIT_MAINTENANCE,
        logical_identity="shadow-quota-header",
        endpoint_family="fixtures",
        started_at=at - timedelta(minutes=1),
        completed_at=at - timedelta(minutes=1),
        quota_limit=100,
        quota_remaining=80,
        quota_observed_at=at - timedelta(minutes=1),
        outcome="SUCCESS",
    )
    with override_settings(BSD_API_TOKEN="fake-only"):
        plan = CapturePlanner(config=CaptureConfig.from_settings()).plan(
            at=at, purpose="RESULT_REFRESH"
        )
    shadow = [
        item for item in plan.items if item.intended_window == "bsd-shadow-sample"
    ]
    assert len(shadow) == 1
    assert shadow[0].params["date"] == NOW.date().isoformat()
    assert shadow[0].target_external_ids == ("1001",)
    assert shadow[0].priority[0] == 5
    assert shadow[0].logical_identity.endswith(NOW.date().isoformat())


def test_bsd_probation_and_steady_sentinel_plan_only_one_surplus_date_sweep():
    from football.capture.planner import CapturePlanner
    from football.models import (
        CompetitionResultRoute,
        MatchSourceRef,
        ProviderCallAudit,
        ReconciliationStatus,
    )
    from football.result_provider import api_football_result, sentinel_phase
    from football.sync import get_api_football_source

    match = _match()
    route = CompetitionResultRoute.objects.create(
        competition=match.season.competition,
        api_football_league_id=1,
        bsd_league_ids=[1],
        bsd_state="BSD_PRIMARY_VALIDATED",
    )
    assert route.bsd_state == "BSD_PRIMARY_VALIDATED"
    source = get_api_football_source()
    MatchSourceRef.objects.create(
        source=source,
        external_id="1001",
        match=match,
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    bsd_result, _ = record(
        match,
        Result("BSD", "2001", "FT", 2, 1, "HOME", NOW + timedelta(hours=3), {}),
        authoritative=True,
    )
    at = NOW + timedelta(hours=4)
    ResultProviderObservation.objects.filter(pk=bsd_result.pk).update(
        result_known_at=NOW + timedelta(hours=3)
    )
    ProviderCallAudit.objects.create(
        capability=ProviderCallAudit.Capability.OTHER_EXPLICIT_MAINTENANCE,
        logical_identity="sentinel-quota-header",
        endpoint_family="fixtures",
        started_at=at - timedelta(minutes=1),
        completed_at=at - timedelta(minutes=1),
        quota_limit=100,
        quota_remaining=80,
        quota_observed_at=at - timedelta(minutes=1),
        outcome="SUCCESS",
    )
    with override_settings(BSD_API_TOKEN="fake-only"):
        plan = CapturePlanner(config=CaptureConfig.from_settings()).plan(
            at=at, purpose="RESULT_REFRESH"
        )
    sentinel = [
        item for item in plan.items if item.intended_window.startswith("bsd-sentinel-")
    ]
    assert len(sentinel) == 1
    assert sentinel[0].intended_window == "bsd-sentinel-probation"
    assert sentinel[0].target_external_ids == ("1001",)
    assert sentinel[0].params["date"] == NOW.date().isoformat()
    assert (
        sentinel_phase({"matches": 99, "competitions": 10, "confirmed_conflicts": 0})
        == "PROBATION"
    )
    assert (
        sentinel_phase({"matches": 100, "competitions": 10, "confirmed_conflicts": 0})
        == "STEADY"
    )
    assert (
        sentinel_phase({"matches": 100, "competitions": 10, "confirmed_conflicts": 1})
        == "PROBATION"
    )
    match.refresh_from_db()
    assert api_football_result(match, "1001").outcome == "HOME"


def test_sentinel_date_sweep_records_matching_api_f_result_without_rewriting_bsd(
    monkeypatch,
):
    from football.capture.contracts import PlannedWork
    from football.capture.executor import CaptureExecutor
    from football.models import (
        CompetitionSourceRef,
        MatchSourceRef,
        ReconciliationStatus,
    )
    from football.sync import get_api_football_source
    from football.tests.helpers import fixture_payload

    match = _match()
    source = get_api_football_source()
    CompetitionSourceRef.objects.create(
        source=source,
        competition=match.season.competition,
        external_id="1",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    MatchSourceRef.objects.create(
        source=source,
        match=match,
        external_id="1001",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    bsd, _ = record(
        match,
        Result("BSD", "2001", "FT", 2, 1, "HOME", NOW, {}),
        authoritative=True,
    )
    original_known = bsd.result_known_at
    payload = fixture_payload(
        fixture_id=1001,
        league_id=1,
        year=2026,
        status_short="FT",
        home_score=2,
        away_score=1,
        kickoff=NOW.isoformat(),
        home_name=match.home_team.name,
        away_name=match.away_team.name,
    )
    payload["score"]["fulltime"] = {"home": None, "away": None}

    class Client:
        calls = 0

        def get_all(self, endpoint, params):
            assert endpoint == "fixtures" and params["date"] == NOW.date().isoformat()
            self.calls += 1
            return [payload]

    client = Client()
    promoted = []
    monkeypatch.setattr(
        "football.result_routing.maybe_promote_shadow", lambda: promoted.append(True)
    )
    item = PlannedWork(
        purpose="RESULT_REFRESH",
        status="PLANNED",
        source=source,
        logical_identity="sentinel:week",
        intended_window="bsd-sentinel-probation",
        params={"date": NOW.date().isoformat(), "timezone": "America/Lima"},
        target_external_ids=("1001",),
    )
    CaptureExecutor._perform(client, item)
    assert client.calls == 1
    assert promoted == [True]
    api = ResultProviderObservation.objects.get(match=match, provider="API_FOOTBALL")
    assert (api.home_regulation, api.away_regulation, api.outcome) == (2, 1, "HOME")
    assert api.authoritative and not api.conflict
    bsd.refresh_from_db()
    match.refresh_from_db()
    assert bsd.result_known_at == original_known
    assert (match.fulltime_home_score, match.fulltime_away_score) == (2, 1)


def test_two_confirmed_bsd_conflicts_in_distinct_leagues_degrade_all_bsd_routes():
    from football.models import CompetitionResultRoute
    from football.result_routing import _confirmed_conflict

    routes = []
    for index in range(2):
        match = _match()
        route = CompetitionResultRoute.objects.create(
            competition=match.season.competition,
            api_football_league_id=index + 1,
            bsd_league_ids=[index + 1],
            bsd_state="BSD_PRIMARY_VALIDATED",
        )
        routes.append(route)
        record(
            match,
            Result("API_FOOTBALL", str(index), "FT", 2, 1, "HOME", NOW, {}),
            authoritative=True,
        )
        record(
            match,
            Result(
                "BSD", str(index), "FT", 1, 2, "AWAY", NOW + timedelta(minutes=1), {}
            ),
            authoritative=False,
        )
        _, disposition = record(
            match,
            Result(
                "BSD",
                str(index),
                "FT",
                1,
                2,
                "AWAY",
                NOW + timedelta(minutes=31),
                {},
            ),
            authoritative=False,
        )
        assert disposition == "RESULT_CONFLICT"
        _confirmed_conflict(match, NOW + timedelta(minutes=31))
    for route in routes:
        route.refresh_from_db()
        assert route.bsd_state == "BSD_DEGRADED"
        assert (
            route.provenance["bsd_global_degradation"] == "TWO_CONFIRMED_CONFLICTS_30D"
        )
