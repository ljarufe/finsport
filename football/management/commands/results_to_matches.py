# -*- coding: utf-8 -*-

# TODO: Is this command used?
import urllib.request
import json

from django.core.management.base import BaseCommand
from django.db.models import Q

from football.models import Match


class Command(BaseCommand):
    help = 'Get results to unknow matches'

    def __init__(self):
        url = 'http://livescore-api.com/api-client/scores/live.json?' \
              'key=OsnX22n686bJQzeO&secret=Q953EfOsAoiSK9SzCfwFiTLq0WaRvoGm'
        with urllib.request.urlopen(url) as url:
            self.data = json.loads(url.read().decode())
            self.matches = self.data['data'].get('match', None)

    def match_found(self, match):
        for m in self.matches:
            if(any(w in match.local_team.name for w in m['home_name'].split(
                " ")) and any(w in match.visitor_team.name for w in m[
                    'away_name'].split(" "))):
                if not m['time'] == 'FT':
                    return True, None
                return True, m
        return False, None

    def handle(self, *args, **options):
        matches = Match.objects.filter(
            Q(state=Match.UNKNOW) | Q(state=Match.PLAYING))
        for m in matches:
            if self.match_found(m)[0] and not self.match_found(m)[1]:
                continue
            if self.match_found(m)[0] and self.match_found(m)[1]:
                json_match = self.match_found(m)[1]
                score = json_match['score'].split(' - ')
                m.local_score = score[0]
                m.visitor_score = score[1]
                # TODO: Where is the parity?
                if score[0] > score[1]:
                    m.state = Match.LOCAL
                else:
                    m.state = Match.VISITOR
                print("MATCH FOUND: ", m)
                m.save()
            if not self.match_found(m)[0] and not self.match_found(m)[1]:
                print("Not found: ", m)
                m.state = Match.PLAYING
                m.save()
