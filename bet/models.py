# -*- coding: utf-8 -*-

from datetime import datetime

from django.conf import settings
from django.db import models

from django_extensions.db.models import TimeStampedModel

from football.models import Match


class BetTable(TimeStampedModel):
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

    @classmethod
    def fill_tables(cls, max_tables):
        matches = Match.objects.filter(
            state=Match.NEW).order_by('start_datetime')
        available_tables = list(BetTable.objects.filter(
            state=BetTable.AVAILABLE).order_by('-created'))
        for match in matches:
            if len(available_tables) < max_tables:
                if match.is_usable():
                    available_tables.append(BetTable.new_table(match))
            else:
                for table in available_tables:
                    bet_row = BetRow.objects.filter(bet_table=table).first()
                    if match.is_usable(table.betrow_set.count()):
                        if match.has_bet_time(bet_row):
                            BetRow.objects.create(
                                match=match, bet_table=table, previous=bet_row)
                            match.set_used()
                            break
                    else:
                        break
                else:
                    match.set_not_used()

    @classmethod
    def new_table(cls, match):
        table = cls.objects.create(
            state=cls.AVAILABLE,
            name=datetime.now().strftime(settings.DATE_FORMAT))
        BetRow.objects.create(match=match, bet_table=table)
        match.set_used()

        return table

    def __str__(self):
        return "{id} - {name}".format(id=self.id, name=self.name)


class MatchManager(models.Manager):
    def get_queryset(self):
        return super(MatchManager, self).get_queryset().select_related(
            'match__local_team', 'match__visitor_team', 'bet_table')


class BetRow(TimeStampedModel):
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
    profit = models.FloatField(default=0)
    state = models.CharField(max_length=1, choices=STATES, default=NEW)
    previous = models.ForeignKey(
        'bet.BetRow', on_delete=models.CASCADE,
        related_name='previous_data', null=True, blank=True)
    objects = MatchManager()

    def __str__(self):
        return "{local} - {visitor} BET TABLE: {bet}".format(
            local=self.match.local_team.name,
            visitor=self.match.visitor_team.name,
            bet=self.bet_table
        )
