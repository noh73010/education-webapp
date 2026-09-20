"""Exam blueprints and verdicts, separate from the existing submission engine."""
from django.db import transaction
from django.db.models import Count, Exists, OuterRef
from django.utils import timezone

from core.models import Attempt, ExamSession, ExamSessionMission, Mission
from core.services.exams import calculate_exam_score, exact_exam_score
from core.services.logistics_curriculum import LOGISTICS_CURRICULUM


def blueprint(subject):
    if subject.code != "logistics":
        return None
    return {"courses": [row["course"] for row in LOGISTICS_CURRICULUM],
            "per_course": 40, "minimum": 40, "average": 60,
            "periods": [(0, 3, 120), (3, 5, 80)]}


def available_courses(subject):
    plan = blueprint(subject)
    return plan["courses"] if plan else list(Mission.objects.filter(
        subject=subject, is_usable_for_set=True).exclude(
        review_status=Mission.REVIEW_CONFIRMED_ERROR,
    ).exclude(course="").order_by("course").values_list("course", flat=True).distinct())


def missing_full_courses(subject):
    plan = blueprint(subject)
    if not plan:
        return []
    counts = dict(Mission.objects.filter(subject=subject, is_usable_for_set=True,
        question_type__in=["choice_one", "true_false", "error_detect"]).exclude(
        review_status=Mission.REVIEW_CONFIRMED_ERROR).exclude(
        correct_answer="").exclude(answer_schema="").values("course").annotate(
        total=Count("pk")).values_list("course", "total"))
    return [course for course in plan["courses"] if counts.get(course, 0) < plan["per_course"]]


def select_questions(user, subject, count, course=None):
    qs = Mission.objects.filter(subject=subject, is_usable_for_set=True,
        question_type__in=["choice_one", "true_false", "error_detect"]).exclude(
        review_status=Mission.REVIEW_CONFIRMED_ERROR,
    ).exclude(correct_answer="").exclude(answer_schema="")
    if course:
        qs = qs.filter(course=course)
    qs = qs.annotate(seen=Exists(
        Attempt.objects.valid_for_learning().filter(user=user, mission_id=OuterRef("pk"))
    ))
    questions = list(qs.order_by("seen", "?")[:count])
    if len(questions) != count:
        raise ValueError(f"{course or '선택한 자격증'}: 출제 가능한 문제가 부족합니다. {count}문제 구성이 준비되면 시작할 수 있습니다.")
    return questions


@transaction.atomic
def create_mode_exam(user, subject, mode, course=""):
    plan = blueprint(subject)
    if mode not in {"short", "course", "full"}:
        raise ValueError("올바른 모드를 선택해 주세요.")
    if mode == "full" and not plan:
        raise ValueError("이 자격증의 실전 시험 구성이 아직 등록되지 않았습니다.")
    groups = []
    if mode == "short":
        groups = [("짧은 실전 연습", 10, select_questions(user, subject, 10))]
    elif mode == "course":
        if course not in available_courses(subject):
            raise ValueError("올바른 과목을 선택해 주세요.")
        groups = [(f"과목별 모의고사 · {course}", 40, select_questions(user, subject, 40, course))]
    else:
        for number, (start, end, minutes) in enumerate(plan["periods"], 1):
            selected = []
            for name in plan["courses"][start:end]:
                selected.extend(select_questions(user, subject, plan["per_course"], name))
            groups.append((f"실전 모의고사 · {number}교시", minutes, selected))
    first = previous = None
    for number, (title, minutes, questions) in enumerate(groups, 1):
        config = {"mode": mode, "course": course, "period": number,
            "plan": plan, "question_courses": {str(q.pk): q.course for q in questions},
            "seen_count": sum(q.seen for q in questions)}
        exam = ExamSession.objects.create(user=user, title=title, time_limit_min=minutes,
            total_questions=len(questions), status="in_progress" if number == 1 else "waiting",
            previous_sitting=previous, mode_config=config)
        ExamSessionMission.objects.bulk_create([ExamSessionMission(exam_session=exam,
            mission=q, order_no=i) for i, q in enumerate(questions, 1)])
        first = first or exam
        previous = exam
    return first


@transaction.atomic
def begin_second_sitting(user, subject, exam_id):
    exam = ExamSession.objects.select_for_update().filter(pk=exam_id, user=user).first()
    if not exam or not exam.items.filter(mission__subject=subject).exists() or not exam.previous_sitting_id or exam.mode_config.get("mode") != "full":
        raise ValueError("시작할 수 없는 시험입니다.")
    if exam.previous_sitting.status not in ("submitted", "expired"):
        raise ValueError("1교시를 먼저 완료해 주세요.")
    if exam.status == "waiting":
        exam.status = "in_progress"
        exam.started_at = timezone.now()
        exam.save(update_fields=["status", "started_at"])
    return exam


def mode_result(exam):
    config = exam.mode_config
    mode = config.get("mode")
    result = {"label": "연습 결과 · 전체 합격 판정 대상 아님", "rows": [],
              "next": None, "average": None, "seen_count": config.get("seen_count")}
    result["sitting_score"] = exact_exam_score(exam)
    if mode not in {"full", "course"}:
        return result
    plan = config.get("plan")
    sessions = [exam]
    if mode == "full":
        first = exam.previous_sitting if exam.previous_sitting_id else exam
        second = ExamSession.objects.filter(previous_sitting=first).first()
        sessions = [first] + ([second] if second else [])
        result["next"] = second if second and second.pk != exam.pk else None
        if len(sessions) != 2 or any(s.status not in ("submitted", "expired") for s in sessions):
            result["label"] = "판정 전 · 두 교시를 모두 완료해 주세요"
            return result
    names = plan["courses"] if mode == "full" else [config["course"]]
    for name in names:
        items = [item for session in sessions for item in session.items.all()
            if session.mode_config.get("question_courses", {}).get(str(item.mission_id)) == name]
        expected = plan["per_course"] if plan else 40
        if len(items) != expected:
            result["label"] = "판정 불가 · 시험 구성 확인 필요"
            return result
        correct = sum(item.user_answer_correct is True for item in items)
        score = calculate_exam_score(correct, expected)
        result["rows"].append({"course": name, "correct": correct, "score": score,
            "below_minimum": bool(plan and score < plan["minimum"])})
    if mode == "full":
        average = round(sum(row["score"] for row in result["rows"]) / len(names), 1)
        result["average"] = average
        result["label"] = "합격 기준 충족" if average >= plan["average"] and not any(
            row["below_minimum"] for row in result["rows"]) else "합격 기준 미충족"
    return result
