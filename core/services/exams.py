import random

from django.db import transaction
from django.utils import timezone

from core.models import Mission, ExamSession, ExamSessionMission, Attempt
from core.services.grading import grade_answer, grade_multi_answer, parse_answer_schema
from core.services.mission_versioning import attempt_snapshot_defaults
from core.services.streaks import update_user_streak


def calculate_exam_score(correct_count, total_questions):
    """Return the canonical percentage score with one decimal place."""
    if not total_questions:
        return 0.0
    return round((correct_count / total_questions) * 100, 1)


def exact_exam_score(exam):
    """Read a precise score while keeping partially populated legacy rows usable."""
    is_mode_exam = bool((exam.mode_config or {}).get("mode"))
    has_complete_legacy_counts = (
        exam.correct_count + exam.wrong_count == exam.total_questions
    )
    if exam.total_questions and (is_mode_exam or has_complete_legacy_counts):
        return calculate_exam_score(exam.correct_count, exam.total_questions)
    return float(exam.score)


def draft_has_answer(draft_answers):
    return any(
        str(value).strip()
        for values in (draft_answers or {}).values()
        for value in (values if isinstance(values, list) else [values])
    )


def grade_exam_draft(mission, draft_answers):
    """Return (submitted_answer, correctness), or None for an unanswered draft."""
    if not draft_has_answer(draft_answers):
        return None
    if mission.question_type == "manual":
        values = draft_answers.get("is_correct", [])
        raw = values[0] if values else ""
        if raw not in ("true", "false"):
            return None
        return raw, raw == "true"
    schema_items = parse_answer_schema(mission.answer_schema)
    if schema_items and mission.question_type not in ("choice_one", "true_false", "error_detect"):
        values = draft_answers.get("submitted_answers", [])
        result = grade_multi_answer(submitted_answers=values, schema_text=mission.answer_schema)
        if result["error"]:
            return None
        return " | ".join(values), result["is_correct"]
    values = draft_answers.get("submitted_answer", [])
    raw = values[0].strip() if values else ""
    result = grade_answer(
        question_type=mission.question_type,
        answer_input_type=mission.answer_input_type,
        submitted_answer=raw,
        correct_answer=mission.correct_answer,
    )
    if result["error"]:
        return None
    return raw, result["is_correct"]


def finalize_exam_drafts(exam):
    """Freeze mutable drafts exactly once immediately before final scoring."""
    submitted_at = timezone.now()
    for item in exam.items.select_related("mission").all():
        if item.submitted_at is not None and not draft_has_answer(item.draft_answers):
            continue  # Preserve a legacy answer created by the old immediate-submit flow.
        graded = grade_exam_draft(item.mission, item.draft_answers)
        if graded is None:
            continue
        item.submitted_answer, item.user_answer_correct = graded
        item.submitted_at = submitted_at
        item.draft_answers = {}
        item.save(update_fields=[
            "submitted_answer", "user_answer_correct", "submitted_at", "draft_answers",
        ])

@transaction.atomic
def create_exam_session(user, title="실전 모의고사 1회", time_limit_min=40, total_questions=40, subject=None):
    """
    시험 세션 1개와 시험 문제를 생성한다.
    - 스킬별로 최대한 고르게 문제를 뽑는다.
    - 부족하면 전체 문제에서 추가 보충한다.
    - total_questions 개수에 맞춰 최종 구성한다.
    """
    mission_qs = Mission.objects.filter(is_usable_for_set=True).exclude(
        review_status=Mission.REVIEW_CONFIRMED_ERROR,
    )
    if subject is not None:
        mission_qs = mission_qs.filter(subject=subject)

    skills = list(
        mission_qs.values_list("skill", flat=True).distinct()
    )

    if not skills:
        raise ValueError("등록된 스킬이 없습니다.")

    per_skill = max(1, total_questions // len(skills))

    exam = ExamSession.objects.create(
        user=user,
        title=title,
        time_limit_min=time_limit_min,
        total_questions=total_questions,
        status="in_progress",
    )

    selected = []
    used_ids = set()

    # 1) 스킬별 우선 선발
    for skill in skills:
        picked = list(
            mission_qs
            .filter(skill=skill)
            .exclude(id__in=used_ids)
            .order_by("?")[:per_skill]
        )
        selected.extend(picked)
        used_ids.update(m.id for m in picked)

    # 2) 부족하면 전체 문제에서 보충
    remain = total_questions - len(selected)
    if remain > 0:
        extra = list(
            mission_qs
            .exclude(id__in=used_ids)
            .order_by("?")[:remain]
        )
        selected.extend(extra)
        used_ids.update(m.id for m in extra)

    # 3) 너무 많으면 잘라내기
    if len(selected) > total_questions:
        random.shuffle(selected)
        selected = selected[:total_questions]

    # 4) 최종 검증
    if len(selected) < total_questions:
        raise ValueError(f"시험 문제 수가 부족합니다. 최소 {total_questions}문제가 필요합니다.")

    # 5) 문제 순서 섞기
    random.shuffle(selected)

    # 6) 시험 문제 저장
    ExamSessionMission.objects.bulk_create([
        ExamSessionMission(
            exam_session=exam,
            mission=mission,
            order_no=idx,
        )
        for idx, mission in enumerate(selected, start=1)
    ])

    return exam


@transaction.atomic
def submit_exam_answer(exam_item, is_correct, submitted_answer=""):
    """
    시험 문제 1개에 대한 사용자의 정답/오답 입력 저장
    """
    exam = ExamSession.objects.select_for_update().get(pk=exam_item.exam_session_id)
    exam_item.refresh_from_db()
    if exam.status != "in_progress" or exam_item.submitted_at is not None:
        return False
    if timezone.now() >= exam.started_at + timezone.timedelta(minutes=exam.time_limit_min):
        finish_exam_session(exam)
        return False
    exam_item.user_answer_correct = is_correct
    exam_item.submitted_at = timezone.now()
    exam_item.submitted_answer = submitted_answer
    exam_item.draft_answers = {}
    exam_item.save(update_fields=["user_answer_correct", "submitted_at", "submitted_answer", "draft_answers"])
    return True


@transaction.atomic
def sync_exam_to_attempts(exam):
    """
    시험 결과를 일반 학습 기록(Attempt)으로 반영한다.
    이미 반영된 시험은 중복 반영하지 않는다.
    """
    locked = ExamSession.objects.select_for_update().get(pk=exam.pk)
    if locked.attempts_synced:
        return

    items = list(
        exam.items.select_related("mission").filter(submitted_at__isnull=False)
    )

    attempt_list = []
    for item in items:
        attempt_list.append(
            Attempt(
                user=exam.user,
                mission=item.mission,
                is_correct=item.user_answer_correct is True,
                time_spent_sec=None,
                daily_date=None,
                submitted_answer=item.submitted_answer,
                **attempt_snapshot_defaults(item.mission),
            )
        )

    Attempt.objects.bulk_create(attempt_list)

    if attempt_list:
        update_user_streak(exam.user)

    exam.attempts_synced = True
    exam.save(update_fields=["attempts_synced"])


@transaction.atomic
def finish_exam_session(exam):
    """
    시험 전체를 제출 완료 처리하고 점수 계산
    """
    locked = ExamSession.objects.select_for_update().get(pk=exam.pk)
    if locked.status == "waiting":
        return exam
    if locked.status != "in_progress" and locked.attempts_synced:
        exam.refresh_from_db()
        return exam
    exam = locked
    finalize_exam_drafts(locked)
    items = list(locked.items.select_related("mission").all())

    correct_count = sum(1 for item in items if item.user_answer_correct is True)
    wrong_count = sum(1 for item in items if item.user_answer_correct is False)

    unanswered_count = sum(1 for item in items if item.user_answer_correct is None)
    wrong_count += unanswered_count

    total = len(items)
    score = calculate_exam_score(correct_count, total)

    exam.correct_count = correct_count
    exam.wrong_count = wrong_count
    exam.score = score
    exam.status = "submitted"
    exam.ended_at = timezone.now()
    exam.save(update_fields=[
        "correct_count",
        "wrong_count",
        "score",
        "status",
        "ended_at",
    ])

    sync_exam_to_attempts(exam)

    return exam
