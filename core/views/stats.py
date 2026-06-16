# core/views/stats.py

from datetime import timedelta

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, OuterRef, Subquery
from django.utils import timezone
from core.services.skill_labels import get_skill_label
from core.services.skill_categories import get_skill_category

from core.models import (
    Mission,
    Attempt,
    AttemptWrongReason,
    AttemptWrongPattern,
    PatternTrainingSession,
)

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

        r["skill_label"] = get_skill_label(raw_skill)
        r["category"] = get_skill_category(raw_skill)

    

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
    wrong_pattern_rows = list(wrong_pattern_rows)

    for row in wrong_pattern_rows:
        row["wrong_pattern_skill_label"] = get_skill_label(
            row["wrong_pattern__skill"]
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
        r["skill_label"] = get_skill_label(raw_skill)
        r["category"] = get_skill_category(raw_skill)

    learning_type_rows = (
        missions_with_last
        .values("skill", "learning_type")
        .annotate(
            total=Count("id"),
            attempted=Count("id", filter=Q(last_time__isnull=False)),
            solved=Count("id", filter=Q(last_is_correct=True)),
            open=Count("id", filter=Q(last_is_correct=False)),
        )
        .filter(total__gte=3)
        .order_by("skill", "learning_type")
    )

    learning_type_rows = list(learning_type_rows)

    for row in learning_type_rows:
        total = row["total"] or 0
        solved = row["solved"] or 0
        attempted = row["attempted"] or 0

        row["skill_label"] = get_skill_label(row["skill"])
        row["solve_rate"] = round((solved / total) * 100, 1) if total else 0.0
        row["attempt_rate"] = round((attempted / total) * 100, 1) if total else 0.0

        if row["learning_type"] == "feature":
            row["learning_type_label"] = "기능 선택형"
        elif row["learning_type"] == "result":
            row["learning_type_label"] = "결과 예측형"
        elif row["learning_type"] == "error":
            row["learning_type_label"] = "오류 진단형"
        elif row["learning_type"] == "next_action":
            row["learning_type_label"] = "다음 행동형"
        elif row["learning_type"] == "procedure":
            row["learning_type_label"] = "절차 순서형"
        else:
            row["learning_type_label"] = row["learning_type"]

    weak_learning_type = None

    weak_candidates = [
        row for row in learning_type_rows
        if row["attempted"] >= 1
    ]

    if weak_candidates:
        weak_learning_type = sorted(
            weak_candidates,
            key=lambda row: (
                row["solve_rate"],
                -row["attempted"],
                row["skill_label"],
            )
        )[0]

        weak_learning_type["recommend_message"] = (
            f"{weak_learning_type['skill_label']}의 "
            f"{weak_learning_type['learning_type_label']} 단계가 약합니다. "
            "이 유형부터 다시 풀어보세요."
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
        "learning_type_rows": learning_type_rows,
        "weak_learning_type": weak_learning_type,
    })