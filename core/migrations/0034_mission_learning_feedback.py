from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0033_problemsetsessionitem_learning_result"),
    ]

    operations = [
        migrations.AddField(
            model_name="mission",
            name="choice_explanations",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="mission",
            name="concept_summary",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="mission",
            name="exam_tip",
            field=models.TextField(blank=True, default=""),
        ),
    ]
