from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe
from django.db import models

from fernet_fields import EncryptedCharField

from bet.selenium_bots.inkabet_selenium_bot import InkabetSeleniumBot


class BetPage(models.Model):
    name = models.CharField(max_length=250)
    domain = models.URLField()
    active = models.BooleanField()

    BET_PAGE_BOTS = {
        "inkabet": {"selenium_bot": InkabetSeleniumBot},
    }

    def __str__(self):
        return f"{self.name}"

    def get_selenium_bot(self):
        return self.BET_PAGE_BOTS[self.name.lower()]["selenium_bot"]

    class Meta:
        verbose_name = "Bet Page"
        verbose_name_plural = "Bet Pages"


class Account(models.Model):
    GANADA = "g"
    PERDIDA = "p"
    RESULTADOS = {
        GANADA: "ganada",
        PERDIDA: "perdida",
    }

    username = models.CharField(max_length=64)
    password = EncryptedCharField(max_length=32)
    email = models.EmailField()
    bet_page = models.ForeignKey(BetPage, on_delete=models.CASCADE)
    num_allow_tables = models.IntegerField(default=1)
    start_bet = models.IntegerField()

    def __str__(self):
        return f"{self.username}"

    def send_finished_table(self, table, bet_row, resultado):
        context = {
            "table": table,
            "bet_row": bet_row,
            # TODO: arreglar esto con el routing del frontend
            "link": f"{settings.INSTANCE_DOMAIN}",
        }
        msg = mark_safe(render_to_string("mails/finished_table.html", context))
        send_mail(
            subject=f"Tabla {self.RESULTADOS[resultado]}",
            message=strip_tags(msg),
            html_message=msg,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[self.email],
        )

    class Meta:
        verbose_name = "Account"
        verbose_name_plural = "Accounts"
