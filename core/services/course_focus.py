from core.models import Attempt, CourseFocus, Mission, UserWeakness
from core.services.logistics_curriculum import LOGISTICS_CURRICULUM
from core.services.subjects import LOGISTICS_SUBJECT_CODE


def available_courses(subject):
    """Return names and chapter codes; the qualification remains the Subject."""
    if subject.code == LOGISTICS_SUBJECT_CODE:
        return [
            {"name": row["course"], "chapter_codes": [code for code, _ in row["chapters"]]}
            for row in LOGISTICS_CURRICULUM
        ]
    rows = Mission.objects.filter(subject=subject).exclude(course="").values_list(
        "course", "chapter_code"
    ).distinct().order_by("course", "chapter_code")
    courses = {}
    for name, code in rows:
        course = courses.setdefault(name, {"name": name, "chapter_codes": []})
        if code and code not in course["chapter_codes"]:
            course["chapter_codes"].append(code)
    return list(courses.values())


def chosen_course(user, subject, courses):
    name = CourseFocus.objects.filter(user=user, subject=subject).values_list("course", flat=True).first()
    return name if name in {row["name"] for row in courses} else None


def course_weakness(user, subject, course):
    """Avoid presenting a guessed weakness before this course has attempt evidence."""
    attempts = Attempt.objects.valid_for_learning().filter(
        user=user, mission__subject=subject, mission__course=course,
    )
    if not attempts.exists():
        return {"state": "new"}
    weakness = UserWeakness.objects.filter(
        user=user, subject=subject,
        wrong_pattern__skill__in=Mission.objects.filter(
            subject=subject, course=course,
        ).exclude(chapter_code="").values_list("chapter_code", flat=True).distinct(),
    ).exclude(status=UserWeakness.STATUS_MASTERED).select_related("wrong_pattern").order_by(
        "-severity", "-recent_failure_count", "-last_detected_at",
    ).first()
    if not weakness:
        return {"state": "none"}
    return {
        "state": "found",
        "label": weakness.wrong_pattern.name.replace(" 핵심 개념 혼동", ""),
        "pattern_code": weakness.wrong_pattern.code,
        "status": "관찰 중" if weakness.status == UserWeakness.STATUS_SUSPECTED else "복습 필요",
    }
