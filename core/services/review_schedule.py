from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.db.models import F, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

from core.models import Attempt


RECENT_ATTEMPT_LIMIT = 3


def get_mission_review_states(user, mission_ids, *, today=None):
    """Derive review timing from Attempt history without duplicating state."""
    mission_ids = list(dict.fromkeys(mission_ids))
    if not mission_ids:
        return {}

    today = today or timezone.localdate()
    recent_attempts = (
        Attempt.objects.valid_for_learning()
        .filter(user=user, mission_id__in=mission_ids)
        .annotate(
            recent_rank=Window(
                expression=RowNumber(),
                partition_by=[F("mission_id")],
                order_by=F("created_at").desc(),
            )
        )
        .filter(recent_rank__lte=RECENT_ATTEMPT_LIMIT)
        .order_by("mission_id", "-created_at")
    )

    attempts_by_mission = defaultdict(list)
    for attempt in recent_attempts:
        attempts_by_mission[attempt.mission_id].append(attempt)

    return {
        mission_id: _build_review_state(attempts, today=today)
        for mission_id, attempts in attempts_by_mission.items()
    }


def _build_review_state(attempts, *, today):
    latest = attempts[0]
    latest_date = timezone.localtime(latest.created_at).date()

    if latest.is_correct and latest.confidence_level != Attempt.CONFIDENCE_CERTAIN:
        due_date = latest_date + timedelta(days=1)
        return {
            "status": "uncertain",
            "label": "확신 보강",
            "due_date": due_date,
            "is_due": due_date <= today,
            "consecutive_correct": 0,
        }

    if not latest.is_correct:
        due_date = latest_date + timedelta(days=1)
        return {
            "status": "wrong",
            "label": "오답 복습",
            "due_date": due_date,
            "is_due": due_date <= today,
            "consecutive_correct": 0,
        }

    consecutive_correct = 0
    has_recent_wrong = False
    certain_correct_dates = []
    for attempt in attempts:
        if attempt.is_correct and attempt.confidence_level == Attempt.CONFIDENCE_CERTAIN:
            consecutive_correct += 1
            certain_correct_dates.append(timezone.localtime(attempt.created_at).date())
            continue
        has_recent_wrong = True
        break

    has_delayed_confirmation = (
        consecutive_correct >= 2
        and (max(certain_correct_dates) - min(certain_correct_dates)).days >= 3
    )
    if has_delayed_confirmation:
        return {
            "status": "mastered",
            "label": "숙련",
            "due_date": None,
            "is_due": False,
            "consecutive_correct": consecutive_correct,
        }

    due_date = latest_date + timedelta(days=3)
    return {
        "status": "confirm",
        "label": "정착 복습",
        "due_date": due_date,
        "is_due": due_date <= today,
        "consecutive_correct": consecutive_correct,
    }


def decorate_missions_with_review_state(user, missions, *, today=None):
    missions = list(missions)
    states = get_mission_review_states(
        user,
        [mission.id for mission in missions],
        today=today,
    )
    for mission in missions:
        state = states.get(mission.id, {})
        mission.my_review_status = state.get("status", "new")
        mission.my_review_label = state.get("label", "")
        mission.my_review_due_date = state.get("due_date")
        mission.my_review_is_due = state.get("is_due", False)
    return missions
