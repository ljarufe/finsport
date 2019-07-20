# -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand

from accounts.models import Account
from bet.models import BetRow


class Command(BaseCommand):
    help = 'Hace las apuestas de las tablas de apuestas'

    def handle(self, *args, **options):
        for account in Account.objects.filter(bet_page__active=True):
            bet_rows = BetRow.objects.filter(state=BetRow.CURRENT)
            if bet_rows.exists():
                bet_selenium = account.bet_page.get_selenium_bot()(account)
                bet_selenium.login()
                for bet_row in bet_rows:
                    bet_row.refund(bet_selenium)
                bet_selenium.clean_driver()
