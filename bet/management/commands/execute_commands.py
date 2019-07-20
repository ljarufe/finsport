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
        get_matches = '{python} {site_root}{command}'.format(
            python=python,
            site_root=settings.SITE_ROOT,
            command='/manage.py get_matches')
        fill_tables = '{python} {site_root}{command}'.format(
            python=python,
            site_root=settings.SITE_ROOT, command='/manage.py fill_tables')
        make_bets = '{python} {site_root}{command}'.format(
            python=python,
            site_root=settings.SITE_ROOT, command='/manage.py make_bets')
        refund = '{python} {site_root}{command}'.format(
            python=python,
            site_root=settings.SITE_ROOT, command='/manage.py refund')
        commands = (
            "{check_results}; "
            "{check_results_inkabet}; "            
            "{get_matches}; "
            "{fill_tables}; "
            "{make_bets}; "
            "{refund}; "
        ).format(
            check_results=check_results,
            check_results_inkabet=check_results_inkabet,
            get_matches=get_matches,
            fill_tables=fill_tables,
            make_bets=make_bets,
            refund=refund,
        )
        os.system(commands)
