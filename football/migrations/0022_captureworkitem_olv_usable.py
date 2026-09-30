from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("football", "0021_capitalresultobservation_provider_result_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="captureworkitem",
            name="olv_usable",
            field=models.BooleanField(blank=True, null=True),
        ),
    ]
