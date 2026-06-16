# core/views/wrong_notes.py

from datetime import timedelta

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.utils import timezone

from core.models import Mission, Attempt, AttemptWrongReason
from core.services.access import get_user_access


@login_required
def wrong_notes(request):
    # --- 필터 파라미터 ---
    mode = request.GET.get("mode", "open").strip()   # open(미해결) / all(전체)
    days = request.GET.get("days", "all").strip()    # all / 7 / 30
    skill = request.GET.get("skill", "").strip()     # '' or skill명

    since = None
    now = timezone.now()
    if days == "7":
        since = now - timedelta(days=7)
    elif days == "30":
        since = now - timedelta(days=30)

    # 1) 사용자 Attempt 전체(기간 필터는 여기서 적용)
    base_qs = Attempt.objects.filter(user=request.user)
    if since is not None:
        base_qs = base_qs.filter(created_at__gte=since)

    # 2) 미션별 최신 attempt 뽑기 (기간 필터가 적용된 범위 안에서)
    latest_per_mission = (
        base_qs
        .values("mission_id")
        .annotate(latest_time=Max("created_at"))
        .order_by("-latest_time")
    )

    # 3) 최신 attempt 객체들
    latest_attempts = []
    for item in latest_per_mission:
        a = (
            base_qs
            .filter(mission_id=item["mission_id"], created_at=item["latest_time"])
            .select_related("mission")
            .first()
        )
        if a:
            latest_attempts.append(a)

    # 4) mode 필터
    if mode == "open":
        final_attempts = [a for a in latest_attempts if not a.is_correct]
    else:
        final_attempts = latest_attempts  # all

    # 5) skill 필터
    if skill:
        final_attempts = [a for a in final_attempts if a.mission.skill == skill]

    # 6) 오답원인 묶기 (오답인 것만 원인이 있으니 오답 attempt만 골라서 조회)
    wrong_only = [a for a in final_attempts if not a.is_correct]

    awr_qs = (
        AttemptWrongReason.objects
        .filter(attempt__in=wrong_only)
        .select_related("wrong_reason")
    )

    reasons_by_attempt_id = {}
    for awr in awr_qs:
        reasons_by_attempt_id.setdefault(awr.attempt_id, []).append(awr.wrong_reason.name)

    wrong_items = []
    for a in final_attempts:
        wrong_items.append({
            "attempt": a,
            "reasons": reasons_by_attempt_id.get(a.id, []),  # 정답이면 빈 리스트
        })
    access = get_user_access(request.user)

    is_limited = False
    if not access.is_premium and len(wrong_items) > 5:
        wrong_items = wrong_items[:5]
        is_limited = True

    # 7) skill 드롭다운용 목록
    skill_choices = (
        Mission.objects
        .values_list("skill", flat=True)
        .distinct()
        .order_by("skill")
    )

    return render(request, "core/wrong_notes.html", {
        "wrong_items": wrong_items,
        "mode": mode,
        "days": days,
        "since": since,
        "skill": skill,
        "skill_choices": skill_choices,
        "is_premium": access.is_premium,
        "is_limited": is_limited,
    })