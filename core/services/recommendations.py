from datetime import date
import hashlib
from typing import List

from django.db.models import Count, Q

from core.models import Attempt, Mission, UserWeakness
from core.services.logistics_curriculum import LOGISTICS_CURRICULUM
from core.services.review_schedule import decorate_missions_with_review_state


def _chapter_progression_recommendations(
    candidates: list[Mission],
    level: int,
    stable_key,
    subject=None,
    priority_pattern_codes=None,
    recommendation_limit: int = 5,
) -> list[Mission] | None:
    """Build a textbook-like daily flow when chapter metadata is available.

    The first chapter with an unattempted question is the current chapter.
    New questions in that chapter come first, followed by another question from
    the same chapter, then one previously missed/weak question for review.
    """
    all_candidates = candidates
    priority_pattern_codes = set(priority_pattern_codes or [])
    level_candidates = [mission for mission in candidates if mission.level == level]
    if level_candidates:
        candidates = level_candidates

    chapter_candidates = [mission for mission in candidates if (mission.chapter_code or "").strip()]
    if not chapter_candidates:
        return None

    available_codes = {mission.chapter_code for mission in chapter_candidates}
    curriculum_codes = [
        code
        for course in LOGISTICS_CURRICULUM
        for code, _chapter_name in course["chapters"]
    ]
    ordered_codes = [code for code in curriculum_codes if code in available_codes]
    ordered_codes.extend(sorted(available_codes - set(ordered_codes)))

    missions_by_chapter = {
        code: [mission for mission in chapter_candidates if mission.chapter_code == code]
        for code in ordered_codes
    }
    current_code = next(
        (
            code
            for code in ordered_codes
            if any((mission.my_total or 0) == 0 for mission in missions_by_chapter[code])
        ),
        None,
    )

    def study_rank(mission: Mission, prefix: str):
        return (
            0 if (mission.my_total or 0) == 0 else 1,
            0 if mission.level == level else 1,
            abs((mission.level or level) - level),
            stable_key(prefix, mission.id),
        )

    selected: list[Mission] = []
    selected_ids: set[int] = set()

    def add(missions, limit: int):
        for mission in missions:
            if len(selected) >= limit:
                break
            if mission.id not in selected_ids:
                selected.append(mission)
                selected_ids.add(mission.id)

    if current_code is not None:
        current_missions = missions_by_chapter[current_code]
        current_untried = sorted(
            [mission for mission in current_missions if (mission.my_total or 0) == 0],
            key=lambda mission: study_rank(mission, "current-new"),
        )
        add(current_untried, min(3, recommendation_limit))

        current_remaining = sorted(
            [mission for mission in current_missions if mission.id not in selected_ids],
            key=lambda mission: study_rank(mission, "current-fill"),
        )
        add(current_remaining, min(4, recommendation_limit))

    chapter_position = {code: index for index, code in enumerate(ordered_codes)}
    current_position = chapter_position.get(current_code, 0)
    untried_fill = [
        mission
        for mission in candidates
        if mission.id not in selected_ids and (mission.my_total or 0) == 0
    ]
    untried_fill.sort(
        key=lambda mission: (
            (chapter_position.get(mission.chapter_code, len(ordered_codes)) - current_position)
            % max(len(ordered_codes), 1),
            stable_key("untried-chapter-fill", mission.id),
        )
    )
    add(untried_fill, min(4, recommendation_limit))

    weak_pool = [
        mission
        for mission in all_candidates
        if mission.id not in selected_ids
        and (mission.my_total or 0) > 0
        and (mission.my_last_is_correct is False or mission.my_accuracy < 70)
    ]
    weak_pool.sort(
        key=lambda mission: (
            0 if mission.variation_group in priority_pattern_codes else 1,
            0 if getattr(mission, "my_review_is_due", False) else 1,
            0 if mission.my_last_is_correct is False else 1,
            mission.my_accuracy,
            -(mission.my_total or 0),
            stable_key("weak-review", mission.id),
        )
    )
    if weak_pool and len(selected) < recommendation_limit:
        add(weak_pool, min(len(selected) + 1, recommendation_limit))

    remaining = [mission for mission in candidates if mission.id not in selected_ids]
    remaining.sort(
        key=lambda mission: (
            0 if (mission.my_total or 0) == 0 else 1,
            (chapter_position.get(mission.chapter_code, len(ordered_codes)) - current_position)
            % max(len(ordered_codes), 1),
            0 if mission.level == level else 1,
            stable_key("chapter-fill", mission.id),
        )
    )
    add(remaining, recommendation_limit)
    return selected[:recommendation_limit]


def get_user_level(user, subject=None):
    attempt_qs = Attempt.objects.valid_for_learning().filter(user=user)
    if subject is not None:
        attempt_qs = attempt_qs.filter(mission__subject=subject)
    attempts = list(attempt_qs.order_by("-created_at")[:20])

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


def get_weak_skills(user, limit=3, subject=None):
    attempt_qs = Attempt.objects.valid_for_learning().filter(user=user)
    if subject is not None:
        attempt_qs = attempt_qs.filter(mission__subject=subject)
    rows = (
        attempt_qs
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
    subject=None,
    recommendation_limit: int = 5,
) -> tuple[list[Mission], str]:
    """
    annotate된 qs를 받아서
    - 오늘 고정 추천
    - 약점 스킬 기반
    - 미풀이3 + 약점2
    - extra_seed가 있으면 같은 날에도 다른 추천 생성 가능
    """
    recommendation_limit = max(1, min(int(recommendation_limit), 10))
    annotated_qs = annotated_qs.filter(is_usable_for_set=True).exclude(
        review_status=Mission.REVIEW_CONFIRMED_ERROR,
    )

    today = date.today().isoformat()
    seed = f"{user.id}:{today}:{extra_seed}"

    def stable_key(prefix: str, mission_id: int) -> str:
        s = f"{seed}:{prefix}:{mission_id}"
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    level = get_user_level(user, subject=subject)
    weak_skills = get_weak_skills(user, subject=subject)
    priority_pattern_codes = []
    if subject is not None:
        priority_pattern_codes = list(
            UserWeakness.objects.filter(
                user=user,
                subject=subject,
                status__in=[
                    UserWeakness.STATUS_REVIEW_DUE,
                    UserWeakness.STATUS_RELAPSED,
                    UserWeakness.STATUS_ACTIVE,
                    UserWeakness.STATUS_TRAINING,
                ],
            )
            .order_by("-severity", "next_review_at")
            .values_list("wrong_pattern__code", flat=True)
        )

    chapter_candidates = list(annotated_qs[:candidate_limit])
    decorate_missions_for_display(chapter_candidates)
    decorate_missions_with_review_state(user, chapter_candidates)
    chapter_selection = _chapter_progression_recommendations(
        chapter_candidates,
        level,
        stable_key,
        subject=subject,
        priority_pattern_codes=priority_pattern_codes,
        recommendation_limit=recommendation_limit,
    )
    if chapter_selection is not None:
        return chapter_selection, today

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
    decorate_missions_with_review_state(user, candidates)

    # -------- 약점 스킬 계산 --------
    skill_attempt_qs = Attempt.objects.valid_for_learning().filter(user=user)
    if subject is not None:
        skill_attempt_qs = skill_attempt_qs.filter(mission__subject=subject)
    skill_rows = (
        skill_attempt_qs
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
        pattern_flag = 0 if m.variation_group in priority_pattern_codes else 1
        review_due_flag = 0 if getattr(m, "my_review_is_due", False) else 1
        weak_skill_flag = 0 if m.skill in weak_skills else 1
        recent_wrong_flag = 0 if m.my_last == "오답" else 1
        acc = m.my_accuracy
        total = m.my_total or 0
        return (pattern_flag, review_due_flag, weak_skill_flag, recent_wrong_flag, acc, total, stable_key("weak", m.id))

    weak_pool.sort(key=weak_rank)
    weak_pick = weak_pool[:2]

    selected = untried_pick + weak_pick
    selected_ids = {mission.id for mission in selected}
    remaining = [mission for mission in candidates if mission.id not in selected_ids]
    remaining.sort(key=lambda mission: stable_key("fill", mission.id))

    return (selected + remaining)[:recommendation_limit], today

def get_recommendations_from_annotated_qs(
    user,
    annotated_qs,
    candidate_limit: int = 300,
    extra_seed: str = "",
    subject=None,
    recommendation_limit: int = 5,
):
    """
    views.py / service가 기대하는 wrapper.
    """
    return get_recommended_missions(
        user,
        annotated_qs,
        candidate_limit=candidate_limit,
        extra_seed=extra_seed,
        subject=subject,
        recommendation_limit=recommendation_limit,
    )
