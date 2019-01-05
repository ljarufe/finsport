# -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand
from bet.utils import obtain_league_matches
from football.utils import save_league_match


class Command(BaseCommand):
    help = 'Update or create matches league'

    def handle(self, *args, **options):
        matches = obtain_league_matches()
        for match in matches:
            save_league_match(match)
