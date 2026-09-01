from django.db import migrations, models
import django.utils.timezone
import django_extensions.db.fields


class Migration(migrations.Migration):
    dependencies = [("football", "0006_remove_legacy_bet_tables")]

    operations = [
        migrations.CreateModel(
            name="MaintenanceRun",
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
                (
                    "created",
                    django_extensions.db.fields.CreationDateTimeField(
                        auto_now_add=True, verbose_name="created"
                    ),
                ),
                (
                    "modified",
                    django_extensions.db.fields.ModificationDateTimeField(
                        auto_now=True, verbose_name="modified"
                    ),
                ),
                (
                    "capability",
                    models.CharField(
                        choices=[
                            ("CATALOGUE", "Catalogue"),
                            ("SEASON_BOOTSTRAP", "Season bootstrap"),
                            ("WEEKLY_EVALUATION", "Weekly evaluation"),
                        ],
                        max_length=30,
                    ),
                ),
                ("logical_identity", models.CharField(max_length=200, unique=True)),
                ("period_start", models.DateField()),
                ("subject_type", models.CharField(blank=True, max_length=40)),
                ("subject_id", models.PositiveBigIntegerField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("RUNNING", "Running"),
                            ("SUCCESS", "Success"),
                            ("NO_WORK", "No work"),
                            ("SKIPPED_QUOTA", "Skipped due to quota"),
                            ("DEGRADED", "Degraded"),
                            ("FAILED", "Failed"),
                        ],
                        default="RUNNING",
                        max_length=24,
                    ),
                ),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("started_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "last_attempt_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("next_eligible_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("provider_attempts", models.PositiveIntegerField(default=0)),
                ("quota_limit", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "quota_remaining_after",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("quota_observed_at", models.DateTimeField(blank=True, null=True)),
                ("config_snapshot", models.JSONField(blank=True, default=dict)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("error_class", models.CharField(blank=True, max_length=120)),
                ("error_message", models.CharField(blank=True, max_length=500)),
            ],
            options={"ordering": ("-started_at", "-id")},
        ),
        migrations.AddIndex(
            model_name="maintenancerun",
            index=models.Index(
                fields=["capability", "status", "period_start"],
                name="football_maintenance_due_idx",
            ),
        ),
    ]
