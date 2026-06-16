from django.core.management.base import BaseCommand

from core.models import Mission
from core.services.mission_quality import build_quality_context, get_quality_reasons


class Command(BaseCommand):
    help = "Audit Mission quality and print suspicious missions without changing data"

    def handle(self, *args, **options):
        missions = list(Mission.objects.all().order_by("id"))
        context = build_quality_context(missions)
        suspicious_count = 0

        for mission in missions:
            reasons = get_quality_reasons(mission, context)

            if not reasons:
                continue

            suspicious_count += 1
            self.stdout.write(
                "\t".join([
                    f"id={mission.id}",
                    f"title={mission.title}",
                    f"skill={mission.skill}",
                    f"learning_type={mission.learning_type}",
                    f"question_type={mission.question_type}",
                    "reasons=" + " / ".join(reasons),
                ])
            )

        self.stdout.write(
            self.style.SUCCESS(f"Audit complete. suspicious={suspicious_count}")
        )
