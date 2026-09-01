from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("football", "0005_pipeline_run_and_prospective_identities"),
    ]

    operations = [
        # The superseded write-capable schema is intentionally not recreated on
        # rollback; omitting reverse_sql makes that limitation fail explicitly.
        migrations.RunSQL(
            sql="""
                DROP TABLE IF EXISTS bet_betrow;
                DROP TABLE IF EXISTS bet_bettable;
            """,
        ),
    ]
