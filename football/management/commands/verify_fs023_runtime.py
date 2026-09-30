"""Read-only effective-setting preflight before local FS-023 scheduling."""

import json
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from football.capture.contracts import CaptureConfig


def verify_effective_settings(*, require_automatic=False):
    try:
        config = CaptureConfig.from_settings()
    except (TypeError, KeyError, ValueError) as error:
        raise ValueError(f"FS023_T10_EFFECTIVE_CONFIG_INVALID:{error}") from error
    if settings.FOOTBALL_CAPTURE_WAKE_SECONDS != 180:
        raise ValueError("FS023_WAKE_MUST_BE_180_SECONDS")
    for name in (
        "FOOTBALL_MODERNIZED_R45_ENABLED",
        "FOOTBALL_MODERNIZED_R45_CAPITAL_ENABLED",
        "INKABET_AUTOMATIC_ENABLED",
    ):
        if getattr(settings, name):
            raise ValueError(f"FS023_UNSAFE_AUTOMATIC_FLAG:{name}")
    schedule = settings.CELERY_BEAT_SCHEDULE
    if settings.FOOTBALL_PIPELINE_ENABLED:
        if set(schedule) != {"football-pipeline-wake"} or schedule[
            "football-pipeline-wake"
        ] != {"task": "football.pipeline.wake", "schedule": 180}:
            raise ValueError("FS023_SINGLE_BEAT_OWNER_REQUIRED")
    elif schedule:
        raise ValueError("FS023_BEAT_WITHOUT_PIPELINE")
    if require_automatic and not settings.FOOTBALL_PIPELINE_ENABLED:
        raise ValueError("FS023_PIPELINE_AUTOMATION_NOT_ENABLED")
    url = urlsplit(settings.BSD_API_BASE_URL)
    if url.scheme not in {"https", "http"} or not url.netloc:
        raise ValueError("FS023_BSD_BASE_URL_INVALID")
    return {
        "status": "PASS",
        "windows": [window.snapshot() for window in config.windows],
        "wake_seconds": settings.FOOTBALL_CAPTURE_WAKE_SECONDS,
        "beat_owner": "football.pipeline.wake" if schedule else "DISABLED",
        "bsd_effective_state": (
            "CONFIGURED_PENDING_PROVIDER_VALIDATION"
            if settings.BSD_API_TOKEN
            else "BSD_NOT_CONFIGURED"
        ),
        "r45_automatic": False,
        "inkabet_automatic": False,
        "real_betting": False,
    }


class Command(BaseCommand):
    help = "Validate effective FS-023 settings without printing secrets or reading providers."

    def add_arguments(self, parser):
        parser.add_argument("--require-automatic", action="store_true")

    def handle(self, *args, **options):
        try:
            report = verify_effective_settings(
                require_automatic=options["require_automatic"]
            )
        except ValueError as error:
            raise CommandError(str(error)) from None
        self.stdout.write(json.dumps(report, sort_keys=True))
