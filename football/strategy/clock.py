"""Wall-clock admission time, distinct from the pipeline planning timestamp."""

from django.utils import timezone


def effective_now(*, planning_at=None):
    # planning_at is only a test seam; it must never determine production time.
    return timezone.now()
