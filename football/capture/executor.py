from datetime import datetime
from types import SimpleNamespace

from django.utils import timezone

from football.api_football import (
    APIFootballClient,
    APIFootballError,
    APIFootballOperationBudgetError,
    APIFootballPaginationError,
    APIFootballQuotaReserveError,
    APIFootballRateLimitError,
)
from football.models import (
    CaptureRun,
    CaptureWorkItem,
    CompetitionSourceRef,
    OddsObservation,
    OddsSnapshot,
    ReconciliationStatus,
    Source,
)
from football.sync import FINISHED_STATUSES, sync_fixture_payloads, sync_odds_payloads

from .contracts import CaptureResult
from .locks import capture_single_flight
from .planner import (
    PRE_MATCH_STATUSES,
    TERMINAL_NO_OUTCOME_STATUSES,
    CapturePlanner,
    quota_state,
)


def _sanitize(value, limit=500):
    return " ".join(str(value or "").split())[:limit]


def _quota_dict(client, fallback):
    observed_at = getattr(client, "quota_observed_at", None)
    remaining = getattr(client, "daily_remaining", None)
    if remaining is None:
        remaining = max(0, fallback.remaining - getattr(client, "calls", 0))
        basis = fallback.basis
    else:
        attempts_after_header = max(
            0,
            getattr(client, "calls", 0)
            - getattr(client, "quota_observed_calls", getattr(client, "calls", 0)),
        )
        remaining = max(0, remaining - attempts_after_header)
        basis = "HEADER_CURRENT_UTC_EPOCH"
    return {
        "basis": basis,
        "limit": getattr(client, "daily_limit", None) or fallback.limit,
        "remaining": remaining,
        "observed_at": observed_at.isoformat() if observed_at else None,
    }


class CaptureExecutor:
    def __init__(self, *, client_factory=APIFootballClient):
        self.client_factory = client_factory

    def execute(self, plan, *, trigger):
        with capture_single_flight() as acquired:
            if not acquired:
                return self._concurrent_result(plan, trigger)
            self._revalidate_under_lock(plan)
            return self._execute_locked(plan, trigger)

    @staticmethod
    def _revalidate_under_lock(plan):
        runtime_now = timezone.now()
        plan.quota = quota_state(runtime_now, plan.config)
        planner = CapturePlanner(config=plan.config)
        for item in plan.items:
            if item.status != CaptureWorkItem.Status.PLANNED:
                continue
            if item.match is not None:
                planned_kickoff = item.match.kickoff
                item.match.refresh_from_db()
                if (
                    item.purpose == CaptureWorkItem.Purpose.RESULT_REFRESH
                    and item.match.outcome
                ):
                    item.status = CaptureWorkItem.Status.ALREADY_FULFILLED
                    item.reason = "canonical outcome was resolved after planning"
                    item.estimated_min_cost = 0
                    item.estimated_max_cost = 0
                    continue
                if (
                    item.purpose == CaptureWorkItem.Purpose.RESULT_REFRESH
                    and item.match.status_short
                    in FINISHED_STATUSES | TERMINAL_NO_OUTCOME_STATUSES
                ):
                    item.status = CaptureWorkItem.Status.STATUS_INELIGIBLE
                    item.reason = "terminal fixture has no canonical outcome"
                    item.estimated_min_cost = 0
                    item.estimated_max_cost = 0
                    continue
                if item.purpose == CaptureWorkItem.Purpose.ODDS_CAPTURE:
                    if item.match.kickoff != planned_kickoff:
                        item.status = CaptureWorkItem.Status.NOT_DUE
                        item.reason = "kickoff changed after planning; current windows must replan"
                        item.estimated_min_cost = 0
                        item.estimated_max_cost = 0
                        continue
                    if item.match.status_short not in PRE_MATCH_STATUSES:
                        item.status = CaptureWorkItem.Status.STATUS_INELIGIBLE
                        item.reason = "match left pre-match status after planning"
                        item.estimated_min_cost = 0
                        item.estimated_max_cost = 0
                        continue
            if item.not_before and runtime_now < item.not_before:
                item.status = CaptureWorkItem.Status.NOT_DUE
                item.reason = "work is not due at actual executor time"
                item.estimated_min_cost = 0
                item.estimated_max_cost = 0
                continue
            if item.not_after and runtime_now > item.not_after:
                item.status = CaptureWorkItem.Status.MISSED_WINDOW
                item.reason = "window expired before actual executor time"
                item.estimated_min_cost = 0
                item.estimated_max_cost = 0
                continue
            status, reason = planner._identity_status(item.logical_identity)
            if status != CaptureWorkItem.Status.PLANNED:
                item.status = status
                item.reason = reason
                item.estimated_min_cost = 0
                item.estimated_max_cost = 0
                continue
            item.estimated_min_cost = 1
            item.estimated_max_cost = plan.config.worst_operation_cost
        planner._admit(plan.items, plan.quota, allow_bootstrap=plan.allow_bootstrap)

    @staticmethod
    def _new_run(plan, trigger):
        return CaptureRun.objects.create(
            trigger=trigger,
            status=CaptureRun.Status.RUNNING,
            planning_at=plan.planning_at,
            started_at=timezone.now(),
            config_snapshot=plan.config.snapshot(),
            quota_basis=plan.quota.basis,
            quota_limit=plan.quota.limit,
            quota_remaining_before=plan.quota.remaining,
            quota_observed_at=plan.quota.observed_at,
            mandatory_reserve=plan.config.mandatory_reserve,
        )

    def _concurrent_result(self, plan, trigger):
        run = self._new_run(plan, trigger)
        run.status = CaptureRun.Status.CONCURRENT_EXECUTOR
        run.completed_at = timezone.now()
        run.skips = 1
        run.summary = {
            "reason": CaptureWorkItem.Status.CONCURRENT_EXECUTOR,
            "plan": plan.as_dict(),
        }
        run.save(
            update_fields=["status", "completed_at", "skips", "summary", "modified"]
        )
        CaptureWorkItem.objects.create(
            run=run,
            purpose=CaptureWorkItem.Purpose.ODDS_CAPTURE,
            status=CaptureWorkItem.Status.CONCURRENT_EXECUTOR,
            source=(
                plan.items[0].source
                if plan.items
                else Source.objects.get(code="api_football")
            ),
            logical_identity=f"concurrent:{run.pk}",
            reason="another executor holds the FS-005 advisory lock",
            completed_at=run.completed_at,
        )
        return CaptureResult(
            run_id=run.pk,
            status=run.status,
            planning_at=plan.planning_at,
            quota_before=plan.quota.as_dict(),
            quota_after=plan.quota.as_dict(),
            skipped_work=[{"status": CaptureWorkItem.Status.CONCURRENT_EXECUTOR}],
            plan=plan.as_dict(),
        )

    def _execute_locked(self, plan, trigger):
        run = self._new_run(plan, trigger)
        work_rows = []
        for rank, item in enumerate(plan.items, start=1):
            work_rows.append(
                CaptureWorkItem.objects.create(
                    run=run,
                    purpose=item.purpose,
                    status=item.status,
                    source=item.source,
                    match=item.match,
                    market=item.market,
                    logical_identity=item.logical_identity,
                    intended_window=item.intended_window,
                    target_at=item.target_at,
                    not_before=item.not_before,
                    not_after=item.not_after,
                    priority=rank,
                    reason=item.reason or item.priority_reason,
                    estimated_min_cost=item.estimated_min_cost,
                    estimated_max_cost=item.estimated_max_cost,
                    quota_before=plan.quota.as_dict(),
                    completed_at=(
                        None
                        if item.status == CaptureWorkItem.Status.PLANNED
                        else timezone.now()
                    ),
                )
            )
        result = CaptureResult(
            run_id=run.pk,
            status=CaptureRun.Status.RUNNING,
            planning_at=plan.planning_at,
            quota_before=plan.quota.as_dict(),
            quota_after=plan.quota.as_dict(),
            plan=plan.as_dict(),
        )
        for item, row in zip(plan.items, work_rows, strict=True):
            if item.status != CaptureWorkItem.Status.PLANNED:
                result.skipped_work.append(item.as_dict())
        if not plan.executable:
            return self._finish(run, result, None)
        try:
            client = self.client_factory(
                max_pages=plan.config.max_operation_pages,
                max_retries=plan.config.max_retries,
                daily_reserve=0,
            )
        except Exception as error:
            for item, row in zip(plan.items, work_rows, strict=True):
                if item.status != CaptureWorkItem.Status.PLANNED:
                    continue
                self._fail_row(row, CaptureWorkItem.Status.FAILED_PROVIDER, error)
                row.completed_at = timezone.now()
                row.save()
                result.failed_work.append(item.as_dict() | {"status": row.status})
            return self._finish(run, result, None)
        halted_status = None
        for item, row in zip(plan.items, work_rows, strict=True):
            if item.status != CaptureWorkItem.Status.PLANNED:
                continue
            if halted_status is not None:
                row.status = halted_status
                row.reason = "prior bounded execution stopped this run"
                row.completed_at = timezone.now()
                row.save()
                result.skipped_work.append(item.as_dict() | {"status": row.status})
                continue
            self._execute_item(plan, client, item, row, result)
            if row.status not in {
                CaptureWorkItem.Status.SUCCESS,
                CaptureWorkItem.Status.SUCCESS_EMPTY,
                CaptureWorkItem.Status.LATE_CAPTURE,
            }:
                halted_status = (
                    CaptureWorkItem.Status.PROVIDER_BACKOFF
                    if row.status
                    in {
                        CaptureWorkItem.Status.FAILED_PROVIDER,
                        CaptureWorkItem.Status.PARTIAL_PAGINATION,
                        CaptureWorkItem.Status.PROVIDER_BACKOFF,
                    }
                    else row.status
                )
        return self._finish(run, result, client)

    def _execute_item(self, plan, client, item, row, result):
        calls_before = client.calls
        pages_before = getattr(client, "pages", 0)
        retries_before = getattr(client, "retries", 0)
        row.executed_at = timezone.now()
        row.quota_before = _quota_dict(client, plan.quota)

        def guard(active_client):
            if (
                plan.quota.basis == "BOUNDED_BOOTSTRAP"
                and item.purpose == CaptureWorkItem.Purpose.ODDS_CAPTURE
                and not plan.allow_bootstrap
            ):
                raise APIFootballQuotaReserveError(
                    "Optional odds bootstrap requires explicit opt-in."
                )
            run_attempt_limit = plan.config.max_provider_attempts
            if plan.quota.basis == "BOUNDED_BOOTSTRAP":
                run_attempt_limit = min(
                    run_attempt_limit, plan.config.bootstrap_max_attempts
                )
            if active_client.calls >= run_attempt_limit:
                raise APIFootballOperationBudgetError(
                    "Capture run reached its configured provider-attempt bound."
                )
            remaining = active_client.daily_remaining
            if remaining is None:
                remaining = max(0, plan.quota.remaining - active_client.calls)
            reserve = (
                plan.config.mandatory_reserve
                if item.purpose == CaptureWorkItem.Purpose.ODDS_CAPTURE
                else 0
            )
            if plan.quota.basis == "BOUNDED_BOOTSTRAP" and (
                item.estimated_max_cost <= plan.config.bootstrap_max_attempts
            ):
                reserve = 0
            if remaining - 1 < reserve:
                raise APIFootballQuotaReserveError(
                    "Provider attempt would cross the mandatory quota reserve."
                )

        client.attempt_guard = guard
        try:
            effects, empty = self._perform(client, item)
            is_late = item.normal_until and row.executed_at > item.normal_until
            row.status = (
                CaptureWorkItem.Status.LATE_CAPTURE
                if is_late
                else (
                    CaptureWorkItem.Status.SUCCESS_EMPTY
                    if empty
                    else CaptureWorkItem.Status.SUCCESS
                )
            )
            row.reason = "bounded provider execution completed"
            row.observations_created = effects["observations_created"]
            row.snapshots_changed = effects["snapshots_changed"]
            row.fixtures_changed = effects["fixtures_changed"]
            row.matches_resolved = effects["matches_resolved"]
            result.observations_created += row.observations_created
            result.snapshots_changed += row.snapshots_changed
            result.fixtures_changed += row.fixtures_changed
            result.matches_resolved += row.matches_resolved
            result.completed_work.append(
                item.as_dict() | {"status": row.status, "effects": effects}
            )
        except APIFootballRateLimitError as error:
            self._fail_row(row, CaptureWorkItem.Status.PROVIDER_BACKOFF, error)
            result.failed_work.append(item.as_dict() | {"status": row.status})
        except (APIFootballPaginationError, APIFootballOperationBudgetError) as error:
            attempted = client.calls > calls_before
            status = (
                CaptureWorkItem.Status.PARTIAL_PAGINATION
                if getattr(client, "pages", 0) > pages_before
                else (
                    CaptureWorkItem.Status.PROVIDER_BACKOFF
                    if attempted
                    else CaptureWorkItem.Status.INSUFFICIENT_WORST_CASE_BUDGET
                )
            )
            self._fail_row(row, status, error)
            target = result.failed_work if attempted else result.skipped_work
            target.append(item.as_dict() | {"status": row.status})
        except APIFootballQuotaReserveError as error:
            attempted = client.calls > calls_before
            status = (
                CaptureWorkItem.Status.PARTIAL_PAGINATION
                if getattr(client, "pages", 0) > pages_before
                else (
                    CaptureWorkItem.Status.PROVIDER_BACKOFF
                    if attempted
                    else CaptureWorkItem.Status.QUOTA_RESERVE
                )
            )
            self._fail_row(row, status, error)
            target = result.failed_work if attempted else result.skipped_work
            target.append(item.as_dict() | {"status": row.status})
        except APIFootballError as error:
            self._fail_row(row, CaptureWorkItem.Status.FAILED_PROVIDER, error)
            result.failed_work.append(item.as_dict() | {"status": row.status})
        except Exception as error:  # Async/operator audit must not lose local failures.
            self._fail_row(row, CaptureWorkItem.Status.FAILED_PROVIDER, error)
            result.failed_work.append(item.as_dict() | {"status": row.status})
        finally:
            row.actual_attempts = client.calls - calls_before
            row.actual_pages = getattr(client, "pages", 0) - pages_before
            row.actual_retries = max(
                0,
                getattr(client, "retries", 0) - retries_before,
            )
            row.completed_at = timezone.now()
            row.quota_after = _quota_dict(client, plan.quota)
            if item.target_at:
                row.lateness_seconds = int(
                    (row.executed_at - item.target_at).total_seconds()
                )
            row.save()

    @staticmethod
    def _fail_row(row, status, error):
        row.status = status
        row.reason = _sanitize(error, 120)
        row.error_class = error.__class__.__name__[:120]
        row.error_message = _sanitize(error)

    @staticmethod
    def _perform(client, item):
        if item.purpose == CaptureWorkItem.Purpose.ODDS_CAPTURE:
            observations_before = OddsObservation.objects.filter(
                match=item.match, source=item.source, market=item.market
            ).count()
            snapshots_before = {
                row.bookmaker_id: (
                    row.home,
                    row.draw,
                    row.away,
                    row.provider_updated_at,
                )
                for row in OddsSnapshot.objects.filter(
                    match=item.match, source=item.source, market=item.market
                )
            }
            payloads = client.get_all("odds", item.params)
            sync_odds_payloads(payloads, {item.external_id: item.match}, item.market)
            observations_after = OddsObservation.objects.filter(
                match=item.match, source=item.source, market=item.market
            ).count()
            snapshots_after = {
                row.bookmaker_id: (
                    row.home,
                    row.draw,
                    row.away,
                    row.provider_updated_at,
                )
                for row in OddsSnapshot.objects.filter(
                    match=item.match, source=item.source, market=item.market
                )
            }
            created = observations_after - observations_before
            bookmaker_set_changed = set(snapshots_before) != set(snapshots_after)
            price_changed = any(
                bookmaker_id in snapshots_before
                and snapshots_before[bookmaker_id][:3] != value[:3]
                for bookmaker_id, value in snapshots_after.items()
            )
            return (
                {
                    "observations_created": created,
                    "snapshots_changed": sum(
                        snapshots_before.get(bookmaker_id) != value
                        for bookmaker_id, value in snapshots_after.items()
                    ),
                    "fixtures_changed": 0,
                    "matches_resolved": 0,
                    "first_observation": observations_before == 0 and created > 0,
                    "price_changed": price_changed,
                    "bookmaker_set_changed": bookmaker_set_changed,
                    "identical_response": (
                        observations_before > 0
                        and created > 0
                        and not price_changed
                        and not bookmaker_set_changed
                    ),
                },
                not payloads or created == 0,
            )
        payloads = client.get_all("fixtures", item.params)
        if item.purpose == CaptureWorkItem.Purpose.RESULT_REFRESH:
            api_ref = CompetitionSourceRef.objects.get(
                source=item.source,
                competition=item.match.season.competition,
                reconciliation_status=ReconciliationStatus.RESOLVED,
            )
            competitions = {api_ref.external_id: item.match.season.competition}
            before = (
                item.match.kickoff,
                item.match.status_short,
                item.match.outcome,
            )
            sync_fixture_payloads(payloads, competitions)
            item.match.refresh_from_db()
            after = (
                item.match.kickoff,
                item.match.status_short,
                item.match.outcome,
            )
            return (
                {
                    "observations_created": 0,
                    "snapshots_changed": 0,
                    "fixtures_changed": int(before != after),
                    "matches_resolved": int(not before[2] and bool(after[2])),
                },
                not payloads or before == after,
            )
        refs = CompetitionSourceRef.objects.filter(
            source=item.source,
            competition__enabled=True,
            reconciliation_status=ReconciliationStatus.RESOLVED,
        ).select_related("competition")
        competitions = {ref.external_id: ref.competition for ref in refs}
        stats, _ = sync_fixture_payloads(payloads, competitions)
        changed = stats.created + stats.updated
        return (
            {
                "observations_created": 0,
                "snapshots_changed": 0,
                "fixtures_changed": changed,
                "matches_resolved": 0,
            },
            not payloads or changed == 0,
        )

    @staticmethod
    def _finish(run, result, client):
        if client is not None:
            result.provider_attempts = client.calls
            result.provider_pages = getattr(client, "pages", 0)
            result.provider_retries = getattr(client, "retries", 0)
            result.quota_after = _quota_dict(
                client,
                SimpleNamespace(
                    basis=result.quota_before["basis"],
                    limit=result.quota_before["limit"],
                    remaining=result.quota_before["remaining"],
                ),
            )
        if result.failed_work and result.completed_work:
            status = CaptureRun.Status.PARTIAL
        elif result.failed_work:
            status = CaptureRun.Status.FAILED
        elif result.completed_work:
            status = CaptureRun.Status.SUCCESS
        else:
            status = CaptureRun.Status.NO_WORK
        result.status = status
        run.status = status
        run.completed_at = timezone.now()
        run.provider_attempts = result.provider_attempts
        run.provider_pages = result.provider_pages
        run.provider_retries = result.provider_retries
        run.observations_created = result.observations_created
        run.snapshots_changed = result.snapshots_changed
        run.fixtures_changed = result.fixtures_changed
        run.matches_resolved = result.matches_resolved
        run.skips = len(result.skipped_work)
        run.failures = len(result.failed_work)
        run.quota_basis = result.quota_after.get("basis") or run.quota_basis
        run.quota_limit = result.quota_after.get("limit")
        run.quota_remaining_after = result.quota_after.get("remaining")
        observed_at = result.quota_after.get("observed_at")
        run.quota_observed_at = (
            datetime.fromisoformat(observed_at) if observed_at else None
        )
        if result.failed_work:
            failed_row = run.work_items.exclude(error_class="").first()
            if failed_row:
                run.error_class = failed_row.error_class
                run.error_message = failed_row.error_message
        result.plan["metrics"] = CaptureExecutor._metrics(run, result)
        run.summary = result.as_dict()
        run.save()
        return result

    @staticmethod
    def _metrics(run, result):
        completed_odds = [
            work
            for work in result.completed_work
            if work["purpose"] == CaptureWorkItem.Purpose.ODDS_CAPTURE
        ]
        effect_count = max(1, len(completed_odds))
        due_odds = sum(
            item["purpose"] == CaptureWorkItem.Purpose.ODDS_CAPTURE
            and item["status"] == CaptureWorkItem.Status.PLANNED
            for item in result.plan.get("items", [])
        )
        lateness = list(
            run.work_items.exclude(lateness_seconds__isnull=True).values_list(
                "lateness_seconds", flat=True
            )
        )
        statuses = {}
        for status in run.work_items.values_list("status", flat=True):
            statuses[status] = statuses.get(status, 0) + 1
        return {
            "quota": {
                "attempts": result.provider_attempts,
                "pages": result.provider_pages,
                "retries": result.provider_retries,
                "remaining": result.quota_after.get("remaining"),
                "reserve": run.mandatory_reserve,
            },
            "coverage": {
                "eligible_fixtures": result.plan.get("eligible", 0),
                "due_work": result.plan.get("due", 0),
                "completed_windows": len(completed_odds),
                "observations_created": result.observations_created,
            },
            "freshness": {
                "lateness_seconds": lateness,
                "maximum_lateness_seconds": max(lateness) if lateness else None,
            },
            "reliability": {"statuses": statuses},
            "data_value": {
                "first_observation_yield": sum(
                    work["effects"].get("first_observation", False)
                    for work in completed_odds
                )
                / effect_count,
                "price_change_yield": sum(
                    work["effects"].get("price_changed", False)
                    for work in completed_odds
                )
                / effect_count,
                "bookmaker_set_change_yield": sum(
                    work["effects"].get("bookmaker_set_changed", False)
                    for work in completed_odds
                )
                / effect_count,
                "identical_response_rate": sum(
                    work["effects"].get("identical_response", False)
                    for work in completed_odds
                )
                / effect_count,
                "window_completion": len(completed_odds) / max(1, due_odds),
            },
        }
