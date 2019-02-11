# -*- coding: utf-8 -*-

from .models import Match


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
