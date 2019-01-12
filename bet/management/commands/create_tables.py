# -*- coding: utf-8 -*-

import pytz

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from football.models import Match
from football.constants import MATCH_STATES
from accounts.models import Account
from bet.models import BetTable, DataTable
from bet.constants import (
    STATES_DATA_TABLE,
    LAPSE_MATCH_IN_MIN,
    STEP_PARITY_FORMULA,
    MIN_VAL_INIT
)
from bet.utils import count_iteration
from bet.rules import Rules

utc = pytz.UTC


def new_table(match, max_tables):
    """
    Creates a new table if the max number of tables allows it

    :param match: current match
    :param max_tables: max number of tables
    """

    if match.start_datetime > timezone.now():
        if BetTable.objects.filter(
                state=BetTable.AVAILABLE).count() <= max_tables - 1:
            table = BetTable.objects.create(
                state=BetTable.AVAILABLE, name=str(timezone.now()))
            DataTable.objects.create(match=match, bet_table=table)
            match.match_state = MATCH_STATES[1][0]
            match.save()


def exist_current(table):
    current = DataTable.objects.filter(
        bet_table=table, state=STATES_DATA_TABLE[1][0])

    return True if current else False


def filter_parity_factor(match, first=False, table=None, current=None):

    if Rules.evaluate(
            match.local_factor, match.parity_factor, match.visitor_factor):
        if first:
            if match.parity_factor >= MIN_VAL_INIT:
                return True
            return False

        values_factor = round(
            ((count_iteration(table, current) *
              STEP_PARITY_FORMULA) + MIN_VAL_INIT) + STEP_PARITY_FORMULA, 2)
        if match.parity_factor >= values_factor:
            return True
        return False

    return False


class Command(BaseCommand):
    help = 'Update or create matches'

    def handle(self, *args, **options):

        print("\n\n--------------------CREATE TABLES------------------")
        accounts = Account.objects.all()
        for account in accounts:
            new_matches = Match.objects.filter(
                match_state=MATCH_STATES[0][0]).order_by('start_datetime')

            for match in new_matches:
                available_tables = BetTable.objects.filter(
                    state=BetTable.AVAILABLE).order_by('-created')
                available_paused_tables = BetTable.objects.filter(
                    Q(state=BetTable.AVAILABLE) | Q(state=BetTable.FINISHED))
                if not available_tables:
                    if filter_parity_factor(match, first=True):
                        new_table(match, account.num_allow_tables)
                        continue
                    continue
                for i, table in enumerate(available_paused_tables, start=1):
                    data_table = DataTable.objects.filter(
                        bet_table=table).order_by(
                        '-match__start_datetime').first()
                    print("TABLEEEEEE: ", table)
                    difference_matches = (
                        match.start_datetime - data_table.match.start_datetime)

                    if difference_matches > timedelta(
                            minutes=LAPSE_MATCH_IN_MIN):
                        parity_factor = filter_parity_factor(
                            match, table=table, current=data_table)
                        exist_currentt = exist_current(table)
                        if parity_factor and not exist_currentt:
                            DataTable.objects.create(
                                match=match,
                                bet_table=table,
                                previous=data_table)
                            match.match_state = MATCH_STATES[1][0]
                            match.save()
                            break
                    else:
                        match.match_state = MATCH_STATES[8][0]
                        match.save()

                    # (S)Setting state to used if was not considered for the table
                    if match.start_datetime < timezone.now():
                        match.match_state = MATCH_STATES[8][0]
                        match.save()
                    # (E)Setting state to used if was not considered for the table

                    # (S)TO CREATE NEW TABLES WHEN EXIST LESS THAN MAXIMUM
                    if len(available_tables) < account.num_allow_tables:
                        if filter_parity_factor(match, first=True):
                            new_table(match, account.num_allow_tables)
                    # (E)TO CREATE NEW TABLES WHEN EXIST LESS THAN MAXIMUM

        new_favorite_matches = Match.objects.filter(
            match_state=MATCH_STATES[7][0]).order_by('start_datetime')
        for fav_match in new_favorite_matches:
            bet_table, found = BetTable.objects.get_or_create(
                state=BetTable.PAUSED,
                defaults={'name': str(timezone.now())})
            DataTable.objects.create(match=fav_match, bet_table=bet_table)
            fav_match.match_state = MATCH_STATES[1][0]
            fav_match.save()
