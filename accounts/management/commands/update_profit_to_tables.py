# -*- coding: utf-8 -*-

# TODO: is this command necessary?
from django.core.management.base import BaseCommand
from django.db.models import Sum

from bet.models import BetTable
from accounts.models import Account


class Command(BaseCommand):
    help = 'Update profit to tables'

    def handle(self, *args, **options):
        finished_tables_profit = BetTable.objects.filter(
            state=BetTable.FINISHED).aggregate(Sum('total_profit'))
        for account in Account.objects.all():        
            new_profit = finished_tables_profit.get('total_profit__sum', 0)    
            if account.profit_to_tables_index < new_profit:
                old_profit = account.profit_to_tables_index
                account.profit_to_tables_index = new_profit
                account.profit_to_tables += (new_profit - old_profit)
                account.save()
