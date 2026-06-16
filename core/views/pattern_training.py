from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.models import Mission, WrongPattern, PatternTrainingSession
from core.services.access import get_user_access
from core.services.analytics import record_event


@login_required
def pattern_training_start(request, pattern_code):
    """
    오답 패턴 코드 기준으로 집중 훈련을 시작한다.
    예: VLOOKUP_FIRST_COL
    """
    wrong_pattern = get_object_or_404(WrongPattern, code=pattern_code)
    
    access = get_user_access(request.user)

    if not access.is_premium:
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
        )
        .order_by("level", "id")
        .values_list("id", flat=True)
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
    wrong_pattern = get_object_or_404(WrongPattern, code=pattern_code)

    results = request.session.get("pattern_training_results", [])

    total = len(results)
    correct = sum(1 for row in results if row.get("is_correct") is True)
    wrong = total - correct
    score = round((correct / total) * 100) if total else 0
    
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
    })
