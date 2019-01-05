# -*- coding: utf-8 -*-
import random
import pytz

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.conf import settings
from datetime import timedelta, datetime

from accounts.models import Account
from bet.models import BetTable, DataTable
from bet.utils import (
    make_bet_selenium,
    count_iteration,
    send_alert,
    check_time_for_attemps,
)
from bet.constants import (
    STATES_DATA_TABLE,
    INIT_AMOUNT,
    LIMIT_ROWS,
    FIRST_VAL_FORMULA as f_v_f,
    SECOND_VAL_FORMULA as s_v_f,
    THRID_VALUE_FORMULA as t_v_f,
    MATCH_SUSPENDED_HOURS as m_s_h
)
from football.constants import MATCH_STATES

utc = pytz.UTC

STATES = (
    (1, 'available'),
    (2, 'finished'),
    (3, 'paused'),
    (4, 'favorite'),
)

STATES_TIME = (
    (0, 'FT'),
    (1, 'HT'),
)


def make_bet(data_table, inkabet, paused=False, data_id=0):

    if inkabet.funds <= data_table.bet_amount:
        print("You have to deposit more funds to the account")
        return False

    if not data_table.previous:
        data_table.bet_amount = INIT_AMOUNT
        data_table.inversion_amount = INIT_AMOUNT
    else:
        print("#############################################")
        print("iteration: ", data_id)
        print("B: ", data_table.previous.inversion_amount)
        print("A: ", data_table.match.parity_factor)
        print("#############################################")
        data_table.bet_amount = (f_v_f * (
            s_v_f ** data_id) + data_table.previous.inversion_amount) / (
            data_table.match.parity_factor - t_v_f)
        data_table.inversion_amount = (
            data_table.previous.inversion_amount + data_table.bet_amount)
        data_table.save()
        print("amount: ", data_table.bet_amount)

    if not settings.EXEC_SELENIUM:
        data_table.match.match_state = MATCH_STATES[2][0]
        data_table.match.save()
        return True
    else:
        match = '%s - %s' % (
            data_table.match.local_team.name,
            data_table.match.visitor_team.name)
        init_time = datetime.now()
        res = make_bet_selenium(my_match=match, amount=data_table.bet_amount)
        while(res[0] is False and 'Error' in res[1] and
                check_time_for_attemps(init_time)):
            res = make_bet_selenium(
                my_match=match, amount=data_table.bet_amount)
        if res[0] is True:
            print("Bet made: ", res[1])
            data_table.match.match_state = MATCH_STATES[2][0]
            data_table.match.local_factor = float(res[2][0])
            data_table.match.parity_factor = float(res[2][1])
            data_table.match.visitor_factor = float(res[2][2])
            data_table.match.save()
            return True
        else:
            print("Error en ", match, ": ", res[1])
            return False


def bet_favorite_team(data_table, favorite_team, bets):
    if favorite_team == data_table.match.local_team:
        amount = random.randint(bets[0], bets[1])
        my_bet = 1
    else:
        amount = random.randint(bets[0], bets[1])
        my_bet = 3
    data_table.bet_amount = amount
    data_table.inversion_amount = amount
    match = data_table.match.local_team.name + \
        ' - ' + data_table.match.visitor_team.name

    res = make_bet_selenium(
        my_match=match, my_bet=my_bet, amount=data_table.bet_amount)
    while res[0] is False and res[1] == 'Error en la ejecucion':
        res = make_bet_selenium(
            my_match=match, my_bet=my_bet, amount=data_table.bet_amount)
    if res[0] is True:
        print(res[1])
        data_table.match.match_state = MATCH_STATES[2][0]
        data_table.match.save()
        data_table.state = STATES_DATA_TABLE[1][0]
        data_table.save()
    else:
        print("Error en ", data_table.match, ": ", res[1])


def check_results(data_table):
    if data_table.match.match_state == MATCH_STATES[2][0]:
        return STATES_DATA_TABLE[1][0]

    if data_table.match.match_state == MATCH_STATES[4][0]:
        return STATES_DATA_TABLE[2][0]

    if (data_table.match.match_state == MATCH_STATES[3][0] or
            data_table.match.match_state >= MATCH_STATES[5][0]):
        return STATES_DATA_TABLE[3][0]


def check_favorite_results(data_table, favorite_team):

    if data_table.match.match_state == MATCH_STATES[2][0]:
        return STATES_DATA_TABLE[1][0], 0

    if (data_table.match.match_state == MATCH_STATES[3][0] and
            data_table.match.local_team == favorite_team):
        return STATES_DATA_TABLE[2][0], data_table.match.local_factor
    elif (data_table.match.match_state == MATCH_STATES[5][0] and
            data_table.match.visitor_team == favorite_team):
        return STATES_DATA_TABLE[2][0], data_table.match.visitor_factor
    else:
        return STATES_DATA_TABLE[3][0], 0


def update_table(table, current):
    total_inversion_list = DataTable.objects.filter(
        bet_table=table).values_list('bet_amount', flat=True)
    bucle_number = len(total_inversion_list)
    table.total_profit = current.profit - current.inversion_amount
    table.bucle_number = bucle_number
    table.total_inversion = current.inversion_amount
    table.state = STATES[1][0]
    table.save()

    send_alert(table)


def update_favorite_table(table, current):
    total_inversion_list = DataTable.objects.filter(
        bet_table=table).values_list('bet_amount', flat=True)
    bucle_number = len(total_inversion_list)
    table.total_profit = current.profit - current.inversion_amount
    table.bucle_number = bucle_number
    table.total_inversion = current.inversion_amount
    table.save()


def set_residue_matches(residue):

    for r in residue:
        r.match.match_state = MATCH_STATES[0][0]
        r.match.save()


def suspended_match(current):
    actual_time = datetime.now() - timedelta(hours=5)
    actual_time = actual_time.replace(tzinfo=utc)
    seconds = (actual_time - current.match.start_datetime).total_seconds()

    return True if ((seconds // 3600) > m_s_h) else False


def remove_match_suspended(current):
    current.match.match_state = MATCH_STATES[1][0]
    current.match.save()
    if current.previous:
        current.previous.state = STATES_DATA_TABLE[4][0]
        current.previous.save()
        current.delete()
    else:
        current.bet_table.delete()


class Command(BaseCommand):
    help = 'Make bets based in BetTables'

    def handle(self, *args, **options):

        print("\n\n---------------------------MAKE BETS------------------")
        inkabet = Account.objects.filter(
            bet_page__name__iexact="inkabet").first()
        # FAVORITE TABLE
        favorite_table = BetTable.objects.filter(
            state=STATES[3][0], state_in_time=STATES_TIME[0][0])
        if len(favorite_table):
            favorite_data_table = DataTable.objects.filter(
                bet_table=favorite_table[0],
                state=STATES_DATA_TABLE[1][0]
            ).first()
            accounts = Account.objects.filter(bet_page__name='Inkabet')
            favorite_team = accounts[0].favorite_team if len(
                accounts) else None
            bets = (accounts[0].min_favorite_bet, accounts[0].max_favorite_bet)
            if not favorite_data_table:
                favorite_data_table = DataTable.objects.filter(
                    bet_table=favorite_table[0],
                    state=STATES_DATA_TABLE[0][0]).order_by(
                    'match__start_datetime').first()
                if favorite_data_table:
                    bet_favorite_team(favorite_data_table, favorite_team, bets)
                    favorite_data_table.save()
            else:
                res, factor = check_favorite_results(
                    favorite_data_table, favorite_team)
                # WIN THE MATCH
                if res == STATES_DATA_TABLE[2][0]:
                    favorite_data_table.state = STATES_DATA_TABLE[2][0]
                    favorite_data_table.profit = (
                        favorite_data_table.bet_amount * factor)
                    favorite_data_table.save()
                    update_favorite_table(
                        favorite_table[0], favorite_data_table)

                # LOST THE BED FOR MATCH - DATA_TABLE
                if res == STATES_DATA_TABLE[3][0]:
                    favorite_data_table.state = STATES_DATA_TABLE[3][0]
                    favorite_data_table.profit = (
                        favorite_data_table.bet_amount * (-1))
                    favorite_data_table.save()
                    update_favorite_table(
                        favorite_table[0], favorite_data_table)

        available_paused_tables = BetTable.objects.filter(
            Q(state=STATES[0][0]) | Q(state=STATES[2][0]),
            Q(state_in_time=STATES_TIME[0][0]))

        for table in available_paused_tables:
            current = DataTable.objects.filter(
                Q(bet_table=table),
                Q(state=STATES_DATA_TABLE[1][0]) | Q(
                    state=STATES_DATA_TABLE[4][0]) | Q(
                    state=STATES_DATA_TABLE[6][0]) | Q(
                    state=STATES_DATA_TABLE[7][0]),
            )

            if not current:
                current = DataTable.objects.filter(
                    bet_table=table, state=STATES_DATA_TABLE[0][0]).order_by(
                    'match__start_datetime').first()
                if not current:
                    continue
                iteration = count_iteration(table, current)
                state_bet = make_bet(current, inkabet, data_id=iteration)
                if state_bet:
                    current.state = STATES_DATA_TABLE[1][0]
                    current.save()
                continue
            else:
                current = current.first()

            # PLAYING THE BED
            if check_results(current) == STATES_DATA_TABLE[1][0]:
                if suspended_match(current):
                    remove_match_suspended(current)
                    break
                continue

            # WON THE BED OF TABLE
            if check_results(current) == STATES_DATA_TABLE[2][0]:
                current.state = STATES_DATA_TABLE[2][0]
                current.profit = (
                    current.bet_amount * current.match.parity_factor)
                current.save()
                residue = DataTable.objects.filter(
                    bet_table=table, state=STATES_DATA_TABLE[0][0]).order_by(
                    'match__start_datetime')
                set_residue_matches(residue)
                residue.delete()
                update_table(table, current)

            # LOST THE BED FOR MATCH - DATA_TABLE
            if check_results(current) == STATES_DATA_TABLE[3][0]:

                datas_table = DataTable.objects.filter(
                    bet_table=table, state=STATES_DATA_TABLE[3][0])

                # (S)SETTING THE DATATABLE IF IS NECESARY TO PAUSED
                if(len(datas_table) >= LIMIT_ROWS - 1):
                    print("CURRENT THAT IS GOING TO BE PAUSED: ", current)
                    current.state = STATES_DATA_TABLE[5][0]
                    current.profit = current.bet_amount * (-1)
                    current.save()
                    residue = DataTable.objects.filter(
                        bet_table=table,
                        state=STATES_DATA_TABLE[0][0]).order_by(
                            'match__start_datetime')
                    set_residue_matches(residue)
                    residue.delete()
                    table.state = STATES[2][0]
                    table.save()
                    continue
                # (E)SETTING THE DATATABLE IF IS NECESARY TO PAUSED

                current.state = STATES_DATA_TABLE[3][0]
                current.profit = current.bet_amount * (-1)
                current.save()

                currents = DataTable.objects.filter(
                    bet_table=table, state=STATES_DATA_TABLE[0][0]).order_by(
                    'match__start_datetime')

                if not currents:
                    current.state = STATES_DATA_TABLE[4][0]
                    current.save()
                    print("MAKE_BET after WAITING")
                else:
                    print("make beet")
                    print("currents: ", currents)
                    current = currents.first()
                    iteration = count_iteration(table, current)
                    state_bet = make_bet(current, inkabet, data_id=iteration)
                    if state_bet:
                        current.state = STATES_DATA_TABLE[1][0]
                        current.save()

            # (S) IF TABLE HAS A DATATABLE WITH NEW_PAUSED OR CURRENT_PAUSED
            if current.state == STATES_DATA_TABLE[7][0]:
                print("\n\ninkabet.profit_to_tables: ",
                      inkabet.profit_to_tables)
                print("current.previous.bet_amount * 2:",
                      current.previous.bet_amount * 2)
                if inkabet.profit_to_tables <= current.previous.bet_amount * 2:
                    print(
                        "You doesn't have enought profit to bet"
                        " in paused tables")
                    current.match.match_state = MATCH_STATES[0][0]
                    current.match.save()
                    current.delete()
                    continue

                iteration = count_iteration(table, current)
                make_bet(current, inkabet, paused=True, data_id=iteration)
                current.state = STATES_DATA_TABLE[6][0]
                current.save()
            # (E) IF TABLE HAS A DATATABLE WITH NEW_PAUSED OR CURRENT_PAUSED

            if current.state == STATES_DATA_TABLE[6][0]:
                continue
