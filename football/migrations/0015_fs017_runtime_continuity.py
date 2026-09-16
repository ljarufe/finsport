import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("football", "0014_capitalexecutionbasis_capitalresultobservation_and_more")
    ]

    operations = [
        migrations.AddField(
            model_name="capitalposition",
            name="next_result_check_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="capitalexecutionstate",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending execution event"),
                    ("PENDING_CAPACITY", "Pending capacity"),
                    ("PLACED", "Placed"),
                    ("NOT_PLACED", "Terminal without position"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="maintenancerun",
            name="capability",
            field=models.CharField(
                choices=[
                    ("CATALOGUE", "Catalogue"),
                    ("SEASON_BOOTSTRAP", "Season bootstrap"),
                    ("HISTORICAL_BOOTSTRAP", "Historical bootstrap"),
                    ("HISTORICAL_MARKET_BOOTSTRAP", "Historical market bootstrap"),
                    ("WEEKLY_EVALUATION", "Weekly evaluation"),
                    ("CURRENT_SEASON_RECONCILIATION", "Current-season reconciliation"),
                ],
                max_length=30,
            ),
        ),
        migrations.CreateModel(
            name="ProviderCallAudit",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("provider", models.CharField(default="API_FOOTBALL", max_length=40)),
                (
                    "capability",
                    models.CharField(
                        choices=[
                            ("DAILY_FIXTURE_DISCOVERY", "Daily fixture discovery"),
                            ("ODDS_T30", "Odds T-30"),
                            ("ODDS_T60", "Odds T-60"),
                            ("ODDS_T6H", "Odds T-6h"),
                            ("OPEN_RESULT_BATCH", "Open result batch"),
                            ("NONBET_RESULT_BATCH", "Non-bet result batch"),
                            (
                                "CATALOGUE_OR_SEASON_MAINTENANCE",
                                "Catalogue or season maintenance",
                            ),
                            (
                                "OTHER_EXPLICIT_MAINTENANCE",
                                "Other explicit maintenance",
                            ),
                            ("FUTURE_EXECUTION_QUOTE", "Future execution quote"),
                        ],
                        max_length=50,
                    ),
                ),
                ("logical_identity", models.CharField(max_length=500)),
                ("endpoint_family", models.CharField(max_length=80)),
                ("request_metadata", models.JSONField(blank=True, default=dict)),
                ("fixture_count", models.PositiveIntegerField(default=0)),
                ("attempt_number", models.PositiveIntegerField(default=1)),
                ("page_number", models.PositiveIntegerField(default=1)),
                ("retry_number", models.PositiveIntegerField(default=0)),
                ("retry_reason", models.CharField(blank=True, max_length=120)),
                ("started_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("outcome", models.CharField(default="STARTED", max_length=50)),
                (
                    "http_status",
                    models.PositiveSmallIntegerField(blank=True, null=True),
                ),
                ("quota_limit", models.PositiveIntegerField(blank=True, null=True)),
                ("quota_remaining", models.PositiveIntegerField(blank=True, null=True)),
                ("minute_limit", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "minute_remaining",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("quota_observed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "capture_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="provider_call_audits",
                        to="football.capturerun",
                    ),
                ),
                (
                    "capture_work_item",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="provider_call_audits",
                        to="football.captureworkitem",
                    ),
                ),
                (
                    "maintenance_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="provider_call_audits",
                        to="football.maintenancerun",
                    ),
                ),
            ],
            options={"ordering": ("started_at", "id")},
        ),
        migrations.AddIndex(
            model_name="providercallaudit",
            index=models.Index(
                fields=["provider", "-started_at"], name="football_provider_latest_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="providercallaudit",
            index=models.Index(
                fields=["capability", "started_at"], name="football_provider_cap_idx"
            ),
        ),
    ]
