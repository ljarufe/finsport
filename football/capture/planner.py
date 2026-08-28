from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, Max, Q

from football.models import (
    CaptureRun,
    CaptureWorkItem,
    Match,
    MatchSourceRef,
    OddsMarket,
    ReconciliationStatus,
    Source,
)
from football.sync import API_FOOTBALL_CODE, FINISHED_STATUSES, MATCH_WINNER_NAMES

from .contracts import CapturePlan, PlannedWork, QuotaState

PRE_MATCH_STATUSES = {"NS", "TBD"}
TERMINAL_NO_OUTCOME_STATUSES = {"CANC", "ABD"}
FULFILLED_STATUSES = {
    CaptureWorkItem.Status.SUCCESS,
    CaptureWorkItem.Status.SUCCESS_EMPTY,
    CaptureWorkItem.Status.LATE_CAPTURE,
}


def _slot_start(at, cadence):
    seconds = max(1, int(cadence.total_seconds()))
    epoch = int(at.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % seconds), tz=UTC)


def quota_state(at, config):
    utc_at = at.astimezone(UTC)
    epoch_start = utc_at.replace(hour=0, minute=0, second=0, microsecond=0)
    observed = (
        CaptureRun.objects.filter(
            quota_observed_at__gte=epoch_start,
            quota_observed_at__lte=at,
            quota_remaining_after__isnull=False,
        )
        .order_by("-quota_observed_at", "-id")
        .first()
    )
    if observed is None:
        bootstrap_attempts = sum(
            CaptureRun.objects.filter(
                started_at__gte=epoch_start,
                started_at__lte=at,
                quota_observed_at__isnull=True,
            ).values_list("provider_attempts", flat=True)
        )
        return QuotaState(
            basis="BOUNDED_BOOTSTRAP",
            limit=None,
            remaining=max(0, config.bootstrap_max_attempts - bootstrap_attempts),
            observed_at=None,
            freshness_seconds=None,
        )
    # Header-less runs are already bounded. Their exact attempt count is summed
    # separately because Count(id) alone would understate multi-attempt failures.
    headerless_attempts = sum(
        CaptureRun.objects.filter(
            started_at__gt=observed.quota_observed_at,
            started_at__lte=at,
            quota_observed_at__isnull=True,
        ).values_list("provider_attempts", flat=True)
    )
    remaining = max(0, observed.quota_remaining_after - headerless_attempts)
    return QuotaState(
        basis="HEADER_CURRENT_UTC_EPOCH",
        limit=observed.quota_limit,
        remaining=remaining,
        observed_at=observed.quota_observed_at,
        freshness_seconds=max(
            0, int((at - observed.quota_observed_at).total_seconds())
        ),
    )


class CapturePlanner:
    def __init__(self, *, config):
        self.config = config

    def plan(
        self,
        *,
        at,
        match_id=None,
        purpose=None,
        window=None,
        allow_bootstrap=False,
    ):
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("Capture planning requires a timezone-aware datetime.")
        purposes = {value for value, _ in CaptureWorkItem.Purpose.choices}
        if purpose is not None and purpose not in purposes:
            raise ValueError(f"Unknown capture purpose: {purpose}.")
        window_names = {candidate.name for candidate in self.config.windows}
        if window is not None and window not in window_names:
            raise ValueError(f"Unknown capture window: {window}.")
        source = Source.objects.get(code=API_FOOTBALL_CODE)
        market = self._market(source)
        quota = quota_state(at, self.config)
        items = []
        if purpose in (None, CaptureWorkItem.Purpose.RESULT_REFRESH):
            items.extend(self._result_items(at, source, match_id))
        if purpose in (None, CaptureWorkItem.Purpose.FIXTURE_REFRESH) and (
            match_id is None or purpose == CaptureWorkItem.Purpose.FIXTURE_REFRESH
        ):
            items.extend(self._discovery_items(at, source))
        if purpose in (None, CaptureWorkItem.Purpose.ODDS_CAPTURE):
            items.extend(self._odds_items(at, source, market, match_id, window))
        items.sort(key=lambda item: item.priority)
        self._admit(items, quota, allow_bootstrap=allow_bootstrap)
        return CapturePlan(at, self.config, quota, items, allow_bootstrap)

    @staticmethod
    def _market(source):
        markets = OddsMarket.objects.filter(source=source)
        return next(
            (
                market
                for market in markets
                if market.name.strip().casefold() in MATCH_WINNER_NAMES
            ),
            None,
        )

    def _result_items(self, at, source, match_id):
        if not self.config.result_refresh_enabled:
            return []
        due_before = at - self.config.result_delay
        queryset = Match.objects.filter(
            season__competition__enabled=True,
            kickoff__lte=due_before,
            outcome="",
        ).select_related("season__competition")
        if match_id is not None:
            queryset = queryset.filter(pk=match_id)
        refs = self._refs(source, queryset)
        slot = _slot_start(at, self.config.result_cadence)
        items = []
        for match in queryset.order_by("kickoff", "id"):
            ref = refs.get(match.pk)
            identity = (
                f"{source.code}:result:{ref.external_id if ref else match.pk}:"
                f"{slot.isoformat()}"
            )
            status, reason = self._identity_status(identity)
            if match.status_short in FINISHED_STATUSES | TERMINAL_NO_OUTCOME_STATUSES:
                status = CaptureWorkItem.Status.STATUS_INELIGIBLE
                reason = "terminal fixture has no canonical outcome to refresh"
            if ref is None:
                status = CaptureWorkItem.Status.UNRESOLVED_IDENTITY
                reason = "resolved API-Football MatchSourceRef is required"
            items.append(
                PlannedWork(
                    purpose=CaptureWorkItem.Purpose.RESULT_REFRESH,
                    status=status,
                    source=source,
                    match=match,
                    external_id=ref.external_id if ref else "",
                    logical_identity=identity,
                    intended_window="result-refresh",
                    target_at=match.kickoff + self.config.result_delay,
                    not_before=match.kickoff + self.config.result_delay,
                    priority=(0, match.kickoff, match.pk),
                    priority_reason="mandatory unresolved outcome debt",
                    reason=reason,
                    estimated_min_cost=1 if status == "PLANNED" else 0,
                    estimated_max_cost=(
                        self.config.worst_operation_cost if status == "PLANNED" else 0
                    ),
                    params={"id": ref.external_id} if ref else {},
                )
            )
        return items

    def _discovery_items(self, at, source):
        if not self.config.discovery_enabled:
            return []
        slot = _slot_start(at, self.config.discovery_cadence)
        local_date = at.astimezone(ZoneInfo(settings.TIME_ZONE)).date()
        items = []
        for days_ahead in range(self.config.discovery_days_ahead + 1):
            discovery_date = local_date + timedelta(days=days_ahead)
            identity = f"{source.code}:discovery:{discovery_date}:{slot.isoformat()}"
            status, reason = self._identity_status(identity)
            items.append(
                PlannedWork(
                    purpose=CaptureWorkItem.Purpose.FIXTURE_REFRESH,
                    status=status,
                    source=source,
                    logical_identity=identity,
                    intended_window="fixture-discovery",
                    target_at=slot,
                    not_before=slot,
                    priority=(2, slot, days_ahead),
                    priority_reason="configured canonical fixture discovery horizon",
                    reason=reason,
                    estimated_min_cost=1 if status == "PLANNED" else 0,
                    estimated_max_cost=(
                        self.config.worst_operation_cost if status == "PLANNED" else 0
                    ),
                    params={
                        "date": discovery_date.isoformat(),
                        "timezone": settings.TIME_ZONE,
                    },
                )
            )
        return items

    def _odds_items(self, at, source, market, match_id, selected_window):
        queryset = Match.objects.filter(
            season__competition__enabled=True,
            kickoff__gte=at,
            kickoff__lte=at + self.config.horizon,
        ).select_related("season__competition")
        if match_id is not None:
            queryset = queryset.filter(pk=match_id)
        queryset = queryset.annotate(
            fulfilled_count=Count(
                "capture_work_items",
                filter=Q(
                    capture_work_items__purpose=CaptureWorkItem.Purpose.ODDS_CAPTURE,
                    capture_work_items__status__in=FULFILLED_STATUSES,
                ),
            ),
            latest_observation=Max("odds_observations__observed_at"),
        )
        matches = list(queryset.order_by("kickoff", "id"))
        refs = self._refs(source, matches)
        local_timezone = ZoneInfo(settings.TIME_ZONE)
        stratum_coverage = {}
        for match in matches:
            local_day = match.kickoff.astimezone(local_timezone).date()
            key = (match.season.competition_id, local_day)
            stratum_coverage[key] = stratum_coverage.get(key, 0) + int(
                match.fulfilled_count > 0
            )
        items = []
        for match in matches:
            local_day = match.kickoff.astimezone(local_timezone).date()
            base_priority = (
                stratum_coverage[(match.season.competition_id, local_day)],
                match.fulfilled_count,
                match.latest_observation or datetime.min.replace(tzinfo=UTC),
                match.kickoff,
                match.pk,
            )
            if match.status_short not in PRE_MATCH_STATUSES:
                items.append(
                    self._ineligible_item(
                        source,
                        match,
                        CaptureWorkItem.Status.STATUS_INELIGIBLE,
                        "match is not in a pre-match status",
                        (1, datetime.max.replace(tzinfo=UTC), *base_priority),
                    )
                )
                continue
            if (match.season.coverage or {}).get("odds") is not True:
                items.append(
                    self._ineligible_item(
                        source,
                        match,
                        CaptureWorkItem.Status.ODDS_NOT_COVERED,
                        "season does not explicitly report odds coverage",
                        (1, datetime.max.replace(tzinfo=UTC), *base_priority),
                    )
                )
                continue
            ref = refs.get(match.pk)
            if ref is None or market is None:
                items.append(
                    self._ineligible_item(
                        source,
                        match,
                        CaptureWorkItem.Status.UNRESOLVED_IDENTITY,
                        "resolved fixture identity and Match Winner market are required",
                        (1, datetime.max.replace(tzinfo=UTC), *base_priority),
                    )
                )
                continue
            for index, candidate in enumerate(self.config.windows):
                if selected_window and candidate.name != selected_window:
                    continue
                target = match.kickoff - candidate.offset
                not_before = target - candidate.before_tolerance
                normal_until = target + candidate.normal_tolerance
                not_after = target + candidate.late_tolerance
                identity = (
                    f"{source.code}:odds:{ref.external_id}:{market.external_id}:"
                    f"{candidate.name}:{target.isoformat()}"
                )
                status, reason = self._window_status(
                    at, not_before, not_after, identity
                )
                items.append(
                    PlannedWork(
                        purpose=CaptureWorkItem.Purpose.ODDS_CAPTURE,
                        status=status,
                        source=source,
                        match=match,
                        market=market,
                        external_id=ref.external_id,
                        logical_identity=identity,
                        intended_window=candidate.name,
                        target_at=target,
                        not_before=not_before,
                        normal_until=normal_until,
                        not_after=not_after,
                        priority=(
                            1,
                            not_after,
                            *base_priority,
                            index,
                        ),
                        priority_reason=(
                            "expiring due window; broad competition/day stratum; "
                            "fewer fulfilled windows; freshness; kickoff; stable id"
                        ),
                        reason=reason,
                        estimated_min_cost=1 if status == "PLANNED" else 0,
                        estimated_max_cost=(
                            self.config.worst_operation_cost
                            if status == "PLANNED"
                            else 0
                        ),
                        params={"fixture": ref.external_id, "bet": market.external_id},
                    )
                )
        return items

    @staticmethod
    def _refs(source, matches):
        match_ids = [match.pk for match in matches]
        return {
            ref.match_id: ref
            for ref in MatchSourceRef.objects.filter(
                source=source,
                match_id__in=match_ids,
                reconciliation_status=ReconciliationStatus.RESOLVED,
                match__isnull=False,
            )
        }

    @staticmethod
    def _identity_status(identity):
        work = CaptureWorkItem.objects.filter(logical_identity=identity)
        if work.filter(status__in=FULFILLED_STATUSES).exists():
            return (
                CaptureWorkItem.Status.ALREADY_FULFILLED,
                "logical intended work already fulfilled",
            )
        if work.filter(actual_attempts__gt=0).exists():
            return (
                CaptureWorkItem.Status.PROVIDER_BACKOFF,
                "bounded execution already attempted for this logical identity",
            )
        return CaptureWorkItem.Status.PLANNED, "due and eligible"

    def _window_status(self, at, not_before, not_after, identity):
        identity_status, reason = self._identity_status(identity)
        if identity_status != CaptureWorkItem.Status.PLANNED:
            return identity_status, reason
        if at < not_before:
            return CaptureWorkItem.Status.NOT_DUE, "window has not opened"
        if at > not_after:
            return CaptureWorkItem.Status.MISSED_WINDOW, "window tolerance expired"
        return CaptureWorkItem.Status.PLANNED, "window is due"

    @staticmethod
    def _ineligible_item(source, match, status, reason, priority):
        return PlannedWork(
            purpose=CaptureWorkItem.Purpose.ODDS_CAPTURE,
            status=status,
            source=source,
            match=match,
            logical_identity=f"{source.code}:odds-ineligible:{match.pk}:{status}",
            priority=priority,
            priority_reason="explicit eligibility evidence",
            reason=reason,
        )

    def _admit(self, items, quota, *, allow_bootstrap):
        projected = quota.remaining
        total_allowed = self.config.max_provider_attempts
        if quota.basis == "BOUNDED_BOOTSTRAP":
            total_allowed = min(total_allowed, self.config.bootstrap_max_attempts)
        for item in items:
            if item.status != CaptureWorkItem.Status.PLANNED:
                continue
            mandatory = item.purpose != CaptureWorkItem.Purpose.ODDS_CAPTURE
            if (
                quota.basis == "BOUNDED_BOOTSTRAP"
                and not mandatory
                and not allow_bootstrap
            ):
                item.status = CaptureWorkItem.Status.QUOTA_RESERVE
                item.reason = "optional odds bootstrap requires explicit opt-in"
                item.estimated_min_cost = 0
                item.estimated_max_cost = 0
                continue
            reserve = 0 if mandatory else self.config.mandatory_reserve
            if quota.basis == "BOUNDED_BOOTSTRAP" and allow_bootstrap:
                reserve = 0
            if quota.basis == "BOUNDED_BOOTSTRAP" and (mandatory or allow_bootstrap):
                item.estimated_max_cost = min(
                    item.estimated_max_cost, self.config.bootstrap_max_attempts
                )
            if projected <= reserve:
                item.status = CaptureWorkItem.Status.QUOTA_RESERVE
                item.reason = "conservative remaining is at mandatory reserve"
                item.estimated_min_cost = 0
                item.estimated_max_cost = 0
                continue
            if item.estimated_max_cost > projected - reserve:
                item.status = CaptureWorkItem.Status.INSUFFICIENT_WORST_CASE_BUDGET
                item.reason = "worst-case bounded operation does not fit"
                item.estimated_min_cost = 0
                item.estimated_max_cost = 0
                continue
            if item.estimated_max_cost > total_allowed:
                item.status = CaptureWorkItem.Status.INSUFFICIENT_WORST_CASE_BUDGET
                item.reason = "run attempt bound cannot admit operation worst case"
                item.estimated_min_cost = 0
                item.estimated_max_cost = 0
                continue
            projected -= item.estimated_max_cost
            total_allowed -= item.estimated_max_cost
