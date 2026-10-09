from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from core.services.subjects import get_current_subject
from core.services.daily_review import review_plan


@login_required
@require_POST
def daily_review_start(request):
    subject, _ = get_current_subject(request)
    plan = review_plan(request.user, subject)
    if not plan["mission_ids"]:
        messages.info(request, "선택한 과목에 지금 복습할 문제가 없어요. 오늘 학습으로 이어가세요.")
        return redirect("mission_list")
    # One active learning pipeline per browser session; completed records stay intact.
    for key in list(request.session.keys()):
        if key.startswith(("problem_set_", "pattern_training_", "learning_type_training_", "review_")):
            request.session.pop(key, None)
    request.session["review_mission_ids"] = plan["mission_ids"]
    request.session["review_current_index"] = 0
    request.session["daily_review_state"] = {"subject_id": subject.pk, "label": plan["label"],
                                             "mission_ids": plan["mission_ids"], "attempt_ids": []}
    return redirect("mission_detail", mission_id=plan["mission_ids"][0])


@login_required
def daily_review_result(request):
    from core.models import Attempt
    subject, _ = get_current_subject(request)
    state = request.session.get("daily_review_state", {})
    ids = state.get("attempt_ids", []) if state.get("subject_id") == subject.pk else []
    attempts = list(Attempt.objects.valid_for_learning().filter(pk__in=ids, user=request.user,
                    mission__subject=subject).select_related("mission"))
    return render(request, "core/daily_review_result.html", {"review_attempts": attempts,
        "review_correct": sum(a.is_correct for a in attempts), "review_total": len(state.get("mission_ids", [])) if ids else 0})
