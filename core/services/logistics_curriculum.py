import re

from django.db.models import Count, OuterRef, Q, Subquery

from core.models import Attempt, Mission


LOGISTICS_CURRICULUM = [
    {
        "course": "물류관리론",
        "chapters": [
            ("LM01", "물류관리 일반"),
            ("LM02", "물류시스템 구축"),
            ("LM03", "SCM과 녹색물류"),
            ("LM04", "국제물류"),
        ],
    },
    {
        "course": "화물운송론",
        "chapters": [
            ("TR01", "화물운송의 기초이론"),
            ("TR02", "화물자동차운송"),
            ("TR03", "수·배송시스템의 합리화"),
            ("TR04", "철도운송"),
            ("TR05", "항공운송"),
            ("TR06", "해상운송(국제 및 연안운송)"),
            ("TR07", "국제복합운송"),
            ("TR08", "택배·생활물류 및 단위적재운송시스템(ULS)"),
        ],
    },
    {
        "course": "국제물류론",
        "chapters": [
            ("IL01", "국제물류관리"),
            ("IL02", "무역실무"),
            ("IL03", "해상운송"),
            ("IL04", "해상보험"),
            ("IL05", "항공운송"),
            ("IL06", "컨테이너 운송"),
            ("IL07", "복합운송"),
        ],
    },
    {
        "course": "보관하역론",
        "chapters": [
            ("WH01", "보관론"),
            ("WH02", "하역론"),
        ],
    },
    {
        "course": "물류관련법규",
        "chapters": [
            ("LW01", "물류정책기본법"),
            ("LW02", "물류시설의 개발 및 운영에 관한 법률"),
            ("LW03", "유통산업발전법"),
            ("LW04", "화물자동차 운수사업법"),
            ("LW05", "철도사업법"),
            ("LW06", "항만운송사업법"),
            ("LW07", "농수산물 유통 및 가격안정에 관한 법률"),
        ],
    },
]


LOGISTICS_SOURCE_PREFIX_ALIASES = {
    "BH": "WH",
    "FT": "TR",
    "IT": "IL",
    "LR": "LW",
}


def normalize_logistics_chapter(chapter_code, chapter_name):
    code = (chapter_code or "").strip().upper()
    name = (chapter_name or "").strip()

    if code == "FT07" and "택배" in name:
        return "TR08", name

    match = re.fullmatch(r"([A-Z]{2})(\d{2})", code)
    if match:
        prefix, number = match.groups()
        code = f"{LOGISTICS_SOURCE_PREFIX_ALIASES.get(prefix, prefix)}{number}"

    return code, name


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
        Attempt.objects
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
