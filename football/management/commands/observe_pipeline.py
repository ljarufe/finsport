import json
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, connections
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from football.observability.events import emit_event
from football.observability.liveness import evaluate_liveness


class Command(BaseCommand):
    help = "Run the DB-only FS-007 pipeline liveness watchdog."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument(
            "--at",
            help="Deterministic aware ISO-8601 instant; valid only with --once.",
        )

    def handle(self, *args, **options):
        del args
        if options["at"] and not options["once"]:
            raise CommandError("--at requires --once.")
        forced_now = self._parse_at(options["at"]) if options["at"] else None
        while True:
            self._check(
                forced_now or timezone.now(),
                prepare_connection=not options["once"],
            )
            if options["once"]:
                return
            time.sleep(settings.OBSERVABILITY_WATCHDOG_INTERVAL_SECONDS)

    @staticmethod
    def _parse_at(value):
        parsed = parse_datetime(value)
        if parsed is None or timezone.is_naive(parsed):
            raise CommandError("--at must be an offset-aware ISO-8601 instant.")
        return parsed

    def _check(self, now, *, prepare_connection=True):
        path = Path(settings.OBSERVABILITY_WATCHDOG_STATE_FILE)
        state = self._load_state(path)
        enabled = settings.FOOTBALL_PIPELINE_ENABLED
        if not enabled:
            self._save_state(
                path,
                {"enabled": False, "monitoring_started_at": None, "overdue": False},
            )
            return
        if not state.get("enabled") or not state.get("monitoring_started_at"):
            state = {
                "enabled": True,
                "monitoring_started_at": now.isoformat(),
                "overdue": False,
            }
        monitoring_since = datetime.fromisoformat(state["monitoring_started_at"])
        if prepare_connection:
            close_old_connections()
        try:
            liveness = evaluate_liveness(
                now=now,
                enabled=True,
                cadence_seconds=settings.FOOTBALL_CAPTURE_WAKE_SECONDS,
                grace_seconds=settings.OBSERVABILITY_PIPELINE_GRACE_SECONDS,
                monitoring_since=monitoring_since,
            )
        except Exception as error:
            # A long-running management command must discard a connection that
            # failed mid-query so the next iteration can reconnect after a DB
            # restart instead of reusing a broken wrapper indefinitely.
            connections["default"].close()
            if not state.get("check_failed"):
                emit_event(
                    event_code="OBSERVABILITY_WATCHDOG_FAILED",
                    severity="ERROR",
                    component="observability-watchdog",
                    operation="query_pipeline_liveness",
                    outcome="FAILED",
                    failure_kind="database_dependency",
                    human_summary="The pipeline watchdog could not query PostgreSQL.",
                    exception=error,
                )
            state["check_failed"] = True
            self._save_state(path, state)
            return
        state["check_failed"] = False
        if liveness.overdue and not state.get("overdue"):
            activity = liveness.last_scheduler_activity
            emit_event(
                event_code="PIPELINE_OVERDUE",
                severity="ERROR",
                component="scheduler",
                operation="pipeline_liveness",
                outcome="FAILED",
                failure_kind="scheduler_silence",
                human_summary="No completed scheduler pipeline activity arrived in time.",
                pipeline_run_id=activity.pk if activity else None,
                context={
                    "enabled": True,
                    "threshold_seconds": liveness.threshold_seconds,
                    "grace_seconds": settings.OBSERVABILITY_PIPELINE_GRACE_SECONDS,
                    "last_scheduler_activity_at": (
                        activity.completed_at.isoformat() if activity else ""
                    ),
                    "scheduler_activity_status": activity.status if activity else "",
                },
            )
        state["overdue"] = liveness.overdue
        state["last_checked_at"] = now.isoformat()
        self._save_state(path, state)

    @staticmethod
    def _load_state(path):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _save_state(path, state):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
        temporary.replace(path)
