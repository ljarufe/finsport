import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "finsport.settings")
django.setup()


LOG_ENABLED = False

BOT_NAME = "bet_scraper"

SPIDER_MODULES = ["bet_scraper.spiders"]
NEWSPIDER_MODULE = "bet_scraper.spiders"

# Obey robots.txt rules
ROBOTSTXT_OBEY = True
