from collections import Counter
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from football.historical.reconciliation import _normalized_team_name
from football.models import (
    HistoricalMarketEvidence,
    HistoricalMarketUnavailable,
    Match,
    MatchSourceRef,
    ReconciliationStatus,
    Team,
    TeamSourceRef,
)

from .result_reconciliation import (
    fill_compatible_final_result,
    final_result_conflicts,
)
from .service import _persist_market, _source, _source_locator
from .source import acquire_source, parse_market_file, source_spec

SOURCE_TIMEZONE = ZoneInfo("Europe/London")


@dataclass(frozen=True)
class FrozenMapping:
    canonical_name: str
    creation_allowed: bool = False


FROZEN_TEAM_MAPPINGS = {
    (("FR", "Ligue 1"), "Le Mans"): FrozenMapping("Le Mans", True),
    (("DE", "Bundesliga"), "Elversberg"): FrozenMapping("SV Elversberg"),
    (
        ("AR", "Liga Profesional Argentina"),
        "Estudiantes Rio Cuarto",
    ): FrozenMapping("Estudiantes de Rio Cuarto"),
    (
        ("AR", "Liga Profesional Argentina"),
        "Gimnasia Mendoza",
    ): FrozenMapping("Gimnasia Mendoza", True),
    (("TR", "Süper Lig"), "Amedspor"): FrozenMapping("Amed", True),
    (("TR", "Süper Lig"), "Corum"): FrozenMapping("Çorum FK", True),
    (("TR", "Süper Lig"), "Erzurumspor"): FrozenMapping("Erzurumspor FK", True),
}


def _canonical_teams(competition, name):
    normalized = _normalized_team_name(name)
    return [
        team
        for team in Team.objects.filter(competition=competition).order_by("id")
        if _normalized_team_name(team.name) == normalized
    ]


def _source_ref_teams(source, competition, external_name):
    normalized = _normalized_team_name(external_name)
    refs = [
        ref
        for ref in TeamSourceRef.objects.filter(
            source=source,
            competition=competition,
            reconciliation_status=ReconciliationStatus.RESOLVED,
            team__isnull=False,
        ).select_related("team")
        if _normalized_team_name(ref.external_name) == normalized
    ]
    return {ref.team_id: ref.team for ref in refs}


def _ensure_team_ref(source, competition, team, external_name):
    external_id = f"{source_spec_external(competition)}:{external_name}"
    existing = TeamSourceRef.objects.filter(
        source=source, external_id=external_id
    ).first()
    if existing:
        if existing.team_id != team.pk or existing.competition_id != competition.pk:
            raise ValueError("FROZEN_TEAM_SOURCE_REF_CONFLICT")
        return existing, False
    canonical_ref = TeamSourceRef.objects.filter(source=source, team=team).first()
    if canonical_ref:
        if _normalized_team_name(canonical_ref.external_name) != _normalized_team_name(
            external_name
        ):
            raise ValueError("FOOTBALL_DATA_CANONICAL_TEAM_ALREADY_MAPPED")
        return canonical_ref, False
    return (
        TeamSourceRef.objects.create(
            source=source,
            external_id=external_id,
            external_name=external_name,
            competition=competition,
            team=team,
            reconciliation_status=ReconciliationStatus.RESOLVED,
            confidence=1,
        ),
        True,
    )


def source_spec_external(competition):
    class SeasonStub:
        year = 2000

    return source_spec(competition, SeasonStub()).external_competition


def _resolve_team(source, competition, external_name, *, apply):
    source_teams = _source_ref_teams(source, competition, external_name)
    if len(source_teams) == 1:
        return next(iter(source_teams.values())), "FOOTBALL_DATA_REF", False
    if len(source_teams) > 1:
        return None, "BLOCKED_TEAM_IDENTITY", False

    exact = _canonical_teams(competition, external_name)
    if len(exact) == 1:
        if apply:
            _ensure_team_ref(source, competition, exact[0], external_name)
        return exact[0], "EXACT_CANONICAL_NAME", False
    if len(exact) > 1:
        return None, "BLOCKED_TEAM_IDENTITY", False

    key = ((str(competition.country), competition.name), external_name)
    frozen = FROZEN_TEAM_MAPPINGS.get(key)
    if frozen is None:
        return None, "BLOCKED_TEAM_IDENTITY", False
    candidates = _canonical_teams(competition, frozen.canonical_name)
    if len(candidates) > 1:
        return None, "BLOCKED_TEAM_IDENTITY", False
    if candidates:
        team = candidates[0]
        if apply:
            _ensure_team_ref(source, competition, team, external_name)
        return team, "FROZEN_MAPPING", False
    if not frozen.creation_allowed:
        return None, "BLOCKED_TEAM_IDENTITY", False
    if not apply:
        return None, "APPROVED_TEAM_CREATION", True
    team = Team.objects.create(
        competition=competition, name=frozen.canonical_name, is_active=True
    )
    _ensure_team_ref(source, competition, team, external_name)
    return team, "APPROVED_TEAM_CREATED", True


def _row_outcome(row):
    if row.home_score > row.away_score:
        return Match.OUTCOME_HOME
    if row.home_score < row.away_score:
        return Match.OUTCOME_AWAY
    return Match.OUTCOME_DRAW


def _candidate_matches(season, home, away, row):
    if home is None or away is None:
        return []
    return list(
        Match.objects.filter(
            season=season,
            home_team=home,
            away_team=away,
            kickoff__date__gte=row.match_date - timedelta(days=2),
            kickoff__date__lte=row.match_date + timedelta(days=2),
        ).order_by("id")[:2]
    )


def _exact_source_match(source, competition, season, home, away, row):
    ref = (
        MatchSourceRef.objects.filter(source=source, external_id=row.external_id)
        .select_related("match__season", "match__home_team", "match__away_team")
        .first()
    )
    if ref is None:
        return None, "", False
    compatible = (
        ref.reconciliation_status == ReconciliationStatus.RESOLVED
        and ref.match_id is not None
        and ref.match.season_id == season.pk
        and ref.match.season.competition_id == competition.pk
        and ref.match.home_team_id == getattr(home, "pk", None)
        and ref.match.away_team_id == getattr(away, "pk", None)
    )
    if not compatible:
        return None, "MATCH_SOURCE_REF_CONFLICT", True
    return ref.match, "", True


def _result_conflicts(match, row):
    return final_result_conflicts(
        match,
        {
            "home_score": row.home_score,
            "away_score": row.away_score,
            "fulltime_home_score": row.home_score,
            "fulltime_away_score": row.away_score,
            "outcome": _row_outcome(row),
            "status_short": "FT",
            "status_long": "Match Finished",
        },
    )


def _fill_result(match, row):
    outcome = fill_compatible_final_result(
        match,
        {
            "home_score": row.home_score,
            "away_score": row.away_score,
            "fulltime_home_score": row.home_score,
            "fulltime_away_score": row.away_score,
            "outcome": _row_outcome(row),
            "status_short": "FT",
            "status_long": "Match Finished",
        },
    )
    return outcome == "FILLED"


def _source_kickoff(row):
    return datetime.combine(
        row.match_date, row.match_time or time(12, 0), tzinfo=SOURCE_TIMEZONE
    )


def _create_match(source, competition, season, home, away, row):
    match = Match(
        season=season,
        home_team=home,
        away_team=away,
        kickoff=_source_kickoff(row),
        kickoff_timezone=str(SOURCE_TIMEZONE),
        status_short="FT",
        status_long="Match Finished",
        outcome=_row_outcome(row),
        home_score=row.home_score,
        away_score=row.away_score,
        fulltime_home_score=row.home_score,
        fulltime_away_score=row.away_score,
        observed_at=timezone.now(),
    )
    match.full_clean()
    match.save()
    MatchSourceRef.objects.create(
        source=source,
        external_id=row.external_id,
        external_label=f"{row.home_name} - {row.away_name}",
        match=match,
        reconciliation_status=ReconciliationStatus.RESOLVED,
        confidence=1,
        context={
            "authority": "football-data.co.uk",
            "reconciliation": "FS015_CURRENT_SEASON_CREATED",
            "fs015_current_season_created": True,
            "source_date": row.match_date.isoformat(),
            "source_score": [row.home_score, row.away_score],
        },
    )
    return match


def _mark_match_ref_for_promotion(ref):
    context = dict(ref.context or {})
    if context.get("fs015_current_season_reconciled") is True:
        return ref
    context["fs015_current_season_reconciled"] = True
    ref.context = context
    ref.save(update_fields=["context"])
    return ref


def _ensure_existing_match_ref(source, match, row, *, mark_for_promotion=False):
    ref = MatchSourceRef.objects.filter(
        source=source, external_id=row.external_id
    ).first()
    if ref:
        if ref.match_id != match.pk:
            raise ValueError("FOOTBALL_DATA_MATCH_SOURCE_REF_CONFLICT")
        if mark_for_promotion:
            _mark_match_ref_for_promotion(ref)
        return ref
    canonical_ref = MatchSourceRef.objects.filter(source=source, match=match).first()
    if canonical_ref:
        if canonical_ref.external_id != row.external_id:
            raise ValueError("FOOTBALL_DATA_CANONICAL_MATCH_ALREADY_MAPPED")
        if mark_for_promotion:
            _mark_match_ref_for_promotion(canonical_ref)
        return canonical_ref
    return MatchSourceRef.objects.create(
        source=source,
        external_id=row.external_id,
        external_label=f"{row.home_name} - {row.away_name}",
        match=match,
        reconciliation_status=ReconciliationStatus.RESOLVED,
        confidence=1,
        context={
            "authority": "football-data.co.uk",
            "reconciliation": "FS015_CURRENT_SEASON_EXISTING",
            "fs015_current_season_reconciled": True,
            "source_date": row.match_date.isoformat(),
            "source_score": [row.home_score, row.away_score],
        },
    )


def _market_plan(source, match, row):
    evidence = HistoricalMarketEvidence.objects.filter(
        source=source, match=match
    ).first()
    unavailable = HistoricalMarketUnavailable.objects.filter(
        source=source, match=match
    ).first()
    if row.price is None:
        if evidence:
            return "HISTORICAL_MARKET_CONFLICT"
        return "NO_WORK" if unavailable else "SOURCE_NO_COMPLETE_1X2"
    if unavailable:
        return "FILL_HISTORICAL_1X2"
    if evidence is None:
        return "CREATE_HISTORICAL_1X2"
    same = (
        evidence.home_price == row.price.home
        and evidence.draw_price == row.price.draw
        and evidence.away_price == row.price.away
        and evidence.selected_group == row.price.group
        and evidence.time_semantics == row.price.time_semantics
    )
    return "NO_WORK" if same else "HISTORICAL_MARKET_CONFLICT"


@transaction.atomic
def recover_current_season(
    competition,
    season,
    *,
    apply=False,
    cache_only=False,
    cache_root=None,
    expected_checksum="",
    http_get=None,
):
    if season.competition_id != competition.pk or not season.is_current:
        raise ValueError("The explicit current Season is required.")
    source = _source()
    spec = source_spec(competition, season, cache_root=cache_root, current_cache=True)
    cached = acquire_source(
        spec,
        cache_only=cache_only,
        expected_checksum=expected_checksum,
        http_get=http_get,
    )
    parsed = parse_market_file(cached, season)
    counts = Counter()
    issues = []
    for row in parsed.rows:
        home, home_basis, home_created = _resolve_team(
            source, competition, row.home_name, apply=False
        )
        away, away_basis, away_created = _resolve_team(
            source, competition, row.away_name, apply=False
        )
        if (
            home_basis == "BLOCKED_TEAM_IDENTITY"
            or away_basis == "BLOCKED_TEAM_IDENTITY"
        ):
            counts["BLOCKED_TEAM_IDENTITY"] += 1
            if len(issues) < 100:
                issues.append(
                    {
                        "csv_line": row.csv_line,
                        "home": row.home_name,
                        "away": row.away_name,
                        "reason": "BLOCKED_TEAM_IDENTITY",
                    }
                )
            continue
        if apply:
            home, home_basis, home_created = _resolve_team(
                source, competition, row.home_name, apply=True
            )
            away, away_basis, away_created = _resolve_team(
                source, competition, row.away_name, apply=True
            )
        if home_created:
            counts["APPROVED_TEAM_CREATION"] += 1
        if away_created:
            counts["APPROVED_TEAM_CREATION"] += 1
        match, match_reason, exact_ref_found = _exact_source_match(
            source, competition, season, home, away, row
        )
        if exact_ref_found and match is None:
            counts[match_reason] += 1
            if len(issues) < 100:
                issues.append(
                    {
                        "csv_line": row.csv_line,
                        "external_id": row.external_id,
                        "reason": match_reason,
                    }
                )
            continue
        if not exact_ref_found:
            candidates = _candidate_matches(season, home, away, row)
            if len(candidates) > 1:
                counts["MATCH_AMBIGUOUS"] += 1
                continue
            match = candidates[0] if candidates else None
        if match is None:
            counts["CREATE_MISSING_MATCH"] += 1
            if apply:
                match = _create_match(source, competition, season, home, away, row)
        else:
            if _result_conflicts(match, row):
                counts["RESULT_CONFLICT"] += 1
                continue
            result_filled = apply and _fill_result(match, row)
            if result_filled:
                counts["FILL_MISSING_RESULT"] += 1
            else:
                counts["PRESERVE_EXISTING_RESULT"] += 1
            if apply:
                _ensure_existing_match_ref(
                    source,
                    match,
                    row,
                    mark_for_promotion=result_filled,
                )
        if match is None:
            market_action = (
                "SOURCE_NO_COMPLETE_1X2"
                if row.price is None
                else "CREATE_HISTORICAL_1X2"
            )
        else:
            market_action = _market_plan(source, match, row)
        counts[market_action] += 1
        if apply and market_action in {
            "CREATE_HISTORICAL_1X2",
            "FILL_HISTORICAL_1X2",
            "SOURCE_NO_COMPLETE_1X2",
        }:
            persisted = _persist_market(
                source,
                match,
                row,
                cached,
                allow_unavailable_fill=True,
            )
            if persisted == "CONFLICT":
                counts[market_action] -= 1
                counts["HISTORICAL_MARKET_CONFLICT"] += 1

    result = {
        "competition_id": competition.pk,
        "season_id": season.pk,
        "season_year": season.year,
        "mode": "APPLY" if apply else "DRY_RUN",
        "source_url": spec.url,
        "source_file": _source_locator(cached),
        "source_file_checksum": cached.checksum,
        "downloaded": cached.downloaded,
        "source_rows": parsed.source_rows,
        "valid_rows": len(parsed.rows),
        "invalid_rows": parsed.invalid_rows,
        "counts": dict(sorted(counts.items())),
        "issues": issues,
    }
    if not apply:
        transaction.set_rollback(True)
    return result
