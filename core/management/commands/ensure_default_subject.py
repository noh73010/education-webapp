from django.core.management.base import BaseCommand

from core.services.subjects import ensure_default_subject_assignments


class Command(BaseCommand):
    help = "Ensure the default 컴활 2급 subject exists and owns legacy missions."

    def handle(self, *args, **options):
        subject, updated_count = ensure_default_subject_assignments()
        self.stdout.write(
            self.style.SUCCESS(
                f"Default subject ready: {subject.code} / {subject.name}"
            )
        )
        self.stdout.write(f"Missions assigned to default subject: {updated_count}")
