# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from django.db.models import Q

from bet.models import BetTable, DataTable
from football.constants import MATCH_STATES

STATES = (
    (1, 'available'),
    (2, 'finished'),
)

STATES_DATA_TABLE = (
    (0, 'new'),
    (1, 'current'),
    (2, 'won'),
    (3, 'lost'),
    (4, 'waiting'),
)

STATES_TIME = (
    (0, 'FT'),
    (1, 'HT'),
)

INIT_AMOUNT = 1


def make_bet(data_table):
    data_table.match.match_state_half_time = MATCH_STATES[2][0]
    data_table.match.save()
    if not data_table.previous:
        data_table.bet_amount = INIT_AMOUNT
        data_table.inversion_amount = INIT_AMOUNT
        data_table.save()
    else:
        data_table.bet_amount = data_table.previous.bet_amount * 2
        data_table.inversion_amount = (
            data_table.previous.inversion_amount + data_table.bet_amount)
        data_table.save()

    # make_bet_selenium()


def check_results(data_table):

    # print("DATA TABLE fron check_results: ", data_table)
    # print("MATCH_STATE_HALF_TIME: ", data_table.match.match_state_half_time)

    if data_table.match.match_state_half_time == MATCH_STATES[2][0]:
        return STATES_DATA_TABLE[1][0]

    if data_table.match.match_state_half_time == MATCH_STATES[4][0]:
        return STATES_DATA_TABLE[2][0]

    if (data_table.match.match_state_half_time == MATCH_STATES[3][0] or
            data_table.match.match_state_half_time >= MATCH_STATES[5][0]):
        return STATES_DATA_TABLE[3][0]


def update_table(table, current):
    total_inversion_list = DataTable.objects.filter(
        bet_table=table).values_list('bet_amount', flat=True)
    bucle_number = len(total_inversion_list)
    table.total_profit = current.profit - current.inversion_amount
    table.bucle_number = bucle_number
    table.total_inversion = current.inversion_amount
    table.state = STATES[1][0]
    table.save()


def set_residue_matches(residue):

    for r in residue:
        r.match.match_state_half_time = MATCH_STATES[0][0]
        r.match.save()


class Command(BaseCommand):
    help = 'Make bets based in BetTables'

    def handle(self, *args, **options):
        available_tables = BetTable.objects.filter(
            state=STATES[0][0], state_in_time=STATES_TIME[1][0])

        for table in available_tables:
            current = DataTable.objects.filter(
                Q(bet_table=table),
                Q(state=STATES_DATA_TABLE[1][0]) | Q(
                    state=STATES_DATA_TABLE[4][0]),
            ).first()

            # SET CURRENT TO FIRST DATA TABLE
            if not current:
                current = DataTable.objects.filter(
                    bet_table=table, state=STATES_DATA_TABLE[0][0]).order_by(
                    'match__start_datetime').first()
                # print("CURRENT: ", current)
                current.state = STATES_DATA_TABLE[1][0]
                make_bet(current)
                current.save()

            # PLAYING THE BED
            if check_results(current) == STATES_DATA_TABLE[1][0]:
                continue

            # WON THE BED OF TABLE
            if check_results(current) == STATES_DATA_TABLE[2][0]:
                current.state = STATES_DATA_TABLE[2][0]
                current.profit = (
                    current.bet_amount * current.match.parity_factor_half_time)
                current.save()
                residue = DataTable.objects.filter(
                    bet_table=table, state=STATES_DATA_TABLE[0][0]).order_by(
                    'match__start_datetime')
                set_residue_matches(residue)
                residue.delete()
                update_table(table, current)

            # LOST THE BED FOR MATCH - DATA_TABLE
            if check_results(current) == STATES_DATA_TABLE[3][0]:
                current.state = STATES_DATA_TABLE[3][0]
                current.profit = current.bet_amount * (-1)
                current.save()
                currents = DataTable.objects.filter(
                    bet_table=table, state=STATES_DATA_TABLE[0][0]).order_by(
                    'match__start_datetime')
                if not currents:
                    current.state = STATES_DATA_TABLE[4][0]
                    current.save()
                else:
                    current = currents.first()
                    current.state = STATES_DATA_TABLE[1][0]
                    make_bet(current)
                    current.save()
