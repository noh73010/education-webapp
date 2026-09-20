from math import ceil

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from core.models import Attempt, Mission, ProblemSet, ProblemSetSession
from core.services.analytics import record_event
from core.services.problem_sets import create_problem_set_session
from core.services.problem_set_recommendations import (
    eligible_problem_sets,
    get_problem_set_recommendations,
)
from core.services.mission_cards import prepare_mission_cards, with_user_learning_state
from core.services.skill_labels import get_skill_label
from core.services.subjects import get_current_subject
from core.services.learning_concepts import get_answer_display
from core.services.learning_feedback import build_mission_feedback
from core.services.learning_experience import summarize_attempt_evidence
from core.services.theory import (
    THEORY_SET_PREFIX,
    get_theory_chapter_context,
    get_theory_chapter_map,
)


@login_required
def problem_set_list(request):
    current_subject, _ = get_current_subject(request)
    problem_sets = list(
        eligible_problem_sets(current_subject)
        .prefetch_related("items__mission")
        .order_by("-created_at")[:10]
    )

    recommendation_data = get_problem_set_recommendations(request.user, subject=current_subject)
    
    def decorate(ps, reason):
        missions = [item.mission for item in ps.items.all()]
        first = missions[0] if missions else None
        ps.learner_title = (
            f"{first.chapter_name or first.course} 핵심 확인"
            if first and ps.title.startswith("[자동]")
            else ps.title.removeprefix("[자동] ")
        )
        ps.skill_label = get_skill_label(ps.skill_group)
        ps.question_count = len(missions)
        ps.estimated_minutes = ceil(len(missions) * 0.8) if missions else 0
        ps.recommendation_reason = reason.format(skill=ps.skill_label)

    for ps in problem_sets:
        decorate(ps, "현재 학습 범위에서 이어서 풀 수 있는 세트입니다.")
    for ps in recommendation_data["today_sets"]:
        decorate(ps, "현재 학습 단계에 맞는 문제를 모았습니다.")
    for ps in recommendation_data["review_sets"]:
        decorate(ps, "이전에 푼 범위를 다시 확인할 차례입니다.")
    for ps in recommendation_data["weak_sets"]:
        decorate(ps, "최근 {skill}에서 틀린 기록이 있어 추천합니다.")

    return render(request, "core/problem_set_list.html", {
        "problem_sets": problem_sets,
        "today_sets": recommendation_data["today_sets"],
        "review_sets": recommendation_data["review_sets"],
        "weak_sets": recommendation_data["weak_sets"],
        "weak_skills": recommendation_data["weak_skills"],
    })

@login_required
def problem_set_detail(request, set_id):
    current_subject, _ = get_current_subject(request)
    problem_set = get_object_or_404(
        eligible_problem_sets(current_subject, include_theory=True).prefetch_related("items__mission"),
        id=set_id,
        is_active=True,
    )

    items = list(problem_set.items.filter(
        mission__is_usable_for_set=True,
        mission__subject=current_subject,
    ))

    problem_set.skill_label = get_skill_label(problem_set.skill_group)

    card_missions = list(
        with_user_learning_state(
            Mission.objects.select_related("subject").filter(
                id__in=[item.mission_id for item in items],
            ),
            request.user,
        )
    )
    prepare_mission_cards(card_missions)
    mission_by_id = {mission.id: mission for mission in card_missions}

    for item in items:
        item.mission = mission_by_id[item.mission_id]

    course_labels = list(dict.fromkeys(
        (item.mission.course or item.mission.subject.name)
        for item in items
    ))
    chapter_labels = list(dict.fromkeys(
        item.mission.chapter_name
        for item in items
        if item.mission.chapter_name
    ))
    estimated_minutes = ceil(len(items) * 0.8) if items else 0
    problem_set.learner_title = (
        f"{chapter_labels[0]} 핵심 확인"
        if chapter_labels and problem_set.title.startswith("[자동]")
        else problem_set.title.removeprefix("[자동] ")
    )

    recent_sessions = (
        ProblemSetSession.objects
        .filter(user=request.user, problem_set=problem_set)
        .order_by("-started_at")[:5]
    )

    return render(request, "core/problem_set_detail.html", {
        "problem_set": problem_set,
        "items": items,
        "estimated_minutes": estimated_minutes,
        "course_label": ", ".join(course_labels),
        "chapter_label": ", ".join(chapter_labels),
        "recent_sessions": recent_sessions,
    })


@login_required
def problem_set_start(request, set_id):
    current_subject, _ = get_current_subject(request)
    problem_set = get_object_or_404(
        ProblemSet.objects.prefetch_related("items__mission"),
        id=set_id,
        is_active=True,
    )
    if (
        not problem_set.title.startswith(THEORY_SET_PREFIX)
        and not eligible_problem_sets(current_subject).filter(pk=problem_set.pk).exists()
    ):
        raise Http404("현재 과목에서 사용할 수 없는 문제 세트입니다.")

    items = list(problem_set.items.filter(
        mission__is_usable_for_set=True,
        mission__subject=current_subject,
    ))

    existing_session = (
        ProblemSetSession.objects
        .filter(
            user=request.user,
            problem_set=problem_set,
            status="in_progress",
            items__mission__subject=current_subject,
        )
        .distinct()
        .order_by("-started_at")
        .first()
    )

    if existing_session:
        session = existing_session
        session_items = list(
            session.items
            .select_related("mission")
            .filter(mission__is_usable_for_set=True, mission__subject=current_subject)
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
        if not items:
            messages.warning(
                request,
                "이 문제 세트에는 현재 훈련 가능한 문제가 없습니다. 학습 로드맵에서 새 배치를 시작하세요.",
            )
            return redirect("mission_list")
        session = create_problem_set_session(
            user=request.user,
            problem_set=problem_set,
            subject=current_subject,
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
    current_subject, _ = get_current_subject(request)
    session = get_object_or_404(
        ProblemSetSession.objects.select_related("problem_set")
        .filter(items__mission__subject=current_subject)
        .distinct(),
        id=session_id,
        user=request.user,
    )

    items = list(
        session.items
        .select_related("mission", "attempt", "mission__question_image")
        .filter(mission__subject=current_subject)
        .order_by("order_no")
    )

    theory_chapter_map = get_theory_chapter_map(request.user, current_subject)
    legacy_attempts = (
        Attempt.objects.valid_for_learning()
        .filter(
            user=request.user,
            mission_id__in=[item.mission_id for item in items],
            created_at__gte=session.started_at,
        )
        .order_by("mission_id", "-created_at")
    )
    if session.completed_at:
        legacy_attempts = legacy_attempts.filter(created_at__lte=session.completed_at)
    legacy_attempt_map = {}
    for attempt in legacy_attempts:
        legacy_attempt_map.setdefault(attempt.mission_id, attempt)

    for item in items:
        mission = item.mission
        if not item.submitted_answer and item.mission_id in legacy_attempt_map:
            item.submitted_answer = legacy_attempt_map[item.mission_id].submitted_answer
        item.question_text = mission.prompt
        item.submitted_answer_display = get_answer_display(mission, item.submitted_answer)
        item.correct_answer_display = get_answer_display(mission, mission.correct_answer)
        item.learning_feedback = build_mission_feedback(mission, item.submitted_answer)
        item.learning_concept = item.learning_feedback["learning_concept"]
        mission.related_theory_chapter = theory_chapter_map.get(mission.chapter_code)
        item.evidence_attempt = item.attempt or legacy_attempt_map.get(item.mission_id)

    learning_evidence = summarize_attempt_evidence(
        [item.evidence_attempt for item in items if item.evidence_attempt]
    )
    result_message = learning_evidence["message"]

    wrong_items = [
        item for item in items
        if item.is_correct is not True
    ]
    correct_items = [item for item in items if item.is_correct is True]
    weak_concepts = []
    seen_concepts = set()
    for item in wrong_items:
        title = item.learning_concept["title"]
        if title not in seen_concepts:
            seen_concepts.add(title)
            weak_concepts.append(item.learning_concept)

    duration_text = ""
    if session.completed_at:
        seconds = max(0, int((session.completed_at - session.started_at).total_seconds()))
        minutes, remainder = divmod(seconds, 60)
        duration_text = f"{minutes}분 {remainder}초" if minutes else f"{remainder}초"

    theory_context = None
    if session.problem_set.title.startswith(THEORY_SET_PREFIX):
        theory_context = get_theory_chapter_context(
            request.user,
            current_subject,
            session.problem_set.skill_group,
        )

    next_set = None

    if wrong_items:
        next_action_label = "틀린 문제만 다시 풀기"
        next_action_url_name = "problem_set_wrong_retry"
        next_action_id = session.id
    elif theory_context and theory_context["chapter"]["remaining_count"]:
        next_action_label = "다음 10문제 이어서 풀기"
        next_action_url_name = "chapter_practice_start"
        next_action_id = theory_context["chapter"]["slug"]
    elif theory_context and theory_context["next_chapter"]:
        next_action_label = "다음 챕터 핵심 이론 보기"
        next_action_url_name = "theory_chapter"
        next_action_id = theory_context["next_chapter"]["slug"]
    elif theory_context:
        next_action_label = "개념 학습 로드맵으로 돌아가기"
        next_action_url_name = "theory_roadmap"
        next_action_id = "complete"
    else:
        next_set = (
            eligible_problem_sets(current_subject)
            .exclude(id=session.problem_set.id)
            .distinct()
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
        "learning_evidence": learning_evidence,
        "next_set": next_set,
        "wrong_items": wrong_items,
        "correct_items": correct_items,
        "weak_concepts": weak_concepts,
        "duration_text": duration_text,
        "next_action_label": next_action_label,
        "next_action_url_name": next_action_url_name,
        "next_action_id": next_action_id,
        "theory_context": theory_context,
    })
    
@login_required
def problem_set_wrong_retry(request, session_id):
    current_subject, _ = get_current_subject(request)
    session = get_object_or_404(
        ProblemSetSession.objects.prefetch_related("items__mission")
        .filter(items__mission__subject=current_subject)
        .distinct(),
        id=session_id,
        user=request.user,
        status="completed",
    )

    wrong_items = [
        item for item in session.items.filter(mission__subject=current_subject)
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
    current_subject, _ = get_current_subject(request)
    original_session = get_object_or_404(
        ProblemSetSession.objects.select_related("problem_set")
        .filter(items__mission__subject=current_subject)
        .distinct(),
        id=session_id,
        user=request.user,
        status="completed",
    )

    recommendation_data = get_problem_set_recommendations(request.user, subject=current_subject)

    theory_context = None
    if original_session.problem_set.title.startswith(THEORY_SET_PREFIX):
        theory_context = get_theory_chapter_context(
            request.user,
            current_subject,
            original_session.problem_set.skill_group,
        )

    next_set = None

    if recommendation_data["weak_sets"]:
        next_set = recommendation_data["weak_sets"][0]
    elif recommendation_data["today_sets"]:
        next_set = recommendation_data["today_sets"][0]

    retry_results = list(request.session.get("wrong_retry_results", []))
    original_items = list(
        original_session.items
        .select_related("mission")
        .filter(mission__subject=current_subject)
        .order_by("order_no")
    )
    item_map = {item.mission_id: item for item in original_items}
    if not retry_results:
        retry_results = [
            {"mission_id": item.mission_id, "is_correct": item.review_is_correct}
            for item in original_items
            if item.review_attempt_count
        ]
    for row in retry_results:
        item = item_map.get(row.get("mission_id"))
        if item:
            row["order_no"] = item.order_no
            row["course"] = item.mission.course or current_subject.name
            row["question"] = item.mission.prompt
            row["review_attempt_count"] = item.review_attempt_count

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
        "theory_context": theory_context,
    })
