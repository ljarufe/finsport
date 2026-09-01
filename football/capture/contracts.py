from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings


@dataclass(frozen=True)
class CaptureWindow:
    name: str
    offset: timedelta
    before_tolerance: timedelta
    normal_tolerance: timedelta
    late_tolerance: timedelta

    @classmethod
    def from_mapping(cls, value):
        return cls(
            name=str(value["name"]),
            offset=timedelta(minutes=int(value["offset_minutes"])),
            before_tolerance=timedelta(
                minutes=int(value.get("before_tolerance_minutes", 0))
            ),
            normal_tolerance=timedelta(
                minutes=int(value.get("normal_tolerance_minutes", 0))
            ),
            late_tolerance=timedelta(
                minutes=int(value.get("late_tolerance_minutes", 0))
            ),
        )

    def snapshot(self):
        return {
            "name": self.name,
            "offset_minutes": int(self.offset.total_seconds() / 60),
            "before_tolerance_minutes": int(self.before_tolerance.total_seconds() / 60),
            "normal_tolerance_minutes": int(self.normal_tolerance.total_seconds() / 60),
            "late_tolerance_minutes": int(self.late_tolerance.total_seconds() / 60),
        }


@dataclass(frozen=True)
class CaptureConfig:
    windows: tuple[CaptureWindow, ...]
    horizon: timedelta
    mandatory_reserve: int
    max_operation_pages: int
    max_provider_attempts: int
    max_retries: int
    bootstrap_max_attempts: int
    discovery_enabled: bool
    discovery_cadence: timedelta
    discovery_days_ahead: int
    result_refresh_enabled: bool
    result_delay: timedelta
    result_cadence: timedelta

    @classmethod
    def from_settings(cls, *, max_provider_attempts=None):
        raw_windows = settings.FOOTBALL_CAPTURE_WINDOWS
        windows = tuple(CaptureWindow.from_mapping(value) for value in raw_windows)
        names = [window.name for window in windows]
        normalized_names = {name.casefold() for name in names}
        if len(windows) > 3 or len(names) != len(normalized_names):
            raise ValueError("Capture windows require at most three unique names.")
        extras = normalized_names - {"early", "middle"}
        if not {"early", "middle"}.issubset(normalized_names) or any(
            not name.startswith("near") for name in extras
        ):
            raise ValueError(
                "Capture windows require early + middle and at most one near candidate."
            )
        if any(
            window.offset.total_seconds() < 0
            or window.before_tolerance.total_seconds() < 0
            or window.normal_tolerance.total_seconds() < 0
            or window.late_tolerance < window.normal_tolerance
            for window in windows
        ):
            raise ValueError(
                "Window offsets/tolerances must be non-negative and late tolerance "
                "must include normal tolerance."
            )
        configured_max = settings.FOOTBALL_CAPTURE_MAX_PROVIDER_ATTEMPTS
        if max_provider_attempts is not None:
            configured_max = min(configured_max, max_provider_attempts)
        positive_values = (
            settings.FOOTBALL_CAPTURE_HORIZON_HOURS,
            settings.FOOTBALL_CAPTURE_MAX_OPERATION_PAGES,
            configured_max,
            settings.FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS,
            settings.FOOTBALL_CAPTURE_DISCOVERY_CADENCE_MINUTES,
            settings.FOOTBALL_CAPTURE_RESULT_CADENCE_MINUTES,
        )
        if any(value < 1 for value in positive_values):
            raise ValueError("Capture horizons, cadences, and bounds must be positive.")
        if any(
            value < 0
            for value in (
                settings.FOOTBALL_CAPTURE_MANDATORY_RESERVE,
                settings.FOOTBALL_CAPTURE_DISCOVERY_DAYS_AHEAD,
                settings.FOOTBALL_CAPTURE_RESULT_DELAY_MINUTES,
            )
        ):
            raise ValueError(
                "Capture reserve, discovery horizon, and result delay cannot be negative."
            )
        return cls(
            windows=windows,
            horizon=timedelta(hours=settings.FOOTBALL_CAPTURE_HORIZON_HOURS),
            mandatory_reserve=settings.FOOTBALL_CAPTURE_MANDATORY_RESERVE,
            max_operation_pages=settings.FOOTBALL_CAPTURE_MAX_OPERATION_PAGES,
            max_provider_attempts=configured_max,
            max_retries=settings.API_FOOTBALL_MAX_RETRIES,
            bootstrap_max_attempts=settings.FOOTBALL_CAPTURE_BOOTSTRAP_MAX_ATTEMPTS,
            discovery_enabled=settings.FOOTBALL_CAPTURE_DISCOVERY_ENABLED,
            discovery_cadence=timedelta(
                minutes=settings.FOOTBALL_CAPTURE_DISCOVERY_CADENCE_MINUTES
            ),
            discovery_days_ahead=settings.FOOTBALL_CAPTURE_DISCOVERY_DAYS_AHEAD,
            result_refresh_enabled=settings.FOOTBALL_CAPTURE_RESULT_REFRESH_ENABLED,
            result_delay=timedelta(
                minutes=settings.FOOTBALL_CAPTURE_RESULT_DELAY_MINUTES
            ),
            result_cadence=timedelta(
                minutes=settings.FOOTBALL_CAPTURE_RESULT_CADENCE_MINUTES
            ),
        )

    @property
    def worst_operation_cost(self):
        return min(
            self.max_provider_attempts,
            self.max_operation_pages * (self.max_retries + 1),
        )

    def snapshot(self):
        return {
            "windows": [window.snapshot() for window in self.windows],
            "horizon_hours": int(self.horizon.total_seconds() / 3600),
            "mandatory_reserve": self.mandatory_reserve,
            "max_operation_pages": self.max_operation_pages,
            "max_provider_attempts": self.max_provider_attempts,
            "max_retries": self.max_retries,
            "bootstrap_max_attempts": self.bootstrap_max_attempts,
            "discovery_enabled": self.discovery_enabled,
            "discovery_cadence_minutes": int(
                self.discovery_cadence.total_seconds() / 60
            ),
            "discovery_days_ahead": self.discovery_days_ahead,
            "result_refresh_enabled": self.result_refresh_enabled,
            "result_delay_minutes": int(self.result_delay.total_seconds() / 60),
            "result_cadence_minutes": int(self.result_cadence.total_seconds() / 60),
        }


@dataclass(frozen=True)
class QuotaState:
    basis: str
    limit: int | None
    remaining: int
    observed_at: datetime | None
    freshness_seconds: int | None

    def as_dict(self):
        return {
            "basis": self.basis,
            "limit": self.limit,
            "remaining": self.remaining,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "freshness_seconds": self.freshness_seconds,
        }


@dataclass
class PlannedWork:
    purpose: str
    status: str
    source: Any
    match: Any = None
    market: Any = None
    external_id: str = ""
    logical_identity: str = ""
    intended_window: str = ""
    target_at: datetime | None = None
    not_before: datetime | None = None
    normal_until: datetime | None = None
    not_after: datetime | None = None
    priority: tuple = field(default_factory=tuple)
    priority_reason: str = ""
    reason: str = ""
    estimated_min_cost: int = 0
    estimated_max_cost: int = 0
    params: dict = field(default_factory=dict)

    def as_dict(self):
        priority = [
            value.isoformat() if isinstance(value, datetime) else value
            for value in self.priority
        ]
        return {
            "purpose": self.purpose,
            "status": self.status,
            "match_id": self.match.pk if self.match else None,
            "competition_id": (
                self.match.season.competition_id if self.match else None
            ),
            "external_id": self.external_id or None,
            "market_id": self.market.pk if self.market else None,
            "logical_identity": self.logical_identity,
            "intended_window": self.intended_window,
            "target_at": self.target_at.isoformat() if self.target_at else None,
            "not_before": self.not_before.isoformat() if self.not_before else None,
            "not_after": self.not_after.isoformat() if self.not_after else None,
            "priority": priority,
            "priority_reason": self.priority_reason,
            "reason": self.reason,
            "estimated_min_cost": self.estimated_min_cost,
            "estimated_max_cost": self.estimated_max_cost,
        }


@dataclass
class CapturePlan:
    planning_at: datetime
    config: CaptureConfig
    quota: QuotaState
    items: list[PlannedWork]
    allow_bootstrap: bool = False

    @property
    def executable(self):
        return [item for item in self.items if item.status == "PLANNED"]

    def as_dict(self):
        return {
            "planning_at": self.planning_at.isoformat(),
            "quota": self.quota.as_dict(),
            "reserve": self.config.mandatory_reserve,
            "eligible": len(
                {item.match.pk for item in self.items if item.match is not None}
            ),
            "due": len(self.executable),
            "estimated_min_cost": sum(
                item.estimated_min_cost for item in self.executable
            ),
            "estimated_max_cost": sum(
                item.estimated_max_cost for item in self.executable
            ),
            "items": [item.as_dict() for item in self.items],
        }


@dataclass
class CaptureResult:
    run_id: int | None
    status: str
    planning_at: datetime
    quota_before: dict
    quota_after: dict
    observations_created: int = 0
    snapshots_changed: int = 0
    fixtures_changed: int = 0
    matches_resolved: int = 0
    provider_attempts: int = 0
    provider_pages: int = 0
    provider_retries: int = 0
    skipped_work: list[dict] = field(default_factory=list)
    failed_work: list[dict] = field(default_factory=list)
    completed_work: list[dict] = field(default_factory=list)
    secondary: dict = field(default_factory=dict)
    plan: dict = field(default_factory=dict)
    operational_cause: dict = field(default_factory=dict, repr=False)

    def as_dict(self):
        return {
            "run_id": self.run_id,
            "status": self.status,
            "planning_at": self.planning_at.isoformat(),
            "quota_before": self.quota_before,
            "quota_after": self.quota_after,
            "observations_created": self.observations_created,
            "snapshots_changed": self.snapshots_changed,
            "fixtures_changed": self.fixtures_changed,
            "matches_resolved": self.matches_resolved,
            "provider_attempts": self.provider_attempts,
            "provider_pages": self.provider_pages,
            "provider_retries": self.provider_retries,
            "skipped_work": self.skipped_work,
            "failed_work": self.failed_work,
            "completed_work": self.completed_work,
            "secondary": self.secondary,
            "plan": self.plan,
        }
