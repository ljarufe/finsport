# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand

from bet.utils import make_bet_selenium


class Command(BaseCommand):
    help = 'Test make bet with Selenium'

    def handle(self, *args, **options):
        make_bet_selenium("Inglaterra - Suiza")
