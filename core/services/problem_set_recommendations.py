from django.db.models import Count, Q

from core.models import ProblemSet, ProblemSetSession, Attempt, AttemptWrongPattern, Mission


def get_recent_average_score(user, limit=5):
    recent_sessions = (
        ProblemSetSession.objects
        .filter(user=user, status="completed")
        .order_by("-started_at")[:limit]
    )

    scores = [session.score for session in recent_sessions]

    if not scores:
        return None

    return round(sum(scores) / len(scores), 1)


def get_target_level(user):
    recent_avg = get_recent_average_score(user)

    if recent_avg is None:
        return 1

    if recent_avg >= 85:
        return 3

    if recent_avg >= 60:
        return 2

    return 1

def get_weak_patterns(user, limit=3):
    rows = (
        AttemptWrongPattern.objects
        .filter(attempt__user=user)
        .values(
            "wrong_pattern__code",
            "wrong_pattern__name",
            "wrong_pattern__skill",
        )
        .annotate(cnt=Count("id"))
        .order_by("-cnt")[:limit]
    )

    return list(rows)


def get_pattern_recommend_missions(user, weak_patterns, limit=5):
    """
    반복 오답 패턴을 기준으로 유사 문제를 추천한다.

    기준:
    - weak_patterns의 code를 variation_group으로 사용
    - 이미 정답 처리한 문제는 제외
    - 최근 틀린 문제 자체는 뒤로 밀고, 같은 그룹의 다른 문제를 우선 추천
    """
    pattern_codes = [
        row["wrong_pattern__code"]
        for row in weak_patterns
        if row["wrong_pattern__code"]
    ]

    if not pattern_codes:
        return []

    attempted_correct_ids = set(
        Attempt.objects
        .filter(user=user, is_correct=True)
        .values_list("mission_id", flat=True)
    )

    recent_wrong_ids = set(
        Attempt.objects
        .filter(
            user=user,
            is_correct=False,
            mission__variation_group__in=pattern_codes,
        )
        .order_by("-created_at")
        .values_list("mission_id", flat=True)[:20]
    )

    base_qs = (
        Mission.objects
        .filter(
            variation_group__in=pattern_codes,
            is_usable_for_set=True,
        )
        .exclude(id__in=attempted_correct_ids)
    )

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


def get_problem_set_recommendations(user, limit_today=3, limit_review=3, limit_weak=3):
    active_sets = (
        ProblemSet.objects
        .filter(is_active=True)
        .annotate(
            unusable_item_count=Count(
                "items",
                filter=Q(items__mission__is_usable_for_set=False),
            )
        )
        .filter(unusable_item_count=0)
    )

    target_level = get_target_level(user)

    attempted_set_ids = set(
        ProblemSetSession.objects
        .filter(user=user)
        .values_list("problem_set_id", flat=True)
        .distinct()
    )

    # 1) 오늘 할 세트: 목표 난이도 + 아직 안 푼 세트 우선
    today_sets = list(
        active_sets
        .filter(level=target_level)
        .exclude(id__in=attempted_set_ids)
        .order_by("-created_at")[:limit_today]
    )

    # 부족하면 같은 난이도에서 이미 푼 세트도 보충
    if len(today_sets) < limit_today:
        needed = limit_today - len(today_sets)
        extra_sets = list(
            active_sets
            .filter(level=target_level)
            .filter(id__in=attempted_set_ids)
            .order_by("-created_at")[:needed]
        )
        today_sets.extend(extra_sets)

    # 그래도 부족하면 전체 활성 세트에서 보충
    if len(today_sets) < limit_today:
        needed = limit_today - len(today_sets)
        already_ids = [ps.id for ps in today_sets]

        fallback_sets = list(
            active_sets
            .exclude(id__in=already_ids)
            .order_by("level", "-created_at")[:needed]
        )
        today_sets.extend(fallback_sets)

    # 2) 복습 추천 세트: 최근 완료 기록 중 낮은 점수 우선
    review_sessions = list(
        ProblemSetSession.objects
        .filter(user=user, status="completed")
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

    # 3) 약점 기반 추천 세트: 최근 오답이 많은 skill 기준
    weak_skill_rows = (
        Attempt.objects
        .filter(user=user)
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
    weak_patterns = get_weak_patterns(user)
    pattern_missions = get_pattern_recommend_missions(
        user=user,
        weak_patterns=weak_patterns,
    )           
    return {
        "today_sets": today_sets,
        "review_sets": review_sets,
        "weak_sets": weak_sets,
        "weak_skills": weak_skills,
        "weak_patterns": weak_patterns,
        "pattern_missions": pattern_missions,
        "target_level": target_level,
        "recent_avg_score": get_recent_average_score(user),
    }
