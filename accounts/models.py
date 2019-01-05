from fernet_fields import EncryptedCharField

from django.db import models

from football.models import Team
from spider.spider.spiders.inkabet_spider import InkabetSpider


class BetPage(models.Model):
    """
    Bet page
    """

    name = models.CharField(max_length=250)
    domain = models.URLField()
    match_list_url = models.URLField()
    active = models.BooleanField()

    BET_PAGE_SPIDERS = {
        'inkabet': InkabetSpider,
    }

    def __str__(self):
        return '{name}'.format(name=self.name)

    def get_spider(self):
        return self.BET_PAGE_SPIDERS[self.name.lower()]

    class Meta:
        verbose_name = 'Bet Page'
        verbose_name_plural = 'Bet Pages'


class Account(models.Model):
    """
    Bet page account
    """

    username = models.CharField(max_length=64)
    password = EncryptedCharField(max_length=32)
    minimum_bet = models.IntegerField()
    bet_page = models.ForeignKey(BetPage, on_delete=models.CASCADE)
    funds = models.FloatField(default=0.0)
    profit_to_tables = models.FloatField(default=0.0)
    profit_to_tables_index = models.FloatField(default=0.0)
    num_allow_tables = models.IntegerField(default=1)
    favorite_team = models.ForeignKey(
        Team, on_delete=models.CASCADE, null=True, blank=True)
    min_favorite_bet = models.FloatField(default=2)
    max_favorite_bet = models.FloatField(default=4)

    def __str__(self):
        return '%s' % self.username

    class Meta:
        verbose_name = 'Account'
        verbose_name_plural = 'Accounts'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
