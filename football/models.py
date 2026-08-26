from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django_countries.fields import CountryField
from django_extensions.db.models import TimeStampedModel


class Source(TimeStampedModel):
    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    base_url = models.URLField()

    def __str__(self):
        return self.name


class Competition(TimeStampedModel):
    name = models.CharField(max_length=250)
    competition_type = models.CharField(max_length=50)
    country = CountryField(blank=True, blank_label="(international / no country)")
    enabled = models.BooleanField(default=False)

    def __str__(self):
        country_name = self.country.name if self.country else "International"
        return f"{country_name} — {self.name}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["country", "name", "competition_type"],
                name="football_competition_country_name_type_unique",
            )
        ]
        ordering = ("country", "name")


class Season(TimeStampedModel):
    competition = models.ForeignKey(
        Competition, on_delete=models.CASCADE, related_name="seasons"
    )
    year = models.PositiveSmallIntegerField()
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    coverage = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.competition} {self.year}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition", "year"],
                name="football_season_competition_year_unique",
            )
        ]
        ordering = ("competition", "-year")


class Team(TimeStampedModel):
    competition = models.ForeignKey(
        Competition, on_delete=models.PROTECT, related_name="teams"
    )
    name = models.CharField(max_length=250)
    code = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.competition.name})"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition", "name"],
                name="football_team_competition_name_unique",
            )
        ]
        ordering = ("name",)


class MatchQuerySet(models.QuerySet):
    def upcoming(self, from_time=None):
        return self.filter(
            kickoff__gte=from_time or timezone.now(), status_short__in=("TBD", "NS")
        )


class Match(TimeStampedModel):
    OUTCOME_HOME = "HOME"
    OUTCOME_DRAW = "DRAW"
    OUTCOME_AWAY = "AWAY"
    OUTCOMES = (
        (OUTCOME_HOME, "Home"),
        (OUTCOME_DRAW, "Draw"),
        (OUTCOME_AWAY, "Away"),
    )

    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name="matches")
    home_team = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name="home_matches"
    )
    away_team = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name="away_matches"
    )
    kickoff = models.DateTimeField()
    kickoff_timezone = models.CharField(max_length=50, blank=True)
    status_short = models.CharField(max_length=10)
    status_long = models.CharField(max_length=100)
    outcome = models.CharField(max_length=4, choices=OUTCOMES, blank=True)
    home_score = models.PositiveSmallIntegerField(null=True, blank=True)
    away_score = models.PositiveSmallIntegerField(null=True, blank=True)
    halftime_home_score = models.PositiveSmallIntegerField(null=True, blank=True)
    halftime_away_score = models.PositiveSmallIntegerField(null=True, blank=True)
    fulltime_home_score = models.PositiveSmallIntegerField(null=True, blank=True)
    fulltime_away_score = models.PositiveSmallIntegerField(null=True, blank=True)
    extratime_home_score = models.PositiveSmallIntegerField(null=True, blank=True)
    extratime_away_score = models.PositiveSmallIntegerField(null=True, blank=True)
    penalties_home_score = models.PositiveSmallIntegerField(null=True, blank=True)
    penalties_away_score = models.PositiveSmallIntegerField(null=True, blank=True)
    observed_at = models.DateTimeField(default=timezone.now)

    objects = MatchQuerySet.as_manager()

    @property
    def competition(self):
        return self.season.competition

    def __str__(self):
        return f"{self.home_team.name} - {self.away_team.name}, {self.kickoff}"

    def clean(self):
        errors = {}
        if self.home_team_id and self.away_team_id:
            if self.home_team_id == self.away_team_id:
                errors["away_team"] = "Home and away teams must be different."
        if self.season_id and self.home_team_id:
            competition_id = self.season.competition_id
            if self.home_team.competition_id != competition_id:
                errors["home_team"] = "Home team must belong to the match competition."
            if self.away_team_id and self.away_team.competition_id != competition_id:
                errors["away_team"] = "Away team must belong to the match competition."
        if errors:
            raise ValidationError(errors)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["season", "home_team", "away_team", "kickoff"],
                name="football_match_canonical_identity_unique",
            ),
            models.CheckConstraint(
                condition=~Q(home_team=models.F("away_team")),
                name="football_match_distinct_teams",
            ),
        ]
        ordering = ("-kickoff",)


class ReconciliationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RESOLVED = "RESOLVED", "Resolved"


class SourceRefFields(models.Model):
    external_id = models.CharField(max_length=150)
    reconciliation_status = models.CharField(
        max_length=10,
        choices=ReconciliationStatus.choices,
        default=ReconciliationStatus.PENDING,
    )
    confidence = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        abstract = True


class CompetitionSourceRef(SourceRefFields):
    external_name = models.CharField(max_length=250, blank=True)
    source = models.ForeignKey(
        Source, on_delete=models.CASCADE, related_name="competition_refs"
    )
    competition = models.ForeignKey(
        Competition,
        on_delete=models.CASCADE,
        related_name="source_refs",
        null=True,
        blank=True,
    )
    proposed_competition = models.ForeignKey(
        Competition,
        on_delete=models.SET_NULL,
        related_name="proposed_source_refs",
        null=True,
        blank=True,
    )
    external_slug = models.CharField(max_length=300, blank=True)
    context = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.source.code}:{self.external_id} — {self.external_name}"

    def clean(self):
        if (
            self.reconciliation_status == ReconciliationStatus.RESOLVED
            and not self.competition_id
        ):
            raise ValidationError(
                "A resolved CompetitionSourceRef needs a competition."
            )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                name="football_competition_ref_source_external_unique",
            ),
            models.UniqueConstraint(
                fields=["source", "competition"],
                condition=Q(competition__isnull=False),
                name="football_competition_ref_source_canonical_unique",
            ),
        ]


class TeamSourceRef(SourceRefFields):
    external_name = models.CharField(max_length=250, blank=True)
    source = models.ForeignKey(
        Source, on_delete=models.CASCADE, related_name="team_refs"
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="source_refs",
        null=True,
        blank=True,
    )
    proposed_team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        related_name="proposed_source_refs",
        null=True,
        blank=True,
    )
    competition = models.ForeignKey(
        Competition, on_delete=models.CASCADE, related_name="team_source_refs"
    )

    def __str__(self):
        return f"{self.source.code}:{self.external_id} — {self.external_name}"

    def clean(self):
        if self.team_id and self.team.competition_id != self.competition_id:
            raise ValidationError("TeamSourceRef must use the team's competition.")
        if (
            self.reconciliation_status == ReconciliationStatus.RESOLVED
            and not self.team_id
        ):
            raise ValidationError("A resolved TeamSourceRef needs a team.")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                name="football_team_ref_source_external_unique",
            ),
            models.UniqueConstraint(
                fields=["source", "team"],
                condition=Q(team__isnull=False),
                name="football_team_ref_source_canonical_unique",
            ),
        ]


class MatchSourceRef(SourceRefFields):
    external_label = models.CharField(max_length=250, blank=True)
    source = models.ForeignKey(
        Source, on_delete=models.CASCADE, related_name="match_refs"
    )
    match = models.ForeignKey(
        Match,
        on_delete=models.CASCADE,
        related_name="source_refs",
        null=True,
        blank=True,
    )
    proposed_match = models.ForeignKey(
        Match,
        on_delete=models.SET_NULL,
        related_name="proposed_source_refs",
        null=True,
        blank=True,
    )
    context = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.source.code}:{self.external_id} — {self.external_label}"

    def clean(self):
        if (
            self.reconciliation_status == ReconciliationStatus.RESOLVED
            and not self.match_id
        ):
            raise ValidationError("A resolved MatchSourceRef needs a match.")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                name="football_match_ref_source_external_unique",
            ),
            models.UniqueConstraint(
                fields=["source", "match"],
                condition=Q(match__isnull=False),
                name="football_match_ref_source_canonical_unique",
            ),
        ]


class Bookmaker(TimeStampedModel):
    source = models.ForeignKey(Source, on_delete=models.PROTECT)
    external_id = models.CharField(max_length=150)
    name = models.CharField(max_length=250)

    def __str__(self):
        return self.name

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                name="football_bookmaker_source_external_unique",
            )
        ]
        ordering = ("name",)


class OddsMarket(TimeStampedModel):
    source = models.ForeignKey(Source, on_delete=models.PROTECT)
    external_id = models.CharField(max_length=150)
    name = models.CharField(max_length=250)

    def __str__(self):
        return self.name

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                name="football_market_source_external_unique",
            )
        ]
        ordering = ("name",)


class OddsSnapshot(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="odds")
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="odds")
    bookmaker = models.ForeignKey(
        Bookmaker, on_delete=models.PROTECT, related_name="odds"
    )
    market = models.ForeignKey(
        OddsMarket, on_delete=models.PROTECT, related_name="odds"
    )
    home = models.DecimalField(max_digits=10, decimal_places=4)
    draw = models.DecimalField(max_digits=10, decimal_places=4)
    away = models.DecimalField(max_digits=10, decimal_places=4)
    provider_updated_at = models.DateTimeField(null=True, blank=True)
    observed_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.match} — {self.bookmaker} @ {self.observed_at}"

    def clean(self):
        if (
            self.source_id
            and self.bookmaker_id
            and self.bookmaker.source_id != self.source_id
        ):
            raise ValidationError("Bookmaker must use the odds source.")
        if (
            self.source_id
            and self.market_id
            and self.market.source_id != self.source_id
        ):
            raise ValidationError("Odds market must use the odds source.")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["match", "source", "bookmaker", "market"],
                name="football_odds_current_value_unique",
            )
        ]
        ordering = ("-observed_at",)
