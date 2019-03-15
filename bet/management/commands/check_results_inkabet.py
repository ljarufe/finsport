# -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand

from bet.models import BetRow, BetTable
from football.models import Match
from accounts.models import Account


class Command(BaseCommand):
    help = 'Check and save matches results'

    def handle(self, *args, **options):
        for account in Account.objects.filter(bet_page__active=True):
            bet_selenium = account.bet_page.get_selenium_bot()(account)
            bet_selenium.login()
            bet_selenium.get_results()
            for table in BetTable.objects.filter(state=BetTable.AVAILABLE):
                # TODO: crear una función para esto
                bet_rows = BetRow.objects.filter(
                    bet_table=table,
                    state__in=(BetRow.CURRENT, BetRow.WAITING))
                if bet_rows.exists():
                    bet_row = bet_rows.first()
                    if bet_row.match.state is Match.PLAYING:
                        if bet_row.match.is_suspended():
                            bet_row.remove_match()
                    elif bet_row.match.state is Match.PARITY:
                        table.set_finished(account, bet_row)
                    else:
                        bet_row.set_waiting()
            bet_selenium.clean_driver()
