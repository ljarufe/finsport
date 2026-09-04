import unicodedata
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from football.models import (
    CompetitionSourceRef,
    Match,
    MatchSourceRef,
    ReconciliationStatus,
    Team,
    TeamSourceRef,
)

from .contracts import HistoricalMappingError

EXPLICIT_TEAM_ALIASES = {
    ("ES", "Ath Bilbao"): "Athletic Club",
    ("ES", "Ath Madrid"): "Atletico Madrid",
    ("ES", "Betis"): "Real Betis",
    ("ES", "Sociedad"): "Real Sociedad",
    ("ES", "Vallecano"): "Rayo Vallecano",
    ("ES", "Celta"): "Celta Vigo",
    ("ES", "Espanol"): "Espanyol",
    ("EN", "Man City"): "Manchester City",
    ("EN", "Man United"): "Manchester United",
    ("EN", "Nott'm Forest"): "Nottingham Forest",
}

EXACT_KICKOFF_TOLERANCE = timedelta(hours=2)


@dataclass
class ReconciliationStats:
    mapped: int = 0
    reconciled: int = 0
    created: int = 0
    unchanged: int = 0
    ambiguities: int = 0
    conflicts: int = 0

    def add(self, other):
        for field in self.__dataclass_fields__:
            setattr(self, field, getattr(self, field) + getattr(other, field))


def _outcome(home_score, away_score):
    if home_score > away_score:
        return Match.OUTCOME_HOME
    if home_score < away_score:
        return Match.OUTCOME_AWAY
    return Match.OUTCOME_DRAW


def ensure_competition_ref(source, competition, external_id):
    ref, created = CompetitionSourceRef.objects.get_or_create(
        source=source,
        external_id=external_id,
        defaults={
            "competition": competition,
            "external_name": competition.name,
            "reconciliation_status": ReconciliationStatus.RESOLVED,
            "confidence": 1,
            "context": {"mapping": "FS-011 approved explicit contract"},
        },
    )
    if not created and ref.competition_id != competition.pk:
        raise HistoricalMappingError("COMPETITION_MAPPING_CONFLICT")
    return ref


def _normalized_team_name(value):
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    punctuation_as_space = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in without_marks.casefold()
    )
    return " ".join(punctuation_as_space.split())


def _team_from_normalized_source_ref(source, competition, external_name):
    normalized_name = _normalized_team_name(external_name)
    matching_refs = [
        ref
        for ref in TeamSourceRef.objects.filter(source=source, competition=competition)
        .select_related("team")
        .order_by("id")
        if _normalized_team_name(ref.external_name) == normalized_name
    ]
    if not matching_refs:
        return None
    if any(
        ref.reconciliation_status != ReconciliationStatus.RESOLVED
        or not ref.team_id
        or ref.team.competition_id != competition.pk
        for ref in matching_refs
    ):
        raise HistoricalMappingError(f"AMBIGUOUS_TEAM_MAPPING:{external_name}")
    teams = {ref.team_id: ref.team for ref in matching_refs}
    if len(teams) != 1:
        raise HistoricalMappingError(f"AMBIGUOUS_TEAM_MAPPING:{external_name}")
    return next(iter(teams.values()))


def _explicit_alias_target(country, external_name, aliases):
    normalized_name = _normalized_team_name(external_name)
    targets = {
        target
        for (alias_country, alias_name), target in aliases.items()
        if alias_country == country
        and _normalized_team_name(alias_name) == normalized_name
    }
    if len(targets) > 1:
        raise HistoricalMappingError(f"AMBIGUOUS_TEAM_MAPPING:{external_name}")
    if targets:
        return next(iter(targets)), True
    return external_name, False


def _team(source, competition, external_id, external_name, aliases):
    ref = TeamSourceRef.objects.filter(source=source, external_id=external_id).first()
    if ref:
        if (
            ref.reconciliation_status != ReconciliationStatus.RESOLVED
            or not ref.team_id
            or ref.competition_id != competition.pk
        ):
            raise HistoricalMappingError("AMBIGUOUS_TEAM_MAPPING")
        return ref.team

    team = _team_from_normalized_source_ref(source, competition, external_name)
    if team is not None:
        return team

    country = str(competition.country)
    canonical_name, alias_matched = _explicit_alias_target(
        country, external_name, aliases
    )
    normalized_name = _normalized_team_name(canonical_name)
    candidates = [
        team
        for team in Team.objects.filter(competition=competition).order_by("id")
        if _normalized_team_name(team.name) == normalized_name
    ][:2]
    if len(candidates) > 1:
        raise HistoricalMappingError(f"AMBIGUOUS_TEAM_MAPPING:{external_name}")
    if candidates:
        team = candidates[0]
    elif alias_matched:
        raise HistoricalMappingError(
            f"EXPLICIT_TEAM_ALIAS_TARGET_MISSING:{external_name}"
        )
    else:
        raise HistoricalMappingError(f"UNMAPPED_TEAM_IDENTITY:{external_name}")
    TeamSourceRef.objects.create(
        source=source,
        external_id=external_id,
        external_name=external_name,
        competition=competition,
        team=team,
        reconciliation_status=ReconciliationStatus.RESOLVED,
        confidence=1,
    )
    return team


def _candidate_matches(record, season, home_team, away_team):
    candidates = Match.objects.filter(
        season=season, home_team=home_team, away_team=away_team
    )
    if record.kickoff_precision == "EXACT":
        candidates = candidates.filter(
            kickoff__gte=record.kickoff - EXACT_KICKOFF_TOLERANCE,
            kickoff__lte=record.kickoff + EXACT_KICKOFF_TOLERANCE,
        )
    else:
        candidates = candidates.filter(kickoff__date=record.kickoff.date())
    return list(candidates.order_by("id")[:2])


def _same_result(match, record):
    return (
        match.status_short == "FT"
        and match.home_score == record.home_score
        and match.away_score == record.away_score
        and match.outcome == _outcome(record.home_score, record.away_score)
    )


def _ref_context(record, *, state, match=None):
    context = {
        **record.provenance,
        "season_year": record.season_year,
        "kickoff_precision": record.kickoff_precision,
        "source_kickoff": record.kickoff.isoformat(),
        "source_score": [record.home_score, record.away_score],
        "reconciliation": state,
    }
    if match is not None:
        context.update(
            {
                "canonical_kickoff": match.kickoff.isoformat(),
                "source_canonical_delta_seconds": int(
                    (match.kickoff - record.kickoff).total_seconds()
                ),
                "exact_kickoff_tolerance_seconds": int(
                    EXACT_KICKOFF_TOLERANCE.total_seconds()
                ),
            }
        )
    return context


@transaction.atomic
def reconcile_result(source, competition, season, record, *, aliases=None):
    aliases = {**EXPLICIT_TEAM_ALIASES, **(aliases or {})}
    stats = ReconciliationStats()
    if season.competition_id != competition.pk or record.season_year != season.year:
        raise HistoricalMappingError("SEASON_MAPPING_MISMATCH")
    existing_ref = (
        MatchSourceRef.objects.select_for_update()
        .filter(source=source, external_id=record.external_id)
        .first()
    )
    if existing_ref and existing_ref.match_id:
        if _same_result(existing_ref.match, record):
            existing_ref.last_seen_at = timezone.now()
            existing_ref.context = _ref_context(
                record, state="UNCHANGED", match=existing_ref.match
            )
            existing_ref.save(update_fields=["last_seen_at", "context"])
            stats.mapped = stats.reconciled = stats.unchanged = 1
            return stats
        existing_ref.context = _ref_context(
            record, state="SOURCE_REIMPORT_CONFLICT", match=existing_ref.match
        )
        existing_ref.last_seen_at = timezone.now()
        existing_ref.save(update_fields=["context", "last_seen_at"])
        stats.mapped = stats.conflicts = 1
        return stats
    if existing_ref:
        raise HistoricalMappingError("UNRESOLVED_SOURCE_MATCH_REFERENCE")

    try:
        home_team = _team(
            source, competition, record.home_external_id, record.home_name, aliases
        )
        away_team = _team(
            source, competition, record.away_external_id, record.away_name, aliases
        )
    except HistoricalMappingError:
        stats.ambiguities = 1
        raise
    stats.mapped = 1
    if home_team.pk == away_team.pk:
        raise HistoricalMappingError("HOME_AWAY_TEAM_MAPPING_COLLISION")

    candidates = _candidate_matches(record, season, home_team, away_team)
    if len(candidates) > 1:
        MatchSourceRef.objects.create(
            source=source,
            external_id=record.external_id,
            external_label=f"{record.home_name} - {record.away_name}",
            reconciliation_status=ReconciliationStatus.PENDING,
            context=_ref_context(record, state="AMBIGUOUS_MATCH"),
        )
        stats.ambiguities = 1
        return stats

    match = candidates[0] if candidates else None
    if match is not None and not _same_result(match, record):
        authority = "secondary"
        if match.source_refs.filter(source__code="api_football").exists():
            authority = "api_football"
        MatchSourceRef.objects.create(
            source=source,
            external_id=record.external_id,
            external_label=f"{record.home_name} - {record.away_name}",
            proposed_match=match,
            reconciliation_status=ReconciliationStatus.PENDING,
            context={
                **_ref_context(record, state="RESULT_CONFLICT", match=match),
                "canonical_authority": authority,
                "canonical_score": [match.home_score, match.away_score],
            },
        )
        stats.conflicts = 1
        return stats

    if match is None:
        match = Match(
            season=season,
            home_team=home_team,
            away_team=away_team,
            kickoff=record.kickoff,
            kickoff_timezone=str(record.kickoff.tzinfo),
            status_short="FT",
            status_long="Match Finished",
            outcome=_outcome(record.home_score, record.away_score),
            home_score=record.home_score,
            away_score=record.away_score,
            fulltime_home_score=record.home_score,
            fulltime_away_score=record.away_score,
            observed_at=timezone.now(),
        )
        match.full_clean()
        match.save()
        stats.created = 1
    else:
        stats.unchanged = 1
    MatchSourceRef.objects.create(
        source=source,
        external_id=record.external_id,
        external_label=f"{record.home_name} - {record.away_name}",
        match=match,
        reconciliation_status=ReconciliationStatus.RESOLVED,
        confidence=1,
        context=_ref_context(record, state="RECONCILED", match=match),
    )
    stats.reconciled = 1
    return stats
