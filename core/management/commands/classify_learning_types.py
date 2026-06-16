from django.core.management.base import BaseCommand

from core.models import Mission


ERROR_KEYWORDS = [
    "오류",
    "에러",
    "문제점",
    "잘못",
    "틀린",
    "수정",
    "고쳐",
    "진단",
]

FEATURE_KEYWORDS = [
    "함수 선택",
    "수식 선택",
    "적절한 함수",
    "올바른 수식",
    "무엇인가요",
    "선택",
    "구조",
    "기능",
    "사용해야",
]

RESULT_KEYWORDS = [
    "결과",
    "계산",
    "구하세요",
    "입력하세요",
    "조회",
    "반환",
    "판정",
    "단가",
    "개수",
    "합계",
    "몇",
    "얼마",
]


class Command(BaseCommand):
    help = "Automatically classify Mission.learning_type"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="실제 저장하지 않고 분류 결과만 출력합니다.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        total_count = 0
        updated_count = 0

        counts = {
            "feature": 0,
            "result": 0,
            "error": 0,
        }

        missions = Mission.objects.all().order_by("id")

        for mission in missions:
            total_count += 1

            old_type = mission.learning_type
            new_type = self.classify(mission)

            counts[new_type] = counts.get(new_type, 0) + 1

            if old_type != new_type:
                updated_count += 1

                if not dry_run:
                    mission.learning_type = new_type
                    mission.save(update_fields=["learning_type"])

            self.stdout.write(
                f"[{mission.id}] {mission.title} / {mission.skill} "
                f"/ {old_type} -> {new_type}"
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN 모드입니다. DB에는 저장하지 않았습니다.")
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"learning_type 자동 분류 완료: 전체 {total_count}개 / 변경 {updated_count}개"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"feature: {counts['feature']}개 / "
                f"result: {counts['result']}개 / "
                f"error: {counts['error']}개"
            )
        )

    def classify(self, mission):
        title = mission.title or ""
        prompt = mission.prompt or ""
        question_type = mission.question_type or ""

        text = f"{title}\n{prompt}"

        if (
            question_type == "error_detect"
            or "오류" in text
            or "에러" in text
            or "잘못" in text
            or "수정" in text
        ):
            return "error"

        if self.contains_any(text, ERROR_KEYWORDS):
            return "error"

        if question_type in ("choice_one", "true_false"):
            if (
                "선택" in text
                or "함수 선택" in text
                or "수식 선택" in text
                or "올바른 함수" in text
            ):
                return "feature"

        if self.contains_any(text, FEATURE_KEYWORDS):
            return "feature"

        if self.contains_any(text, RESULT_KEYWORDS):
            return "result"

        if question_type in ("value_answer", "short_answer"):
            return "result"

        return "result"

    def contains_any(self, text, keywords):
        return any(keyword in text for keyword in keywords)