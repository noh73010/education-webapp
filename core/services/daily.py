# core/services/daily.py

from django.db.models import Case, When, IntegerField
from django.utils import timezone

from core.models import DailyMission, Attempt
from core.services.recommendations import get_recommendations_from_annotated_qs


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
        DailyMission.objects.filter(user=user, date=today_date).delete()

    existing_qs = DailyMission.objects.filter(
        user=user,
        date=today_date,
        mission__is_usable_for_set=True,
    )
    if subject is not None:
        existing_qs = existing_qs.filter(mission__subject=subject)

    existing_ids = list(existing_qs.values_list("mission_id", flat=True))

    if len(existing_ids) >= 5:
        recommended_ids = existing_ids
        today_str = str(today_date)
    else:
        extra_seed = ""
        if reset_daily:
            extra_seed = timezone.now().strftime("%H%M%S%f")

        recommended_raw, today_str = get_recommendations_from_annotated_qs(
            user,
            annotated_qs,
            extra_seed=extra_seed,
        )
        recommended_ids = [m.id for m in recommended_raw]

        DailyMission.objects.bulk_create(
            [
                DailyMission(user=user, date=today_date, mission_id=mid)
                for mid in recommended_ids
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
    daily_done = done_qs.values("mission_id").distinct().count()

    return {
        "date": today_date,
        "total": daily_total,
        "done": daily_done,
        "remain": max(daily_total - daily_done, 0),
        "pct": round((daily_done / daily_total) * 100, 1) if daily_total else 0.0,
    }
