import json

from django.core.management.base import BaseCommand, CommandError

from core.services.content_regrading import ContentRegradeError, regrade_mission_records


class Command(BaseCommand):
    help = "정답 변경 문항의 기존 학습 기록을 안전하게 재평가합니다. 기본 동작은 dry-run입니다."

    def add_arguments(self, parser):
        parser.add_argument("--external-id", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirm-fingerprint", default="")

    def handle(self, *args, **options):
        try:
            report = regrade_mission_records(
                external_id=options["external_id"],
                apply=options["apply"],
                confirm_fingerprint=options["confirm_fingerprint"],
            )
        except ContentRegradeError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        if not options["apply"]:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN: 변경하지 않았습니다. 적용하려면 --apply와 위 fingerprint를 함께 지정하세요."
            ))
