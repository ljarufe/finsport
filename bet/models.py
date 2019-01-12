# -*- coding: utf-8 -*-

from django.db import models
from django_extensions.db.models import TimeStampedModel


class BetTable(TimeStampedModel):
    AVAILABLE = 'A'
    FINISHED = 'F'
    PAUSED = 'P'
    STATES = (
        ('A', 'available'),
        ('F', 'finished'),
        ('P', 'paused'),
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


class DataTable(TimeStampedModel):
    STATES = (
        (0, 'new'),
        (1, 'current'),
        (2, 'won'),
        (3, 'lost'),
        (4, 'waiting'),
        (5, 'paused'),
        (6, 'current_paused'),
    )
    match = models.ForeignKey('football.Match', on_delete=models.CASCADE)
    bet_table = models.ForeignKey('bet.BetTable', on_delete=models.CASCADE)
    bet_amount = models.FloatField(default=0)
    inversion_amount = models.FloatField(default=0)
    profit = models.FloatField(null=True, default=0)
    state = models.IntegerField(choices=STATES, default=STATES[0][0])
    previous = models.ForeignKey(
        'bet.DataTable', on_delete=models.CASCADE,
        related_name='previous_data', null=True, blank=True, default=None)
    objects = MyManager()

    def __str__(self):

        return '(%s) - %s - %s . BET TABLE: %s' % (
            self.match.start_datetime,
            self.match.local_team.name,
            self.match.visitor_team.name,
            self.bet_table.name
        )
