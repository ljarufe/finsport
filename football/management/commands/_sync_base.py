from django.core.management.base import BaseCommand, CommandError

from football.api_football import APIFootballClient, APIFootballError
from football.api_inkabet import InkabetError
from football.observability.events import emit_event
from football.sync import FootballSyncError, SyncStats


class SyncCommand(BaseCommand):
    client_class = APIFootballClient

    def run_sync(self, **options):
        raise NotImplementedError

    def handle(self, *args, **options):
        self.stats = SyncStats()
        client = None
        error_message = None
        try:
            client = self.client_class()
            self.stats = self.run_sync(client=client, **options)
        except (APIFootballError, InkabetError, FootballSyncError) as error:
            error_message = str(error)
            provider = getattr(error, "provider", "")
            emit_event(
                event_code=(
                    "PROVIDER_OPERATION_FAILED" if provider else "SYNC_OPERATION_FAILED"
                ),
                severity="ERROR",
                component="provider" if provider else "synchronization",
                operation=self.__class__.__module__.rsplit(".", 1)[-1],
                outcome="FAILED",
                failure_kind=getattr(error, "failure_kind", "sync_contract"),
                human_summary="A football synchronization command failed.",
                provider=provider,
                exception=error,
                context=getattr(error, "diagnostic_context", {}),
            )
        self._report(self.stats, client, error_message)
        if error_message:
            raise CommandError(error_message)

    def _report(self, stats, client, error_message):
        remaining = (
            client.daily_remaining
            if client is not None and client.daily_remaining is not None
            else "unknown"
        )
        calls = client.calls if client is not None else 0
        inkabet_client = getattr(self, "inkabet_client", None)
        inkabet_calls = inkabet_client.calls if inkabet_client is not None else 0
        inkabet_errors = getattr(self, "inkabet_errors", 0)
        self.stdout.write(
            " ".join(
                (
                    f"created={stats.created}",
                    f"updated={stats.updated}",
                    f"unchanged={stats.unchanged}",
                    f"skipped={stats.skipped}",
                    f"pending_competitions={stats.pending_competitions}",
                    f"pending_teams={stats.pending_teams}",
                    f"pending_matches={stats.pending_matches}",
                    f"calls={calls}",
                    f"inkabet_calls={inkabet_calls}",
                    f"inkabet_errors={inkabet_errors}",
                    f"daily_remaining={remaining}",
                    f"error={error_message or 'none'}",
                )
            )
        )
        if stats.reconciliation_required:
            models = []
            if stats.pending_competitions:
                models.append("Football > Competition source refs")
            if stats.pending_teams:
                models.append("Football > Team source refs")
            if stats.pending_matches:
                models.append("Football > Match source refs")
            self.stdout.write(
                self.style.WARNING(
                    "RECONCILIATION_REQUIRED: "
                    f"competitions={stats.pending_competitions} "
                    f"teams={stats.pending_teams} "
                    f"matches={stats.pending_matches}; "
                    f"review {', '.join(models)} in Django Admin; "
                    "filter by source and reconciliation status"
                )
            )
