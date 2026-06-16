from collections import Counter

from django.core.management.base import BaseCommand

from core.models import Mission
from core.services.mission_quality import build_quality_context, classify_mission_quality


class Command(BaseCommand):
    help = "Apply Mission quality levels without deleting mission data"

    def handle(self, *args, **options):
        missions = list(Mission.objects.all().order_by("id"))
        context = build_quality_context(missions)

        quality_counts = Counter()
        usable_count = 0
        excluded_count = 0

        for mission in missions:
            quality_level, is_usable_for_set, reasons = classify_mission_quality(
                mission=mission,
                context=context,
            )

            mission.quality_level = quality_level
            mission.is_usable_for_set = is_usable_for_set
            mission.is_quality_checked = True
            mission.quality_note = " / ".join(reasons)
            mission.save(update_fields=[
                "quality_level",
                "is_usable_for_set",
                "is_quality_checked",
                "quality_note",
            ])

            quality_counts[quality_level] += 1
            if is_usable_for_set:
                usable_count += 1
            else:
                excluded_count += 1

        self.stdout.write(f"basic={quality_counts['basic']}")
        self.stdout.write(f"standard={quality_counts['standard']}")
        self.stdout.write(f"practical={quality_counts['practical']}")
        self.stdout.write(f"excluded_from_sets={excluded_count}")
        self.stdout.write(f"usable_for_sets={usable_count}")
        self.stdout.write(self.style.SUCCESS("Mission quality applied."))
