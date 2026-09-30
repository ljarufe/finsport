"""Offline FS-023 subset Experiment Lab command; no deployment side effects."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from football.experiments.fs023_runner import candidate_ids, run_subset
from football.experiments.storage import canonical


class Command(BaseCommand):
    help = (
        "Run only the preregistered FS-023 candidate subset on the exact frozen corpus."
    )

    def add_arguments(self, parser):
        parser.add_argument("--candidate-ids", required=True)
        parser.add_argument("--benchmark-spec", required=True)
        parser.add_argument("--root", required=True)
        parser.add_argument("--durable-corpus", required=True)

    def handle(self, *args, **options):
        try:
            ids = candidate_ids(options["candidate_ids"])
            benchmark = json.loads(Path(options["benchmark_spec"]).read_text())
            directory, publication = run_subset(
                ids=ids,
                benchmark=benchmark,
                output_root=options["root"],
                durable=options["durable_corpus"],
                mode="evaluation-only" if ids == (209,) else "selection",
            )
        except (ValueError, OSError, KeyError, TypeError) as error:
            raise CommandError(str(error)) from None
        self.stdout.write(
            canonical(
                {
                    "status": "COMPLETE",
                    "execution_id": directory.name,
                    "candidate_ids": list(ids),
                    "publication": str(directory / "publication.json"),
                    "activation": publication["activation"],
                }
            )
        )
