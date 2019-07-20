# -*- coding: utf-8 -*-

import time
import logging

from datetime import datetime, timedelta

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.keys import Keys
from scrapy.selector import Selector
from selenium.webdriver.common.by import By

from bet.selenium_bots.selenium_bot import SeleniumBot

logger = logging.getLogger('make_bets')


class InkabetSeleniumBot(SeleniumBot):
    LONG_SLEEP = 10
    SHORT_SLEEP = 5
    RETRY_TIME = 3

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
        time.sleep(InkabetSeleniumBot.SHORT_SLEEP)

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
        logger.info("Error, match is not longer available")
        return False

    def bet(self, bet, amount):
        try:
            empty = len(self.driver.find_elements_by_class_name(
                'osg-betslip__content--empty'))
            if not empty:
                # TODO: limpiar las apuestas seleccionadas
                logger.info("Error, a bet is already selected")
                return False
            bet[2].click()
            time.sleep(InkabetSeleniumBot.SHORT_SLEEP)
            combined = self.driver.find_elements_by_class_name(
                'osg-betslip__selection--multiple')
            if len(combined):
                logger.info('Error, a multiple bet is already selected')
                return False
            amount_css = self.driver.find_elements_by_xpath(
                "//div[@class='osg-betslip__input-field-container']//input"
                "[@type='text']")
            amount_css[0].send_keys(str(amount))
        except Exception as err:
            logger.info('Error, putting the amount: %s' % err)
            return False

        return self.confirm_bet(datetime.now())

    def confirm_bet(self, init):
        try:
            bet_button = self.driver.find_element_by_class_name(
                'osg-betslip__actions-place-bet-button')
            bet_button.send_keys(Keys.RETURN)
            time.sleep(InkabetSeleniumBot.SHORT_SLEEP)
            receipt = self.driver.find_elements_by_class_name(
                'osg-betslip__receipt-title')
            if len(receipt):
                logger.info("Successful bet")
                return True
            else:
                error = self.driver.find_elements_by_class_name(
                    'osg-betslip__actions-errors-list-item')[0].text
                logger.info('Error, pressing confirm: %s' % error)
                return False
        except Exception as e:
            if init + timedelta(minutes=InkabetSeleniumBot.RETRY_TIME) < (
                    datetime.now()):
                logger.info('Error: %s' % e)
                return False
            self.driver.refresh()
            time.sleep(InkabetSeleniumBot.LONG_SLEEP)

            return self.confirm_bet(init)

    def emergency_refund(self, bet_row):
        self.driver.find_element_by_css_selector(
            "div.osg-my-bets__opener").click()
        items = self.driver.find_elements_by_css_selector(
            "div.osg-my-bets__panel")
        for item in items:
            local_team = item.find_element_by_css_selector(
                "div.osg-my-bets__selection-info-outcome-event-description"
            ).text.split(" - ")[0]
            if local_team == bet_row.match.local_team.name:
                try:
                    button = item.find_element_by_css_selector(
                        "button.osg-my-bets__cashout--button")
                    if float(button.text.split()[-1]) <= bet_row.bet_amount * 1.5:
                        button.click()
                        print("hola")
                        # self.driver.find_element_by_css_selector(
                        #     "button.osg-my-bets__cashout--confirmation-yes").click()
                        self.driver.find_element_by_css_selector(
                            "button.osg-my-bets__cashout--confirmation-no").click()
                        time.sleep(5)
                except NoSuchElementException:
                    print("chau")

        return

    def stop_refund(self, bet_row):
        self.driver.find_element_by_css_selector(
            "div.osg-my-bets__opener").click()
        time.sleep(5)
        items = self.driver.find_elements_by_css_selector(
            "button.osg-my-bets__cashout--button")
        for item in items:
            print(item.text.split()[-1])
            item.click()
            # self.driver.find_element_by_css_selector(
            #     "button.osg-my-bets__cashout--confirmation-yes").click()
            self.driver.find_element_by_css_selector(
                "button.osg-my-bets__cashout--confirmation-no").click()
        return
