import csv
import hashlib
import io
import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests
from django.conf import settings

from football.models import HistoricalMarketEvidence
from football.providers.football_data import _external_id

from .contracts import (
    CachedSource,
    MarketSourceRow,
    ParsedMarketFile,
    PriceTriplet,
    SourceIntegrityError,
    SourceSchemaError,
    SourceSpec,
    SourceUnsupported,
)

SOURCE_CODE = "football_data"
SOURCE_NAME = "football-data.co.uk"
SOURCE_BASE_URL = "https://www.football-data.co.uk/"
PROVENANCE_VERSION = "fs015-football-data-v1"

EUROPE = {
    ("FR", "Ligue 1"): ("FRA Ligue 1", "F1", "ligue_1"),
    ("EN", "Premier League"): ("ENG Premier League", "E0", "premier_league"),
    ("DE", "Bundesliga"): ("DEU Bundesliga 1", "D1", "bundesliga"),
    ("IT", "Serie A"): ("ITA Serie A", "I1", "serie_a_italy"),
    ("NL", "Eredivisie"): ("NLD Eredivisie", "N1", "eredivisie"),
    ("PT", "Primeira Liga"): ("PRT Liga 1", "P1", "primeira_liga"),
    ("ES", "La Liga"): ("ESP La Liga", "SP1", "la_liga"),
    ("TR", "Süper Lig"): ("TUR Super Lig", "T1", "super_lig"),
}
DIRECT = {
    ("AR", "Liga Profesional Argentina"): (
        "ARG",
        "https://www.football-data.co.uk/new/ARG.csv",
        "liga_profesional_argentina",
    ),
    ("BR", "Serie A"): (
        "BRA",
        "https://www.football-data.co.uk/new/BRA.csv",
        "serie_a_brazil",
    ),
}

PRICE_GROUPS = (
    (
        HistoricalMarketEvidence.PriceGroup.PINNACLE_CLOSING,
        ("PSCH", "PSCD", "PSCA"),
        HistoricalMarketEvidence.TimeSemantics.ASSUMED_T30M,
    ),
    (
        HistoricalMarketEvidence.PriceGroup.BET365_CLOSING,
        ("B365CH", "B365CD", "B365CA"),
        HistoricalMarketEvidence.TimeSemantics.ASSUMED_T30M,
    ),
    (
        HistoricalMarketEvidence.PriceGroup.AVG_CLOSING,
        ("AvgCH", "AvgCD", "AvgCA"),
        HistoricalMarketEvidence.TimeSemantics.ASSUMED_T30M,
    ),
    (
        HistoricalMarketEvidence.PriceGroup.MAX_CLOSING,
        ("MaxCH", "MaxCD", "MaxCA"),
        HistoricalMarketEvidence.TimeSemantics.ASSUMED_T30M,
    ),
    (
        HistoricalMarketEvidence.PriceGroup.PINNACLE_PRE,
        ("PSH", "PSD", "PSA"),
        HistoricalMarketEvidence.TimeSemantics.ASSUMED_T6H,
    ),
    (
        HistoricalMarketEvidence.PriceGroup.BET365_PRE,
        ("B365H", "B365D", "B365A"),
        HistoricalMarketEvidence.TimeSemantics.ASSUMED_T6H,
    ),
    (
        HistoricalMarketEvidence.PriceGroup.AVG_PRE,
        ("AvgH", "AvgD", "AvgA"),
        HistoricalMarketEvidence.TimeSemantics.ASSUMED_T6H,
    ),
    (
        HistoricalMarketEvidence.PriceGroup.MAX_PRE,
        ("MaxH", "MaxD", "MaxA"),
        HistoricalMarketEvidence.TimeSemantics.ASSUMED_T6H,
    ),
)


def _cache_root(cache_root=None):
    return Path(cache_root or Path(settings.BASE_DIR) / "tmp" / "FS-015_sources")


def season_code(year):
    return f"{year % 100:02d}{(year + 1) % 100:02d}"


def season_label(year):
    return f"{year}-{(year + 1) % 100:02d}"


def source_spec(competition, season, *, cache_root=None, current_cache=False):
    key = (str(competition.country), competition.name)
    root = _cache_root(cache_root)
    if key in EUROPE:
        external, code, slug = EUROPE[key]
        url = f"{SOURCE_BASE_URL}mmz4281/{season_code(season.year)}/{code}.csv"
        if current_cache:
            path = root / f"{key[0]}_{code}_{season.year}.csv"
        else:
            path = root / slug / f"{season_label(season.year)}.csv"
        return SourceSpec(
            family="EUROPE_SEASON_FILE",
            external_competition=external,
            source_season=season_label(season.year),
            url=url,
            cache_path=str(path),
        )
    if key in DIRECT:
        external, url, slug = DIRECT[key]
        if current_cache:
            path = root / f"{key[0]}_{external}_{season.year}.csv"
        else:
            path = root / slug / "multi-season.csv"
        return SourceSpec(
            family="DIRECT_MULTI_SEASON_CSV",
            external_competition=external,
            source_season=str(season.year),
            url=url,
            cache_path=str(path),
        )
    raise SourceUnsupported("NO_APPROVED_FOOTBALL_DATA_SOURCE")


def _validate_payload(payload):
    prefix = payload[:256].lstrip().lower()
    if not payload or prefix.startswith((b"<html", b"<!doctype")):
        raise SourceIntegrityError("FOOTBALL_DATA_RESPONSE_IS_NOT_CSV")


def _default_http_get(url):
    response = requests.get(
        url,
        timeout=(10, 30),
        headers={"User-Agent": "Finsport-FS015/1.0"},
    )
    response.raise_for_status()
    return response.content


def _atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def acquire_source(spec, *, cache_only=False, expected_checksum="", http_get=None):
    path = Path(spec.cache_path)
    if cache_only:
        if not path.exists():
            raise SourceIntegrityError(f"CACHE_MISS:{path}")
        payload = path.read_bytes()
        downloaded = False
        provenance_locator = str(path)
    else:
        try:
            payload = (http_get or _default_http_get)(spec.url)
        except requests.RequestException as error:
            raise SourceIntegrityError(
                f"FOOTBALL_DATA_FETCH_FAILED:{type(error).__name__}"
            ) from error
        if isinstance(payload, str):
            payload = payload.encode()
        _validate_payload(payload)
        downloaded = True
        provenance_locator = spec.url
    _validate_payload(payload)
    checksum = hashlib.sha256(payload).hexdigest()
    if expected_checksum and checksum != expected_checksum:
        raise SourceIntegrityError("CACHE_CHECKSUM_MISMATCH")
    return CachedSource(
        spec=spec,
        payload=payload,
        checksum=checksum,
        downloaded=downloaded,
        provenance_locator=provenance_locator,
    )


def _decode(payload):
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise SourceSchemaError("CSV_ENCODING_UNRESOLVED")


def _delimiter(text):
    try:
        return csv.Sniffer().sniff(text[:8192], delimiters=",;\t").delimiter
    except csv.Error:
        return ","


def _direct_year(value):
    match = re.search(r"(?:19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else None


def _date(value):
    value = str(value or "").strip()
    for pattern in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise ValueError("INVALID_DATE")


def _time(value):
    value = str(value or "").strip()
    if not value:
        return None
    for pattern in ("%H:%M", "%H.%M"):
        try:
            return datetime.strptime(value, pattern).time()
        except ValueError:
            continue
    raise ValueError("INVALID_TIME")


def _score(value):
    number = Decimal(str(value or "").strip())
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        raise ValueError("INVALID_SCORE")
    return int(number)


def _price(value):
    try:
        number = Decimal(str(value or "").strip())
    except InvalidOperation:
        return None
    if not number.is_finite() or number <= 1:
        return None
    return number


def select_price_triplet(row, header):
    fields = set(header)
    for group, columns, time_semantics in PRICE_GROUPS:
        if not set(columns) <= fields:
            continue
        values = tuple(_price(row.get(column)) for column in columns)
        if all(value is not None for value in values):
            return PriceTriplet(group, *values, time_semantics)
    return None


def parse_market_file(cached, season):
    text = _decode(cached.payload)
    reader = csv.DictReader(io.StringIO(text), delimiter=_delimiter(text))
    header = reader.fieldnames or []
    fields = set(header)
    if {"HomeTeam", "AwayTeam", "FTHG", "FTAG", "Date"} <= fields:
        family = "EUROPE_SEASON_FILE"
        home_field, away_field = "HomeTeam", "AwayTeam"
        home_score_field, away_score_field = "FTHG", "FTAG"
    elif {"Home", "Away", "HG", "AG", "Date", "Season"} <= fields:
        family = "DIRECT_MULTI_SEASON_CSV"
        home_field, away_field = "Home", "Away"
        home_score_field, away_score_field = "HG", "AG"
    else:
        raise SourceSchemaError("UNSUPPORTED_FOOTBALL_DATA_SCHEMA")
    if family != cached.spec.family:
        raise SourceSchemaError("SOURCE_SCHEMA_FAMILY_MISMATCH")

    result = ParsedMarketFile(
        schema_family=family,
        header_signature=hashlib.sha256(
            json.dumps(header, separators=(",", ":")).encode()
        ).hexdigest(),
    )
    invalid = Counter()
    for csv_line, row in enumerate(reader, start=2):
        if family == "DIRECT_MULTI_SEASON_CSV":
            if _direct_year(row.get("Season")) != season.year:
                continue
        result.source_rows += 1
        try:
            match_date = _date(row.get("Date"))
            match_time = _time(row.get("Time"))
            home_name = str(row.get(home_field) or "").strip()
            away_name = str(row.get(away_field) or "").strip()
            if not home_name or not away_name:
                raise ValueError("MISSING_TEAM")
            home_score = _score(row.get(home_score_field))
            away_score = _score(row.get(away_score_field))
        except (InvalidOperation, ValueError) as error:
            invalid[str(error) or "INVALID_ROW"] += 1
            continue
        external_id = _external_id(
            cached.spec.external_competition,
            season.year,
            match_date,
            home_name,
            away_name,
        )
        result.rows.append(
            MarketSourceRow(
                season_year=season.year,
                csv_line=csv_line,
                match_date=match_date,
                match_time=match_time,
                home_name=home_name,
                away_name=away_name,
                home_score=home_score,
                away_score=away_score,
                external_id=external_id,
                row_identity=hashlib.sha256(
                    f"{cached.checksum}:{csv_line}".encode()
                ).hexdigest(),
                price=select_price_triplet(row, header),
            )
        )
    result.invalid_rows = sum(invalid.values())
    result.invalid_reasons = dict(sorted(invalid.items()))
    return result
