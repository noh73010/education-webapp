from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0045_mission_content_versioning"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CourseFocus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("course", models.CharField(max_length=100)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="core.subject")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("user", "subject"), name="unique_course_focus")]},
        ),
    ]
