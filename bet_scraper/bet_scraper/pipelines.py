import logging

from datetime import datetime

from django.db.models import Q
from scrapy.exceptions import DropItem

from bet.models import BetRow
from football.models import Match, Team, LeagueRelatedName

logger_get_matches = logging.getLogger('get_matches')
logger_inkabet_results = logging.getLogger('inkabet_results')


class MatchPipeline:
    def process_item(self, item, spider):
        # TODO: lleva esta lógica a match en varias funciones
        checked_league = LeagueRelatedName.objects.filter(
            related_name__icontains=item['league'])
        if checked_league.exists():
            league = checked_league.first().league
            local_team, _ = Team.objects.update_or_create(
                name=item['local_team'], defaults={'league': league})
            visitor_team, _ = Team.objects.update_or_create(
                name=item['visitor_team'], defaults={'league': league})
            checked_rules, msg = Match.check_rules(
                item['local_factor'],
                item['draw_factor'],
                item['visitor_factor']
            )
            if checked_rules:
                match, created = Match.objects.filter(
                    start_datetime__date=datetime.today()
                ).update_or_create(
                    local_team=local_team,
                    visitor_team=visitor_team,
                    defaults={
                        'start_datetime': item['start_datetime'],
                        'local_factor': item['local_factor'],
                        'draw_factor': item['draw_factor'],
                        'visitor_factor': item['visitor_factor']})
                if created:
                    logger_get_matches.info(
                        "Created match: %s" % match.get_logger_info())
                else:
                    if match.state is Match.NOT_USED:
                        match.set_new()
                        logger_get_matches.info(
                            "Match set as new: %s" % match.get_logger_info())
                    else:
                        logger_get_matches.info(
                            "Updated match: %s" % match.get_logger_info())
                return item
            else:
                try:
                    match = Match.objects.get(
                        start_datetime__date=datetime.today(),
                        local_team=local_team,
                        visitor_team=visitor_team,
                        state=Match.NEW
                    )
                    match.start_datetime = item['start_datetime']
                    match.local_factor = item['local_factor']
                    match.draw_factor = item['draw_factor']
                    match.visitor_factor = item['visitor_factor']
                    match.set_not_used()
                    logger_get_matches.info(
                        "Not used match: %s because: %s" %
                        (match.get_logger_info(), msg))
                except Match.DoesNotExist:
                    pass

        raise DropItem("Match is not usable: %s" % item)


class LivescorePipeline:
    def process_item(self, item, spider):
        if item['local_score'] != "?" and item['visitor_score'] != "?":
            local_query = Q()
            for w in filter(lambda x: len(x) > 2, item['local_team'].split()):
                local_query |= Q(local_team__name__unaccent__icontains=w)
            visitor_query = Q()
            for w in filter(lambda x: len(x) > 2, item['visitor_team'].split()):
                visitor_query |= Q(visitor_team__name__unaccent__icontains=w)
            matches = Match.objects.filter(local_query & visitor_query).filter(
                start_datetime__date=datetime.today())
            if matches.exists():
                # TODO: buscar los FT y poner quién ganó
                matches.update(
                    local_score=int(item['local_score']),
                    visitor_score=int(item['visitor_score'])
                )

        raise DropItem("This match is not finished yet: %s" % item)


class ResultsPipeline:
    def process_item(self, item, spider):
        bet_rows = BetRow.objects.filter(
            match__local_team__name__icontains=item['local_team'],
            match__visitor_team__name__icontains=item['visitor_team'],
            state=BetRow.CURRENT)
        if bet_rows.exists():
            bet_row = bet_rows.first()
            if item['result'] is BetRow.WON:
                bet_row.bet_table.set_finished(spider.account, bet_row)
                logger_inkabet_results.info(
                    "Won match: %s" % bet_row.match.get_logger_info())
            else:
                bet_row.set_lost()
                logger_inkabet_results.info(
                    "Lost match: %s" % bet_row.match.get_logger_info())
