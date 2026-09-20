from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.management.commands.import_missions import sync_generated_problem_sets
from core.models import Mission, Subject


class Command(BaseCommand):
    help = "표준 챕터 기준으로 자동 문제 세트를 재구성합니다. 기본 동작은 dry-run입니다."

    def add_arguments(self, parser):
        parser.add_argument("--subject-code", required=True)
        parser.add_argument("--apply", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            subject = Subject.objects.get(code=options["subject_code"])
        except Subject.DoesNotExist as exc:
            raise CommandError("등록되지 않은 자격증 코드입니다.") from exc
        missions = list(
            Mission.objects.filter(subject=subject)
            .exclude(course="")
            .exclude(chapter_code="")
            .order_by("course", "chapter_code", "external_id")
        )
        created, updated, deactivated = sync_generated_problem_sets(missions)
        if not options["apply"]:
            transaction.set_rollback(True)
        self.stdout.write(
            f"subject={subject.code}, missions={len(missions)}, created={created}, "
            f"updated={updated}, deactivated={deactivated}, apply={options['apply']}"
        )
        if not options["apply"]:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN: 변경하지 않았습니다. 검토 후 같은 명령에 --apply를 추가하세요."
            ))
