import re

from django.core.management.base import BaseCommand, CommandError

from football.experiments.capital_artifacts import publish_capital
from football.experiments.capital_runner import (
    CapitalSpec,
    capital_root,
    execute_shard,
    execution_context,
    freeze_capital_spec,
    local_capital_spec_path,
    run_capital_experiment,
    verify_capital_run,
)
from football.experiments.storage import canonical, read_json, require_dev


class Command(BaseCommand):
    help = (
        "Manually freeze, shard, run or publish the offline FS-020 Capital experiment."
    )

    def add_arguments(self, parser):
        parser.add_argument("--spec", required=True)
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--freeze", action="store_true")
        mode.add_argument("--run", action="store_true")
        mode.add_argument("--publish-existing", metavar="EXECUTION_ID")
        mode.add_argument(
            "--shard", nargs=4, type=int, metavar=("LAG", "BLOCK", "START", "STOP")
        )
        parser.add_argument("--promote", action="store_true")
        parser.add_argument("--workspace-root")

    def handle(self, *args, **options):
        try:
            require_dev()
            workspace = options.get("workspace_root")
            path = local_capital_spec_path(options["spec"], workspace_root=workspace)
            # Never chain promotion to --run: changing even this CLI file alters
            # capital_runtime() and would create a new economic execution ID.
            if options["promote"]:
                raise ValueError("USE_PUBLISH_EXISTING_FOR_FROZEN_RUN")
            publication_id = options.get("publish_existing")
            if publication_id is not None and not re.fullmatch(
                r"[0-9a-f]{64}", publication_id
            ):
                raise ValueError("INVALID_CAPITAL_EXECUTION_ID")
            if options["freeze"]:
                spec = freeze_capital_spec(path)
                self.stdout.write(canonical(dict(status="FROZEN", spec_id=spec.id)))
                return
            spec = CapitalSpec.load(path)
            if publication_id is not None:
                # Resolve from the explicit historical ID, not from the current
                # code hash. Run/shards and the stored runtime stay immutable.
                directory = capital_root(workspace) / publication_id
                result = read_json(directory / "run.json")
                if result.get("execution_id") != publication_id:
                    raise ValueError("CAPITAL_EXECUTION_ID_MISMATCH")
                verify_capital_run(result, spec, directory=directory)
                record = publish_capital(result, workspace_root=workspace)
                self.stdout.write(
                    canonical(
                        dict(
                            status="PUBLISHED_EXISTING",
                            execution_id=publication_id,
                            run_id=result["run_id"],
                            promotion=record["promotion"],
                            selected=record["selected"],
                            disposition=record["disposition"],
                        )
                    )
                )
                return
            if options["shard"]:
                opportunities, _, execution_id, directory = execution_context(
                    spec, workspace_root=workspace
                )
                result = execute_shard(
                    opportunities, execution_id, directory, *options["shard"]
                )
                self.stdout.write(
                    canonical(
                        {k: result[k] for k in ("shard_id", "status", "start", "stop")}
                    )
                )
                return
            result = run_capital_experiment(spec, workspace_root=workspace)
            self.stdout.write(
                canonical(
                    dict(
                        run_id=result["run_id"],
                        execution_id=result["execution_id"],
                        **result["summary"],
                    )
                )
            )
        except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as error:
            raise CommandError(str(error)) from None
