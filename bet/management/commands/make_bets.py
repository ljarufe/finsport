# -*- coding: utf-8 -*-

# TODO: Delete all the utc logic
import pytz

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.conf import settings
from datetime import timedelta, datetime

from accounts.models import Account
from bet.models import BetTable, BetRow
from bet.utils import (
    make_bet_selenium,
    count_iteration,
    send_alert,
    check_time_for_attemps,
)
# TODO: Use the complete name
from bet.constants import (
    INIT_AMOUNT,
    FIRST_VAL_FORMULA as f_v_f,
    SECOND_VAL_FORMULA as s_v_f,
    THRID_VALUE_FORMULA as t_v_f,
    MATCH_SUSPENDED_HOURS as m_s_h
)
from football.models import Match

utc = pytz.UTC


def make_bet(data_table, inkabet, data_id=0):

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
        data_table.match.state = Match.PLAYING
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
            data_table.match.state = Match.PLAYING
            data_table.match.local_factor = float(res[2][0])
            data_table.match.parity_factor = float(res[2][1])
            data_table.match.visitor_factor = float(res[2][2])
            data_table.match.save()
            return True
        else:
            print("Error en ", match, ": ", res[1])
            return False


# TODO: move to BetTable as a method
def update_table(table, current):
    total_inversion_list = BetRow.objects.filter(
        bet_table=table).values_list('bet_amount', flat=True)
    bucle_number = len(total_inversion_list)
    table.total_profit = current.profit - current.inversion_amount
    table.bucle_number = bucle_number
    table.total_inversion = current.inversion_amount
    table.state = BetTable.FINISHED
    table.save()

    send_alert(table)


# TODO: All the not used matches for today must be set them to new if they are
#  not in the past
def set_residue_matches(residue):
    for r in residue:
        r.match.state = Match.NEW
        r.match.save()


def suspended_match(current):
    actual_time = datetime.now() - timedelta(hours=5)
    actual_time = actual_time.replace(tzinfo=utc)
    seconds = (actual_time - current.match.start_datetime).total_seconds()

    return True if ((seconds // 3600) > m_s_h) else False


def remove_match_suspended(current):
    current.match.state = Match.USED
    current.match.save()
    if current.previous:
        current.previous.state = BetRow.WAITING
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
        available_tables = BetTable.objects.filter(state=BetTable.AVAILABLE)
        for table in available_tables:
            current = BetRow.objects.filter(
                Q(bet_table=table),
                Q(state=BetRow.CURRENT) | Q(state=BetRow.WAITING))
            if not current:
                current = BetRow.objects.filter(
                    bet_table=table, state=BetRow.NEW).order_by(
                    'match__start_datetime').first()
                if not current:
                    continue
                iteration = count_iteration(table, current)
                state_bet = make_bet(current, inkabet, data_id=iteration)
                if state_bet:
                    current.state = BetRow.CURRENT
                    current.save()
                continue
            else:
                # TODO: Verify if this match is the next one in time to pick
                #  the nearest one
                current = current.first()

            # TODO: Call functions inside every if to modularize this
            # PLAYING THE BED
            if current.match.state == Match.PLAYING:
                if suspended_match(current):
                    remove_match_suspended(current)
                    break
                continue

            # WON THE BED OF TABLE
            if current.match.state == Match.PARITY:
                current.state = BetRow.WON
                current.profit = (
                    current.bet_amount * current.match.parity_factor)
                current.save()
                residue = BetRow.objects.filter(
                    bet_table=table, state=BetRow.NEW).order_by(
                    'match__start_datetime')
                set_residue_matches(residue)
                residue.delete()
                update_table(table, current)

            # LOST THE BED FOR MATCH - DATA_TABLE
            # TODO: Move this logic to a function on Match
            if (current.match.state == Match.LOCAL or
                    current.match.state == Match.VISITOR or
                    current.match.state == Match.UNKNOW or
                    current.match.state == Match.NOT_USED):
                current.state = BetRow.LOST
                current.profit = current.bet_amount * (-1)
                current.save()

                currents = BetRow.objects.filter(
                    bet_table=table, state=BetRow.NEW).order_by(
                    'match__start_datetime')
                if not currents:
                    current.state = BetRow.WAITING
                    current.save()
                    print("MAKE_BET after WAITING")
                else:
                    print("make beet")
                    print("currents: ", currents)
                    # TODO: Select the nearest match in time, not the first one
                    current = currents.first()
                    iteration = count_iteration(table, current)
                    state_bet = make_bet(current, inkabet, data_id=iteration)
                    if state_bet:
                        current.state = BetRow.CURRENT
                        current.save()
