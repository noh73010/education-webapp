from django.core.management.base import BaseCommand
from django.db.models import Count, Min
from core.models import Mission

class Command(BaseCommand):
    help = "Remove duplicate Mission rows by (title, skill). Keeps the smallest id."

    def handle(self, *args, **options):
        dup_groups = (
            Mission.objects
            .values("title", "skill")
            .annotate(cnt=Count("id"), keep_id=Min("id"))
            .filter(cnt__gt=1)
        )

        total_deleted = 0
        for g in dup_groups:
            title = g["title"]
            skill = g["skill"]
            keep_id = g["keep_id"]

            qs = Mission.objects.filter(title=title, skill=skill).exclude(id=keep_id)
            deleted, _ = qs.delete()
            total_deleted += deleted

        self.stdout.write(self.style.SUCCESS(f"중복 삭제 완료: {total_deleted}개"))