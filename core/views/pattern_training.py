from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import Attempt, Mission, WrongPattern, PatternTrainingSession
from core.services.access import has_full_learning_access
from core.services.analytics import record_event
from core.services.subjects import get_current_subject
from core.services.weaknesses import complete_pattern_training, mark_training_started
from core.services.learning_concepts import get_answer_display
from core.services.learning_experience import reviewed_concept, summarize_attempt_evidence


@login_required
def pattern_training_start(request, pattern_code):
    """
    오답 패턴 코드 기준으로 집중 훈련을 시작한다.
    예: VLOOKUP_FIRST_COL
    """
    current_subject, _ = get_current_subject(request)
    wrong_pattern = get_object_or_404(
        WrongPattern.objects.filter(Q(subject=current_subject) | Q(subject__isnull=True)),
        code=pattern_code,
    )
    
    if not has_full_learning_access(request.user):
        today = timezone.localdate()

        already_trained_today = PatternTrainingSession.objects.filter(
            user=request.user,
            created_at__date=today,
        ).exists()

        if already_trained_today:
            return render(request, "core/premium_required.html", {
                "title": "패턴 집중 훈련 제한",
                "message": "무료 회원은 패턴 집중 훈련을 하루 1회만 이용할 수 있습니다.",
            })

    missions = list(
        Mission.objects
        .filter(
            variation_group=pattern_code,
            is_usable_for_set=True,
            subject=current_subject,
        )
        .exclude(review_status=Mission.REVIEW_CONFIRMED_ERROR)
        .order_by("level", "id")
        .values_list("id", flat=True)[:3]
    )

    if not missions:
        return render(request, "core/pattern_training_empty.html", {
            "wrong_pattern": wrong_pattern,
        })

    request.session["pattern_training_pattern_code"] = pattern_code
    request.session["pattern_training_mission_ids"] = missions
    request.session["pattern_training_index"] = 0
    request.session["pattern_training_results"] = []
    request.session["pattern_training_saved"] = False
    request.session.modified = True
    mark_training_started(request.user, current_subject, wrong_pattern)
    record_event(
        request.user,
        "start_pattern_training",
        page="pattern_training_start",
        metadata={
            "pattern_code": pattern_code,
            "mission_count": len(missions),
        },
    )

    return redirect("mission_detail", mission_id=missions[0])


@login_required
def pattern_training_result(request, pattern_code):
    """
    패턴 집중 훈련 결과 화면
    """
    current_subject, _ = get_current_subject(request)
    wrong_pattern = get_object_or_404(
        WrongPattern.objects.filter(Q(subject=current_subject) | Q(subject__isnull=True)),
        code=pattern_code,
    )

    stored_results = list(request.session.get("pattern_training_results", []))
    attempt_ids = [row.get("attempt_id") for row in stored_results if row.get("attempt_id")]
    attempts = {
        attempt.id: attempt
        for attempt in Attempt.objects.valid_for_learning().filter(
            id__in=attempt_ids,
            user=request.user,
            mission__subject=current_subject,
            mission__variation_group=pattern_code,
        ).select_related("mission", "mission__concept_unit")
    }
    results = []
    for stored in stored_results:
        attempt = attempts.get(stored.get("attempt_id"))
        if not attempt:
            continue
        mission = attempt.mission
        results.append({
            "attempt": attempt,
            "mission": mission,
            "mission_id": mission.id,
            "is_correct": attempt.is_correct,
            "question": mission.prompt,
            "submitted_answer": get_answer_display(mission, attempt.submitted_answer),
            "correct_answer": get_answer_display(mission, mission.correct_answer),
            "explanation": mission.explanation,
            "concept": reviewed_concept(mission),
        })
    results.sort(key=lambda row: row["is_correct"] is True)

    total = len(results)
    correct = sum(1 for row in results if row.get("is_correct") is True)
    wrong = total - correct
    score = round((correct / total) * 100) if total else 0
    learning_evidence = summarize_attempt_evidence([row["attempt"] for row in results])
    
    if total > 0:
        already_saved = request.session.get("pattern_training_saved")

        if not already_saved:
            PatternTrainingSession.objects.create(
                user=request.user,
                wrong_pattern=wrong_pattern,
                total=total,
                correct=correct,
                wrong=wrong,
                score=score,
            )
            complete_pattern_training(request.user, current_subject, wrong_pattern, score)
            record_event(
                request.user,
                "finish_pattern_training",
                page="pattern_training_result",
                metadata={
                    "pattern_code": pattern_code,
                    "total": total,
                    "score": score,
                },
            )

            request.session["pattern_training_saved"] = True
            request.session.modified = True
    
    return render(request, "core/pattern_training_result.html", {
        "wrong_pattern": wrong_pattern,
        "results": results,
        "total": total,
        "correct": correct,
        "wrong": wrong,
        "score": score,
        "learning_evidence": learning_evidence,
    })


@login_required
@require_POST
def pattern_training_retry_wrong(request, pattern_code):
    current_subject, _ = get_current_subject(request)
    wrong_pattern = get_object_or_404(
        WrongPattern.objects.filter(Q(subject=current_subject) | Q(subject__isnull=True)),
        code=pattern_code,
    )
    stored_results = list(request.session.get("pattern_training_results", []))
    attempt_ids = [
        row.get("attempt_id") for row in stored_results
        if row.get("attempt_id") and row.get("is_correct") is not True
    ]
    attempts = {
        attempt.id: attempt
        for attempt in Attempt.objects.valid_for_learning().filter(
            id__in=attempt_ids,
            user=request.user,
            mission__subject=current_subject,
            mission__variation_group=pattern_code,
            mission__is_usable_for_set=True,
        ).exclude(
            mission__review_status=Mission.REVIEW_CONFIRMED_ERROR,
        )
    }
    mission_ids = [attempts[pk].mission_id for pk in attempt_ids if pk in attempts]
    if not mission_ids:
        return redirect("pattern_training_result", pattern_code=pattern_code)
    request.session["pattern_training_pattern_code"] = pattern_code
    request.session["pattern_training_mission_ids"] = mission_ids
    request.session["pattern_training_index"] = 0
    request.session["pattern_training_results"] = []
    request.session["pattern_training_saved"] = False
    request.session.modified = True
    mark_training_started(request.user, current_subject, wrong_pattern)
    return redirect("mission_detail", mission_id=mission_ids[0])
