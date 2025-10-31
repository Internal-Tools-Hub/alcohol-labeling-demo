from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_comment"),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="intentional_fail",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="submission",
            name="intentional_failure_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="submission",
            name="regulatory_citation",
            field=models.CharField(max_length=255, blank=True),
        ),
    ]


