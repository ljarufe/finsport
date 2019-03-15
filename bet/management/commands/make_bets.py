# -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand

from accounts.models import Account
from bet.models import BetTable, BetRow


class Command(BaseCommand):
    help = 'Hace las apuestas de las tablas de apuestas'

    def handle(self, *args, **options):
        for account in Account.objects.filter(bet_page__active=True):
            current_bets = BetRow.objects.filter(
                state__in=(BetRow.CURRENT, BetRow.WAITING)).count()
            available_tables = BetTable.objects.filter(state=BetTable.AVAILABLE)
            if current_bets is not available_tables:
                bet_selenium = account.bet_page.get_selenium_bot()(account)
                bet_selenium.login()
                for table in available_tables:
                    table.make_bet(account, bet_selenium)
                bet_selenium.clean_driver()
