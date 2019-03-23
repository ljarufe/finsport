# -*- coding: utf-8 -*-

import time

from django.conf import settings

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


class SeleniumBot:
    LONG_SLEEP = 5

    def __init__(self):
        self.driver = SeleniumBot._set_driver()

    def clean_driver(self):
        self.driver.delete_all_cookies()
        self.driver.close()
        self.driver.quit()

    def get_page_source(self, url):
        self.driver.get(url)
        time.sleep(SeleniumBot.LONG_SLEEP)

        return self.driver.page_source

    @staticmethod
    def _set_driver():
        chrome_options = Options()
        if not settings.DEBUG:
            chrome_options.add_argument("--headless")
        driver = webdriver.Chrome(
            '%s/chromedriver' % settings.SELENIUM_DATA,
            chrome_options=chrome_options)
        driver.set_window_size(2000, 2050)

        return driver
