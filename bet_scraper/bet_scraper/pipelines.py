import logging

from datetime import datetime

from django.db.models import Q
from scrapy.exceptions import DropItem

from bet.models import BetRow
from football.models import Match, Team, LeagueRelatedName

logger = logging.getLogger('get_matches')


class MatchPipeline:
    def process_item(self, item, spider):
        # TODO: lleva esta lógica a match en varias funciones
        checked_rules = Match.check_rules(
            item['start_datetime'],
            item['local_factor'],
            item['parity_factor'],
            item['visitor_factor']
        )
        checked_league = LeagueRelatedName.objects.filter(
            related_name__icontains=item['league'])
        if checked_league.exists():
            league = checked_league.first().league
            local_team, _ = Team.objects.update_or_create(
                name=item['local_team'], defaults={'league': league})
            visitor_team, _ = Team.objects.update_or_create(
                name=item['visitor_team'], defaults={'league': league})
            if checked_rules:
                match, created = Match.objects.filter(
                    start_datetime__date=datetime.today()
                ).update_or_create(
                    local_team=local_team,
                    visitor_team=visitor_team,
                    defaults={
                        'start_datetime': item['start_datetime'],
                        'local_factor': item['local_factor'],
                        'parity_factor': item['parity_factor'],
                        'visitor_factor': item['visitor_factor']})
                if created:
                    logger.info("Created match: %s" % match.get_logger_info())
                else:
                    if match.state is Match.NOT_USED:
                        match.set_new()
                        logger.info(
                            "Match set as new: %s" % match.get_logger_info())
                    else:
                        logger.info(
                            "Updated match: %s" % match.get_logger_info())
                return item
            else:
                matches = Match.objects.filter(
                    start_datetime__date=datetime.today(),
                    local_team=local_team,
                    visitor_team=visitor_team,
                    state=Match.NEW
                )
                matches.update(
                    state=Match.NOT_USED,
                    start_datetime=item['start_datetime'],
                    local_factor=item['local_factor'],
                    parity_factor=item['parity_factor'],
                    visitor_factor=item['visitor_factor'])
                if matches.exists():
                    logger.info(
                        "Notused match: %s" % matches.first().get_logger_info())

        raise DropItem("Match is not usable: %s" % item)


class LivescorePipeline:
    def process_item(self, item, spider):
        logger.error("Notused match")
        if item['local_score'] != "?" and item['visitor_score'] != "?":
            # TODO: Agregar al filtro la fecha y hora del partido
            local_query = Q()
            for word in item['local_team'].split():
                local_query |= Q(local_team__name__unaccent__icontains=word)
            visitor_query = Q()
            for word in item['visitor_team'].split():
                visitor_query |= Q(visitor_team__name__unaccent__icontains=word)
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
            else:
                bet_row.set_lost()
