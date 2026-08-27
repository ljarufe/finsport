import math

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django_countries.fields import CountryField
from django_extensions.db.models import TimeStampedModel

PROBABILITY_TOLERANCE = 1e-6


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


class OddsObservation(models.Model):
    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="odds_observations"
    )
    source = models.ForeignKey(
        Source, on_delete=models.PROTECT, related_name="odds_observations"
    )
    bookmaker = models.ForeignKey(
        Bookmaker, on_delete=models.PROTECT, related_name="odds_observations"
    )
    market = models.ForeignKey(
        OddsMarket, on_delete=models.PROTECT, related_name="odds_observations"
    )
    home = models.DecimalField(max_digits=10, decimal_places=4)
    draw = models.DecimalField(max_digits=10, decimal_places=4)
    away = models.DecimalField(max_digits=10, decimal_places=4)
    provider_updated_at = models.DateTimeField(null=True, blank=True)
    observed_at = models.DateTimeField()

    def __str__(self):
        return f"{self.match} — {self.bookmaker} observed @ {self.observed_at}"

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
                fields=["match", "source", "bookmaker", "market", "observed_at"],
                name="football_odds_observation_identity_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=["match", "observed_at"],
                name="football_odds_match_obs_idx",
            ),
            models.Index(
                fields=["match", "source", "bookmaker", "market", "observed_at"],
                name="football_odds_asof_idx",
            ),
        ]
        ordering = ("-observed_at", "id")


class PredictionExperiment(TimeStampedModel):
    MODE_BACKTEST = "BACKTEST"
    MODE_PROSPECTIVE = "PROSPECTIVE"
    MODES = (
        (MODE_BACKTEST, "Backtest"),
        (MODE_PROSPECTIVE, "Prospective"),
    )

    competition = models.ForeignKey(
        Competition, on_delete=models.PROTECT, related_name="prediction_experiments"
    )
    mode = models.CharField(max_length=12, choices=MODES)
    period_start = models.DateField()
    period_end = models.DateField()
    engine_version = models.CharField(max_length=50, default="fs003-v1")
    config = models.JSONField(default=dict)
    summary = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return (
            f"{self.competition} {self.mode} " f"{self.period_start}..{self.period_end}"
        )

    class Meta:
        ordering = ("-created",)


class Prediction(TimeStampedModel):
    DIXON_COLES = "DIXON_COLES"
    INDEPENDENT_POISSON = "INDEPENDENT_POISSON"
    ELO_MULTINOMIAL_LOGIT = "ELO_MULTINOMIAL_LOGIT"
    MARKET_CONSENSUS = "MARKET_CONSENSUS"
    MODERNIZED_R45 = "MODERNIZED_R45"
    MODEL_CODES = (
        (DIXON_COLES, "Dixon-Coles"),
        (INDEPENDENT_POISSON, "Independent Poisson"),
        (ELO_MULTINOMIAL_LOGIT, "Elo multinomial logit"),
        (MARKET_CONSENSUS, "Market consensus"),
        (MODERNIZED_R45, "Modernized R45"),
    )

    experiment = models.ForeignKey(
        PredictionExperiment, on_delete=models.CASCADE, related_name="predictions"
    )
    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="predictions"
    )
    model_code = models.CharField(max_length=30, choices=MODEL_CODES)
    variant = models.CharField(max_length=20, blank=True)
    model_version = models.CharField(max_length=100)
    model_config = models.JSONField(default=dict)
    cutoff = models.DateTimeField()
    p_home = models.FloatField()
    p_draw = models.FloatField()
    p_away = models.FloatField()
    predicted_outcome = models.CharField(max_length=4, choices=Match.OUTCOMES)
    diagnostics = models.JSONField(default=dict, blank=True)
    evaluated_at = models.DateTimeField(null=True, blank=True)
    actual_outcome = models.CharField(
        max_length=4, choices=Match.OUTCOMES, null=True, blank=True
    )

    def clean(self):
        super().clean()
        probabilities = (self.p_home, self.p_draw, self.p_away)
        if not all(math.isfinite(value) and 0 <= value <= 1 for value in probabilities):
            raise ValidationError("Probabilities must be finite and between 0 and 1.")
        if abs(sum(probabilities) - 1) > PROBABILITY_TOLERANCE:
            raise ValidationError("Probabilities must sum to one.")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["experiment", "match", "model_code", "variant"],
                name="football_prediction_logical_identity_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(p_home__gte=0)
                    & Q(p_home__lte=1)
                    & Q(p_draw__gte=0)
                    & Q(p_draw__lte=1)
                    & Q(p_away__gte=0)
                    & Q(p_away__lte=1)
                ),
                name="football_prediction_probability_bounds",
            ),
        ]
        ordering = ("cutoff", "match_id", "model_code", "variant")


class Decision(TimeStampedModel):
    ACTION_NO_BET = "NO_BET"
    ACTIONS = (*Match.OUTCOMES, (ACTION_NO_BET, "No bet"))

    experiment = models.ForeignKey(
        PredictionExperiment, on_delete=models.CASCADE, related_name="decisions"
    )
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="decisions")
    prediction = models.ForeignKey(
        Prediction,
        on_delete=models.CASCADE,
        related_name="decisions",
        null=True,
        blank=True,
    )
    policy_code = models.CharField(max_length=30)
    policy_variant = models.CharField(max_length=30, blank=True)
    policy_version = models.CharField(max_length=100)
    policy_config = models.JSONField(default=dict, blank=True)
    decision_time = models.DateTimeField()
    action = models.CharField(max_length=6, choices=ACTIONS)
    reason = models.CharField(max_length=100)
    model_probability = models.FloatField(null=True, blank=True)
    selected_odds_observation = models.ForeignKey(
        OddsObservation,
        on_delete=models.PROTECT,
        related_name="decisions",
        null=True,
        blank=True,
    )
    selected_price = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    expected_value = models.FloatField(null=True, blank=True)

    def clean(self):
        super().clean()
        errors = {}
        if self.model_probability is not None and (
            not math.isfinite(self.model_probability)
            or not 0 <= self.model_probability <= 1
        ):
            errors["model_probability"] = (
                "Model probability must be finite and between zero and one."
            )
        if self.expected_value is not None and not math.isfinite(self.expected_value):
            errors["expected_value"] = "Expected value must be finite."
        if self.prediction_id:
            if self.prediction.experiment_id != self.experiment_id:
                errors["prediction"] = "Prediction must belong to this experiment."
            if self.prediction.match_id != self.match_id:
                errors["prediction"] = "Prediction must belong to this match."
        if self.selected_odds_observation_id:
            observation = self.selected_odds_observation
            if observation.match_id != self.match_id:
                errors["selected_odds_observation"] = (
                    "Selected odds must belong to this match."
                )
            if self.action in dict(Match.OUTCOMES) and self.selected_price is not None:
                expected_price = getattr(
                    self.selected_odds_observation, self.action.lower()
                )
                if self.selected_price != expected_price:
                    errors["selected_price"] = (
                        "Selected price must match the selected observation."
                    )
        if errors:
            raise ValidationError(errors)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "experiment",
                    "match",
                    "prediction",
                    "policy_code",
                    "policy_variant",
                ],
                name="football_decision_logical_identity_unique",
                nulls_distinct=False,
            )
        ]
        ordering = ("decision_time", "match_id", "policy_code", "policy_variant")


class CapitalExperiment(TimeStampedModel):
    MODE_REPLAY = "REPLAY"
    MODE_MONTE_CARLO = "MONTE_CARLO"
    MODE_STRESS = "STRESS"
    MODES = (
        (MODE_REPLAY, "Deterministic replay"),
        (MODE_MONTE_CARLO, "Monte Carlo"),
        (MODE_STRESS, "Stress"),
    )

    source_experiment = models.ForeignKey(
        PredictionExperiment,
        on_delete=models.PROTECT,
        related_name="capital_experiments",
    )
    source_model_code = models.CharField(max_length=30, blank=True)
    source_model_variant = models.CharField(max_length=20, blank=True)
    source_comparator_code = models.CharField(max_length=30, blank=True)
    decision_policy_code = models.CharField(max_length=30)
    decision_policy_variant = models.CharField(max_length=30, blank=True)
    engine_version = models.CharField(max_length=50, default="fs004-v1")
    mode = models.CharField(max_length=12, choices=MODES)
    initial_bankroll = models.DecimalField(max_digits=24, decimal_places=8)
    config = models.JSONField(default=dict)
    input_count = models.PositiveIntegerField(default=0)
    input_hash = models.CharField(max_length=64)
    input_manifest = models.JSONField(default=dict)
    completed_at = models.DateTimeField(null=True, blank=True)
    summary = models.JSONField(default=dict, blank=True)

    def __str__(self):
        source = self.source_model_code or self.source_comparator_code
        return f"{self.mode} {source}/{self.decision_policy_code} ({self.pk})"

    class Meta:
        ordering = ("-created",)
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(source_model_code="", source_comparator_code__gt="")
                    | Q(source_model_code__gt="", source_comparator_code="")
                ),
                name="football_capital_experiment_one_source_identity",
            ),
            models.CheckConstraint(
                condition=Q(initial_bankroll__gt=0),
                name="football_capital_experiment_positive_bankroll",
            ),
        ]


class CapitalPolicyRun(TimeStampedModel):
    STATUS_PRODUCED = "PRODUCED"
    STATUS_UNAVAILABLE = "UNAVAILABLE"
    STATUS_FAILED = "FAILED"
    STATUSES = (
        (STATUS_PRODUCED, "Produced"),
        (STATUS_UNAVAILABLE, "Unavailable"),
        (STATUS_FAILED, "Failed"),
    )

    experiment = models.ForeignKey(
        CapitalExperiment, on_delete=models.CASCADE, related_name="policy_runs"
    )
    policy_code = models.CharField(max_length=40)
    policy_version = models.CharField(max_length=100)
    policy_config = models.JSONField(default=dict)
    status = models.CharField(max_length=12, choices=STATUSES)
    reason = models.CharField(max_length=120, blank=True)
    seed = models.BigIntegerField(null=True, blank=True)
    path_count = models.PositiveIntegerField(null=True, blank=True)
    metrics = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.policy_code} {self.status} ({self.pk})"

    class Meta:
        ordering = ("experiment_id", "id")


class CapitalLedgerEntry(models.Model):
    policy_run = models.ForeignKey(
        CapitalPolicyRun, on_delete=models.CASCADE, related_name="ledger_entries"
    )
    source_decision = models.ForeignKey(
        Decision, on_delete=models.PROTECT, related_name="capital_ledger_entries"
    )
    batch_time = models.DateTimeField()
    batch_index = models.PositiveIntegerField()
    step = models.PositiveIntegerField(null=True, blank=True)
    requested_stake = models.DecimalField(max_digits=24, decimal_places=8)
    applied_stake = models.DecimalField(max_digits=24, decimal_places=8)
    bankroll_before = models.DecimalField(max_digits=24, decimal_places=8)
    bankroll_after = models.DecimalField(max_digits=24, decimal_places=8)
    profit_loss = models.DecimalField(max_digits=24, decimal_places=8)
    action_snapshot = models.CharField(max_length=6)
    outcome_snapshot = models.CharField(max_length=4, blank=True)
    price_snapshot = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    capital_reason = models.CharField(max_length=120, blank=True)
    policy_state = models.JSONField(default=dict, blank=True)
    cap_hit = models.BooleanField(default=False)
    shortfall = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    practical_ruin = models.BooleanField(default=False)
    termination_reason = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ("policy_run_id", "batch_index", "source_decision_id")
        constraints = [
            models.UniqueConstraint(
                fields=["policy_run", "source_decision"],
                name="football_capital_ledger_run_decision_unique",
            )
        ]
