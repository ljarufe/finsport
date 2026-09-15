from datetime import datetime, timezone
from decimal import Decimal

import pytest

from football.capital.retirement import (
    CapitalRetirementScopeError,
    build_v1_retirement_manifest,
    retire_v1_capital,
)
from football.capital.runtime import provision_automatic_configs
from football.capital.service import run_capital_experiment
from football.models import (
    CapitalExperiment,
    CapitalLedgerEntry,
    CapitalLongitudinalSeries,
    CapitalPolicyRun,
    Decision,
    Match,
    OddsObservation,
    Prediction,
    PredictionExperiment,
)

from .capital_helpers import create_capital_stream

pytestmark = pytest.mark.django_db


def test_v1_retirement_dry_run_apply_and_second_run_preserve_upstream():
    prediction_experiment, decisions = create_capital_stream(
        [{"outcome": Match.OUTCOME_HOME}],
        decision_policy="MODAL_ALL",
        suffix="-retire",
    )
    experiment = run_capital_experiment(
        prediction_experiment=prediction_experiment,
        decision_policy_code="MODAL_ALL",
        source_model_code=Prediction.DIXON_COLES,
        config={
            "mode": "REPLAY",
            "initial_bankroll": "100",
            "policies": [{"code": "FLAT_UNIT", "config": {"unit": "1"}}],
        },
    )
    provision_automatic_configs()
    upstream = {
        "PredictionExperiment": PredictionExperiment.objects.count(),
        "Prediction": Prediction.objects.count(),
        "Decision": Decision.objects.count(),
        "OddsObservation": OddsObservation.objects.count(),
    }

    dry_run = retire_v1_capital()

    assert dry_run["status"] == "DRY_RUN"
    manifest = dry_run["manifest"]
    assert manifest["selector"] == {"CapitalExperiment.engine_version": "fs004-v1"}
    assert manifest["counts"] == {
        "CapitalLongitudinalSeries": 0,
        "CapitalExperiment": 1,
        "CapitalPolicyRun": 1,
        "CapitalLedgerEntry": 1,
        "upstream_selected_for_deletion": 0,
    }
    assert manifest["ids"]["CapitalExperiment"] == [experiment.pk]
    assert CapitalExperiment.objects.filter(pk=experiment.pk).exists()

    applied = retire_v1_capital(expected_manifest=manifest, apply=True)

    assert applied["status"] == "APPLIED"
    assert not CapitalExperiment.objects.filter(pk=experiment.pk).exists()
    assert not CapitalPolicyRun.objects.exists()
    assert not CapitalLedgerEntry.objects.exists()
    assert {
        "PredictionExperiment": PredictionExperiment.objects.count(),
        "Prediction": Prediction.objects.count(),
        "Decision": Decision.objects.count(),
        "OddsObservation": OddsObservation.objects.count(),
    } == upstream
    assert len(provision_automatic_configs()) == 7
    assert retire_v1_capital()["status"] == "NO_WORK"
    assert Decision.objects.filter(pk=decisions[0].pk).exists()


def test_v1_retirement_fails_closed_for_mixed_series():
    series = CapitalLongitudinalSeries.objects.create(
        code="mixed-series",
        evidence_class="PROSPECTIVE",
        source_model_code="DIXON_COLES",
        decision_policy_code="MODAL_ALL",
        frozen_competition_ids=[1],
        cohort_hash="a" * 64,
        epoch=datetime(2026, 1, 1, tzinfo=timezone.utc),
        mode="REPLAY",
        initial_bankroll=Decimal("100"),
        config={},
    )
    common = {
        "longitudinal_series": series,
        "source_model_code": "DIXON_COLES",
        "decision_policy_code": "MODAL_ALL",
        "mode": "REPLAY",
        "initial_bankroll": Decimal("100"),
        "config": {},
        "input_count": 0,
        "input_hash": "b" * 64,
        "input_manifest": {"schema": "fs010-longitudinal-capital-v1"},
    }
    CapitalExperiment.objects.create(engine_version="fs004-v1", **common)
    CapitalExperiment.objects.create(
        engine_version="fs999-unknown",
        semantic_identity="mixed-non-v1",
        **common,
    )

    with pytest.raises(
        CapitalRetirementScopeError, match="AMBIGUOUS_OR_MIXED_V1_SERIES"
    ):
        build_v1_retirement_manifest()


def test_v1_retirement_apply_requires_exact_prior_manifest():
    with pytest.raises(
        CapitalRetirementScopeError, match="APPLY_REQUIRES_DRY_RUN_MANIFEST"
    ):
        retire_v1_capital(apply=True)


def test_compatible_v1_series_is_deleted_only_after_its_snapshots():
    series = CapitalLongitudinalSeries.objects.create(
        code="compatible-v1-series",
        evidence_class="PROSPECTIVE",
        source_model_code="DIXON_COLES",
        decision_policy_code="MODAL_ALL",
        frozen_competition_ids=[1],
        cohort_hash="c" * 64,
        epoch=datetime(2026, 1, 1, tzinfo=timezone.utc),
        mode="REPLAY",
        initial_bankroll=Decimal("100"),
        config={},
    )
    snapshot = CapitalExperiment.objects.create(
        longitudinal_series=series,
        source_model_code="DIXON_COLES",
        decision_policy_code="MODAL_ALL",
        engine_version="fs004-v1",
        mode="REPLAY",
        initial_bankroll=Decimal("100"),
        config={},
        input_count=0,
        input_hash="d" * 64,
        input_manifest={"schema": "fs010-longitudinal-capital-v1"},
    )
    series.current_snapshot = snapshot
    series.save()
    manifest = build_v1_retirement_manifest()

    assert manifest["ids"]["CapitalLongitudinalSeries"] == [series.pk]
    assert (
        retire_v1_capital(expected_manifest=manifest, apply=True)["status"] == "APPLIED"
    )
    assert not CapitalExperiment.objects.filter(pk=snapshot.pk).exists()
    assert not CapitalLongitudinalSeries.objects.filter(pk=series.pk).exists()


def test_v1_retirement_fails_closed_when_scope_drifts_after_dry_run():
    prediction_experiment, _ = create_capital_stream(
        [{"outcome": Match.OUTCOME_HOME}],
        decision_policy="MODAL_ALL",
        suffix="-drift",
    )
    kwargs = {
        "prediction_experiment": prediction_experiment,
        "decision_policy_code": "MODAL_ALL",
        "source_model_code": Prediction.DIXON_COLES,
        "config": {
            "mode": "REPLAY",
            "initial_bankroll": "100",
            "policies": [{"code": "FLAT_UNIT", "config": {"unit": "1"}}],
        },
    }
    run_capital_experiment(**kwargs)
    manifest = build_v1_retirement_manifest()
    run_capital_experiment(**kwargs)

    with pytest.raises(CapitalRetirementScopeError, match="RETIREMENT_SCOPE_DRIFT"):
        retire_v1_capital(expected_manifest=manifest, apply=True)
