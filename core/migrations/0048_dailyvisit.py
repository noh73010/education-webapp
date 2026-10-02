from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0047_realtor_study_path"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DailyVisit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("day", models.DateField(db_index=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-day"]},
        ),
        migrations.AddConstraint(
            model_name="dailyvisit",
            constraint=models.UniqueConstraint(fields=("user", "day"), name="unique_daily_user_visit"),
        ),
        migrations.CreateModel(
            name="DailyVisitTotal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("day", models.DateField(unique=True)),
                ("count", models.PositiveIntegerField(default=0)),
            ],
            options={"ordering": ["-day"]},
        ),
    ]
