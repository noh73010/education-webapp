# core/views/stats.py

from datetime import timedelta

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, OuterRef, Subquery
from django.utils import timezone
from core.services.skill_labels import get_skill_label
from core.services.skill_categories import get_skill_category
from core.services.subjects import get_current_subject
from core.services.logistics_curriculum import LOGISTICS_CHAPTER_NAMES
from core.services.realtor_curriculum import REALTOR_CHAPTERS, REALTOR_LEARNING_AREAS
from core.services.learning_experience import progress_evidence

from core.models import (
    Mission,
    Attempt,
    AttemptWrongReason,
    AttemptWrongPattern,
    PatternTrainingSession,
    UserWeakness,
    WrongReason,
)

REALTOR_AREA_NAMES = {area["code"]: area["title"] for area in REALTOR_LEARNING_AREAS}


def _learner_skill_label(raw_skill, current_subject):
    if current_subject.code == "logistics":
        return LOGISTICS_CHAPTER_NAMES.get(raw_skill, get_skill_label(raw_skill))
    if current_subject.code == "realtor":
        chapter = REALTOR_CHAPTERS.get(raw_skill)
        if chapter:
            return chapter[1]
    return get_skill_label(raw_skill)


def _scope_labels(skill, chapter_code, chapter_name, course, current_subject):
    chapter_code = chapter_code or skill
    if current_subject.code == "realtor" and chapter_code in REALTOR_CHAPTERS:
        return REALTOR_AREA_NAMES[chapter_code.split("-")[0]], REALTOR_CHAPTERS[chapter_code][1]
    return (course or current_subject.name,
            chapter_name or _learner_skill_label(skill, current_subject))


def _period_since(period):
    if period == "7":
        return timezone.now() - timedelta(days=7)
    if period == "30":
        return timezone.now() - timedelta(days=30)
    return None


@login_required
def stats(request):
    current_subject, _ = get_current_subject(request)
    # 기간 필터: all / 7 / 30 (기본 all)
    period = request.GET.get("period", "all").strip()
    now = timezone.now()
    if period not in {"all", "7", "30"}:
        period = "all"
    since = _period_since(period)

    # ---------------------------
    # A) 누적 통계(기간 필터 반영)
    # ---------------------------
    attempt_qs = Attempt.objects.valid_for_learning().filter(
        user=request.user, mission__subject=current_subject
    )
    has_learning_history = attempt_qs.exists()
    awr_qs = AttemptWrongReason.objects.filter(
        attempt__user=request.user,
        attempt__mission__subject=current_subject,
        attempt__grading_valid=True,
        attempt__is_correct=False,
    )

    if since is not None:
        attempt_qs = attempt_qs.filter(created_at__gte=since)
        awr_qs = awr_qs.filter(attempt__created_at__gte=since)

    # 1) 스킬별 정답/오답 + 정답률
    skill_rows = (
        attempt_qs
        .values("mission__skill", "mission__chapter_code", "mission__chapter_name", "mission__course")
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
        r["course_label"], r["chapter_label"] = _scope_labels(
            raw_skill, r["mission__chapter_code"], r["mission__chapter_name"],
            r["mission__course"], current_subject,
        )
        r["category"] = get_skill_category(raw_skill)

    

    # 2) 현재 기간에 기록한 오답 원인별 문제
    wrong_reason_rows = (
        awr_qs
        .values("wrong_reason_id", "wrong_reason__name")
        .annotate(cnt=Count("id"))
        .order_by("-cnt", "wrong_reason__name")
    )
    wrong_reason_rows = list(wrong_reason_rows)
    for row in wrong_reason_rows:
        row["examples"] = list(
            awr_qs.filter(wrong_reason_id=row["wrong_reason_id"])
            .select_related("attempt__mission")
            .order_by("-attempt__created_at", "-pk")[:3]
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
        mission = attempt.mission
        attempt.course_label, attempt.chapter_label = _scope_labels(
            mission.skill, mission.chapter_code, mission.chapter_name, mission.course, current_subject,
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
        row["course_label"], row["label"] = _scope_labels(
            skill, row["chapter_code"], row["chapter_name"], row["course"], current_subject,
        )
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
        "has_learning_history": has_learning_history,
        "progress_evidence": progress_evidence(request.user, Attempt.objects.valid_for_learning().filter(
            user=request.user, mission__subject=current_subject,
        ).select_related("mission__concept_unit").order_by("-created_at", "-pk").first()),
    })


@login_required
def wrong_reason_attempts(request, reason_id):
    current_subject, _ = get_current_subject(request)
    reason = get_object_or_404(WrongReason, pk=reason_id)
    period = request.GET.get("period", "all").strip()
    if period not in {"all", "7", "30"}:
        period = "all"
    attempts = AttemptWrongReason.objects.filter(
        wrong_reason=reason, attempt__user=request.user,
        attempt__mission__subject=current_subject, attempt__grading_valid=True,
        attempt__is_correct=False,
    ).select_related("attempt__mission").order_by("-attempt__created_at", "-pk")
    since = _period_since(period)
    if since is not None:
        attempts = attempts.filter(attempt__created_at__gte=since)
    page_obj = Paginator(attempts, 20).get_page(request.GET.get("page"))
    for row in page_obj:
        mission = row.attempt.mission
        row.course_label, row.chapter_label = _scope_labels(
            mission.skill, mission.chapter_code, mission.chapter_name, mission.course, current_subject,
        )
    return render(request, "core/wrong_reason_attempts.html", {
        "reason": reason,
        "period": period,
        "page_obj": page_obj,
        "current_subject": current_subject,
    })
