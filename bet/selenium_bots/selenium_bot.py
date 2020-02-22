# -*- coding: utf-8 -*-

import logging
import time

from django.conf import settings

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options

logger_scrapy = logging.getLogger('scrapy_extra')


class SeleniumBot:
    SHORT_SLEEP = 5

    def __init__(self):
        self.driver = SeleniumBot._set_driver()

    def clean_driver(self):
        self.driver.delete_all_cookies()
        self.driver.quit()

    def get_page_source(self, url, sleep_time=SHORT_SLEEP, scroll_down=False):
        try:
            self.driver.get(url)
        except TimeoutException:
            logger_scrapy.info("Timeout escaped")
            self.driver.quit()
            return
        time.sleep(sleep_time)
        if scroll_down:
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(sleep_time)
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);")

        return self.driver.page_source

    @staticmethod
    def _set_driver():
        chrome_options = Options()
        if not settings.DEBUG:
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument('--no-sandbox')
        driver = webdriver.Chrome(
            '%s/chromedriver' % settings.SELENIUM_DATA,
            chrome_options=chrome_options)
        driver.set_window_size(2000, 2050)

        return driver
