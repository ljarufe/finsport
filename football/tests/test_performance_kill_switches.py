from pathlib import Path
from types import SimpleNamespace

from django.test import override_settings

from football.models import Prediction
from football.pipeline.service import (
    _capital_experiment_allowed,
    _r45_capture_prediction_candidates,
)
from football.prediction.service import _runtime_model_gate


@override_settings(FOOTBALL_MODERNIZED_R45_ENABLED=False)
def test_r45_candidate_generation_is_disabled():
    capture_result = SimpleNamespace(plan={"items": []})

    assert _r45_capture_prediction_candidates(capture_result, None) == []


@override_settings(FOOTBALL_MODERNIZED_R45_ENABLED=False)
def test_r45_is_removed_from_requested_models():
    requested = {
        Prediction.DIXON_COLES,
        Prediction.MODERNIZED_R45,
    }

    assert _runtime_model_gate(requested) == {Prediction.DIXON_COLES}


@override_settings(FOOTBALL_MODERNIZED_R45_CAPITAL_ENABLED=False)
def test_r45_only_experiments_are_excluded_from_capital_baseline():
    r45_only = SimpleNamespace(config={"model_codes": [Prediction.MODERNIZED_R45]})
    dixon_coles = SimpleNamespace(config={"model_codes": [Prediction.DIXON_COLES]})
    mixed = SimpleNamespace(
        config={
            "model_codes": [
                Prediction.DIXON_COLES,
                Prediction.MODERNIZED_R45,
            ]
        }
    )

    assert not _capital_experiment_allowed(r45_only)
    assert _capital_experiment_allowed(dixon_coles)
    assert _capital_experiment_allowed(mixed)


def test_operational_compose_forces_performance_kill_switches_off():
    root = Path(__file__).resolve().parents[2]
    compose = (root / "compose.yml").read_text()

    assert compose.count('INKABET_AUTOMATIC_ENABLED: "False"') >= 2
    assert compose.count('FOOTBALL_MODERNIZED_R45_ENABLED: "False"') >= 2
    assert compose.count('FOOTBALL_MODERNIZED_R45_CAPITAL_ENABLED: "False"') >= 2
