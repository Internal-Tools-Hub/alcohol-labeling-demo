from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_alter_submission_location_nullable"),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="ocr_extract",
            field=models.JSONField(blank=True, null=True),
        ),
    ]


