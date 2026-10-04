from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0048_dailyvisit")]

    operations = [
        migrations.AddField(
            model_name="coursefocus",
            name="area_code",
            field=models.CharField(blank=True, max_length=8),
        ),
    ]
