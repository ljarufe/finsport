import csv
import hashlib
import io
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import requests

from football.historical.contracts import (
    HistoricalParserError,
    HistoricalResult,
    HistoricalSourceUnavailable,
)

from .catalog import DIRECT_COMPETITIONS, EUROPE_COMPETITIONS

SOURCE_CODE = "football_data"
SOURCE_NAME = "football-data.co.uk"
SOURCE_BASE_URL = "https://www.football-data.co.uk/"
SOURCE_TIMEZONE_NAME = "Europe/London"
SOURCE_TIMEZONE = ZoneInfo(SOURCE_TIMEZONE_NAME)
NON_FINAL_RESULT_CLAIMS = {
    "P",
    "POSTPONED",
    "C",
    "CANCELLED",
    "CANCELED",
    "ABD",
    "ABANDONED",
    "VOID",
}


def source_contract(competition):
    key = (str(competition.country), competition.name)
    if key in EUROPE_COMPETITIONS:
        return "EUROPE_PENALTYBLOG", EUROPE_COMPETITIONS[key]
    if key in DIRECT_COMPETITIONS:
        return "DIRECT_CSV", DIRECT_COMPETITIONS[key][0]
    raise HistoricalSourceUnavailable("NO_APPROVED_HISTORICAL_SOURCE")


def _technical_kickoff(value, explicit_time=None):
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        raw_date = value.date().isoformat()
        raw_time = value.timetz().replace(tzinfo=None)
        was_aware = value.tzinfo is not None and value.utcoffset() is not None
        if not was_aware:
            value = value.replace(tzinfo=SOURCE_TIMEZONE)
        precision = "EXACT" if raw_time != time.min else "DATE_ONLY"
        return (
            value,
            precision,
            {
                "raw_source_date": raw_date,
                "raw_source_time": raw_time.isoformat() if precision == "EXACT" else "",
                "source_timezone_contract": SOURCE_TIMEZONE_NAME,
                "source_datetime_was_aware": was_aware,
                "normalized_source_kickoff": value.isoformat(),
            },
        )
    if isinstance(value, date):
        clock = explicit_time or time(12, 0)
        precision = "EXACT" if explicit_time is not None else "DATE_ONLY"
        kickoff = datetime.combine(value, clock, tzinfo=SOURCE_TIMEZONE)
        return (
            kickoff,
            precision,
            {
                "raw_source_date": value.isoformat(),
                "raw_source_time": explicit_time.isoformat() if explicit_time else "",
                "source_timezone_contract": SOURCE_TIMEZONE_NAME,
                "source_datetime_was_aware": False,
                "normalized_source_kickoff": kickoff.isoformat(),
            },
        )
    parsed = _parse_date(str(value))
    clock = explicit_time or time(12, 0)
    precision = "EXACT" if explicit_time is not None else "DATE_ONLY"
    kickoff = datetime.combine(parsed, clock, tzinfo=SOURCE_TIMEZONE)
    return (
        kickoff,
        precision,
        {
            "raw_source_date": str(value).strip(),
            "raw_source_time": explicit_time.isoformat() if explicit_time else "",
            "source_timezone_contract": SOURCE_TIMEZONE_NAME,
            "source_datetime_was_aware": False,
            "normalized_source_kickoff": kickoff.isoformat(),
        },
    )


def _external_id(*parts):
    material = "|".join(str(part) for part in parts)
    return hashlib.sha256(material.encode()).hexdigest()


def _score(row, *names):
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() not in {"", "nan", "None"}:
            return int(float(value))
    raise HistoricalParserError("SOURCE_ROW_MISSING_FULL_TIME_SCORE")


def _value(row, *names):
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() not in {"", "nan", "None"}:
            return str(value).strip()
    return ""


def _raw_value(row, *names):
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() not in {
            "",
            "nan",
            "NaT",
            "None",
        }:
            return value
    raise HistoricalParserError("SOURCE_ROW_MISSING_DATE")


class EuropeFootballDataAdapter:
    def __init__(self, competition, *, scraper_factory=None):
        self.competition = competition
        self.strategy, self.external_competition = source_contract(competition)
        if self.strategy != "EUROPE_PENALTYBLOG":
            raise HistoricalSourceUnavailable("COMPETITION_REQUIRES_DIRECT_CSV")
        if scraper_factory is None:
            from penaltyblog.scrapers import FootballData

            scraper_factory = FootballData
        self.scraper_factory = scraper_factory
        self.download_count = 0

    def records_for_season(self, season):
        season_label = f"{season.year}-{season.year + 1}"
        try:
            frame = self.scraper_factory(
                self.external_competition, season_label
            ).get_fixtures()
            self.download_count += 1
        except requests.RequestException as error:
            raise HistoricalSourceUnavailable(
                f"FOOTBALL_DATA_UNAVAILABLE:{type(error).__name__}"
            ) from error
        records = []
        for _, raw in frame.iterrows():
            row = raw.to_dict()
            home = _value(row, "team_home", "HomeTeam")
            away = _value(row, "team_away", "AwayTeam")
            if not home or not away:
                raise HistoricalParserError("SOURCE_ROW_MISSING_TEAM_IDENTITY")
            kickoff, precision, time_provenance = _technical_kickoff(
                _raw_value(row, "datetime", "date", "Date")
            )
            external_id = _external_id(
                self.external_competition, season.year, kickoff.date(), home, away
            )
            records.append(
                HistoricalResult(
                    source_code=SOURCE_CODE,
                    competition_external_id=self.external_competition,
                    season_year=season.year,
                    external_id=external_id,
                    home_external_id=f"{self.external_competition}:{home}",
                    home_name=home,
                    away_external_id=f"{self.external_competition}:{away}",
                    away_name=away,
                    kickoff=kickoff,
                    kickoff_precision=precision,
                    home_score=_score(row, "goals_home", "fthg", "FTHG"),
                    away_score=_score(row, "goals_away", "ftag", "FTAG"),
                    provenance={
                        "authority": SOURCE_NAME,
                        "adapter": "penaltyblog.FootballData",
                        "competition": self.external_competition,
                        "source_season": season_label,
                        **time_provenance,
                    },
                )
            )
        return records


def _default_http_get(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.content


def _parse_date(value):
    value = value.strip()
    for pattern in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise HistoricalParserError("SOURCE_ROW_INVALID_DATE")


def _parse_time(value):
    value = value.strip()
    if not value:
        return None
    for pattern in ("%H:%M", "%H.%M"):
        try:
            return datetime.strptime(value, pattern).time()
        except ValueError:
            continue
    raise HistoricalParserError("SOURCE_ROW_INVALID_TIME")


def _direct_final_scores(row):
    home = _value(row, "HG", "FTHG", "goals_home")
    away = _value(row, "AG", "FTAG", "goals_away")
    result_claim = _value(row, "Res", "Result", "FTR", "result").upper()
    if not home and not away:
        if result_claim and result_claim not in NON_FINAL_RESULT_CLAIMS:
            raise HistoricalParserError("SOURCE_ROW_FINAL_RESULT_WITHOUT_SCORES")
        return None
    if not home or not away:
        raise HistoricalParserError("SOURCE_ROW_PARTIAL_FULL_TIME_SCORE")
    try:
        return int(float(home)), int(float(away))
    except ValueError as error:
        raise HistoricalParserError("SOURCE_ROW_INVALID_FULL_TIME_SCORE") from error


class DirectFootballDataCSVAdapter:
    def __init__(self, competition, *, http_get=None):
        self.competition = competition
        self.strategy, self.external_competition = source_contract(competition)
        if self.strategy != "DIRECT_CSV":
            raise HistoricalSourceUnavailable("COMPETITION_REQUIRES_EUROPE_ADAPTER")
        self.url = DIRECT_COMPETITIONS[(str(competition.country), competition.name)][1]
        self.http_get = http_get or _default_http_get
        self.download_count = 0
        self._rows = None
        self.season_diagnostics = {}

    def _load(self):
        if self._rows is not None:
            return self._rows
        try:
            payload = self.http_get(self.url)
            self.download_count += 1
        except requests.RequestException as error:
            raise HistoricalSourceUnavailable(
                f"FOOTBALL_DATA_UNAVAILABLE:{type(error).__name__}"
            ) from error
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8-sig")
        self._rows = list(csv.DictReader(io.StringIO(payload)))
        return self._rows

    def records_for_season(self, season):
        if (
            season.start_date is None
            or season.end_date is None
            or season.start_date > season.end_date
        ):
            raise HistoricalParserError("CANONICAL_SEASON_DATE_RANGE_REQUIRED")
        overlaps = self.competition.seasons.exclude(pk=season.pk).filter(
            start_date__lte=season.end_date,
            end_date__gte=season.start_date,
        )
        if overlaps.exists():
            raise HistoricalParserError("CANONICAL_SEASON_DATE_RANGES_OVERLAP")
        records = []
        skipped_non_final = 0
        for row in self._load():
            raw_date = _value(row, "Date", "date")
            match_date = _parse_date(raw_date)
            if not season.start_date <= match_date <= season.end_date:
                continue
            home = _value(row, "Home", "HomeTeam", "team_home")
            away = _value(row, "Away", "AwayTeam", "team_away")
            if not home or not away:
                raise HistoricalParserError("SOURCE_ROW_MISSING_TEAM_IDENTITY")
            scores = _direct_final_scores(row)
            if scores is None:
                skipped_non_final += 1
                continue
            raw_time = _value(row, "Time", "time")
            explicit_time = _parse_time(raw_time)
            kickoff, precision, time_provenance = _technical_kickoff(
                match_date, explicit_time
            )
            time_provenance.update(
                {"raw_source_date": raw_date, "raw_source_time": raw_time}
            )
            source_season = _value(row, "Season", "season")
            external_id = _external_id(
                self.external_competition, season.year, match_date, home, away
            )
            records.append(
                HistoricalResult(
                    source_code=SOURCE_CODE,
                    competition_external_id=self.external_competition,
                    season_year=season.year,
                    external_id=external_id,
                    home_external_id=f"{self.external_competition}:{home}",
                    home_name=home,
                    away_external_id=f"{self.external_competition}:{away}",
                    away_name=away,
                    kickoff=kickoff,
                    kickoff_precision=precision,
                    home_score=scores[0],
                    away_score=scores[1],
                    provenance={
                        "authority": SOURCE_NAME,
                        "adapter": "direct_csv",
                        "url": self.url,
                        "source_season": source_season,
                        **time_provenance,
                    },
                )
            )
        self.season_diagnostics[season.year] = {
            "non_final_rows_skipped": skipped_non_final,
        }
        return records


def adapter_for(competition, **kwargs):
    strategy, _ = source_contract(competition)
    if strategy == "EUROPE_PENALTYBLOG":
        return EuropeFootballDataAdapter(competition, **kwargs)
    return DirectFootballDataCSVAdapter(competition, **kwargs)
