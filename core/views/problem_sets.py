from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from core.models import ProblemSet, ProblemSetSession
from core.services.analytics import record_event
from core.services.problem_sets import create_problem_set_session
from core.services.problem_set_recommendations import get_problem_set_recommendations
from core.services.skill_labels import get_skill_label


@login_required
def problem_set_list(request):
    problem_sets = (
        ProblemSet.objects
        .filter(is_active=True)
        .annotate(
            usable_item_count=Count(
                "items",
                filter=Q(items__mission__is_usable_for_set=True),
            ),
            unusable_item_count=Count(
                "items",
                filter=Q(items__mission__is_usable_for_set=False),
            ),
        )
        .filter(usable_item_count__gt=0, unusable_item_count=0)
        .order_by("-created_at")[:10]
    )

    recommendation_data = get_problem_set_recommendations(request.user)
    
    for ps in problem_sets:
        ps.skill_label = get_skill_label(ps.skill_group)

    for ps in recommendation_data["today_sets"]:
        ps.skill_label = get_skill_label(ps.skill_group)

    for ps in recommendation_data["review_sets"]:
        ps.skill_label = get_skill_label(ps.skill_group)

    for ps in recommendation_data["weak_sets"]:
        ps.skill_label = get_skill_label(ps.skill_group)

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

    items = problem_set.items.filter(mission__is_usable_for_set=True)

    problem_set.skill_label = get_skill_label(problem_set.skill_group)

    for item in items:
        item.mission.skill_label = get_skill_label(item.mission.skill)

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

    items = list(problem_set.items.filter(mission__is_usable_for_set=True))

    if not items:
        messages.warning(
            request,
            "이 문제 세트에는 현재 훈련 가능한 문제가 없습니다. 관리자에게 문의하거나 문제를 추가하세요.",
        )
        return redirect("problem_set_detail", set_id=problem_set.id)

    existing_session = (
        ProblemSetSession.objects
        .filter(
            user=request.user,
            problem_set=problem_set,
            status="in_progress",
        )
        .order_by("-started_at")
        .first()
    )

    if existing_session:
        session = existing_session
        session_items = list(
            session.items
            .select_related("mission")
            .filter(mission__is_usable_for_set=True)
            .order_by("order_no")
        )

        mission_ids = [item.mission_id for item in session_items]

        if not mission_ids:
            messages.warning(
                request,
                "진행 중인 세트에 현재 훈련 가능한 문제가 없습니다. 관리자에게 문의하거나 문제를 추가하세요.",
            )
            return redirect("problem_set_detail", set_id=problem_set.id)

        first_unanswered_item = None

        for item in session_items:
            if item.is_correct is None:
                first_unanswered_item = item
                break

        if first_unanswered_item:
            current_index = mission_ids.index(first_unanswered_item.mission_id)
            next_mission_id = first_unanswered_item.mission_id
        else:
            current_index = 0
            next_mission_id = mission_ids[0]

    else:
        session = create_problem_set_session(
            user=request.user,
            problem_set=problem_set,
        )

        mission_ids = [item.mission_id for item in items]
        current_index = 0
        next_mission_id = mission_ids[0]

    request.session["problem_set_mission_ids"] = mission_ids
    request.session["problem_set_current_index"] = current_index
    request.session["problem_set_id"] = problem_set.id
    request.session["problem_set_session_id"] = session.id
    record_event(
        request.user,
        "start_problem_set",
        page="problem_set_start",
        metadata={
            "problem_set_id": problem_set.id,
            "session_id": session.id,
            "mission_count": len(mission_ids),
        },
    )

    return redirect("mission_detail", mission_id=next_mission_id)


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
