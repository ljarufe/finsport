from django.core.management.base import BaseCommand, CommandError

from football.experiments.decision_artifacts import promote_decision
from football.experiments.decision_runner import (
    DecisionSpec,
    freeze_decision_spec,
    run_decision_experiment,
)
from football.experiments.storage import (
    canonical,
    local_decision_spec_path,
    require_dev,
)


class Command(BaseCommand):
    help = "Freeze or run the offline FS-019 global Decision experiment."

    def add_arguments(self, parser):
        parser.add_argument("--spec", required=True)
        parser.add_argument("--freeze", action="store_true")
        parser.add_argument("--promote", action="store_true")
        parser.add_argument(
            "--workspace-root",
            help="Visible Experiment Lab workspace root (default: <BASE_DIR>/tmp)",
        )

    def handle(self, *args, **options):
        try:
            require_dev()
            workspace_root = options.get("workspace_root")
            path = local_decision_spec_path(
                options["spec"], workspace_root=workspace_root
            )
            if options["freeze"]:
                if options["promote"]:
                    raise ValueError("Freeze cannot analyze or promote")
                spec = freeze_decision_spec(path)
                self.stdout.write(
                    canonical(
                        {
                            "status": "FROZEN",
                            "spec_id": spec.id,
                            "snapshot_hash": spec.data["snapshot"]["content_hash"],
                            "decision_common_cohort_hash": spec.data[
                                "decision_common_cohort_hash"
                            ],
                            "decision_common_count": spec.data["snapshot"]["row_count"],
                        }
                    )
                )
                return
            spec = DecisionSpec.load(path)
            result = run_decision_experiment(spec, path, workspace_root=workspace_root)
            promoted = False
            if options["promote"]:
                promoted = (
                    promote_decision(result, spec, workspace_root=workspace_root)
                    is not None
                )
            self.stdout.write(
                canonical(
                    {
                        "run_id": result["run_id"],
                        "execution_id": result["execution_id"],
                        "disposition": result["summary"]["disposition"],
                        "selected": result["summary"]["selected"],
                        "promoted": promoted,
                    }
                )
            )
        except (ValueError, OSError, KeyError) as error:
            raise CommandError(str(error)) from None
