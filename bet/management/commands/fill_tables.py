# -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand

from accounts.models import Account
from bet.models import BetTable


class Command(BaseCommand):
    help = 'Update or create matches'

    def handle(self, *args, **options):
        for account in Account.objects.all():
            BetTable.fill_tables(account.num_allow_tables)
