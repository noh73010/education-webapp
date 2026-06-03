from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from core.models import ProblemSet, ProblemSetSession
from core.services.problem_sets import create_problem_set_session
from core.services.problem_set_recommendations import get_problem_set_recommendations


@login_required
def problem_set_list(request):
    problem_sets = (
        ProblemSet.objects
        .filter(is_active=True)
        .order_by("-created_at")
    )

    recommendation_data = get_problem_set_recommendations(request.user)

    return render(request, "core/problem_set_list.html", {
        "problem_sets": problem_sets,
        "today_sets": recommendation_data["today_sets"],
        "review_sets": recommendation_data["review_sets"],
        "weak_sets": recommendation_data["weak_sets"],
        "weak_skills": recommendation_data["weak_skills"],
    })


@login_required
def problem_set_detail(request, set_id):
    problem_set = get_object_or_404(
        ProblemSet.objects.prefetch_related("items__mission"),
        id=set_id,
        is_active=True,
    )

    items = problem_set.items.all()

    recent_sessions = (
        ProblemSetSession.objects
        .filter(user=request.user, problem_set=problem_set)
        .order_by("-started_at")[:5]
    )

    return render(request, "core/problem_set_detail.html", {
        "problem_set": problem_set,
        "items": items,
        "recent_sessions": recent_sessions,
    })


@login_required
def problem_set_start(request, set_id):
    problem_set = get_object_or_404(
        ProblemSet.objects.prefetch_related("items__mission"),
        id=set_id,
        is_active=True,
    )

    items = list(problem_set.items.all())

    if not items:
        return redirect("problem_set_detail", set_id=problem_set.id)

    session = create_problem_set_session(
        user=request.user,
        problem_set=problem_set,
    )

    mission_ids = [item.mission_id for item in items]

    request.session["problem_set_mission_ids"] = mission_ids
    request.session["problem_set_current_index"] = 0
    request.session["problem_set_id"] = problem_set.id
    request.session["problem_set_session_id"] = session.id

    return redirect("mission_detail", mission_id=mission_ids[0])


@login_required
def problem_set_result(request, session_id):
    session = get_object_or_404(
        ProblemSetSession.objects.select_related("problem_set"),
        id=session_id,
        user=request.user,
    )

    items = session.items.select_related("mission").all()

    if session.score >= 90:
        result_message = "좋습니다. 이 세트는 거의 안정권입니다."
    elif session.score >= 70:
        result_message = "기본은 잡혔지만 아직 실수가 남아 있습니다."
    elif session.score >= 50:
        result_message = "개념은 일부 알고 있지만 복습이 필요합니다."
    else:
        result_message = "이 세트는 다시 풀어야 합니다. 그냥 넘어가면 안 됩니다."

    wrong_items = [
        item for item in items
        if item.is_correct is not True
    ]

    next_set = None

    if wrong_items:
        next_action_label = "틀린 문제만 다시 풀기"
        next_action_url_name = "problem_set_wrong_retry"
        next_action_id = session.id
    else:
        next_set = (
            ProblemSet.objects
            .filter(is_active=True)
            .exclude(id=session.problem_set.id)
            .order_by("?")
            .first()
        )

        next_action_label = "다음 추천 세트 풀기"
        next_action_url_name = "problem_set_start"
        next_action_id = next_set.id if next_set else None

    return render(request, "core/problem_set_result.html", {
        "session": session,
        "items": items,
        "result_message": result_message,
        "next_set": next_set,
        "wrong_items": wrong_items,
        "next_action_label": next_action_label,
        "next_action_url_name": next_action_url_name,
        "next_action_id": next_action_id,
    })
    
@login_required
def problem_set_wrong_retry(request, session_id):
    session = get_object_or_404(
        ProblemSetSession.objects.prefetch_related("items__mission"),
        id=session_id,
        user=request.user,
        status="completed",
    )

    wrong_items = [
        item for item in session.items.all()
        if item.is_correct is not True
    ]

    if not wrong_items:
        return redirect("problem_set_result", session_id=session.id)

    mission_ids = [item.mission_id for item in wrong_items]

    request.session["problem_set_mission_ids"] = mission_ids
    request.session["problem_set_current_index"] = 0
    request.session["problem_set_id"] = session.problem_set_id
    request.session["wrong_retry_return_session_id"] = session.id
    # 기존 세션과 구분하려고 새 세션 기록은 만들지 않는다.
    # 단순 오답 복습 루프만 돌린다.
    request.session.pop("problem_set_session_id", None)

    return redirect("mission_detail", mission_id=mission_ids[0])

@login_required
def problem_set_wrong_retry_result(request, session_id):
    original_session = get_object_or_404(
        ProblemSetSession.objects.select_related("problem_set"),
        id=session_id,
        user=request.user,
        status="completed",
    )

    recommendation_data = get_problem_set_recommendations(request.user)

    next_set = None

    if recommendation_data["weak_sets"]:
        next_set = recommendation_data["weak_sets"][0]
    elif recommendation_data["today_sets"]:
        next_set = recommendation_data["today_sets"][0]

    retry_results = request.session.get("wrong_retry_results", [])

    retry_correct_count = sum(1 for row in retry_results if row.get("is_correct") is True)
    retry_wrong_count = sum(1 for row in retry_results if row.get("is_correct") is not True)
    retry_total_count = len(retry_results)

    request.session.pop("wrong_retry_results", None)

    return render(request, "core/problem_set_wrong_retry_result.html", {
        "original_session": original_session,
        "next_set": next_set,
        "retry_results": retry_results,
        "retry_total_count": retry_total_count,
        "retry_correct_count": retry_correct_count,
        "retry_wrong_count": retry_wrong_count,
    })