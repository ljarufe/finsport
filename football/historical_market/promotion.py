from django.utils import timezone

from football.models import MaintenanceRun

from .contracts import PackageConflict

BASELINE_PROMOTION_IDENTITY = "fs015-historical-market-baseline-promoted:v1"


def market_baseline_is_promoted():
    return MaintenanceRun.objects.filter(
        logical_identity=BASELINE_PROMOTION_IDENTITY,
        status=MaintenanceRun.Status.SUCCESS,
    ).exists()


def promote_market_baseline():
    """Create the idempotent marker inside the caller's import transaction."""
    now = timezone.now()
    marker, created = MaintenanceRun.objects.get_or_create(
        logical_identity=BASELINE_PROMOTION_IDENTITY,
        defaults={
            "capability": MaintenanceRun.Capability.HISTORICAL_MARKET_BOOTSTRAP,
            "period_start": timezone.localdate(now),
            "subject_type": "SystemBaseline",
            "status": MaintenanceRun.Status.SUCCESS,
            "attempt_count": 1,
            "started_at": now,
            "last_attempt_at": now,
            "completed_at": now,
            "config_snapshot": {
                "ticket": "FS-015",
                "transition": "SCOPED_PACKAGE_IMPORT_APPLY",
            },
            "summary": {"reason": "FS015_MARKET_BASELINE_PROMOTED"},
        },
    )
    if not created and marker.status != MaintenanceRun.Status.SUCCESS:
        raise PackageConflict("FS015_MARKET_BASELINE_MARKER_CONFLICT")
    return "CREATED" if created else "ALREADY_COMPLETE"
