from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import override_settings

from football.capture.contracts import CaptureConfig, CaptureResult
from football.capture.planner import CapturePlanner
from football.models import (
    Bookmaker,
    BookmakerCanonicalRef,
    CanonicalBookmaker,
    CanonicalOddsMarket,
    CaptureRun,
    CaptureWorkItem,
    Competition,
    Match,
    MatchSourceRef,
    OddsMarket,
    OddsMarketCanonicalRef,
    OddsObservation,
    Prediction,
    PredictionExperiment,
    ReconciliationStatus,
    Season,
    Source,
    Team,
)
from football.pipeline import run_pipeline
from football.prediction.contracts import ProbabilityResult, UnavailablePrediction
from football.prediction.market import MarketConsensusAdapter
from football.prediction.service import predict_competition_day

pytestmark = pytest.mark.django_db

FS013_WINDOWS = [
    {
        "name": "market-t6h",
        "offset_minutes": 360,
        "before_tolerance_minutes": 0,
        "normal_tolerance_minutes": 10,
        "late_tolerance_minutes": 15,
    },
    {
        "name": "market-t60m",
        "offset_minutes": 60,
        "before_tolerance_minutes": 0,
        "normal_tolerance_minutes": 10,
        "late_tolerance_minutes": 15,
    },
    {
        "name": "market-t30m",
        "offset_minutes": 30,
        "before_tolerance_minutes": 0,
        "normal_tolerance_minutes": 10,
        "late_tolerance_minutes": 15,
    },
]

IGNORED_LEGACY_WINDOWS = [
    {"name": "early", "offset_minutes": 2880},
    {"name": "middle", "offset_minutes": 720},
]

CAPTURE_SETTINGS = {
    "FOOTBALL_CAPTURE_WINDOWS": IGNORED_LEGACY_WINDOWS,
    "FOOTBALL_MARKET_CONSENSUS_WINDOWS": FS013_WINDOWS,
    "FOOTBALL_CAPTURE_HORIZON_HOURS": 24,
    "FOOTBALL_CAPTURE_MANDATORY_RESERVE": 0,
    "FOOTBALL_CAPTURE_MAX_OPERATION_PAGES": 1,
    "FOOTBALL_CAPTURE_MAX_PROVIDER_ATTEMPTS": 3,
    "FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS": 3,
    "FOOTBALL_CAPTURE_DISCOVERY_ENABLED": False,
    "FOOTBALL_CAPTURE_DISCOVERY_DAYS_AHEAD": 0,
    "FOOTBALL_CAPTURE_RESULT_REFRESH_ENABLED": False,
    "FOOTBALL_CAPTURE_RESULT_DELAY_MINUTES": 60,
    "FOOTBALL_CAPTURE_RESULT_CADENCE_MINUTES": 360,
    "API_FOOTBALL_MAX_RETRIES": 0,
}


def target_match(*, kickoff=None):
    kickoff = kickoff or datetime(2026, 9, 10, 18, tzinfo=UTC)
    competition = Competition.objects.create(
        name="FS-013 League",
        competition_type="League",
        country="PE",
        enabled=True,
    )
    season = Season.objects.create(
        competition=competition,
        year=kickoff.year,
        start_date=date(kickoff.year, 1, 1),
        end_date=date(kickoff.year, 12, 31),
        coverage={"odds": True},
    )
    home = Team.objects.create(competition=competition, name="FS-013 Home")
    away = Team.objects.create(competition=competition, name="FS-013 Away")
    return Match.objects.create(
        season=season,
        home_team=home,
        away_team=away,
        kickoff=kickoff,
        status_short="NS",
        status_long="Not Started",
    )


def canonical_market(source, *, external_id="1", name="Match Winner"):
    raw = OddsMarket.objects.create(source=source, external_id=external_id, name=name)
    canonical, _ = CanonicalOddsMarket.objects.get_or_create(code="1x2", name="1X2")
    OddsMarketCanonicalRef.objects.create(
        market=raw,
        canonical_market=canonical,
        reconciliation_status=ReconciliationStatus.RESOLVED,
        reason="TEST_GOVERNED_MAPPING",
    )
    return raw


def canonical_bookmaker(source, code, *, canonical=None):
    raw = Bookmaker.objects.create(source=source, external_id=code, name=f"Book {code}")
    canonical = canonical or CanonicalBookmaker.objects.create(
        code=f"book-{code}", name=f"Book {code}"
    )
    BookmakerCanonicalRef.objects.create(
        bookmaker=raw,
        canonical_bookmaker=canonical,
        reconciliation_status=ReconciliationStatus.RESOLVED,
        reason="TEST_GOVERNED_MAPPING",
    )
    return raw, canonical


def observation(match, source, bookmaker, market, observed_at, prices):
    return OddsObservation.objects.create(
        match=match,
        source=source,
        bookmaker=bookmaker,
        market=market,
        home=Decimal(prices[0]),
        draw=Decimal(prices[1]),
        away=Decimal(prices[2]),
        observed_at=observed_at,
    )


def test_zero_canonical_quotes_is_explicit_and_diagnostic():
    match = target_match()
    source = Source.objects.create(
        code="unmapped", name="Unmapped", base_url="https://unmapped.test"
    )
    market = OddsMarket.objects.create(source=source, external_id="?", name="Unknown")
    bookmaker = Bookmaker.objects.create(source=source, external_id="?", name="Unknown")
    observation(
        match,
        source,
        bookmaker,
        market,
        match.kickoff - timedelta(minutes=30),
        ("2", "3", "4"),
    )

    result = MarketConsensusAdapter().predict(match, match.kickoff)

    assert isinstance(result, UnavailablePrediction)
    assert result.reason == "NO_VALID_CANONICAL_1X2_QUOTES"
    assert result.diagnostics["canonical_bookmaker_count"] == 0
    assert result.diagnostics["rejection_counts"]["unmapped_bookmaker"] == 1
    assert (
        result.diagnostics["rejected_raw_provenance"][0][
            "bookmaker_reconciliation_reason"
        ]
        == "NO_CANONICAL_REF"
    )


def test_one_book_is_produced_without_claiming_mature_consensus():
    match = target_match()
    source = Source.objects.create(code="one", name="One", base_url="https://one.test")
    market = canonical_market(source)
    bookmaker, _ = canonical_bookmaker(source, "one")
    observation(
        match,
        source,
        bookmaker,
        market,
        match.kickoff - timedelta(minutes=10),
        ("2", "4", "4"),
    )

    result = MarketConsensusAdapter().predict(match, match.kickoff)

    assert isinstance(result, ProbabilityResult)
    assert result.as_tuple() == pytest.approx((0.5, 0.25, 0.25))
    assert result.diagnostics["canonical_bookmaker_count"] == 1
    assert result.diagnostics["consensus_evidence"] == (
        "SINGLE_BOOKMAKER_TECHNICAL_ONLY"
    )


def test_equal_pool_deduplicates_cross_source_book_and_equivalent_markets():
    match = target_match()
    first_source = Source.objects.create(
        code="first", name="First", base_url="https://first.test"
    )
    second_source = Source.objects.create(
        code="second", name="Second", base_url="https://second.test"
    )
    first_market = canonical_market(first_source, external_id="winner")
    equivalent_market = canonical_market(second_source, external_id="MW3W")
    duplicate_market = canonical_market(first_source, external_id="1X2", name="1X2")
    economic_book = CanonicalBookmaker.objects.create(
        code="economic-book", name="Economic Book"
    )
    first_raw, _ = canonical_bookmaker(first_source, "raw-a", canonical=economic_book)
    second_raw, _ = canonical_bookmaker(second_source, "raw-b", canonical=economic_book)
    independent, _ = canonical_bookmaker(first_source, "independent")
    cutoff = match.kickoff
    older = observation(
        match,
        first_source,
        first_raw,
        first_market,
        cutoff - timedelta(minutes=20),
        ("2", "4", "4"),
    )
    latest = observation(
        match,
        second_source,
        second_raw,
        equivalent_market,
        cutoff - timedelta(minutes=10),
        ("4", "2", "4"),
    )
    observation(
        match,
        first_source,
        first_raw,
        duplicate_market,
        cutoff - timedelta(minutes=30),
        ("9", "9", "9"),
    )
    observation(
        match,
        first_source,
        independent,
        first_market,
        cutoff - timedelta(minutes=5),
        ("4", "4", "2"),
    )

    result = MarketConsensusAdapter().predict(match, cutoff)

    assert result.as_tuple() == pytest.approx((0.25, 0.375, 0.375))
    assert result.diagnostics["canonical_bookmaker_count"] == 2
    selected_ids = {
        row["observation_id"] for row in result.diagnostics["selected_raw_provenance"]
    }
    assert latest.pk in selected_ids
    assert older.pk not in selected_ids
    assert result.diagnostics["rejection_counts"]["duplicate_canonical_vote"] == 2


def test_latest_valid_quote_wins_and_cutoff_is_strict():
    match = target_match()
    source = Source.objects.create(
        code="temporal", name="Temporal", base_url="https://temporal.test"
    )
    market = canonical_market(source)
    bookmaker, _ = canonical_bookmaker(source, "temporal")
    cutoff = match.kickoff - timedelta(minutes=30)
    valid = observation(
        match,
        source,
        bookmaker,
        market,
        cutoff - timedelta(minutes=10),
        ("2", "3", "4"),
    )
    observation(
        match,
        source,
        bookmaker,
        market,
        cutoff - timedelta(minutes=5),
        ("1", "3", "4"),
    )
    observation(
        match,
        source,
        bookmaker,
        market,
        cutoff,
        ("9", "9", "9"),
    )

    result = MarketConsensusAdapter().predict(match, cutoff)

    assert result.diagnostics["selected_raw_provenance"][0]["observation_id"] == (
        valid.pk
    )
    assert result.diagnostics["raw_observations_considered"] == 2
    assert result.diagnostics["rejection_counts"]["invalid_prices"] == 1


@override_settings(**CAPTURE_SETTINGS)
def test_three_capture_windows_are_independent_and_non_polling():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=UTC)
    match = target_match(kickoff=kickoff)
    source = Source.objects.get(code="api_football")
    market = canonical_market(source)
    MatchSourceRef.objects.create(
        source=source,
        external_id="fixture-1",
        match=match,
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    config = CaptureConfig.from_settings()
    planner = CapturePlanner(config=config)

    def statuses(plan):
        return {item.intended_window: item.status for item in plan.items}

    def fulfill(item, completed_at):
        run = CaptureRun.objects.create(
            trigger=CaptureRun.Trigger.SCHEDULER,
            status=CaptureRun.Status.SUCCESS,
            planning_at=completed_at,
            completed_at=completed_at,
        )
        CaptureWorkItem.objects.create(
            run=run,
            purpose=CaptureWorkItem.Purpose.ODDS_CAPTURE,
            status=CaptureWorkItem.Status.SUCCESS,
            source=source,
            match=match,
            market=market,
            logical_identity=item.logical_identity,
            intended_window=item.intended_window,
            target_at=item.target_at,
        )

    t6_at = kickoff - timedelta(hours=6)
    t6 = planner.plan(at=t6_at, allow_bootstrap=True)
    assert statuses(t6) == {
        "market-t6h": CaptureWorkItem.Status.PLANNED,
        "market-t60m": CaptureWorkItem.Status.NOT_DUE,
        "market-t30m": CaptureWorkItem.Status.NOT_DUE,
    }
    t6_due = next(item for item in t6.items if item.intended_window == "market-t6h")
    fulfill(t6_due, t6_at + timedelta(minutes=1))

    t60_at = kickoff - timedelta(hours=1)
    t60 = planner.plan(at=t60_at, allow_bootstrap=True)
    assert statuses(t60) == {
        "market-t6h": CaptureWorkItem.Status.ALREADY_FULFILLED,
        "market-t60m": CaptureWorkItem.Status.PLANNED,
        "market-t30m": CaptureWorkItem.Status.NOT_DUE,
    }
    t60_due = next(item for item in t60.items if item.intended_window == "market-t60m")
    fulfill(t60_due, t60_at + timedelta(minutes=1))

    t30_at = kickoff - timedelta(minutes=30)
    t30 = planner.plan(at=t30_at, allow_bootstrap=True)
    assert statuses(t30) == {
        "market-t6h": CaptureWorkItem.Status.ALREADY_FULFILLED,
        "market-t60m": CaptureWorkItem.Status.ALREADY_FULFILLED,
        "market-t30m": CaptureWorkItem.Status.PLANNED,
    }
    t30_due = next(item for item in t30.items if item.intended_window == "market-t30m")
    fulfill(t30_due, t30_at + timedelta(minutes=1))

    repeated = planner.plan(at=t30_at + timedelta(minutes=5), allow_bootstrap=True)
    assert statuses(repeated) == {
        "market-t6h": CaptureWorkItem.Status.ALREADY_FULFILLED,
        "market-t60m": CaptureWorkItem.Status.ALREADY_FULFILLED,
        "market-t30m": CaptureWorkItem.Status.ALREADY_FULFILLED,
    }
    assert not any(
        item.status == CaptureWorkItem.Status.PLANNED for item in repeated.items
    )

    assert (
        len(
            {
                t6_due.logical_identity,
                t60_due.logical_identity,
                t30_due.logical_identity,
            }
        )
        == 3
    )
    chronological = [t6_due, t60_due, t30_due]
    assert all(
        previous.not_after < current.not_before
        for previous, current in zip(chronological, chronological[1:])
    )
    assert {window.name for window in config.windows} == {
        "market-t6h",
        "market-t60m",
        "market-t30m",
    }
    assert {item.intended_window for item in t6.items} == {
        "market-t6h",
        "market-t60m",
        "market-t30m",
    }
    assert not {item.intended_window for item in t6.items} & {"early", "middle"}
    assert settings.FOOTBALL_CAPTURE_WAKE_SECONDS == 300


def completed_capture(match, *, target_at, cutoff, observations_created):
    source = match.source_refs.get(source__code="api_football").source
    market = OddsMarket.objects.get(source=source, external_id="1")
    run = CaptureRun.objects.create(
        trigger=CaptureRun.Trigger.SCHEDULER,
        status=CaptureRun.Status.SUCCESS,
        planning_at=target_at,
        completed_at=cutoff,
    )
    identity = f"api_football:odds:fixture-1:1:batch:{target_at.isoformat()}"
    item = CaptureWorkItem.objects.create(
        run=run,
        purpose=CaptureWorkItem.Purpose.ODDS_CAPTURE,
        status=CaptureWorkItem.Status.SUCCESS,
        source=source,
        match=match,
        market=market,
        logical_identity=identity,
        intended_window=(
            "market-t60m"
            if target_at == match.kickoff - timedelta(hours=1)
            else "market-t30m"
        ),
        target_at=target_at,
        not_before=target_at,
        not_after=target_at + timedelta(minutes=15),
        observations_created=observations_created,
        executed_at=target_at,
        completed_at=cutoff,
    )
    payload = {
        "purpose": item.purpose,
        "status": item.status,
        "match_id": match.pk,
        "competition_id": match.competition.pk,
        "logical_identity": identity,
        "intended_window": item.intended_window,
        "target_at": target_at.isoformat(),
        "not_before": item.not_before.isoformat(),
        "not_after": item.not_after.isoformat(),
    }
    return CaptureResult(
        run_id=run.pk,
        status=run.status,
        planning_at=target_at,
        quota_before={},
        quota_after={},
        observations_created=observations_created,
        completed_work=[payload],
        plan={"items": [payload]},
    )


def test_completed_batch_creates_one_versioned_prediction_and_retry_is_idempotent(
    monkeypatch,
):
    match = target_match()
    source = Source.objects.get(code="api_football")
    market = canonical_market(source)
    MatchSourceRef.objects.create(
        source=source,
        external_id="fixture-1",
        match=match,
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    first, _ = canonical_bookmaker(source, "first")
    second, _ = canonical_bookmaker(source, "second")
    stale, _ = canonical_bookmaker(source, "stale")
    historical_experiment = PredictionExperiment.objects.create(
        competition=match.competition,
        mode=PredictionExperiment.MODE_BACKTEST,
        period_start=match.kickoff.date(),
        period_end=match.kickoff.date(),
        config={},
    )
    historical = Prediction.objects.create(
        experiment=historical_experiment,
        match=match,
        model_code=Prediction.MARKET_CONSENSUS,
        model_version="fs003-market-consensus-v1",
        model_config={"consensus_method": "mean"},
        cutoff=match.kickoff - timedelta(days=1),
        p_home=0.5,
        p_draw=0.3,
        p_away=0.2,
        predicted_outcome=Match.OUTCOME_HOME,
    )
    historical_original = (
        historical.cutoff,
        historical.p_home,
        historical.model_version,
        historical.modified,
    )
    first_target = match.kickoff - timedelta(hours=1)
    first_cutoff = first_target + timedelta(minutes=1)
    stale_observation = observation(
        match,
        source,
        stale,
        market,
        first_target - timedelta(minutes=5),
        ("99", "3", "3"),
    )
    first_observation = observation(
        match,
        source,
        first,
        market,
        first_target + timedelta(seconds=10),
        ("2", "3", "4"),
    )
    observation(
        match,
        source,
        second,
        market,
        first_target + timedelta(seconds=20),
        ("3", "3", "3"),
    )
    assert not Prediction.objects.filter(
        model_version="fs013-market-consensus-v2"
    ).exists()
    first_capture = completed_capture(
        match,
        target_at=first_target,
        cutoff=first_cutoff,
        observations_created=2,
    )
    monkeypatch.setattr(
        "football.pipeline.service.run_capture", lambda **kwargs: first_capture
    )

    run_pipeline(at=first_cutoff)
    run_pipeline(at=first_cutoff)

    assert (
        PredictionExperiment.objects.filter(
            intended_window="market-t60m",
            logical_identity__startswith="fs013:market-consensus:",
        ).count()
        == 1
    )
    first_prediction = Prediction.objects.get(
        model_code=Prediction.MARKET_CONSENSUS,
        model_version="fs013-market-consensus-v2",
    )
    original = (
        first_prediction.cutoff,
        first_prediction.p_home,
        first_prediction.evidence_identity,
        first_prediction.created,
    )
    assert first_prediction.model_version == "fs013-market-consensus-v2"
    assert first_prediction.cutoff == first_cutoff
    assert first_prediction.evidence_identity
    assert first_prediction.diagnostics["canonical_bookmaker_count"] == 2
    first_experiment = first_prediction.experiment
    assert first_experiment.config["model_codes"] == [Prediction.MARKET_CONSENSUS]
    modal = first_experiment.decisions.get(
        prediction=first_prediction,
        policy_code="MODAL_ALL",
    )
    assert modal.selected_odds_observation_id != stale_observation.pk
    assert modal.selected_odds_observation.observed_at >= first_target
    assert not first_experiment.predictions.exclude(
        model_code=Prediction.MARKET_CONSENSUS
    ).exists()

    later_target = match.kickoff - timedelta(minutes=30)
    later_cutoff = later_target + timedelta(minutes=1)
    observation(
        match,
        source,
        first,
        market,
        later_target + timedelta(seconds=10),
        ("4", "3", "2"),
    )
    later_capture = completed_capture(
        match,
        target_at=later_target,
        cutoff=later_cutoff,
        observations_created=1,
    )
    monkeypatch.setattr(
        "football.pipeline.service.run_capture", lambda **kwargs: later_capture
    )

    run_pipeline(at=later_cutoff)

    predictions = list(
        Prediction.objects.filter(
            model_code=Prediction.MARKET_CONSENSUS,
            model_version="fs013-market-consensus-v2",
        ).order_by("cutoff")
    )
    first_prediction.refresh_from_db()
    assert len(predictions) == 2
    assert (
        first_prediction.cutoff,
        first_prediction.p_home,
        first_prediction.evidence_identity,
        first_prediction.created,
    ) == original
    assert predictions[1].cutoff == later_cutoff
    assert predictions[1].evidence_identity != first_prediction.evidence_identity
    assert first_observation.observed_at < first_prediction.cutoff
    historical.refresh_from_db()
    assert (
        historical.cutoff,
        historical.p_home,
        historical.model_version,
        historical.modified,
    ) == historical_original


def test_market_consensus_v2_requires_completed_capture_evidence():
    match = target_match()

    with pytest.raises(
        ValueError,
        match="requires a capture evidence identity",
    ):
        predict_competition_day(
            match.competition,
            match.kickoff.date(),
            match.kickoff - timedelta(hours=1),
            match_ids=[match.pk],
            model_codes=[Prediction.MARKET_CONSENSUS],
        )


def test_completed_empty_batch_persists_explicit_unavailable_evidence(monkeypatch):
    match = target_match()
    source = Source.objects.get(code="api_football")
    market = canonical_market(source)
    bookmaker, _ = canonical_bookmaker(source, "stale-prior-window")
    MatchSourceRef.objects.create(
        source=source,
        external_id="fixture-1",
        match=match,
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    target = match.kickoff - timedelta(hours=1)
    cutoff = target + timedelta(minutes=1)
    observation(
        match,
        source,
        bookmaker,
        market,
        match.kickoff - timedelta(hours=6),
        ("2", "3", "4"),
    )
    capture = completed_capture(
        match, target_at=target, cutoff=cutoff, observations_created=0
    )
    capture.completed_work[0]["status"] = CaptureWorkItem.Status.SUCCESS_EMPTY
    CaptureWorkItem.objects.filter(run_id=capture.run_id).update(
        status=CaptureWorkItem.Status.SUCCESS_EMPTY
    )
    monkeypatch.setattr(
        "football.pipeline.service.run_capture", lambda **kwargs: capture
    )

    run_pipeline(at=cutoff)

    experiment = PredictionExperiment.objects.get(
        intended_window="market-t60m",
        logical_identity__startswith="fs013:market-consensus:",
    )
    unavailable = experiment.summary["unavailable"][f"MARKET_CONSENSUS:{match.pk}"]
    assert not experiment.predictions.filter(
        model_code=Prediction.MARKET_CONSENSUS
    ).exists()
    assert unavailable["reason"] == "NO_VALID_CANONICAL_1X2_QUOTES"
    assert unavailable["diagnostics"]["canonical_bookmaker_count"] == 0


@pytest.mark.django_db(transaction=True)
def test_fs013_migration_reconciles_supported_existing_raw_rows():
    executor = MigrationExecutor(connection)
    executor.migrate([("football", "0011_shared_model_readiness")])
    old_apps = executor.loader.project_state(
        [("football", "0011_shared_model_readiness")]
    ).apps
    OldSource = old_apps.get_model("football", "Source")
    OldBookmaker = old_apps.get_model("football", "Bookmaker")
    OldMarket = old_apps.get_model("football", "OddsMarket")
    source, _ = OldSource.objects.get_or_create(
        code="api_football",
        defaults={
            "name": "API-Football",
            "base_url": "https://v3.football.api-sports.io/",
        },
    )
    OldBookmaker.objects.create(source=source, external_id="8", name="Bet365")
    OldMarket.objects.create(source=source, external_id="1", name="Match Winner")

    executor = MigrationExecutor(connection)
    executor.migrate([("football", "0012_fs013_market_consensus_identity")])
    new_apps = executor.loader.project_state(
        [("football", "0012_fs013_market_consensus_identity")]
    ).apps
    bookmaker_ref = new_apps.get_model(
        "football", "BookmakerCanonicalRef"
    ).objects.get()
    market_ref = new_apps.get_model("football", "OddsMarketCanonicalRef").objects.get()

    assert bookmaker_ref.reconciliation_status == "RESOLVED"
    assert bookmaker_ref.canonical_bookmaker.code == "bet365"
    assert market_ref.reconciliation_status == "RESOLVED"
    assert market_ref.canonical_market.code == "1x2"
