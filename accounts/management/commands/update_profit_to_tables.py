# -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand
from django.db.models import Sum

from bet.models import BetTable
from accounts.models import Account

STATES = (
    (1, 'available'),
    (2, 'finished'),
    (3, 'paused'),
    (4, 'favorite')
)

STATES_TIME = (
    (0, 'FT'),
    (1, 'HT'),
)


class Command(BaseCommand):
    help = 'Update profit to tables'

    def handle(self, *args, **options):
        finished_tables_profit = BetTable.objects.filter(
            state=STATES[1][0],
            state_in_time=STATES_TIME[0][0]).aggregate(Sum('total_profit'))
        inkabet = Account.objects.filter(
            bet_page__name__iexact="inkabet").first()
        new_profit = finished_tables_profit.get(
            'total_profit__sum', 0)

        if inkabet.profit_to_tables_index < new_profit:
            old_profit = inkabet.profit_to_tables_index
            inkabet.profit_to_tables_index = new_profit
            inkabet.profit_to_tables += (new_profit - old_profit)
            inkabet.save()
