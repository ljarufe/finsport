# -*- coding: utf-8 -*-

import time

from selenium.webdriver.common.keys import Keys
from scrapy.selector import Selector
from selenium.webdriver.common.by import By

from bet.selenium_bots.selenium_bot import SeleniumBot
from football.models import Match


class InkabetSeleniumBot(SeleniumBot):
    LONG_SLEEP = 10
    SHORT_SLEEP = 5

    def __init__(self, account):
        self.account = account
        super().__init__()

    def login(self):
        self.driver.get(self.account.bet_page.domain)
        time.sleep(InkabetSeleniumBot.LONG_SLEEP)
        username = self.driver.find_element_by_id('user_username')
        password = self.driver.find_element_by_id('user_password')
        submit = self.driver.find_element_by_name('commit')
        username.clear()
        username.send_keys(self.account.username)
        password.send_keys(self.account.password)
        submit.click()
        time.sleep(InkabetSeleniumBot.LONG_SLEEP)

    def make_bet(self, bet_row):
        self.driver.get(self.account.bet_page.match_list_url)
        time.sleep(InkabetSeleniumBot.LONG_SLEEP)
        my_match = '%s - %s' % (
            bet_row.match.local_team.name,
            bet_row.match.visitor_team.name)
        table = Selector(text=self.driver.page_source).css(
            'div.today_weekend_coupon_container table tbody tr')
        table2 = self.driver.find_elements(
            By.CSS_SELECTOR,
            'div.today_weekend_coupon_container table tbody tr')
        # TODO: Buscar el partido por el nombre y no iterar
        for i in range(len(table)):
            if 'event' not in table[i].xpath("@class").extract()[0]:
                continue
            bet = table2[i].find_elements_by_css_selector('a')
            for td in table[i].css('td'):
                if 'event' in td.xpath("@class").extract()[0]:
                    match = td.css('a::text').extract_first().strip()
                    if match == my_match:
                        return self.bet(bet, bet_row.bet_amount)
        bet_row.remove_match()
        print('Error, el partido ya no existe')
        return False

    def bet(self, bet, amount):
        try:
            bets = self.driver.find_elements_by_class_name(
                'osg-betslip__content--empty')
            if not len(bets):
                print('Error, se encontro una apuesta seleccionada')
                return False
            bet[2].click()
            time.sleep(InkabetSeleniumBot.SHORT_SLEEP)
            combined = self.driver.find_elements_by_class_name(
                'osg-betslip__selection--multiple')
            if len(combined):
                print('Error, se encontro una apuesta combinada')
                return False
            amount_css = self.driver.find_elements_by_xpath(
                "//div[@class='osg-betslip__input-field-container']//input"
                "[@type='text']")
            try:
                amount_css[0].send_keys(str(amount))
            except Exception as err:
                print('Error, poniendo el monto en %s' % err)
                return False
            bet_button = self.driver.find_element_by_class_name(
                'osg-betslip__actions-place-bet-button')
            bet_button.send_keys(Keys.RETURN)
            time.sleep(InkabetSeleniumBot.SHORT_SLEEP)
            receipt = self.driver.find_elements_by_class_name(
                'osg-betslip__receipt-title')
            if len(receipt):
                print("Apuesta exitosa")
                return True
            else:
                error = self.driver.find_elements_by_class_name(
                    'osg-betslip__actions-errors-list-item')[0].text
                print('Error al realizar la apuesta %s' % error)
                return False
        except Exception as e:
            print('Error en la ejecucion: %s' % e)
            # TODO: testear si es necesario y ponerle timer
            self.driver.refresh()
            time.sleep(InkabetSeleniumBot.LONG_SLEEP)
            self.bet(bet, amount)
            return False

    def get_results(self):
        self.driver.find_element_by_xpath(
            "//*[@id='user_balance']/span").click()
        time.sleep(InkabetSeleniumBot.SHORT_SLEEP)
        table = Selector(text=self.driver.page_source).xpath(
            "//*[@id='history_table']/tbody/tr")
        for match in Match.objects.filter(state=Match.PLAYING):
            for i in range(1, len(table)):
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
                if (teams[2] == match.local_team.name and
                        match.visitor_team.name == teams[3]):
                    match.state = state
                    match.save()
