from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.db.models import Count, Q
from django.utils import timezone
from django.http import JsonResponse
from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from types import SimpleNamespace
from core.services.exam_modes import (available_courses, blueprint, create_mode_exam,
    begin_second_sitting, mode_result, missing_full_courses)
from datetime import timedelta

from core.models import Mission, ExamSession, ExamSessionMission
from core.services.access import get_user_access, has_full_learning_access
from core.services.exams import (
    create_exam_session,
    draft_has_answer,
    submit_exam_answer,
    finish_exam_session,
)
from core.services.analytics import record_event
from core.services.exam_analysis import build_exam_analysis
from core.services.skill_labels import get_skill_label
from core.services.grading import (
    parse_answer_schema,
    parse_choice_schema,
    grade_answer,
    grade_multi_answer,
)
from core.services.subjects import get_current_subject
from core.services.exam_requests import serialized_exam_request
from core.services.exam_results import representative_wrong_items, result_sessions
from core.services.exam_history import build_exam_history_cards


EXAM_DRAFT_FIELDS = ("submitted_answer", "submitted_answers", "is_correct")


def _posted_exam_draft(request):
    return {
        key: request.POST.getlist(key)
        for key in EXAM_DRAFT_FIELDS
        if key in request.POST
    }


def _resume_exam_order(exam):
    items = list(exam.items.order_by("order_no"))
    first_unanswered = next(
        (item for item in items if not draft_has_answer(item.draft_answers) and item.submitted_at is None),
        None,
    )
    if first_unanswered:
        return first_unanswered.order_no
    first_marked = next((item for item in items if item.is_marked_for_review), None)
    return first_marked.order_no if first_marked else (items[0].order_no if items else None)




@login_required
def exam_start(request):
    """
    시험 시작 안내 페이지
    """
    access = get_user_access(request.user)
    has_full_access = has_full_learning_access(request.user)
    current_subject, _ = get_current_subject(request)
    return render(request, "core/exam_start.html", {
        "is_premium": access.is_premium,
        "has_full_access": has_full_access,
        "current_subject": current_subject,
        "courses": available_courses(current_subject),
        "supports_full": bool(blueprint(current_subject)),
        "missing_full_courses": missing_full_courses(current_subject),
        "open_exams": ExamSession.objects.filter(user=request.user,
            items__mission__subject=current_subject, status__in=["in_progress", "waiting"]).distinct(),
    })


@login_required
def exam_create(request):
    """
    시험 세션 실제 생성
    - 무료 회원: 하루 1회
    - 유료 회원: 무제한
    """
    if request.method != "POST":
        return redirect("exam_start")

    if "mode" in request.POST or "second_sitting" in request.POST:
        return create_selected_mode(request)

    access = get_user_access(request.user)
    current_subject, _ = get_current_subject(request)
    today = timezone.localdate()

    existing_exam = (
        ExamSession.objects
        .filter(
            user=request.user,
            status="in_progress",
            items__mission__subject=current_subject,
        )
        .distinct()
        .order_by("-started_at")
        .first()
    )

    if existing_exam:
        resume_order = _resume_exam_order(existing_exam)
        if resume_order:
            return redirect(
                "exam_take",
                exam_id=existing_exam.id,
                order_no=resume_order,
            )

    # Resuming an existing exam must not consume/block the daily new-exam quota.
    if not has_full_learning_access(request.user) and ExamSession.objects.filter(
        user=request.user, started_at__date=today,
    ).exists():
        return render(request, "core/premium_required.html", {
            "title": "실전 모의고사 제한",
            "message": "무료 회원은 실전 모의고사를 하루 1회만 이용할 수 있습니다.",
        })

    try:
        exam = create_exam_session(user=request.user, subject=current_subject)
    except ValueError:
        messages.warning(request, "현재 선택한 과목에는 아직 등록된 모의고사 문제가 없습니다.")
        return redirect("mission_list")
    record_event(
        request.user,
        "start_exam",
        page="exam_create",
        metadata={
            "exam_id": exam.id,
            "total_questions": exam.total_questions,
            "time_limit_min": exam.time_limit_min,
        },
    )
    first_item = exam.items.order_by("order_no").first()

    if not first_item:
        return redirect("mission_list")

    return redirect("exam_take", exam_id=exam.id, order_no=1)


@transaction.atomic
def create_selected_mode(request):
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    subject, _ = get_current_subject(request)
    try:
        if request.POST.get("second_sitting"):
            exam = begin_second_sitting(request.user, subject, int(request.POST["second_sitting"]))
        else:
            mode, course = request.POST.get("mode"), request.POST.get("course", "")
            if mode not in {"short", "course", "full"}:
                raise ValueError("올바른 모드를 선택해 주세요.")
            if mode == "course" and course not in available_courses(subject):
                raise ValueError("올바른 과목을 선택해 주세요.")
            existing = ExamSession.objects.filter(user=request.user, items__mission__subject=subject,
                mode_config__mode=mode, status__in=["in_progress", "waiting"])
            if mode == "course":
                existing = existing.filter(mode_config__course=course)
            exam = existing.distinct().order_by("pk").first()
            if exam is None:
                if not has_full_learning_access(request.user) and ExamSession.objects.filter(
                    user=request.user, previous_sitting__isnull=True,
                    started_at__date=timezone.localdate()).exists():
                    raise ValueError("무료 회원은 세 모드를 합쳐 하루 1회 새 시험을 시작할 수 있습니다. 풀던 시험은 계속 이용할 수 있습니다.")
                exam = create_mode_exam(request.user, subject, mode, course)
                record_event(request.user, "start_exam", page="exam_create", metadata={
                    "exam_id": exam.pk, "mode": mode, "total_questions": exam.total_questions,
                    "time_limit_min": exam.time_limit_min})
        if exam.status == "waiting":
            return redirect("exam_result", exam_id=exam.previous_sitting_id)
        if exam.status != "in_progress":
            return redirect("exam_result", exam_id=exam.pk)
        resume_order = _resume_exam_order(exam)
        if not resume_order:
            return redirect("exam_result", exam_id=exam.pk)
        return redirect("exam_take", exam_id=exam.pk, order_no=resume_order)
    except (ValueError, TypeError) as error:
        messages.warning(request, str(error))
        return redirect("exam_start")


@login_required
@serialized_exam_request
def exam_take(request, exam_id, order_no):
    current_subject, _ = get_current_subject(request)
    exam = get_object_or_404(
        ExamSession.objects
        .filter(items__mission__subject=current_subject)
        .distinct(),
        id=exam_id,
        user=request.user,
    )

    if exam.status != "in_progress":
        return redirect("exam_result", exam_id=exam.id)

    end_time = exam.started_at + timedelta(minutes=exam.time_limit_min)

    if timezone.now() >= end_time:
        finish_exam_session(exam)
        record_event(
            request.user,
            "finish_exam",
            page="exam_take",
            metadata={
                "exam_id": exam.id,
                "score": exam.score,
                "total_questions": exam.total_questions,
                "reason": "time_limit",
            },
        )
        return redirect("exam_result", exam_id=exam.id)

    item = get_object_or_404(
        ExamSessionMission.objects.select_related("mission", "exam_session"),
        exam_session=exam,
        order_no=order_no,
    )

    mission = item.mission
    all_items = list(exam.items.select_related("mission").order_by("order_no"))
    total_count = len(all_items)
    schema_items = parse_answer_schema(mission.answer_schema)
    choice_items = parse_choice_schema(mission.answer_schema)

    if request.method == "POST":
        action = request.POST.get("action", "goto" if "target_order" in request.POST else "next")
        if action == "skip":
            item.draft_answers = {}
            item.draft_updated_at = timezone.now()
            item.save(update_fields=["draft_answers", "draft_updated_at"])
        else:
            posted_draft = _posted_exam_draft(request)
            if posted_draft:
                item.draft_answers = posted_draft
                item.draft_updated_at = timezone.now()
                item.save(update_fields=["draft_answers", "draft_updated_at"])

        if action == "toggle_review":
            item.is_marked_for_review = not item.is_marked_for_review
            item.save(update_fields=["is_marked_for_review"])
            target_order = order_no
        elif action == "previous":
            target_order = max(1, order_no - 1)
        elif action == "goto":
            try:
                target_order = int(request.POST.get("target_order", order_no))
            except (TypeError, ValueError):
                target_order = order_no
            if target_order not in {row.order_no for row in all_items}:
                target_order = order_no
        elif action == "final":
            finish_exam_session(exam)
            record_event(request.user, "finish_exam", page="exam_take", metadata={
                "exam_id": exam.id,
                "score": exam.score,
                "total_questions": exam.total_questions,
                "reason": "manual_submit",
            })
            return redirect("exam_result", exam_id=exam.id)
        else:
            target_order = min(total_count, order_no + 1)
        return redirect("exam_take", exam_id=exam.id, order_no=target_order)

    remaining_seconds = int((end_time - timezone.now()).total_seconds())
    navigation = []
    for nav_item in all_items:
        answered = draft_has_answer(nav_item.draft_answers) or nav_item.submitted_at is not None
        navigation.append({
            "order_no": nav_item.order_no,
            "answered": answered,
            "marked": nav_item.is_marked_for_review,
            "current": nav_item.pk == item.pk,
        })
    answered_count = sum(row["answered"] for row in navigation)
    marked_count = sum(row["marked"] for row in navigation)
    draft_answers = item.draft_answers
    if not draft_answers and item.submitted_at is not None:
        key = "is_correct" if mission.question_type == "manual" else "submitted_answer"
        draft_answers = {key: [item.submitted_answer]}

    return render(request, "core/exam_take.html", {
        "exam": exam,
        "item": item,
        "mission": mission,
        "order_no": order_no,
        "total_count": total_count,
        "remaining_seconds": max(remaining_seconds, 0),
        "schema_items": schema_items,
        "choice_items": choice_items,
        "draft_answers": draft_answers,
        "navigation": navigation,
        "answered_count": answered_count,
        "unanswered_count": total_count - answered_count,
        "marked_count": marked_count,
        "current_answered": draft_has_answer(item.draft_answers) or item.submitted_at is not None,
        "previous_order": order_no - 1 if order_no > 1 else None,
        "next_order": order_no + 1 if order_no < total_count else None,
    })


@login_required
@require_POST
@serialized_exam_request
def exam_submit(request, exam_id):
    current_subject, _ = get_current_subject(request)
    exam = get_object_or_404(
        ExamSession.objects
        .filter(items__mission__subject=current_subject)
        .distinct(),
        id=exam_id,
        user=request.user,
    )

    if exam.status == "in_progress":
        finish_exam_session(exam)
        record_event(
            request.user,
            "finish_exam",
            page="exam_submit",
            metadata={
                "exam_id": exam.id,
                "score": exam.score,
                "total_questions": exam.total_questions,
                "reason": "manual_submit",
            },
        )

    return redirect("exam_result", exam_id=exam.id)


@login_required
@require_POST
@serialized_exam_request
def exam_draft(request, exam_id, order_no):
    subject, _ = get_current_subject(request)
    item = get_object_or_404(ExamSessionMission.objects.select_related("exam_session"),
        exam_session_id=exam_id, order_no=order_no, exam_session__user=request.user,
        mission__subject=subject)
    exam = item.exam_session
    if exam.status == "waiting":
        return JsonResponse({"error": "아직 시작하지 않은 교시입니다."}, status=400)
    if timezone.now() >= exam.started_at + timedelta(minutes=exam.time_limit_min):
        finish_exam_session(exam)
        exam.refresh_from_db()
    if exam.status != "in_progress":
        return JsonResponse({"saved": True, "submitted": True})
    answers = _posted_exam_draft(request)
    if sum(len(value) for values in answers.values() for value in values) > 12000:
        return JsonResponse({"error": "답안이 너무 깁니다."}, status=400)
    item.draft_answers = answers
    item.draft_updated_at = timezone.now()
    item.save(update_fields=["draft_answers", "draft_updated_at"])
    return JsonResponse({"saved": True, "submitted": False})



@login_required
@serialized_exam_request
def exam_result(request, exam_id):
    """
    시험 결과 페이지
    """
    current_subject, _ = get_current_subject(request)
    exam = get_object_or_404(
        ExamSession.objects
        .filter(items__mission__subject=current_subject)
        .distinct(),
        id=exam_id,
        user=request.user,
    )
    if exam.status == "waiting":
        return redirect("exam_result", exam_id=exam.previous_sitting_id)
    if exam.status == "in_progress":
        if timezone.now() >= exam.started_at + timedelta(minutes=exam.time_limit_min):
            finish_exam_session(exam)
        else:
            resume_order = _resume_exam_order(exam)
            if resume_order:
                return redirect("exam_take", exam_id=exam.pk, order_no=resume_order)
    related_sessions = result_sessions(exam)
    items = []
    for sitting_number, related_exam in enumerate(related_sessions, 1):
        sitting_items = list(
            related_exam.items.select_related("mission")
            .filter(mission__subject=current_subject)
            .order_by("order_no")
        )
        for result_item in sitting_items:
            result_item.sitting_number = sitting_number if len(related_sessions) > 1 else None
        items.extend(sitting_items)
    access = get_user_access(request.user)
    has_full_access = has_full_learning_access(request.user)
    result = mode_result(exam)

    answered_items = [item for item in items if item.submitted_at is not None]
    unanswered_items = [item for item in items if item.submitted_at is None]
    skill_totals = {}
    for item in answered_items:
        label = item.mission.chapter_name or get_skill_label(item.mission.skill)
        row = skill_totals.setdefault(item.mission.skill, {
            "mission__skill": item.mission.skill, "skill_label": label,
            "total": 0, "correct": 0, "wrong": 0,
        })
        row["total"] += 1
        if item.user_answer_correct is True:
            row["correct"] += 1
        else:
            row["wrong"] += 1
    skill_rows = list(skill_totals.values())
    for row in skill_rows:
        row["accuracy"] = round((row["correct"] / row["total"]) * 100, 1)

    wrong_items = [item for item in answered_items if item.user_answer_correct is False]
    
    for item in wrong_items:
        item.mission.skill_label = get_skill_label(item.mission.skill)

    analysis_exam = SimpleNamespace(
        score=result["average"] if result["average"] is not None else result["sitting_score"],
        total_questions=len(items),
        correct_count=sum(item.user_answer_correct is True for item in items),
    )
    analysis = build_exam_analysis(
        exam=analysis_exam,
        skill_rows=skill_rows,
        wrong_items=wrong_items,
    )
    representative_wrong = representative_wrong_items(
        wrong_items, analysis["weak_skills"], limit=5,
    )
    is_combined_result = len(related_sessions) > 1
    # 추천 문제 5개
    recommend_missions = []

    if analysis["weak_skills"]:
        weak_skill_names = [row["skill"] for row in analysis["weak_skills"]]

        recommend_missions = (
            Mission.objects.filter(
                skill__in=weak_skill_names,
                is_usable_for_set=True,
                subject=current_subject,
            )
            .exclude(review_status=Mission.REVIEW_CONFIRMED_ERROR)
            .exclude(
                id__in=[item.mission.id for item in items]
            )
            .order_by("?")[:5]
        )
    for mission in recommend_missions:
        mission.skill_label = get_skill_label(mission.skill)

    return render(request, "core/exam_result.html", {
        "exam": exam,
        "items": items,
        "mode_result": result,
        "skill_rows": skill_rows,
        "wrong_items": representative_wrong,
        "total_wrong_count": len(wrong_items),
        "result_title": "실전 모의고사 1·2교시 종합" if is_combined_result else exam.title,
        "result_score": result["average"] if is_combined_result else result["sitting_score"],
        "result_correct_count": sum(item.user_answer_correct is True for item in items),
        "result_total_questions": len(items),
        "unanswered_items": unanswered_items,
        "answered_count": len(answered_items),
        "unanswered_count": len(unanswered_items),
        "analysis": analysis,
        "is_premium": access.is_premium,
        "has_full_access": has_full_access,
        "recommend_missions": recommend_missions,
    })


@login_required
def exam_wrong_answers(request, exam_id):
    """Paginated wrong answers for one exam or one linked full-exam attempt."""
    current_subject, _ = get_current_subject(request)
    exam = get_object_or_404(
        ExamSession.objects.filter(items__mission__subject=current_subject).distinct(),
        id=exam_id,
        user=request.user,
    )
    if exam.status == "waiting":
        exam = exam.previous_sitting

    sessions = result_sessions(exam)
    wrong_items = (
        ExamSessionMission.objects
        .filter(
            exam_session__in=sessions,
            mission__subject=current_subject,
            submitted_at__isnull=False,
            user_answer_correct=False,
        )
        .select_related("mission", "exam_session")
        .order_by("exam_session__started_at", "order_no")
    )
    page_obj = Paginator(wrong_items, 20).get_page(request.GET.get("page"))
    session_numbers = {session.pk: number for number, session in enumerate(sessions, 1)}
    for item in page_obj.object_list:
        item.mission.skill_label = item.mission.chapter_name or get_skill_label(item.mission.skill)
        item.sitting_number = session_numbers[item.exam_session_id] if len(sessions) > 1 else None

    return render(request, "core/exam_wrong_answers.html", {
        "exam": exam,
        "page_obj": page_obj,
    })


@login_required
def exam_recommend_start(request, exam_id):
    """
    시험 결과에서 추천된 5문제 복습 루프 시작
    """
    current_subject, _ = get_current_subject(request)
    exam = get_object_or_404(
        ExamSession.objects
        .filter(items__mission__subject=current_subject)
        .distinct(),
        id=exam_id,
        user=request.user,
    )
    items = list(exam.items.select_related("mission").filter(mission__subject=current_subject))

    skill_rows = (
        exam.items.filter(mission__subject=current_subject, submitted_at__isnull=False)
        .values("mission__skill")
        .annotate(
            total=Count("id"),
            correct=Count("id", filter=Q(user_answer_correct=True)),
            wrong=Count("id", filter=Q(user_answer_correct=False)),
        )
        .order_by("mission__skill")
    )

    skill_rows = list(skill_rows)
    for row in skill_rows:
        total = row["total"] or 0
        correct = row["correct"] or 0
        row["accuracy"] = round((correct / total) * 100, 1) if total else 0.0

    wrong_items = [item for item in items if item.user_answer_correct is False]

    analysis = build_exam_analysis(
        exam=exam,
        skill_rows=skill_rows,
        wrong_items=wrong_items,
    )

    recommend_missions = []

    if analysis["weak_skills"]:
        weak_skill_names = [row["skill"] for row in analysis["weak_skills"]]

        recommend_missions = list(
            Mission.objects.filter(
                skill__in=weak_skill_names,
                is_usable_for_set=True,
                subject=current_subject,
            )
            .exclude(review_status=Mission.REVIEW_CONFIRMED_ERROR)
            .exclude(id__in=[item.mission.id for item in items])
            .order_by("?")[:5]
        )

    if recommend_missions:
        recommend_ids = [m.id for m in recommend_missions]

        request.session["review_mission_ids"] = recommend_ids
        request.session["review_current_index"] = 0
        request.session["review_return_exam_id"] = exam.id

        return redirect("mission_detail", mission_id=recommend_ids[0])

    return redirect("mission_list")

@login_required
def exam_history(request):
    """
    사용자의 시험 히스토리 목록
    """
    current_subject, _ = get_current_subject(request)
    exams = (
        ExamSession.objects
        .filter(user=request.user, items__mission__subject=current_subject)
        .distinct()
        .prefetch_related("items__mission")
        .order_by("-started_at")
    )
    return render(request, "core/exam_history.html", {
        "exams": exams,
        "history_cards": build_exam_history_cards(exams),
    })
