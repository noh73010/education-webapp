from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0050_subject_exam_dates")]

    operations = [
        migrations.AddField(
            model_name="inquiry",
            name="staff_reply",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="inquiry",
            name="replied_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
