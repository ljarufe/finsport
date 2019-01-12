# -*- coding: utf-8 -*-
import time
import random
import locale

from datetime import datetime, timedelta
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from scrapy.selector import Selector
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

from accounts.models import Account
from bet.models import DataTable
from football.models import League
from bet.constants import MAX_TIME_ATTEMPS_MINUTES

BET = (
    (1, 'local'),
    (2, 'parity'),
    (3, 'visitor'),
)
max_time = 15


def make_bet_selenium(my_match, my_bet=BET[1][0], amount=1):
    amount = round(amount, 2)
    inkabet = Account.objects.filter(bet_page__name__iexact="inkabet").first()
    date_time = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(
        '%s/chromedriver' % settings.SELENIUM_DATA,
        chrome_options=chrome_options)
    driver.set_window_size(2000, 2050)

    # Login
    driver.get(inkabet.bet_page.match_list_url)
    username = driver.find_element_by_id('user_username')
    password = driver.find_element_by_id('user_password')
    driver.save_screenshot(
        '%s/finsport-after-login-%s.png' % (settings.SELENIUM_DATA, date_time))
    submit = driver.find_element_by_name('commit')
    username.clear()
    username.send_keys(inkabet.username)
    password.send_keys(inkabet.password)
    submit.click()
    time.sleep(random.randint(3, max_time))

    print("driver.current_url: ", driver.current_url)
    driver.find_element_by_xpath(
        "//section/nav/ul/li/a[@data-eventpath-id='240']").click()
    time.sleep(random.randint(3, max_time))
    print("driver.current_url: ", driver.current_url)

    table = Selector(text=driver.page_source).css(
        'div.today_weekend_coupon_container table tbody tr')
    table2 = driver.find_elements(
        By.CSS_SELECTOR,
        'div.today_weekend_coupon_container table tbody tr')
    for i in range(len(table)):
        if 'event' not in table[i].xpath("@class").extract()[0]:
            continue

        factors = []
        bet = table2[i].find_elements_by_css_selector('a')
        for td in table[i].css('td'):
            if 'event' in td.xpath("@class").extract()[0]:
                match = td.css('a::text').extract_first().strip()
            if 'outcome' in td.xpath("@class").extract()[0]:
                factors.append(td.css('a::text').extract_first())

        if not len(factors) > 3:
            continue

        print("match: ", match)
        print("my_match: ", my_match)
        if match == my_match:
            try:
                bets = driver.find_elements_by_class_name(
                    'osg-betslip__content--empty')

                if not len(bets):
                    print(False,
                        'Error al realizar la apuesta se encontro una apuesta '
                        'ya seleccionada')
                    return (
                        False,
                        'Error al realizar la apuesta se encontro una apuesta '
                        'ya seleccionada')

                bet[my_bet].click()
                time.sleep(random.randint(3, max_time))
                driver.save_screenshot(
                    '%s/finsport-before-bet-%s.png' % (
                        settings.SELENIUM_DATA, date_time))
                combined = driver.find_elements_by_class_name(
                    'osg-betslip__selection--multiple')
                if len(combined):
                    return (
                        False,
                        'Error al realizar la apuesta se encontro una apuesta '
                        'combinada')

                amount_css = driver.find_elements_by_xpath(
                    "//div[@class='osg-betslip__input-field-container']//input[@type='text']")
                print("Monto: ", amount_css)
                print("amount: ", amount)
                driver.save_screenshot(
                    '%s/finsport-after-amout-%s.png' % (
                        settings.SELENIUM_DATA, date_time))
                try:
                    amount_css[0].send_keys(str(amount))
                except Exception as err:
                    print("ERROR PUTTING DATA: ", err)
                    driver.delete_all_cookies()
                    driver.close()
                    driver.quit()
                    del driver

                    return False, 'Error putting amount in field %s' % err, None

                driver.save_screenshot(
                    '%s/finsport-after-put-amout-%s.png' % (
                        settings.SELENIUM_DATA, date_time))
                time.sleep(random.randint(3, max_time))
                print("PUT AMOUNT")

                apostar = driver.find_element_by_class_name(
                    'osg-betslip__actions-place-bet-button')
                apostar.send_keys(Keys.RETURN)

                time.sleep(random.randint(3, max_time))
                receipt = driver.find_elements_by_class_name(
                    'osg-betslip__receipt-title')
                print("RECEIPT: ", receipt)
                if len(receipt):
                    print(True, 'Apuesta Realizada', factors)
                    driver.delete_all_cookies()
                    driver.close()
                    driver.quit()
                    del driver
                    return True, 'Apuesta Realizada', factors
                else:
                    error = driver.find_elements_by_class_name(
                        'osg-betslip__actions-errors-list-item')
                    print(False, 'Error al realizar la apuesta %s' % error[0].text)
                    driver.delete_all_cookies()
                    driver.close()
                    driver.quit()
                    del driver
                    return (
                        False,
                        'Error al realizar la apuesta %s' % error[0].text, None)
            except Exception as e:
                print(False, 'Error en la ejecucion: %s' % e)
                driver.delete_all_cookies()
                driver.close()
                driver.quit()
                del driver
                return False, 'Error en la ejecucion: %s' % e, None
    print(False, 'Match not Found')
    driver.delete_all_cookies()
    driver.close()
    driver.quit()
    del driver

    return False, 'Match not Found'


def count_iteration(table, data_table):

    return DataTable.objects.filter(
        bet_table=table, created__lt=data_table.created).count()


def obtain_league_matches():
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(
        '%s/chromedriver' % settings.SELENIUM_DATA,
        chrome_options=chrome_options)
    driver.set_window_size(2000, 2050)
    driver.get('https://www.inkabet.pe/es-ES/sportsbook/eventpaths/240')
    driver.find_element_by_xpath(
        "//section/nav/ul/li/a[@data-eventpath-id='240']/span").click()
    time.sleep(10)

    futbol = driver.find_elements_by_xpath(
        "//section/nav/ul/li[@class='sport_240']/ul/li")
    matches = []
    for li in futbol:
        a = li.find_element_by_css_selector('a')
        a.click()
        time.sleep(1)
        li = li.find_element_by_css_selector('ul li')
        league = League.objects.filter(country__iexact=a.text).first()
        if league:
            print("pais:", a.text)
            print("league:", league)
            li.click()
            time.sleep(20)
            table = driver.find_element_by_xpath(
                '//*[@id="main"]/section[2]/div/div[2]/div[1]')
            day = table.find_element_by_css_selector('h2').text
            print('daay:', day)
            day_datetime = datetime.strptime(
                '%s %s' % (day, 2018), '%A %d %B %Y').date()
            if day_datetime == datetime.now().date():
                match_table = table.find_elements_by_class_name('event-title')
                match_parity = table.find_elements_by_class_name(
                    'event_content')
                for i in range(len(match_table)):
                    teams = match_table[i].text.split('\n')[1].split(' - ')
                    parity = match_parity[i].find_elements_by_class_name(
                        'formatted_price')
                    date = '%s %s %s' % (day, 2018, teams[2])
                    date = datetime.strptime(date, '%A %d %B %Y %H:%M')
                    matches.append({
                        'local_team': teams[0],
                        'visitor_team': teams[1],
                        'start_datetime': date,
                        'factors': [
                            parity[0].text, parity[1].text, parity[2].text
                        ],
                        'league': league,
                    })
            li.click()
        a.click()
    time.sleep(5)

    return matches


def send_alert(table):
    users = User.objects.filter(is_staff=True).values_list('email', flat=True)
    iterations = DataTable.objects.filter(bet_table=table).count()

    message = (
        "La tabla creada el {name}  ha sido cerrada con el "
        "siguiente balance: \n\n"
        "Inversión: S/ {inversion}\n"
        "Ganancia neta: S/ {profit}\n"
        "Iteraciones: {iterations}\n\n"
        "Revisa la tabla en {link}"
    ).format(
        name=table.created.strftime('%d %b %Y %H:%M:%S'),
        iterations=iterations,
        inversion=round(table.total_inversion, 2),
        profit=round(table.total_profit, 2),
        link='%s/%s' % (settings.INSTANCE_DOMAIN, 'bet/tables/?state=finished')
    )

    send_mail(
        'Tabla finalizada',
        message,
        'luisjarufe@gmail.com',
        users,
    )


def check_time_for_attemps(init_time):

    return (datetime.now() - init_time) < timedelta(
        minutes=MAX_TIME_ATTEMPS_MINUTES)
