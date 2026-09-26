"""Manual offline FS-021 lifecycle; economics require validated technical gates."""

import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from football.experiments.capital_runner import write_json_once
from football.experiments.economic_diagnostics import (
    analyze_diagnostics_existing,
    publish_diagnostics_existing,
)
from football.experiments.economic_report import (
    analyze_existing,
    publish_economic_existing,
)
from football.experiments.integrated_artifacts import publish_existing
from football.experiments.integrated_conformance import compare_reference
from football.experiments.integrated_inputs import (
    freeze_spec,
    require,
    resolve_inputs,
)
from football.experiments.integrated_runner import (
    Progress,
    ResourcePause,
    bootstrap,
    execution_binding,
    finish,
    json_artifact,
    observe,
    stability,
    store_artifact,
    validate_execution,
)
from football.experiments.storage import (
    atomic_json,
    canonical,
    identity,
    lock,
    read_json,
    require_dev,
)


class Command(BaseCommand):
    help = "FS-021: validate, freeze, technical gates, observed, bootstrap, resume, status or publish an existing execution."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        for name in (
            "validate-inputs",
            "freeze",
            "technical",
            "observed",
            "bootstrap",
            "resume",
            "status",
            "publish-existing",
            "analyze-existing",
            "publish-economic-existing",
        ):
            mode.add_argument("--" + name, action="store_true")
        parser.add_argument("--pack", default="tmp/E2_phase3_fs019_binding_pack")
        parser.add_argument("--per-match")
        parser.add_argument("--reference")
        parser.add_argument("--root", required=True)
        parser.add_argument("--spec")
        parser.add_argument("--execution-id")
        parser.add_argument("--workers", type=int, default=4)
        parser.add_argument("--stage", choices=("observed", "bootstrap"))

    def handle(self, *args, **options):
        try:
            require_dev()
            self.execute_mode(options)
        except (
            ValueError,
            OSError,
            KeyError,
            TypeError,
            ArithmeticError,
            subprocess.SubprocessError,
        ) as error:
            raise CommandError(str(error)) from None

    def execute_mode(self, options):
        base = Path(settings.BASE_DIR)
        root = Path(options["root"]).resolve()
        per_match = options["per_match"]
        if not per_match and (options["validate_inputs"] or options["freeze"]):
            matches = list(
                (base / "tmp/FS-021_01_fs018_restore").rglob("per_match.jsonl.gz")
            )
            require(len(matches) == 1, "EXPLICIT_PER_MATCH_PATH_REQUIRED")
            per_match = matches[0]
        if options["validate_inputs"] or options["freeze"]:
            _, binding = resolve_inputs(base, options["pack"], per_match)
            if options["validate_inputs"]:
                path = root / "input-validation.json"
                atomic_json(path, binding)
                self.stdout.write(
                    canonical(
                        dict(
                            status=binding["status"],
                            counts=binding["counts"],
                            evidence=str(path),
                        )
                    )
                )
                return
            require(bool(options["spec"]), "SPEC_PATH_REQUIRED")
            spec = freeze_spec(base, binding, options["spec"])
            execution_id = identity(execution_binding(spec))
            directory = root / execution_id
            write_json_once(directory / "spec.json", spec)
            with lock(directory / "prepare.lock"):
                # Retain original full rows (including NO_BET and future suffix) once.
                for name in binding["files"]:
                    store_artifact(
                        directory,
                        "inputs/" + name,
                        (Path(options["pack"]) / name).read_bytes(),
                        execution_binding(spec),
                    )
                store_artifact(
                    directory,
                    "inputs/per_match.jsonl.gz",
                    Path(per_match).read_bytes(),
                    execution_binding(spec),
                )
                sources = {
                    "pack": str(Path(options["pack"]).resolve()),
                    "per_match": str(Path(per_match).resolve()),
                    "restore_pack": str(directory / "inputs"),
                    "restore_per_match": str(directory / "inputs/per_match.jsonl.gz"),
                    "status": "PRESERVE_ACTIVE",
                }
                write_json_once(directory / "restore.json", sources)
            self.stdout.write(
                canonical(
                    dict(
                        status="FROZEN",
                        execution_id=execution_id,
                        spec_sha=identity(spec),
                        directory=str(directory),
                    )
                )
            )
            return
        execution_id = options["execution_id"]
        require(
            isinstance(execution_id, str)
            and len(execution_id) == 64
            and all(c in "0123456789abcdef" for c in execution_id),
            "EXPLICIT_EXECUTION_ID_REQUIRED",
        )
        directory = root / execution_id
        spec = read_json(directory / "spec.json")
        require(
            identity(execution_binding(spec)) == execution_id, "EXECUTION_ID_MISMATCH"
        )
        if options["status"]:
            self.stdout.write(
                canonical(
                    {
                        name: (
                            read_json(directory / name)
                            if (directory / name).exists()
                            else None
                        )
                        for name in (
                            "worker.json",
                            "heartbeat.json",
                            "gates.json",
                            "economic_analysis_status.json",
                            "supervisor.json",
                            "alarm.json",
                            "ack.json",
                        )
                    }
                )
            )
            return
        # Prefer retained originals for recovery; never drop a missing candidate.
        pack = directory / "inputs"
        retained = pack / "per_match.jsonl.gz"
        if options["technical"]:
            _, binding = resolve_inputs(base, pack, retained)
            require(binding == spec["input"], "FROZEN_INPUT_CHANGED")
            require(bool(options["reference"]), "AUTHENTICATED_V2R_REFERENCE_REQUIRED")
            reference = compare_reference(options["reference"], base)
            json_artifact(
                directory, "technical/v2r.json", reference, execution_binding(spec)
            )
            gates = dict(
                binding=execution_binding(spec),
                INPUT_AND_ARTIFACT_INTEGRITY="PASS",
                SEMANTIC_CONFORMANCE="NOT_RUN",
                RUNNER_EQUIVALENCE="NOT_RUN",
            )
            for gate, files, expression in [
                (
                    "SEMANTIC_CONFORMANCE",
                    [
                        "football/tests/test_fs020_capital.py",
                        "football/tests/test_fs021_integrated.py",
                    ],
                    "not d12",
                ),
                (
                    "RUNNER_EQUIVALENCE",
                    ["football/tests/test_fs021_integrated.py"],
                    (
                        "d10 or d11 or d12 or atomic_readback "
                        "or worker_checks_resource_pause"
                    ),
                ),
            ]:
                output = directory / "technical" / (gate + ".txt")
                junit = directory / "technical" / (gate + ".xml")
                with output.open("w") as log:
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "pytest",
                            "-q",
                            "-o",
                            "cache_dir=/tmp/finsport-pytest-cache",
                            *files,
                            "-k",
                            expression,
                            f"--junitxml={junit}",
                        ],
                        cwd=base,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )
                gates[gate] = "PASS" if result.returncode == 0 else "FAIL"
                gates[gate + "_evidence"] = dict(
                    log=str(output.relative_to(directory)),
                    exit_code=result.returncode,
                )
                atomic_json(directory / "gates.json", gates)
                require(result.returncode == 0, gate + "_FAILED_SEE_" + str(output))
            self.stdout.write(canonical(gates))
            return
        streams, spec = validate_execution(directory, base, pack, retained)

        def analyze_and_record():
            try:
                economic = analyze_existing(directory, spec, streams)
                analyze_diagnostics_existing(directory, spec, streams, economic)
            except Exception as error:
                atomic_json(
                    directory / "economic_analysis_status.json",
                    dict(status="STOP_TECHNICAL", reason=str(error)),
                )
                raise
            atomic_json(
                directory / "economic_analysis_status.json",
                dict(
                    status="COMPLETE",
                    winner=economic["winner"],
                    method_version=economic["method_version"],
                    upstream_retention_index=(
                        "PRESENT"
                        if (directory / "RETENTION_INDEX.tsv").is_file()
                        else "MISSING_REVIEW"
                    ),
                ),
            )
            return economic

        if options["analyze_existing"]:
            result = analyze_and_record()
            self.stdout.write(
                canonical(
                    dict(
                        status="ECONOMIC_ANALYSIS_COMPLETE",
                        winner=result["winner"],
                        method_version=result["method_version"],
                    )
                )
            )
            return
        if options["publish_economic_existing"]:
            result = analyze_and_record()
            manifest = publish_economic_existing(directory, base)
            publish_diagnostics_existing(directory, base)
            self.stdout.write(
                canonical(
                    dict(
                        status="ECONOMIC_PUBLICATION_COMPLETE",
                        winner=result["winner"],
                        manifest=manifest["schema"],
                    )
                )
            )
            return
        if options["publish_existing"]:
            authority = publish_existing(directory, spec, streams, base)
            self.stdout.write(
                canonical(
                    dict(
                        status="PUBLISHED_EXISTING",
                        execution_id=authority["execution_id"],
                    )
                )
            )
            return
        stage = (
            "observed"
            if options["observed"]
            else "bootstrap" if options["bootstrap"] else options["stage"]
        )
        require(stage in {"observed", "bootstrap"}, "RESUME_REQUIRES_STAGE")
        with lock(directory / "worker.lock"):
            if options["resume"]:
                require(
                    (directory / "worker.json").exists(),
                    "RESUME_REQUIRES_EXISTING_EXECUTION",
                )
            with Progress(directory, stage.upper()) as progress:
                try:
                    progress.check()
                    atomic_json(
                        directory / "worker.json", dict(status="RUNNING", stage=stage)
                    )
                    if stage == "observed":
                        observe(directory, streams, spec, progress)
                        status = "OBSERVED_COMPLETE"
                    else:
                        scores = bootstrap(
                            directory, streams, spec, progress, options["workers"]
                        )
                        slices = stability(directory, streams, spec, progress)
                        progress.check()
                        finish(directory, spec, scores, slices)
                        status = "COMPLETE"
                        try:
                            result = analyze_existing(directory, spec, streams)
                            analyze_diagnostics_existing(
                                directory, spec, streams, result
                            )
                            atomic_json(
                                directory / "economic_analysis_status.json",
                                dict(
                                    status="COMPLETE",
                                    winner=result["winner"],
                                    method_version=result["method_version"],
                                    upstream_retention_index=(
                                        "PRESENT"
                                        if (directory / "RETENTION_INDEX.tsv").is_file()
                                        else "MISSING_REVIEW"
                                    ),
                                ),
                            )
                        except Exception as economic_error:
                            atomic_json(
                                directory / "economic_analysis_status.json",
                                dict(
                                    status="STOP_TECHNICAL", reason=str(economic_error)
                                ),
                            )
                    atomic_json(
                        directory / "worker.json", dict(status=status, stage=stage)
                    )
                except ResourcePause as error:
                    atomic_json(
                        directory / "worker.json",
                        dict(status="PAUSE_RESOURCE", stage=stage, reason=str(error)),
                    )
                except Exception as error:
                    atomic_json(
                        directory / "worker.json",
                        dict(status="STOP_TECHNICAL", stage=stage, reason=str(error)),
                    )
                    raise
