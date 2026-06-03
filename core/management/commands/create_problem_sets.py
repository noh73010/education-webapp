from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Mission, ProblemSet, ProblemSetItem


SET_DEFINITIONS = [
    {
        "title": "COUNTA 기본 훈련 세트",
        "skill_group": "COUNTA",
        "level": 1,
        "set_type": "training",
        "description": "빈 셀 제외, 비어있지 않은 셀 개수 계산을 훈련하는 세트입니다.",
        "mission_external_ids": [
            "SCN_COUNTA_002",  # 함수 선택
            "SCN_COUNTA_001",  # 실제 개수 계산
            "SCN_COUNTA_003",  # 오류 찾기
        ],
    },
    {
        "title": "IF 기본 훈련 세트",
        "skill_group": "IF",
        "level": 1,
        "set_type": "training",
        "description": "조건 판단, 합격/불합격 판정, IF 수식 구조를 훈련하는 세트입니다.",
        "mission_external_ids": [
            "SCN_IF_002",  # 수식 선택
            "SCN_IF_001",  # 결과 판단
            "SCN_IF_003",  # 오류 찾기
        ],
    },
    {
        "title": "SUMIF 기본 훈련 세트",
        "skill_group": "SUMIF",
        "level": 2,
        "set_type": "training",
        "description": "조건에 맞는 항목만 합산하는 SUMIF 기본 훈련 세트입니다.",
        "mission_external_ids": [
            "SCN_SUMIF_002",  # 수식 선택
            "SCN_SUMIF_001",  # 결과 계산
        ],
    },
    {
        "title": "VLOOKUP 기본 훈련 세트",
        "skill_group": "VLOOKUP",
        "level": 2,
        "set_type": "training",
        "description": "상품코드 조회, 열 번호 선택, VLOOKUP 오류 판단을 훈련하는 세트입니다.",
        "mission_external_ids": [
            "SCN_VLOOKUP_002",  # 열 번호 판단
            "SCN_VLOOKUP_001",  # 값 찾기
            "SCN_VLOOKUP_003",  # 오류 찾기
        ],
    },
    {
        "title": "기초 함수 종합 훈련 세트",
        "skill_group": "mixed",
        "level": 2,
        "set_type": "exam_like",
        "description": "COUNTA, IF, SUMIF, VLOOKUP을 섞어 실전 감각을 훈련하는 종합 세트입니다.",
        "mission_external_ids": [
            "SCN_COUNTA_002",
            "SCN_COUNTA_001",
            "SCN_IF_002",
            "SCN_IF_001",
            "SCN_SUMIF_002",
            "SCN_SUMIF_001",
            "SCN_VLOOKUP_002",
            "SCN_VLOOKUP_001",
            "SCN_VLOOKUP_003",
        ],
    },
]


class Command(BaseCommand):
    help = "Create structured problem sets from scenario missions"

    @transaction.atomic
    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0
        skipped_count = 0

        for definition in SET_DEFINITIONS:
            result = self.create_or_update_set(definition)

            if result == "created":
                created_count += 1
            elif result == "updated":
                updated_count += 1
            else:
                skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"문제 세트 처리 완료: 생성 {created_count}개 / 수정 {updated_count}개 / 스킵 {skipped_count}개"
            )
        )

    def create_or_update_set(self, definition):
        title = definition["title"]
        external_ids = definition["mission_external_ids"]

        missions = list(
            Mission.objects
            .filter(
                external_id__in=external_ids,
                is_usable_for_set=True,
            )
        )

        mission_map = {
            mission.external_id: mission
            for mission in missions
        }

        ordered_missions = []
        missing_ids = []

        for external_id in external_ids:
            mission = mission_map.get(external_id)

            if mission:
                ordered_missions.append(mission)
            else:
                missing_ids.append(external_id)

        if missing_ids:
            self.stdout.write(
                self.style.WARNING(
                    f"스킵: {title} / 누락된 문제: {', '.join(missing_ids)}"
                )
            )
            return "skipped"

        problem_set, created = ProblemSet.objects.update_or_create(
            title=title,
            defaults={
                "skill_group": definition["skill_group"],
                "level": definition["level"],
                "set_type": definition["set_type"],
                "description": definition["description"],
                "is_active": True,
            },
        )

        ProblemSetItem.objects.filter(problem_set=problem_set).delete()

        items = []
        for index, mission in enumerate(ordered_missions, start=1):
            role = self.get_role_by_order(index=index, total=len(ordered_missions))

            items.append(
                ProblemSetItem(
                    problem_set=problem_set,
                    mission=mission,
                    order_no=index,
                    role=role,
                )
            )

        ProblemSetItem.objects.bulk_create(items)

        if created:
            self.stdout.write(self.style.SUCCESS(f"생성: {title}"))
            return "created"

        self.stdout.write(self.style.SUCCESS(f"수정: {title}"))
        return "updated"

    def get_role_by_order(self, *, index, total):
        if index == 1:
            return "core"

        if index == total:
            return "challenge"

        return "review"