from django.db.models import Min
from django.utils import timezone

from football.models import (
    CompetitionSourceRef,
    MatchSourceRef,
    ReconciliationStatus,
    Source,
    TeamSourceRef,
)

from .events import emit_event


def pending_reconciliation(now=None):
    now = now or timezone.now()
    rows = []
    for source in Source.objects.order_by("code"):
        models = (CompetitionSourceRef, TeamSourceRef, MatchSourceRef)
        querysets = [
            model.objects.filter(
                source=source,
                reconciliation_status=ReconciliationStatus.PENDING,
            )
            for model in models
        ]
        counts = [queryset.count() for queryset in querysets]
        if not any(counts):
            continue
        oldest = min(
            value
            for value in (
                queryset.aggregate(value=Min("first_seen_at"))["value"]
                for queryset in querysets
            )
            if value is not None
        )
        rows.append(
            {
                "source": source.code,
                "competition_pending": counts[0],
                "team_pending": counts[1],
                "match_pending": counts[2],
                "oldest_pending_age_seconds": max(
                    0, int((now - oldest).total_seconds())
                ),
            }
        )
    return rows


def emit_reconciliation_pending(*, pipeline_run_id=None, capture_run_id=None, now=None):
    events = []
    for row in pending_reconciliation(now=now):
        source = row.pop("source")
        events.append(
            emit_event(
                event_code="RECONCILIATION_PENDING",
                severity="WARNING",
                component="reconciliation",
                operation="aggregate_pending_source_refs",
                outcome="DEGRADED",
                failure_kind="unresolved_identity",
                human_summary=f"Pending {source} identities require Admin review.",
                provider=source,
                pipeline_run_id=pipeline_run_id,
                capture_run_id=capture_run_id,
                context=row,
            )
        )
    return events
