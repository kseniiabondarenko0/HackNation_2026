from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analysis", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="analysis",
            name="verdict",
            field=models.CharField(blank=True, db_index=True, max_length=12),
        ),
    ]
