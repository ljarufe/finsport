import django.db.models.deletion
import django_extensions.db.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("football", "0007_maintenancerun")]

    operations = [
        migrations.CreateModel(
            name="CapitalLongitudinalSeries",
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
                ("code", models.SlugField(max_length=80, unique=True)),
                ("evidence_class", models.CharField(max_length=20)),
                ("source_model_code", models.CharField(max_length=30)),
                ("decision_policy_code", models.CharField(max_length=30)),
                ("frozen_competition_ids", models.JSONField(default=list)),
                ("cohort_hash", models.CharField(max_length=64)),
                ("epoch", models.DateTimeField()),
                ("mode", models.CharField(max_length=12)),
                (
                    "initial_bankroll",
                    models.DecimalField(decimal_places=8, max_digits=24),
                ),
                ("config", models.JSONField(default=dict)),
            ],
            options={"ordering": ("code",)},
        ),
        migrations.AlterField(
            model_name="capitalexperiment",
            name="source_experiment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="capital_experiments",
                to="football.predictionexperiment",
            ),
        ),
        migrations.AddField(
            model_name="capitalexperiment",
            name="longitudinal_series",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="snapshots",
                to="football.capitallongitudinalseries",
            ),
        ),
        migrations.AddConstraint(
            model_name="capitalexperiment",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        ("longitudinal_series__isnull", True),
                        ("source_experiment__isnull", False),
                    )
                    | models.Q(
                        ("longitudinal_series__isnull", False),
                        ("source_experiment__isnull", True),
                    )
                ),
                name="football_capital_experiment_one_source_owner",
            ),
        ),
        migrations.AddField(
            model_name="capitallongitudinalseries",
            name="current_snapshot",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="current_for_longitudinal_series",
                to="football.capitalexperiment",
            ),
        ),
        migrations.AddConstraint(
            model_name="capitallongitudinalseries",
            constraint=models.CheckConstraint(
                condition=models.Q(("initial_bankroll__gt", 0)),
                name="football_capital_series_positive_bankroll",
            ),
        ),
    ]
