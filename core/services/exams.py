import random

from django.db import transaction
from django.utils import timezone

from core.models import Mission, ExamSession, ExamSessionMission, Attempt
from core.services.streaks import update_user_streak

@transaction.atomic
def create_exam_session(user, title="실전 모의고사 1회", time_limit_min=40, total_questions=40):
    """
    시험 세션 1개와 시험 문제를 생성한다.
    - 스킬별로 최대한 고르게 문제를 뽑는다.
    - 부족하면 전체 문제에서 추가 보충한다.
    - total_questions 개수에 맞춰 최종 구성한다.
    """
    skills = list(
        Mission.objects.values_list("skill", flat=True).distinct()
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
            Mission.objects
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
            Mission.objects
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
def submit_exam_answer(exam_item, is_correct):
    """
    시험 문제 1개에 대한 사용자의 정답/오답 입력 저장
    """
    exam_item.user_answer_correct = is_correct
    exam_item.submitted_at = timezone.now()
    exam_item.save(update_fields=["user_answer_correct", "submitted_at"])


@transaction.atomic
def sync_exam_to_attempts(exam):
    """
    시험 결과를 일반 학습 기록(Attempt)으로 반영한다.
    이미 반영된 시험은 중복 반영하지 않는다.
    """
    if exam.attempts_synced:
        return

    items = list(
        exam.items.select_related("mission").all()
    )

    attempt_list = []
    for item in items:
        is_correct = (item.user_answer_correct is True)

        attempt_list.append(
            Attempt(
                user=exam.user,
                mission=item.mission,
                is_correct=is_correct,
                time_spent_sec=None,
                daily_date=None,
            )
        )

    Attempt.objects.bulk_create(attempt_list)

    update_user_streak(exam.user)

    exam.attempts_synced = True
    exam.save(update_fields=["attempts_synced"])


@transaction.atomic
def finish_exam_session(exam):
    """
    시험 전체를 제출 완료 처리하고 점수 계산
    """
    items = list(exam.items.select_related("mission").all())

    correct_count = sum(1 for item in items if item.user_answer_correct is True)
    wrong_count = sum(1 for item in items if item.user_answer_correct is False)

    unanswered_count = sum(1 for item in items if item.user_answer_correct is None)
    wrong_count += unanswered_count

    total = len(items)
    score = round((correct_count / total) * 100) if total else 0

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