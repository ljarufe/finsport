# -*- coding: utf-8 -*-

import math
import logging

from datetime import datetime

from django.conf import settings
from django.db import models

from django_extensions.db.models import TimeStampedModel

from football.models import Match

logger = logging.getLogger('fill_tables')


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
        available_tables = BetTable.objects.filter(state=BetTable.AVAILABLE)
        current_rows = BetRow.objects.filter(
            state__in=(BetRow.CURRENT, BetRow.NEW)
        ).values_list('bet_table_id', flat=True)
        current_tables = available_tables.exclude(
            id__in=current_rows).order_by("id")
        for table in current_tables:
            match = Match.get_best_match()
            if match:
                table.add_row(match)
        for i in range(0, max_tables - available_tables.count()):
            match = Match.get_best_match()
            if match:
                table = BetTable.objects.create(
                    name=datetime.now().strftime(settings.DATE_FORMAT))
                logger.info("New table: %s" % table)
                table.add_row(match)

    def __str__(self):
        return "{id} - {name}".format(id=self.id, name=self.name)

    def add_row(self, match):
        previous_rows = self.betrow_set.all()
        if previous_rows.exists():
            previous_row = previous_rows.first()
            BetRow.objects.create(
                match=match, bet_table=self, previous=previous_row,
                iteration=previous_rows.count())
        else:
            BetRow.objects.create(match=match, bet_table=self)
        match.set_used()
        logger.info(
            "Match to table: %s, table: %s" %
            (match.get_logger_info(), self.id))

    def set_finished(self, account, bet_row):
        self.total_profit = bet_row.profit - bet_row.inversion_amount
        self.bucle_number = bet_row.iteration + 1
        self.total_inversion = bet_row.inversion_amount
        self.state = BetTable.FINISHED
        self.save()
        account.send_finished_table(self, bet_row)


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

    DEVIATION = 1

    def first_earn(self):
        first_row = BetRow.objects.get(bet_table=self.bet_table, iteration=0)

        return first_row.bet_amount * (first_row.match.draw_factor - 1)

    def __str__(self):
        return "{local} - {visitor} BET TABLE: {bet}".format(
            local=self.match.local_team.name,
            visitor=self.match.visitor_team.name,
            bet=self.bet_table
        )

    def set_current(self):
        self.match.set_playing()
        self.state = BetRow.CURRENT
        self.save()

    def set_won(self):
        self.match.set_draw()
        self.state = BetRow.WON
        self.profit = self.bet_amount * self.match.draw_factor
        self.save()

    def set_lost(self):
        # TODO: cambiar esto cuando siempre se saque el resultado del partido
        self.match.set_used()
        self.state = BetRow.LOST
        self.profit = self.bet_amount * (-1)
        self.save()

    def get_bet_amount(self, account):
        if self.previous:
            amount = (
                    (self.first_earn()*BetRow.DEVIATION**self.iteration +
                     self.previous.inversion_amount) /
                    (self.match.draw_factor - 1))
        else:
            amount = account.start_bet

        return math.ceil(amount)

    def get_inversion_amount(self, account):
        if self.previous:
            return self.previous.inversion_amount + self.bet_amount
        else:
            return account.start_bet

    def remove_match(self):
        # TODO: Ya no es necesario revisar toda la tabla, sólo hay un partido
        #  en new
        self.match.set_used()
        if self.previous:
            bet_rows = BetRow.objects.filter(
                bet_table=self.bet_table, state=BetRow.NEW)
            for bet_row in bet_rows:
                bet_row.match.set_new()
            bet_rows.delete()
            self.delete()
        else:
            self.bet_table.delete()

    def make_bet(self, account, bet_selenium):
        self.bet_amount = self.get_bet_amount(account)
        self.inversion_amount = self.get_inversion_amount(account)
        if bet_selenium.make_bet(self):
            self.set_current()
            account.decrease_profit(self.bet_amount)
