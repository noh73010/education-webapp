"""Explicit, user-scoped data removal; shared question content is never deleted."""

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import (
    Attempt, ConfusionCard, DailyMission, ExamSession, Inquiry,
    PatternTrainingSession, ProblemSetSession, UserEvent, UserStreak, UserWeakness,
    LearningStart, MissionWork, WrongPattern,
)

LEARNING_MODELS = (
    MissionWork, LearningStart,
    ProblemSetSession, ExamSession, PatternTrainingSession, Attempt,
    DailyMission, ConfusionCard, UserWeakness, UserStreak,
)
LEARNING_EVENTS = (
    "start_mission", "finish_mission", "start_exam", "finish_exam",
    "start_problem_set", "finish_problem_set",
    "start_pattern_training", "finish_pattern_training",
)


def _remove_sessions(user_id):
    # The project uses Django's database session backend. Never delete other users' sessions.
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if str(session.get_decoded().get("_auth_user_id")) == str(user_id):
            session.delete()


@transaction.atomic
def reset_learning_data(user):
    get_user_model().objects.select_for_update().get(pk=user.pk)
    for model in LEARNING_MODELS:
        model.objects.filter(user_id=user.pk).delete()
    UserEvent.objects.filter(user_id=user.pk, event_type__in=LEARNING_EVENTS).delete()
    _remove_sessions(user.pk)


class MixedQualificationSessionError(ValueError):
    """A legacy session contains multiple qualifications and cannot be safely erased in part."""


def _refresh_streak_from_remaining_attempts(user):
    days = sorted({timezone.localtime(created_at).date() for created_at in
                   Attempt.objects.filter(user=user).values_list("created_at", flat=True)})
    if not days:
        UserStreak.objects.filter(user=user).delete()
        return
    best = run = 0
    previous = None
    from datetime import timedelta

    for day in days:
        run = run + 1 if previous == day - timedelta(days=1) else 1
        best = max(best, run)
        previous = day
    current = run if days[-1] >= timezone.localdate() - timedelta(days=1) else 0
    UserStreak.objects.update_or_create(user=user, defaults={
        "current_streak": current, "best_streak": best, "last_solved_date": days[-1],
    })


@transaction.atomic
def reset_subject_learning_data(user, subject):
    """Erase one qualification, without deleting another qualification's sessions."""
    get_user_model().objects.select_for_update().get(pk=user.pk)
    exam_ids = set(ExamSession.objects.filter(
        user=user, items__mission__subject=subject,
    ).values_list("pk", flat=True))
    set_ids = set(ProblemSetSession.objects.filter(
        user=user, items__mission__subject=subject,
    ).values_list("pk", flat=True))
    exam_subjects = ExamSession.objects.filter(pk__in=exam_ids).values_list(
        "items__mission__subject_id", flat=True,
    )
    set_subjects = ProblemSetSession.objects.filter(pk__in=set_ids).values_list(
        "items__mission__subject_id", flat=True,
    )
    if any(subject_id != subject.pk for subject_id in exam_subjects) or any(
        subject_id != subject.pk for subject_id in set_subjects
    ):
        raise MixedQualificationSessionError("여러 자격증이 섞인 시험 기록이 있어 안전하게 초기화할 수 없습니다. 관리자에게 문의해 주세요.")
    if ExamSession.objects.filter(pk__in=exam_ids, previous_sitting__isnull=False).exclude(
        previous_sitting_id__in=exam_ids,
    ).exists() or ExamSession.objects.filter(previous_sitting_id__in=exam_ids).exclude(
        pk__in=exam_ids,
    ).exists():
        raise MixedQualificationSessionError("다른 자격증과 연결된 시험 기록이 있어 안전하게 초기화할 수 없습니다. 관리자에게 문의해 주세요.")

    mission_ids = list(MissionWork.objects.filter(user=user, mission__subject=subject)
                       .values_list("mission_id", flat=True))
    # Include attempted missions even when no draft remains.
    mission_ids.extend(Attempt.objects.filter(user=user, mission__subject=subject)
                       .values_list("mission_id", flat=True))
    safe_pattern_codes = list(WrongPattern.objects.filter(subject=subject).exclude(
        code__in=WrongPattern.objects.exclude(subject=subject).values("code")
    ).values_list("code", flat=True))
    event_scope = (Q(event_type__in=("start_mission", "finish_mission"),
                     metadata__mission_id__in=mission_ids)
                   | Q(event_type__in=("start_exam", "finish_exam"),
                       metadata__exam_id__in=exam_ids)
                   | Q(event_type__in=("start_problem_set", "finish_problem_set"),
                       metadata__session_id__in=set_ids)
                   | Q(event_type__in=("start_pattern_training", "finish_pattern_training"),
                       metadata__pattern_code__in=safe_pattern_codes))
    UserEvent.objects.filter(user=user).filter(event_scope).delete()

    MissionWork.objects.filter(user=user, mission__subject=subject).delete()
    LearningStart.objects.filter(user=user, subject=subject).delete()
    ProblemSetSession.objects.filter(pk__in=set_ids, user=user).delete()
    ExamSession.objects.filter(pk__in=exam_ids, user=user).delete()
    PatternTrainingSession.objects.filter(user=user, wrong_pattern__subject=subject).delete()
    Attempt.objects.filter(user=user, mission__subject=subject).delete()
    DailyMission.objects.filter(user=user, mission__subject=subject).delete()
    ConfusionCard.objects.filter(user=user, subject=subject).delete()
    UserWeakness.objects.filter(user=user, subject=subject).delete()
    _refresh_streak_from_remaining_attempts(user)
    _remove_sessions(user.pk)


@transaction.atomic
def delete_member(user):
    member = get_user_model().objects.select_for_update().get(pk=user.pk)
    # These relations use SET_NULL, so explicitly remove personal content first.
    Inquiry.objects.filter(user_id=member.pk).delete()
    UserEvent.objects.filter(user_id=member.pk).delete()
    _remove_sessions(member.pk)
    # CASCADE includes learning records, profile, access and allauth credentials.
    member.delete()
