from collections import defaultdict
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from django.conf import settings

from football.models import Match

from .constants import OUTCOMES


@dataclass(frozen=True)
class MatchRow:
    match_id: int
    kickoff: object
    season_year: int
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    outcome: str


def score_outcome(home_score, away_score):
    if home_score > away_score:
        return Match.OUTCOME_HOME
    if home_score < away_score:
        return Match.OUTCOME_AWAY
    return Match.OUTCOME_DRAW


def eligible_finished_matches(competition, *, before=None, season_year=None):
    queryset = (
        Match.objects.filter(
            season__competition=competition,
            season__competition__competition_type="League",
            season__competition__country__gt="",
            status_short="FT",
            home_score__isnull=False,
            away_score__isnull=False,
        )
        .select_related("season", "home_team", "away_team")
        .order_by("kickoff", "id")
    )
    if before is not None:
        queryset = queryset.filter(kickoff__lt=before)
    if season_year is not None:
        queryset = queryset.filter(season__year=season_year)
    return queryset


def rows_from_matches(matches):
    rows = []
    for match in matches:
        outcome = score_outcome(match.home_score, match.away_score)
        if match.outcome and match.outcome != outcome:
            raise ValueError(
                f"Match {match.id} outcome {match.outcome} contradicts its FT score."
            )
        rows.append(
            MatchRow(
                match_id=match.id,
                kickoff=match.kickoff,
                season_year=match.season.year,
                home_team=str(match.home_team_id),
                away_team=str(match.away_team_id),
                home_score=match.home_score,
                away_score=match.away_score,
                outcome=outcome,
            )
        )
    return rows


def local_day(value):
    return value.astimezone(ZoneInfo(settings.TIME_ZONE)).date()


def daily_batches(matches):
    batches = defaultdict(list)
    for match in matches:
        batches[local_day(match.kickoff)].append(match)
    return [
        (day, sorted(batch, key=lambda item: (item.kickoff, item.id)))
        for day, batch in sorted(batches.items())
    ]


def history_before_local_day(matches, target_day):
    """Conservative historical boundary: strictly earlier local calendar days."""
    return [match for match in matches if local_day(match.kickoff) < target_day]


def upcoming_matches_for_day(competition, day, cutoff):
    timezone = ZoneInfo(settings.TIME_ZONE)
    start = __import__("datetime").datetime.combine(
        day, __import__("datetime").time.min, tzinfo=timezone
    )
    end = __import__("datetime").datetime.combine(
        day, __import__("datetime").time.max, tzinfo=timezone
    )
    return (
        Match.objects.filter(
            season__competition=competition,
            season__competition__competition_type="League",
            season__competition__country__gt="",
            kickoff__range=(start, end),
            kickoff__gt=cutoff,
        )
        .filter(status_short__in=("TBD", "NS"))
        .select_related("season", "home_team", "away_team")
        .order_by("kickoff", "id")
    )


def outcome_index(outcome):
    return OUTCOMES.index(outcome)
