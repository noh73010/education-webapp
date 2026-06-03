from django.core.management.base import BaseCommand

from core.models import Mission


ALWAYS_BLOCK_PREFIXES = [
    "CNT_",
    "IF_CH_",
    "IF_ERR_",
    "IF_VAL_",
]

ALWAYS_ALLOW_PREFIXES = [
    "SCN_",
]

LOW_QUALITY_KEYWORDS = [
    "결과 입력",
    "결과값 입력",
    "결과 일수 입력",
    "값이 ",
    "전체 건수를 구하시오",
    "전체 개수를 계산",
]


class Command(BaseCommand):
    help = "Mark low-quality missions as not usable for problem sets"

    def handle(self, *args, **options):
        checked_count = 0
        allowed_count = 0
        blocked_count = 0

        for mission in Mission.objects.all().order_by("id"):
            checked_count += 1

            external_id = mission.external_id or ""
            prompt = mission.prompt or ""
            explanation = mission.explanation or ""

            reasons = []

            # 1) 새 시나리오 문제는 우선 통과
            if self.starts_with_any(external_id, ALWAYS_ALLOW_PREFIXES):
                mission.is_usable_for_set = True
                mission.is_quality_checked = True
                mission.quality_note = "시나리오 기반 문제: 사용 가능"
                mission.save(update_fields=[
                    "is_usable_for_set",
                    "is_quality_checked",
                    "quality_note",
                ])
                allowed_count += 1
                continue

            # 2) 기존 자동 생성 문제는 차단
            if self.starts_with_any(external_id, ALWAYS_BLOCK_PREFIXES):
                reasons.append(f"기존 자동생성 저품질 문제: {external_id}")

            # 3) 짧은 value_answer 차단
            if mission.question_type == "value_answer" and not mission.answer_schema:
                if len(prompt.strip()) < 120:
                    reasons.append("짧은 value_answer 문제")

            # 4) 저품질 문구 차단
            for keyword in LOW_QUALITY_KEYWORDS:
                if keyword in prompt or keyword in explanation:
                    reasons.append(f"저품질 키워드 포함: {keyword}")

            # 5) 선택형인데 선택지가 없으면 차단
            if mission.question_type in ("choice_one", "true_false", "error_detect"):
                if not mission.answer_schema.strip():
                    reasons.append("선택형 문제인데 answer_schema 없음")

            # 6) 자동채점형인데 정답이 없으면 차단
            if mission.question_type != "manual":
                if not mission.correct_answer.strip() and not mission.answer_schema.strip():
                    reasons.append("자동채점형 문제인데 correct_answer/answer_schema 없음")

            if reasons:
                mission.is_usable_for_set = False
                mission.is_quality_checked = True
                mission.quality_note = " / ".join(reasons)
                blocked_count += 1
            else:
                mission.is_usable_for_set = True
                mission.is_quality_checked = True
                mission.quality_note = "기본 품질 검사 통과"
                allowed_count += 1

            mission.save(update_fields=[
                "is_usable_for_set",
                "is_quality_checked",
                "quality_note",
            ])

        self.stdout.write(
            self.style.SUCCESS(
                f"품질 검사 완료: 검사 {checked_count}개 / 사용 가능 {allowed_count}개 / 제외 {blocked_count}개"
            )
        )

    def starts_with_any(self, text, prefixes):
        return any(text.startswith(prefix) for prefix in prefixes)