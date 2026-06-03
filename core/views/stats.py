# core/views/stats.py

from datetime import timedelta

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, OuterRef, Subquery
from django.utils import timezone

from core.models import (
    Mission,
    Attempt,
    AttemptWrongReason,
    AttemptWrongPattern,
    PatternTrainingSession,
)
SKILL_LABELS = {
    "COUNT": "COUNT 함수",
    "IF": "IF 함수",
    "VLOOKUP": "VLOOKUP 함수",
    "scenario": "시나리오 적용",
    "chart_axis": "차트 축 설정",
    "chart_border": "차트 테두리",
    "chart_color": "차트 색상 변경",
    "chart_format": "차트 서식",
    "chart_label": "차트 데이터 레이블",
    "advanced_filter_or": "고급필터 OR조건",
    "averageif": "AVERAGEIF 함수",
    "averageif_roundup": "AVERAGEIF + ROUNDUP",
    "basic_input": "기본 입력",
    "basic_sum": "SUM 기본 합계",
    "max": "MAX 함수",
}
SKILL_CATEGORY = {
    "COUNT": "함수",
    "IF": "함수",
    "VLOOKUP": "함수",
    "MAX": "함수",
    "MIN": "함수",
    "AVERAGE": "함수",
    "SUMIF": "함수",
    "SUMIFS": "함수",
    "COUNTIFS": "함수",
    "AVERAGEIF": "함수",

    "chart_axis": "차트",
    "chart_style": "차트",
    "chart_type": "차트",
    "chart_color": "차트",
    "chart_label": "차트",

    "pivot_basic": "피벗테이블",
    "pivot_average": "피벗테이블",

    "macro_basic": "매크로",
    "macro_sum": "매크로",

    "scenario": "시나리오",

    "advanced_filter_or": "고급필터",
    "advanced_filter_eval": "고급필터",
}

@login_required
def stats(request):
    # 기간 필터: all / 7 / 30 (기본 all)
    period = request.GET.get("period", "all").strip()
    since = None

    now = timezone.now()
    if period == "7":
        since = now - timedelta(days=7)
    elif period == "30":
        since = now - timedelta(days=30)

    # ---------------------------
    # A) 누적 통계(기간 필터 반영)
    # ---------------------------
    attempt_qs = Attempt.objects.filter(user=request.user)
    awr_qs = AttemptWrongReason.objects.filter(attempt__user=request.user)

    if since is not None:
        attempt_qs = attempt_qs.filter(created_at__gte=since)
        awr_qs = awr_qs.filter(attempt__created_at__gte=since)

    # 1) 스킬별 정답/오답 + 정답률
    skill_rows = (
        attempt_qs
        .values("mission__skill")
        .annotate(
            total=Count("id"),
            correct=Count("id", filter=Q(is_correct=True)),
            wrong=Count("id", filter=Q(is_correct=False)),
        )
        .filter(total__gte=2)
        .order_by("-total", "mission__skill")
    )

    skill_rows = list(skill_rows)
    for r in skill_rows:
        total = r["total"] or 0
        correct = r["correct"] or 0

        r["accuracy"] = round((correct / total) * 100, 1) if total else 0.0

        raw_skill = r["mission__skill"]

        r["skill_label"] = SKILL_LABELS.get(
            raw_skill,
            raw_skill,
        )
        r["category"] = SKILL_CATEGORY.get(
            raw_skill,
            "기타",
        )

    

    # 2) 오답원인 TOP 5
    wrong_reason_rows = (
        awr_qs
        .values("wrong_reason__name")
        .annotate(cnt=Count("id"))
        .order_by("-cnt")[:5]
    )
    
    wrong_pattern_rows = (
        AttemptWrongPattern.objects
        .filter(attempt__user=request.user)
        .values(
            "wrong_pattern__skill",
            "wrong_pattern__name",
            "wrong_pattern__code",
        )
        .annotate(cnt=Count("id"))
        .order_by("-cnt")[:10]
    )
    top_wrong_pattern = wrong_pattern_rows[0] if wrong_pattern_rows else None
    pattern_training_rows = (
    PatternTrainingSession.objects
    .filter(user=request.user)
    .select_related("wrong_pattern")
    .order_by("-created_at")[:10]
    )


    # 3) 최근 풀이 20개
    recent_attempts = (
        attempt_qs
        .select_related("mission")
        .order_by("-created_at")[:20]
    )

    # 전체 요약
    summary = attempt_qs.aggregate(
        total=Count("id"),
        correct=Count("id", filter=Q(is_correct=True)),
        wrong=Count("id", filter=Q(is_correct=False)),
    )
    total = summary["total"] or 0
    correct = summary["correct"] or 0
    summary["accuracy"] = round((correct / total) * 100, 1) if total else 0.0

    # -----------------------------------------
    # B) 현재 상태 통계 (미션별 최신 풀이 기준)
    # -----------------------------------------
    latest_attempt_qs = (
        Attempt.objects
        .filter(user=request.user, mission=OuterRef("pk"))
        .order_by("-created_at")
    )

    missions_with_last = (
        Mission.objects
        .all()
        .annotate(
            last_time=Subquery(latest_attempt_qs.values("created_at")[:1]),
            last_is_correct=Subquery(latest_attempt_qs.values("is_correct")[:1]),
        )
    )

    current_summary = {
        "missions_total": missions_with_last.count(),
        "attempted": missions_with_last.filter(last_time__isnull=False).count(),
        "solved": missions_with_last.filter(last_is_correct=True).count(),
        "open": missions_with_last.filter(last_is_correct=False).count(),
    }
    attempted = current_summary["attempted"] or 0
    solved = current_summary["solved"] or 0
    current_summary["solve_rate"] = round((solved / attempted) * 100, 1) if attempted else 0.0

    # 스킬별 현재 상태
    skill_current_rows = (
        missions_with_last
        .values("skill")
        .annotate(
            attempted=Count("id", filter=Q(last_time__isnull=False)),
            solved=Count("id", filter=Q(last_is_correct=True)),
            open=Count("id", filter=Q(last_is_correct=False)),
        )
        .filter(attempted__gte=2)
        .order_by("-attempted", "skill")
    )

    skill_current_rows = list(skill_current_rows)
    for r in skill_current_rows:
        a = r["attempted"] or 0
        s = r["solved"] or 0

        r["solve_rate"] = round((s / a) * 100, 1) if a else 0.0

        raw_skill = r["skill"]

        r["skill_label"] = SKILL_LABELS.get(
            raw_skill,
            raw_skill,
        )

    return render(request, "core/stats.html", {
        "period": period,
        "since": since,
        "summary": summary,
        "skill_rows": skill_rows,
        "wrong_reason_rows": wrong_reason_rows,
        "wrong_pattern_rows": wrong_pattern_rows,
        "top_wrong_pattern": top_wrong_pattern,
        "pattern_training_rows": pattern_training_rows,
        "recent_attempts": recent_attempts,
        "current_summary": current_summary,
        "skill_current_rows": skill_current_rows,
    })