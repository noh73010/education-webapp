"""Explicit, user-scoped data removal; shared question content is never deleted."""

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from core.models import (
    Attempt, ConfusionCard, DailyMission, ExamSession, Inquiry,
    PatternTrainingSession, ProblemSetSession, UserEvent, UserStreak, UserWeakness,
    LearningStart, MissionWork,
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


@transaction.atomic
def delete_member(user):
    member = get_user_model().objects.select_for_update().get(pk=user.pk)
    # These relations use SET_NULL, so explicitly remove personal content first.
    Inquiry.objects.filter(user_id=member.pk).delete()
    UserEvent.objects.filter(user_id=member.pk).delete()
    _remove_sessions(member.pk)
    # CASCADE includes learning records, profile, access and allauth credentials.
    member.delete()
