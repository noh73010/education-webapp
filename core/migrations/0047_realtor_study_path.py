from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def register_realtor(apps, schema_editor):
    Subject = apps.get_model("core", "Subject")
    Subject.objects.update_or_create(
        code="realtor",
        defaults={
            "name": "공인중개사",
            "description": "1차·2차 학습을 나누어 준비하는 공인중개사 학습",
            "is_active": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0046_coursefocus"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="RealtorStudyPath",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("path", models.CharField(choices=[("first", "1차 준비"), ("second", "2차 준비"), ("both", "동차 준비")], max_length=10)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="realtor_study_path", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(register_realtor, migrations.RunPython.noop),
    ]
