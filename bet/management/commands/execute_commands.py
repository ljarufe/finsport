from django.core.management.base import BaseCommand

from bet.tasks import run_betting_cycle


class Command(BaseCommand):
    help = "Queue sequential betting commands through Celery"

    def handle(self, *args, **options):
        task = run_betting_cycle.delay()
        self.stdout.write(self.style.SUCCESS(f"Betting cycle queued: {task.id}"))
