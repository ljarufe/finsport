from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, Max, Q

from football.capture_eligibility import (
    match_winner_market,
    odds_capture_prerequisite,
)
from football.models import (
    CapitalPosition,
    CaptureWorkItem,
    Match,
    MatchSourceRef,
    ReconciliationStatus,
    Source,
)
from football.providers.api_football import (
    FIXTURE_TIMEZONE,
    fixture_date_params,
    fixture_id_params,
)
from football.quota import dynamic_reserve
from football.quota import quota_state as shared_quota_state
from football.sync import API_FOOTBALL_CODE, FINISHED_STATUSES

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
    state = shared_quota_state(at, config)
    return QuotaState(**state)


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
        reserve = dynamic_reserve(at, self.config)
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
        self._admit(items, quota, reserve, allow_bootstrap=allow_bootstrap)
        return CapturePlan(
            at,
            self.config,
            quota,
            items,
            allow_bootstrap,
            reserve=reserve,
        )

    @staticmethod
    def _market(source):
        return match_winner_market(source)

    def _result_items(self, at, source, match_id):
        if not self.config.result_refresh_enabled:
            return []
        due_before = at - self.config.result_delay
        queryset = (
            Match.objects.filter(
                season__competition__enabled=True,
                kickoff__lte=due_before,
                outcome="",
            )
            .exclude(capital_positions__status=CapitalPosition.Status.OPEN)
            .select_related("season__competition")
        )
        if match_id is not None:
            queryset = queryset.filter(pk=match_id)
        refs = self._refs(source, queryset)
        slot = _slot_start(at, self.config.result_cadence)
        items = []
        local_today = at.astimezone(ZoneInfo(FIXTURE_TIMEZONE)).date()
        recent_dates = {local_today - timedelta(days=1), local_today}
        eligible = [
            match
            for match in queryset.order_by("kickoff", "id")
            if refs.get(match.pk) is not None
            and match.status_short
            not in FINISHED_STATUSES | TERMINAL_NO_OUTCOME_STATUSES
            and match.kickoff.astimezone(ZoneInfo(FIXTURE_TIMEZONE)).date()
            in recent_dates
        ]
        by_date = {}
        for match in eligible:
            day = match.kickoff.astimezone(ZoneInfo(FIXTURE_TIMEZONE)).date()
            by_date.setdefault(day, []).append(match)
        for day, batch in sorted(by_date.items()):
            external_ids = tuple(
                dict.fromkeys(refs[match.pk].external_id for match in batch)
            )
            identity = (
                f"{source.code}:nonbet-results:{day.isoformat()}:{slot.isoformat()}"
            )
            status, reason = self._identity_status(identity)
            items.append(
                PlannedWork(
                    purpose=CaptureWorkItem.Purpose.RESULT_REFRESH,
                    status=status,
                    source=source,
                    logical_identity=identity,
                    intended_window="nonbet-result-date",
                    target_at=slot,
                    not_before=slot,
                    priority=(3, batch[0].kickoff, -1, batch[0].pk),
                    priority_reason="surplus-only recent-date non-bet result completion",
                    reason=reason,
                    estimated_min_cost=1 if status == "PLANNED" else 0,
                    estimated_max_cost=1 if status == "PLANNED" else 0,
                    params=fixture_date_params(day, FIXTURE_TIMEZONE),
                    target_external_ids=external_ids,
                )
            )
        return items

    def _discovery_items(self, at, source):
        if not self.config.discovery_enabled:
            return []
        local_date = at.astimezone(ZoneInfo(settings.TIME_ZONE)).date()
        items = []
        for days_ahead in range(self.config.discovery_days_ahead + 1):
            discovery_date = local_date + timedelta(days=days_ahead)
            identity = f"{source.code}:discovery:{discovery_date}"
            status, reason = self._identity_status(identity)
            items.append(
                PlannedWork(
                    purpose=CaptureWorkItem.Purpose.FIXTURE_REFRESH,
                    status=status,
                    source=source,
                    logical_identity=identity,
                    intended_window="fixture-discovery",
                    target_at=at,
                    not_before=at,
                    priority=(0, days_ahead),
                    priority_reason="protected persisted fixture discovery horizon",
                    reason=reason,
                    estimated_min_cost=1 if status == "PLANNED" else 0,
                    estimated_max_cost=1 if status == "PLANNED" else 0,
                    params=fixture_date_params(discovery_date, settings.TIME_ZONE),
                )
            )
        recovery_matches = list(
            Match.objects.filter(
                status_short="PST",
                capital_positions__status=CapitalPosition.Status.OPEN,
            )
            .select_related("season__competition")
            .distinct()
            .order_by("kickoff", "id")
        )
        recovery_refs = self._refs(source, recovery_matches)
        recovery_slot = _slot_start(at, self.config.discovery_cadence)
        for match in recovery_matches:
            ref = recovery_refs.get(match.pk)
            if ref is None:
                continue
            identity = (
                f"{source.code}:fixture-recovery:{ref.external_id}:"
                f"{recovery_slot.isoformat()}"
            )
            status, reason = self._identity_status(identity)
            items.append(
                PlannedWork(
                    purpose=CaptureWorkItem.Purpose.FIXTURE_REFRESH,
                    status=status,
                    source=source,
                    match=match,
                    external_id=ref.external_id,
                    logical_identity=identity,
                    intended_window="pst-fixture-reconciliation",
                    target_at=recovery_slot,
                    not_before=recovery_slot,
                    priority=(0, -1, match.kickoff, match.pk),
                    priority_reason="explicit postponed OPEN fixture reconciliation",
                    reason=reason,
                    estimated_min_cost=1 if status == "PLANNED" else 0,
                    estimated_max_cost=1 if status == "PLANNED" else 0,
                    params=fixture_id_params(ref.external_id),
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
            ref = refs.get(match.pk)
            prerequisite = odds_capture_prerequisite(match, source, ref, market)
            if prerequisite is not None:
                status, reason = prerequisite
                items.append(
                    self._ineligible_item(
                        source,
                        match,
                        status,
                        reason,
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
                            1 if candidate.name == "market-t30m" else 3,
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
                        estimated_max_cost=1 if status == "PLANNED" else 0,
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

    def _admit(self, items, quota, reserve, *, allow_bootstrap):
        reserve = dict(reserve)
        projected = quota.remaining
        total_allowed = self.config.max_provider_attempts
        if quota.basis == "BOUNDED_BOOTSTRAP":
            total_allowed = min(total_allowed, self.config.bootstrap_max_attempts)
        elif quota.basis == "HEADER_STALE_EPOCH":
            # Exactly one physical critical attempt may establish this epoch.
            # A headerless attempt anywhere in the system consumes that allowance.
            projected = 1 if quota.stale_establishing_attempt_available else 0
            total_allowed = min(total_allowed, 1)
        for item in items:
            if item.status != CaptureWorkItem.Status.PLANNED:
                continue
            critical_component = None
            if item.purpose == CaptureWorkItem.Purpose.FIXTURE_REFRESH:
                critical_component = "fixture"
            elif (
                item.purpose == CaptureWorkItem.Purpose.ODDS_CAPTURE
                and item.intended_window == "market-t30m"
            ):
                critical_component = "t30"
            mandatory = critical_component is not None
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
            protected = reserve["total"]
            if critical_component:
                protected = 0
            if quota.basis == "HEADER_STALE_EPOCH" and not mandatory:
                item.status = CaptureWorkItem.Status.QUOTA_RESERVE
                item.reason = "optional work waits for a current provider header"
                item.estimated_min_cost = 0
                item.estimated_max_cost = 0
                continue
            if (
                quota.basis == "HEADER_STALE_EPOCH"
                and critical_component == "t30"
                and reserve["fixture"] > 0
            ):
                item.status = CaptureWorkItem.Status.QUOTA_RESERVE
                item.reason = "fixture discovery has stale-epoch priority"
                item.estimated_min_cost = 0
                item.estimated_max_cost = 0
                continue
            if projected - 1 < protected:
                item.status = CaptureWorkItem.Status.QUOTA_RESERVE
                item.reason = "deferred to protect dynamic critical reserve"
                item.estimated_min_cost = 0
                item.estimated_max_cost = 0
                continue
            if total_allowed < 1:
                item.status = CaptureWorkItem.Status.INSUFFICIENT_WORST_CASE_BUDGET
                item.reason = "finite admitted-call circuit breaker reached"
                item.estimated_min_cost = 0
                item.estimated_max_cost = 0
                continue
            item.estimated_max_cost = 1
            projected -= 1
            total_allowed -= 1
            if critical_component and reserve[critical_component] > 0:
                reserve[critical_component] -= 1
                reserve["total"] -= 1
