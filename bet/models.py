# -*- coding: utf-8 -*-
import math
from datetime import datetime

from django.conf import settings
from django.db import models

from django_extensions.db.models import TimeStampedModel

from football.models import Match


class BetTable(TimeStampedModel):
    # TODO: Aumentar la cuenta como campo
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
            state=BetTable.AVAILABLE).order_by('created'))
        for match in matches:
            if len(available_tables) < max_tables:
                if match.is_usable():
                    available_tables.append(BetTable.new_table(match))
            else:
                for table in available_tables:
                    bet_row = BetRow.objects.filter(bet_table=table).first()
                    if match.is_usable():
                        if match.has_bet_time(bet_row):
                            BetRow.objects.create(
                                match=match, bet_table=table, previous=bet_row,
                                iteration=table.betrow_set.count())
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

    def set_finished(self, account, bet_row):
        bet_row.set_won()
        residual_rows = BetRow.objects.filter(bet_table=self, state=BetRow.NEW)
        for row in residual_rows:
            row.match.set_new()
        residual_rows.delete()
        self.total_profit = bet_row.profit - bet_row.inversion_amount
        self.bucle_number = BetRow.objects.filter(bet_table=self).count()
        self.total_inversion = bet_row.inversion_amount
        self.state = BetTable.FINISHED
        self.save()
        account.send_finished_table(self)

    def make_bet(self, account, bet_selenium):
        bet_rows = BetRow.objects.filter(
            bet_table=self, state=BetRow.NEW
        ).order_by('match__start_datetime')
        if bet_rows.exists():
            bet_row = bet_rows.first()
            if bet_row.make_bet(account, bet_selenium):
                bet_row.set_current()


class MatchManager(models.Manager):
    def get_queryset(self):
        return super(MatchManager, self).get_queryset().select_related(
            'match__local_team', 'match__visitor_team', 'bet_table')


class BetRow(TimeStampedModel):
    NEW = 'N'
    CURRENT = 'C'
    WON = 'W'
    LOST = 'L'
    STATES = (
        ('N', 'new'),
        ('C', 'current'),
        ('W', 'won'),
        ('L', 'lost'),
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
    iteration = models.PositiveSmallIntegerField(default=0)

    objects = MatchManager()

    DEVIATION = 0.65

    def first_earn(self):
        first_row = BetRow.objects.get(bet_table=self.bet_table, iteration=0)

        return first_row.bet_amount * (first_row.match.parity_factor - 1)

    def __str__(self):
        return "{local} - {visitor} BET TABLE: {bet}".format(
            local=self.match.local_team.name,
            visitor=self.match.visitor_team.name,
            bet=self.bet_table
        )

    def set_current(self):
        self.state = BetRow.CURRENT
        self.save()

    def set_won(self):
        self.state = BetRow.WON
        self.profit = self.bet_amount * self.match.parity_factor
        self.save()

    def set_lost(self):
        self.state = BetRow.LOST
        self.profit = self.bet_amount * (-1)
        self.save()

    def make_bet(self, account, bet_selenium):
        self.bet_amount = self.get_bet_amount(account)
        self.inversion_amount = self.get_inversion_amount(account)
        have_bet = bet_selenium.make_bet(self)
        if have_bet:
            self.save()
            self.match.set_playing()
            return True

        return False

    def get_bet_amount(self, account):
        if self.previous:
            amount = (
                    (self.first_earn()*BetRow.DEVIATION**self.iteration +
                     self.previous.inversion_amount) /
                    (self.match.parity_factor - 1))
        else:
            amount = account.start_bet

        return math.ceil(amount)

    def get_inversion_amount(self, account):
        if self.previous:
            return self.previous.inversion_amount + self.bet_amount
        else:
            return account.start_bet

    def remove_match(self):
        self.match.set_used()
        if self.previous:
            self.delete()
        else:
            self.bet_table.delete()
