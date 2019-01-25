# -*- coding: utf-8 -*-

import time

from django.core.management.base import BaseCommand
from django.conf import settings

from scrapy.selector import Selector
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from football.models import Match

from accounts.models import Account


class Command(BaseCommand):
    help = 'Check and save matches results'

    def handle(self, *args, **options):
        accounts = Account.objects.filter(bet_page__active=True)
        for account in accounts:
            matches = Match.objects.filter(state=Match.PLAYING)
            print("matches: ", matches)
            # TODO: Mode all the scraper logic to the Inkabet scraper
            chrome_options = Options()
            # TODO: create a setting to activate the headless option in all
            #  the code
            chrome_options.add_argument("--headless")
            driver = webdriver.Chrome(
                '%s/chromedriver' % settings.SELENIUM_DATA,
                chrome_options=chrome_options)
            driver.set_window_size(2000, 2050)

            # Login
            driver.get('https://www.account.pe/es-ES/sportsbook')
            username = driver.find_element_by_id('user_username')
            password = driver.find_element_by_id('user_password')
            submit = driver.find_element_by_name('commit')
            username.send_keys(account.username)
            password.send_keys(account.password)
            submit.click()
            time.sleep(3)

            driver.find_element_by_xpath("//*[@id='user_balance']/span").click()
            time.sleep(3)

            table = Selector(text=driver.page_source).xpath(
                "//*[@id='history_table']/tbody/tr")
            for match in matches:
                for i in range(1, len(table)):
                    # TODO: Get the visitor result
                    if 'lost' in table[i].xpath("@class").extract()[0]:
                        state = Match.LOCAL
                    elif 'won' in table[i].xpath("@class").extract()[0]:
                        state = Match.PARITY
                    elif 'void ' in table[i].xpath("@class").extract()[0]:
                        state = Match.UNKNOW
                    else:
                        continue
                    teams = table[i].xpath(
                        'td[6]/span/span/text()').extract()[1].split(' - ')
                    print(teams[2], '-', teams[3])
                    if (teams[2] == match.local_team.name and
                            match.visitor_team.name in teams[3]):
                        match.state = state
                        match.save()
