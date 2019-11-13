# -*- coding: utf-8 -*-

import time
import logging

from datetime import datetime, timedelta
from urllib.parse import urljoin

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.keys import Keys

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
        self.driver.get(urljoin(self.account.bet_page.domain, 'login'))
        time.sleep(InkabetSeleniumBot.SHORT_SLEEP)
        username = self.driver.find_element_by_name('username')
        password = self.driver.find_element_by_name('password')
        submit = self.driver.find_element_by_xpath(
            '//*[@id="osg-app"]/div/div[1]/form/button')
        username.clear()
        username.send_keys(self.account.username)
        password.send_keys(self.account.password)
        submit.click()
        time.sleep(InkabetSeleniumBot.SHORT_SLEEP)

    def make_bet(self, bet_row):
        self.driver.get(
            urljoin(self.account.bet_page.domain, bet_row.match.inkabet_url))
        time.sleep(InkabetSeleniumBot.SHORT_SLEEP)
        bet = self.driver.find_elements_by_xpath(
            '//*[@id="osg-app"]/div/div[1]/div/div[2]/div[2]/div[2]/div[2]'
            '/div[2]/div/div[2]/div/div')
        if len(bet) > 0:
            return self.bet(bet[0], bet_row.bet_amount)
        bet_row.remove_match()
        logger.info("Error, match is not longer available")

        return False

    def bet(self, bet, amount):
        try:
            clean_bets = self.driver.find_elements_by_xpath(
                '//*[@id="osg-app"]/div/div[1]/div/div[3]/div[1]/div/div'
                '/div[2]/div/div[3]/div[3]/button')
            if len(clean_bets) > 0:
                clean_bets[0].click()
            bet.click()
            time.sleep(InkabetSeleniumBot.SHORT_SLEEP)
            amount_css = self.driver.find_element_by_xpath(
                '//*[@id="osg-app"]/div/div[1]/div/div[3]/div[1]/div/div/div[2]'
                '/div/div[1]/div[2]/div[2]/div[1]/div[2]/input')
            amount_css.send_keys(str(amount))
        except Exception as err:
            logger.info('Error, putting the amount: %s' % err)
            return False

        return self.confirm_bet(datetime.now())

    def confirm_bet(self, init):
        try:
            bet_button = self.driver.find_element_by_xpath(
                '//*[@id="osg-app"]/div/div[1]/div/div[3]/div[1]/div/div/div[2]'
                '/div/div[3]/div[2]/button')
            bet_button.send_keys(Keys.RETURN)
            time.sleep(InkabetSeleniumBot.SHORT_SLEEP)
            error = self.driver.find_elements_by_xpath(
                '//*[@id="osg-app"]/div/div[1]/div/div[3]/div[1]/div/div/'
                'div[2]/div/div[3]/div[2]/ul/li')
            if len(error) > 0:
                logger.info('Error, pressing confirm: %s' % error[0].text)
                return False
            else:
                logger.info("Successful bet")
                return True
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
