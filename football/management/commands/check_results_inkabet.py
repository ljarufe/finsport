# -*- coding: utf-8 -*-
import time

from django.core.management.base import BaseCommand
from django.conf import settings

from scrapy.selector import Selector
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from football.models import Match
from football.constants import MATCH_STATES

from accounts.models import Account


class Command(BaseCommand):
    help = 'Check and save matches results'

    def handle(self, *args, **options):
        inkabet = Account.objects.filter(
            bet_page__name__iexact="inkabet").first()
        matches = Match.objects.filter(match_state=2)
        print("matches: ", matches)

        chrome_options = Options()
        chrome_options.add_argument("--headless")
        driver = webdriver.Chrome(
            '%s/chromedriver' % settings.SELENIUM_DATA,
            chrome_options=chrome_options)
        driver.set_window_size(2000, 2050)

        # Login
        driver.get('https://www.inkabet.pe/es-ES/sportsbook')

        username = driver.find_element_by_id('user_username')
        password = driver.find_element_by_id('user_password')
        submit = driver.find_element_by_name('commit')
        username.send_keys(inkabet.username)
        password.send_keys(inkabet.password)
        submit.click()
        time.sleep(3)

        driver.find_element_by_xpath("//*[@id='user_balance']/span").click()
        time.sleep(3)

        table = Selector(text=driver.page_source).xpath(
            "//*[@id='history_table']/tbody/tr")
        for match in matches:
            for i in range(1, len(table)):
                if 'lost' in table[i].xpath("@class").extract()[0]:
                    state = MATCH_STATES[3][0]
                elif 'won' in table[i].xpath("@class").extract()[0]:
                    state = MATCH_STATES[4][0]
                elif 'void ' in table[i].xpath("@class").extract()[0]:
                    state = MATCH_STATES[6][0]
                else:
                    continue

                teams = table[i].xpath(
                    'td[6]/span/span/text()').extract()[1].split(' - ')
                print(teams[2], '-', teams[3])
                if (teams[2] == match.local_team.name and
                        match.visitor_team.name in teams[3]):
                    match.match_state = state
                    match.save()
