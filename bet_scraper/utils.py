from django.conf import settings


PIPELINES = {
    'check_results': {
        'ITEM_PIPELINES': {
            'bet_scraper.bet_scraper.pipelines.LivescorePipeline': 300}
    },
    'check_results_inkabet': {
        'ITEM_PIPELINES': {
            'bet_scraper.bet_scraper.pipelines.ResultsPipeline': 300},
    },
    'get_matches': {
        'ITEM_PIPELINES': {
            'bet_scraper.bet_scraper.pipelines.MatchPipeline': 300},
    },
    'get_leagues': {
        'ITEM_PIPELINES': {
            'bet_scraper.bet_scraper.pipelines.LeaguesPipeline': 300},
    }
}


def get_crawler_options(command):
    return {**settings.CRAWLER_OPTIONS, **PIPELINES[command]}
