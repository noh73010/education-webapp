from django.db import migrations


VALID_CODES = {
    *(f"LOGISTICS_LM{number:02d}" for number in range(1, 9)),
    *(f"LOGISTICS_FT{number:02d}" for number in range(1, 9)),
    *(f"LOGISTICS_IT{number:02d}" for number in range(1, 5)),
    *(f"LOGISTICS_BH{number:02d}" for number in range(1, 9)),
    *(f"LOGISTICS_LR{number:02d}" for number in range(1, 8)),
}


def archive_stale_patterns(apps, schema_editor):
    Subject = apps.get_model("core", "Subject")
    WrongPattern = apps.get_model("core", "WrongPattern")
    logistics = Subject.objects.filter(code="logistics").first()
    if not logistics:
        return
    for pattern in WrongPattern.objects.filter(subject=logistics, code__startswith="LOGISTICS_"):
        if pattern.code not in VALID_CODES:
            pattern.code = f"LEGACY_{pattern.code}"
            pattern.save(update_fields=["code"])


class Migration(migrations.Migration):
    dependencies = [("core", "0036_correct_logistics_curriculum")]
    operations = [migrations.RunPython(archive_stale_patterns, migrations.RunPython.noop)]
