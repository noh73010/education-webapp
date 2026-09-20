from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0042_exam_modes"),
    ]

    operations = [
        migrations.AddField(
            model_name="mission",
            name="review_status",
            field=models.CharField(
                choices=[
                    ("unreviewed", "검수 전"),
                    ("verified", "검수 완료"),
                    ("confirmed_error", "오류 확인 · 출제 중지"),
                ],
                db_index=True,
                default="unreviewed",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="examsessionmission",
            name="is_marked_for_review",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="problemset",
            name="generation_key",
            field=models.CharField(blank=True, db_index=True, default="", max_length=200),
        ),
        migrations.AddConstraint(
            model_name="problemset",
            constraint=models.UniqueConstraint(
                condition=models.Q(("generation_key", ""), _negated=True),
                fields=("generation_key",),
                name="unique_generated_problem_set_key",
            ),
        ),
    ]
