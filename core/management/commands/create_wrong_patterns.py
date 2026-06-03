from django.core.management.base import BaseCommand

from core.models import WrongPattern


PATTERNS = [
    {
        "code": "COUNT_CONFUSION",
        "name": "COUNT/COUNTA 혼동",
        "skill": "COUNT",
        "description": "문자 개수를 COUNT로 세려고 하는 실수",
    },
    {
        "code": "VLOOKUP_COL_INDEX",
        "name": "VLOOKUP 열번호 오류",
        "skill": "VLOOKUP",
        "description": "반환 열 번호를 잘못 지정하는 실수",
    },
    {
        "code": "VLOOKUP_FIRST_COL",
        "name": "VLOOKUP 첫 열 조건 오류",
        "skill": "VLOOKUP",
        "description": "찾을 값이 첫 번째 열에 있어야 하는 규칙을 놓침",
    },
    {
        "code": "IF_DIRECTION",
        "name": "IF 조건 방향 오류",
        "skill": "IF",
        "description": ">= 와 < 방향을 반대로 작성",
    },
    {
        "code": "IF_MISSING_FALSE",
        "name": "IF 거짓값 누락",
        "skill": "IF",
        "description": "IF 함수에서 false 값을 빼먹음",
    },
]

class Command(BaseCommand):
    help = "Create default wrong patterns"

    def handle(self, *args, **options):
        created_count = 0

        for row in PATTERNS:
            _, created = WrongPattern.objects.get_or_create(
                code=row["code"],
                defaults={
                    "name": row["name"],
                    "skill": row["skill"],
                    "description": row["description"],
                }
            )

            if created:
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"오답 패턴 생성 완료: {created_count}개"
            )
        )