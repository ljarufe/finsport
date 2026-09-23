"""Manual FS-020 durable publication; never consulted by automatic routing."""

import hashlib
from decimal import Decimal
from pathlib import Path

from django.conf import settings

from .capital_runner import (
    CANDIDATES,
    RESEARCH_REF,
    CapitalSpec,
    capital_root,
    execution_context,
    verify_capital_run,
    write_json_once,
)
from .storage import canonical, identity, immutable_bytes, lock, require_dev

AUTHORITY_REF = "docs/research/FS-020_global_capital_v1.json"
REPORT_REF = "docs/research/FS-020_global_capital_report.md"
EVIDENCE_REF = "docs/research/FS-020_capital_baseline_evidence"
PUBLICATION_SELECTION_POLICY = "FS020_MAXIMIN_LAG_RETURN_V1"
PUBLICATION_LAGS = ("120", "130", "150")


def publication_selection(run):
    """Apply the approved economic rule without changing scientific inference."""
    if set(run["lags"]) != set(PUBLICATION_LAGS):
        raise ValueError("CAPITAL_PUBLICATION_LAGS_INCOMPLETE")
    canonical_order = {
        candidate.code: index for index, candidate in enumerate(CANDIDATES)
    }
    expected = set(canonical_order)
    ranking = []
    for code, order in canonical_order.items():
        metrics = []
        for lag in PUBLICATION_LAGS:
            observed = run["lags"][lag].get("observed")
            if not isinstance(observed, dict) or set(observed) != expected:
                raise ValueError("CAPITAL_PUBLICATION_PATHS_INCOMPLETE")
            metrics.append(observed[code])
        eligible = all(
            metric.get("structurally_complete") is True
            and metric.get("hard_risk") == "PASS"
            for metric in metrics
        )
        returns = {
            lag: Decimal(str(metric["total_return"]))
            for lag, metric in zip(PUBLICATION_LAGS, metrics, strict=True)
        }
        drawdowns = {
            lag: Decimal(str(metric["maximum_drawdown"]))
            for lag, metric in zip(PUBLICATION_LAGS, metrics, strict=True)
        }
        if not all(
            value.is_finite() for value in (*returns.values(), *drawdowns.values())
        ):
            raise ValueError("CAPITAL_PUBLICATION_METRIC_INVALID")
        ranking.append(
            dict(
                candidate=code,
                eligible=eligible,
                worst_lag_return=str(min(returns.values())),
                return_t150=str(returns["150"]),
                worst_maximum_drawdown=str(max(drawdowns.values())),
                canonical_order=order,
            )
        )
    eligible = [row for row in ranking if row["eligible"]]
    if not eligible:
        raise ValueError("CAPITAL_PUBLICATION_NO_ELIGIBLE_CANDIDATE")
    eligible.sort(
        key=lambda row: (
            -Decimal(row["worst_lag_return"]),
            -Decimal(row["return_t150"]),
            Decimal(row["worst_maximum_drawdown"]),
            row["canonical_order"],
        )
    )
    ranking.sort(
        key=lambda row: (
            not row["eligible"],
            -Decimal(row["worst_lag_return"]),
            -Decimal(row["return_t150"]),
            Decimal(row["worst_maximum_drawdown"]),
            row["canonical_order"],
        )
    )
    return dict(
        policy=PUBLICATION_SELECTION_POLICY,
        required_lags=[int(lag) for lag in PUBLICATION_LAGS],
        eligibility="COMPLETE_PATH_AND_HARD_RISK_PASS_AT_ALL_REQUIRED_LAGS",
        tie_breaks=[
            "RETURN_T150_DESC",
            "WORST_MAXIMUM_DRAWDOWN_ASC",
            "CANONICAL_ORDER_ASC",
        ],
        selected=eligible[0]["candidate"],
        ranking=ranking,
    )


def human_report(run, selection=None):
    selection = selection or publication_selection(run)
    selected = next(c.data() for c in CANDIDATES if c.code == selection["selected"])
    lines = [
        "# FS-020 Global Capital Baseline",
        "",
        f"Run: `{run['run_id']}`",
        f"Scientific disposition: {run['summary']['disposition']}",
        "Publication promotion: PROMOTE",
        f"Selected: {selection['selected']}",
        f"Selected configuration: `{canonical(selected['config'])}`; max lanes: {selected['max_lanes']}",
        f"Settlement stability: {run['summary']['settlement_time_stability']}",
        f"Selection policy: {selection['policy']}",
        "The publication preserves the scientific disposition UNSTABLE and does not claim scientific superiority.",
        "",
        "## Economic publication ranking",
        "",
        "| Capital | Eligible | Worst-lag return | T+150 return | Worst max drawdown | Canonical order |",
        "|---|---|---:|---:|---:|---:|",
        *[
            f"| {row['candidate']} | {row['eligible']} | {row['worst_lag_return']} | {row['return_t150']} | {row['worst_maximum_drawdown']} | {row['canonical_order']} |"
            for row in selection["ranking"]
        ],
        "",
    ]
    for lag, result in run["lags"].items():
        lines += [
            f"## Synthetic settlement +{lag}m",
            "",
            f"Disposition: {result['disposition']}; promotion: {result['promotion']}",
            f"Fallback: {result.get('fallback', 'NOT_APPLICABLE')}",
            "",
        ]
        if "error" in result:
            lines += [f"Unestimable evidence: {result['error']}", ""]
            continue
        lines += [
            "| Capital | Total return | Max drawdown | Placements | Risk |",
            "|---|---:|---:|---:|---|",
        ]
        # Stable report bytes for in-memory runs and canonical run.json reloads.
        for code, metric in sorted(result["observed"].items()):
            lines.append(
                f"| {code} | {metric['total_return']} | {metric['maximum_drawdown']} | {metric['placements']} | {metric['hard_risk']} |"
            )
        lines += [
            "",
            f"Stability: {result['stability']['status']}",
            f"Strict top versus all (1/2/4w): {canonical(result['strict_top_vs_all'])}",
            f"Capacity, state, risk diagnostics: {canonical({c: m for c, m in result['observed'].items()})}",
            f"Stability slices: {canonical(result['stability']['slices'])}",
            f"Simultaneous inference: {canonical(result['families'])}",
            "",
        ]
    lines += [
        "Historical local research only. Synthetic settlement times; no prospective/live profitability claim.",
        "Opportunity cost: UNAVAILABLE_CURRENCY_NOT_BOUND. No operational routing change.",
        "Provider calls: 0. Manual UAT is separate evidence.",
        "",
    ]
    return "\n".join(lines)


def publish_capital(run, *, base=None, workspace_root=None):
    require_dev()
    base = Path(base or settings.BASE_DIR)
    spec = CapitalSpec(canonical(run["spec"]))
    # Revalidate the frozen inputs and research binding. Publisher-only changes
    # intentionally do not create or rerun an economic execution.
    execution_context(spec, base=base, workspace_root=workspace_root)
    directory = capital_root(workspace_root) / run["execution_id"]
    verify_capital_run(run, spec, directory=directory)
    selection = publication_selection(run)
    selected = next(
        (c.data() for c in CANDIDATES if c.code == selection["selected"]), None
    )
    if selected is None:
        raise ValueError("UNKNOWN_CAPITAL_PROMOTION")
    published_summary = dict(
        run["summary"], promotion="PROMOTE", selected=selection["selected"]
    )
    evidence = f"{EVIDENCE_REF}/{run['run_id'][:16]}/run.json"
    report = human_report(run, selection)
    record = dict(
        schema="FS020_GLOBAL_CAPITAL_AUTHORITY_V1",
        baseline="GLOBAL_CAPITAL_V1",
        **published_summary,
        selected_capital=selected,
        publication_selection=selection,
        scientific_run_summary=run["summary"],
        fallback={
            k: v.get("fallback", "NOT_APPLICABLE") for k, v in run["lags"].items()
        },
        risk_gate={k: v.get("hard_risk", {}) for k, v in run["lags"].items()},
        upstream=spec.data["input"],
        candidate_matrix=spec.data["candidates"],
        candidate_matrix_id=spec.data["candidate_matrix_id"],
        research_ref=RESEARCH_REF,
        research_sha256=spec.data["research_sha256"],
        spec_id=spec.id,
        execution_id=run["execution_id"],
        execution_runtime_id=run["execution_runtime_id"],
        execution_runtime=run["execution_runtime"],
        analysis_id=run["analysis_id"],
        run_id=run["run_id"],
        lags=run["lags"],
        bootstrap=spec.data["bootstrap"],
        rng_manifest=spec.data["rng_manifest"],
        evidence_ref=evidence,
        evidence_hash=identity(run),
        artifacts=run["artifacts"],
        report_ref=REPORT_REF,
        report_sha256=hashlib.sha256(report.encode()).hexdigest(),
        operational_activation=False,
    )
    with lock(capital_root(workspace_root) / "publication.lock"):
        # Verify every existing member before writing any member. Report first,
        # authority last: interrupted identical publication is safely resumable.
        files = {
            base / evidence: (canonical(run) + "\n").encode(),
            base / REPORT_REF: report.encode(),
            base / AUTHORITY_REF: (canonical(record) + "\n").encode(),
        }
        for path, content in files.items():
            if path.exists() and path.read_bytes() != content:
                raise ValueError("GLOBAL_CAPITAL_V1_ALREADY_FROZEN")
        write_json_once(base / evidence, run)
        immutable_bytes(
            base / REPORT_REF, report.encode(), conflict="CAPITAL_REPORT_CONFLICT"
        )
        write_json_once(base / AUTHORITY_REF, record)
    return record
