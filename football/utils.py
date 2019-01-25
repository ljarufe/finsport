# -*- coding: utf-8 -*-

from datetime import datetime

from django.core.exceptions import ObjectDoesNotExist

from bet.rules import Rules
from .models import Match, Team
from .models import League, LeagueRelatedName


def save_match(data):
    local_team = data.get('local_team', None)
    visitor_team = data.get('visitor_team', None)
    league = data.get('league', None)
    start_datetime = data.get('start_datetime', None)
    start_datetime = datetime.strptime(start_datetime, '%d-%m-%y %H:%M')
    factors = list(map(lambda x: float(x), data.get('factors', [])[:3]))
    local_team, _ = Team.objects.get_or_create(name=local_team)
    visitor_team, _ = Team.objects.get_or_create(name=visitor_team)
    if (Rules.evaluate(factors[0], factors[1], factors[2]) and
            check_league(local_team, visitor_team, league)):
        Match.objects.update_or_create(
            local_team=local_team,
            visitor_team=visitor_team,
            start_datetime=start_datetime,
            state=Match.NEW,
            defaults={
                'local_factor': factors[0],
                'parity_factor': factors[1],
                'visitor_factor': factors[2],
            },
        )
        return data['url']

    return None


def save_league_match(data):
    local_team = data.get('local_team', None)
    visitor_team = data.get('visitor_team', None)
    start_datetime = data.get('start_datetime', None)
    league = data.get('league', None)
    factors = list(map(lambda x: float(x), data.get('factors', [])[:3]))
    local_team, _ = Team.objects.get_or_create(name__iexact=local_team)
    visitor_team, _ = Team.objects.get_or_create(name__iexact=visitor_team)
    local_team.league = league
    visitor_team.league = league
    local_team.save()
    visitor_team.save()
    Match.objects.update_or_create(
        local_team=local_team,
        visitor_team=visitor_team,
        start_datetime=start_datetime,
        defaults={
            'local_factor': factors[0],
            'parity_factor': factors[1],
            'visitor_factor': factors[2],
        },
    )


def check_league(local_team, visitor_team, league):
    try:
        league2 = League.objects.get(name__iexact=league)
    except ObjectDoesNotExist:
        try:
            league2 = LeagueRelatedName.objects.get(
                related_name__iexact=league).league
        except ObjectDoesNotExist:
            return False
    local_team.league = league2
    visitor_team.league = league2
    return True


def save_result(match, data):
    try:
        if data and len(data['score']) == 2:
            score = data.get('score')
            state = data.get('state')

            # TODO: Use if state in (xxx)
            if(state == 'Finalizado' or state == 'Full-time' or
                    state == 'Final'):
                match.local_score = score[0]
                match.visitor_score = score[1]
                if score[0] > score[1]:
                    match.state = Match.LOCAL
                elif score[0] < score[1]:
                    match.state = Match.VISITOR
                else:
                    match.state = Match.PARITY
        elif data['score'][0] == 'vs.':
            match.state = Match.PLAYING
    # TODO: Check which exception is used here
    except:
        match.state = Match.PLAYING

    match.save()
