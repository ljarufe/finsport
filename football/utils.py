# -*- coding: utf-8 -*-
from datetime import datetime

from django.core.exceptions import ObjectDoesNotExist

from .models import Match, Team
from bet.rules import Rules
from .constants import MATCH_STATES
from .models import League, LeagueRelatedName


def save_match(data, favorite_team=None):
    local_team = data.get('local_team', None)
    visitor_team = data.get('visitor_team', None)
    league = data.get('league', None)
    start_datetime = data.get('start_datetime', None)
    start_datetime = datetime.strptime(start_datetime, '%d-%m-%y %H:%M')
    factors = list(map(lambda x: float(x), data.get('factors', [])[:3]))
    local_team, _ = Team.objects.get_or_create(name=local_team)
    visitor_team, _ = Team.objects.get_or_create(name=visitor_team)

    if (favorite_team and favorite_team.name in
            [local_team.name, visitor_team.name]):
        Match.objects.update_or_create(
            local_team=local_team,
            visitor_team=visitor_team,
            start_datetime=start_datetime,
            match_state=MATCH_STATES[7][0],
            match_state_half_time=MATCH_STATES[7][0],
            defaults={
                'local_factor': factors[0],
                'parity_factor': factors[1],
                'visitor_factor': factors[2],
            },
        )
        return data['url']
    elif (Rules.evaluate(factors[0], factors[1], factors[2]) and
            check_league(local_team, visitor_team, league)):
        Match.objects.update_or_create(
            local_team=local_team,
            visitor_team=visitor_team,
            start_datetime=start_datetime,
            match_state=MATCH_STATES[0][0],
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


def save_half_match(data):
    local_team = data.get('local_team', None)
    visitor_team = data.get('visitor_team', None)
    halftime_factors = data.get('halftime_factors', [])

    matches = Match.objects.filter(
        visitor_team__name=visitor_team, local_team__name=local_team)
    if matches:
        matches.first().local_factor_half_time = halftime_factors[0]
        matches.first().parity_factor_half_time = halftime_factors[1]
        matches.first().visitor_factor_half_time = halftime_factors[2]
        matches.first().save()
    else:
        print("ERROR: It doesn't have half time bet")


def save_result(match, data):
    try:
        if data and len(data['score']) == 2:
            score = data.get('score')
            state = data.get('state')

            if(state == 'Finalizado' or state == 'Full-time' or
                    state == 'Final'):
                match.local_score = score[0]
                match.visitor_score = score[1]
                if score[0] > score[1]:
                    match.match_state = 3
                elif score[0] < score[1]:
                    match.match_state = 5
                else:
                    match.match_state = 4
        elif data['score'][0] == 'vs.':
            match.match_state = 2
    except:
        match.match_state = 2

    match.save()
