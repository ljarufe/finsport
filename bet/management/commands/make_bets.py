import logging

from django.core.management.base import BaseCommand

from accounts.models import Account
from bet.models import BetTable, BetRow

logger = logging.getLogger("make_bets")


class Command(BaseCommand):
    help = "Hace las apuestas de las tablas de apuestas"

    def handle(self, *args, **options):
        # TODO: poner en cache las cuentas de apuestas activas
        for account in Account.objects.filter(bet_page__active=True):
            # TODO: optimizar la consulta de las tablas de apuestas
            current_tables = BetRow.objects.filter(state=BetRow.CURRENT).values_list(
                "bet_table_id", flat=True
            )
            available_tables = BetTable.objects.filter(
                state=BetTable.AVAILABLE
            ).exclude(id__in=current_tables)
            if available_tables:
                bet_selenium = account.bet_page.get_selenium_bot()(account)
                if bet_selenium.login():
                    for table in available_tables:
                        bet_rows = BetRow.objects.filter(
                            bet_table=table, state=BetRow.NEW
                        ).order_by("match__start_datetime")
                        if bet_rows.exists():
                            bet_row = bet_rows.first()
                            logger.info(
                                f"Making the bet for: {bet_row.match.get_logger_info()}"
                            )
                            bet_row.make_bet(account, bet_selenium)
                bet_selenium.clean_driver()
