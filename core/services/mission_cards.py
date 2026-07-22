from django.db.models import Count, OuterRef, Q, Subquery

from core.models import Attempt, Mission


def with_user_learning_state(queryset, user):
    """Attach reusable per-user learning statistics to a Mission queryset."""
    latest_attempt = (
        Attempt.objects
        .filter(user=user, mission=OuterRef("pk"))
        .order_by("-created_at")
    )

    return queryset.annotate(
        my_total=Count("attempt", filter=Q(attempt__user=user)),
        my_correct=Count(
            "attempt",
            filter=Q(attempt__user=user, attempt__is_correct=True),
        ),
        my_wrong=Count(
            "attempt",
            filter=Q(attempt__user=user, attempt__is_correct=False),
        ),
        my_last_is_correct=Subquery(latest_attempt.values("is_correct")[:1]),
        my_last_time=Subquery(latest_attempt.values("created_at")[:1]),
    )


def prepare_mission_cards(missions):
    """Add learner-facing labels without changing persisted Mission data."""
    for mission in missions:
        total = mission.my_total or 0
        correct = mission.my_correct or 0
        mission.my_accuracy = round((correct / total) * 100) if total else 0

        if total == 0:
            mission.my_last = "미풀이"
        elif mission.my_last_is_correct is True:
            mission.my_last = "정답"
        elif mission.my_last_is_correct is False:
            mission.my_last = "오답"
        else:
            mission.my_last = "미풀이"

    return missions


def load_mission_cards(missions, user):
    """Reload Mission objects with user state while preserving input order."""
    mission_ids = [mission.id for mission in missions]
    if not mission_ids:
        return []

    annotated = list(
        with_user_learning_state(
            Mission.objects.select_related("subject").filter(
                id__in=mission_ids,
            ),
            user,
        )
    )
    prepare_mission_cards(annotated)
    by_id = {mission.id: mission for mission in annotated}
    return [by_id[mission_id] for mission_id in mission_ids if mission_id in by_id]
