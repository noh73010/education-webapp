from django.db import migrations, models


def backfill_precise_scores(apps, schema_editor):
    ExamSession = apps.get_model("core", "ExamSession")
    completed = ExamSession.objects.filter(
        status__in=["submitted", "expired"],
        total_questions__gt=0,
    )
    for exam in completed.iterator():
        if exam.correct_count + exam.wrong_count != exam.total_questions:
            continue
        exam.score = round((exam.correct_count / exam.total_questions) * 100, 1)
        exam.save(update_fields=["score"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0043_content_review_status_and_exam_review_flag"),
    ]

    operations = [
        migrations.AlterField(
            model_name="examsession",
            name="score",
            field=models.FloatField(default=0),
        ),
        migrations.RunPython(backfill_precise_scores, migrations.RunPython.noop),
    ]
