"""Audit and optionally remove ONLY verified FS-021 data copies in docs/research.

Run after native --analyze-existing, --publish-existing and
--publish-economic-existing succeed. Default is DRY RUN. Never removes
maintainer research, tracked files, or any source without an authenticated
byte/JSON-semantic equivalent in the original durable execution.
"""

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

ORIGINAL = (
    "FS-021_global_strategy_v1.json",
    "FS-021_candidate_matrix.json",
    "FS-021_input_manifest.json",
    "FS-021_retention_manifest.json",
    "FS-021_spec.json",
    "FS-021_summary_231.json",
    "FS-021_global_strategy_report.md",
)
ECONOMIC = (
    "FS-021_economic_selector_v1.json",
    "FS-021_economic_231.csv",
    "FS-021_economic_top20.csv",
    "FS-021_observed_economic_metrics.csv",
    "FS-021_economic_report.md",
    "FS-021_daily_equity_693.json",
    "FS-021_economic_retention.tsv",
    "FS-021_economic_manifest_v1.json",
)
DIAGNOSTICS = (
    "FS-021_economic_diagnostics_v1.json",
    "FS-021_economic_diagnostics_manifest_v1.json",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution", required=True, type=Path)
    parser.add_argument("--repo", default=Path.cwd(), type=Path)
    parser.add_argument(
        "--apply", action="store_true", help="Delete verified UNTRACKED duplicates"
    )
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = args.execution.resolve()
    research = repo / "docs/research"
    if not root.is_dir() or not (root / "run.json").is_file():
        parser.error("Original execution/root not found. Nothing deleted.")
    # All three native publication indexes MUST have been generated successfully.
    indexes = repo / "docs/experiments/FS-021" / root.name
    needed = ("original_v1.json", "economic_v1_1.json", "diagnostics_v1_1.json")
    for name in needed:
        if not (indexes / name).is_file():
            parser.error(
                f"Missing native compact index {indexes / name}. Nothing deleted."
            )
    sources = {}
    for name in ORIGINAL:
        sources[name] = root / "original_publication_v1" / name
    # Historical v1 copies remain immutable. v1.1 corrects reporting separately.
    for name in ECONOMIC:
        sources[name] = root / "economic_selection_v1" / name
    for name in DIAGNOSTICS:
        sources[name] = root / "economic_diagnostics_v1" / name

    # Verify each present source against its own original manifest when possible.
    original_index = json.loads((indexes / "original_v1.json").read_text())
    original = root / original_index["relative_path"]
    if hashlib.sha256(original.read_bytes()).hexdigest() != original_index["sha256"]:
        parser.error("Original index hash mismatch. Nothing deleted.")
    for kind, idx, directory in (
        ("economic", "economic_v1_1.json", "economic_selection_v1_1"),
        ("diagnostics", "diagnostics_v1_1.json", "economic_diagnostics_v1_1"),
    ):
        entry = json.loads((indexes / idx).read_text())
        path = root / entry["relative_path"]
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != entry["manifest_sha256"]
        ):
            parser.error(f"{kind} new publication hash mismatch. Nothing deleted.")

    # Validate the native products, not just the presence of their compact locators.
    economic_manifest = json.loads(
        (root / "economic_selection_v1_1/FS-021_economic_manifest_v1.json").read_text()
    )
    for name, meta in economic_manifest["outputs"].items():
        path = root / "economic_selection_v1_1" / name
        if (
            not path.is_file()
            or path.stat().st_size != meta["bytes"]
            or (hashlib.sha256(path.read_bytes()).hexdigest() != meta["sha256"])
        ):
            parser.error(f"New economic output mismatch: {name}. Nothing deleted.")
    selected = json.loads(
        (root / "economic_selection_v1_1/FS-021_economic_selector_v1.json").read_text()
    )
    original_run = json.loads((root / "run.json").read_text())
    if (
        selected["original_practical_winner"]
        != original_run["practical_selection"]["selected"]["integrated_index"]
        or selected["scientific_disposition"]
        != original_run["scientific_evidence"]["disposition"]
        or selected["source_hashes"]["run"]
        != hashlib.sha256((root / "run.json").read_bytes()).hexdigest()
        or selected["activation"].get("real_betting") is not False
    ):
        parser.error("Original result identity/activation changed. Nothing deleted.")
    with (root / "economic_selection_v1_1/FS-021_economic_top20.csv").open(
        newline=""
    ) as source:
        first = next(csv.DictReader(source), None)
    if not first or int(first["integrated_index"]) != selected["winner"]:
        parser.error("New top20 does not start with selected winner. Nothing deleted.")
    for folder in ("economic_selection_v1", "economic_selection_v1_1"):
        legacy_manifest = root / folder / "FS-021_economic_manifest_v1.json"
        if legacy_manifest.exists():
            for name, meta in json.loads(legacy_manifest.read_text())[
                "outputs"
            ].items():
                file = root / folder / name
                if (
                    not file.is_file()
                    or file.stat().st_size != meta["bytes"]
                    or (hashlib.sha256(file.read_bytes()).hexdigest() != meta["sha256"])
                ):
                    parser.error(f"Economic manifest mismatch: {folder}/{name}.")
    for folder in ("economic_diagnostics_v1", "economic_diagnostics_v1_1"):
        old_manifest = root / folder / "FS-021_economic_diagnostics_manifest_v1.json"
        if old_manifest.exists():
            meta = json.loads(old_manifest.read_text())
            output = root / folder / "FS-021_economic_diagnostics_v1.json"
            if (
                not output.is_file()
                or output.stat().st_size != meta["output_bytes"]
                or (
                    hashlib.sha256(output.read_bytes()).hexdigest()
                    != meta["output_sha256"]
                )
            ):
                parser.error(f"Diagnostics output mismatch: {folder}.")

    checked = []
    failures = []
    for name, source in sources.items():
        dest = research / name
        if not dest.exists():
            continue
        if (
            dest.is_symlink()
            or source.is_symlink()
            or not dest.is_file()
            or not source.is_file()
        ):
            failures.append(f"UNSAFE_OR_MISSING: {name}")
            continue
        tracked = (
            subprocess.run(
                [
                    "git",
                    "ls-files",
                    "--error-unmatch",
                    "--",
                    str(dest.relative_to(repo)),
                ],
                cwd=repo,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            ).returncode
            == 0
        )
        if tracked:
            failures.append(f"TRACKED_REFUSE_DELETE: {name}")
            continue
        old, new = dest.read_bytes(), source.read_bytes()
        equivalent = old == new
        if not equivalent and dest.suffix == ".json":
            try:
                equivalent = json.loads(old) == json.loads(new)
            except (ValueError, UnicodeDecodeError):
                pass
        if not equivalent and name == "FS-021_retention_manifest.json":
            try:
                portable = json.loads(old)
                durable = json.loads(new)

                portable_root = portable.pop("durable_root", None)
                durable_root = durable.pop("durable_root", None)

                equivalent = (
                    portable == durable
                    and portable_root == f"/evidence/{root.name}"
                    and durable_root == str(root)
                )
            except (ValueError, UnicodeDecodeError):
                equivalent = False
        if not equivalent:
            failures.append(f"COPY_DIFFERS_KEEP: {name}")
        else:
            checked.append((dest, hashlib.sha256(old).hexdigest()))
    # Never partially prune when any expected source differs.
    for issue in failures:
        print("HOLD", issue)
    for dest, digest in checked:
        print(
            "DELETE" if args.apply and not failures else "VERIFIED_KEEP", dest, digest
        )
    if failures:
        print(f"STOP: {len(failures)} issue(s). No deletions performed.")
        return 2
    if args.apply:
        for dest, digest in checked:
            if hashlib.sha256(dest.read_bytes()).hexdigest() != digest:
                print(f"STOP: changed since verification: {dest}")
                return 2
        for dest, _ in checked:
            dest.unlink()
        print(
            f"Removed {len(checked)} verified, untracked duplicates. Research .md preserved."
        )
    else:
        print(f"DRY RUN: {len(checked)} verified duplicate(s); use --apply to remove.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
