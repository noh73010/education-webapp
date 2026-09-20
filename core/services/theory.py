import html
import re
from pathlib import Path

from django.conf import settings
from django.db.models import Count, Min, Q
from django.utils.safestring import mark_safe
from django.utils.text import slugify

from core.models import Attempt, Mission
from core.services.logistics_curriculum import LOGISTICS_CURRICULUM


THEORY_ROOT = Path(settings.BASE_DIR) / "theory"
SAFE_CODE = re.compile(r"^[A-Za-z0-9_-]+$")
THEORY_SET_PREFIX = "[이론학습]"
THEORY_BATCH_SIZE = 10


def get_theory_path(subject_code: str, chapter_code: str) -> Path | None:
    if not SAFE_CODE.fullmatch(subject_code or "") or not SAFE_CODE.fullmatch(chapter_code or ""):
        return None
    return THEORY_ROOT / subject_code / f"{chapter_code}.md"


def load_theory_markdown(subject_code: str, chapter_code: str) -> str | None:
    path = get_theory_path(subject_code, chapter_code)
    if path is None or not path.is_file():
        return None
    # PowerShell이나 일부 편집기로 저장된 UTF-8 BOM이 첫 Markdown 제목의
    # `#` 인식을 방해하지 않도록 BOM을 함께 제거합니다.
    return path.read_text(encoding="utf-8-sig")


def has_theory(subject_code: str, chapter_code: str) -> bool:
    return load_theory_markdown(subject_code, chapter_code) is not None


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text, quote=True)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def render_theory_markdown(source: str):
    """Render the small, trusted Markdown subset used by chapter theory files."""
    source = (source or "").lstrip("\ufeff")
    output = []
    paragraph = []
    list_type = None

    def flush_paragraph():
        if paragraph:
            output.append(f"<p>{'<br>'.join(_inline_markdown(line) for line in paragraph)}</p>")
            paragraph.clear()

    def close_list():
        nonlocal list_type
        if list_type:
            output.append(f"</{list_type}>")
            list_type = None

    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            close_list()
            continue

        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            output.append(f"<h{level}>{_inline_markdown(heading.group(2))}</h{level}>")
            continue

        if re.fullmatch(r"-{3,}", line):
            flush_paragraph()
            close_list()
            output.append("<hr>")
            continue


        bullet = re.match(r"^[-*]\s+(.+)$", line)
        numbered = re.match(r"^\d+\.\s+(.+)$", line)
        if bullet or numbered:
            flush_paragraph()
            wanted_type = "ul" if bullet else "ol"
            if list_type != wanted_type:
                close_list()
                list_type = wanted_type
                output.append(f"<{list_type}>")
            output.append(f"<li>{_inline_markdown((bullet or numbered).group(1))}</li>")
            continue

        if line.startswith("> "):
            flush_paragraph()
            close_list()
            output.append(f"<blockquote>{_inline_markdown(line[2:])}</blockquote>")
            continue

        if line.startswith("정답:"):
            flush_paragraph()
            close_list()
            answer = line.removeprefix("정답:").strip()
            output.append(
                '<details class="theory-check-answer">'
                '<summary>정답과 설명 확인</summary>'
                f'<p>{_inline_markdown(answer)}</p>'
                '</details>'
            )
            continue

        paragraph.append(line)

    flush_paragraph()
    close_list()
    return mark_safe("\n".join(output))


def build_subject_theory_roadmap(user, subject):
    rows = list(
        Mission.objects
        .filter(subject=subject, is_usable_for_set=True)
        .exclude(chapter_code="")
        .values("course", "chapter_code", "chapter_name")
        .annotate(
            first_id=Min("id"),
            total_count=Count("id", distinct=True),
            attempted_count=Count(
                "id",
                filter=Q(attempt__user=user, attempt__grading_valid=True),
                distinct=True,
            ),
            solved_count=Count(
                "id",
                filter=Q(
                    attempt__user=user,
                    attempt__is_correct=True,
                    attempt__grading_valid=True,
                ),
                distinct=True,
            ),
        )
    )

    latest_attempt_by_mission = {}
    for attempt in (
        Attempt.objects.valid_for_learning()
        .filter(
            user=user,
            mission__subject=subject,
            mission__is_usable_for_set=True,
        )
        .exclude(mission__chapter_code="")
        .select_related("mission")
        .order_by("mission_id", "-created_at")
    ):
        latest_attempt_by_mission.setdefault(attempt.mission_id, attempt)
    review_count_by_chapter = {}
    for attempt in latest_attempt_by_mission.values():
        if attempt.is_correct is False:
            code = attempt.mission.chapter_code
            review_count_by_chapter[code] = review_count_by_chapter.get(code, 0) + 1
    for row in rows:
        row["review_count"] = review_count_by_chapter.get(row["chapter_code"], 0)

    logistics_order = {
        code: position
        for position, code in enumerate(
            code
            for course in LOGISTICS_CURRICULUM
            for code, _name in course["chapters"]
        )
    }
    if subject.code == "logistics":
        row_by_code = {row["chapter_code"]: row for row in rows}
        curriculum_rows = []
        for position, course in enumerate(LOGISTICS_CURRICULUM):
            for chapter_position, (chapter_code, chapter_name) in enumerate(course["chapters"]):
                curriculum_rows.append(row_by_code.pop(chapter_code, {
                    "course": course["course"],
                    "chapter_code": chapter_code,
                    "chapter_name": chapter_name,
                    "first_id": 1_000_000 + (position * 100) + chapter_position,
                    "total_count": 0,
                    "attempted_count": 0,
                    "solved_count": 0,
                    "review_count": 0,
                }))
        rows = curriculum_rows + list(row_by_code.values())

    rows.sort(
        key=lambda row: (
            logistics_order.get(row["chapter_code"], 10_000),
            row["first_id"],
        )
    )

    courses = []
    course_map = {}
    for row in rows:
        total = row["total_count"] or 0
        solved = row["solved_count"] or 0
        attempted = row["attempted_count"] or 0
        review_count = row.get("review_count", 0)
        if not total:
            status = "연습문제 준비 중"
        elif attempted >= total and not review_count:
            status = "연습 완료"
        elif attempted >= total and review_count:
            status = "복습 필요"
        elif attempted:
            status = "학습 중"
        else:
            status = "미시작"

        chapter = {
            **row,
            "slug": slugify(
                f"{row['course'] or subject.name}-{row['chapter_name']}",
                allow_unicode=True,
            ),
            "progress_pct": round((attempted / total) * 100, 1) if total else 0,
            "mastery_pct": round((solved / total) * 100, 1) if total else 0,
            "remaining_count": max(total - attempted, 0),
            "status": status,
            "has_theory": has_theory(subject.code, row["chapter_code"]),
        }
        course_name = row["course"] or subject.name
        if course_name not in course_map:
            course = {"course": course_name, "chapters": []}
            course_map[course_name] = course
            courses.append(course)
        course_map[course_name]["chapters"].append(chapter)

    recommended_assigned = False
    for course in courses:
        for display_no, chapter in enumerate(course["chapters"], start=1):
            chapter["display_no"] = f"{display_no:02d}"
            chapter["is_recommended"] = False
            if (
                not recommended_assigned
                and chapter["has_theory"]
                and chapter["status"] != "연습 완료"
            ):
                chapter["is_recommended"] = True
                recommended_assigned = True
        course["total_count"] = sum(chapter["total_count"] for chapter in course["chapters"])
        course["attempted_count"] = sum(chapter["attempted_count"] for chapter in course["chapters"])
        course["solved_count"] = sum(chapter["solved_count"] for chapter in course["chapters"])
        course["progress_pct"] = round(
            (course["attempted_count"] / course["total_count"]) * 100, 1
        ) if course["total_count"] else 0
        course["is_recommended"] = any(chapter["is_recommended"] for chapter in course["chapters"])
    return courses


def flatten_theory_roadmap(roadmap):
    return [chapter for course in roadmap for chapter in course["chapters"]]


def get_theory_chapter_map(user, subject):
    return {
        chapter["chapter_code"]: chapter
        for chapter in flatten_theory_roadmap(build_subject_theory_roadmap(user, subject))
        if chapter["has_theory"]
    }


def get_theory_chapter_context(user, subject, chapter_reference: str):
    roadmap = build_subject_theory_roadmap(user, subject)
    chapters = flatten_theory_roadmap(roadmap)
    for index, chapter in enumerate(chapters):
        if chapter["slug"] == chapter_reference or chapter["chapter_code"] == chapter_reference:
            return {
                "chapter": chapter,
                "previous_chapter": chapters[index - 1] if index > 0 else None,
                "next_chapter": chapters[index + 1] if index + 1 < len(chapters) else None,
                "roadmap": roadmap,
            }
    return None


def build_chapter_practice_plan(user, subject, chapter_code: str, *, mode="batch", batch_size=THEORY_BATCH_SIZE):
    """Select a scalable chapter practice batch without changing the source missions."""
    missions = list(
        Mission.objects
        .filter(subject=subject, chapter_code=chapter_code, is_usable_for_set=True)
        .order_by("external_id", "id")
    )
    mission_ids = [mission.id for mission in missions]
    latest_attempts = {}
    for attempt in (
        Attempt.objects.valid_for_learning()
        .filter(user=user, mission_id__in=mission_ids)
        .order_by("mission_id", "-created_at")
    ):
        latest_attempts.setdefault(attempt.mission_id, attempt)

    unlearned = [mission for mission in missions if mission.id not in latest_attempts]
    wrong = [
        mission for mission in missions
        if mission.id in latest_attempts and latest_attempts[mission.id].is_correct is False
    ]
    learned = [
        mission for mission in missions
        if mission.id in latest_attempts and latest_attempts[mission.id].is_correct is True
    ]
    wrong.sort(key=lambda mission: latest_attempts[mission.id].created_at)
    learned.sort(key=lambda mission: latest_attempts[mission.id].created_at)

    if mode == "all":
        selected = missions
    elif mode == "wrong":
        selected = wrong
    else:
        selected = (unlearned + wrong + learned)[:batch_size]

    return {
        "missions": selected,
        "total_count": len(missions),
        "attempted_count": len(missions) - len(unlearned),
        "remaining_count": len(unlearned),
        "review_count": len(wrong),
        "batch_size": batch_size,
        "mode": mode,
    }
