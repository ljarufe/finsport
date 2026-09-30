"""BSD shadow/primary routing ahead of the single canonical Capital settlement path."""

from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from football.models import (
    BSDEventBinding,
    CapitalPosition,
    CompetitionResultRoute,
)
from football.providers.bsd import BSDClient, BSDError
from football.providers.bsd_identity import rebind_stale_event
from football.result_provider import normalize_bsd, record, sentinel_phase, shadow_gate


@transaction.atomic
def _failure(route, error, at):
    if error.state in {
        "BSD_AUTH_FAILED",
        "BSD_ENTITLEMENT_FAILED",
        "BSD_TASTER_EXHAUSTED",
    }:
        until = None
        if error.state == "BSD_TASTER_EXHAUSTED":
            until = (
                at + timedelta(seconds=error.retry_after)
                if error.retry_after is not None
                else datetime.combine(
                    at.astimezone(UTC).date() + timedelta(days=1),
                    datetime.min.time(),
                    tzinfo=UTC,
                )
            )
        for affected in CompetitionResultRoute.objects.select_for_update().all():
            if not affected.bsd_league_ids:
                continue
            affected.provenance = {
                **affected.provenance,
                "bsd_previous_state": affected.provenance.get(
                    "bsd_previous_state", affected.bsd_state
                ),
                "bsd_global_failure": error.state,
            }
            affected.bsd_state = "BSD_BACKOFF" if until is not None else error.state
            affected.bsd_backoff_until = until
            affected.save(
                update_fields=["bsd_state", "bsd_backoff_until", "provenance"]
            )
        return
    if error.state == "BSD_BACKOFF":
        level = min(2, int(route.provenance.get("bsd_backoff_level", 0)) + 1)
        route.provenance = {
            **route.provenance,
            "bsd_previous_state": route.provenance.get(
                "bsd_previous_state", route.bsd_state
            ),
            "bsd_backoff_level": level,
        }
        route.bsd_state = "BSD_BACKOFF"
        route.bsd_backoff_until = at + timedelta(seconds=error.retry_after or 900)
    elif error.state not in {"BSD_IDENTITY_UNRESOLVED", "BSD_IDENTITY_AMBIGUOUS"}:
        if (
            route.bsd_failure_window_started_at is None
            or at - route.bsd_failure_window_started_at > timedelta(minutes=10)
        ):
            route.bsd_failure_window_started_at = at
            route.bsd_failures = 0
        route.bsd_failures += 1
        if route.bsd_failures >= 3 or route.bsd_state == "BSD_BACKOFF":
            level = min(2, int(route.provenance.get("bsd_backoff_level", 0)) + 1)
            route.provenance = {
                **route.provenance,
                "bsd_previous_state": route.provenance.get(
                    "bsd_previous_state", route.bsd_state
                ),
                "bsd_backoff_level": level,
            }
            route.bsd_state = "BSD_BACKOFF"
            route.bsd_backoff_until = at + timedelta(minutes=(15, 30, 60)[level - 1])
    route.save(
        update_fields=[
            "bsd_state",
            "bsd_backoff_until",
            "bsd_failures",
            "bsd_failure_window_started_at",
            "provenance",
        ]
    )


def _success(route):
    if route.bsd_state == "BSD_BACKOFF":
        route.bsd_state = route.provenance.get(
            "bsd_previous_state", "BSD_SHADOW_VALIDATION"
        )
    route.provenance = {
        key: value
        for key, value in route.provenance.items()
        if key not in {"bsd_backoff_level", "bsd_global_failure", "bsd_previous_state"}
    }
    route.bsd_failures = 0
    route.bsd_failure_window_started_at = None
    route.bsd_backoff_until = None
    route.save(
        update_fields=[
            "bsd_state",
            "bsd_failures",
            "bsd_failure_window_started_at",
            "bsd_backoff_until",
            "provenance",
        ]
    )


def _ready(route, at):
    if route.bsd_state in {"BSD_AUTH_FAILED", "BSD_ENTITLEMENT_FAILED", "BSD_DEGRADED"}:
        return False
    if (
        route.bsd_state == "BSD_BACKOFF"
        and route.bsd_backoff_until
        and at < route.bsd_backoff_until
    ):
        return False
    return route.bsd_state in {
        "BSD_SHADOW_VALIDATION",
        "BSD_PRIMARY_VALIDATED",
        "BSD_BACKOFF",
    }


def effective_bsd_state(route):
    """Report missing configuration without changing persisted readiness history."""
    if route.bsd_league_ids and not settings.BSD_API_TOKEN:
        return "BSD_NOT_CONFIGURED"
    return route.bsd_state


def process_due_bsd(due, *, at, client_factory=BSDClient):
    """Return match IDs postponed/settled through BSD; the rest use API-F."""
    if not settings.BSD_API_TOKEN:
        return set(), 0, []
    handled = set()
    settled = 0
    errors = []
    client = None
    for position in due:
        match = position.match
        if match.pk in handled:
            continue
        try:
            route = CompetitionResultRoute.objects.get(
                competition_id=match.season.competition_id
            )
            binding = BSDEventBinding.objects.get(match=match)
        except (CompetitionResultRoute.DoesNotExist, BSDEventBinding.DoesNotExist):
            continue
        if (
            not route.bsd_league_ids
            or not _ready(route, at)
            or binding.provenance.get("state") == "STALE_404"
        ):
            continue
        if client is None:
            client = client_factory()
        try:
            try:
                payload = client.get(
                    f"events/{binding.bsd_event_id}/",
                    logical_identity=f"bsd:result:{match.pk}:{binding.bsd_event_id}:{at.isoformat()}",
                    match_id=match.pk,
                )
            except BSDError as error:
                if error.status != 404:
                    raise
                if (
                    rebind_stale_event(match, route, binding, client=client, at=at)
                    != "BOUND"
                ):
                    raise
                payload = client.get(
                    f"events/{binding.bsd_event_id}/",
                    logical_identity=f"bsd:result-rebind:{match.pk}:{binding.bsd_event_id}:{at.isoformat()}",
                    match_id=match.pk,
                )
            result = normalize_bsd(match, binding, payload, observed_at=timezone.now())
            primary = route.bsd_state == "BSD_PRIMARY_VALIDATED"
            observation, disposition = record(match, result, authoritative=primary)
            _success(route)
            if disposition == "RESULT_CONFLICT":
                _confirmed_conflict(match, at)
                CapitalPosition.objects.filter(match=match, status="OPEN").update(
                    debt_status="DEGRADED",
                    next_result_check_at=None,
                    result_refresh_error="RESULT_CONFLICT",
                )
                errors.append(f"RESULT_CONFLICT:{match.pk}")
                handled.add(match.pk)
                continue
            if disposition == "PENDING_CONFLICT":
                CapitalPosition.objects.filter(match=match, status="OPEN").update(
                    next_result_check_at=at + timedelta(minutes=30),
                    result_refresh_error="RESULT_CONFLICT_PENDING",
                )
                handled.add(match.pk)
                continue
            if result.status == "PST":
                CapitalPosition.objects.filter(match=match, status="OPEN").update(
                    next_result_check_at=None,
                    debt_status="DEGRADED",
                    result_refresh_error="WAITING_FOR_FIXTURE_RECONCILIATION",
                )
                handled.add(match.pk)
                continue
            if not primary:
                continue  # API-F remains settlement authority in SHADOW.
            if result.status in {"FT", "CANC", "ABD", "AWD", "WO"}:
                from football.capital.runtime import (
                    observe_terminal_result,
                    settle_observation,
                )

                match.refresh_from_db()
                canonical, _ = observe_terminal_result(
                    match,
                    known_at=timezone.now(),
                    provider_result=observation,
                    provenance={
                        "authority": "BSD_PRIMARY_VALIDATED",
                        "external_ref": result.external_ref,
                    },
                )
                if canonical:
                    settled += settle_observation(canonical, settled_at=timezone.now())
                    handled.add(match.pk)
            elif position.result_refresh_error != "BSD_NONTERMINAL":
                CapitalPosition.objects.filter(match=match, status="OPEN").update(
                    next_result_check_at=at + timedelta(minutes=30),
                    result_refresh_attempted_at=at,
                    result_refresh_error="BSD_NONTERMINAL",
                )
                handled.add(match.pk)
            # Second nonterminal observation falls through to API-F fallback.
        except BSDError as error:
            _failure(route, error, at)
            errors.append(f"{error.state}:{match.pk}")
            # Failure falls through to admitted API-F same-wake fallback.
    return handled, settled, errors


def maybe_promote_shadow():
    gate = shadow_gate()
    if gate["status"] == "PASS":
        for route in CompetitionResultRoute.objects.filter(
            bsd_state="BSD_SHADOW_VALIDATION"
        ):
            route.bsd_state = "BSD_PRIMARY_VALIDATED"
            route.provenance = {
                **route.provenance,
                "bsd_validated_at": timezone.now().isoformat(),
                "bsd_sentinel_phase": sentinel_phase(gate),
                "bsd_validation_gate": gate,
            }
            route.save(update_fields=["bsd_state", "provenance"])
    if gate["status"] == "PASS":
        phase = sentinel_phase(gate)
        for route in CompetitionResultRoute.objects.filter(
            bsd_state="BSD_PRIMARY_VALIDATED"
        ):
            if route.provenance.get("bsd_sentinel_phase") != phase:
                route.provenance = {**route.provenance, "bsd_sentinel_phase": phase}
                route.save(update_fields=["provenance"])
    return gate


@transaction.atomic
def _confirmed_conflict(match, at):
    competition_id = match.season.competition_id
    CompetitionResultRoute.objects.filter(competition_id=competition_id).update(
        bsd_state="BSD_DEGRADED"
    )
    from football.models import ResultProviderObservation

    affected = set(
        ResultProviderObservation.objects.filter(
            provider="BSD",
            conflict=True,
            provider_observed_at__gte=at - timedelta(days=30),
            provider_observed_at__lte=at,
        ).values_list("match__season__competition_id", flat=True)
    )
    if len(affected) >= 2:
        for route in CompetitionResultRoute.objects.all():
            if route.bsd_league_ids:
                route.bsd_state = "BSD_DEGRADED"
                route.provenance = {
                    **route.provenance,
                    "bsd_global_degradation": "TWO_CONFIRMED_CONFLICTS_30D",
                }
                route.save(update_fields=["bsd_state", "provenance"])


def recheck_pending_conflicts(*, at, client_factory=BSDClient):
    """Retry a tentative mismatch only after BSD's 30-minute lag allowance."""
    from football.models import ResultProviderObservation

    if not settings.BSD_API_TOKEN:
        return 0, []
    rows = (
        ResultProviderObservation.objects.filter(
            provider="BSD",
            status_short__in=("FT", "ET", "P", "AET", "PEN"),
            provider_observed_at__lte=at - timedelta(minutes=30),
        )
        .select_related("match__season__competition")
        .order_by("provider_observed_at", "id")
    )
    calls = 0
    errors = []
    seen = set()
    client = None
    for row in rows:
        if row.match_id in seen or not row.provenance.get("pending_conflict"):
            continue
        seen.add(row.match_id)
        if ResultProviderObservation.objects.filter(
            match_id=row.match_id, provider="BSD", conflict=True
        ).exists():
            continue
        try:
            route = CompetitionResultRoute.objects.get(
                competition_id=row.match.season.competition_id
            )
            binding = BSDEventBinding.objects.get(match_id=row.match_id)
        except (CompetitionResultRoute.DoesNotExist, BSDEventBinding.DoesNotExist):
            continue
        if not _ready(route, at):
            continue
        client = client or client_factory()
        try:
            payload = client.get(
                f"events/{binding.bsd_event_id}/",
                logical_identity=f"bsd:conflict-recheck:{row.match_id}:{at.isoformat()}",
                match_id=row.match_id,
            )
            calls += 1
            result = normalize_bsd(row.match, binding, payload, observed_at=at)
            _, disposition = record(row.match, result, authoritative=False)
            _success(route)
            if disposition == "RESULT_CONFLICT":
                _confirmed_conflict(row.match, at)
                errors.append(f"RESULT_CONFLICT:{row.match_id}")
        except BSDError as error:
            calls += 1
            _failure(route, error, at)
            errors.append(f"{error.state}:{row.match_id}")
    return calls, errors
