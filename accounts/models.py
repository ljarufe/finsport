from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe
from django.db import models

from fernet_fields import EncryptedCharField

from bet.selenium_bots.inkabet_selenium_bot import InkabetSeleniumBot
from bet_scraper.bet_scraper.spiders.inkabet_match_spider import (
    InkabetMatchSpider
)


class BetPage(models.Model):
    name = models.CharField(max_length=250)
    domain = models.URLField()
    match_list_url = models.URLField()
    active = models.BooleanField()

    BET_PAGE_BOTS = {
        'inkabet': {
            'match_spider': InkabetMatchSpider,
            'selenium_bot': InkabetSeleniumBot},
    }

    def __str__(self):
        return '{name}'.format(name=self.name)

    def get_match_spider(self):
        return self.BET_PAGE_BOTS[self.name.lower()]['match_spider']

    def get_selenium_bot(self):
        return self.BET_PAGE_BOTS[self.name.lower()]['selenium_bot']

    class Meta:
        verbose_name = 'Bet Page'
        verbose_name_plural = 'Bet Pages'


class Account(models.Model):
    username = models.CharField(max_length=64)
    password = EncryptedCharField(max_length=32)
    email = models.EmailField()
    bet_page = models.ForeignKey(BetPage, on_delete=models.CASCADE)
    funds = models.FloatField(default=0.0)
    num_allow_tables = models.IntegerField(default=1)
    start_bet = models.IntegerField()

    def __str__(self):
        return '%s' % self.username

    def increase_profit(self, profit):
        self.funds += profit
        self.save()

    def decrease_profit(self, profit):
        self.funds -= profit
        self.save()

    def send_finished_table(self, table, bet_row):
        self.increase_profit(table.total_profit)
        context = dict(
            table=table,
            bet_row=bet_row,
            link="{}{}".format(
                settings.INSTANCE_DOMAIN, '/bet/tables/?state=F'))
        msg = mark_safe(render_to_string('mails/finished_table.html', context))
        send_mail(
            subject='Ganaste!',
            message=strip_tags(msg),
            html_message=msg,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[self.email])

    class Meta:
        verbose_name = 'Account'
        verbose_name_plural = 'Accounts'
