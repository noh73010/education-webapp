from datetime import date
import hashlib
from typing import List

from django.db.models import Count, Q

from core.models import Attempt, Mission


def get_user_level(user):
    attempts = list(
        Attempt.objects
        .filter(user=user)
        .order_by("-created_at")[:20]
    )

    if not attempts:
        return 1

    correct = sum(1 for a in attempts if a.is_correct)
    rate = correct / len(attempts)

    if rate >= 0.8:
        return 3
    elif rate <= 0.5:
        return 1
    else:
        return 2


def get_weak_skills(user, limit=3):
    rows = (
        Attempt.objects
        .filter(user=user)
        .values("mission__skill")
        .annotate(
            total=Count("id"),
            wrong=Count("id", filter=Q(is_correct=False)),
        )
        .filter(wrong__gt=0)
        .order_by("-wrong", "-total")[:limit]
    )

    return [row["mission__skill"] for row in rows]


def decorate_missions_for_display(missions: List[Mission]) -> None:
    """
    mission 객체에 my_accuracy / my_last 붙이기
    """
    for m in missions:
        total = getattr(m, "my_total", 0) or 0
        correct = getattr(m, "my_correct", 0) or 0

        m.my_accuracy = round((correct / total) * 100, 1) if total else 0.0

        if total == 0:
            m.my_last = "미풀이"
        else:
            if m.my_last_is_correct is True:
                m.my_last = "정답"
            elif m.my_last_is_correct is False:
                m.my_last = "오답"
            else:
                m.my_last = "미풀이"


def get_recommended_missions(
    user,
    annotated_qs,
    candidate_limit: int = 300,
    extra_seed: str = "",
) -> tuple[list[Mission], str]:
    """
    annotate된 qs를 받아서
    - 오늘 고정 추천
    - 약점 스킬 기반
    - 미풀이3 + 약점2
    - extra_seed가 있으면 같은 날에도 다른 추천 생성 가능
    """
    today = date.today().isoformat()
    seed = f"{user.id}:{today}:{extra_seed}"

    def stable_key(prefix: str, mission_id: int) -> str:
        s = f"{seed}:{prefix}:{mission_id}"
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    level = get_user_level(user)
    weak_skills = get_weak_skills(user)

    base_qs = annotated_qs.filter(level=level)

    if weak_skills:
        weak_qs = base_qs.filter(skill__in=weak_skills)
        other_qs = base_qs.exclude(skill__in=weak_skills)

        candidates = list(weak_qs[: int(candidate_limit * 0.7)])
        candidates += list(other_qs[: candidate_limit - len(candidates)])
    else:
        candidates = list(base_qs[:candidate_limit])

    if not candidates:
        candidates = list(annotated_qs[:candidate_limit])
    decorate_missions_for_display(candidates)

    # -------- 약점 스킬 계산 --------
    skill_rows = (
        Attempt.objects
        .filter(user=user)
        .values("mission__skill")
        .annotate(
            total=Count("id"),
            correct=Count("id", filter=Q(is_correct=True)),
        )
    )

    skill_acc = []
    for r in skill_rows:
        total = r["total"] or 0
        correct = r["correct"] or 0
        acc = (correct / total) if total else 1.0
        skill_acc.append((r["mission__skill"], acc, total))

    strong_data = [x for x in skill_acc if x[2] >= 3]
    weak_skill_candidates = strong_data if strong_data else skill_acc
    weak_skill_candidates.sort(key=lambda x: (x[1], -x[2]))
    weak_skills = [s for (s, acc, total) in weak_skill_candidates[:3]]

    # -------- 미풀이 3 --------
    untried = [m for m in candidates if (m.my_total or 0) == 0]
    untried_weak = [m for m in untried if m.skill in weak_skills]
    untried_other = [m for m in untried if m.skill not in weak_skills]

    untried_weak.sort(key=lambda m: stable_key("untried_weak", m.id))
    untried_other.sort(key=lambda m: stable_key("untried_other", m.id))

    untried_pick = (untried_weak + untried_other)[:3]

    # -------- 약점 2 --------
    weak_pool = [m for m in candidates if (m.my_total or 0) > 0 and m not in untried_pick]

    def weak_rank(m):
        weak_skill_flag = 0 if m.skill in weak_skills else 1
        recent_wrong_flag = 0 if m.my_last == "오답" else 1
        acc = m.my_accuracy
        total = m.my_total or 0
        return (weak_skill_flag, recent_wrong_flag, acc, total, stable_key("weak", m.id))

    weak_pool.sort(key=weak_rank)
    weak_pick = weak_pool[:2]

    return untried_pick + weak_pick, today

def get_recommendations_from_annotated_qs(
    user,
    annotated_qs,
    candidate_limit: int = 300,
    extra_seed: str = "",
):
    """
    views.py / service가 기대하는 wrapper.
    """
    return get_recommended_missions(
        user,
        annotated_qs,
        candidate_limit=candidate_limit,
        extra_seed=extra_seed,
    )