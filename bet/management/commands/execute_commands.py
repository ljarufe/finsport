# -*- coding: utf-8 -*-

import os

from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Execute commands sequentially'

    def handle(self, *args, **options):
        python = '{env}{python_path}'.format(
            env=settings.ENV_FOLDER, python_path='bin/python3')
        check_results = '{python} {site_root}{command}'.format(
            python=python,
            site_root=settings.SITE_ROOT,
            command='/manage.py check_results')
        check_results_inkabet = '{python} {site_root}{command}'.format(
            python=python,
            site_root=settings.SITE_ROOT,
            command='/manage.py check_results_inkabet')
        create_tables = '{python} {site_root}{command}'.format(
            python=python,
            site_root=settings.SITE_ROOT, command='/manage.py create_tables')
        make_bets = '{python} {site_root}{command}'.format(
            python=python,
            site_root=settings.SITE_ROOT, command='/manage.py make_bets')
        update_profit_tables = '{python} {site_root}{command}'.format(
            python=python,
            site_root=settings.SITE_ROOT,
            command='/manage.py update_profit_to_tables')

        commands = (
            "{check_results_inkabet}; "
            "{create_tables}; "
            "{make_bets}; "
            "{create_tables}; "
            "{create_tables}; "
            "{make_bets}; "
        ).format(
            check_results_inkabet=check_results_inkabet,
            create_tables=create_tables,
            make_bets=make_bets,
        )

        os.system(commands)
