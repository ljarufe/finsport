from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from football.models import (
    Bookmaker,
    Competition,
    Match,
    OddsMarket,
    OddsObservation,
    Season,
    Source,
    Team,
)


def round_robin(team_ids):
    teams = list(team_ids)
    rounds = []
    for round_index in range(len(teams) - 1):
        pairs = []
        for index in range(len(teams) // 2):
            home = teams[index]
            away = teams[-index - 1]
            pairs.append((home, away) if round_index % 2 else (away, home))
        rounds.append(pairs)
        teams = [teams[0], teams[-1], *teams[1:-1]]
    return rounds


def create_synthetic_league():
    competition = Competition.objects.create(
        name="Synthetic League",
        competition_type="League",
        country="ES",
        enabled=True,
    )
    stable = [
        Team.objects.create(competition=competition, name=f"Team {index}")
        for index in range(1, 9)
    ]
    newcomers = [
        Team.objects.create(competition=competition, name=f"New Team {index}")
        for index in range(1, 3)
    ]
    season_teams = (stable, stable, [*stable[:6], *newcomers])
    seasons = []
    matches = []
    score_cycle = (
        (1, 0),
        (0, 0),
        (0, 1),
        (1, 1),
        (2, 0),
        (1, 2),
        (3, 1),
        (2, 2),
    )
    for season_index, year in enumerate((2022, 2023, 2024)):
        season = Season.objects.create(
            competition=competition,
            year=year,
            start_date=date(year, 8, 1),
            end_date=date(year + 1, 5, 31),
        )
        seasons.append(season)
        teams = season_teams[season_index]
        rounds = round_robin([team.id for team in teams])
        fixtures = rounds + [[(away, home) for home, away in pairs] for pairs in rounds]
        for round_index, pairs in enumerate(fixtures):
            kickoff_day = date(year, 8, 1) + timedelta(days=7 * round_index)
            for pair_index, (home_id, away_id) in enumerate(pairs):
                home_score, away_score = score_cycle[
                    (season_index * 3 + round_index + pair_index) % len(score_cycle)
                ]
                outcome = (
                    Match.OUTCOME_HOME
                    if home_score > away_score
                    else (
                        Match.OUTCOME_AWAY
                        if home_score < away_score
                        else Match.OUTCOME_DRAW
                    )
                )
                matches.append(
                    Match.objects.create(
                        season=season,
                        home_team_id=home_id,
                        away_team_id=away_id,
                        kickoff=timezone.make_aware(
                            datetime.combine(kickoff_day, time(14 + pair_index, 0))
                        ),
                        status_short="FT",
                        status_long="Match Finished",
                        home_score=home_score,
                        away_score=away_score,
                        outcome=outcome,
                    )
                )
    return competition, seasons, matches


def create_synthetic_odds(matches):
    source = Source.objects.create(
        code="synthetic", name="Synthetic", base_url="https://example.test/"
    )
    market = OddsMarket.objects.create(
        source=source, external_id="1", name="Match Winner"
    )
    bookmakers = [
        Bookmaker.objects.create(
            source=source, external_id=str(index), name=f"Book {index}"
        )
        for index in range(1, 5)
    ]
    observations = []
    offsets = (timedelta(hours=24), timedelta(hours=3), timedelta(minutes=30))
    for match_index, match in enumerate(matches):
        for book_index, bookmaker in enumerate(bookmakers):
            for observation_index, offset in enumerate(offsets):
                base = Decimal("2.00") + Decimal(book_index) / Decimal("10")
                if book_index == 3:
                    home = Decimal("2.30")
                    draw = Decimal("3.00")
                    away = Decimal("3.50")
                else:
                    home = base + Decimal(observation_index) / Decimal("100")
                    draw = (
                        Decimal("3.00")
                        + Decimal((book_index + 1) % 4) / Decimal("10")
                        + Decimal(observation_index) / Decimal("100")
                    )
                    away = Decimal("3.80") - Decimal(book_index) / Decimal("10")
                observations.append(
                    OddsObservation.objects.create(
                        match=match,
                        source=source,
                        bookmaker=bookmaker,
                        market=market,
                        home=home,
                        draw=draw,
                        away=away,
                        provider_updated_at=(
                            None if book_index == 3 else match.kickoff - offset
                        ),
                        observed_at=match.kickoff - offset,
                    )
                )
    return source, market, bookmakers, observations
