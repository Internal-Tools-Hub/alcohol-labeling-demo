from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_alter_submission_brand_name"),
    ]

    operations = [
        migrations.AlterField(
            model_name="submission",
            name="location",
            field=models.ForeignKey(
                to="core.location",
                on_delete=models.deletion.PROTECT,
                null=True,
                blank=True,
            ),
        ),
    ]


