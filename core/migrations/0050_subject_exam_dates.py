from datetime import date

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def preserve_legacy_goals_and_seed_schedule(apps, schema_editor):
    Subject = apps.get_model("core", "Subject")
    StudyProfile = apps.get_model("core", "StudyProfile")
    SubjectExamGoal = apps.get_model("core", "SubjectExamGoal")
    OfficialExamDate = apps.get_model("core", "OfficialExamDate")
    logistics = Subject.objects.filter(code="logistics").first()
    if logistics:
        for profile in StudyProfile.objects.exclude(target_exam_date__isnull=True).iterator():
            SubjectExamGoal.objects.get_or_create(
                user_id=profile.user_id, subject_id=logistics.pk,
                defaults={"target_date": profile.target_exam_date},
            )
    realtor = Subject.objects.filter(code="realtor").first()
    if realtor:
        OfficialExamDate.objects.get_or_create(
            subject_id=realtor.pk,
            label="2026년 제37회 공인중개사 1·2차",
            exam_date=date(2026, 10, 31),
            defaults={
                "source_url": "https://www.q-net.or.kr/site/junggae",
                "verified_on": date(2026, 10, 10),
            },
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0049_coursefocus_area_code"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="SubjectExamGoal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_date", models.DateField()),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="core.subject")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("user", "subject"), name="unique_subject_exam_goal")]},
        ),
        migrations.CreateModel(
            name="OfficialExamDate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=120)),
                ("exam_date", models.DateField()),
                ("source_url", models.URLField()),
                ("verified_on", models.DateField()),
                ("is_active", models.BooleanField(default=True)),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="core.subject")),
            ],
            options={
                "ordering": ["exam_date", "label"],
                "constraints": [models.UniqueConstraint(fields=("subject", "label", "exam_date"), name="unique_official_exam_date")],
            },
        ),
        migrations.RunPython(preserve_legacy_goals_and_seed_schedule, migrations.RunPython.noop),
    ]
