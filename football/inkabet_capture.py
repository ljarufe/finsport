from dataclasses import dataclass, field

from django.conf import settings

from football.api_inkabet import InkabetClient
from football.inkabet import (
    reconcile_categories,
    resolved_match_refs_for,
    sync_mw3w_payload,
)
from football.models import OddsObservation, OddsSnapshot
from football.observability.events import emit_event, sanitize_text
from football.sync import SyncStats


@dataclass
class InkabetCaptureResult:
    status: str
    stats: SyncStats = field(default_factory=SyncStats)
    calls: int = 0
    observations_created: int = 0
    snapshots_changed: int = 0
    errors: list[dict] = field(default_factory=list)
    client: object = field(default=None, repr=False)

    def as_dict(self):
        return {
            "status": self.status,
            "calls": self.calls,
            "observations_created": self.observations_created,
            "snapshots_changed": self.snapshots_changed,
            "created": self.stats.created,
            "updated": self.stats.updated,
            "unchanged": self.stats.unchanged,
            "skipped": self.stats.skipped,
            "pending_competitions": self.stats.pending_competitions,
            "pending_teams": self.stats.pending_teams,
            "pending_matches": self.stats.pending_matches,
            "errors": self.errors,
        }


def _error_evidence(error, operation, *, match_id=None, event_id=None):
    return {
        "operation": operation,
        "match_id": match_id,
        "event_id": event_id,
        "failure_kind": getattr(error, "failure_kind", "provider_request"),
        "provider": getattr(error, "provider", "Inkabet"),
        "error_class": error.__class__.__name__,
        "error_message": " ".join(sanitize_text(error, 500).split()),
    }


def _emit_degraded(error, errors):
    emit_event(
        event_code="PROVIDER_DEGRADED",
        severity="WARNING",
        component="capture",
        operation=errors[0]["operation"],
        outcome="DEGRADED",
        failure_kind=getattr(error, "failure_kind", "provider_request"),
        human_summary="Inkabet evidence was incomplete; canonical work continued.",
        provider="Inkabet",
        match_id=errors[0].get("match_id"),
        exception=error,
        context={
            **getattr(error, "diagnostic_context", {}),
            "occurrence_count": len(errors),
        },
    )


def capture_inkabet_matches(
    matches,
    *,
    client_factory=InkabetClient,
    automatic=True,
):
    matches = list({match.pk: match for match in matches}.values())
    if not matches:
        return InkabetCaptureResult("NO_WORK")
    if automatic and not settings.INKABET_AUTOMATIC_ENABLED:
        return InkabetCaptureResult("DISABLED")
    if not settings.INKABET_BRAND_ID or not settings.INKABET_MARKET_CODE:
        return InkabetCaptureResult(
            "SKIPPED_CONFIGURATION",
            stats=SyncStats(skipped=len(matches)),
        )

    before_observations = OddsObservation.objects.filter(
        match__in=matches, source__code="inkabet"
    ).count()
    before_snapshots = {
        (row.match_id, row.bookmaker_id, row.market_id): (
            row.home,
            row.draw,
            row.away,
            row.provider_updated_at,
            row.observed_at,
        )
        for row in OddsSnapshot.objects.filter(
            match__in=matches, source__code="inkabet"
        )
    }
    stats = SyncStats()
    errors = []
    first_error = None
    client = None
    try:
        client = client_factory()
        categories = client.categories()
        stats.merge(reconcile_categories(categories, matches))
    except Exception as error:  # Secondary acquisition must never stop canonical work.
        first_error = error
        errors.append(_error_evidence(error, "categories"))
    if not errors:
        resolved = list(resolved_match_refs_for(matches))
        resolved_match_ids = {ref.match_id for ref in resolved}
        stats.skipped += len({match.pk for match in matches} - resolved_match_ids)
        for match_ref in resolved:
            try:
                stats.merge(
                    sync_mw3w_payload(
                        client.match_winner(match_ref.external_id), match_ref
                    )
                )
            except Exception as error:  # Preserve other resolved events on one failure.
                if first_error is None:
                    first_error = error
                errors.append(
                    _error_evidence(
                        error,
                        "match_winner",
                        match_id=match_ref.match_id,
                        event_id=match_ref.external_id,
                    )
                )
    if errors:
        _emit_degraded(first_error, errors)
    after_observations = OddsObservation.objects.filter(
        match__in=matches, source__code="inkabet"
    ).count()
    after_snapshots = {
        (row.match_id, row.bookmaker_id, row.market_id): (
            row.home,
            row.draw,
            row.away,
            row.provider_updated_at,
            row.observed_at,
        )
        for row in OddsSnapshot.objects.filter(
            match__in=matches, source__code="inkabet"
        )
    }
    return InkabetCaptureResult(
        "DEGRADED" if errors else "SUCCESS",
        stats=stats,
        calls=getattr(client, "calls", 0),
        observations_created=after_observations - before_observations,
        snapshots_changed=sum(
            before_snapshots.get(identity) != value
            for identity, value in after_snapshots.items()
        ),
        errors=errors,
        client=client,
    )
