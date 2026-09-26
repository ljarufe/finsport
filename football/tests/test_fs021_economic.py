"""Economic selection branches must remain deterministic and simulation-only."""

from decimal import Decimal

import numpy as np
import pytest

from football.experiments.economic_selector import select_economic_baseline


def case(returns, drawdowns=None, tails=None, *, risky=()):
    n = len(returns)
    drawdowns = drawdowns or ["0.1"] * n
    tails = tails or ["0.1"] * n
    observed = {
        str(lag): [
            dict(
                structurally_complete=True,
                total_return=str(returns[i]),
                maximum_drawdown=str(drawdowns[i]),
                ever_nonpositive_equity=i in risky,
                operational_depletion=False,
                economic_ruin=False,
                policy_termination="",
                termination_reason="",
                hard_risk="FAIL" if i in risky else "PASS",
                placements=38,
                placed_competitions=[1, 2, 3],
                placed_weeks=[1, 2, 3, 4],
            )
            for i in range(n)
        ]
        for lag in (120, 130, 150)
    }
    return dict(
        schema="ECONOMIC_SELECTOR_INPUT_V1",
        candidates=[dict(integrated_index=i) for i in range(n)],
        observed=observed,
        scores={
            str(block): np.tile([-float(x) for x in tails], (20, 1))
            for block in (1, 2, 4)
        },
        scientific_disposition="UNSTABLE",
    )


def test_positive_high_risk_is_still_one_simulation_selection():
    result = select_economic_baseline(case(["0.2"], ["0.99"], ["0.96"], risky=(0,)))
    assert result["winner"] == 0
    assert result["mode"] == "PRACTICAL_BASELINE_SIMULATION_ONLY_HIGH_RISK"
    assert "OBSERVED_DRAWDOWN_GE_50_PERCENT" in result["risk_warnings"]
    assert result["activation"]["real_betting"] is False


def test_negative_and_zero_are_distinct_from_positive():
    negative = select_economic_baseline(case(["-0.3", "-0.2"]))
    assert negative["mode"] == "DIAGNOSTIC_ONLY__NO_NEW_STAKES"
    assert negative["winner"] == 1
    zero = select_economic_baseline(case(["-0.1", "0"]))
    assert zero["mode"] == "BREAKEVEN_SIMULATION_ONLY"
    assert zero["winner"] == 1


def test_crossed_frontier_uses_positive_fallback():
    result = select_economic_baseline(
        case(["0.1", "0.2"], ["0.1", "0.4"], ["0.4", "0.1"])
    )
    assert result["frontier"] == [0, 1]
    assert result["survivors"] == []
    assert result["fallback"] is True
    assert (
        max(
            result["fallback_violations"]["D_normalized"],
            result["fallback_violations"]["L_normalized"],
        )
        > 0
    )
    assert result["mode"] == "PRACTICAL_BASELINE_SIMULATION_ONLY_HIGH_RISK"


def test_decimal_return_order_and_canonical_tie_break():
    result = select_economic_baseline(case(["0.1000000000000000000000000001", "0.1"]))
    assert Decimal(result["rows"][0]["R"]) > Decimal(result["rows"][1]["R"])
    assert result["winner"] == 0
    tied = select_economic_baseline(case(["0.1", "0.1"]))
    assert tied["winner"] == 0


def test_nonfinite_bootstrap_is_technical_error():
    payload = case(["0.1"])
    payload["scores"]["1"][0, 0] = np.nan
    with pytest.raises(ValueError, match="ECONOMIC_SCORE_MATRIX"):
        select_economic_baseline(payload)


def test_future_bootstrap_risk_accumulator_preserves_terminal_score():
    from football.experiments.capital_analysis import week_start
    from football.experiments.capital_runner import CANDIDATES
    from football.experiments.integrated_events import run_integrated_path
    from football.tests.test_fs020_capital import AT, opp

    rows = [opp(1, won=False), opp(2, minute=180, won=True)]
    plain = run_integrated_path(rows, CANDIDATES[0])
    enriched = run_integrated_path(
        rows, CANDIDATES[0], risk_horizon_start=week_start(AT)
    )
    assert enriched["metrics"] == plain["metrics"]
    assert (
        enriched["risk_accumulators"]["maximum_drawdown"]
        == plain["metrics"]["maximum_drawdown"]
    )
    assert Decimal(enriched["risk_accumulators"]["mean_reserved_exposure"]) > 0


def test_future_risk_shard_is_immutable_and_manifest_verified(tmp_path):
    from football.experiments.integrated_runner import (
        RISK_COLUMNS,
        existing_risks,
        save_risk_shard,
    )

    spec = dict(
        runner={},
        input=dict(cohort_sha="cohort", stream_sha="stream", calendar_sha="calendar"),
    )
    row = np.zeros((231, len(RISK_COLUMNS)), dtype=np.float64)
    save_risk_shard(tmp_path, spec, 1, 0, 1, [row])
    values, covered = existing_risks(tmp_path, spec, 1)
    assert covered == {0}
    assert np.array_equal(values[0], row)
    save_risk_shard(tmp_path, spec, 1, 0, 1, [row])
    with pytest.raises(ValueError, match="CORRUPT_CHECKPOINT"):
        path = tmp_path / "risk-shards/150-1-00000-00001.npy"
        path.write_bytes(path.read_bytes()[:-8])
        existing_risks(tmp_path, spec, 1)


def test_explanatory_top20_places_selected_and_risk_survivors_first():
    import csv
    import io

    from football.experiments.economic_report import output_files

    rows = [
        dict(
            integrated_index=i,
            R=r,
            D=d,
            L=loss,
            tier=1,
            min_placements=100,
            selection_reason="SELECTED" if i == 209 else "OTHER",
        )
        for i, r, d, loss in (
            (60, "1.2426", "0.7851", 0.9868),
            (202, "0.8487", "0.2154", 0.3391),
            (209, "0.6667", "0.1223", 0.1760),
            (216, "0.6559", "0.0848", 0.1708),
            (223, "0.4517", "0.0746", 0.1717),
        )
    ]
    result = dict(
        rows=rows,
        winner=209,
        tier=1,
        frontier=[60, 202, 209, 216, 223],
        survivors=[209, 216, 223],
        execution_id="synthetic",
        mode="PRACTICAL_BASELINE_SIMULATION_ONLY",
        original_practical_winner=60,
        scientific_disposition="UNSTABLE",
        thresholds=dict(D=0.21, L=0.25),
        fallback=False,
        risk_warnings=[],
        reconciled_ledgers=0,
        logical_suffixes_verified=0,
    )
    files = output_files(result, [])
    ranked = list(
        csv.DictReader(io.StringIO(files["FS-021_economic_top20.csv"].decode()))
    )
    assert [int(row["integrated_index"]) for row in ranked] == [209, 216, 223, 60, 202]
    complete = list(
        csv.DictReader(io.StringIO(files["FS-021_economic_231.csv"].decode()))
    )
    assert [int(row["integrated_index"]) for row in complete] == [
        60,
        202,
        209,
        216,
        223,
    ]
    assert b"upstream_retention_index" not in files["FS-021_economic_selector_v1.json"]


def test_reporting_v1_1_is_immutable_and_independent_of_retention_status(
    tmp_path, monkeypatch
):

    import json

    from football.experiments import economic_report as report

    execution = tmp_path / "execution"
    execution.mkdir()
    (execution / "economic_selection_v1").mkdir()
    old = execution / "economic_selection_v1/FS-021_economic_selector_v1.json"
    old.write_text('{"upstream_retention_index":"MISSING_REVIEW"}\n')
    legacy_bytes = old.read_bytes()
    result = dict(
        rows=[
            dict(
                integrated_index=0,
                R="0.1",
                D="0.2",
                L=0.3,
                tier=1,
                min_placements=38,
                selection_reason="SELECTED",
            )
        ],
        winner=0,
        tier=1,
        frontier=[0],
        survivors=[0],
        thresholds=dict(D=0.2, L=0.3),
        execution_id=execution.name,
        method_version="FS021_SINGLE_ECONOMIC_SELECTOR_V1",
        source_hashes=dict(spec="test", run="test", observed="test"),
        mode="PRACTICAL_BASELINE_SIMULATION_ONLY",
        original_practical_winner=0,
        scientific_disposition="UNSTABLE",
        fallback=False,
        risk_warnings=[],
        activation=dict(
            automatic_operational_routing=False,
            real_betting=False,
        ),
        reconciled_ledgers=0,
        logical_suffixes_verified=0,
    )
    monkeypatch.setattr(report, "build_economic_analysis", lambda *_: (result, []))
    spec = dict(
        bootstrap=dict(replicates=5000),
        input=dict(candidates=[dict(integrated_index=0)]),
    )
    report.analyze_existing(execution, spec, ())
    previous_manifest = (
        execution / report.OUTPUT_DIR / "FS-021_economic_manifest_v1.json"
    )
    historical = json.loads(previous_manifest.read_text())
    historical["selector_code_sha256"] = "historical_pre_format_hash"
    previous_manifest.write_text(report.canonical(historical) + "\n")
    before = (
        execution / report.OUTPUT_DIR / "FS-021_economic_manifest_v1.json"
    ).read_bytes()
    (execution / "RETENTION_INDEX.tsv").write_text("new retention status\n")
    report.analyze_existing(execution, spec, ())
    assert (
        execution / report.OUTPUT_DIR / "FS-021_economic_manifest_v1.json"
    ).read_bytes() == before
    assert old.read_bytes() == legacy_bytes
    published = report.publish_economic_existing(execution, tmp_path)
    assert published["report_version"] == report.REPORT_VERSION
    assert (tmp_path / "docs/experiments/FS-021/execution/economic_v1_1.json").exists()
    assert not (tmp_path / "docs/research").exists()
