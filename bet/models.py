# -*- coding: utf-8 -*-

from django.db import models

from django_extensions.db.models import TimeStampedModel


class BetTable(TimeStampedModel):
    """
    Bet table
    """

    AVAILABLE = 'A'
    FINISHED = 'F'
    STATES = (
        ('A', 'available'),
        ('F', 'finished'),
    )
    name = models.CharField(max_length=250)
    total_profit = models.FloatField(default=0)
    total_inversion = models.FloatField(default=0)
    state = models.CharField(max_length=1, choices=STATES, default=AVAILABLE)
    bucle_number = models.IntegerField(default=0)

    def __str__(self):
        return '%s' % self.name


class MyManager(models.Manager):
    def get_queryset(self):
        return super(MyManager, self).get_queryset().select_related(
            'match__local_team', 'match__visitor_team', 'bet_table')


# TODO: It might be the match for an account, relate to it or delete all this
#   logic
class DataTable(TimeStampedModel):
    NEW = 'N'
    CURRENT = 'C'
    WON = 'W'
    LOST = 'L'
    WAITING = 'T'
    STATES = (
        ('N', 'new'),
        ('C', 'current'),
        ('W', 'won'),
        ('L', 'lost'),
        ('T', 'waiting'),
    )
    match = models.ForeignKey('football.Match', on_delete=models.CASCADE)
    bet_table = models.ForeignKey('bet.BetTable', on_delete=models.CASCADE)
    bet_amount = models.FloatField(default=0)
    inversion_amount = models.FloatField(default=0)
    profit = models.FloatField(null=True, default=0)
    state = models.CharField(max_length=1, choices=STATES, default=NEW)
    previous = models.ForeignKey(
        'bet.DataTable', on_delete=models.CASCADE,
        related_name='previous_data', null=True, blank=True)
    objects = MyManager()

    def __str__(self):
        return '(%s) - %s - %s . BET TABLE: %s' % (
            self.match.start_datetime,
            self.match.local_team.name,
            self.match.visitor_team.name,
            self.bet_table.name
        )
