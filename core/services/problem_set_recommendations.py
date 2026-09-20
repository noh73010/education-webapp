from django.db.models import Count, Exists, OuterRef, Q

from core.models import (
    Attempt,
    AttemptWrongPattern,
    Mission,
    ProblemSet,
    ProblemSetItem,
    ProblemSetSession,
)
from core.services.theory import THEORY_SET_PREFIX


def eligible_problem_sets(subject=None, *, include_theory=False):
    """Return sets whose metadata agrees with every eligible item."""
    items = ProblemSetItem.objects.filter(problem_set=OuterRef("pk"))
    queryset = (
        ProblemSet.objects.filter(is_active=True)
        .annotate(
            has_items=Exists(items),
            has_blocked_item=Exists(
                items.filter(
                    Q(mission__is_usable_for_set=False)
                    | Q(mission__review_status=Mission.REVIEW_CONFIRMED_ERROR)
                )
            ),
            has_chapter_mismatch=Exists(
                items.exclude(mission__chapter_code=OuterRef("skill_group"))
            ),
        )
        .filter(has_items=True, has_blocked_item=False, has_chapter_mismatch=False)
    )
    if not include_theory:
        queryset = queryset.exclude(title__startswith=THEORY_SET_PREFIX)
    if subject is not None:
        queryset = (
            queryset.annotate(
                has_other_subject=Exists(items.exclude(mission__subject=subject)),
            )
            .filter(has_other_subject=False, items__mission__subject=subject)
            .distinct()
        )
    return queryset


def get_recent_average_score(user, limit=5, subject=None):
    recent_sessions = ProblemSetSession.objects.filter(user=user, status="completed")
    if subject is not None:
        recent_sessions = recent_sessions.filter(items__mission__subject=subject).distinct()

    recent_sessions = recent_sessions.order_by("-started_at")[:limit]
    scores = [session.score for session in recent_sessions]

    if not scores:
        return None

    return round(sum(scores) / len(scores), 1)


def get_target_level(user, subject=None):
    recent_avg = get_recent_average_score(user, subject=subject)

    if recent_avg is None:
        return 1

    if recent_avg >= 85:
        return 3

    if recent_avg >= 60:
        return 2

    return 1


def get_weak_patterns(user, limit=3, subject=None):
    qs = AttemptWrongPattern.objects.filter(
        attempt__user=user, attempt__grading_valid=True
    )
    if subject is not None:
        qs = qs.filter(attempt__mission__subject=subject)

    rows = (
        qs
        .values(
            "wrong_pattern__code",
            "wrong_pattern__name",
            "wrong_pattern__skill",
        )
        .annotate(cnt=Count("id"))
        .order_by("-cnt")[:limit]
    )

    return list(rows)


def get_pattern_recommend_missions(user, weak_patterns, limit=5, subject=None):
    pattern_codes = [
        row["wrong_pattern__code"]
        for row in weak_patterns
        if row["wrong_pattern__code"]
    ]

    if not pattern_codes:
        return []

    attempted_correct_qs = Attempt.objects.valid_for_learning().filter(user=user, is_correct=True)
    if subject is not None:
        attempted_correct_qs = attempted_correct_qs.filter(mission__subject=subject)
    attempted_correct_ids = set(attempted_correct_qs.values_list("mission_id", flat=True))

    recent_wrong_qs = Attempt.objects.valid_for_learning().filter(
        user=user,
        is_correct=False,
        mission__variation_group__in=pattern_codes,
    )
    if subject is not None:
        recent_wrong_qs = recent_wrong_qs.filter(mission__subject=subject)
    recent_wrong_ids = set(
        recent_wrong_qs
        .order_by("-created_at")
        .values_list("mission_id", flat=True)[:20]
    )

    base_qs = (
        Mission.objects
        .filter(
            variation_group__in=pattern_codes,
            is_usable_for_set=True,
        )
        .exclude(review_status=Mission.REVIEW_CONFIRMED_ERROR)
        .exclude(id__in=attempted_correct_ids)
    )
    if subject is not None:
        base_qs = base_qs.filter(subject=subject)

    other_missions = list(
        base_qs
        .exclude(id__in=recent_wrong_ids)
        .order_by("level", "id")[:limit]
    )

    if len(other_missions) >= limit:
        return other_missions

    needed = limit - len(other_missions)
    retry_missions = list(
        base_qs
        .filter(id__in=recent_wrong_ids)
        .order_by("level", "id")[:needed]
    )

    return other_missions + retry_missions


def get_problem_set_recommendations(user, limit_today=3, limit_review=3, limit_weak=3, subject=None):
    active_sets = eligible_problem_sets(subject)

    target_level = get_target_level(user, subject=subject)

    attempted_sessions = ProblemSetSession.objects.filter(user=user)
    if subject is not None:
        attempted_sessions = attempted_sessions.filter(items__mission__subject=subject).distinct()
    attempted_set_ids = set(
        attempted_sessions
        .values_list("problem_set_id", flat=True)
        .distinct()
    )

    today_sets = list(
        active_sets
        .filter(level=target_level)
        .exclude(id__in=attempted_set_ids)
        .order_by("-created_at")[:limit_today]
    )

    if len(today_sets) < limit_today:
        needed = limit_today - len(today_sets)
        extra_sets = list(
            active_sets
            .filter(level=target_level)
            .filter(id__in=attempted_set_ids)
            .order_by("-created_at")[:needed]
        )
        today_sets.extend(extra_sets)

    if len(today_sets) < limit_today:
        needed = limit_today - len(today_sets)
        already_ids = [ps.id for ps in today_sets]
        fallback_sets = list(
            active_sets
            .exclude(id__in=already_ids)
            .order_by("level", "-created_at")[:needed]
        )
        today_sets.extend(fallback_sets)

    review_sessions = list(
        attempted_sessions
        .filter(status="completed")
        .select_related("problem_set")
        .order_by("score", "-started_at")[:20]
    )

    review_sets = []
    used_review_ids = set()

    for session in review_sessions:
        ps = session.problem_set
        if ps.is_active and ps.id not in used_review_ids:
            review_sets.append(ps)
            used_review_ids.add(ps.id)

        if len(review_sets) >= limit_review:
            break

    weak_attempt_qs = Attempt.objects.valid_for_learning().filter(user=user)
    if subject is not None:
        weak_attempt_qs = weak_attempt_qs.filter(mission__subject=subject)

    weak_skill_rows = (
        weak_attempt_qs
        .values("mission__skill")
        .annotate(
            total=Count("id"),
            wrong=Count("id", filter=Q(is_correct=False)),
        )
        .filter(wrong__gt=0)
        .order_by("-wrong", "-total")[:5]
    )

    weak_skills = [row["mission__skill"] for row in weak_skill_rows]

    weak_sets = []
    used_weak_ids = set()

    for skill in weak_skills:
        matched_sets = (
            active_sets
            .filter(skill_group=skill)
            .exclude(id__in=used_weak_ids)
            .order_by("level", "-created_at")
        )

        for ps in matched_sets:
            weak_sets.append(ps)
            used_weak_ids.add(ps.id)

            if len(weak_sets) >= limit_weak:
                break

        if len(weak_sets) >= limit_weak:
            break

    weak_patterns = get_weak_patterns(user, subject=subject)
    pattern_missions = get_pattern_recommend_missions(
        user=user,
        weak_patterns=weak_patterns,
        subject=subject,
    )

    return {
        "today_sets": today_sets,
        "review_sets": review_sets,
        "weak_sets": weak_sets,
        "weak_skills": weak_skills,
        "weak_patterns": weak_patterns,
        "pattern_missions": pattern_missions,
        "target_level": target_level,
        "recent_avg_score": get_recent_average_score(user, subject=subject),
    }
