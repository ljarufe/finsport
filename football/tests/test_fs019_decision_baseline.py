"""Focused deterministic contract tests for FS-019 Pass 1."""

import copy
import gzip
import io
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import numpy as np
import pytest
import requests
from django.core.management import call_command
from django.core.management.base import CommandError

from football.experiments import decision_artifacts, decision_runner
from football.experiments.comparison import (
    fallback_selection,
    observed_ranking,
    paired_weekly_bootstrap,
    scientific_disposition,
    stability_checks,
)
from football.experiments.decision import (
    CANDIDATE_IDS,
    CANDIDATES,
    EXPECTED_ACTION_COUNTS,
    candidate_matrix,
    replay_candidate,
    replay_decisions,
    validate_frozen_action_counts,
)
from football.experiments.decision_runner import DecisionSpec
from football.experiments.historical_prices import best_price, validate_price_evidence
from football.experiments.reward import (
    fixed_unit_reward,
    settle_rows,
    summarize_decisions,
)
from football.experiments.storage import (
    canonical,
    decision_root,
    experiment_workspace_root,
    identity,
    local_decision_spec_path,
)
from football.experiments.views import deterministic_gzip

UTC = timezone.utc
KICKOFF = datetime(2026, 1, 12, 20, tzinfo=UTC)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path, settings):
    settings.BASE_DIR = tmp_path
    settings.TIME_ZONE = "America/Lima"
    settings.FOOTBALL_PIPELINE_ENABLED = False
    settings.FOOTBALL_CAPTURE_ENABLED = False
    settings.CELERY_TASK_DEFAULT_QUEUE = "finsport.local.safe"
    monkeypatch.setenv("FINSPORT_EXPERIMENT_RUNTIME", "finsport-dev")
    monkeypatch.setattr(
        requests.Session,
        "get",
        Mock(side_effect=AssertionError("LIVE NETWORK FORBIDDEN")),
    )


def price_row(*, probabilities=(0.5, 0.3, 0.2), books=("pinnacle", "bet365")):
    prices = {
        "pinnacle": {"101": 2.1, "102": 3.2, "103": 4.0},
        "bet365": {"101": 2.1, "102": 3.3, "103": 4.2},
        "unibet": {"101": 2.0, "102": 3.3, "103": 4.2},
    }
    timestamps = {
        bookmaker: {
            outcome: (KICKOFF - timedelta(minutes=31 + index)).isoformat()
            for index, outcome in enumerate(("101", "102", "103"))
        }
        for bookmaker in books
    }
    ages = {
        bookmaker: {
            outcome: 1860 + index * 60
            for index, outcome in enumerate(("101", "102", "103"))
        }
        for bookmaker in books
    }
    return {
        "match_id": 1,
        "competition_id": 1270,
        "kickoff": KICKOFF.isoformat(),
        "actual_regulation_outcome": "HOME",
        "model_code": "MARKET_CONSENSUS",
        "model_version": "fs013-market-consensus-v2",
        "config_identity": decision_runner.UPSTREAM["config_identity"],
        "p_home": probabilities[0],
        "p_draw": probabilities[1],
        "p_away": probabilities[2],
        "evidence_profile": "ODDSPAPI_RECONSTRUCTED_T30_V1",
        "bookmaker_count": len(books),
        "selected_prices": {bookmaker: prices[bookmaker] for bookmaker in books},
        "selected_quote_timestamps": timestamps,
        "quote_ages_seconds": ages,
        "provider_fixture_id": "fixture-1",
        "fs018_evidence_id": "e" * 64,
        "raw_cache_hash": "c" * 64,
    }


def test_candidate_matrix_is_exact_and_value_is_absent():
    assert len(CANDIDATES) == 6
    assert [candidate.order for candidate in CANDIDATES] == list(range(1, 7))
    assert [candidate.threshold for candidate in CANDIDATES] == [
        None,
        0.40,
        0.45,
        0.50,
        0.55,
        0.60,
    ]
    assert all("VALUE" not in canonical(candidate) for candidate in candidate_matrix())


def test_current_policy_ties_equality_and_reason_codes():
    tie = price_row(probabilities=(1 / 3, 1 / 3, 1 / 3))
    modal = replay_candidate(tie, CANDIDATES[0])
    assert modal["selected_outcome"] == "HOME"
    assert modal["reason"] == "MODAL_OUTCOME"
    exact = replay_candidate(price_row(probabilities=(0.4, 0.3, 0.3)), CANDIDATES[1])
    assert exact["action"] == "BET"
    assert exact["reason"] == "CONFIDENCE_THRESHOLD_MET"
    below = replay_candidate(
        price_row(probabilities=(0.399, 0.301, 0.3)), CANDIDATES[1]
    )
    assert below["action"] == "NO_BET"
    assert below["reason"] == "BELOW_CONFIDENCE_THRESHOLD"


def test_price_adapter_two_three_books_raw_max_and_tie_order():
    two = price_row()
    assert validate_price_evidence(two) is two
    home = best_price(two, "HOME")
    assert home["selected_price"] == 2.1
    assert home["co_best_bookmakers"] == ["pinnacle", "bet365"]
    assert home["representative_bookmaker"] == "pinnacle"
    assert (
        home["selected_quote_timestamp"]
        == two["selected_quote_timestamps"]["pinnacle"]["101"]
    )
    assert home["selected_quote_age_seconds"] == 1860
    assert home["provider_fixture_id"] == "fixture-1"
    assert home["raw_cache_hash"] == "c" * 64
    three = price_row(books=("pinnacle", "bet365", "unibet"))
    away = best_price(three, "AWAY")
    assert away["selected_price"] == 4.2
    assert away["co_best_bookmakers"] == ["bet365", "unibet"]
    assert away["representative_bookmaker"] == "bet365"
    assert away["fs018_evidence_id"] == "e" * 64


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row["selected_prices"]["pinnacle"].pop("103"),
        lambda row: row["selected_prices"]["pinnacle"].update({"101": 1}),
        lambda row: row["selected_quote_timestamps"]["pinnacle"].update(
            {"101": (KICKOFF - timedelta(minutes=29)).isoformat()}
        ),
        lambda row: row["quote_ages_seconds"]["pinnacle"].update({"101": 1799}),
        lambda row: row.update({"raw_cache_hash": None}),
    ],
)
def test_price_adapter_fails_closed_on_structural_or_post_t30_evidence(mutation):
    row = price_row()
    mutation(row)
    with pytest.raises(ValueError):
        validate_price_evidence(row)


def test_fixed_unit_settlement_all_branches():
    assert fixed_unit_reward("BET", "HOME", "HOME", 2.5) == 1.5
    assert fixed_unit_reward("BET", "HOME", "AWAY", 2.5) == -1
    assert fixed_unit_reward("NO_BET", None, "HOME") == 0
    assert fixed_unit_reward("BET", "HOME", "VOID", 2.5) == 0
    assert fixed_unit_reward("BET", "HOME", "REFUND", 2.5) == 0


def _settled(candidate, match_id, league, kickoff, reward):
    return {
        "candidate_id": candidate,
        "match_id": match_id,
        "competition_id": league,
        "kickoff": kickoff.isoformat(),
        "action": "BET" if reward else "NO_BET",
        "selected_outcome": "HOME" if reward else None,
        "actual_regulation_outcome": "HOME",
        "reason": "MODAL_OUTCOME" if reward else "BELOW_CONFIDENCE_THRESHOLD",
        "selected_price": reward + 1 if reward > 0 else (2 if reward < 0 else None),
        "representative_bookmaker": "pinnacle" if reward else None,
        "co_best_bookmakers": ["pinnacle"] if reward else None,
        "selected_quote_age_seconds": 1800 if reward else None,
        "stake": 1.0 if reward else 0.0,
        "reward": float(reward),
    }


def test_primary_metric_keeps_no_bet_denominator_and_equal_league_weight():
    rows = [
        _settled("A", 1, 10, KICKOFF, 1),
        _settled("A", 2, 10, KICKOFF + timedelta(hours=1), 0),
        _settled("A", 3, 20, KICKOFF + timedelta(hours=2), -1),
    ]
    report = summarize_decisions(rows, ("A",), (10, 20))["A"]
    assert report["per_league"]["10"]["ppo"] == 0.5
    assert report["per_league"]["20"]["ppo"] == -1
    assert report["global_ppo"] == -0.25
    assert report["pooled_ppo_diagnostic"] == 0


def bootstrap_rows(candidate_ids=("A", "B", "C"), leagues=(10, 20)):
    rows = []
    match_id = 0
    for round_number in range(2):
        for league in leagues:
            match_id += 1
            kickoff = KICKOFF + timedelta(days=round_number * 8, minutes=league)
            values = (1.0, 0.25, -0.5)
            rewards = {
                candidate: values[index]
                for index, candidate in enumerate(candidate_ids)
            }
            for candidate in candidate_ids:
                rows.append(
                    _settled(candidate, match_id, league, kickoff, rewards[candidate])
                )
    return sorted(
        rows,
        key=lambda row: (row["competition_id"], row["kickoff"], row["match_id"]),
    )


def test_bootstrap_is_paired_deterministic_and_uses_linear_max_guard():
    rows = bootstrap_rows()
    first = paired_weekly_bootstrap(rows, ("A", "B", "C"), (10, 20), replicates=50)
    second = paired_weekly_bootstrap(rows, ("A", "B", "C"), (10, 20), replicates=50)
    assert first == second
    assert first["seed"] == 18092026
    assert first["quantile_method"] == "LINEAR_R7"
    assert first["block_count"] == 4
    assert first["observed_top"] == "A"
    assert set(first["simultaneous_lower_bounds"]) == {"B", "C"}
    top_scores = np.asarray(first["replicate_scores"]["A"])
    adverse = []
    observed = {"B": 0.75, "C": 1.5}
    for candidate in ("B", "C"):
        delta = top_scores - np.asarray(first["replicate_scores"][candidate])
        adverse.append(observed[candidate] - delta)
    assert first["simultaneous_q95"] == pytest.approx(
        np.quantile(np.max(np.column_stack(adverse), axis=1), 0.95, method="linear")
    )


def test_observed_exact_tie_uses_frozen_candidate_order():
    rows = [_settled(candidate, 1, 10, KICKOFF, 1) for candidate in CANDIDATE_IDS]
    _, ranking = observed_ranking(rows, CANDIDATE_IDS, (10,))
    assert ranking == list(CANDIDATE_IDS)


def test_stability_keeps_fixed_pair_and_exact_chronological_halves():
    leagues = tuple(range(10))
    rows = bootstrap_rows(("A", "B"), leagues)
    result = stability_checks(rows, "A", "B", leagues)
    assert len(result["leave_one_league_out"]) == 10
    assert result["chronological_split_index"] == 10
    assert [half["sample_count"] for half in result["chronological_halves"]] == [10, 10]
    assert result["fixed_top"] == "A"
    assert result["fixed_strongest_alternative"] == "B"
    assert all(delta > 0 for delta in result["deltas"])


def test_stability_uses_exact_953_953_split_for_frozen_corpus_size():
    rows = []
    leagues = decision_runner.COMPETITION_IDS
    for index in range(1906):
        league = leagues[index % len(leagues)]
        kickoff = KICKOFF + timedelta(minutes=index)
        rows.extend(
            (
                _settled("A", index + 1, league, kickoff, 1),
                _settled("B", index + 1, league, kickoff, 0.25),
            )
        )
    result = stability_checks(rows, "A", "B", leagues)
    assert result["chronological_split_index"] == 953
    assert [half["sample_count"] for half in result["chronological_halves"]] == [
        953,
        953,
    ]


@pytest.mark.parametrize(
    "available,bounds,deltas,expected",
    [
        (False, [1] * 5, [-1] + [1] * 11, "INSUFFICIENT_EVIDENCE"),
        (True, [1] * 5, [-0.01] + [1] * 11, "UNSTABLE"),
        (True, [0.01] * 5, [0.01] * 12, "CLEAR_SUPERIORITY"),
        (True, [0, 1, 1, 1, 1], [0.01] * 12, "NO_CLEAR_SUPERIORITY"),
        (True, [0.01] * 5, [0] + [0.01] * 11, "NO_CLEAR_SUPERIORITY"),
        (
            True,
            [float("nan"), 1, 1, 1, 1],
            [0.01] * 12,
            "INSUFFICIENT_EVIDENCE",
        ),
        (True, [1] * 4, [1] * 12, "INSUFFICIENT_EVIDENCE"),
        (True, [1] * 5, [1] * 11, "INSUFFICIENT_EVIDENCE"),
    ],
)
def test_scientific_disposition_precedence_and_strictness(
    available, bounds, deltas, expected
):
    assert scientific_disposition(available, bounds, deltas) == expected


@pytest.mark.parametrize(
    "disposition,modal_bound,expected,promote",
    [
        ("CLEAR_SUPERIORITY", -1, CANDIDATE_IDS[1], True),
        ("NO_CLEAR_SUPERIORITY", 0, CANDIDATE_IDS[0], True),
        ("NO_CLEAR_SUPERIORITY", 0.1, CANDIDATE_IDS[1], True),
        ("UNSTABLE", 0, CANDIDATE_IDS[0], True),
        ("UNSTABLE", 0.1, CANDIDATE_IDS[1], True),
        ("INSUFFICIENT_EVIDENCE", 0, None, False),
    ],
)
def test_fallback_truth_table(disposition, modal_bound, expected, promote):
    top = CANDIDATE_IDS[1]
    scores = {
        candidate: 1 - index / 10 for index, candidate in enumerate(CANDIDATE_IDS)
    }
    scores[top] = 2
    bounds = {
        candidate: (modal_bound if candidate == CANDIDATE_IDS[0] else 0.1)
        for candidate in CANDIDATE_IDS
        if candidate != top
    }
    result = fallback_selection(disposition, top, scores, bounds)
    assert result["selected"] == expected
    assert result["promotion_permitted"] is promote


def test_replay_has_one_row_per_candidate_and_never_calls_provider():
    rows = settle_rows(replay_decisions([price_row()]))
    assert len(rows) == 6
    assert [row["candidate_id"] for row in rows] == list(CANDIDATE_IDS)
    assert all(row["reward"] is not None for row in rows)


def test_command_requires_isolated_dev_before_reading_spec(settings, tmp_path):
    settings.FOOTBALL_PIPELINE_ENABLED = True
    with pytest.raises(CommandError, match="RESEARCH_REQUIRES_ISOLATED_FINSPORT_DEV"):
        call_command(
            "run_decision_experiment",
            spec=str(tmp_path / "missing.json"),
            stdout=io.StringIO(),
        )


def test_command_freeze_cannot_promote(tmp_path):
    spec_path = tmp_path / "tmp/FS-019_experiments/spec.json"
    with pytest.raises(CommandError, match="Freeze cannot analyze or promote"):
        call_command(
            "run_decision_experiment",
            spec=str(spec_path),
            freeze=True,
            promote=True,
            stdout=io.StringIO(),
        )


def test_upstream_binding_verifies_all_local_lineage_and_fails_on_mismatch(
    monkeypatch, tmp_path
):
    manifest = [{"match_id": 1, "candidates": {}}]
    spec = {"data_cutoff": "2026-01-01T00:00:00+00:00"}
    synthetic = copy.deepcopy(decision_runner.UPSTREAM)
    synthetic.update(
        experiment_spec_id=identity(spec),
        manifest_hash=identity(manifest),
        prediction_cohort_hash="cohort",
        source_acquisition_id="acquisition",
        execution_runtime_id="runtime",
        analysis_id="analysis",
        data_cutoff=spec["data_cutoff"],
    )
    acquisition = {"run_id": "acquisition", "spec_id": synthetic["experiment_spec_id"]}
    run = {
        "analysis_id": "analysis",
        "source_acquisition_id": "acquisition",
        "execution_runtime_id": "runtime",
        "spec_id": synthetic["experiment_spec_id"],
        "spec": spec,
        "manifest": manifest,
        "summary": {"cohort_hash": "cohort"},
        "acquisition": acquisition,
    }
    run["run_id"] = identity(run)
    synthetic["full_run_id"] = run["run_id"]
    monkeypatch.setattr(decision_runner, "UPSTREAM", synthetic)
    monkeypatch.setattr(decision_runner, "per_match_rows", lambda run: iter(()))
    root = tmp_path / "FS-018"
    directory = root / "analysis"
    directory.mkdir(parents=True)
    (root / "acquisition").mkdir()
    (directory / "run.json").write_text(canonical(run))
    (directory / "manifest.json").write_text(canonical(manifest))
    (directory / "per_match.jsonl.gz").write_bytes(deterministic_gzip([]))
    (root / "acquisition" / "backfill.json").write_text(canonical(acquisition))
    authority = {
        key: synthetic[key]
        for key in (
            "baseline",
            "model_code",
            "model_version",
            "config_identity",
            "experiment_spec_id",
            "full_run_id",
            "manifest_hash",
            "data_cutoff",
        )
    }
    authority["cohort_hash"] = synthetic["prediction_cohort_hash"]
    authority_path = tmp_path / "authority.json"
    authority_path.write_text(canonical(authority))
    assert decision_runner._verify_upstream(authority_path, directory) == (
        run,
        manifest,
        acquisition,
    )
    authority["manifest_hash"] = "wrong"
    authority_path.write_text(canonical(authority))
    with pytest.raises(ValueError, match="UPSTREAM_AUTHORITY_MISMATCH:manifest_hash"):
        decision_runner._verify_upstream(authority_path, directory)


def test_upstream_binding_rejects_tampered_derived_per_match_view(
    monkeypatch, tmp_path
):
    expected = [
        {
            "match_id": 1,
            "competition_id": 1270,
            "kickoff": KICKOFF.isoformat(),
        }
    ]
    monkeypatch.setattr(
        decision_runner,
        "per_match_rows",
        lambda run: iter(expected),
    )

    path = tmp_path / "per_match.jsonl.gz"
    path.write_bytes(deterministic_gzip(expected))

    decision_runner._verify_per_match_view(path, {})

    damaged = copy.deepcopy(expected)
    damaged[0]["competition_id"] = 1272
    path.write_bytes(deterministic_gzip(damaged))

    with pytest.raises(
        ValueError,
        match="UPSTREAM_PER_MATCH_VIEW_MISMATCH",
    ):
        decision_runner._verify_per_match_view(path, {})


def valid_spec(snapshot_hash="a" * 64, cohort_hash=None):
    cohort_hash = cohort_hash or decision_runner.decision_common_cohort_hash(
        [price_row()]
    )
    return DecisionSpec(
        canonical(
            {
                **decision_runner.METHODOLOGY,
                "upstream": decision_runner.UPSTREAM,
                "competition_ids": list(decision_runner.COMPETITION_IDS),
                "decision_common_cohort_hash": cohort_hash,
                "snapshot": {
                    "file": f"decision-input-{snapshot_hash}.jsonl.gz",
                    "content_hash": snapshot_hash,
                    "row_count": 1906,
                    "per_league": {
                        str(key): value
                        for key, value in decision_runner.COMPETITION_COUNTS.items()
                    },
                },
            }
        )
    )


def promotion_run(spec, disposition="NO_CLEAR_SUPERIORITY"):
    rows = settle_rows(replay_decisions([price_row()]))
    metrics = summarize_decisions(rows, CANDIDATE_IDS, (1270,))
    summary = {
        "disposition": disposition,
        "promotion_permitted": disposition != "INSUFFICIENT_EVIDENCE",
        "selected": None if disposition == "INSUFFICIENT_EVIDENCE" else "MODAL_ALL",
        "decision_common_count": 1,
        "natural_count": 1,
        "price_coverage": 1.0,
        "observed_global_ppo": {candidate: 0.0 for candidate in CANDIDATE_IDS},
        "observed_order": list(CANDIDATE_IDS),
        "observed_top": "MODAL_ALL",
        "observed_strongest_alternative": CANDIDATE_IDS[1],
        "bootstrap": {
            "method": "test",
            "quantile_method": "LINEAR_R7",
            "replicates": 5000,
            "seed": 18092026,
            "block_count": 1,
            "draws_hash": "1" * 64,
            "replicate_scores_hash": "2" * 64,
            "observed_deltas": {},
            "simultaneous_q95": 0.0,
            "simultaneous_lower_bounds": {},
        },
        "stability": {},
        "survivors": list(CANDIDATE_IDS),
        "candidate_metrics": metrics,
    }
    run = {
        "execution_id": "execution",
        "execution_runtime": {"code": "test"},
        "execution_runtime_id": identity({"code": "test"}),
        "spec_id": spec.id,
        "spec": spec.data,
        "input_snapshot_hash": spec.data["snapshot"]["content_hash"],
        "decision_common_cohort_hash": spec.data["decision_common_cohort_hash"],
        "decision_rows_hash": decision_runner.snapshot_hash(rows),
        "decision_row_count": len(rows),
        "summary": summary,
        "resources": {},
        "warnings": [],
    }
    run["execution_id"] = decision_runner.execution_identity(
        spec.id, run["input_snapshot_hash"], run["execution_runtime_id"]
    )
    run["run_id"] = identity(run)
    return run, rows


def write_promotion_rows(run, rows):
    directory = decision_root() / run["execution_id"]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "decision-rows.jsonl.gz").write_bytes(deterministic_gzip(rows))


@pytest.mark.parametrize(
    "disposition",
    ["CLEAR_SUPERIORITY", "NO_CLEAR_SUPERIORITY", "UNSTABLE"],
)
def test_permitted_dispositions_promote(disposition, tmp_path):
    spec = valid_spec()
    allowed, rows = promotion_run(spec, disposition)
    write_promotion_rows(allowed, rows)
    record = decision_artifacts.promote_decision(allowed, spec, base=tmp_path)
    assert record["baseline"] == "GLOBAL_DECISION_V1"
    assert record["experiment"]["scientific_disposition"] == disposition
    assert record["upstream_prediction"] == decision_runner.UPSTREAM
    assert record["decision"] == {
        "policy_code": "MODAL_ALL",
        "policy_version": CANDIDATES[0].version,
        "policy_variant": "",
        "policy_config": {},
        "selected_candidate_id": "MODAL_ALL",
    }
    assert (
        record["experiment"]["decision_common_cohort_hash"]
        == spec.data["decision_common_cohort_hash"]
    )
    assert record["selected_decision_stream"]["schema"] == (
        decision_artifacts.STREAM_SCHEMA
    )


def test_promotion_is_idempotent_conflict_safe_and_insufficient_writes_nothing(
    tmp_path,
):
    spec = valid_spec()
    insufficient, _ = promotion_run(spec, "INSUFFICIENT_EVIDENCE")
    assert (
        decision_artifacts.promote_decision(insufficient, spec, base=tmp_path) is None
    )
    promotion_path = tmp_path / decision_artifacts.PROMOTION_REF
    assert not promotion_path.exists()
    allowed, rows = promotion_run(spec)
    write_promotion_rows(allowed, rows)
    record = decision_artifacts.promote_decision(allowed, spec, base=tmp_path)
    assert record["baseline"] == "GLOBAL_DECISION_V1"
    assert decision_artifacts.promote_decision(allowed, spec, base=tmp_path) == record
    conflict = copy.deepcopy(allowed)
    conflict["summary"]["selected"] = CANDIDATE_IDS[1]
    conflict["run_id"] = identity(
        {key: value for key, value in conflict.items() if key != "run_id"}
    )
    conflict_rows = rows
    conflict["run_id"] = identity(
        {key: value for key, value in conflict.items() if key != "run_id"}
    )
    write_promotion_rows(conflict, conflict_rows)
    with pytest.raises(ValueError, match="GLOBAL_DECISION_V1_ALREADY_FROZEN"):
        decision_artifacts.promote_decision(conflict, spec, base=tmp_path)


def test_decision_source_resolver_fails_closed_on_authority_and_stream(tmp_path):
    with pytest.raises(ValueError, match="AUTHORITY_OR_STREAM_MISSING"):
        decision_artifacts.resolve_global_decision(base=tmp_path)
    authority_path = tmp_path / decision_artifacts.PROMOTION_REF
    authority_path.parent.mkdir(parents=True)
    authority_path.write_text("not-json")
    with pytest.raises(ValueError, match="MALFORMED"):
        decision_artifacts.resolve_global_decision(base=tmp_path)
    authority_path.write_text(
        canonical({"schema": "UNKNOWN", "baseline": "GLOBAL_DECISION_V1"})
    )
    with pytest.raises(ValueError, match="UNSUPPORTED"):
        decision_artifacts.resolve_global_decision(base=tmp_path)
    spec = valid_spec()
    run, rows = promotion_run(spec)
    write_promotion_rows(run, rows)
    authority_path.unlink()
    record = decision_artifacts.promote_decision(run, spec, base=tmp_path)
    (tmp_path / record["selected_decision_stream"]["path"]).unlink()
    with pytest.raises(ValueError, match="AUTHORITY_OR_STREAM_MISSING"):
        decision_artifacts.resolve_global_decision(base=tmp_path)


def test_snapshot_hash_uses_semantic_rows_not_gzip_metadata():
    rows = [price_row()]
    assert decision_runner.snapshot_hash(rows) == decision_runner.snapshot_hash(
        json.loads(canonical(rows))
    )
    assert deterministic_gzip(rows) == deterministic_gzip(rows)


def authoritative_price_fixture():
    source = price_row()
    books = {}
    for bookmaker in source["selected_prices"]:
        books[bookmaker] = {
            "legs": [
                {
                    "outcome_id": outcome,
                    "price": source["selected_prices"][bookmaker][outcome],
                    "created_at": source["selected_quote_timestamps"][bookmaker][
                        outcome
                    ],
                    "quote_age_seconds": source["quote_ages_seconds"][bookmaker][
                        outcome
                    ],
                }
                for outcome in ("101", "102", "103")
            ]
        }
    retained = {
        "match_id": source["match_id"],
        "fixture_id": source["provider_fixture_id"],
        "kickoff": source["kickoff"],
        "model_code": source["model_code"],
        "model_version": source["model_version"],
        "evidence_profile": source["evidence_profile"],
        "raw_hash": source["raw_cache_hash"],
        "book_count": source["bookmaker_count"],
        "books": books,
    }
    retained["evidence_id"] = identity(retained)
    linked = {"evidence_id": retained["evidence_id"]}
    return source, linked, retained


def test_authoritative_price_crosscheck_accepts_exact_retained_evidence():
    source, linked, retained = authoritative_price_fixture()
    decision_runner.verify_authoritative_price(source, linked, retained)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row["selected_prices"]["pinnacle"].update({"101": 9.9}),
        lambda row: row["selected_quote_timestamps"]["pinnacle"].update(
            {"101": "2020-01-01T00:00:00+00:00"}
        ),
        lambda row: row["quote_ages_seconds"]["pinnacle"].update({"101": 9999}),
        lambda row: row.update(raw_cache_hash="f" * 64),
        lambda row: row.update(provider_fixture_id="different"),
        lambda row: row["selected_prices"].pop("bet365"),
        lambda row: row["selected_prices"]["pinnacle"].pop("103"),
    ],
)
def test_authoritative_price_crosscheck_rejects_materialized_tampering(mutation):
    source, linked, retained = authoritative_price_fixture()
    mutation(source)
    with pytest.raises(ValueError, match="FS018_AUTHORITATIVE_PRICE_MISMATCH"):
        decision_runner.verify_authoritative_price(source, linked, retained)


def test_authoritative_price_crosscheck_rejects_evidence_id_tampering():
    source, linked, retained = authoritative_price_fixture()
    linked["evidence_id"] = "f" * 64
    with pytest.raises(ValueError, match="FS018_AUTHORITATIVE_EVIDENCE_ID_MISMATCH"):
        decision_runner.verify_authoritative_price(source, linked, retained)


def test_decision_common_cohort_hash_is_deterministic_and_sensitive():
    rows = synthetic_frozen_snapshot()
    observed = decision_runner.decision_common_cohort_hash(rows)
    assert observed == decision_runner.decision_common_cohort_hash(list(reversed(rows)))
    changed = copy.deepcopy(rows)
    changed[0]["kickoff"] = (KICKOFF - timedelta(days=1)).isoformat()
    assert decision_runner.decision_common_cohort_hash(changed) != observed


def test_workspace_root_default_override_and_escape(tmp_path, settings):
    assert experiment_workspace_root() == (tmp_path / "tmp").resolve()
    alternate = tmp_path / "external-visible"
    valid = alternate / "FS-019_experiments/spec.json"
    assert local_decision_spec_path(valid, workspace_root=alternate) == valid.resolve()
    with pytest.raises(ValueError, match="FS-019_experiments"):
        local_decision_spec_path(
            tmp_path / "outside/spec.json", workspace_root=alternate
        )


def _probabilities(outcome, confidence):
    remainder = (1 - confidence) / 2
    return {
        "HOME": (confidence, remainder, remainder),
        "DRAW": (remainder, confidence, remainder),
        "AWAY": (remainder, remainder, confidence),
    }[outcome]


def synthetic_frozen_snapshot():
    profiles = (
        (0.65, {"HOME": 337, "DRAW": 0, "AWAY": 113}),
        (0.575, {"HOME": 135, "DRAW": 0, "AWAY": 65}),
        (0.525, {"HOME": 152, "DRAW": 0, "AWAY": 60}),
        (0.475, {"HOME": 199, "DRAW": 0, "AWAY": 80}),
        (0.425, {"HOME": 261, "DRAW": 2, "AWAY": 103}),
        (0.39, {"HOME": 211, "DRAW": 0, "AWAY": 167}),
        (0.34, {"HOME": 0, "DRAW": 21, "AWAY": 0}),
    )
    vectors = []
    for confidence, counts in profiles:
        for outcome, count in counts.items():
            vectors.extend([_probabilities(outcome, confidence)] * count)
    remaining = dict(decision_runner.COMPETITION_COUNTS)
    leagues = []
    while any(remaining.values()):
        for competition in decision_runner.COMPETITION_IDS:
            if remaining[competition]:
                leagues.append(competition)
                remaining[competition] -= 1
    rows = []
    for index, (probabilities, competition) in enumerate(zip(vectors, leagues), 1):
        kickoff = KICKOFF + timedelta(minutes=index)
        row = price_row(probabilities=probabilities)
        row.update(
            match_id=index,
            competition_id=competition,
            kickoff=kickoff.isoformat(),
            provider_fixture_id=f"fixture-{index}",
            fs018_evidence_id=f"{index:064x}",
            raw_cache_hash=f"{index + 1906:064x}",
        )
        for bookmaker in row["selected_quote_timestamps"]:
            for offset, outcome_id in enumerate(("101", "102", "103"), 31):
                row["selected_quote_timestamps"][bookmaker][outcome_id] = (
                    kickoff - timedelta(minutes=offset)
                ).isoformat()
                row["quote_ages_seconds"][bookmaker][outcome_id] = offset * 60
        rows.append(row)
    return sorted(
        rows,
        key=lambda row: (row["competition_id"], row["kickoff"], row["match_id"]),
    )


def test_full_synthetic_snapshot_has_exact_cohort_and_frozen_action_counts():
    rows = synthetic_frozen_snapshot()
    decision_runner._validate_snapshot(rows)
    assert len(rows) == 1906
    assert decision_runner.snapshot_hash(rows) == decision_runner.snapshot_hash(
        json.loads(canonical(rows))
    )
    replayed = replay_decisions(rows)
    assert validate_frozen_action_counts(replayed) == EXPECTED_ACTION_COUNTS
    replayed[-1]["action"] = "BET"
    with pytest.raises(ValueError, match="FROZEN_DECISION_ACTION_COUNTS_MISMATCH"):
        validate_frozen_action_counts(replayed)
    duplicate = copy.deepcopy(rows)
    duplicate[-1]["match_id"] = duplicate[0]["match_id"]
    with pytest.raises(ValueError, match="DECISION_COMMON_COUNT_MISMATCH"):
        decision_runner._validate_snapshot(duplicate)
    with pytest.raises(ValueError, match="DECISION_INPUT_ORDER_MISMATCH"):
        decision_runner._validate_snapshot(list(reversed(rows)))


def test_frozen_snapshot_is_self_contained_and_hash_verified(tmp_path):
    rows = synthetic_frozen_snapshot()
    content_hash = decision_runner.snapshot_hash(rows)
    spec = valid_spec(content_hash, decision_runner.decision_common_cohort_hash(rows))
    spec_path = tmp_path / "spec.json"
    spec.save(spec_path)
    snapshot_path = tmp_path / spec.data["snapshot"]["file"]
    snapshot_path.write_bytes(deterministic_gzip(rows))
    assert decision_runner.read_snapshot(spec, spec_path) == rows
    damaged = copy.deepcopy(rows)
    damaged[0]["p_home"] += 0.01
    snapshot_path.write_bytes(deterministic_gzip(damaged))
    with pytest.raises(ValueError, match="DECISION_INPUT_SNAPSHOT_HASH_MISMATCH"):
        decision_runner.read_snapshot(spec, spec_path)


def test_snapshot_builder_rejects_missing_manifest_evidence(tmp_path):
    source = {
        **price_row(),
        "NATURAL": True,
        "status": "PRODUCED",
    }
    source.pop("fs018_evidence_id")
    path = tmp_path / "per-match.jsonl.gz"
    with gzip.open(path, "wt") as stream:
        stream.write(canonical(source) + "\n")
    with pytest.raises(ValueError, match="MISSING_FS018_MARKET_EVIDENCE_ID"):
        decision_runner.build_snapshot_rows(path, [], {"leagues": {}})


def test_complete_synthetic_runner_is_offline_idempotent_and_resource_sane(tmp_path):
    rows = synthetic_frozen_snapshot()
    content_hash = decision_runner.snapshot_hash(rows)
    spec = valid_spec(content_hash, decision_runner.decision_common_cohort_hash(rows))
    workspace = tmp_path / "external-visible"
    spec_path = workspace / "FS-019_experiments/spec.json"
    spec.save(spec_path)
    (spec_path.parent / spec.data["snapshot"]["file"]).write_bytes(
        deterministic_gzip(rows)
    )
    first = decision_runner.run_decision_experiment(
        spec, spec_path, base=tmp_path, workspace_root=workspace
    )
    second = decision_runner.run_decision_experiment(
        spec, spec_path, base=tmp_path, workspace_root=workspace
    )
    assert first == second
    assert first["decision_row_count"] == 1906 * 6
    assert first["summary"]["action_counts"] == EXPECTED_ACTION_COUNTS
    assert len(first["summary"]["stability"]["deltas"]) == 12
    assert first["summary"]["bootstrap"]["replicates"] == 5000
    assert first["resources"]["decision_seconds"] < 60
    directory = workspace / "FS-019_experiments" / first["execution_id"]
    assert (directory / "decision-rows.jsonl.gz").is_file()
    assert sum(path.stat().st_size for path in directory.iterdir()) < 10 * 1024 * 1024
    assert (directory / "report.md").is_file()
    assert not (tmp_path / decision_artifacts.REPORT_REF).exists()
    record = decision_artifacts.promote_decision(
        first, spec, base=tmp_path, workspace_root=workspace
    )
    assert record["upstream_prediction"] == decision_runner.UPSTREAM
    assert (
        record["experiment"]["decision_common_cohort_hash"]
        == spec.data["decision_common_cohort_hash"]
    )
    assert record["selected_decision_stream"]["row_count"] == 1906
    stream_path = tmp_path / record["selected_decision_stream"]["path"]
    assert stream_path.stat().st_size < 500 * 1024
    with gzip.open(stream_path, "rt") as stream:
        selected_rows = [json.loads(line) for line in stream]
    assert len({row["match_id"] for row in selected_rows}) == 1906
    assert selected_rows[0]["historical_outcome"] in {"HOME", "DRAW", "AWAY"}
    assert "fixed_unit_reward" in selected_rows[0]["research"]
    descriptor = decision_artifacts.resolve_global_decision(base=tmp_path)
    assert descriptor.model_code == "MARKET_CONSENSUS"
    assert (
        descriptor.selected_decision_stream_semantic_hash
        == record["selected_decision_stream"]["semantic_sha256"]
    )

    stream_content = stream_path.read_bytes()
    damaged_stream = copy.deepcopy(selected_rows)
    damaged_stream[0]["research"]["fixed_unit_reward"] += 1
    stream_path.write_bytes(deterministic_gzip(damaged_stream))
    with pytest.raises(ValueError, match="SELECTED_DECISION_STREAM_GZIP_HASH_MISMATCH"):
        decision_artifacts.resolve_global_decision(base=tmp_path)
    stream_path.write_bytes(stream_content)

    decision_path = directory / "decision-rows.jsonl.gz"
    decision_content = decision_path.read_bytes()
    decision_path.unlink()
    with pytest.raises(ValueError, match="DECISION_ROWS_UNREADABLE"):
        decision_runner.run_decision_experiment(
            spec, spec_path, base=tmp_path, workspace_root=workspace
        )
    decision_path.write_bytes(deterministic_gzip(selected_rows))
    with pytest.raises(ValueError, match="DECISION_ROWS_HASH_MISMATCH"):
        decision_runner.run_decision_experiment(
            spec, spec_path, base=tmp_path, workspace_root=workspace
        )
    decision_path.write_bytes(decision_content)


def test_selected_stream_preserves_no_bet_semantics_and_provenance():
    spec = valid_spec()
    run, rows = promotion_run(spec)
    run["summary"]["selected"] = "SELECTIVE_CONFIDENCE_0.60"
    stream = decision_artifacts.selected_stream_rows(run, rows)
    assert stream[0]["decision"]["action"] == "NO_BET"
    assert stream[0]["decision"]["policy_config"] == {"threshold": 0.6}
    assert stream[0]["price"]["selected_raw_decimal"] is None
    assert stream[0]["price"]["representative_bookmaker"] is None
    assert stream[0]["price"]["provider_fixture_id"] == "fixture-1"
    assert stream[0]["research"]["fixed_unit_reward"] == 0


def test_report_contains_complete_a12_diagnostics():
    spec = valid_spec()
    run, _ = promotion_run(spec)
    report = decision_artifacts.human_report(run)
    for label in (
        "Natural/common N",
        "BET/rate",
        "NO_BET/rate",
        "NO_BET reasons",
        "H/D/A",
        "P&L",
        "yield",
        "hit",
        "odds",
        "books",
        "co-best",
        "quote-age",
        "monthly",
        "longest losing bet streak",
        "Pooled PPO diagnostic",
        "Required-league PPO",
    ):
        assert label in report
