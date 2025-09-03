from django.core.management.base import BaseCommand

from common.scrapy_runner import run_scrapy_spider


class Command(BaseCommand):
    help = "Update or create matches"

    def handle(self, *args, **options):
        message = run_scrapy_spider("leagues")
        self.stdout.write(message)
