from django.db import migrations


def retire_comhwal2_subject(apps, schema_editor):
    Subject = apps.get_model("core", "Subject")
    Subject.objects.filter(code="comhwal2").update(is_active=False)
    Subject.objects.update_or_create(
        code="logistics",
        defaults={
            "name": "물류관리사",
            "description": "물류관리사 자격시험 대비 학습",
            "is_active": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0038_mobile_personal_coach")]
    operations = [
        migrations.RunPython(retire_comhwal2_subject, migrations.RunPython.noop),
    ]
