from dataclasses import dataclass, field
from datetime import datetime


class HistoricalIngestionError(Exception):
    """Base class for classified historical-ingestion failures."""


class HistoricalSourceUnavailable(HistoricalIngestionError):
    pass


class HistoricalParserError(HistoricalIngestionError):
    pass


class HistoricalMappingError(HistoricalIngestionError):
    pass


@dataclass(frozen=True)
class HistoricalResult:
    source_code: str
    competition_external_id: str
    season_year: int
    external_id: str
    home_external_id: str
    home_name: str
    away_external_id: str
    away_name: str
    kickoff: datetime
    kickoff_precision: str
    home_score: int
    away_score: int
    provenance: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.kickoff_precision not in {"EXACT", "DATE_ONLY"}:
            raise ValueError("Historical kickoff precision must be EXACT or DATE_ONLY.")
        if self.kickoff.tzinfo is None:
            raise ValueError("Historical kickoff must include a timezone offset.")
        if self.home_score < 0 or self.away_score < 0:
            raise ValueError("Historical full-time scores cannot be negative.")
