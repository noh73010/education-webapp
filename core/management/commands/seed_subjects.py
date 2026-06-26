from django.core.management.base import BaseCommand

from core.services.subjects import seed_platform_subjects


class Command(BaseCommand):
    help = "Seed platform subjects such as 컴활 2급 and 물류관리사."

    def handle(self, *args, **options):
        subjects = seed_platform_subjects()

        for subject in subjects:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Subject ready: {subject.code} / {subject.name}"
                )
            )
