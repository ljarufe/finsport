"""Immutable promotion: references research evidence, changes no routing."""

import subprocess
from pathlib import Path

from django.conf import settings

from .analysis import PAIRED_COMMON_SELECTION_POLICY
from .runner import verify_run
from .spec import TOURNAMENTS, ExperimentSpec
from .storage import atomic_json, atomic_text, canonical, identity, lock, read_json

REPORT_REF = "docs/research/FS-018_global_prediction_baseline_report.md"
PROMOTION_REF = "docs/research/FS-018_global_prediction_v1.json"
RESEARCH_REF = "docs/research/FS-018_experiment_lab_global_prediction_research.md"


def human_report(run, *, local=False):
    summary = run["summary"]
    lines = [
        (
            "# FS-018 Local Experiment Run"
            if local
            else "# FS-018 Global Prediction Baseline"
        ),
        "",
        f"Run: `{run['run_id']}`",
        f"Spec: `{run['spec_id']}`",
        f"Cutoff: {run['spec']['data_cutoff']}",
        f"Disposition: **{summary['disposition']}**",
        f"Selected: `{summary['selected']}`",
        f"Selection policy: `{summary.get('selection_policy')}`",
        f"Selection basis: `{summary.get('selection_basis')}`",
        "",
        "| Candidate | Global eligible | COMMON N | NATURAL N | Coverage | Equal-league log-loss |",
        "|---|---|---|---|---|---|",
    ]
    for code, row in summary["candidates"].items():
        lines.append(
            f"| {code} | {row['global_eligible']} | {row['COMMON']['sample_count']} | {row['NATURAL']['sample_count']} | {row['coverage']:.4f} | {row['primary_score']} |"
        )
    lines += [
        "",
        "Per-league COMMON metrics (partial challengers use their available intersection):",
        "",
        "| Competition | Candidate | N | Log-loss | Brier | RPS | Accuracy |",
        "|---|---|---|---|---|---|---|",
    ]
    for code, row in summary["candidates"].items():
        for league, cohorts in row["per_league"].items():
            m = cohorts["COMMON"]
            lines.append(
                f"| {league} | {code} | {m['sample_count']} | {m.get('log_loss')} | {m.get('multiclass_brier')} | {m.get('rps')} | {m.get('accuracy')} |"
            )
    lines += [
        "",
        "Paired bootstrap: 5,000 Competition-stratified Lima-week replicates, seed 18092026.",
        "",
        "| A minus B log-loss | 95% lower | 95% upper |",
        "|---|---|---|",
    ]
    for pair, interval in (
        summary.get("uncertainty", {}).get("paired_intervals", {}).items()
    ):
        lines.append(
            f"| {pair.replace('|', ' minus ')} | {interval['lower']} | {interval['upper']} |"
        )
    lines += [
        "",
        "All per-league/temporal scores, calibration, exclusions and paired uncertainty:",
        "",
        "```json",
        canonical(summary),
        "```",
        "",
        "Acquisition outcomes:",
        "",
        "```json",
        canonical(
            {
                k: {
                    field: v.get(field)
                    for field in ("status", "counts", "reason", "discovered_count")
                }
                for k, v in run["acquisition"]["leagues"].items()
            }
        ),
        "```",
        "",
        f"Physical acquisition audit: {canonical(run['acquisition'].get('audit', {}))}",
        "",
        f"Resources: {canonical(run['resources'])}",
        f"Warnings: {canonical(run.get('warnings', []))}",
        "",
        "Read-only historical research; no operational routing change.",
        "Manual live UAT evidence must be reviewed separately from automated scores.",
        "",
    ]
    return "\n".join(lines)


def promotion_record(run):
    spec = ExperimentSpec(canonical(run["spec"]))
    verify_run(run, spec)
    summary, data, acquisition = run["summary"], spec.data, run["acquisition"]
    selected = summary["selected"]
    if data.get("acquisition", {}).get("mode") == "RECOVERY_V1" and (
        run.get("analysis_mode") != "FRESH_CONFIRMATION_V2"
        or summary.get("selection_policy") != PAIRED_COMMON_SELECTION_POLICY
    ):
        raise ValueError("RECOVERY_PROMOTION_REQUIRES_CONFIRMATION")
    if (
        data["competition_ids"] != sorted(TOURNAMENTS)
        or acquisition["pilot"]
        or acquisition["status"] not in {"COMPLETE", "PARTIAL"}
        or set(acquisition["leagues"]) != {str(i) for i in TOURNAMENTS}
        or not selected
        or not summary["candidates"][selected]["global_eligible"]
        or summary["disposition"] not in {"CLEAR_SUPERIORITY", "NO_CLEAR_SUPERIORITY"}
    ):
        raise ValueError("FULL_VALID_EXPERIMENT_REQUIRED_FOR_PROMOTION")
    return {
        "baseline": "GLOBAL_PREDICTION_V1",
        "model_code": selected,
        "model_version": data["models"][selected],
        "config_identity": identity(effective_baseline_config(data, selected)),
        "effective_config": effective_baseline_config(data, selected),
        "configs": data["configs"],
        "experiment_spec_id": spec.id,
        "full_run_id": run["run_id"],
        "data_cutoff": data["data_cutoff"],
        "manifest_hash": summary["manifest_hash"],
        "cohort_hash": summary["cohort_hash"],
        "selection_disposition": summary["disposition"],
        "selection_policy": summary.get("selection_policy"),
        "selection_basis": summary.get("selection_basis"),
        "research_ref": RESEARCH_REF,
        "report_ref": REPORT_REF,
        "run_ref": f"tmp/FS-018_experiments/{run.get('analysis_id', acquisition['run_id'])}/run.json",
        "evidence_profile": data["evidence_profile"],
        "evidence_class": data["evidence_class"],
    }


def effective_baseline_config(data, selected):
    """Identify the selected model's effective global configuration only."""
    result = {"model_code": selected, "model_version": data["models"][selected]}
    if selected == "MARKET_CONSENSUS":
        result.update(
            evidence_profile=data["evidence_profile"],
            bookmakers=data["bookmakers"],
            minimum_books=data["minimum_books"],
            cutoff=data["t30"],
            de_vig=data["de_vig_method"],
            consensus=data["consensus_method"],
        )
    else:
        result["per_competition"] = {
            key: {
                "executable": config["executable"][selected],
                "selected_identity": identity(config["selected"][selected.lower()]),
            }
            for key, config in sorted(data["configs"].items())
        }
    return result


def promote(
    run, *, base=None, replace_provisional=False, expected_previous_run_id=None
):
    record = promotion_record(run)
    base = Path(base or settings.BASE_DIR)
    path, report_path = base / PROMOTION_REF, base / REPORT_REF
    report = human_report(run)
    with lock(base / "tmp/FS-018_experiments/promotion.lock"):
        if path.exists() and read_json(path) == record:
            return record
        conflicting = path.exists() or (
            report_path.exists() and report_path.read_text() != report
        )
        if conflicting:
            if not replace_provisional or not expected_previous_run_id:
                raise ValueError("GLOBAL_PREDICTION_V1_ALREADY_FROZEN")
            if (
                run.get("analysis_mode") != "FRESH_CONFIRMATION_V2"
                or run["spec"].get("acquisition", {}).get("mode") != "RECOVERY_V1"
            ):
                raise ValueError(
                    "PROVISIONAL_REPLACEMENT_REQUIRES_RECOVERY_CONFIRMATION"
                )
            if not path.exists() or not report_path.exists():
                raise ValueError("PROVISIONAL_PAIR_INCOMPLETE")
            old = read_json(path)
            if old.get("full_run_id") != expected_previous_run_id:
                raise ValueError("PROVISIONAL_RUN_ID_MISMATCH")
            for relative in (PROMOTION_REF, REPORT_REF):
                tracked = subprocess.run(
                    ["git", "ls-files", "--error-unmatch", "--", relative],
                    cwd=base,
                    capture_output=True,
                    check=False,
                )
                if tracked.returncode == 0:
                    raise ValueError("REFUSING_TO_REPLACE_TRACKED_PROMOTION")
                if tracked.returncode != 1:
                    raise ValueError("PROMOTION_TRACKING_CHECK_FAILED")
            backup = (
                base
                / "tmp/FS-018_experiments/provisional-backups"
                / expected_previous_run_id
            )
            backup_record_path = backup / "record.json"
            backup_report_path = backup / "report.md"
            current_report = report_path.read_text()
            if backup_record_path.exists():
                if read_json(backup_record_path) != old:
                    raise ValueError("PROVISIONAL_BACKUP_RECORD_MISMATCH")
            else:
                atomic_json(backup_record_path, old)
            if backup_report_path.exists():
                backup_report = backup_report_path.read_text()
                if current_report not in {backup_report, report}:
                    raise ValueError("PROVISIONAL_BACKUP_REPORT_MISMATCH")
            else:
                if current_report == report:
                    raise ValueError("PROVISIONAL_BACKUP_INCOMPLETE")
                atomic_text(backup_report_path, current_report)
            if current_report != report:
                atomic_text(report_path, report)
            atomic_json(path, record)
            return record
        report_path.parent.mkdir(parents=True, exist_ok=True)
        # Report first: interrupted promotion resumes with the identical report.
        if not report_path.exists():
            atomic_text(report_path, report)
        atomic_json(path, record)
    return record
