# -*- coding: utf-8 -*-
from datetime import datetime

from scrapy.exceptions import DropItem

from football.models import Match, Team, LeagueRelatedName


class MatchPipeline(object):
    def process_item(self, item, spider):
        checked_rules = Match.check_rules(
            item['local_factor'], item['parity_factor'], item['visitor_factor'])
        checked_league = LeagueRelatedName.objects.filter(
            related_name__iexact=item['league']).exists()
        if checked_rules and checked_league:
            league = LeagueRelatedName.objects.get(
                related_name__iexact=item['league']).league
            local_team, _ = Team.objects.update_or_create(
                name=item['local_team'], defaults={'league': league})
            visitor_team, _ = Team.objects.update_or_create(
                name=item['visitor_team'], defaults={'league': league})
            # TODO: log this created match, date and number of matches created
            Match.objects.filter(
                start_datetime__date=datetime.today()
            ).update_or_create(
                local_team=local_team,
                visitor_team=visitor_team,
                defaults={
                    'start_datetime': item['start_datetime'],
                    'local_factor': item['local_factor'],
                    'parity_factor': item['parity_factor'],
                    'visitor_factor': item['visitor_factor']})
            return item

        raise DropItem("Match is not usable: %s" % item)
