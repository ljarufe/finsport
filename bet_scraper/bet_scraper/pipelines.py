# -*- coding: utf-8 -*-

from scrapy.exceptions import DropItem

from football.models import Match, Team, LeagueRelatedName


class MatchPipeline(object):
    def process_item(self, item, spider):
        checked_league = LeagueRelatedName.objects.filter(
                related_name__iexact=item['league']).exists()
        checked_rules = Match.check_rules(
            item['local_factor'], item['parity_factor'], item['visitor_factor'])
        if checked_league and checked_rules:
            league = LeagueRelatedName.objects.get(
                related_name__iexact=item['league']).league
            local_team, _ = Team.objects.update_or_create(
                name=item['local_team'],
                defaults={
                    'league': league
                }
            )
            visitor_team, _ = Team.objects.update_or_create(
                name=item['visitor_team'],
                defaults={
                    'league': league
                }
            )
            Match.objects.update_or_create(
                local_team=local_team,
                visitor_team=visitor_team,
                start_datetime=item['start_datetime'],
                defaults={
                    'local_factor': item['local_factor'],
                    'parity_factor': item['parity_factor'],
                    'visitor_factor': item['visitor_team'],
                },
            )
            return item

        raise DropItem("Match is not usable: %s" % item)
