import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from football.historical.reconciliation import _normalized_team_name
from football.models import (
    Competition,
    HistoricalMarketCoverage,
    HistoricalMarketEvidence,
    HistoricalMarketUnavailable,
    Match,
    MatchSourceRef,
    ReconciliationStatus,
    Season,
    Team,
    TeamSourceRef,
)

from .contracts import PackageConflict, PackageIntegrityError
from .current_season import FROZEN_TEAM_MAPPINGS
from .promotion import market_baseline_is_promoted, promote_market_baseline
from .result_reconciliation import fill_compatible_final_result
from .service import _source
from .source import _atomic_write

PACKAGE_SCHEMA = "fs015-historical-market-package-v1"
PACKAGE_COLLECTIONS = (
    "team_refs",
    "created_matches",
    "current_match_refs",
    "evidence",
    "unavailable",
    "coverage",
)


def _competition_payload(competition):
    return {
        "country": str(competition.country),
        "name": competition.name,
        "competition_type": competition.competition_type,
    }


def _match_payload(match, source_external_id=""):
    payload = {
        "competition": _competition_payload(match.season.competition),
        "season_year": match.season.year,
        "home_team": match.home_team.name,
        "away_team": match.away_team.name,
        "kickoff": match.kickoff.isoformat(),
        "kickoff_timezone": match.kickoff_timezone,
        "status_short": match.status_short,
        "status_long": match.status_long,
        "outcome": match.outcome,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "fulltime_home_score": match.fulltime_home_score,
        "fulltime_away_score": match.fulltime_away_score,
    }
    if source_external_id:
        payload["source_external_id"] = source_external_id
    return payload


def _match_ref_payload(ref):
    return {
        **_match_payload(ref.match, ref.external_id),
        "source_external_id": ref.external_id,
        "source_external_label": ref.external_label,
        "source_context": ref.context,
    }


def _creation_authorized(competition, external_name, canonical_name):
    mapping = FROZEN_TEAM_MAPPINGS.get(
        ((str(competition.country), competition.name), external_name)
    )
    return bool(
        mapping
        and mapping.creation_allowed
        and mapping.canonical_name == canonical_name
    )


def build_package_payload():
    source = _source()
    evidences = list(
        HistoricalMarketEvidence.objects.filter(source=source)
        .select_related(
            "match__season__competition", "match__home_team", "match__away_team"
        )
        .order_by("id")
    )
    unavailable = list(
        HistoricalMarketUnavailable.objects.filter(source=source)
        .select_related(
            "match__season__competition", "match__home_team", "match__away_team"
        )
        .order_by("id")
    )
    coverages = list(
        HistoricalMarketCoverage.objects.filter(source=source)
        .select_related("competition", "season")
        .order_by("competition_id", "season__year")
    )
    created_match_refs = list(
        MatchSourceRef.objects.filter(
            source=source, context__fs015_current_season_created=True
        )
        .select_related(
            "match__season__competition", "match__home_team", "match__away_team"
        )
        .order_by("id")
    )
    existing_match_refs = list(
        MatchSourceRef.objects.filter(
            source=source, context__fs015_current_season_reconciled=True
        )
        .select_related(
            "match__season__competition", "match__home_team", "match__away_team"
        )
        .order_by("id")
    )
    evidence_match_ids = {item.match_id for item in [*evidences, *unavailable]}
    source_ref_by_match = dict(
        MatchSourceRef.objects.filter(
            source=source,
            match_id__in=evidence_match_ids,
            reconciliation_status=ReconciliationStatus.RESOLVED,
        ).values_list("match_id", "external_id")
    )
    required_team_ids = {
        team_id
        for ref in [*created_match_refs, *existing_match_refs]
        if ref.match_id
        for team_id in (ref.match.home_team_id, ref.match.away_team_id)
    }
    team_refs = list(
        TeamSourceRef.objects.filter(
            source=source,
            team_id__in=required_team_ids,
            reconciliation_status=ReconciliationStatus.RESOLVED,
            team__isnull=False,
        )
        .select_related("competition", "team")
        .order_by("competition_id", "external_id")
    )
    return {
        "schema": PACKAGE_SCHEMA,
        "source": source.code,
        "created_at": timezone.now().isoformat(),
        "team_refs": [
            {
                "competition": _competition_payload(ref.competition),
                "external_id": ref.external_id,
                "external_name": ref.external_name,
                "canonical_name": ref.team.name,
                "creation_authorized": _creation_authorized(
                    ref.competition, ref.external_name, ref.team.name
                ),
            }
            for ref in team_refs
        ],
        "created_matches": [
            _match_ref_payload(ref) for ref in created_match_refs if ref.match_id
        ],
        "current_match_refs": [
            _match_ref_payload(ref) for ref in existing_match_refs if ref.match_id
        ],
        "evidence": [
            {
                "match": _match_payload(
                    item.match, source_ref_by_match.get(item.match_id, "")
                ),
                "home_price": str(item.home_price),
                "draw_price": str(item.draw_price),
                "away_price": str(item.away_price),
                "selected_group": item.selected_group,
                "time_semantics": item.time_semantics,
                "source_price_is_real": item.source_price_is_real,
                "timestamp_is_imputed": item.timestamp_is_imputed,
                "evidence_class": item.evidence_class,
                "source_competition": item.source_competition,
                "source_season": item.source_season,
                "source_file": item.source_file,
                "source_file_checksum": item.source_file_checksum,
                "source_row_identity": item.source_row_identity,
                "provenance_version": item.provenance_version,
            }
            for item in evidences
        ],
        "unavailable": [
            {
                "match": _match_payload(
                    item.match, source_ref_by_match.get(item.match_id, "")
                ),
                "reason": item.reason,
                "source_file": item.source_file,
                "source_file_checksum": item.source_file_checksum,
                "source_row_identity": item.source_row_identity,
                "provenance_version": item.provenance_version,
            }
            for item in unavailable
        ],
        "coverage": [
            {
                "competition": _competition_payload(item.competition),
                "season_year": item.season.year,
                "status": item.status,
                "strategy_version": item.strategy_version,
                "source_url": item.source_url,
                "source_file": item.source_file,
                "source_file_checksum": item.source_file_checksum,
                "attempted": item.attempted,
                "available": item.available,
                "source_rows": item.source_rows,
                "valid_rows": item.valid_rows,
                "complete_triplet_rows": item.complete_triplet_rows,
                "imported_rows": item.imported_rows,
                "unavailable_rows": item.unavailable_rows,
                "outside_canonical_pool_rows": item.outside_canonical_pool_rows,
                "unresolved_rows": item.unresolved_rows,
                "conflict_rows": item.conflict_rows,
                "invalid_rows": item.invalid_rows,
                "attempt_count": item.attempt_count,
                "download_count": item.download_count,
                "reason": item.reason,
                "time_semantics": item.time_semantics,
                "diagnostics": item.diagnostics,
                "last_attempt_at": (
                    item.last_attempt_at.isoformat() if item.last_attempt_at else None
                ),
                "completed_at": (
                    item.completed_at.isoformat() if item.completed_at else None
                ),
            }
            for item in coverages
        ],
    }


def _competition_key(data):
    return (data["country"], data["name"], data["competition_type"])


def _competition_from_row(collection, row):
    if collection in {"evidence", "unavailable"}:
        return row["match"]["competition"]
    return row["competition"]


def _season_from_row(collection, row):
    if collection == "team_refs":
        return None
    if collection in {"evidence", "unavailable"}:
        return row["match"]["season_year"]
    return row["season_year"]


def package_aggregates(payload):
    competition_counts = {}
    season_counts = {}
    for collection in PACKAGE_COLLECTIONS:
        for row in payload.get(collection, []):
            competition = _competition_from_row(collection, row)
            key = _competition_key(competition)
            competition_counts.setdefault(key, Counter())[collection] += 1
            season_year = _season_from_row(collection, row)
            if season_year is not None:
                season_counts.setdefault((key, season_year), Counter())[collection] += 1

    def counts(counter):
        return {collection: counter[collection] for collection in PACKAGE_COLLECTIONS}

    return {
        "overall": {
            collection: len(payload.get(collection, []))
            for collection in PACKAGE_COLLECTIONS
        },
        "by_competition": [
            {
                "competition": {
                    "country": key[0],
                    "name": key[1],
                    "competition_type": key[2],
                },
                "counts": counts(competition_counts[key]),
            }
            for key in sorted(competition_counts)
        ],
        "by_competition_season": [
            {
                "competition": {
                    "country": key[0][0],
                    "name": key[0][1],
                    "competition_type": key[0][2],
                },
                "season_year": key[1],
                "counts": counts(season_counts[key]),
            }
            for key in sorted(season_counts)
        ],
    }


def export_package(package_path, manifest_path):
    package_path = Path(package_path)
    manifest_path = Path(manifest_path)
    payload = build_package_payload()
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode()
    checksum = hashlib.sha256(raw).hexdigest()
    aggregates = package_aggregates(payload)
    counts = aggregates["overall"]
    manifest = {
        "ticket": "FS-015",
        "schema": PACKAGE_SCHEMA,
        "created_at": payload["created_at"],
        "package_file": package_path.name,
        "package_sha256": checksum,
        "counts": counts,
        "aggregates": aggregates,
        "natural_key_order": [
            "Competition",
            "Season",
            "Team/TeamSourceRef",
            "Match/MatchSourceRef",
            "Current MatchSourceRef",
            "HistoricalMarketEvidence/Unavailable",
            "HistoricalMarketCoverage",
        ],
    }
    _atomic_write(package_path, raw)
    _atomic_write(
        manifest_path,
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
    )
    return manifest


def read_package(package_path, manifest_path):
    package_path = Path(package_path)
    manifest_path = Path(manifest_path)
    raw = package_path.read_bytes()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != PACKAGE_SCHEMA:
        raise PackageIntegrityError("PACKAGE_MANIFEST_SCHEMA_MISMATCH")
    if hashlib.sha256(raw).hexdigest() != manifest.get("package_sha256"):
        raise PackageIntegrityError("PACKAGE_CHECKSUM_MISMATCH")
    payload = json.loads(raw)
    if payload.get("schema") != PACKAGE_SCHEMA:
        raise PackageIntegrityError("PACKAGE_SCHEMA_MISMATCH")
    for key, count in manifest.get("counts", {}).items():
        if len(payload.get(key, [])) != count:
            raise PackageIntegrityError(f"PACKAGE_COUNT_MISMATCH:{key}")
    if manifest.get("aggregates") != package_aggregates(payload):
        raise PackageIntegrityError("PACKAGE_AGGREGATE_MISMATCH")
    return payload, manifest


def _competition(data):
    try:
        return Competition.objects.get(
            country=data["country"],
            name=data["name"],
            competition_type=data["competition_type"],
        )
    except Competition.DoesNotExist as error:
        raise PackageConflict("PACKAGE_COMPETITION_MISSING") from error


def _team(competition, name, *, create=False):
    normalized = _normalized_team_name(name)
    candidates = [
        team
        for team in Team.objects.filter(competition=competition).order_by("id")
        if _normalized_team_name(team.name) == normalized
    ]
    if len(candidates) > 1:
        raise PackageConflict("PACKAGE_TEAM_AMBIGUOUS")
    if candidates:
        return candidates[0], False
    if not create:
        raise PackageConflict(f"PACKAGE_TEAM_MISSING:{name}")
    return Team.objects.create(competition=competition, name=name), True


def _season(competition, year):
    try:
        return Season.objects.get(competition=competition, year=year)
    except Season.DoesNotExist as error:
        raise PackageConflict("PACKAGE_SEASON_MISSING") from error


def _match(data, source=None, *, allow_missing=False):
    competition = _competition(data["competition"])
    season = _season(competition, data["season_year"])
    home, _ = _team(competition, data["home_team"])
    away, _ = _team(competition, data["away_team"])
    external_id = data.get("source_external_id", "")
    if source is not None and external_id:
        ref = (
            MatchSourceRef.objects.filter(source=source, external_id=external_id)
            .select_related("match__season")
            .first()
        )
        if ref is not None:
            compatible = (
                ref.reconciliation_status == ReconciliationStatus.RESOLVED
                and ref.match_id is not None
                and ref.match.season_id == season.pk
                and ref.match.season.competition_id == competition.pk
                and ref.match.home_team_id == home.pk
                and ref.match.away_team_id == away.pk
            )
            if not compatible:
                raise PackageConflict("PACKAGE_MATCH_REF_CONFLICT")
            return ref.match
    kickoff = datetime.fromisoformat(data["kickoff"])
    candidates = list(
        Match.objects.filter(
            season=season,
            home_team=home,
            away_team=away,
            kickoff__gte=kickoff - timedelta(days=2),
            kickoff__lte=kickoff + timedelta(days=2),
        ).order_by("id")[:2]
    )
    if not candidates and allow_missing:
        return None
    if len(candidates) != 1:
        reason = "MISSING" if not candidates else "AMBIGUOUS"
        raise PackageConflict(f"PACKAGE_MATCH_{reason}")
    return candidates[0]


def _reconcile_match_values(match, row, counts):
    outcome = fill_compatible_final_result(match, row)
    if outcome == "CONFLICT":
        raise PackageConflict("PACKAGE_CANONICAL_MATCH_CONFLICT")
    if outcome == "FILLED":
        counts["matches_filled"] += 1
    else:
        counts["matches_unchanged"] += 1


def _ensure_match_ref(source, match, row, counts):
    ref = MatchSourceRef.objects.filter(
        source=source, external_id=row["source_external_id"]
    ).first()
    if ref and ref.match_id != match.pk:
        raise PackageConflict("PACKAGE_MATCH_REF_CONFLICT")
    canonical_ref = MatchSourceRef.objects.filter(source=source, match=match).first()
    if canonical_ref and canonical_ref.external_id != row["source_external_id"]:
        raise PackageConflict("PACKAGE_CANONICAL_MATCH_REF_CONFLICT")
    if ref is None and canonical_ref is None:
        MatchSourceRef.objects.create(
            source=source,
            external_id=row["source_external_id"],
            external_label=row["source_external_label"],
            match=match,
            reconciliation_status=ReconciliationStatus.RESOLVED,
            confidence=1,
            context=row["source_context"],
        )
        counts["match_refs_created"] += 1
    else:
        counts["match_refs_unchanged"] += 1


def _import_team_refs(source, payload, counts):
    for row in payload["team_refs"]:
        competition = _competition(row["competition"])
        team, created = _team(
            competition,
            row["canonical_name"],
            create=row["creation_authorized"],
        )
        counts["teams_created"] += int(created)
        existing = TeamSourceRef.objects.filter(
            source=source, external_id=row["external_id"]
        ).first()
        if existing:
            if existing.team_id != team.pk or existing.competition_id != competition.pk:
                raise PackageConflict("PACKAGE_TEAM_REF_CONFLICT")
            counts["team_refs_unchanged"] += 1
            continue
        canonical_ref = TeamSourceRef.objects.filter(source=source, team=team).first()
        if canonical_ref:
            if _normalized_team_name(
                canonical_ref.external_name
            ) != _normalized_team_name(row["external_name"]):
                raise PackageConflict("PACKAGE_CANONICAL_TEAM_REF_CONFLICT")
            counts["team_refs_unchanged"] += 1
            continue
        TeamSourceRef.objects.create(
            source=source,
            external_id=row["external_id"],
            external_name=row["external_name"],
            competition=competition,
            team=team,
            reconciliation_status=ReconciliationStatus.RESOLVED,
            confidence=1,
        )
        counts["team_refs_created"] += 1


def _import_created_matches(source, payload, counts):
    for row in payload["created_matches"]:
        competition = _competition(row["competition"])
        season = _season(competition, row["season_year"])
        home, _ = _team(competition, row["home_team"])
        away, _ = _team(competition, row["away_team"])
        kickoff = datetime.fromisoformat(row["kickoff"])
        match = _match(row, source, allow_missing=True)
        if match is not None:
            _reconcile_match_values(match, row, counts)
        else:
            match = Match(
                season=season,
                home_team=home,
                away_team=away,
                kickoff=kickoff,
                kickoff_timezone=row["kickoff_timezone"],
                status_short=row["status_short"],
                status_long=row["status_long"],
                outcome=row["outcome"],
                home_score=row["home_score"],
                away_score=row["away_score"],
                fulltime_home_score=row["fulltime_home_score"],
                fulltime_away_score=row["fulltime_away_score"],
                observed_at=timezone.now(),
            )
            match.full_clean()
            match.save()
            counts["matches_created"] += 1
        _ensure_match_ref(source, match, row, counts)


def _import_current_match_refs(source, payload, counts):
    for row in payload["current_match_refs"]:
        match = _match(row, source)
        _reconcile_match_values(match, row, counts)
        _ensure_match_ref(source, match, row, counts)


def _same_model(instance, values):
    return all(getattr(instance, key) == value for key, value in values.items())


@transaction.atomic
def import_package(package_path, manifest_path, *, apply=False):
    payload, manifest = read_package(package_path, manifest_path)
    if payload.get("source") != "football_data":
        raise PackageIntegrityError("PACKAGE_SOURCE_MISMATCH")
    source = _source()
    counts = Counter()
    _import_team_refs(source, payload, counts)
    _import_created_matches(source, payload, counts)
    _import_current_match_refs(source, payload, counts)
    for row in payload["evidence"]:
        match = _match(row["match"], source)
        if HistoricalMarketUnavailable.objects.filter(
            source=source, match=match
        ).exists():
            raise PackageConflict("PACKAGE_MARKET_AVAILABILITY_CONFLICT")
        values = {
            key: row[key]
            for key in (
                "home_price",
                "draw_price",
                "away_price",
                "selected_group",
                "time_semantics",
                "source_price_is_real",
                "timestamp_is_imputed",
                "evidence_class",
                "source_competition",
                "source_season",
                "source_file",
                "source_file_checksum",
                "source_row_identity",
                "provenance_version",
            )
        }
        for key in ("home_price", "draw_price", "away_price"):
            values[key] = Decimal(values[key])
        existing = HistoricalMarketEvidence.objects.filter(
            source=source, match=match
        ).first()
        if existing:
            if not _same_model(existing, values):
                raise PackageConflict("PACKAGE_HISTORICAL_MARKET_CONFLICT")
            counts["evidence_unchanged"] += 1
        else:
            evidence = HistoricalMarketEvidence(source=source, match=match, **values)
            evidence.full_clean()
            evidence.save()
            counts["evidence_created"] += 1
    for row in payload["unavailable"]:
        match = _match(row["match"], source)
        if HistoricalMarketEvidence.objects.filter(source=source, match=match).exists():
            raise PackageConflict("PACKAGE_MARKET_AVAILABILITY_CONFLICT")
        values = {
            key: row[key]
            for key in (
                "reason",
                "source_file",
                "source_file_checksum",
                "source_row_identity",
                "provenance_version",
            )
        }
        existing = HistoricalMarketUnavailable.objects.filter(
            source=source, match=match
        ).first()
        if existing:
            if not _same_model(existing, values):
                raise PackageConflict("PACKAGE_HISTORICAL_UNAVAILABLE_CONFLICT")
            counts["unavailable_unchanged"] += 1
        else:
            unavailable = HistoricalMarketUnavailable(
                source=source, match=match, **values
            )
            unavailable.full_clean()
            unavailable.save()
            counts["unavailable_created"] += 1
    for row in payload["coverage"]:
        competition = _competition(row["competition"])
        season = _season(competition, row["season_year"])
        values = {
            key: row[key]
            for key in (
                "status",
                "strategy_version",
                "source_url",
                "source_file",
                "source_file_checksum",
                "attempted",
                "available",
                "source_rows",
                "valid_rows",
                "complete_triplet_rows",
                "imported_rows",
                "unavailable_rows",
                "outside_canonical_pool_rows",
                "unresolved_rows",
                "conflict_rows",
                "invalid_rows",
                "attempt_count",
                "download_count",
                "reason",
                "time_semantics",
                "diagnostics",
            )
        }
        values["last_attempt_at"] = (
            datetime.fromisoformat(row["last_attempt_at"])
            if row["last_attempt_at"]
            else None
        )
        values["completed_at"] = (
            datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
        )
        existing = HistoricalMarketCoverage.objects.filter(
            competition=competition, season=season, source=source
        ).first()
        if existing:
            if not _same_model(existing, values):
                raise PackageConflict("PACKAGE_HISTORICAL_COVERAGE_CONFLICT")
            counts["coverage_unchanged"] += 1
        else:
            coverage = HistoricalMarketCoverage(
                competition=competition, season=season, source=source, **values
            )
            coverage.full_clean()
            coverage.save()
            counts["coverage_created"] += 1
    baseline_promotion = "NOT_APPLIED"
    if not apply:
        if market_baseline_is_promoted():
            baseline_promotion = "ALREADY_COMPLETE"
        transaction.set_rollback(True)
    else:
        baseline_promotion = promote_market_baseline()
    return {
        "mode": "APPLY" if apply else "DRY_RUN",
        "schema": manifest["schema"],
        "package_sha256": manifest["package_sha256"],
        "counts": dict(sorted(counts.items())),
        "baseline_promotion": baseline_promotion,
    }
