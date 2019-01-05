# -*- coding: utf-8 -*-
import urllib.request
import json

from django.core.management.base import BaseCommand
from django.db.models import Q

from football.models import Match
from football.constants import MATCH_STATES


class Command(BaseCommand):
    help = 'Get results to unknow matches'

    def __init__(self):
        url = 'http://livescore-api.com/api-client/scores/live.json?key=OsnX22n686bJQzeO&secret=Q953EfOsAoiSK9SzCfwFiTLq0WaRvoGm'
        with urllib.request.urlopen(url) as url:
            self.data = json.loads(url.read().decode())
            self.matches = self.data['data'].get('match', None)
            # print("self.data: ", json.dumps(self.data, indent=4))
            # print("self.matches: ", json.dumps(self.matches, indent=4))

    def match_found(self, match):
        # self.matches = self.data['data'].get('match', None)
        # print("SELF.MATCHES: ", len(self.matches))
        for m in self.matches:
            # print("M: ", m)
            if(any(w in match.local_team.name for w in m['home_name'].split(
                " ")) and any(w in match.visitor_team.name for w in m[
                    'away_name'].split(" "))):
                if not m['time'] == 'FT':
                    return True, None
                return True, m
            # else:
        return False, None

    def handle(self, *args, **options):
        matches = Match.objects.filter(
            Q(match_state=MATCH_STATES[6][0]) |
            Q(match_state=MATCH_STATES[2][0]),
        )

        for m in matches:
            if self.match_found(m)[0] and not self.match_found(m)[1]:
                continue
            if self.match_found(m)[0] and self.match_found(m)[1]:
                json_match = self.match_found(m)[1]
                score = json_match['score'].split(' - ')
                m.local_score = score[0]
                m.visitor_score = score[1]
                if score[0] > score[1]:
                    m.match_state = MATCH_STATES[3][0]
                else:
                    m.match_state = MATCH_STATES[5][0]
                print("MATCH FOUND: ", m)
                m.save()
            if not self.match_found(m)[0] and not self.match_found(m)[1]:
                print("Not found: ", m)
                m.match_state = MATCH_STATES[2][0]
                m.save()
