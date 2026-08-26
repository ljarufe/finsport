from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from .country_mapping import country_code, normalized_text
from .models import (
    Bookmaker,
    Competition,
    CompetitionSourceRef,
    Match,
    MatchSourceRef,
    OddsMarket,
    OddsObservation,
    OddsSnapshot,
    ReconciliationStatus,
    Season,
    Source,
    Team,
    TeamSourceRef,
)

API_FOOTBALL_CODE = "api_football"
API_FOOTBALL_NAME = "API-Football"
API_FOOTBALL_BASE_URL = "https://v3.football.api-sports.io/"
INKABET_CODE = "inkabet"
INKABET_NAME = "Inkabet"
INKABET_BASE_URL = "https://d-cf.inkabetplayground.net/api/sb/v1/"
FINISHED_STATUSES = {"FT", "AET", "PEN", "AWD", "WO"}
MATCH_WINNER_NAMES = {"match winner", "1x2"}


class FootballSyncError(Exception):
    pass


@dataclass
class SyncStats:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    pending_competitions: int = 0
    pending_teams: int = 0
    pending_matches: int = 0

    def add(self, result):
        setattr(self, result, getattr(self, result) + 1)

    def merge(self, other):
        self.created += other.created
        self.updated += other.updated
        self.unchanged += other.unchanged
        self.skipped += other.skipped
        self.pending_competitions += other.pending_competitions
        self.pending_teams += other.pending_teams
        self.pending_matches += other.pending_matches

    @property
    def reconciliation_required(self):
        return any(
            (
                self.pending_competitions,
                self.pending_teams,
                self.pending_matches,
            )
        )


def get_api_football_source():
    source, _ = Source.objects.get_or_create(
        code=API_FOOTBALL_CODE,
        defaults={"name": API_FOOTBALL_NAME, "base_url": API_FOOTBALL_BASE_URL},
    )
    return source


def get_inkabet_source():
    source, _ = Source.objects.get_or_create(
        code=INKABET_CODE,
        defaults={"name": INKABET_NAME, "base_url": INKABET_BASE_URL},
    )
    return source


def _upsert(model, lookup, defaults):
    instance, created = model.objects.get_or_create(**lookup, defaults=defaults)
    if created:
        return instance, "created"
    changed = []
    for field, value in defaults.items():
        if getattr(instance, field) != value:
            setattr(instance, field, value)
            changed.append(field)
    if changed:
        instance.full_clean()
        instance.save(update_fields=[*changed, "modified"])
        return instance, "updated"
    return instance, "unchanged"


def _parse_provider_date(value):
    return parse_date(value) if value else None


def _parse_provider_datetime(value):
    parsed = parse_datetime(value) if value else None
    if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _resolved_ref(ref, canonical_field):
    return (
        ref is not None
        and ref.reconciliation_status == ReconciliationStatus.RESOLVED
        and getattr(ref, f"{canonical_field}_id") is not None
    )


def _mark_resolved_ref(ref, canonical_field, canonical, **defaults):
    changed = []
    values = {
        canonical_field: canonical,
        "reconciliation_status": ReconciliationStatus.RESOLVED,
        "confidence": Decimal("1.0000"),
        "last_seen_at": timezone.now(),
        **defaults,
    }
    for field, value in values.items():
        if getattr(ref, field) != value:
            setattr(ref, field, value)
            changed.append(field)
    ref.full_clean()
    if ref.pk:
        if changed:
            ref.save(update_fields=changed)
    else:
        ref.save()
    return ref


def _canonical_competition_for_api(source, league, country):
    external_id = str(league["id"])
    ref = (
        CompetitionSourceRef.objects.filter(source=source, external_id=external_id)
        .select_related("competition")
        .first()
    )
    canonical_country = country_code(country.get("name"), country.get("code"))
    if _resolved_ref(ref, "competition"):
        return ref.competition, ref

    candidates = Competition.objects.filter(
        country=canonical_country,
        competition_type=league.get("type") or "",
    )
    normalized_name = normalized_text(league["name"])
    competition = next(
        (
            candidate
            for candidate in candidates
            if normalized_text(candidate.name) == normalized_name
        ),
        None,
    )
    if competition is None:
        competition = Competition.objects.create(
            name=league["name"],
            competition_type=league.get("type") or "",
            country=canonical_country,
        )
        result = "created"
    else:
        result = "unchanged"
    if ref is None:
        ref = CompetitionSourceRef(source=source, external_id=external_id)
    _mark_resolved_ref(
        ref,
        "competition",
        competition,
        external_name=league["name"],
        context={
            "country_name": country.get("name") or "",
            "country_code": country.get("code") or "",
        },
    )
    return competition, ref, result


@transaction.atomic
def sync_catalog_payloads(leagues, bets):
    source = get_api_football_source()
    stats = SyncStats()
    for item in leagues:
        league = item.get("league") or {}
        country = item.get("country") or {}
        if league.get("id") is None or not league.get("name"):
            stats.skipped += 1
            continue
        result = None
        resolved = _canonical_competition_for_api(source, league, country)
        if len(resolved) == 3:
            competition, ref, result = resolved
        else:
            competition, ref = resolved
        canonical_defaults = {
            "name": league["name"],
            "competition_type": league.get("type") or "",
            "country": country_code(country.get("name"), country.get("code")),
        }
        changed = [
            field
            for field, value in canonical_defaults.items()
            if getattr(competition, field) != value
        ]
        if changed:
            for field in changed:
                setattr(competition, field, canonical_defaults[field])
            competition.full_clean()
            competition.save(update_fields=[*changed, "modified"])
            result = "updated"
        stats.add(result or "unchanged")

        if ref.external_name != league["name"]:
            ref.external_name = league["name"]
            ref.last_seen_at = timezone.now()
            ref.save(update_fields=["external_name", "last_seen_at"])

        for season_data in item.get("seasons") or []:
            year = season_data.get("year")
            if year is None:
                stats.skipped += 1
                continue
            _, result = _upsert(
                Season,
                {"competition": competition, "year": year},
                {
                    "start_date": _parse_provider_date(season_data.get("start")),
                    "end_date": _parse_provider_date(season_data.get("end")),
                    "is_current": bool(season_data.get("current")),
                    "coverage": season_data.get("coverage") or {},
                },
            )
            stats.add(result)

    match_winner = None
    for bet in bets:
        name = str(bet.get("name") or "").strip()
        if name.casefold() not in MATCH_WINNER_NAMES or bet.get("id") is None:
            continue
        match_winner, result = _upsert(
            OddsMarket,
            {"source": source, "external_id": str(bet["id"])},
            {"name": name},
        )
        stats.add(result)
        break
    if match_winner is None:
        raise FootballSyncError(
            "API-Football odds catalogue did not contain Match Winner / 1X2."
        )
    return stats, match_winner


def _team_from_fixture(source, competition, data, stats):
    external_id = data.get("id")
    name = data.get("name")
    if external_id is None or not name:
        raise FootballSyncError("Fixture team identity is incomplete.")
    external_id = str(external_id)
    ref = (
        TeamSourceRef.objects.filter(source=source, external_id=external_id)
        .select_related("team")
        .first()
    )
    if _resolved_ref(ref, "team"):
        team = ref.team
        if team.competition_id != competition.id:
            raise FootballSyncError(
                f"Team {external_id} is already assigned to a different tracked competition."
            )
        defaults = {
            "name": name,
            "code": data.get("code") or "",
            "is_active": True,
        }
        changed = [
            field for field, value in defaults.items() if getattr(team, field) != value
        ]
        if changed:
            for field in changed:
                setattr(team, field, defaults[field])
            team.full_clean()
            team.save(update_fields=[*changed, "modified"])
            stats.updated += 1
        else:
            stats.unchanged += 1
        ref.external_name = name
        ref.last_seen_at = timezone.now()
        ref.save(update_fields=["external_name", "last_seen_at"])
        return team

    normalized_name = normalized_text(name)
    team = next(
        (
            candidate
            for candidate in competition.teams.all()
            if normalized_text(candidate.name) == normalized_name
        ),
        None,
    )
    if team is None:
        team = Team.objects.create(
            competition=competition,
            name=name,
            code=data.get("code") or "",
            is_active=True,
        )
        stats.created += 1
    else:
        stats.unchanged += 1
    if ref is None:
        ref = TeamSourceRef(
            source=source,
            external_id=external_id,
            competition=competition,
        )
    elif ref.competition_id != competition.id:
        raise FootballSyncError(
            f"Team {external_id} is already assigned to a different tracked competition."
        )
    _mark_resolved_ref(ref, "team", team, external_name=name)
    return team


def _score_pair(score, period):
    values = (score or {}).get(period) or {}
    return values.get("home"), values.get("away")


def _fixture_outcome(item, status_short):
    if status_short not in FINISHED_STATUSES:
        return ""
    teams = item.get("teams") or {}
    home_winner = (teams.get("home") or {}).get("winner")
    away_winner = (teams.get("away") or {}).get("winner")
    if home_winner is True:
        return Match.OUTCOME_HOME
    if away_winner is True:
        return Match.OUTCOME_AWAY
    goals = item.get("goals") or {}
    home_score = goals.get("home")
    away_score = goals.get("away")
    if home_score is not None and away_score is not None:
        if home_score > away_score:
            return Match.OUTCOME_HOME
        if away_score > home_score:
            return Match.OUTCOME_AWAY
        return Match.OUTCOME_DRAW
    if home_winner is False and away_winner is False:
        return Match.OUTCOME_DRAW
    return ""


def _match_defaults(item, season, home_team, away_team, observed_at):
    fixture = item.get("fixture") or {}
    status = fixture.get("status") or {}
    goals = item.get("goals") or {}
    score = item.get("score") or {}
    halftime = _score_pair(score, "halftime")
    fulltime = _score_pair(score, "fulltime")
    extratime = _score_pair(score, "extratime")
    penalties = _score_pair(score, "penalty")
    kickoff = _parse_provider_datetime(fixture.get("date"))
    if kickoff is None:
        raise FootballSyncError("Fixture kickoff is missing or invalid.")
    status_short = status.get("short") or ""
    return {
        "season": season,
        "home_team": home_team,
        "away_team": away_team,
        "kickoff": kickoff,
        "kickoff_timezone": fixture.get("timezone") or "",
        "status_short": status_short,
        "status_long": status.get("long") or "",
        "outcome": _fixture_outcome(item, status_short),
        "home_score": goals.get("home"),
        "away_score": goals.get("away"),
        "halftime_home_score": halftime[0],
        "halftime_away_score": halftime[1],
        "fulltime_home_score": fulltime[0],
        "fulltime_away_score": fulltime[1],
        "extratime_home_score": extratime[0],
        "extratime_away_score": extratime[1],
        "penalties_home_score": penalties[0],
        "penalties_away_score": penalties[1],
        "observed_at": observed_at,
    }


@transaction.atomic
def sync_fixture_payloads(payloads, competitions_by_external_id, expected_year=None):
    source = get_api_football_source()
    stats = SyncStats()
    accepted = {}
    observed_at = timezone.now()
    normalized_competitions = {
        str(external_id): competition
        for external_id, competition in competitions_by_external_id.items()
    }
    for item in payloads:
        fixture = item.get("fixture") or {}
        league = item.get("league") or {}
        external_id = fixture.get("id")
        league_id = league.get("id")
        year = league.get("season")
        competition = normalized_competitions.get(str(league_id))
        if (
            external_id is None
            or competition is None
            or year is None
            or (expected_year is not None and year != expected_year)
        ):
            stats.skipped += 1
            continue
        season = Season.objects.filter(competition=competition, year=year).first()
        if season is None:
            raise FootballSyncError(
                f"Season {year} is missing for Competition {competition.id}; "
                "run sync_football_catalog first."
            )
        teams = item.get("teams") or {}
        home_team = _team_from_fixture(
            source, competition, teams.get("home") or {}, stats
        )
        away_team = _team_from_fixture(
            source, competition, teams.get("away") or {}, stats
        )
        defaults = _match_defaults(item, season, home_team, away_team, observed_at)
        external_id = str(external_id)
        ref = (
            MatchSourceRef.objects.filter(source=source, external_id=external_id)
            .select_related("match__season")
            .first()
        )
        if _resolved_ref(ref, "match"):
            match = ref.match
            if match.season.competition_id != competition.id:
                raise FootballSyncError(
                    f"Fixture {external_id} is mapped to a different competition."
                )
        else:
            match = Match.objects.filter(
                season=season,
                home_team=home_team,
                away_team=away_team,
                kickoff=defaults["kickoff"],
            ).first()
            if match is None:
                match = Match(**defaults)
                match.full_clean()
                match.save()
                stats.created += 1
                result = "created"
            else:
                result = "unchanged"
            if ref is None:
                ref = MatchSourceRef(source=source, external_id=external_id)
            _mark_resolved_ref(
                ref,
                "match",
                match,
                external_label=f"{home_team.name} - {away_team.name}",
                context={"league_id": str(league_id), "season": year},
            )
            if result == "created":
                accepted[external_id] = match
                continue

        business_fields = [field for field in defaults if field != "observed_at"]
        changed = [
            field
            for field in business_fields
            if getattr(match, field) != defaults[field]
        ]
        for field in [*changed, "observed_at"]:
            setattr(match, field, defaults[field])
        if changed:
            match.full_clean()
            match.save(update_fields=[*changed, "observed_at", "modified"])
            stats.updated += 1
        else:
            Match.objects.filter(pk=match.pk).update(observed_at=observed_at)
            stats.unchanged += 1
        ref.external_label = f"{home_team.name} - {away_team.name}"
        ref.last_seen_at = observed_at
        ref.save(update_fields=["external_label", "last_seen_at"])
        accepted[external_id] = match
    return stats, accepted


def _decimal_odds(values, labels):
    by_name = {
        str(value.get("value") or "").strip().casefold(): value.get("odd")
        for value in values
    }
    parsed = []
    for alternatives in labels:
        raw = next((by_name[name] for name in alternatives if name in by_name), None)
        if raw is None:
            return None
        try:
            value = Decimal(str(raw))
        except InvalidOperation:
            return None
        if not value.is_finite() or value <= 1:
            return None
        parsed.append(value)
    return tuple(parsed)


def upsert_current_odds(
    *,
    match,
    source,
    bookmaker,
    market,
    prices,
    provider_updated_at=None,
    observed_at=None,
):
    observed_at = observed_at or timezone.now()
    observation, _ = OddsObservation.objects.get_or_create(
        match=match,
        source=source,
        bookmaker=bookmaker,
        market=market,
        observed_at=observed_at,
        defaults={
            "home": prices[0],
            "draw": prices[1],
            "away": prices[2],
            "provider_updated_at": provider_updated_at,
        },
    )
    observation.full_clean()
    snapshot = OddsSnapshot.objects.filter(
        match=match,
        source=source,
        bookmaker=bookmaker,
        market=market,
    ).first()
    if snapshot is None:
        snapshot = OddsSnapshot(
            match=match,
            source=source,
            bookmaker=bookmaker,
            market=market,
            home=prices[0],
            draw=prices[1],
            away=prices[2],
            provider_updated_at=provider_updated_at,
            observed_at=observed_at,
        )
        snapshot.full_clean()
        snapshot.save()
        return snapshot, "created"
    changed = any(
        (
            snapshot.home != prices[0],
            snapshot.draw != prices[1],
            snapshot.away != prices[2],
            snapshot.provider_updated_at != provider_updated_at,
        )
    )
    snapshot.home, snapshot.draw, snapshot.away = prices
    snapshot.provider_updated_at = provider_updated_at
    snapshot.observed_at = observed_at
    snapshot.full_clean()
    snapshot.save(
        update_fields=[
            "home",
            "draw",
            "away",
            "provider_updated_at",
            "observed_at",
        ]
    )
    return snapshot, "updated" if changed else "unchanged"


@transaction.atomic
def sync_odds_payloads(payloads, matches_by_external_id, market):
    source = get_api_football_source()
    stats = SyncStats()
    observed_at = timezone.now()
    labels = (("home", "1"), ("draw", "x"), ("away", "2"))
    normalized_matches = {
        str(external_id): match for external_id, match in matches_by_external_id.items()
    }
    for item in payloads:
        fixture_id = (item.get("fixture") or {}).get("id")
        match = normalized_matches.get(str(fixture_id))
        if match is None:
            stats.skipped += 1
            continue
        provider_updated_at = _parse_provider_datetime(item.get("update"))
        for bookmaker_data in item.get("bookmakers") or []:
            bookmaker_id = bookmaker_data.get("id")
            bookmaker_name = bookmaker_data.get("name")
            if bookmaker_id is None or not bookmaker_name:
                stats.skipped += 1
                continue
            bookmaker, result = _upsert(
                Bookmaker,
                {"source": source, "external_id": str(bookmaker_id)},
                {"name": bookmaker_name},
            )
            stats.add(result)
            for bet in bookmaker_data.get("bets") or []:
                if str(bet.get("id")) != market.external_id:
                    continue
                prices = _decimal_odds(bet.get("values") or [], labels)
                if prices is None:
                    stats.skipped += 1
                    continue
                _, result = upsert_current_odds(
                    match=match,
                    source=source,
                    bookmaker=bookmaker,
                    market=market,
                    prices=prices,
                    provider_updated_at=provider_updated_at,
                    observed_at=observed_at,
                )
                stats.add(result)
    return stats


def validate_sync_date(value):
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValidationError("Date must use YYYY-MM-DD format.") from error
