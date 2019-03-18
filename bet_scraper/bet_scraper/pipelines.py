from datetime import datetime

from django.db.models import Q
from scrapy.exceptions import DropItem

from bet.models import BetRow
from football.models import Match, Team, LeagueRelatedName


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
        print("#########################################################")
        print("item", item['league'])
        print("league", checked_league)
        print("league?", checked_league.exists())
        print("#########################################################")
        if checked_league.exists():
            league = checked_league.first().league
            local_team, _ = Team.objects.update_or_create(
                name=item['local_team'], defaults={'league': league})
            visitor_team, _ = Team.objects.update_or_create(
                name=item['visitor_team'], defaults={'league': league})
            if checked_rules:
                # TODO: log this created match, date and number
                match, _ = Match.objects.filter(
                    start_datetime__date=datetime.today()
                ).update_or_create(
                    local_team=local_team,
                    visitor_team=visitor_team,
                    defaults={
                        'start_datetime': item['start_datetime'],
                        'local_factor': item['local_factor'],
                        'parity_factor': item['parity_factor'],
                        'visitor_factor': item['visitor_factor']})
                if match.state is Match.NOT_USED:
                    match.set_new()
                return item
            else:
                # TODO: log this discard match
                Match.objects.filter(
                    start_datetime__date=datetime.today(),
                    local_team=local_team,
                    visitor_team=visitor_team,
                    state=Match.NEW
                ).update(
                    state=Match.NOT_USED,
                    start_datetime=item['start_datetime'],
                    local_factor=item['local_factor'],
                    parity_factor=item['parity_factor'],
                    visitor_factor=item['visitor_factor'])

        raise DropItem("Match is not usable: %s" % item)


class LivescorePipeline:
    def process_item(self, item, spider):
        if item['local_score'] != "?" and item['visitor_score'] != "?":
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
