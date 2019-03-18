# -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand

from accounts.models import Account
from bet.models import BetTable, BetRow


class Command(BaseCommand):
    help = 'Hace las apuestas de las tablas de apuestas'

    def handle(self, *args, **options):
        for account in Account.objects.filter(bet_page__active=True):
            current_tables = BetRow.objects.filter(
                state=BetRow.CURRENT).values_list('bet_table_id', flat=True)
            available_tables = BetTable.objects.filter(
                state=BetTable.AVAILABLE).exclude(id__in=current_tables)
            if available_tables:
                bet_selenium = account.bet_page.get_selenium_bot()(account)
                bet_selenium.login()
                for table in available_tables:
                    table.make_bet(account, bet_selenium)
                bet_selenium.clean_driver()
