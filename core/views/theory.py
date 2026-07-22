from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.http import Http404

from core.models import Mission, ProblemSet, ProblemSetSession
from core.services.analytics import record_event
from core.services.problem_sets import create_problem_set_session_from_missions
from core.services.subjects import get_current_subject
from core.services.learning_concepts import get_mission_learning_concept
from core.services.theory import (
    get_theory_chapter_context,
    load_theory_markdown,
    render_theory_markdown,
    THEORY_SET_PREFIX,
    build_chapter_practice_plan,
)

@login_required
def theory_chapter(request, chapter_slug):
    current_subject, _ = get_current_subject(request)
    context = get_theory_chapter_context(request.user, current_subject, chapter_slug)
    if context is None:
        raise Http404("현재 과목에 없는 챕터입니다.")

    chapter_code = context["chapter"]["chapter_code"]
    source = load_theory_markdown(current_subject.code, chapter_code)
    if source is None:
        raise Http404("아직 핵심 이론이 준비되지 않은 챕터입니다.")
    practice_plan = build_chapter_practice_plan(
        request.user,
        current_subject,
        chapter_code,
    )

    representative_mission = (
        Mission.objects
        .select_related("question_image")
        .filter(
            subject=current_subject,
            chapter_code=chapter_code,
            question_image__isnull=False,
        )
        .first()
    )
    focused_mission = None
    focused_concept = None
    mission_reference = request.GET.get("mission", "")
    if mission_reference.isdigit():
        focused_mission = Mission.objects.filter(
            id=int(mission_reference),
            subject=current_subject,
            chapter_code=chapter_code,
        ).first()
        if focused_mission:
            focused_concept = get_mission_learning_concept(focused_mission)
    record_event(
        request.user,
        "view_chapter_theory",
        page="theory_chapter",
        metadata={"subject": current_subject.code, "chapter_code": chapter_code},
    )
    return render(request, "core/theory_chapter.html", {
        **context,
        "current_subject": current_subject,
        "theory_html": render_theory_markdown(source),
        "representative_mission": representative_mission,
        "focused_mission": focused_mission,
        "focused_concept": focused_concept,
        "practice_plan": practice_plan,
    })


@login_required
@transaction.atomic
def chapter_practice_start(request, chapter_slug):
    current_subject, _ = get_current_subject(request)
    context = get_theory_chapter_context(request.user, current_subject, chapter_slug)
    if context is None:
        raise Http404("현재 과목에 없는 챕터입니다.")

    chapter_code = context["chapter"]["chapter_code"]
    mode = request.GET.get("mode", "batch")
    if mode not in {"batch", "wrong", "all"}:
        mode = "batch"
    plan = build_chapter_practice_plan(
        request.user,
        current_subject,
        chapter_code,
        mode=mode,
    )
    missions = plan["missions"]
    if not missions:
        if mode == "wrong":
            messages.info(request, "현재 다시 풀어야 할 오답이 없습니다.")
        else:
            messages.warning(request, "이 챕터에는 아직 연습할 수 있는 문제가 없습니다.")
        return redirect("theory_chapter", chapter_slug=chapter_slug)

    chapter = context["chapter"]
    problem_set, _created = ProblemSet.objects.update_or_create(
        title=f"{THEORY_SET_PREFIX} {current_subject.name} · {chapter['chapter_name']}",
        defaults={
            "skill_group": chapter_code,
            "level": 1,
            "set_type": "training",
            "description": f"{chapter['chapter_name']} 핵심 이론을 확인한 뒤 푸는 기출 연습문제입니다.",
            "is_active": True,
        },
    )
    # 챕터 배치는 사용자별 Attempt를 기준으로 만들어지므로 공유 ProblemSetItem에
    # 저장하지 않고 SessionItem에 스냅샷으로 보관합니다.
    problem_set.items.all().delete()

    session = (
        ProblemSetSession.objects
        .filter(user=request.user, problem_set=problem_set, status="in_progress")
        .order_by("-started_at")
        .first()
    )
    if session:
        session_items = list(
            session.items
            .select_related("mission")
            .filter(mission__subject=current_subject)
            .order_by("order_no")
        )
        mission_ids = [item.mission_id for item in session_items]
        first_unanswered = next((item for item in session_items if item.is_correct is None), None)
        current_index = mission_ids.index(first_unanswered.mission_id) if first_unanswered else 0
    else:
        session = create_problem_set_session_from_missions(
            user=request.user,
            problem_set=problem_set,
            missions=missions,
        )
        mission_ids = [mission.id for mission in missions]
        current_index = 0

    request.session["problem_set_mission_ids"] = mission_ids
    request.session["problem_set_current_index"] = current_index
    request.session["problem_set_id"] = problem_set.id
    request.session["problem_set_session_id"] = session.id

    record_event(
        request.user,
        "start_chapter_practice",
        page="chapter_practice_start",
        metadata={
            "subject": current_subject.code,
            "chapter_code": chapter_code,
            "mode": mode,
            "mission_count": len(mission_ids),
        },
    )
    return redirect("mission_detail", mission_id=mission_ids[current_index])
