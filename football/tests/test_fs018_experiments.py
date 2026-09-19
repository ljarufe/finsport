"""Deterministic offline FS-018 contract and integration tests."""

import copy
import io
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from django.core.management import call_command
from django.core.management.base import CommandError

from football.experiments import (
    analysis,
    artifacts,
    backfill,
    mapping,
    provider,
    replay,
    runner,
    spec,
    storage,
)
from football.experiments.analysis import compare, paired_bootstrap, week_id
from football.experiments.market import reconstruct
from football.models import Competition, Match, OddsObservation, Season, Team
from football.prediction.contracts import (
    FailedPrediction,
    ProbabilityResult,
    UnavailablePrediction,
)

UTC = timezone.utc
KICKOFF = datetime(2026, 9, 17, 17, tzinfo=UTC)
CUTOFF = KICKOFF - timedelta(minutes=30)
FIXTURE = "id1000000872478570"
ORACLE = [
    [0.6346539639557827, 0.23621510951134744, 0.12913092653286992],
    [0.6160670280926566, 0.23410547067520948, 0.14982750123213406],
    [0.6380263717566993, 0.23606975754997875, 0.12590387069332198],
]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path, settings):
    settings.BASE_DIR = tmp_path
    settings.TIME_ZONE = "America/Lima"
    settings.FOOTBALL_PIPELINE_ENABLED = False
    settings.FOOTBALL_CAPTURE_ENABLED = False
    settings.CELERY_TASK_DEFAULT_QUEUE = "finsport.local.safe"
    monkeypatch.setenv("FINSPORT_EXPERIMENT_RUNTIME", "finsport-dev")
    monkeypatch.setenv("ODDSPAPI_API_KEY", "test-secret-do-not-serialize")
    monkeypatch.setattr(
        requests.Session,
        "get",
        Mock(side_effect=AssertionError("LIVE NETWORK FORBIDDEN")),
    )


def frozen(ids=(1278,)):
    selected = {
        "dixon_coles": {"xi": 0.001},
        "independent_poisson": {"xi": 0.002},
        "elo_multinomial_logit": {"k": 20, "C": 1.0},
    }
    configs = {
        str(i): {
            "selected": copy.deepcopy(selected),
            "executable": {
                code: spec.executable_config(code, selected[code.lower()])
                for code in spec.MODELS.keys() - {"MARKET_CONSENSUS"}
            },
            "identity": storage.identity(selected),
            "source": "test-current",
            "readiness_profiles": {},
        }
        for i in ids
    }
    return spec.ExperimentSpec(
        storage.canonical(
            {
                **spec.CONTRACT,
                "competition_ids": sorted(ids),
                "configs": configs,
                "tournament_map": {str(i): spec.TOURNAMENTS[i] for i in ids},
                "window_start": "2026-01-01T00:00:00+00:00",
                "data_cutoff": "2026-09-19T00:00:00+00:00",
                "runtime": {"name": "finsport-dev", "git_revision": "synthetic"},
            }
        )
    )


def payload(count=3):
    books = {}
    for book, fair in zip(spec.BOOKMAKERS[:count], ORACLE):
        books[book] = {
            "markets": {
                "101": {
                    "outcomes": {
                        outcome: {
                            "players": {
                                "0": [
                                    {
                                        "createdAt": CUTOFF.isoformat(),
                                        "price": 1 / (p * 1.04),
                                        "active": True,
                                    }
                                ]
                            }
                        }
                        for outcome, p in zip(("101", "102", "103"), fair)
                    }
                }
            }
        }
    return {"fixtureId": FIXTURE, "bookmakers": books}


def reconstruct_test(data):
    return reconstruct(data, fixture_id=FIXTURE, match_id=55300, kickoff=KICKOFF)


def test_spec_canonical_frozen_hash(tmp_path):
    value = frozen()
    reordered = spec.ExperimentSpec(json.dumps(value.data, indent=2))
    assert value.id == reordered.id
    data = value.data
    data["configs"]["1278"]["selected"]["dixon_coles"]["xi"] = 999
    assert value.data["configs"]["1278"]["selected"]["dixon_coles"]["xi"] == 0.001
    path = tmp_path / "spec.json"
    value.save(path)
    value.save(path)
    assert spec.ExperimentSpec.load(path) == value
    with pytest.raises(ValueError):
        frozen((1270,)).save(path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("evidence_profile", "FAKE"),
        ("models", {}),
        ("bootstrap", {}),
        ("tournament_map", {}),
        ("configs", {}),
        ("competition_ids", [999]),
        ("window_start", "2025-01-01T00:00:00Z"),
        ("data_cutoff", "2025-01-01T00:00:00Z"),
    ],
)
def test_spec_rejects_contract_changes(field, value):
    data = frozen().data
    data[field] = value
    with pytest.raises(ValueError):
        spec.ExperimentSpec(storage.canonical(data))


def test_freeze_current_config_source(monkeypatch):
    current = {
        "dixon_coles": {"xi": 0.7},
        "independent_poisson": {"xi": 0.3},
        "elo_multinomial_logit": {"k": 33, "C": 0.5},
    }
    monkeypatch.setattr(
        spec, "latest_selected_config", lambda c: (current, "experiment:42")
    )
    monkeypatch.setattr(spec, "active_profile", lambda *a, **k: None)
    value = spec.freeze_spec([SimpleNamespace(pk=1278)], "2026-09-19T00:00:00Z")
    current["dixon_coles"]["xi"] = 100
    assert value.data["configs"]["1278"]["selected"]["dixon_coles"]["xi"] == 0.7
    assert value.data["configs"]["1278"]["source"] == "experiment:42"


@pytest.mark.parametrize(
    "count,status",
    [(0, "UNAVAILABLE"), (1, "UNAVAILABLE"), (2, "PRODUCED"), (3, "PRODUCED")],
)
def test_market_book_count_and_oracle(count, status):
    result = reconstruct_test(payload(count))
    assert result["status"] == status
    assert result["book_count"] == count
    assert result["model_version"] == "fs013-market-consensus-v2"
    assert result["evidence_profile"] == spec.PROFILE
    assert result["evidence_class"] == "HISTORICAL_RESEARCH"
    if count >= 2:
        assert result["probabilities"] == pytest.approx(
            [sum(v[i] for v in ORACLE[:count]) / count for i in range(3)]
        )
    if count == 3:
        assert result["probabilities"] == pytest.approx(
            [0.6295824546017128, 0.23546344591217858, 0.13495409948610868]
        )


@pytest.mark.parametrize(
    "state",
    [
        {
            "createdAt": (CUTOFF + timedelta(microseconds=1)).isoformat(),
            "price": 1.1,
            "active": True,
        },
        {"createdAt": CUTOFF.isoformat(), "price": 1.1, "active": False},
        {"createdAt": CUTOFF.isoformat(), "price": 1.1, "active": "true"},
        {"createdAt": CUTOFF.isoformat(), "price": 1, "active": True},
        {"createdAt": CUTOFF.isoformat(), "price": "NaN", "active": True},
        {"createdAt": "bad", "price": 1.1, "active": True},
    ],
)
def test_market_ignores_future_inactive_invalid_states(state):
    data = payload()
    before = reconstruct_test(data)
    data["bookmakers"]["pinnacle"]["markets"]["101"]["outcomes"]["101"]["players"][
        "0"
    ].append(state)
    result = reconstruct_test(data)
    assert result["probabilities"] == before["probabilities"]


def test_market_selects_latest_valid_and_requires_exact_ids():
    data = payload()
    legs = data["bookmakers"]["pinnacle"]["markets"]["101"]["outcomes"]
    legs["101"]["players"]["0"].insert(
        0,
        {
            "createdAt": (CUTOFF - timedelta(days=1)).isoformat(),
            "active": True,
            "price": 9,
        },
    )
    assert (
        reconstruct_test(data)["books"]["pinnacle"]["legs"][0]["quote_age_seconds"]
        == 1800
    )
    del legs["103"]["players"]["0"]
    assert reconstruct_test(data)["book_count"] == 2
    data["bookmakers"]["bet365"]["markets"]["other"] = data["bookmakers"]["bet365"][
        "markets"
    ].pop("101")
    assert reconstruct_test(data)["status"] == "UNAVAILABLE"


def test_conflicting_timestamp_fails_closed():
    data = payload(2)
    series = data["bookmakers"]["pinnacle"]["markets"]["101"]["outcomes"]["101"][
        "players"
    ]["0"]
    series.append({**series[0], "price": 9})
    assert reconstruct_test(data)["status"] == "UNAVAILABLE"


def fixture_row():
    return {
        "fixtureId": FIXTURE,
        "tournamentId": 8,
        "statusId": 2,
        "startTime": KICKOFF.isoformat(),
        "participant1Name": "Real Betis Seville",
        "participant2Name": "Getafe CF",
    }


@pytest.mark.parametrize(
    "change", ["duplicate", "tournament", "status", "name", "shape", "window"]
)
def test_discovery_validation(change):
    row = fixture_row()
    data = [row]
    if change == "duplicate":
        data.append(row.copy())
    elif change == "tournament":
        row["tournamentId"] = 17
    elif change == "status":
        row["statusId"] = 1
    elif change == "name":
        del row["participant1Name"]
    elif change == "shape":
        data = {}
    else:
        row["startTime"] = "2025-01-01T00:00:00Z"
    with pytest.raises(provider.ProviderError):
        provider.validate_fixtures(
            data, 8, "2026-01-01T00:00:00Z", "2026-09-19T00:00:00Z"
        )


@pytest.fixture
def canonical_match(db):
    c = Competition.objects.create(
        pk=1278, name="La Liga", country="ES", competition_type="League", enabled=True
    )
    season = Season.objects.create(competition=c, year=2026)
    home = Team.objects.create(competition=c, name="Real Betis")
    away = Team.objects.create(competition=c, name="Getafe")
    match = Match.objects.create(
        id=55300,
        season=season,
        home_team=home,
        away_team=away,
        kickoff=KICKOFF,
        status_short="FT",
        home_score=1,
        away_score=0,
        outcome="HOME",
    )
    return c, match


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("zero", "UNMATCHED"),
        ("one", "MATCHED"),
        ("two", "AMBIGUOUS"),
        ("missing_team", "MATCHED"),
    ],
)
def test_mapping_cardinality(canonical_match, monkeypatch, mode, expected):
    c, match = canonical_match
    fixture = provider.validate_fixtures(
        [fixture_row()], 8, "2026-01-01T00:00:00Z", "2026-09-19T00:00:00Z"
    )[0]
    if mode == "zero":
        fixture["kickoff"] = (KICKOFF + timedelta(hours=1)).isoformat()
    elif mode == "two":
        Match.objects.create(
            season=match.season,
            home_team=match.home_team,
            away_team=match.away_team,
            kickoff=KICKOFF + timedelta(minutes=10),
        )
    elif mode == "missing_team":
        monkeypatch.setattr(mapping, "find_team_candidate", lambda *a: (None, 0))
    result = mapping.map_fixture(c, fixture)
    assert result["status"] == expected
    if mode == "one":
        assert result["match_id"] == 55300
        assert result["home_confidence"] == pytest.approx(2 / 3)
        assert result["away_confidence"] == 0.5
    assert (
        not c.matchsourceref_set.exists() if hasattr(c, "matchsourceref_set") else True
    )


class Clock:
    def __init__(self):
        self.now = 1000
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def response(data, status=200):
    return SimpleNamespace(
        status_code=status, json=lambda: data, headers={"ETag": "fake-etag"}
    )


@pytest.mark.parametrize("endpoint,spacing", [("fixtures", 2), ("historical-odds", 10)])
def test_client_cooldown_cache_and_request_shape(endpoint, spacing):
    clock = Clock()
    calls = []
    session = SimpleNamespace(
        get=lambda url, **kwargs: calls.append((clock.time(), url, kwargs))
        or response({"safe": True})
    )
    client = provider.OddsPapiClient(
        session=session, clock=clock.time, sleep=clock.sleep
    )
    first = client.request(endpoint, {"id": 1})
    second = client.request(endpoint, {"id": 1})
    client.request(endpoint, {"id": 2})
    assert first[1] == "FETCHED" and second[1] == "CACHED"
    assert len(calls) == 2 and calls[1][0] - calls[0][0] >= spacing
    assert calls[0][2]["timeout"] == (10, 60)
    assert not calls[0][2]["allow_redirects"]
    assert all(
        "test-secret" not in p.read_text() for p in storage.roots()[0].glob("*.json")
    )
    with storage.lock(storage.roots()[0] / "duplicate.lock"):
        with pytest.raises(ValueError, match="ALREADY_RUNNING"):
            with storage.lock(storage.roots()[0] / "duplicate.lock"):
                pass


@pytest.mark.parametrize(
    "failure,classification,attempts",
    [
        (401, "ACCESS_DENIED", 1),
        (404, "NOT_FOUND", 1),
        (429, "RATE_LIMITED", 3),
        (503, "UPSTREAM_ERROR", 3),
        (302, "HTTP_REJECTED", 1),
        (0, "NETWORK_ERROR", 3),
    ],
)
def test_client_bounded_errors_are_secret_safe(
    failure, classification, attempts, caplog
):
    clock = Clock()
    session = Mock()
    if failure:
        session.get.return_value = response(
            {"secret": "test-secret-do-not-serialize"}, failure
        )
    else:
        session.get.side_effect = requests.ConnectionError(
            "https://secret?apiKey=test-secret-do-not-serialize"
        )
    client = provider.OddsPapiClient(
        session=session, clock=clock.time, sleep=clock.sleep
    )
    with pytest.raises(provider.ProviderError, match=classification) as error:
        client.historical(FIXTURE)
    assert session.get.call_count == attempts
    assert "test-secret" not in str(error.value) + caplog.text


def test_secret_echo_rejected():
    session = Mock(
        get=Mock(return_value=response({"apiKey": "test-secret-do-not-serialize"}))
    )
    with pytest.raises(provider.ProviderError, match="SECRET_ECHO_REJECTED"):
        provider.OddsPapiClient(session=session).historical(FIXTURE)


def test_backfill_resume_no_reacquisition_and_readonly(canonical_match):
    client = Mock()
    fixtures = provider.validate_fixtures(
        [fixture_row()], 8, "2026-01-01T00:00:00Z", "2026-09-19T00:00:00Z"
    )
    client.fixtures.return_value = (fixtures, "FETCHED")
    client.historical.side_effect = [KeyboardInterrupt(), (payload(), "FETCHED")]
    value = frozen()
    with pytest.raises(KeyboardInterrupt):
        backfill.backfill(value, client=client, pilot=True)
    result = backfill.backfill(value, client=client, pilot=True)
    assert result["status"] == "COMPLETE"
    state = storage.read_json(result["checkpoint"])
    assert state["leagues"]["1278"]["counts"] == {"RECONSTRUCTED": 1}
    backfill.backfill(value, client=client, pilot=True)
    assert client.fixtures.call_count == 1
    assert client.historical.call_count == 2
    assert OddsObservation.objects.count() == 0
    with storage.lock(storage.roots()[1] / result["run_id"] / "backfill.lock"):
        with pytest.raises(ValueError, match="ALREADY_RUNNING"):
            backfill.backfill(value, client=client, pilot=True)


def fake_match(pk, when):
    return SimpleNamespace(
        id=pk,
        kickoff=when,
        season=SimpleNamespace(year=2026),
        home_team_id=1,
        away_team_id=2,
        home_score=1,
        away_score=0,
        outcome="HOME",
    )


def test_replay_strict_lima_day_and_frozen_config():
    history = [fake_match(1, datetime(2026, 1, 1, 23, tzinfo=UTC))]
    targets = [
        fake_match(2, datetime(2026, 1, 2, 4, tzinfo=UTC)),
        fake_match(3, datetime(2026, 1, 2, 5, tzinfo=UTC)),
        fake_match(4, datetime(2026, 1, 2, 20, tzinfo=UTC)),
    ]
    fits = []

    class Adapter:
        config = {}

        def __init__(self, code, config):
            self.model_version = spec.MODELS[code]
            self.code, self.config = code, config

        def fit(self, training, cutoff, *args, **kwargs):
            fits.append((self.code, self.config, [m.id for m in training], cutoff))
            return self

        fit_for_targets = fit

        def predict(self, match, cutoff):
            return ProbabilityResult(0.5, 0.3, 0.2)

    result, _ = replay.sporting_replay(
        history + targets, targets, frozen().data["configs"]["1278"], factory=Adapter
    )
    assert len(result) == 3
    assert len(fits) == 6
    assert all(ids == [] for _, _, ids, _ in fits[:3])
    assert all(ids == [1, 2] for _, _, ids, _ in fits[3:])
    assert fits[0][1]["xi"] == 0.001


@pytest.mark.parametrize(
    "kind", ["unavailable", "fit_error", "predict_error", "failed"]
)
def test_replay_classified_outcomes(kind):
    class Adapter:
        model_version = ""
        config = {}

        def fit(self, *a, **k):
            if kind == "unavailable":
                return UnavailablePrediction("NO_HISTORY")
            if kind == "failed":
                return FailedPrediction("BAD_FIT")
            if kind == "fit_error":
                raise RuntimeError("unsafe details")
            return self

        fit_for_targets = fit

        def predict(self, *a):
            raise RuntimeError("unsafe details")

    def factory(code, config):
        obj = Adapter()
        obj.model_version = spec.MODELS[code]
        return obj

    match = fake_match(1, KICKOFF)
    result, _ = replay.sporting_replay(
        [match], [match], frozen().data["configs"]["1278"], factory=factory
    )
    assert {x["status"] for x in result[1].values()} == {
        "UNAVAILABLE" if kind == "unavailable" else "FAILED"
    }


def manifest(competitions=(1270, 1278), *, partial=False, identical=False):
    rows = []
    for competition in competitions:
        for i in range(4 if competition == 1270 else 8):
            candidates = {
                code: {
                    "status": "PRODUCED",
                    "reason": "",
                    "probabilities": (
                        [0.6, 0.2, 0.2]
                        if identical or competition == 1270
                        else [0.3, 0.4, 0.3]
                    ),
                }
                for code in spec.MODELS
            }
            if partial and competition == 1270:
                candidates["MARKET_CONSENSUS"] = {
                    "status": "UNAVAILABLE",
                    "reason": "NO_MARKET",
                }
            rows.append(
                {
                    "match_id": competition * 100 + i,
                    "competition_id": competition,
                    "kickoff": (KICKOFF - timedelta(days=i * 7)).isoformat(),
                    "outcome": "HOME",
                    "eligible": True,
                    "candidates": candidates,
                }
            )
    return rows


def resources():
    return {code: {"seconds": 1, "rss_mib": 100} for code in spec.MODELS}


def test_cohorts_equal_league_metrics_partial_market_and_fallback():
    import math

    result = compare(manifest(partial=True), spec.MODELS, [1270, 1278], resources())
    assert len(result["cohorts"]["COMMON"]) == 12
    market = result["candidates"]["MARKET_CONSENSUS"]
    assert not market["global_eligible"] and market["role"] == "PARTIAL_DIAGNOSTIC"
    assert market["unavailable_count"] == 4
    assert result["selected"] != "MARKET_CONSENSUS"
    assert result["disposition"] == "NO_CLEAR_SUPERIORITY"
    dc = result["candidates"]["DIXON_COLES"]
    assert dc["primary_score"] == pytest.approx((-math.log(0.6) - math.log(0.3)) / 2)
    assert dc["primary_score"] != pytest.approx(dc["COMMON"]["log_loss"])
    assert dc["per_league"]["1270"]["COMMON"]["multiclass_brier"] == pytest.approx(0.24)
    assert dc["per_league"]["1270"]["COMMON"]["rps"] == pytest.approx(0.1)


def test_confirmation_selects_best_common_score_not_highest_coverage():
    rows = manifest()
    for index, row in enumerate(rows):
        for code in spec.MODELS:
            row["candidates"][code] = {
                "status": "PRODUCED",
                "reason": "",
                "probabilities": [0.45, 0.30, 0.25],
            }
        row["candidates"]["MARKET_CONSENSUS"] = {
            "status": "PRODUCED",
            "reason": "",
            "probabilities": [0.80, 0.10, 0.10],
        }
        # Reduce Market NATURAL coverage in both leagues without removing its
        # global eligibility. These rows are excluded from COMMON for all arms.
        if index in {0, 4}:
            row["candidates"]["MARKET_CONSENSUS"] = {
                "status": "UNAVAILABLE",
                "reason": "NO_MARKET",
            }

    standard = compare(rows, spec.MODELS, [1270, 1278], resources())
    confirmation = compare(
        rows,
        spec.MODELS,
        [1270, 1278],
        resources(),
        selection_policy=analysis.PAIRED_COMMON_SELECTION_POLICY,
    )

    assert standard["selected"] != "MARKET_CONSENSUS"
    assert confirmation["selected"] == "MARKET_CONSENSUS"
    assert confirmation["score_order"][0] == "MARKET_CONSENSUS"
    assert confirmation["coverage_used_for_selection"] is False
    assert confirmation["natural_used_for_selection"] is False
    assert (
        confirmation["candidates"]["MARKET_CONSENSUS"]["coverage"]
        < confirmation["candidates"]["ELO_MULTINOMIAL_LOGIT"]["coverage"]
    )
    common_n = len(confirmation["cohorts"]["COMMON"])
    assert common_n > 0
    assert all(
        row["COMMON"]["sample_count"] == common_n
        for row in confirmation["candidates"].values()
    )


def test_confirmation_requires_all_four_candidates_in_every_league():
    result = compare(
        manifest(partial=True),
        spec.MODELS,
        [1270, 1278],
        resources(),
        selection_policy=analysis.PAIRED_COMMON_SELECTION_POLICY,
    )
    assert result["selected"] is None
    assert result["disposition"] == "INSUFFICIENT_EVIDENCE"
    assert result["selection_failure"] == "ALL_FOUR_GLOBAL_CANDIDATES_REQUIRED"
    assert result["cohorts"]["COMMON"] == []


def test_common_exclusions_and_empty_league():
    rows = manifest()
    rows[0]["candidates"]["DIXON_COLES"] = {"status": "FAILED", "reason": "BAD_FIT"}
    result = compare(rows, spec.MODELS, [1270, 1278], resources())
    assert len(result["cohorts"]["COMMON"]) == 11
    assert (
        result["common_exclusions"][str(rows[0]["match_id"])]["DIXON_COLES"]
        == "BAD_FIT"
    )
    result = compare(rows, spec.MODELS, [1270, 1278, 1273], resources())
    assert result["disposition"] == "INSUFFICIENT_EVIDENCE"
    assert result["selected"] is None


def test_bootstrap_paired_stratified_deterministic_lima_week():
    rows = manifest(identical=True)
    first = paired_bootstrap(rows, list(spec.MODELS), [1270, 1278])
    assert first == paired_bootstrap(rows, list(spec.MODELS), [1270, 1278])
    assert first["replicates"] == 5000 and first["seed"] == 18092026
    assert set(first["blocks"]) == {"1270", "1278"}
    assert all(
        v["lower"] == v["upper"] == 0 for v in first["paired_intervals"].values()
    )
    assert week_id("2026-01-05T04:59:00Z") == "2026-W01"
    assert week_id("2026-01-05T05:00:00Z") == "2026-W02"


def test_future_challenger_reuses_comparison():
    rows = manifest(identical=True)
    for row in rows:
        row["candidates"]["FUTURE_CHALLENGER"] = {
            "status": "PRODUCED",
            "reason": "",
            "probabilities": [0.8, 0.1, 0.1],
        }
    result = compare(
        rows,
        {**spec.MODELS, "FUTURE_CHALLENGER": "test-v1"},
        [1270, 1278],
        {**resources(), "FUTURE_CHALLENGER": {"seconds": 1, "rss_mib": 100}},
    )
    assert result["selected"] == "FUTURE_CHALLENGER"
    assert result["disposition"] == "CLEAR_SUPERIORITY"


def test_runner_offline_readonly_idempotent_and_pilot_cannot_promote(canonical_match):
    client = Mock()
    client.fixtures.return_value = (
        provider.validate_fixtures(
            [fixture_row()], 8, "2026-01-01T00:00:00Z", "2026-09-19T00:00:00Z"
        ),
        "FETCHED",
    )
    client.historical.return_value = (payload(), "FETCHED")
    value = frozen()
    backfill.backfill(value, client=client, pilot=True)
    before = (Match.objects.count(), OddsObservation.objects.count())
    result = runner.run_experiment(value, pilot=True)
    assert result == runner.run_experiment(value, pilot=True)
    original_path = storage.roots()[1] / result["analysis_id"] / "run.json"
    original_bytes = original_path.read_bytes()
    confirmed = runner.run_experiment(value, pilot=True, confirm=True)
    assert confirmed["analysis_mode"] == "FRESH_CONFIRMATION_V2"
    assert (
        confirmed["summary"]["selection_policy"]
        == analysis.PAIRED_COMMON_SELECTION_POLICY
    )
    assert confirmed["analysis_id"] != result["analysis_id"]
    assert confirmed["run_id"] != result["run_id"]
    assert confirmed["source_acquisition_id"] == result["source_acquisition_id"]
    assert runner.run_experiment(value, pilot=True, confirm=True) == confirmed
    assert original_path.read_bytes() == original_bytes
    assert (
        storage.roots()[1] / confirmed["analysis_id"] / "sporting-1278.json"
    ).exists()
    assert (
        result["manifest"][0]["candidates"]["MARKET_CONSENSUS"]["status"] == "PRODUCED"
    )
    assert before == (Match.objects.count(), OddsObservation.objects.count())
    with pytest.raises(ValueError, match="FULL_VALID"):
        artifacts.promotion_record(result)


def test_execution_runtime_changes_analysis_not_acquisition(
    canonical_match, monkeypatch
):
    client = Mock()
    client.fixtures.return_value = (
        provider.validate_fixtures(
            [fixture_row()], 8, "2026-01-01T00:00:00Z", "2026-09-19T00:00:00Z"
        ),
        "FETCHED",
    )
    client.historical.return_value = (payload(), "FETCHED")
    value = frozen()
    acquired = backfill.backfill(value, client=client, pilot=True)
    acquisition_bytes = (
        storage.roots()[1] / acquired["run_id"] / "backfill.json"
    ).read_bytes()
    runtime = {
        "name": "finsport-dev",
        "python": "3.13",
        "git_revision": "test-revision",
        "dirty": False,
        "code_identity": "runtime-A",
        "dependencies": {"Django": "test-version"},
    }
    monkeypatch.setattr(runner, "execution_runtime", lambda: copy.deepcopy(runtime))
    first = runner.run_experiment(value, pilot=True, confirm=True)
    assert runner.run_experiment(value, pilot=True, confirm=True) == first
    assert first["execution_runtime_id"] == storage.identity(runtime)
    runtime["code_identity"] = "runtime-B"
    second = runner.run_experiment(value, pilot=True, confirm=True)
    assert second["analysis_id"] != first["analysis_id"]
    assert second["run_id"] != first["run_id"]
    assert (
        second["source_acquisition_id"]
        == first["source_acquisition_id"]
        == acquired["run_id"]
    )
    assert (
        second["spec"]["runtime"] == first["spec"]["runtime"] == value.data["runtime"]
    )
    assert runner.run_experiment(value, pilot=True, confirm=True) == second
    runner.verify_run(
        first, value
    )  # Verifying old evidence does not use this machine's runtime.
    tampered = copy.deepcopy(first)
    tampered["execution_runtime_id"] = "incorrect"
    tampered["run_id"] = storage.identity(
        {k: v for k, v in tampered.items() if k != "run_id"}
    )
    with pytest.raises(ValueError, match="EXECUTION_RUNTIME_IDENTITY_MISMATCH"):
        runner.verify_run(tampered, value)
    tampered = copy.deepcopy(first)
    tampered["analysis_id"] = "incorrect"
    tampered["run_id"] = storage.identity(
        {k: v for k, v in tampered.items() if k != "run_id"}
    )
    with pytest.raises(ValueError, match="ANALYSIS_LINEAGE_MISMATCH"):
        runner.verify_run(tampered, value)
    assert (
        storage.roots()[1] / acquired["run_id"] / "backfill.json"
    ).read_bytes() == acquisition_bytes
    assert client.historical.call_count == 1


def test_promotion_lineage_immutable(tmp_path):
    value = frozen(tuple(spec.TOURNAMENTS))
    rows = manifest(tuple(spec.TOURNAMENTS), identical=True)
    rows.sort(key=lambda r: (r["competition_id"], r["kickoff"], r["match_id"]))
    summary = compare(rows, spec.MODELS, sorted(spec.TOURNAMENTS), resources())
    run = {
        "spec_id": value.id,
        "spec": value.data,
        "manifest": rows,
        "summary": summary,
        "resources": {},
        "acquisition": {
            "pilot": False,
            "status": "COMPLETE",
            "run_id": "fake-test-only",
            "leagues": {str(i): {} for i in spec.TOURNAMENTS},
        },
    }
    run["run_id"] = storage.identity(run)
    original = storage.canonical(run)
    record = artifacts.promote(run, base=tmp_path)
    assert record["baseline"] == "GLOBAL_PREDICTION_V1"
    assert record["effective_config"] == artifacts.effective_baseline_config(
        value.data, record["model_code"]
    )
    assert record["config_identity"] == storage.identity(record["effective_config"])
    report_path = tmp_path / artifacts.REPORT_REF
    storage.atomic_text(report_path, "Compact maintainer-authored report\n")
    assert record == artifacts.promote(run, base=tmp_path)
    assert report_path.read_text() == "Compact maintainer-authored report\n"
    assert storage.canonical(run) == original
    assert (tmp_path / artifacts.REPORT_REF).exists()
    changed = copy.deepcopy(run)
    changed["summary"]["selected"] = "ELO_MULTINOMIAL_LOGIT"
    changed["run_id"] = storage.identity(
        {k: v for k, v in changed.items() if k != "run_id"}
    )
    with pytest.raises(ValueError, match="ALREADY_FROZEN"):
        artifacts.promote(changed, base=tmp_path)


def test_provisional_replacement_resumes_after_interruption(tmp_path, monkeypatch):
    old_record = {"full_run_id": "old-run", "baseline": "GLOBAL_PREDICTION_V1"}
    new_record = {"full_run_id": "new-run", "baseline": "GLOBAL_PREDICTION_V1"}
    path = tmp_path / artifacts.PROMOTION_REF
    report_path = tmp_path / artifacts.REPORT_REF
    backup = (
        tmp_path
        / "tmp/FS-018_experiments/provisional-backups"
        / old_record["full_run_id"]
    )
    storage.atomic_json(path, old_record)
    storage.atomic_text(report_path, "old report")
    monkeypatch.setattr(artifacts, "promotion_record", lambda run: new_record)
    monkeypatch.setattr(artifacts, "human_report", lambda run: "new report")
    monkeypatch.setattr(
        artifacts.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )
    run = {
        "analysis_mode": "FRESH_CONFIRMATION_V2",
        "spec": {"acquisition": {"mode": "RECOVERY_V1"}},
    }

    # Simulate a reboot after only the first backup write.
    storage.atomic_json(backup / "record.json", old_record)
    result = artifacts.promote(
        run,
        base=tmp_path,
        replace_provisional=True,
        expected_previous_run_id="old-run",
    )
    assert result == new_record
    assert storage.read_json(path) == new_record
    assert report_path.read_text() == "new report"
    assert storage.read_json(backup / "record.json") == old_record
    assert (backup / "report.md").read_text() == "old report"

    # Simulate the other resumable state: report replaced, record still old.
    storage.atomic_json(path, old_record)
    storage.atomic_text(report_path, "new report")
    result = artifacts.promote(
        run,
        base=tmp_path,
        replace_provisional=True,
        expected_previous_run_id="old-run",
    )
    assert result == new_record
    assert storage.read_json(path) == new_record
    assert report_path.read_text() == "new report"
    assert storage.read_json(backup / "record.json") == old_record
    assert (backup / "report.md").read_text() == "old report"


def test_commands_and_task_registration(monkeypatch, settings):
    from finsport.celery import app
    from football.tasks import oddspapi_historical_backfill

    app.autodiscover_tasks(force=True)
    assert "football.experiments.oddspapi_historical_backfill" in app.tasks
    assert all("oddspapi" not in str(v) for v in app.conf.beat_schedule.values())
    path = storage.roots()[1] / "spec.json"
    frozen().save(path)
    enqueue = Mock(return_value=SimpleNamespace(id="offline-task"))
    monkeypatch.setattr(app, "send_task", enqueue)
    settings.DEBUG = True
    settings.CELERY_TASK_ALWAYS_EAGER = True
    monkeypatch.setattr(
        oddspapi_historical_backfill,
        "apply_async",
        Mock(side_effect=AssertionError("INLINE_TASK_FORBIDDEN")),
    )
    output = io.StringIO()
    call_command(
        "enqueue_oddspapi_historical_backfill",
        spec=str(path),
        pilot=True,
        allow_network=True,
        stdout=output,
    )
    assert "offline-task" in output.getvalue()
    assert enqueue.call_args.kwargs["queue"] == "finsport.local.safe"
    assert enqueue.call_args.args == (
        "football.experiments.oddspapi_historical_backfill",
    )
    with pytest.raises(CommandError, match="allow-network"):
        call_command("enqueue_oddspapi_historical_backfill", spec=str(path))
    monkeypatch.delenv("FINSPORT_EXPERIMENT_RUNTIME")
    with pytest.raises(CommandError, match="ISOLATED"):
        call_command("run_prediction_experiment", spec=str(path))


@pytest.mark.parametrize(
    "flag", ["FOOTBALL_PIPELINE_ENABLED", "FOOTBALL_CAPTURE_ENABLED"]
)
def test_safety_guard(settings, flag):
    setattr(settings, flag, True)
    with pytest.raises(ValueError, match="ISOLATED"):
        storage.require_dev()


def test_atomic_interruption_keeps_previous_file(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    storage.atomic_json(path, {"step": 1})
    monkeypatch.setattr(storage.os, "replace", Mock(side_effect=OSError("interrupted")))
    with pytest.raises(OSError):
        storage.atomic_json(path, {"step": 2})
    assert storage.read_json(path) == {"step": 1}
    assert not list(tmp_path.glob(".pending-*"))


def test_cache_survives_interrupted_reconstruction(canonical_match, monkeypatch):
    clock = Clock()
    calls = []

    def get(url, **kwargs):
        calls.append((url.rsplit("/", 1)[-1], kwargs["params"].copy()))
        return response([fixture_row()] if url.endswith("fixtures") else payload())

    client = provider.OddsPapiClient(
        session=SimpleNamespace(get=get), clock=clock.time, sleep=clock.sleep
    )
    original = backfill.reconstruct
    monkeypatch.setattr(backfill, "reconstruct", Mock(side_effect=KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        backfill.backfill(frozen(), client=client, pilot=True)
    monkeypatch.setattr(backfill, "reconstruct", original)
    result = backfill.backfill(frozen(), client=client, pilot=True)
    assert result["status"] == "COMPLETE" and len(calls) == 2
    state = storage.read_json(result["checkpoint"])
    assert state["leagues"]["1278"]["fixtures"][FIXTURE]["acquisition"] == "CACHED"
    assert calls[1][1]["bookmakers"] == "pinnacle,bet365,unibet"
    assert calls[1][1]["fixtureId"] == FIXTURE
    assert calls[0][1]["tournamentId"] == 8


def test_pilot_missing_fixture_never_becomes_false_complete(canonical_match):
    client = Mock()
    client.fixtures.return_value = ([], "CACHED")
    for _ in range(2):
        result = backfill.backfill(frozen(), client=client, pilot=True)
        assert result["status"] == "FAILED"


def test_client_account_whitelist_missing_key_and_cache_integrity(monkeypatch):
    session = Mock(
        get=Mock(
            return_value=response(
                {
                    "current_subscription_id": "sub-1",
                    "api_key": "test-secret-do-not-serialize",
                    "email": "private",
                    "subscriptions": [
                        {
                            "subscription_id": "sub-1",
                            "is_active": True,
                            "request_limit": 250,
                            "request_count": 17,
                        }
                    ],
                }
            )
        )
    )
    client = provider.OddsPapiClient(session=session)
    assert client.account() == {"request_limit": 250, "request_count": 17}
    session.get.return_value = response({"safe": True})
    client.historical(FIXTURE)
    path = next(
        p for p in storage.roots()[0].glob("*.json") if p.name != "traffic-clock.json"
    )
    cached = storage.read_json(path)
    cached["payload"]["request_count"] = 99
    storage.atomic_json(path, cached)
    with pytest.raises(provider.ProviderError, match="CACHE_HASH_MISMATCH"):
        client.historical(FIXTURE)
    monkeypatch.delenv("ODDSPAPI_API_KEY")
    with pytest.raises(provider.ProviderError, match="MISSING_ODDSPAPI"):
        client.historical("uncached")


def test_account_only_command_projects_echoed_key(monkeypatch):
    command = __import__(
        "football.management.commands.enqueue_oddspapi_historical_backfill",
        fromlist=["Command"],
    )
    account = Mock(return_value={"request_limit": 250, "request_count": 17})
    monkeypatch.setattr(command.OddsPapiClient, "account", account)
    output = io.StringIO()
    call_command(
        "enqueue_oddspapi_historical_backfill",
        account_only=True,
        allow_network=True,
        stdout=output,
    )
    assert json.loads(output.getvalue()) == {"request_limit": 250, "request_count": 17}
    assert "api_key" not in output.getvalue()


def test_retry_after_and_persisted_terminal_cooldown():
    clock = Clock()
    attempts = []

    def get(url, **kwargs):
        attempts.append(clock.time())
        return SimpleNamespace(
            status_code=429,
            json=lambda: {},
            headers={"Retry-After": "37"},
        )

    first = provider.OddsPapiClient(
        session=SimpleNamespace(get=get), clock=clock.time, sleep=clock.sleep
    )
    with pytest.raises(provider.ProviderError, match="RATE_LIMITED"):
        first.historical(FIXTURE)
    assert [b - a for a, b in zip(attempts, attempts[1:])] == [37, 37]
    traffic = storage.read_json(storage.roots()[0] / "traffic-clock.json")
    assert traffic["historical-odds:not_before"] == clock.time() + 37
    second = provider.OddsPapiClient(
        session=SimpleNamespace(get=lambda url, **kwargs: response({"safe": True})),
        clock=clock.time,
        sleep=clock.sleep,
    )
    assert second.historical(FIXTURE)[1] == "FETCHED"
    assert clock.sleeps[-1] >= 37
    audit = storage.read_json(storage.roots()[1] / "standalone-traffic.json")
    assert audit["http_429"] == 3 and audit["retries"] == 2
    assert audit["physical_calls"]["historical-odds"] == 4


def test_retry_backoff_increases_without_header():
    clock = Clock()
    client = provider.OddsPapiClient(
        session=SimpleNamespace(
            get=lambda url, **kwargs: SimpleNamespace(
                status_code=429, json=lambda: {}, headers={}
            )
        ),
        clock=clock.time,
        sleep=clock.sleep,
    )
    with pytest.raises(provider.ProviderError, match="RATE_LIMITED"):
        client.historical(FIXTURE)
    assert clock.sleeps == [10, 20]


def test_contextual_ordered_pair_mapping(canonical_match, monkeypatch):
    c, match = canonical_match
    espanyol = Team.objects.create(competition=c, name="Espanyol")
    barcelona = Team.objects.create(competition=c, name="Barcelona")
    Match.objects.create(
        season=match.season,
        home_team=espanyol,
        away_team=match.away_team,
        kickoff=KICKOFF,
    )
    Match.objects.create(
        season=match.season,
        home_team=barcelona,
        away_team=match.home_team,
        kickoff=KICKOFF,
    )
    fixture = {
        "home_name": "Espanyol Barcelona",
        "away_name": "Getafe CF",
        "kickoff": KICKOFF.isoformat(),
    }
    monkeypatch.setattr(mapping, "find_team_candidate", lambda *a: (None, 0))
    result = mapping.map_fixture(c, fixture)
    assert result["status"] == "MATCHED"
    assert result["match_id"] != match.pk
    assert result["method"] == mapping.MAPPING_POLICY["version"]
    assert result["confidence"] >= mapping.MAPPING_POLICY["minimum_pair"]
    swapped = mapping.map_fixture(
        c, {**fixture, "home_name": "Getafe CF", "away_name": "Espanyol Barcelona"}
    )
    assert swapped["status"] == "UNMATCHED"
    conflict = mapping.map_fixture(
        c, {**fixture, "home_name": "Arsenal", "away_name": "Liverpool"}
    )
    assert conflict["status"] == "UNMATCHED"
    Match.objects.create(
        season=match.season,
        home_team=espanyol,
        away_team=match.away_team,
        kickoff=KICKOFF + timedelta(minutes=5),
    )
    assert mapping.map_fixture(c, fixture)["status"] == "AMBIGUOUS"


def test_mapping_policy_changes_spec_and_acquisition_identity():
    value = frozen(tuple(spec.TOURNAMENTS))
    changed = copy.deepcopy(value.data)
    changed["mapping_policy"]["version"] = "another-policy"
    assert changed["mapping_policy"] != spec.CONTRACT["mapping_policy"]
    with pytest.raises(ValueError, match="methodology mismatch"):
        spec.ExperimentSpec(storage.canonical(changed))
    recovery = copy.deepcopy(value.data)
    recovery["acquisition"] = {
        "mode": "RECOVERY_V1",
        "source_spec_id": value.id,
        "source_run_id": storage.identity({"spec_id": value.id, "pilot": False}),
    }
    new = spec.ExperimentSpec(storage.canonical(recovery))
    assert new.id != value.id
    assert (
        storage.identity({"spec_id": new.id, "pilot": False})
        != recovery["acquisition"]["source_run_id"]
    )


def test_recovery_refreshes_once_and_reuses_successful_history(canonical_match):
    value = frozen()
    old_run_id = storage.identity({"spec_id": value.id, "pilot": False})
    source_path = storage.roots()[1] / old_run_id / "backfill.json"
    statuses = {
        "successful": "RECONSTRUCTED",
        "not-found": "FAILED",
        "one-book": "NO_USABLE_T30",
        "formerly-unmatched": "UNMATCHED",
    }
    source_only_fixture = provider.validate_fixtures(
        [fixture_row()], 8, "2026-01-01T00:00:00Z", "2026-09-19T00:00:00Z"
    )[0]
    source_only_fixture["fixture_id"] = "source-only"
    source = {
        "run_id": old_run_id,
        "spec_id": value.id,
        "status": "PARTIAL",
        "leagues": {
            "1278": {
                "fixtures": {
                    **{k: {"status": v} for k, v in statuses.items()},
                    "source-only": {
                        "status": "RECONSTRUCTED",
                        "fixture": source_only_fixture,
                    },
                }
            }
        },
    }
    storage.atomic_json(source_path, source)
    source_bytes = source_path.read_bytes()
    raw_marker = storage.roots()[0] / "original-evidence.marker"
    raw_marker.parent.mkdir(parents=True, exist_ok=True)
    raw_marker.write_text("retained")
    data = value.data
    data["acquisition"] = {
        "mode": "RECOVERY_V1",
        "source_spec_id": value.id,
        "source_run_id": old_run_id,
    }
    recovery = SimpleNamespace(data=data, id=storage.identity(data))
    fixtures = [
        {
            **provider.validate_fixtures(
                [fixture_row()], 8, "2026-01-01T00:00:00Z", "2026-09-19T00:00:00Z"
            )[0],
            "fixture_id": fixture_id,
        }
        for fixture_id in (*statuses, "newly-discovered")
    ]
    calls = []

    class Client:
        def fixtures(self, *args, refresh_revision=None):
            calls.append(("fixtures", refresh_revision))
            return fixtures, "FETCHED"

        def has_historical_cache(self, fixture_id, *, refresh_revision=None):
            return (
                fixture_id in {"successful", "source-only"}
                or refresh_revision == recovery.id
            )

        def historical(self, fixture_id, *, refresh_revision=None):
            calls.append((fixture_id, refresh_revision))
            data = payload(2)
            data["fixtureId"] = fixture_id
            return (
                data,
                "CACHED" if fixture_id in {"successful", "source-only"} else "FETCHED",
            )

    client = Client()
    first = backfill.backfill(recovery, client=client)
    assert first["status"] == "COMPLETE"
    assert calls.count(("fixtures", recovery.id)) == 1
    assert ("successful", None) in calls
    assert ("not-found", recovery.id) in calls
    assert ("one-book", recovery.id) in calls
    assert ("formerly-unmatched", None) in calls
    assert ("newly-discovered", None) in calls
    assert ("source-only", None) in calls
    checkpoint = storage.read_json(first["checkpoint"])["leagues"]["1278"]
    assert checkpoint["refreshed_discovered_count"] == len(fixtures)
    assert checkpoint["source_discovered_count"] == len(
        source["leagues"]["1278"]["fixtures"]
    )
    assert checkpoint["discovered_count"] == len(fixtures) + 1
    assert len(calls) == 7
    assert source_path.read_bytes() == source_bytes
    assert raw_marker.read_text() == "retained"
    assert backfill.backfill(recovery, client=client) == first
    assert len(calls) == 7


def test_refresh_revision_keeps_original_cache():
    clock = Clock()
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return response({"safe": len(calls)})

    client = provider.OddsPapiClient(
        session=SimpleNamespace(get=get), clock=clock.time, sleep=clock.sleep
    )
    assert client.historical(FIXTURE)[1] == "FETCHED"
    assert client.historical(FIXTURE, refresh_revision="recovery")[1] == "FETCHED"
    assert client.historical(FIXTURE, refresh_revision="recovery")[1] == "CACHED"
    assert client.historical(FIXTURE)[0] == {"safe": 1}
    assert len(calls) == 2


@pytest.mark.parametrize(
    "prior,still_unavailable",
    [("FAILED", False), ("NO_USABLE_T30", True)],
)
def test_recovery_refresh_is_one_time_even_after_resume(
    canonical_match, prior, still_unavailable
):
    value = frozen()
    old_run_id = storage.identity({"spec_id": value.id, "pilot": False})
    storage.atomic_json(
        storage.roots()[1] / old_run_id / "backfill.json",
        {
            "run_id": old_run_id,
            "spec_id": value.id,
            "status": "PARTIAL",
            "leagues": {"1278": {"fixtures": {FIXTURE: {"status": prior}}}},
        },
    )
    data = value.data
    data["acquisition"] = {
        "mode": "RECOVERY_V1",
        "source_spec_id": value.id,
        "source_run_id": old_run_id,
    }
    recovery = SimpleNamespace(data=data, id=storage.identity(data))
    fixtures = provider.validate_fixtures(
        [fixture_row()], 8, "2026-01-01T00:00:00Z", "2026-09-19T00:00:00Z"
    )

    class Client:
        calls = 0

        def fixtures(self, *args, refresh_revision=None):
            assert refresh_revision == recovery.id
            return fixtures, "FETCHED"

        def has_historical_cache(self, fixture_id, *, refresh_revision=None):
            return False

        def historical(self, fixture_id, *, refresh_revision=None):
            assert refresh_revision == recovery.id
            self.calls += 1
            if still_unavailable:
                return payload(1), "FETCHED"
            raise provider.ProviderError("NOT_FOUND")

    client = Client()
    first = backfill.backfill(recovery, client=client)
    second = backfill.backfill(recovery, client=client)
    assert client.calls == 1
    assert second["status"] in {"COMPLETE", "PARTIAL", "FAILED"}
    item = storage.read_json(first["checkpoint"])["leagues"]["1278"]["fixtures"][
        FIXTURE
    ]
    assert item["status"] == ("NO_USABLE_T30" if still_unavailable else "FAILED")
    assert item["recovery_attempted"] is True


def test_freeze_recovery_preserves_scientific_contract():
    old = frozen(tuple(spec.TOURNAMENTS)).data
    old.pop("mapping_policy")
    old.pop("acquisition", None)
    source_path = storage.roots()[1] / "original-spec.json"
    storage.atomic_json(source_path, old)
    old_id = storage.identity(old)
    old_run_id = storage.identity({"spec_id": old_id, "pilot": False})
    storage.atomic_json(
        storage.roots()[1] / old_run_id / "backfill.json",
        {"spec_id": old_id, "run_id": old_run_id, "status": "PARTIAL"},
    )
    recovered = spec.freeze_recovery_spec(source_path)
    assert recovered.id != old_id
    assert recovered.data["data_cutoff"] == old["data_cutoff"]
    assert recovered.data["configs"] == old["configs"]
    assert recovered.data["bookmakers"] == old["bookmakers"]
    assert recovered.data["acquisition"]["source_run_id"] == old_run_id


def test_espanyol_not_forced(canonical_match):
    c, match = canonical_match
    Team.objects.create(competition=c, name="Espanyol")
    fixture = {
        "home_name": "Espanyol Barcelona",
        "away_name": "Getafe CF",
        "kickoff": KICKOFF.isoformat(),
    }
    result = mapping.map_fixture(c, fixture)
    assert result["status"] == "UNMATCHED"
    assert result["reason"] == "NO_CONFIDENT_ORDERED_PAIR"


def test_freeze_command_and_offline_runner_command(canonical_match, monkeypatch):
    path = storage.roots()[1] / "frozen.json"
    monkeypatch.setattr(spec, "active_profile", lambda *a, **k: None)
    monkeypatch.setattr(
        spec,
        "latest_selected_config",
        lambda c: (frozen().data["configs"]["1278"]["selected"], "CURRENT"),
    )
    out = io.StringIO()
    call_command(
        "run_prediction_experiment",
        spec=str(path),
        freeze=True,
        cutoff="2026-09-19T00:00:00Z",
        competitions="1278",
        stdout=out,
    )
    assert json.loads(out.getvalue())["status"] == "FROZEN"
    command_module = __import__(
        "football.management.commands.run_prediction_experiment", fromlist=["Command"]
    )
    fake = {
        "run_id": "offline-test",
        "summary": {"disposition": "INSUFFICIENT_EVIDENCE", "selected": None},
    }
    run = Mock(return_value=fake)
    monkeypatch.setattr(command_module, "run_experiment", run)
    out = io.StringIO()
    call_command("run_prediction_experiment", spec=str(path), stdout=out)
    assert json.loads(out.getvalue())["run_id"] == "offline-test"
    assert not json.loads(out.getvalue())["promoted"]


def test_ineligible_matches_retained_in_manifest(canonical_match):
    c, match = canonical_match
    Match.objects.create(
        season=match.season,
        home_team=match.away_team,
        away_team=match.home_team,
        kickoff=KICKOFF,
        status_short="PST",
    )
    inputs = runner.snapshot_matches(frozen())
    excluded = runner.excluded_targets(frozen(), inputs)
    assert len(excluded) == 1
    assert not excluded[0]["eligible"]
    assert all(
        row["status"] == "UNAVAILABLE" for row in excluded[0]["candidates"].values()
    )


def test_backfill_contract_contradiction_stops(canonical_match):
    client = Mock()
    client.fixtures.side_effect = provider.ProviderError("FIXTURES_SHAPE_MISMATCH")
    with pytest.raises(provider.ProviderError):
        backfill.backfill(frozen(), client=client)
    path = (
        storage.roots()[1]
        / storage.identity({"spec_id": frozen().id, "pilot": False})
        / "backfill.json"
    )
    assert storage.read_json(path)["status"] == "FAILED"


@pytest.mark.parametrize(
    "path,code",
    [
        (("bookmakers", "pinnacle"), "BOOKMAKER"),
        (("bookmakers", "pinnacle", "markets"), "MARKETS"),
        (("bookmakers", "pinnacle", "markets", "101"), "MARKET"),
        (("bookmakers", "pinnacle", "markets", "101", "outcomes"), "OUTCOMES"),
        (("bookmakers", "pinnacle", "markets", "101", "outcomes", "101"), "OUTCOME"),
        (
            ("bookmakers", "pinnacle", "markets", "101", "outcomes", "101", "players"),
            "PLAYERS",
        ),
        (
            (
                "bookmakers",
                "pinnacle",
                "markets",
                "101",
                "outcomes",
                "101",
                "players",
                "0",
            ),
            "SERIES",
        ),
    ],
)
def test_present_malformed_historical_node_is_classified(path, code):
    data = payload(2)
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = [] if code != "SERIES" else {}
    with pytest.raises(ValueError, match=f"HISTORICAL_{code}_SHAPE_MISMATCH"):
        reconstruct_test(data)


def test_missing_historical_node_is_incomplete_not_schema_failure():
    data = payload(2)
    del data["bookmakers"]["pinnacle"]["markets"]
    result = reconstruct_test(data)
    assert result["status"] == "UNAVAILABLE"
    assert result["book_count"] == 1


def test_malformed_historical_shape_aborts_backfill(canonical_match):
    client = Mock()
    client.fixtures.return_value = (
        provider.validate_fixtures(
            [fixture_row()], 8, "2026-01-01T00:00:00Z", "2026-09-19T00:00:00Z"
        ),
        "FETCHED",
    )
    malformed = payload(2)
    malformed["bookmakers"]["pinnacle"]["markets"] = []
    client.historical.return_value = (malformed, "FETCHED")
    value = frozen()
    with pytest.raises(ValueError, match="HISTORICAL_MARKETS_SHAPE_MISMATCH"):
        backfill.backfill(value, client=client, pilot=True)
    path = (
        storage.roots()[1]
        / storage.identity({"spec_id": value.id, "pilot": True})
        / "backfill.json"
    )
    state = storage.read_json(path)
    assert state["status"] == "FAILED"
    assert state["leagues"]["1278"]["reason"] == "HISTORICAL_MARKETS_SHAPE_MISMATCH"


def test_future_elo_target_results_do_not_change_predictions(canonical_match):
    from football.prediction.elo import EloMultinomialAdapter

    matches = []
    for i, scores in enumerate([(1, 0), (0, 0), (0, 1)] * 4):
        m = fake_match(i + 1, KICKOFF - timedelta(days=20 - i))
        m.home_score, m.away_score = scores
        m.outcome = (
            "HOME"
            if scores[0] > scores[1]
            else "AWAY" if scores[0] < scores[1] else "DRAW"
        )
        matches.append(m)
    target = fake_match(99, KICKOFF)
    adapter = EloMultinomialAdapter(k=20, c=1.0)
    adapter.fit(matches, KICKOFF)
    first = adapter.predict(target, KICKOFF).as_tuple()
    target.home_score, target.away_score, target.outcome = 0, 99, "AWAY"
    assert adapter.predict(target, KICKOFF).as_tuple() == first


def test_generic_provider_has_no_experiment_dependency_or_auto_caller():
    import ast
    from pathlib import Path

    from football.providers import oddspapi

    root = Path(__file__).resolve().parents[2]
    source = Path(oddspapi.__file__).read_text()
    tree = ast.parse(source)
    imports = [
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ]
    imports += [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    assert all(not name.startswith("football.experiments") for name in imports)
    assert "football.experiments" not in source
    assert "oddspapi" not in (root / "finsport/settings.py").read_text().casefold()
    assert "oddspapi" not in (root / "compose.yml").read_text().casefold()
    assert all(
        "oddspapi" not in path.read_text().casefold()
        for path in (root / "football/pipeline").glob("*.py")
    )


@pytest.mark.parametrize(
    "account, expected",
    [
        (
            {
                "current_subscription_id": "new",
                "subscriptions": [
                    {
                        "subscription_id": "old",
                        "is_active": True,
                        "request_limit": 100,
                        "request_count": 99,
                    },
                    {
                        "subscription_id": "new",
                        "is_active": True,
                        "request_limit": 250,
                        "request_count": 17,
                        "email": "hidden",
                    },
                ],
            },
            {"request_limit": 250, "request_count": 17},
        ),
        (
            {
                "current_subscription_id": None,
                "subscriptions": [
                    {
                        "subscription_id": "only",
                        "is_active": True,
                        "request_limit": 250,
                        "request_count": 17,
                    }
                ],
            },
            {"request_limit": 250, "request_count": 17},
        ),
    ],
)
def test_physical_account_shape_selects_safe_quota(account, expected):
    from football.providers.oddspapi import parse_account

    assert parse_account(account) == expected
    assert "email" not in storage.canonical(parse_account(account))


@pytest.mark.parametrize(
    "account",
    [
        {"request_limit": 250, "request_count": 17},
        {"current_subscription_id": None, "subscriptions": []},
        {
            "current_subscription_id": None,
            "subscriptions": [
                {
                    "subscription_id": "a",
                    "is_active": True,
                    "request_limit": 10,
                    "request_count": 1,
                },
                {
                    "subscription_id": "b",
                    "is_active": True,
                    "request_limit": 10,
                    "request_count": 1,
                },
            ],
        },
        {
            "current_subscription_id": "a",
            "subscriptions": [
                {"subscription_id": "a", "is_active": True, "request_limit": 10}
            ],
        },
        {
            "current_subscription_id": "a",
            "subscriptions": [
                {
                    "subscription_id": "a",
                    "is_active": True,
                    "request_limit": True,
                    "request_count": 1,
                }
            ],
        },
    ],
)
def test_account_ambiguous_or_missing_fails_closed(account):
    from football.providers.oddspapi import ProviderError, parse_account

    with pytest.raises(ProviderError, match="ACCOUNT_SHAPE_MISMATCH"):
        parse_account(account)


def test_generic_historical_accepts_caller_bookmakers():
    from football.providers.oddspapi import OddsPapiTransport, ProviderError

    seen = []
    transport = OddsPapiTransport(
        session=SimpleNamespace(
            get=lambda url, **kwargs: seen.append(kwargs["params"])
            or response({"ok": True})
        )
    )
    transport.historical(FIXTURE, ("pinnacle", "bet365"))
    assert seen[0]["bookmakers"] == "pinnacle,bet365"
    with pytest.raises(ProviderError, match="INVALID_HISTORICAL_REQUEST"):
        transport.historical(FIXTURE, ("pinnacle", "bet365", "unibet", "fourth"))


def test_freeze_real_current_metadata_without_retuning(monkeypatch):
    selected = {
        "dixon_coles": {
            "xi": 0.002,
            "grid": [0.0, 0.001, 0.002],
            "validation_log_loss": 1.0277767805770497,
        },
        "independent_poisson": {
            "xi": 0.001,
            "grid": [0.0, 0.001],
            "selection_source": "CURRENT",
        },
        "elo_multinomial_logit": {
            "k": 20,
            "C": 1.0,
            "grid": {"k": [10, 20, 40]},
            "validation_log_loss": 1.05,
        },
    }
    monkeypatch.setattr(
        spec, "latest_selected_config", lambda c: (selected, "experiment:42")
    )
    monkeypatch.setattr(spec, "active_profile", lambda *a, **k: None)
    value = spec.freeze_spec([SimpleNamespace(pk=1278)], "2026-09-19T00:00:00Z")
    saved = value.data["configs"]["1278"]
    assert saved["selected"] == selected
    assert saved["executable"] == {
        "DIXON_COLES": {"xi": 0.002},
        "INDEPENDENT_POISSON": {"xi": 0.001},
        "ELO_MULTINOMIAL_LOGIT": {"k": 20, "C": 1.0},
    }
    assert saved["identity"] == storage.identity(selected)
    assert saved["source"] == "experiment:42"
    assert value.data["changed_layer"] == "Prediction"
    assert value.data["artifact_schema_version"] == "fs018-artifacts-v1"
    assert value.data["de_vig_method"] == "multiplicative"
    assert value.data["consensus_method"] == "equal_weight_arithmetic_mean"
    assert set(value.data["metrics"]) >= {
        "log_loss",
        "multiclass_brier",
        "rps",
        "accuracy",
        "calibration",
        "coverage",
    }


def test_quote_age_from_kickoff_not_cutoff():
    data = payload(2)
    selected = reconstruct_test(data)["books"]["pinnacle"]["legs"][0]
    assert selected["quote_age_seconds"] == 1800
    assert selected["seconds_before_cutoff"] == 0
    series = data["bookmakers"]["pinnacle"]["markets"]["101"]["outcomes"]["101"][
        "players"
    ]["0"]
    series[0]["createdAt"] = (CUTOFF - timedelta(seconds=45)).isoformat()
    selected = reconstruct_test(data)["books"]["pinnacle"]["legs"][0]
    assert selected["quote_age_seconds"] == 1845
    assert selected["seconds_before_cutoff"] == 45


def test_traffic_audit_attempt_retry_429_cache_restart_and_redaction(tmp_path):
    clock = Clock()
    call_status = [429, 200]
    session = SimpleNamespace(
        get=lambda url, **kwargs: response(payload(2), call_status.pop(0))
    )
    audit_path = tmp_path / "audit.json"
    first = provider.OddsPapiClient(
        session=session, audit_path=audit_path, clock=clock.time, sleep=clock.sleep
    )
    assert first.historical(FIXTURE)[1] == "FETCHED"
    second = provider.OddsPapiClient(
        session=session, audit_path=audit_path, clock=clock.time, sleep=clock.sleep
    )
    assert second.historical(FIXTURE)[1] == "CACHED"
    audit = storage.read_json(audit_path)
    assert audit["physical_calls"]["historical-odds"] == 2
    assert audit["http_status_counts"] == {"429": 1, "200": 1}
    assert audit["http_429"] == 1 and audit["retries"] == 1
    assert audit["cache_hits"]["historical-odds"] == 1
    assert audit["in_flight"] == 0
    assert "test-secret" not in audit_path.read_text()
    assert "bookmakers" not in audit_path.read_text()


def test_backfill_terminal_audit_persists_after_resume(canonical_match):
    clock = Clock()
    calls = []

    def get(url, **kwargs):
        endpoint = url.rsplit("/", 1)[-1]
        calls.append(endpoint)
        return response([fixture_row()] if endpoint == "fixtures" else payload(2))

    session = SimpleNamespace(get=get)
    value = frozen()
    run_id = storage.identity({"spec_id": value.id, "pilot": True})
    audit_path = storage.roots()[1] / run_id / "traffic-audit.json"
    client = provider.OddsPapiClient(
        session=session, audit_path=audit_path, clock=clock.time, sleep=clock.sleep
    )
    first = backfill.backfill(value, client=client, pilot=True)
    assert first["audit"]["physical_calls"] == {
        "fixtures": 1,
        "historical-odds": 1,
        "account": 0,
    }
    assert first["audit"]["matched"] == first["audit"]["fetched"] == 1
    assert first["audit"]["complete_book_counts"] == {"2": 1}
    assert first["audit"]["quote_age_seconds"]["min"] == 1800
    second = backfill.backfill(value, client=client, pilot=True)
    assert second["audit"] == first["audit"]
    assert calls == ["fixtures", "historical-odds"]
    checkpoint = storage.read_json(first["checkpoint"])
    assert checkpoint["audit"] == first["audit"]
    assert "test-secret" not in storage.canonical(checkpoint["audit"])


def test_run_local_views_are_deterministic_and_derived(canonical_match):
    import gzip

    client = Mock()
    client.fixtures.return_value = (
        provider.validate_fixtures(
            [fixture_row()], 8, "2026-01-01T00:00:00Z", "2026-09-19T00:00:00Z"
        ),
        "FETCHED",
    )
    client.historical.return_value = (payload(2), "FETCHED")
    value = frozen()
    backfill.backfill(value, client=client, pilot=True)
    run = runner.run_experiment(value, pilot=True)
    directory = storage.roots()[1] / run["analysis_id"]
    names = (
        "spec.json",
        "manifest.json",
        "summary.json",
        "per_match.jsonl.gz",
        "report.md",
    )
    before = {name: (directory / name).read_bytes() for name in names}
    rows = [
        json.loads(line)
        for line in gzip.decompress(before["per_match.jsonl.gz"]).splitlines()
    ]
    assert len(rows) == 4
    market = next(row for row in rows if row["model_code"] == "MARKET_CONSENSUS")
    assert market["provider_fixture_id"] == FIXTURE
    assert market["bookmaker_count"] == 2
    assert market["quote_ages_seconds"]["pinnacle"]["101"] == 1800
    assert market["raw_cache_hash"] == storage.identity(payload(2))
    assert (
        market["log_loss"] is not None
        and market["multiclass_brier"] is not None
        and market["rps"] is not None
    )
    sporting = next(row for row in rows if row["model_code"] == "DIXON_COLES")
    assert sporting["provider_fixture_id"] is None
    assert sporting["bookmaker_count"] is None
    assert (directory / "spec.json").read_text() == storage.canonical(value.data) + "\n"
    assert storage.read_json(directory / "manifest.json") == run["manifest"]
    assert (
        storage.read_json(directory / "summary.json")["cohort_hash"]
        == run["summary"]["cohort_hash"]
    )
    runner.run_experiment(value, pilot=True)
    assert before == {name: (directory / name).read_bytes() for name in names}
    assert before["per_match.jsonl.gz"][4:8] == b"\x00\x00\x00\x00"
    assert "test-secret" not in (directory / "report.md").read_text()
    assert not (directory / "report.md").read_text().startswith("# FS-018 Global")


def test_effective_sporting_and_market_config_identity():
    value = frozen(tuple(spec.TOURNAMENTS)).data
    market = artifacts.effective_baseline_config(value, "MARKET_CONSENSUS")
    assert market == {
        "model_code": "MARKET_CONSENSUS",
        "model_version": "fs013-market-consensus-v2",
        "evidence_profile": spec.PROFILE,
        "bookmakers": list(spec.BOOKMAKERS),
        "minimum_books": 2,
        "cutoff": value["t30"],
        "de_vig": "multiplicative",
        "consensus": "equal_weight_arithmetic_mean",
    }
    sporting = artifacts.effective_baseline_config(value, "DIXON_COLES")
    assert len(sporting["per_competition"]) == 10
    assert set(sporting["per_competition"]["1278"]["executable"]) == {"xi"}
    assert storage.identity(sporting) == storage.identity(
        artifacts.effective_baseline_config(value, "DIXON_COLES")
    )
    changed = copy.deepcopy(value)
    changed["configs"]["1278"]["selected"]["dixon_coles"]["xi"] = 0.002
    assert storage.identity(sporting) != storage.identity(
        artifacts.effective_baseline_config(changed, "DIXON_COLES")
    )
    changed = copy.deepcopy(value)
    changed["minimum_books"] = 3
    assert storage.identity(market) != storage.identity(
        artifacts.effective_baseline_config(changed, "MARKET_CONSENSUS")
    )


def test_per_match_log_loss_matches_existing_metric_at_zero_probability():
    from football.experiments.views import per_match_rows
    from football.prediction.metrics import prediction_metrics

    data = frozen().data
    candidates = {
        code: {
            "model_version": version,
            "status": "PRODUCED",
            "reason": "",
            "probabilities": [0.0, 0.5, 0.5],
        }
        for code, version in data["models"].items()
    }
    match = {
        "match_id": 1,
        "competition_id": 1278,
        "kickoff": KICKOFF.isoformat(),
        "outcome": "HOME",
        "eligible": True,
        "candidates": candidates,
    }
    run = {
        "spec": data,
        "manifest": [match],
        "acquisition": {"leagues": {}},
        "summary": {
            "cohorts": {
                "COMMON": [1],
                "NATURAL": {code: [1] for code in data["models"]},
            }
        },
    }
    row = next(per_match_rows(run))
    expected = prediction_metrics(["HOME"], [[0.0, 0.5, 0.5]])
    assert row["log_loss"] == pytest.approx(expected["log_loss"])
    assert row["multiclass_brier"] == pytest.approx(expected["multiclass_brier"])
    assert row["rps"] == pytest.approx(expected["rps"])


def test_market_promotion_record_identifies_only_market_policy():
    value = frozen(tuple(spec.TOURNAMENTS))
    rows = manifest(tuple(spec.TOURNAMENTS), identical=True)
    rows.sort(key=lambda row: (row["competition_id"], row["kickoff"], row["match_id"]))
    summary = compare(rows, spec.MODELS, sorted(spec.TOURNAMENTS), resources())
    summary["selected"] = "MARKET_CONSENSUS"  # controlled synthetic identity fixture
    summary["disposition"] = "NO_CLEAR_SUPERIORITY"
    run = {
        "spec_id": value.id,
        "spec": value.data,
        "manifest": rows,
        "summary": summary,
        "acquisition": {
            "pilot": False,
            "status": "COMPLETE",
            "run_id": "synthetic",
            "leagues": {str(i): {} for i in spec.TOURNAMENTS},
        },
    }
    run["run_id"] = storage.identity(run)
    record = artifacts.promotion_record(run)
    assert record["model_code"] == "MARKET_CONSENSUS"
    assert record["effective_config"] == artifacts.effective_baseline_config(
        value.data, "MARKET_CONSENSUS"
    )
    assert record["config_identity"] == storage.identity(record["effective_config"])
    assert record["config_identity"] != storage.identity(value.data["configs"])


def test_frozen_source_identity_includes_new_provider(monkeypatch):
    from pathlib import Path

    selected = frozen().data["configs"]["1278"]["selected"]
    monkeypatch.setattr(spec, "latest_selected_config", lambda c: (selected, "CURRENT"))
    monkeypatch.setattr(spec, "active_profile", lambda *a, **k: None)
    competition = SimpleNamespace(pk=1278)
    before = spec.freeze_spec([competition], "2026-09-19T00:00:00Z")
    read_text = Path.read_text

    def changed_provider(path, *args, **kwargs):
        source = read_text(path, *args, **kwargs)
        return (
            source + "# hypothetical provider change"
            if (path.name == "oddspapi.py" and path.parent.name == "providers")
            else source
        )

    monkeypatch.setattr(Path, "read_text", changed_provider)
    after = spec.freeze_spec([competition], "2026-09-19T00:00:00Z")
    assert (
        before.data["runtime"]["code_identity"]
        != after.data["runtime"]["code_identity"]
    )
    assert before.id != after.id
