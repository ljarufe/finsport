# -*- coding: utf-8 -*-

import json
import os

from django.core.management.base import BaseCommand
from django.conf import settings

from accounts.models import BetPage
from football.utils import save_match


class Command(BaseCommand):
    help = 'Update or create matches'

    def handle(self, *args, **options):
        for bet_page in BetPage.objects.filter(active=True):
            matches_data_path = "{path}/spider-data.json".format(
                path=settings.SPIDER_DATA_PATH)
            os.system("rm -rf {path}".format(path=matches_data_path))
            bet_page.get_spider().run(matches_data_path)
            with open(matches_data_path) as f:
                url_matches = []
                data = json.load(f)
                for match in data.get('matches', None):
                    match_url = save_match(match)
                    if match_url:
                        match_url = '%s%s' % (bet_page.domain, match_url)
                        url_matches.append(match_url)
