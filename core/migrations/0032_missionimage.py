from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0031_mission_chapter_code_mission_chapter_name_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="MissionImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("static_path", models.CharField(max_length=500)),
                ("alt_text", models.CharField(blank=True, default="", max_length=300)),
                ("source", models.CharField(blank=True, default="", max_length=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("mission", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="question_image", to="core.mission")),
            ],
            options={"ordering": ["mission_id"]},
        ),
    ]
