from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("football", "0008_capitallongitudinalseries_and_source_owner")]

    operations = [
        migrations.AddField(
            model_name="capitalexperiment",
            name="semantic_identity",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
    ]
