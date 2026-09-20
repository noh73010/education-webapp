# core/views/stats.py

from datetime import timedelta

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, OuterRef, Subquery
from django.utils import timezone
from core.services.skill_labels import get_skill_label
from core.services.skill_categories import get_skill_category
from core.services.subjects import get_current_subject
from core.services.logistics_curriculum import LOGISTICS_CHAPTER_NAMES
from core.services.learning_experience import progress_evidence

from core.models import (
    Mission,
    Attempt,
    AttemptWrongReason,
    AttemptWrongPattern,
    PatternTrainingSession,
    UserWeakness,
)


def _learner_skill_label(raw_skill, current_subject):
    if current_subject.code == "logistics":
        return LOGISTICS_CHAPTER_NAMES.get(raw_skill, get_skill_label(raw_skill))
    return get_skill_label(raw_skill)

@login_required
def stats(request):
    current_subject, _ = get_current_subject(request)
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
    attempt_qs = Attempt.objects.valid_for_learning().filter(
        user=request.user, mission__subject=current_subject
    )
    awr_qs = AttemptWrongReason.objects.filter(
        attempt__user=request.user,
        attempt__mission__subject=current_subject,
        attempt__grading_valid=True,
    )

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

        r["skill_label"] = _learner_skill_label(raw_skill, current_subject)
        r["category"] = get_skill_category(raw_skill)

    

    # 2) 오답원인 TOP 5
    wrong_reason_rows = (
        awr_qs
        .values("wrong_reason__name")
        .annotate(cnt=Count("id"))
        .order_by("-cnt")[:5]
    )
    
    active_pattern_codes = UserWeakness.objects.filter(
        user=request.user,
        subject=current_subject,
    ).exclude(
        status=UserWeakness.STATUS_MASTERED,
    ).values_list("wrong_pattern__code", flat=True)
    wrong_pattern_qs = (
        AttemptWrongPattern.objects
        .filter(
            attempt__user=request.user,
            attempt__mission__subject=current_subject,
            attempt__grading_valid=True,
            wrong_pattern__code__in=active_pattern_codes,
        )
    )
    if since is not None:
        wrong_pattern_qs = wrong_pattern_qs.filter(attempt__created_at__gte=since)
    wrong_pattern_rows = (
        wrong_pattern_qs
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
        row["wrong_pattern_skill_label"] = _learner_skill_label(
            row["wrong_pattern__skill"], current_subject
        )
        
    top_wrong_pattern = wrong_pattern_rows[0] if wrong_pattern_rows else None
    pattern_training_rows = (
    PatternTrainingSession.objects
    .filter(user=request.user, wrong_pattern__subject=current_subject)
    .select_related("wrong_pattern")
    .order_by("-created_at")[:10]
    )


    # 3) 최근 풀이 20개
    recent_attempts = list(
        attempt_qs
        .select_related("mission")
        .order_by("-created_at")[:20]
    )
    for attempt in recent_attempts:
        attempt.skill_label = _learner_skill_label(attempt.mission.skill, current_subject)

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
        Attempt.objects.valid_for_learning()
        .filter(user=request.user, mission=OuterRef("pk"))
        .order_by("-created_at")
    )

    missions_with_last = (
        Mission.objects
        .filter(subject=current_subject)
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
        r["skill_label"] = _learner_skill_label(raw_skill, current_subject)
        r["category"] = get_skill_category(raw_skill)

    chapter_rows = list(
        missions_with_last
        .values("course", "chapter_code", "chapter_name", "skill")
        .annotate(
            total=Count("id"),
            attempted=Count("id", filter=Q(last_time__isnull=False)),
            solved=Count("id", filter=Q(last_is_correct=True)),
            open=Count("id", filter=Q(last_is_correct=False)),
        )
        .order_by("course", "chapter_code", "skill")
    )
    weakness_by_skill = {
        weakness.wrong_pattern.skill: weakness
        for weakness in UserWeakness.objects.filter(
            user=request.user, subject=current_subject,
        ).select_related("wrong_pattern")
    }
    weakness_statuses = {
        UserWeakness.STATUS_SUSPECTED: ("관찰 중", "조금 더 풀어 약점인지 확인해 보세요.", 3),
        UserWeakness.STATUS_ACTIVE: ("약점 발견", "3문제 집중 훈련으로 바로 보강하세요.", 0),
        UserWeakness.STATUS_TRAINING: ("집중 훈련 중", "짧은 약점 훈련을 이어가세요.", 1),
        UserWeakness.STATUS_REVIEW_DUE: ("재평가 예정", "다시 풀어 기억이 남았는지 확인하세요.", 1),
        UserWeakness.STATUS_MASTERED: ("안정적", "현재 학습 흐름을 유지하세요.", 5),
        UserWeakness.STATUS_RELAPSED: ("복습 필요", "다시 틀린 개념을 우선 복습하세요.", 0),
    }
    learning_status_rows = []
    for row in chapter_rows:
        skill = row["skill"]
        weakness = weakness_by_skill.get(skill)
        row["label"] = (
            row["chapter_name"]
            or _learner_skill_label(skill, current_subject)
            or row["course"]
        )
        row["course_label"] = row["course"] or current_subject.name
        row["pattern_code"] = weakness.wrong_pattern.code if weakness else ""
        if weakness and weakness.status in weakness_statuses:
            row["status_label"], row["next_action"], row["priority"] = weakness_statuses[weakness.status]
        elif not row["attempted"]:
            row["status_label"], row["next_action"], row["priority"] = (
                "학습 전", "오늘의 추천 학습에서 가볍게 시작하세요.", 4,
            )
        elif row["open"]:
            row["status_label"], row["next_action"], row["priority"] = (
                "복습 필요", "최근 틀린 문제를 다시 확인하세요.", 2,
            )
        elif row["attempted"] < row["total"]:
            row["status_label"], row["next_action"], row["priority"] = (
                "학습 중", "추천 문제를 이어서 풀어 보세요.", 3,
            )
        else:
            row["status_label"], row["next_action"], row["priority"] = (
                "재평가 대기", "3일 이상 간격을 두고 다시 풀어 기억이 남았는지 확인하세요.", 4,
            )
        row["status_key"] = {
            "약점 발견": "weak", "복습 필요": "review", "집중 훈련 중": "training",
            "재평가 예정": "review", "관찰 중": "learning", "학습 중": "learning",
            "안정적": "stable", "학습 전": "not-started",
        }.get(row["status_label"], "learning")
        learning_status_rows.append(row)
    tracked_status_rows = [
        row for row in learning_status_rows
        if row["attempted"] or row["pattern_code"]
    ]
    tracked_status_rows.sort(
        key=lambda row: (row["priority"], -row["attempted"], row["label"])
    )
    learning_focus = tracked_status_rows[0] if tracked_status_rows else None
    learning_status_rows = tracked_status_rows[1:5]
    learning_status_more_rows = tracked_status_rows[5:]
    recent_improvement = (
        UserWeakness.objects.filter(
            user=request.user,
            subject=current_subject,
            status=UserWeakness.STATUS_MASTERED,
            resolved_at__isnull=False,
        )
        .select_related("wrong_pattern")
        .order_by("-resolved_at")
        .first()
    )
    reassessment_due = (
        UserWeakness.objects.filter(
            user=request.user,
            subject=current_subject,
            status=UserWeakness.STATUS_REVIEW_DUE,
            next_review_at__lte=now,
        )
        .select_related("wrong_pattern")
        .order_by("next_review_at")
        .first()
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
        "learning_status_rows": learning_status_rows,
        "learning_status_more_rows": learning_status_more_rows,
        "learning_focus": learning_focus,
        "recent_improvement": recent_improvement,
        "reassessment_due": reassessment_due,
        "current_subject": current_subject,
        "progress_evidence": progress_evidence(request.user, Attempt.objects.valid_for_learning().filter(
            user=request.user, mission__subject=current_subject,
        ).select_related("mission__concept_unit").order_by("-created_at", "-pk").first()),
    })
