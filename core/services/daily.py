# core/services/daily.py

from django.db.models import Case, When, IntegerField
from django.utils import timezone

from core.models import DailyMission, Attempt
from core.services.recommendations import get_recommendations_from_annotated_qs
from core.services.review_schedule import decorate_missions_with_review_state


ESTIMATED_MINUTES_PER_QUESTION = 2


def build_daily_study_plan(user, missions, *, done_ids=None, today=None):
    """Explain today's fixed recommendations in learner-facing terms."""
    missions = decorate_missions_with_review_state(user, missions, today=today)
    done_ids = set(done_ids or [])
    categories = {
        "new": {"label": "새 학습", "count": 0},
        "review": {"label": "오답 복습", "count": 0},
        "weak": {"label": "약점 보완", "count": 0},
        "reinforce": {"label": "실력 유지", "count": 0},
    }

    for mission in missions:
        total = getattr(mission, "my_total", 0) or 0
        correct = getattr(mission, "my_correct", 0) or 0
        accuracy = round((correct / total) * 100) if total else 0
        if total == 0:
            category = "new"
            chapter = mission.chapter_name or mission.course or "현재 범위"
            reason = f"아직 풀지 않은 {chapter} 문제"
        elif getattr(mission, "my_review_is_due", False):
            category = "review"
            reason = f"복습할 시점이 된 {mission.my_review_label} 문제"
        elif mission.my_last_is_correct is False or accuracy < 70:
            category = "weak"
            reason = "최근 오답 또는 낮은 정답률을 보완할 문제"
        else:
            category = "reinforce"
            reason = "학습한 내용을 잊지 않도록 확인할 문제"

        mission.daily_category = category
        mission.daily_category_label = categories[category]["label"]
        mission.daily_reason = reason
        categories[category]["count"] += 1

    total = len(missions)
    completed = sum(1 for mission in missions if mission.id in done_ids)
    remaining = max(total - completed, 0)
    return {
        "categories": [row for row in categories.values() if row["count"]],
        "total": total,
        "completed": completed,
        "remaining": remaining,
        "estimated_minutes": remaining * ESTIMATED_MINUTES_PER_QUESTION,
        "total_estimated_minutes": total * ESTIMATED_MINUTES_PER_QUESTION,
    }


def get_or_create_daily_recommendations(user, annotated_qs, reset_daily=False, subject=None):
    """
    오늘의 데일리 추천 5문제를 반환한다.
    - reset_daily=True 이면 기존 추천 삭제 후 재생성
    - reset_daily=False 이면 기존 추천 재사용
    반환:
        recommended: annotate가 유지된 mission 리스트
        today_str: 오늘 날짜 문자열
        today_date: 오늘 date 객체
    """
    today_date = timezone.localdate()

    if reset_daily:
        reset_qs = DailyMission.objects.filter(user=user, date=today_date)
        if subject is not None:
            reset_qs = reset_qs.filter(mission__subject=subject)
        reset_qs.delete()

    existing_qs = DailyMission.objects.filter(
        user=user,
        date=today_date,
        mission__is_usable_for_set=True,
    )
    if subject is not None:
        existing_qs = existing_qs.filter(mission__subject=subject)

    existing_ids = list(
        existing_qs.order_by("id").values_list("mission_id", flat=True)[:5]
    )

    if len(existing_ids) >= 5:
        recommended_ids = existing_ids[:5]
        today_str = str(today_date)
    else:
        extra_seed = ""
        if reset_daily:
            extra_seed = timezone.now().strftime("%H%M%S%f")

        recommended_raw, today_str = get_recommendations_from_annotated_qs(
            user,
            annotated_qs,
            extra_seed=extra_seed,
            subject=subject,
        )
        recommended_ids = list(existing_ids)
        for mission in recommended_raw:
            if mission.id not in recommended_ids:
                recommended_ids.append(mission.id)
            if len(recommended_ids) >= 5:
                break

        DailyMission.objects.bulk_create(
            [
                DailyMission(user=user, date=today_date, mission_id=mid)
                for mid in recommended_ids
                if mid not in existing_ids
            ],
            ignore_conflicts=True,
        )

    if not recommended_ids:
        return [], str(today_date), today_date

    order_case = Case(
        *[When(id=mid, then=pos) for pos, mid in enumerate(recommended_ids)],
        output_field=IntegerField(),
    )

    recommended = list(
        annotated_qs
        .filter(id__in=recommended_ids, is_usable_for_set=True)
        .order_by(order_case)
    )

    return recommended, today_str, today_date


def get_daily_done_ids(user, today_date, subject=None):
    """
    오늘 데일리 미션 중 이미 푼 mission id 집합 반환
    """
    qs = Attempt.objects.filter(user=user, daily_date=today_date)
    if subject is not None:
        qs = qs.filter(mission__subject=subject)
    return set(qs.values_list("mission_id", flat=True))


def get_daily_progress(user, today_date, subject=None):
    """
    오늘 데일리 진행률 반환
    """
    daily_qs = DailyMission.objects.filter(
        user=user,
        date=today_date,
        mission__is_usable_for_set=True,
    )
    if subject is not None:
        daily_qs = daily_qs.filter(mission__subject=subject)
    daily_total = daily_qs.count()

    done_qs = Attempt.objects.filter(
        user=user,
        daily_date=today_date,
        mission__is_usable_for_set=True,
    )
    if subject is not None:
        done_qs = done_qs.filter(mission__subject=subject)
    latest_results = {}
    for attempt in done_qs.order_by("mission_id", "-created_at"):
        latest_results.setdefault(attempt.mission_id, attempt.is_correct)
    daily_done = len(latest_results)
    daily_correct = sum(1 for is_correct in latest_results.values() if is_correct)
    daily_wrong = daily_done - daily_correct

    return {
        "date": today_date,
        "total": daily_total,
        "done": daily_done,
        "remain": max(daily_total - daily_done, 0),
        "pct": round((daily_done / daily_total) * 100, 1) if daily_total else 0.0,
        "correct": daily_correct,
        "wrong": daily_wrong,
        "accuracy": round((daily_correct / daily_done) * 100) if daily_done else 0,
        "estimated_minutes": max(daily_total - daily_done, 0) * ESTIMATED_MINUTES_PER_QUESTION,
    }
