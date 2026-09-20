from django.core.management.base import BaseCommand

from core.services.subjects import seed_platform_subjects


class Command(BaseCommand):
    help = "Seed active platform subjects while keeping Subject-based expansion."

    def handle(self, *args, **options):
        subjects = seed_platform_subjects()

        for subject in subjects:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Subject ready: {subject.code} / {subject.name}"
                )
            )
