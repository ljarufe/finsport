from django.core.management.base import BaseCommand, CommandError

from football.experiments.artifacts import promote
from football.experiments.runner import run_experiment
from football.experiments.spec import (
    TOURNAMENTS,
    ExperimentSpec,
    freeze_recovery_spec,
    freeze_spec,
)
from football.experiments.storage import canonical, local_spec_path, require_dev
from football.models import Competition


class Command(BaseCommand):
    help = "Freeze CURRENT configs or replay a frozen experiment offline."

    def add_arguments(self, parser):
        parser.add_argument("--spec", required=True)
        parser.add_argument("--freeze", action="store_true")
        parser.add_argument("--cutoff")
        parser.add_argument(
            "--competitions", default=",".join(map(str, sorted(TOURNAMENTS)))
        )
        parser.add_argument("--pilot", action="store_true")
        parser.add_argument("--promote", action="store_true")
        parser.add_argument("--recover-from")
        parser.add_argument("--confirm", action="store_true")
        parser.add_argument("--replace-provisional", action="store_true")
        parser.add_argument("--expected-previous-run-id")

    def handle(self, *args, **options):
        try:
            require_dev()
            path = local_spec_path(options["spec"])
            if options["replace_provisional"] and not options["promote"]:
                raise ValueError("--replace-provisional requires --promote")
            if (
                options["expected_previous_run_id"]
                and not options["replace_provisional"]
            ):
                raise ValueError("Expected previous run requires --replace-provisional")
            if options["freeze"]:
                if options["promote"] or options["confirm"]:
                    raise ValueError("Freeze cannot analyze or promote")
                if options["recover_from"]:
                    if options["cutoff"]:
                        raise ValueError("Recovery inherits the frozen cutoff")
                    if options["competitions"] != ",".join(
                        map(str, sorted(TOURNAMENTS))
                    ):
                        raise ValueError("Recovery inherits all ten competitions")
                    spec = freeze_recovery_spec(
                        local_spec_path(options["recover_from"])
                    )
                else:
                    if not options["cutoff"]:
                        raise ValueError("Freeze requires --cutoff")
                    ids = sorted(set(map(int, options["competitions"].split(","))))
                    if set(ids) - TOURNAMENTS.keys():
                        raise ValueError("Unknown competition")
                    competitions = list(
                        Competition.objects.filter(pk__in=ids, enabled=True)
                    )
                    if len(competitions) != len(ids):
                        raise ValueError(
                            "All requested competitions must exist and be enabled"
                        )
                    spec = freeze_spec(competitions, options["cutoff"])
                spec.save(path)
                self.stdout.write(canonical({"status": "FROZEN", "spec_id": spec.id}))
                return
            spec = ExperimentSpec.load(path)
            if options["recover_from"]:
                raise ValueError("--recover-from requires --freeze")
            result = run_experiment(
                spec, pilot=options["pilot"], confirm=options["confirm"]
            )
            if options["promote"]:
                promote(
                    result,
                    replace_provisional=options["replace_provisional"],
                    expected_previous_run_id=options["expected_previous_run_id"],
                )
            self.stdout.write(
                canonical(
                    {
                        "run_id": result["run_id"],
                        "analysis_id": result.get("analysis_id"),
                        "source_acquisition_id": result.get("source_acquisition_id"),
                        "disposition": result["summary"]["disposition"],
                        "selected": result["summary"]["selected"],
                        "promoted": options["promote"],
                    }
                )
            )
        except (ValueError, OSError, KeyError) as error:
            raise CommandError(str(error)) from None
