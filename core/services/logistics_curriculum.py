import re

from django.db.models import Count, OuterRef, Q, Subquery

from core.models import Attempt, Mission


LOGISTICS_CURRICULUM = [
    {
        "course": "물류관리론",
        "chapters": [
            ("LM01", "물류관리총론"),
            ("LM02", "물류경영"),
            ("LM03", "물류표준화와 물류공동화"),
            ("LM04", "물류정보화(정보시스템)"),
            ("LM05", "물류비 회계"),
            ("LM06", "공급사슬관리(SCM)"),
            ("LM07", "친환경 녹색물류와 물류포장"),
            ("LM08", "물류아웃소싱과 물류보안"),
        ],
    },
    {
        "course": "화물운송론",
        "chapters": [
            ("FT01", "화물운송의 기초"),
            ("FT02", "공로운송"),
            ("FT03", "철도운송"),
            ("FT04", "해상운송"),
            ("FT05", "항공운송"),
            ("FT06", "국제복합운송"),
            ("FT07", "유닛로드시스템(ULS)"),
            ("FT08", "수·배송시스템의 합리화"),
        ],
    },
    {
        "course": "국제물류론",
        "chapters": [
            ("IT01", "국제물류 총론"),
            ("IT02", "국제해상운송"),
            ("IT03", "국제항공운송"),
            ("IT04", "국제복합운송 및 국제물류보안"),
        ],
    },
    {
        "course": "보관하역론",
        "chapters": [
            ("BH01", "보관 및 창고의 기초개념"),
            ("BH02", "물류시설과 창고관리시스템"),
            ("BH03", "물류시설의 계획 및 운영"),
            ("BH04", "재고관리시스템"),
            ("BH05", "하역의 이해"),
            ("BH06", "하역운반장비"),
            ("BH07", "유닛로드시스템과 포장"),
            ("BH08", "운송수단별 하역방식"),
        ],
    },
    {
        "course": "물류관련법규",
        "chapters": [
            ("LR01", "물류정책기본법"),
            ("LR02", "물류시설의 개발 및 운영에 관한 법률"),
            ("LR03", "화물자동차 운수사업법"),
            ("LR04", "철도사업법"),
            ("LR05", "항만운송사업법"),
            ("LR06", "유통산업발전법"),
            ("LR07", "농수산물 유통 및 가격안정에 관한 법률"),
        ],
    },
]


LOGISTICS_SOURCE_PREFIX_ALIASES = {
    "WH": "BH",
    "TR": "FT",
    "IL": "IT",
    "LW": "LR",
}
LOGISTICS_CHAPTER_NAMES = {
    code: name
    for course in LOGISTICS_CURRICULUM
    for code, name in course["chapters"]
}


def normalize_logistics_chapter(chapter_code, chapter_name):
    code = (chapter_code or "").strip().upper()
    name = (chapter_name or "").strip()

    match = re.fullmatch(r"([A-Z]{2})(\d{2})", code)
    if match:
        prefix, number = match.groups()
        code = f"{LOGISTICS_SOURCE_PREFIX_ALIASES.get(prefix, prefix)}{number}"

    return code, LOGISTICS_CHAPTER_NAMES.get(code, name)


def get_logistics_curriculum():
    return [
        {
            "course": item["course"],
            "chapters": [
                {
                    "chapter_code": code,
                    "chapter_name": name,
                    "display_no": f"{index:02d}",
                }
                for index, (code, name) in enumerate(item["chapters"], start=1)
            ],
        }
        for item in LOGISTICS_CURRICULUM
    ]


def build_logistics_chapter_roadmap(user, subject):
    latest_attempt_qs = (
        Attempt.objects.valid_for_learning()
        .filter(user=user, mission=OuterRef("pk"))
        .order_by("-created_at")
    )

    rows = (
        Mission.objects
        .filter(subject=subject, is_usable_for_set=True)
        .annotate(
            last_time=Subquery(latest_attempt_qs.values("created_at")[:1]),
            last_is_correct=Subquery(latest_attempt_qs.values("is_correct")[:1]),
        )
        .values("chapter_code")
        .annotate(
            total_count=Count("id"),
            attempted_count=Count("id", filter=Q(last_time__isnull=False)),
            solved_count=Count("id", filter=Q(last_is_correct=True)),
        )
    )

    stats_by_code = {row["chapter_code"]: row for row in rows}

    roadmap = []
    for course in LOGISTICS_CURRICULUM:
        chapters = []
        for index, (chapter_code, chapter_name) in enumerate(course["chapters"], start=1):
            stats = stats_by_code.get(chapter_code, {})
            total_count = stats.get("total_count", 0) or 0
            attempted_count = stats.get("attempted_count", 0) or 0
            solved_count = stats.get("solved_count", 0) or 0
            progress_pct = round((solved_count / total_count) * 100, 1) if total_count else 0.0

            if total_count == 0:
                status = "문제 준비 중"
            elif solved_count >= total_count:
                status = "완료"
            elif attempted_count > 0:
                status = "학습 중"
            else:
                status = "미시작"

            chapters.append({
                "chapter_code": chapter_code,
                "chapter_name": chapter_name,
                "display_no": f"{index:02d}",
                "total_count": total_count,
                "attempted_count": attempted_count,
                "solved_count": solved_count,
                "correct_count": solved_count,
                "progress_pct": progress_pct,
                "status": status,
            })

        roadmap.append({
            "course": course["course"],
            "chapters": chapters,
        })

    return roadmap
