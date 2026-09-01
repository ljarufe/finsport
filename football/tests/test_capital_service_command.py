import json
from copy import deepcopy
from io import StringIO
from unittest import mock

import pytest
from django.contrib import admin
from django.core.management import call_command
from django.test import RequestFactory

from football.capital.contracts import CapitalInputError
from football.capital.service import (
    build_input_manifest,
    run_capital_experiment,
    select_decision_basis,
)
from football.models import (
    CapitalExperiment,
    CapitalLedgerEntry,
    CapitalPolicyRun,
    Decision,
    Prediction,
)

from .capital_helpers import create_capital_stream

pytestmark = pytest.mark.django_db


ALL_POLICIES = [
    {"code": "FLAT_UNIT", "config": {"unit": "1"}},
    {
        "code": "FIXED_FRACTION_BANKROLL",
        "config": {"fraction": "0.05"},
    },
    {
        "code": "FIXED_TARGET_PROFIT_NO_RECOVERY",
        "config": {"target_profit": "1"},
    },
    {"code": "LEGACY_RECOVERY", "config": {"initial_stake": "1"}},
    {
        "code": "LEGACY_CAPPED",
        "config": {"initial_stake": "1", "max_absolute_stake": "5"},
    },
    {
        "code": "LEGACY_PARTIAL",
        "config": {"target_profit": "1", "alpha": "0.5"},
    },
    {"code": "FRACTIONAL_KELLY", "config": {"lambda": "0.25"}},
]


def replay_config(policies=None):
    return {
        "mode": "REPLAY",
        "initial_bankroll": "100",
        "policies": deepcopy(policies or ALL_POLICIES),
    }


def test_service_persists_exact_selector_shared_manifest_runs_and_replay_ledger():
    source_experiment, source_decisions = create_capital_stream(
        [
            {"outcome": "HOME", "price": "2.1000"},
            {"outcome": "AWAY", "price": "2.3000"},
            {"action": Decision.ACTION_NO_BET, "outcome": ""},
        ],
        model_variant="BASE",
        decision_variant="EV_002",
    )
    before = list(
        Decision.objects.order_by("id").values(
            "id", "action", "reason", "selected_price", "model_probability"
        )
    )
    experiment = run_capital_experiment(
        prediction_experiment=source_experiment,
        source_model_code=Prediction.DIXON_COLES,
        source_model_variant="BASE",
        decision_policy_code="VALUE",
        decision_policy_variant="EV_002",
        config=replay_config(),
    )

    assert experiment.source_experiment == source_experiment
    assert experiment.source_model_code == Prediction.DIXON_COLES
    assert experiment.source_model_variant == "BASE"
    assert experiment.decision_policy_code == "VALUE"
    assert experiment.decision_policy_variant == "EV_002"
    assert experiment.input_count == 3
    assert experiment.input_manifest["decision_ids"] == [
        decision.id for decision in source_decisions
    ]
    assert experiment.input_manifest["sha256"] == experiment.input_hash
    assert len(experiment.policy_runs.all()) == 7
    assert set(experiment.policy_runs.values_list("status", flat=True)) == {"PRODUCED"}
    assert all(run.ledger_entries.count() == 3 for run in experiment.policy_runs.all())
    assert experiment.summary["pareto"] == {
        "status": "UNAVAILABLE",
        "reason": "MISSING_PARETO_DIMENSION:expected_shortfall",
    }
    assert all(
        "expected_shortfall" not in run.metrics for run in experiment.policy_runs.all()
    )
    assert before == list(
        Decision.objects.order_by("id").values(
            "id", "action", "reason", "selected_price", "model_probability"
        )
    )


def test_selector_identity_is_unambiguous_and_hash_is_reproducible():
    source_experiment, _ = create_capital_stream([{}])
    rows = select_decision_basis(
        prediction_experiment=source_experiment,
        source_model_code=Prediction.DIXON_COLES,
        decision_policy_code="VALUE",
    )
    _, first, first_hash = build_input_manifest(rows)
    _, second, second_hash = build_input_manifest(rows)
    assert first == second
    assert first_hash == second_hash

    with pytest.raises(CapitalInputError, match="Exactly one"):
        select_decision_basis(
            prediction_experiment=source_experiment,
            source_model_code=Prediction.DIXON_COLES,
            source_comparator_code="RESEARCH_COMPARATOR",
            decision_policy_code="VALUE",
        )


def test_all_no_bet_comparator_stream_remains_representable_without_fake_evidence():
    source_experiment, _ = create_capital_stream(
        [
            {"action": Decision.ACTION_NO_BET, "outcome": "", "price": None},
            {"action": Decision.ACTION_NO_BET, "outcome": "", "price": None},
        ],
        decision_policy="RESEARCH_COMPARATOR",
        comparator=True,
    )
    experiment = run_capital_experiment(
        prediction_experiment=source_experiment,
        source_comparator_code="RESEARCH_COMPARATOR",
        decision_policy_code="RESEARCH_COMPARATOR",
        config=replay_config([{"code": "FLAT_UNIT", "config": {"unit": "1"}}]),
    )
    run = experiment.policy_runs.get()
    assert run.status == "PRODUCED"
    assert run.metrics["capital_actions"] == 0
    assert run.metrics["total_staked"] == "0"
    assert run.ledger_entries.count() == 2


def test_unresolved_real_replay_is_honestly_unavailable_not_backfilled():
    source_experiment, _ = create_capital_stream([{"outcome": ""}])
    experiment = run_capital_experiment(
        prediction_experiment=source_experiment,
        source_model_code=Prediction.DIXON_COLES,
        decision_policy_code="VALUE",
        config=replay_config([{"code": "FLAT_UNIT", "config": {"unit": "1"}}]),
    )
    run = experiment.policy_runs.get()
    assert run.status == "UNAVAILABLE"
    assert run.reason == "UNAVAILABLE_INSUFFICIENT_RESOLVED_TIMESTAMP_VALID_DECISIONS"
    assert not run.ledger_entries.exists()


def test_stochastic_service_persists_real_es_and_complete_multi_policy_pareto():
    source_experiment, _ = create_capital_stream([{}, {}, {}])
    config = {
        "mode": "MONTE_CARLO",
        "initial_bankroll": "100",
        "policies": [
            {"code": "FLAT_UNIT", "config": {"unit": "1"}},
            {
                "code": "FIXED_FRACTION_BANKROLL",
                "config": {"fraction": "0.01"},
            },
        ],
        "simulation": {
            "seed": 19,
            "path_count": 128,
            "tail_level": 0.05,
            "mdd_thresholds": [0.1, 0.2],
        },
    }
    experiment = run_capital_experiment(
        prediction_experiment=source_experiment,
        source_model_code=Prediction.DIXON_COLES,
        decision_policy_code="VALUE",
        config=config,
    )
    runs = list(experiment.policy_runs.all())
    assert len(runs) == 2
    assert all(run.status == "PRODUCED" for run in runs)
    assert all(run.seed == 19 for run in runs)
    assert all(run.path_count == 128 for run in runs)
    assert all("expected_shortfall" in run.metrics for run in runs)
    assert all(run.metrics["numpy_version"] == "2.4.6" for run in runs)
    assert not CapitalLedgerEntry.objects.filter(policy_run__in=runs).exists()
    assert experiment.summary["pareto"]["metrics_used"] == [
        "return",
        "maximum_drawdown",
        "expected_shortfall",
        "practical_ruin_probability",
        "stake_concentration",
    ]


def test_required_arm_failure_is_persisted_and_never_silently_omitted():
    source_experiment, _ = create_capital_stream([{}])
    experiment = run_capital_experiment(
        prediction_experiment=source_experiment,
        source_model_code=Prediction.DIXON_COLES,
        decision_policy_code="VALUE",
        config=replay_config(
            [{"code": "FLAT_UNIT", "config": {"unit": "not-a-decimal"}}]
        ),
    )
    run = experiment.policy_runs.get()
    assert run.status == "FAILED"
    assert run.reason.startswith("INVALID_DECIMAL_POLICY_CONFIG")


def test_command_delegates_one_workflow_and_admin_registers_audit_models():
    source_experiment, _ = create_capital_stream([{}])
    output = StringIO()
    call_command(
        "evaluate_capital_policies",
        prediction_experiment=source_experiment.id,
        model_code=Prediction.DIXON_COLES,
        model_variant="",
        decision_policy="VALUE",
        decision_variant="",
        config=json.dumps(
            replay_config([{"code": "FLAT_UNIT", "config": {"unit": "1"}}])
        ),
        stdout=output,
    )
    assert "capital_experiment=" in output.getvalue()
    assert CapitalExperiment.objects.count() == 1
    assert admin.site.is_registered(CapitalExperiment)
    assert admin.site.is_registered(CapitalPolicyRun)
    assert admin.site.is_registered(CapitalLedgerEntry)


def test_capital_admin_surfaces_are_view_only_without_mutation_permissions():
    request = RequestFactory().get("/admin/")
    request.user = mock.Mock()
    request.user.has_perm.return_value = True
    critical_fields = {
        CapitalExperiment: {
            "source_experiment",
            "source_model_code",
            "source_model_variant",
            "source_comparator_code",
            "decision_policy_code",
            "decision_policy_variant",
            "mode",
            "initial_bankroll",
            "input_count",
        },
        CapitalPolicyRun: {
            "policy_code",
            "policy_version",
            "policy_config",
            "status",
            "reason",
            "seed",
            "path_count",
            "metrics",
        },
        CapitalLedgerEntry: {
            "requested_stake",
            "applied_stake",
            "bankroll_before",
            "bankroll_after",
            "profit_loss",
            "cap_hit",
            "shortfall",
            "practical_ruin",
            "termination_reason",
        },
    }
    for model, expected_readonly in critical_fields.items():
        model_admin = admin.site._registry[model]
        readonly = set(model_admin.get_readonly_fields(request))
        concrete = {field.name for field in model._meta.concrete_fields}
        assert concrete <= readonly
        assert expected_readonly <= readonly
        assert model_admin.has_add_permission(request) is False
        assert model_admin.has_change_permission(request) is False
        assert model_admin.has_delete_permission(request) is False
        assert model_admin.has_view_permission(request) is True

    experiment_admin = admin.site._registry[CapitalExperiment]
    inline = experiment_admin.inlines[0](CapitalExperiment, admin.site)
    inline_readonly = set(inline.get_readonly_fields(request))
    assert {
        field.name for field in CapitalPolicyRun._meta.concrete_fields
    } <= inline_readonly
    assert inline.has_add_permission(request) is False
    assert inline.has_change_permission(request) is False
    assert inline.has_delete_permission(request) is False
    assert inline.can_delete is False


def test_evaluator_has_no_provider_or_financial_write_call(monkeypatch):
    source_experiment, _ = create_capital_stream([{}])

    def forbidden(*args, **kwargs):
        del args, kwargs
        raise AssertionError("external provider call")

    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    experiment = run_capital_experiment(
        prediction_experiment=source_experiment,
        source_model_code=Prediction.DIXON_COLES,
        decision_policy_code="VALUE",
        config=replay_config([{"code": "FLAT_UNIT", "config": {"unit": "1"}}]),
    )
    assert experiment.policy_runs.get().status == "PRODUCED"
