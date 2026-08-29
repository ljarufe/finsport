from dataclasses import dataclass, field


class PhaseState:
    SUCCESS = "SUCCESS"
    NO_WORK = "NO_WORK"
    SKIPPED = "SKIPPED"
    UNAVAILABLE = "UNAVAILABLE"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PhaseResult:
    state: str
    details: dict = field(default_factory=dict)
    reason: str = ""

    def as_dict(self):
        return {
            "state": self.state,
            "reason": self.reason,
            "details": self.details,
        }


@dataclass(frozen=True)
class PipelineResult:
    run_id: int | None
    cycle_identity: str
    status: str
    phases: dict
    report: dict
    dry_run: bool = False

    def as_dict(self):
        return {
            "run_id": self.run_id,
            "cycle_identity": self.cycle_identity,
            "status": self.status,
            "dry_run": self.dry_run,
            "phases": self.phases,
            "report": self.report,
        }
