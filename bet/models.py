from django.db import models
from django_extensions.db.models import TimeStampedModel


class BetTable(TimeStampedModel):
    AVAILABLE = "A"
    FINISHED = "F"
    STATES = (
        (AVAILABLE, "available"),
        (FINISHED, "finished"),
    )

    name = models.CharField(max_length=250)
    total_profit = models.FloatField(default=0)
    total_inversion = models.FloatField(default=0)
    state = models.CharField(max_length=1, choices=STATES, default=AVAILABLE)
    bucle_number = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.id} - {self.name}"


class BetRowManager(models.Manager):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("match__home_team", "match__away_team", "bet_table")
        )


class BetRow(TimeStampedModel):
    NEW = "N"
    CURRENT = "C"
    WON = "W"
    LOST = "L"
    STATES = (
        (NEW, "new"),
        (CURRENT, "current"),
        (WON, "won"),
        (LOST, "lost"),
    )
    match = models.ForeignKey("football.Match", on_delete=models.CASCADE)
    bet_table = models.ForeignKey(
        BetTable, related_name="bet_rows", on_delete=models.CASCADE
    )
    bet_amount = models.FloatField(default=0)
    inversion_amount = models.FloatField(default=0)
    profit = models.FloatField(default=0)
    state = models.CharField(max_length=1, choices=STATES, default=NEW)
    previous = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="previous_data",
        null=True,
        blank=True,
    )
    iteration = models.PositiveSmallIntegerField(default=0)

    objects = BetRowManager()

    def __str__(self):
        return (
            f"{self.match.home_team.name} - {self.match.away_team.name} "
            f"BET TABLE: {self.bet_table}"
        )
