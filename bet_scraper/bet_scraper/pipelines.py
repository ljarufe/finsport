import logging

from datetime import datetime

from django.db.models import Q

from scrapy.exceptions import DropItem
from twisted.internet.threads import deferToThread

from accounts.models import Account
from bet.models import BetRow, BetTable
from football.models import Match, Team, LeagueRelatedName, League

logger_get_matches = logging.getLogger("get_matches")
logger_inkabet_results = logging.getLogger("inkabet_results")
logger_leagues = logging.getLogger("leagues")


class MatchPipeline:
    def process_item(self, item, spider):
        league = LeagueRelatedName.get_league(
            item["league"], item["country"], spider.bet_page
        )
        if league and item["start_datetime"] > datetime.now():
            local_team, _ = Team.objects.update_or_create(
                name=item["local_team"], defaults={"league": league}
            )
            visitor_team, _ = Team.objects.update_or_create(
                name=item["visitor_team"], defaults={"league": league}
            )
            match, created = Match.objects.filter(
                start_datetime__date=datetime.today(),
            ).update_or_create(
                local_team=local_team,
                visitor_team=visitor_team,
                defaults={
                    "inkabet_url": item["url"],
                    "start_datetime": item["start_datetime"],
                    "local_factor": item["local_factor"],
                    "draw_factor": item["draw_factor"],
                    "visitor_factor": item["visitor_factor"],
                },
            )
            checked_rules, msg = match.check_rules()
            if checked_rules:
                if created:
                    logger_get_matches.info(f"Created match: {match.get_logger_info()}")
                elif match.state is Match.NOT_USED:
                    match.set_new()
                    logger_get_matches.info(
                        f"Match set as new: {match.get_logger_info()}"
                    )
                return item
            if created:
                match.set_not_used()
                logger_get_matches.info(
                    f"Not used match: {match.get_logger_info()} because: {msg}"
                )
            return item

        raise DropItem(f"Match is not usable: {item}")


class LivescorePipeline:
    def process_item(self, item, spider):
        if item["local_score"] != "?" and item["visitor_score"] != "?":
            # TODO: Poner todo esto en un manager en Match
            local_query = Q()
            for w in filter(lambda x: len(x) > 2, item["local_team"].split()):
                local_query |= Q(local_team__name__unaccent__icontains=w)
            visitor_query = Q()
            for w in filter(lambda x: len(x) > 2, item["visitor_team"].split()):
                visitor_query |= Q(visitor_team__name__unaccent__icontains=w)
            matches = Match.objects.filter(local_query & visitor_query).filter(
                start_datetime__date=datetime.today()
            )
            if matches.exists():
                # TODO: buscar los FT y poner quién ganó
                matches.update(
                    local_score=int(item["local_score"]),
                    visitor_score=int(item["visitor_score"]),
                )
            return item

        raise DropItem(f"This match is not finished yet: {item}")


class ResultsPipeline:
    def process_item(self, item, spider):
        bet_rows = BetRow.objects.filter(
            match__local_team__name__icontains=item["local_team"],
            match__visitor_team__name__icontains=item["visitor_team"],
            state=BetRow.CURRENT,
        )
        if bet_rows.exists():
            bet_row = bet_rows.first()
            if item["result"]:
                if item["result"] == "Ganadas":
                    bet_row.set_won()
                    bet_row.bet_table.set_finished()
                    spider.account.send_finished_table(
                        bet_row.bet_table, bet_row, Account.GANADA
                    )
                    logger_inkabet_results.info(
                        f"Won match: {bet_row.match.get_logger_info()}"
                    )
                elif item["result"] == "Perdidas":
                    bet_row.set_lost()
                    if bet_row.iteration > BetTable.MAX_ITERATION:
                        bet_row.bet_table.set_finished()
                        spider.account.send_finished_table(
                            bet_row.bet_table, bet_row, Account.PERDIDA
                        )
                    logger_inkabet_results.info(
                        f"Lost match: {bet_row.match.get_logger_info()}"
                    )
                elif item["result"] == "Transacción cancelada":
                    bet_row.remove_match()
                    logger_inkabet_results.info(
                        f"Suspended match: {bet_row.match.get_logger_info()}"
                    )
            return item

        raise DropItem(f"Match does not exist: {item}")


class LeaguesPipeline:
    async def process_item(self, item, spider):
        def _save():
            league, created = League.objects.update_or_create(
                name=item["name"],
                country=item["country"],
                defaults={"draw_percentage": item["percentage"]},
            )
            if created:
                logger_leagues.info(f"League created: {league}")

            return item

        return deferToThread(_save)
