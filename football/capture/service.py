from django.utils import timezone

from football.models import CaptureRun

from .contracts import CaptureConfig, CaptureResult
from .executor import CaptureExecutor
from .planner import CapturePlanner


def run_capture(
    *,
    at=None,
    dry_run=False,
    trigger=CaptureRun.Trigger.MANUAL,
    match_id=None,
    purpose=None,
    window=None,
    max_provider_attempts=None,
    allow_bootstrap=False,
    client_factory=None,
):
    """Plan and optionally execute one bounded FS-005 capture run.

    The return value is structured for management commands, Celery, tests/UAT,
    and the future FS-006 orchestrator. Dry-run invokes only the planner and
    never instantiates a provider client or writes capture audit/data rows.
    """
    at = at or timezone.now()
    if timezone.is_naive(at):
        raise ValueError("--at / at must include an explicit timezone offset.")
    config = CaptureConfig.from_settings(max_provider_attempts=max_provider_attempts)
    plan = CapturePlanner(config=config).plan(
        at=at,
        match_id=match_id,
        purpose=purpose,
        window=window,
        allow_bootstrap=allow_bootstrap,
    )
    if dry_run:
        return CaptureResult(
            run_id=None,
            status="DRY_RUN",
            planning_at=at,
            quota_before=plan.quota.as_dict(),
            quota_after=plan.quota.as_dict(),
            skipped_work=[
                item.as_dict() for item in plan.items if item.status != "PLANNED"
            ],
            plan=plan.as_dict(),
        )
    executor_kwargs = {}
    if client_factory is not None:
        executor_kwargs["client_factory"] = client_factory
    return CaptureExecutor(**executor_kwargs).execute(plan, trigger=trigger)
