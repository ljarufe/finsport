from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal


class HistoricalMarketError(Exception):
    """Base error for structural FS-015 failures."""


class SourceUnsupported(HistoricalMarketError):
    pass


class SourceIntegrityError(HistoricalMarketError):
    pass


class SourceSchemaError(HistoricalMarketError):
    pass


class HistoricalMarketScopeError(HistoricalMarketError):
    pass


class PackageIntegrityError(HistoricalMarketError):
    pass


class PackageConflict(HistoricalMarketError):
    pass


@dataclass(frozen=True)
class PriceTriplet:
    group: str
    home: Decimal
    draw: Decimal
    away: Decimal
    time_semantics: str


@dataclass(frozen=True)
class MarketSourceRow:
    season_year: int
    csv_line: int
    match_date: date
    match_time: time | None
    home_name: str
    away_name: str
    home_score: int
    away_score: int
    external_id: str
    row_identity: str
    price: PriceTriplet | None


@dataclass(frozen=True)
class InvalidMarketSourceRow:
    csv_line: int
    reason: str
    match_date: date | None
    home_name: str
    away_name: str
    external_id: str
    row_identity: str
    empty_match_fields: bool


@dataclass
class ParsedMarketFile:
    rows: list[MarketSourceRow] = field(default_factory=list)
    invalid: list[InvalidMarketSourceRow] = field(default_factory=list)
    source_rows: int = 0
    invalid_rows: int = 0
    invalid_reasons: dict[str, int] = field(default_factory=dict)
    schema_family: str = ""
    header_signature: str = ""


@dataclass(frozen=True)
class SourceSpec:
    family: str
    external_competition: str
    source_season: str
    url: str
    cache_path: str


@dataclass(frozen=True)
class CachedSource:
    spec: SourceSpec
    payload: bytes
    checksum: str
    downloaded: bool
    provenance_locator: str = ""
