# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from datetime import timedelta, datetime

from bet.models import BetTable, DataTable
from football.models import Match
from football.constants import MATCH_STATES

STATES = (
    (1, 'available'),
    (2, 'finished'),
)

STATES_TIME = (
    (0, 'FT'),
    (1, 'HT'),
)

LAPSE_MATCH_IN_MIN = 120


def new_table(match):
    table = BetTable.objects.create(
        state=STATES[0][0], name=str(datetime.now()),
        state_in_time=STATES_TIME[1][0])
    DataTable.objects.create(
        match=match, bet_table=table, state_in_time=STATES_TIME[1][0])
    match.match_state_half_time = MATCH_STATES[1][0]
    match.save()


class Command(BaseCommand):
    help = 'Update or create matches'

    def handle(self, *args, **options):

        new_matches = Match.objects.filter(
            match_state_half_time=MATCH_STATES[0][0],
            start_datetime__gt=datetime(2018, 9, 3)
        ).order_by('start_datetime')
        # print("new_matches: ", new_matches)
        for match in new_matches:
            # print("match: ", match)
            # print("local_factor_half_time: ", match.local_factor_half_time)
            if match.local_factor_half_time is None:
                match.match_state_half_time = MATCH_STATES[6][0]
                match.save()
                continue
            available_tables = BetTable.objects.filter(
                state=STATES[0][0],
                state_in_time=STATES_TIME[1][0]).order_by('-created')
            if not available_tables:
                new_table(match)
                # print("------------------------------------------------")
                # print("------------------------------------------------\n")
                continue

            for i, table in enumerate(available_tables, start=1):
                data_table = DataTable.objects.filter(
                    bet_table=table,
                    state_in_time=STATES_TIME[1][0]
                ).order_by('-match__start_datetime').first()
                difference_matches = (
                    match.start_datetime - data_table.match.start_datetime)

                if difference_matches > timedelta(minutes=LAPSE_MATCH_IN_MIN):
                    DataTable.objects.create(
                        match=match,
                        bet_table=table,
                        state_in_time=STATES_TIME[1][0],
                        previous=data_table)
                    match.match_state_half_time = MATCH_STATES[1][0]
                    match.save()
                    break

                if i == len(available_tables):
                    new_table(match)

                # print("------------------------------------------------")
                # print("------------------------------------------------\n")
