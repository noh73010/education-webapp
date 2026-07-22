from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0032_missionimage")]

    operations = [
        migrations.AddField(
            model_name="problemsetsessionitem",
            name="attempt",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="problem_set_session_items", to="core.attempt"),
        ),
        migrations.AddField(model_name="problemsetsessionitem", name="review_attempt_count", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="problemsetsessionitem", name="review_is_correct", field=models.BooleanField(blank=True, null=True)),
        migrations.AddField(model_name="problemsetsessionitem", name="reviewed_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="problemsetsessionitem", name="submitted_answer", field=models.TextField(blank=True, default="")),
    ]
