from datetime import timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q, OuterRef, Subquery
from django.core.paginator import Paginator
from django.utils import timezone
from django.http import Http404
from uuid import UUID

from core.models import (
    Attempt,
    DailyMission,
    ExamSession,
    Mission,
    ProblemSet,
    ProblemSetSession,
    StudyProfile,
    UserStreak,
    WrongReason,
)
from core.services.attempts import save_attempt, AttemptSaveError
from core.services.daily import (
    build_daily_completion_summary,
    build_daily_study_plan,
    get_or_create_daily_recommendations,
    get_daily_done_ids,
    get_daily_progress,
)
from core.services.grading import (
    grade_answer,
    parse_answer_schema,
    parse_choice_schema,
    grade_multi_answer,
)
from core.services.problem_sets import (
    record_problem_set_item_review,
    submit_problem_set_item_answer,
    finish_problem_set_session,
)
from core.services.problem_set_recommendations import get_problem_set_recommendations
from core.services.skill_labels import get_skill_label
from core.services.analytics import record_event
from core.services.learning_dashboard import build_learning_dashboard
from core.services.learning_concepts import get_answer_display
from core.services.learning_feedback import build_mission_feedback
from core.services.logistics_curriculum import build_logistics_chapter_roadmap
from core.services.mission_cards import load_mission_cards, prepare_mission_cards, with_user_learning_state
from core.services.personal_coach import build_personal_coach_context
from core.services.pattern_training_context import build_pattern_training_context
from core.services.subjects import LOGISTICS_SUBJECT_CODE, get_current_subject, get_default_subject
from core.services.theory import build_subject_theory_roadmap, get_theory_chapter_context
from core.models import MissionWork
from core.services.learning_experience import experience_home, repetition_guidance, progress_evidence, diagnostic_state
from core.services.reliable_submission import reliable_submission
from core.services.exams import draft_has_answer


def get_today_action(user, subject=None):
    session = (
        ProblemSetSession.objects
        .filter(user=user, status="in_progress")
        .order_by("-started_at")
        .first()
    )
    if subject is not None:
        session = (
            ProblemSetSession.objects
            .filter(user=user, status="in_progress", items__mission__subject=subject)
            .distinct()
            .order_by("-started_at")
            .first()
        )

    if session:
        return "continue", session

    done_today_qs = (
        ProblemSetSession.objects
        .filter(
            user=user,
            status="completed",
            started_at__date=timezone.localdate(),
        )
    )
    if subject is not None:
        done_today_qs = done_today_qs.filter(items__mission__subject=subject).distinct()

    done_today = done_today_qs.exists()

    if not done_today:
        ps_qs = (
            ProblemSet.objects
            .filter(is_active=True, set_type="training")
        )
        if subject is not None:
            ps_qs = ps_qs.filter(items__mission__subject=subject).distinct()
        ps = ps_qs.order_by("-created_at").first()
        return "start", ps

    return "review", None


def get_weak_learning_type(user, subject=None):
    subject = subject or get_default_subject()
    latest_attempt_qs = (
        Attempt.objects.valid_for_learning()
        .filter(user=user, mission=OuterRef("pk"))
        .order_by("-created_at")
    )

    rows = (
        Mission.objects
        .filter(is_usable_for_set=True, subject=subject)
        .annotate(
            last_time=Subquery(latest_attempt_qs.values("created_at")[:1]),
            last_is_correct=Subquery(latest_attempt_qs.values("is_correct")[:1]),
        )
        .values("skill", "learning_type")
        .annotate(
            total=Count("id"),
            attempted=Count("id", filter=Q(last_time__isnull=False)),
            solved=Count("id", filter=Q(last_is_correct=True)),
            open=Count("id", filter=Q(last_is_correct=False)),
        )
        .filter(total__gte=3)
        .order_by("skill", "learning_type")
    )

    rows = list(rows)

    for row in rows:
        total = row["total"] or 0
        solved = row["solved"] or 0

        row["skill_label"] = get_skill_label(row["skill"])
        row["solve_rate"] = round((solved / total) * 100, 1) if total else 0.0

        if row["learning_type"] == "feature":
            row["learning_type_label"] = "기능 선택형"
        elif row["learning_type"] == "result":
            row["learning_type_label"] = "결과 예측형"
        elif row["learning_type"] == "error":
            row["learning_type_label"] = "오류 진단형"
        elif row["learning_type"] == "next_action":
            row["learning_type_label"] = "다음 행동형"
        elif row["learning_type"] == "procedure":
            row["learning_type_label"] = "절차 순서형"
        else:
            row["learning_type_label"] = row["learning_type"]

    if not rows:
        return None

    return sorted(
        rows,
        key=lambda row: (
            row["solve_rate"],
            -row["attempted"],
            row["skill_label"],
        )
    )[0]

def get_learning_roadmap(user, subject=None):
    subject = subject or get_default_subject()
    latest_attempt_qs = (
        Attempt.objects.valid_for_learning()
        .filter(user=user, mission=OuterRef("pk"))
        .order_by("-created_at")
    )

    rows = (
        Mission.objects
        .filter(is_usable_for_set=True, subject=subject)
        .annotate(
            last_time=Subquery(latest_attempt_qs.values("created_at")[:1]),
            last_is_correct=Subquery(latest_attempt_qs.values("is_correct")[:1]),
        )
        .values("skill", "learning_type")
        .annotate(
            total=Count("id"),
            attempted=Count("id", filter=Q(last_time__isnull=False)),
            solved=Count("id", filter=Q(last_is_correct=True)),
            open=Count("id", filter=Q(last_is_correct=False)),
        )
        .filter(total__gte=3)
        .order_by("skill", "learning_type")
    )

    grouped = {}

    for row in rows:
        skill = row["skill"]
        learning_type = row["learning_type"]
        total = row["total"] or 0
        attempted = row["attempted"] or 0
        solved = row["solved"] or 0
        solve_rate = round((solved / total) * 100, 1) if total else 0.0
        attempt_accuracy = round((solved / attempted) * 100, 1) if attempted else 0.0

        if skill not in grouped:
            grouped[skill] = {
                "skill": skill,
                "skill_label": get_skill_label(skill),
                "steps": [],
            }

        if learning_type == "feature":
            label = "기능 선택형"
            order = 1
        elif learning_type == "result":
            label = "결과 예측형"
            order = 2
        elif learning_type == "error":
            label = "오류 진단형"
            order = 3
        elif learning_type in {"practical", "practice"}:
            label = "실전형"
            order = 4
        else:
            label = learning_type
            order = 99

        if attempted == 0:
            status = "미시작"
        elif attempt_accuracy >= 80 and attempted >= 5:
            status = "완료"
        elif attempt_accuracy >= 50:
            status = "학습중"
        else:
            status = "복습필요"

        grouped[skill]["steps"].append({
            "learning_type": learning_type,
            "label": label,
            "order": order,
            "total": total,
            "attempted": attempted,
            "solved": solved,
            "solve_rate": solve_rate,
            "attempt_accuracy": attempt_accuracy,
            "status": status,
        })

    roadmap = list(grouped.values())

    for item in roadmap:
        item["steps"] = sorted(item["steps"], key=lambda step: step["order"])

        previous_completed = True

        for step in item["steps"]:
            step["is_locked"] = not previous_completed

            if step["attempt_accuracy"] >= 80 and step["attempted"] >= 5:
                step["is_completed"] = True
            else:
                step["is_completed"] = False

            previous_completed = step["is_completed"]

        completed_count = sum(1 for step in item["steps"] if step["is_completed"])
        locked_count = sum(1 for step in item["steps"] if step["is_locked"])
        review_count = sum(
            1
            for step in item["steps"]
            if (not step["is_locked"]) and step["status"] == "복습필요"
        )

        if completed_count == len(item["steps"]):
            item["roadmap_class"] = "roadmap-card-complete"
            item["roadmap_status_label"] = "스킬 완료"
        elif review_count > 0:
            item["roadmap_class"] = "roadmap-card-review"
            item["roadmap_status_label"] = "복습 필요"
        elif locked_count > 0:
            item["roadmap_class"] = "roadmap-card-locked"
            item["roadmap_status_label"] = "단계 잠금 있음"
        else:
            item["roadmap_class"] = "roadmap-card-progress"
            item["roadmap_status_label"] = "학습 진행중"

    return roadmap[:5]

def get_next_learning_step(learning_roadmap):
    for item in learning_roadmap:
        for step in item["steps"]:
            if not step.get("is_locked") and not step.get("is_completed"):
                return {
                    "skill": item["skill"],
                    "skill_label": item["skill_label"],
                    "learning_type": step["learning_type"],
                    "learning_type_label": step["label"],
                    "status": step["status"],
                    "solve_rate": step["solve_rate"],
                }

    return None

@login_required
def learning_type_training_start(request, skill, learning_type):
    request.session.pop("learning_type_training_skill", None)
    request.session.pop("learning_type_training_learning_type", None)
    request.session.pop("learning_type_training_mission_ids", None)
    request.session.pop("learning_type_training_index", None)
    request.session.pop("learning_type_training_results", None)

    latest_attempt_qs = (
        Attempt.objects.valid_for_learning()
        .filter(user=request.user, mission=OuterRef("pk"))
        .order_by("-created_at")
    )

    current_subject, _ = get_current_subject(request)
    candidate_missions = list(
        Mission.objects
        .filter(
            skill=skill,
            learning_type=learning_type,
            is_usable_for_set=True,
            subject=current_subject,
        )
        .annotate(
            last_time=Subquery(latest_attempt_qs.values("created_at")[:1]),
            last_is_correct=Subquery(latest_attempt_qs.values("is_correct")[:1]),
        )
        .order_by(
            "last_is_correct",
            "last_time",
            "level",
            "id",
        )[:50]
    )

    missions = [mission.id for mission in candidate_missions[:5]]

    if not missions:
        messages.warning(
            request,
            "이 학습 단계에는 현재 훈련 가능한 문제가 없습니다. 관리자에게 문의하거나 문제를 추가하세요.",
        )
        return redirect("mission_list")

    request.session["learning_type_training_skill"] = skill
    request.session["learning_type_training_learning_type"] = learning_type
    request.session["learning_type_training_mission_ids"] = missions
    request.session["learning_type_training_index"] = 0
    request.session["learning_type_training_results"] = []
    request.session.modified = True

    return redirect("mission_detail", mission_id=missions[0])

@login_required
def learning_type_training_result(request, skill, learning_type):
    results = request.session.get("learning_type_training_results", [])

    total = len(results)
    correct = sum(1 for row in results if row.get("is_correct") is True)
    wrong = total - correct
    score = round((correct / total) * 100) if total else 0

    if learning_type == "feature":
        learning_type_label = "기능 선택형"
    elif learning_type == "result":
        learning_type_label = "결과 예측형"
    elif learning_type == "error":
        learning_type_label = "오류 진단형"
    elif learning_type == "next_action":
        learning_type_label = "다음 행동형"
    elif learning_type == "procedure":
        learning_type_label = "절차 순서형"
    else:
        learning_type_label = learning_type

    request.session.pop("learning_type_training_skill", None)
    request.session.pop("learning_type_training_learning_type", None)
    request.session.pop("learning_type_training_results", None)

    return render(request, "core/learning_type_training_result.html", {
        "skill": skill,
        "skill_label": get_skill_label(skill),
        "learning_type": learning_type,
        "learning_type_label": learning_type_label,
        "results": results,
        "total": total,
        "correct": correct,
        "wrong": wrong,
        "score": score,
    })

@login_required
def mission_list(request):
    q = request.GET.get("q", "").strip()
    skill = request.GET.get("skill", "").strip()
    level = request.GET.get("level", "").strip()
    sort = request.GET.get("sort", "new").strip()

    current_subject, subject_needs_selection = get_current_subject(request)
    subject_mission_count = Mission.objects.filter(subject=current_subject).count()
    qs = Mission.objects.filter(subject=current_subject)
    recommendation_qs = with_user_learning_state(
        Mission.objects.filter(subject=current_subject, is_usable_for_set=True).exclude(
            review_status=Mission.REVIEW_CONFIRMED_ERROR,
        ),
        request.user,
    ).order_by("id")

    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(prompt__icontains=q)
            | Q(skill__icontains=q)
        )

    if skill:
        qs = qs.filter(skill=skill)

    if level.isdigit():
        qs = qs.filter(level=int(level))

    qs = with_user_learning_state(qs, request.user)

    if sort == "untried":
        qs = qs.order_by("my_total", "-created_at")
    elif sort == "weak":
        qs = qs.order_by("my_last_is_correct", "-my_wrong", "my_correct", "-my_total", "-created_at")
    else:
        qs = qs.order_by("-created_at")

    paginator = Paginator(qs, 10)
    page_number = request.GET.get("page", "1")
    page_obj = paginator.get_page(page_number)

    prepare_mission_cards(page_obj.object_list)

    profile, _ = StudyProfile.objects.get_or_create(user=request.user)
    requested_minutes = request.GET.get("minutes", "").strip()
    if requested_minutes in {"5", "10", "20"}:
        profile.daily_minutes = int(requested_minutes)
        profile.save(update_fields=["daily_minutes", "updated_at"])
    daily_question_limit = {5: 3, 10: 5, 20: 10}.get(profile.daily_minutes, 5)
    reset_daily = request.GET.get("reset_daily") == "1" or bool(requested_minutes)

    recommended, today_str, today_date = get_or_create_daily_recommendations(
        user=request.user,
        annotated_qs=recommendation_qs,
        reset_daily=reset_daily,
        subject=current_subject,
        recommendation_limit=daily_question_limit,
    )

    prepare_mission_cards(recommended)

    done_ids = get_daily_done_ids(request.user, today_date, subject=current_subject)

    for m in recommended:
        m.today_done = (m.id in done_ids)

    today_start_mission = next(
        (mission for mission in recommended if not mission.today_done),
        None,
    )

    skill_choices = (
        Mission.objects
        .filter(subject=current_subject)
        .values_list("skill", flat=True)
        .distinct()
        .order_by("skill")
    )

    daily_progress = get_daily_progress(request.user, today_date, subject=current_subject)
    daily_study_plan = build_daily_study_plan(
        request.user,
        recommended,
        done_ids=done_ids,
        today=today_date,
    )
    streak, _ = UserStreak.objects.get_or_create(user=request.user)
    dashboard = build_learning_dashboard(request.user, streak=streak, subject=current_subject)
    personal_coach = build_personal_coach_context(request.user, current_subject, streak=streak)

    recommendation_data = get_problem_set_recommendations(request.user, subject=current_subject)
    recommendation_data["pattern_missions"] = load_mission_cards(
        recommendation_data["pattern_missions"],
        request.user,
    )

    auto_start = request.GET.get("auto", "0") == "1"

    if auto_start and recommendation_data["today_sets"]:
        primary_set_for_auto = recommendation_data["today_sets"][0]
        return redirect("problem_set_start", set_id=primary_set_for_auto.id)

    weak_skill_labels = [
        get_skill_label(skill)
        for skill in recommendation_data["weak_skills"]
    ]

    primary_set = None
    if recommendation_data["today_sets"]:
        primary_set = recommendation_data["today_sets"][0]
    elif recommendation_data["weak_sets"]:
        primary_set = recommendation_data["weak_sets"][0]

    recent_sessions = (
        ProblemSetSession.objects
        .filter(user=request.user, status="completed", items__mission__subject=current_subject)
        .distinct()
        .order_by("-started_at")[:3]
    )
    recent_attempts = list(
        Attempt.objects.valid_for_learning().filter(
            user=request.user, mission__subject=current_subject
        )
        .select_related("mission")
        .order_by("-created_at")[:3]
    )
    for attempt in recent_attempts:
        attempt.skill_label = attempt.mission.chapter_name or get_skill_label(attempt.mission.skill)
    ongoing_exam = (
        ExamSession.objects.filter(
            user=request.user,
            status="in_progress",
            items__mission__subject=current_subject,
        )
        .distinct()
        .order_by("-started_at")
        .first()
    )
    ongoing_exam_context = None
    if ongoing_exam:
        exam_items = list(ongoing_exam.items.order_by("order_no"))
        answered = sum(
            draft_has_answer(item.draft_answers) or item.submitted_at is not None
            for item in exam_items
        )
        resume_item = next(
            (item for item in exam_items if not draft_has_answer(item.draft_answers) and item.submitted_at is None),
            exam_items[0] if exam_items else None,
        )
        deadline = ongoing_exam.started_at + timedelta(minutes=ongoing_exam.time_limit_min)
        ongoing_exam_context = {
            "exam": ongoing_exam,
            "answered": answered,
            "total": len(exam_items),
            "resume_order": resume_item.order_no if resume_item else 1,
            "expired": timezone.now() >= deadline,
        }
    today_action, today_action_obj = get_today_action(request.user, subject=current_subject)
    is_logistics_subject = current_subject.code == LOGISTICS_SUBJECT_CODE
    weak_learning_type = None
    learning_roadmap = []
    logistics_chapter_roadmap = []
    theory_roadmap = build_subject_theory_roadmap(request.user, current_subject)

    if is_logistics_subject:
        logistics_chapter_roadmap = build_logistics_chapter_roadmap(
            request.user,
            current_subject,
        )
        next_learning_step = None
    else:
        weak_learning_type = get_weak_learning_type(request.user, subject=current_subject)
        learning_roadmap = get_learning_roadmap(request.user, subject=current_subject)
        next_learning_step = get_next_learning_step(learning_roadmap)

    if today_start_mission and today_start_mission.chapter_code:
        chapter_label = today_start_mission.chapter_name or today_start_mission.course or "현재 챕터"
        today_guide_message = (
            f"{chapter_label}의 미학습 문제부터 시작하고, 마지막에는 약점 문제를 복습합니다."
        )
        today_guide_url_name = "daily_mission"
        today_guide_skill = ""
        today_guide_learning_type = ""
        today_guide_text = "오늘 학습 시작"
    elif next_learning_step:
        today_guide_message = (
            f"{next_learning_step['skill_label']} "
            f"{next_learning_step['learning_type_label']} 단계가 "
            f"{next_learning_step['status']} 상태입니다. "
            "이 단계부터 먼저 학습하세요."
        )
        today_guide_url_name = "learning_type_training_start"
        today_guide_skill = next_learning_step["skill"]
        today_guide_learning_type = next_learning_step["learning_type"]
        today_guide_text = (
            f"{next_learning_step['skill_label']} "
            f"{next_learning_step['learning_type_label']} 훈련 시작"
        )
    else:
        today_guide_message = "오늘은 기본 학습 세트부터 시작하세요."
        today_guide_url_name = "problem_set_list"
        today_guide_skill = ""
        today_guide_learning_type = ""
        today_guide_text = "오늘 학습 시작"

    today_guide_pattern_code = ""

    if personal_coach["dday_phase"] == "final" and personal_coach["confusion_cards"]:
        today_guide_message = "시험 직전에는 새 범위보다 내가 실제로 헷갈린 내용부터 확인하세요."
        today_guide_url_name = "final_cards"
        today_guide_text = "나의 시험 직전 카드 보기"

    if (
        personal_coach["return_mode"]
        and personal_coach["dday_phase"] != "final"
        and today_start_mission
    ):
        today_guide_message = (
            f"{personal_coach['return_days']}일 만의 복귀 학습입니다. "
            "부담 없이 추천 문제 3개로 감각부터 되찾으세요."
        )
        today_guide_url_name = "daily_mission"
        today_guide_text = "3분 복귀 학습 시작"

    if (
        today_guide_url_name not in ("daily_mission", "final_cards")
        and not next_learning_step
        and recommendation_data["weak_patterns"]
    ):
        top_pattern = recommendation_data["weak_patterns"][0]

        today_guide_message = (
            f"{top_pattern['wrong_pattern__name']} 패턴이 반복되고 있습니다. "
            "먼저 이 약점을 집중 훈련하세요."
        )
        today_guide_url_name = "pattern_training_start"
        today_guide_pattern_code = top_pattern["wrong_pattern__code"]
        today_guide_text = "약점 집중 훈련 시작"

    return render(request, "core/mission_list.html", {
        "missions": page_obj,
        "page_obj": page_obj,
        "q": q,
        "skill": skill,
        "level": level,
        "sort": sort,
        "skill_choices": skill_choices,
        "recommended": recommended,
        "today": today_str,
        "daily_progress": daily_progress,
        "daily_study_plan": daily_study_plan,
        "selected_daily_minutes": profile.daily_minutes,
        "streak": streak,
        "today_sets": recommendation_data["today_sets"],
        "recent_sessions": recent_sessions,
        "recent_attempts": recent_attempts,
        "weak_sets": recommendation_data["weak_sets"],
        "weak_skills": recommendation_data["weak_skills"],
        "weak_patterns": recommendation_data["weak_patterns"],
        "pattern_missions": recommendation_data["pattern_missions"],
        "weak_skill_labels": weak_skill_labels,
        "primary_set": primary_set,
        "target_level": recommendation_data["target_level"],
        "recent_avg_score": recommendation_data["recent_avg_score"],
        "today_action": today_action,
        "today_action_obj": today_action_obj,
        "today_guide_message": today_guide_message,
        "today_guide_url_name": today_guide_url_name,
        "today_guide_pattern_code": today_guide_pattern_code,
        "today_guide_skill": today_guide_skill,
        "today_guide_learning_type": today_guide_learning_type,
        "today_guide_text": today_guide_text,
        "today_start_mission": today_start_mission,
        "weak_learning_type": weak_learning_type,
        "learning_roadmap": learning_roadmap,
        "logistics_chapter_roadmap": logistics_chapter_roadmap,
        "theory_roadmap": theory_roadmap,
        "is_logistics_subject": is_logistics_subject,
        "dashboard": dashboard,
        "personal_coach": personal_coach,
        "current_subject": current_subject,
        "subject_needs_selection": subject_needs_selection,
        "subject_mission_count": subject_mission_count,
        "learning_experience": experience_home(request.user, current_subject),
        "ongoing_exam": ongoing_exam_context,
    })


@login_required
@reliable_submission
def mission_detail(request, mission_id):
    current_subject, _ = get_current_subject(request)
    mission = get_object_or_404(Mission, id=mission_id, subject=current_subject)
    pattern_training = build_pattern_training_context(request, current_subject, mission)
    wrong_reasons = WrongReason.objects.all()

    saved = False
    error = None
    saved_is_correct = None
    grading_rows = []
    next_daily_mission = None
    saved_attempt = None
    if request.method == "GET" and request.GET.get("attempt"):
        if not request.GET["attempt"].isdigit():
            raise Http404
        saved_attempt = get_object_or_404(Attempt, pk=request.GET["attempt"], user=request.user, mission=mission)
        saved = True
        saved_is_correct = saved_attempt.is_correct
    if request.method == "GET" and request.GET.get("work"):
        try:
            work_id = UUID(request.GET["work"])
        except ValueError:
            raise Http404
        work = get_object_or_404(MissionWork, pk=work_id, user=request.user, mission=mission)
        if work.attempt_id:
            return redirect(work.return_url)
    work = None
    if not saved:
        work, _ = MissionWork.objects.get_or_create(user=request.user, mission=mission, attempt__isnull=True)
    schema_items = parse_answer_schema(mission.answer_schema)
    choice_items = parse_choice_schema(mission.answer_schema)
    mission_event_metadata = {
        "mission_id": mission.id,
        "skill": mission.skill,
        "question_type": mission.question_type,
    }
    active_problem_set_ids = request.session.get("problem_set_mission_ids", [])
    if pattern_training:
        submit_button_label = "훈련 결과 확인" if pattern_training["is_last"] else "다음 훈련 문제"
    elif mission.question_type == "manual":
        submit_button_label = "학습 결과 저장"
    elif mission.id in active_problem_set_ids:
        current_position = active_problem_set_ids.index(mission.id)
        submit_button_label = "결과 확인" if current_position == len(active_problem_set_ids) - 1 else "다음 문제"
    else:
        submit_button_label = "답안 제출"

    if request.method == "GET":
        record_event(
            request.user,
            "start_mission",
            page="mission_detail",
            metadata=mission_event_metadata,
        )

    def handle_problem_set_progress(is_correct: bool, attempt=None):
        problem_set_ids = request.session.get("problem_set_mission_ids", [])
        problem_set_id = request.session.get("problem_set_id")
        problem_set_session_id = request.session.get("problem_set_session_id")

        if not problem_set_ids or mission.id not in problem_set_ids:
            return None
        
        wrong_retry_return_session_id = request.session.get("wrong_retry_return_session_id")

        if wrong_retry_return_session_id:
            retry_results = request.session.get("wrong_retry_results", [])

            retry_results.append({
                "mission_id": mission.id,
                "mission_title": mission.title,
                "is_correct": is_correct,
            })

            request.session["wrong_retry_results"] = retry_results
            request.session.modified = True

            original_session = ProblemSetSession.objects.filter(
                id=wrong_retry_return_session_id,
                user=request.user,
            ).first()
            if original_session:
                record_problem_set_item_review(
                    session=original_session,
                    mission_id=mission.id,
                    is_correct=is_correct,
                )
            
        problem_set_session = (
            ProblemSetSession.objects
            .filter(id=problem_set_session_id, user=request.user)
            .first()
        )

        if problem_set_session:
            submit_problem_set_item_answer(
                session=problem_set_session,
                mission_id=mission.id,
                is_correct=is_correct,
                submitted_answer=getattr(attempt, "submitted_answer", ""),
                attempt=attempt,
            )

        current_index = problem_set_ids.index(mission.id)
        next_index = current_index + 1

        if next_index < len(problem_set_ids):
            next_mission_id = problem_set_ids[next_index]
            request.session["problem_set_current_index"] = next_index
            return redirect("mission_detail", mission_id=next_mission_id)

        if problem_set_session:
            finish_problem_set_session(problem_set_session)
            record_event(
                request.user,
                "finish_problem_set",
                page="problem_set",
                metadata={
                    "problem_set_id": problem_set_session.problem_set_id,
                    "session_id": problem_set_session.id,
                    "score": problem_set_session.score,
                    "total_count": problem_set_session.total_count,
                },
            )

        request.session.pop("problem_set_mission_ids", None)
        request.session.pop("problem_set_current_index", None)
        request.session.pop("problem_set_id", None)
        request.session.pop("problem_set_session_id", None)

        if problem_set_session:
            return redirect("problem_set_result", session_id=problem_set_session.id)

        wrong_retry_return_session_id = request.session.get("wrong_retry_return_session_id")

        if wrong_retry_return_session_id:
            request.session.pop("wrong_retry_return_session_id", None)
            return redirect(
                "problem_set_wrong_retry_result",
                session_id=wrong_retry_return_session_id,
            )
        
        if problem_set_id:
            return redirect("problem_set_detail", set_id=problem_set_id)

        return redirect("problem_set_list")

    def handle_review_progress():
        review_ids = request.session.get("review_mission_ids", [])
        return_exam_id = request.session.get("review_return_exam_id")

        if not review_ids or mission.id not in review_ids:
            return None

        current_index = review_ids.index(mission.id)
        next_index = current_index + 1

        if next_index < len(review_ids):
            next_mission_id = review_ids[next_index]
            request.session["review_current_index"] = next_index
            return redirect("mission_detail", mission_id=next_mission_id)

        request.session.pop("review_mission_ids", None)
        request.session.pop("review_current_index", None)
        request.session.pop("review_return_exam_id", None)

        if return_exam_id:
            return redirect("exam_result", exam_id=return_exam_id)

        return redirect("mission_list")
    
    def get_next_daily_mission():
        today = timezone.localdate()

        daily_mission_ids = list(
            DailyMission.objects
            .filter(user=request.user, date=today, mission__subject=current_subject)
            .order_by("id")
            .values_list("mission_id", flat=True)
        )

        if not daily_mission_ids or mission.id not in daily_mission_ids:
            return None

        done_ids = set(
            Attempt.objects.valid_for_learning()
            .filter(user=request.user, daily_date=today, mission__subject=current_subject)
            .values_list("mission_id", flat=True)
        )

        for next_mission_id in daily_mission_ids:
            if next_mission_id != mission.id and next_mission_id not in done_ids:
                return Mission.objects.filter(
                    id=next_mission_id,
                    is_usable_for_set=True,
                    subject=current_subject,
                ).first()

        return None

    def handle_learning_type_training_progress(is_correct: bool):
        mission_ids = request.session.get("learning_type_training_mission_ids", [])
        index = request.session.get("learning_type_training_index", 0)
        skill = request.session.get("learning_type_training_skill")
        learning_type = request.session.get("learning_type_training_learning_type")

        if not mission_ids:
            return None

        if mission.id not in mission_ids:
            return None

        results = request.session.get("learning_type_training_results", [])
        results = list(results)

        results.append({
            "mission_id": mission.id,
            "mission_title": mission.title,
            "is_correct": is_correct,
        })

        request.session["learning_type_training_results"] = results

        next_index = index + 1
        request.session["learning_type_training_index"] = next_index
        request.session.modified = True

        if next_index >= len(mission_ids):
            request.session.pop("learning_type_training_mission_ids", None)
            request.session.pop("learning_type_training_index", None)

            return redirect(
                "learning_type_training_result",
                skill=skill,
                learning_type=learning_type,
            )

        next_mission_id = mission_ids[next_index]
        return redirect("mission_detail", mission_id=next_mission_id)
    
    def handle_pattern_training_progress(is_correct: bool, attempt=None):
        pattern_code = request.session.get("pattern_training_pattern_code")
        mission_ids = request.session.get("pattern_training_mission_ids", [])
        index = request.session.get("pattern_training_index", 0)

        if not pattern_code or not mission_ids:
            return None

        if mission.id not in mission_ids:
            return None

        results = request.session.get("pattern_training_results", [])

        results = list(results)

        attempt_id = attempt.id if attempt is not None else None
        if attempt_id and not any(row.get("attempt_id") == attempt_id for row in results):
            results.append({
                "mission_id": mission.id,
                "attempt_id": attempt_id,
                "is_correct": is_correct,
            })

        request.session["pattern_training_results"] = results

        next_index = index + 1

        request.session["pattern_training_index"] = next_index
        request.session.modified = True

        if next_index >= len(mission_ids):
            request.session.pop("pattern_training_pattern_code", None)
            request.session.pop("pattern_training_mission_ids", None)
            request.session.pop("pattern_training_index", None)

            return redirect(
                "pattern_training_result",
                pattern_code=pattern_code,
            )

        next_mission_id = mission_ids[next_index]

        return redirect("mission_detail", mission_id=next_mission_id)
    
    def handle_after_save_redirect(is_correct: bool, attempt=None):
        """
        저장 후 이동 처리

        원칙:
        - 일반 문제 세트: 맞아도/틀려도 다음 문제로 이동
        - 시험 결과 추천 복습: 맞아도/틀려도 다음 문제로 이동
        - 틀린 문제 다시 풀기: 틀려도 다음 문제로 이동
        단, 결과 페이지에서 다시 틀린 문제를 확인하게 한다.
        """
        learning_type_training_redirect = handle_learning_type_training_progress(is_correct=is_correct)
        if learning_type_training_redirect:
            return learning_type_training_redirect

        pattern_training_redirect = handle_pattern_training_progress(
            is_correct=is_correct,
            attempt=attempt,
        )
        if pattern_training_redirect:
            return pattern_training_redirect
        
        problem_set_redirect = handle_problem_set_progress(is_correct=is_correct, attempt=attempt)
        if problem_set_redirect:
            return problem_set_redirect

        review_redirect = handle_review_progress()
        if review_redirect:
            return review_redirect

        return None

    if request.method == "POST":
        confidence_level = request.POST.get("confidence_level", "").strip()
        if confidence_level not in {value for value, _ in Attempt.CONFIDENCE_CHOICES}:
            confidence_level = ""
        quick_wrong_reason_ids = [
            int(value) for value in request.POST.getlist("wrong_reason_ids")
            if str(value).isdigit()
        ]
        if mission.question_type != "manual":
            if schema_items:
                submitted_answers = request.POST.getlist("submitted_answers")

                grading_result = grade_multi_answer(
                    submitted_answers=submitted_answers,
                    schema_text=mission.answer_schema,
                )

                error = grading_result["error"]
                saved_is_correct = grading_result["is_correct"]
                grading_rows = grading_result["results"]

                if error is None:
                    try:
                        attempt = save_attempt(
                            user=request.user,
                            mission=mission,
                            is_correct=saved_is_correct,
                            wrong_reason_ids=quick_wrong_reason_ids if not saved_is_correct else None,
                            submitted_answer=" | ".join(
                                row["submitted_answer"] for row in grading_rows
                            ),
                            confidence_level=confidence_level,
                        )

                        attempt.submitted_answer = " | ".join(
                            row["submitted_answer"] for row in grading_rows
                        )
                        attempt.save(update_fields=["submitted_answer"])
                        saved_attempt = attempt

                        saved = True
                        record_event(
                            request.user,
                            "finish_mission",
                            page="mission_detail",
                            metadata={
                                **mission_event_metadata,
                                "is_correct": saved_is_correct,
                            },
                        )

                        after_save_redirect = handle_after_save_redirect(
                            is_correct=saved_is_correct,
                            attempt=attempt,
                        )
                        if after_save_redirect:
                            return after_save_redirect

                    except AttemptSaveError as e:
                        error = str(e)

            else:
                submitted_answer = request.POST.get("submitted_answer", "").strip()

                grading_result = grade_answer(
                    question_type=mission.question_type,
                    answer_input_type=mission.answer_input_type,
                    submitted_answer=submitted_answer,
                    correct_answer=mission.correct_answer,
                )

                error = grading_result["error"]
                saved_is_correct = grading_result["is_correct"]

                if error is None:
                    try:
                        attempt = save_attempt(
                            user=request.user,
                            mission=mission,
                            is_correct=saved_is_correct,
                            wrong_reason_ids=quick_wrong_reason_ids if not saved_is_correct else None,
                            submitted_answer=submitted_answer,
                            confidence_level=confidence_level,
                        )
                        attempt.submitted_answer = submitted_answer
                        attempt.save(update_fields=["submitted_answer"])
                        saved_attempt = attempt

                        saved = True
                        record_event(
                            request.user,
                            "finish_mission",
                            page="mission_detail",
                            metadata={
                                **mission_event_metadata,
                                "is_correct": saved_is_correct,
                            },
                        )

                        after_save_redirect = handle_after_save_redirect(
                            is_correct=saved_is_correct,
                            attempt=attempt,
                        )
                        if after_save_redirect:
                            return after_save_redirect

                    except AttemptSaveError as e:
                        error = str(e)

        else:
            raw = request.POST.get("is_correct")

            if raw not in ("true", "false"):
                error = "정답/오답을 선택하고 제출하세요."
            else:
                saved_is_correct = (raw == "true")
                only_int_ids = []

                if not saved_is_correct:
                    selected_ids = request.POST.getlist("wrong_reason_ids")

                    if not selected_ids:
                        error = "오답을 선택했으면 오답 원인도 최소 1개 체크하세요."
                    else:
                        for x in selected_ids:
                            if str(x).isdigit():
                                only_int_ids.append(int(x))

                        if not only_int_ids:
                            error = "오답 원인이 올바르지 않습니다."

                if error is None:
                    try:
                        attempt = save_attempt(
                            user=request.user,
                            mission=mission,
                            is_correct=saved_is_correct,
                            wrong_reason_ids=None if saved_is_correct else only_int_ids,
                            confidence_level=confidence_level,
                        )
                        saved_attempt = attempt

                        saved = True
                        record_event(
                            request.user,
                            "finish_mission",
                            page="mission_detail",
                            metadata={
                                **mission_event_metadata,
                                "is_correct": saved_is_correct,
                            },
                        )

                        after_save_redirect = handle_after_save_redirect(
                            is_correct=saved_is_correct,
                            attempt=attempt,
                        )
                        if after_save_redirect:
                            return after_save_redirect

                    except AttemptSaveError as e:
                        error = str(e)
    if saved:
        next_daily_mission = get_next_daily_mission()
    related_theory_chapter = None
    related_learning_concept = None
    mission_feedback = None
    correction_mission = None
    if saved and saved_is_correct is False:
        mission_feedback = build_mission_feedback(
            mission,
            saved_attempt.submitted_answer if saved_attempt else "",
        )
        related_learning_concept = mission_feedback["learning_concept"]
        if mission.chapter_code:
            theory_context = get_theory_chapter_context(
                request.user,
                current_subject,
                mission.chapter_code,
            )
            if theory_context and theory_context["chapter"]["has_theory"]:
                related_theory_chapter = theory_context["chapter"]
        if mission.variation_group:
            correction_mission = (
                Mission.objects.filter(
                    subject=current_subject,
                    variation_group=mission.variation_group,
                    is_usable_for_set=True,
                )
                .exclude(id=mission.id)
                .order_by("level", "id")
                .first()
            )

    daily_completion = None
    if saved and next_daily_mission is None:
        today_date = timezone.localdate()
        is_daily_mission = DailyMission.objects.filter(
            user=request.user,
            date=today_date,
            mission=mission,
        ).exists()
        if is_daily_mission:
            daily_completion = get_daily_progress(
                request.user,
                today_date,
                subject=current_subject,
            )
            daily_completion.update(build_daily_completion_summary(
                request.user,
                today_date,
                subject=current_subject,
            ))
    return render(request, "core/mission_detail.html", {
        "mission": mission,
        "wrong_reasons": wrong_reasons,
        "saved": saved,
        "error": error,
        "saved_is_correct": saved_is_correct,
        "saved_attempt": saved_attempt,
        "schema_items": schema_items,
        "choice_items": choice_items,
        "grading_rows": grading_rows,
        "next_daily_mission": next_daily_mission,
        "related_theory_chapter": related_theory_chapter,
        "related_learning_concept": related_learning_concept,
        "mission_feedback": mission_feedback,
        "correction_mission": correction_mission,
        "daily_completion": daily_completion,
        "saved_answer_display": get_answer_display(mission, saved_attempt.submitted_answer if saved_attempt else ""),
        "correct_answer_display": get_answer_display(mission, mission.correct_answer),
        "submit_button_label": submit_button_label,
        "work": work,
        "draft_answers": work.answers if work else {},
        "repetition_guidance": repetition_guidance(request.user, mission) if saved_is_correct is False else None,
        "progress_evidence": progress_evidence(request.user, saved_attempt),
        "diagnostic": diagnostic_state(request.user, current_subject),
        "pattern_training": pattern_training,
    })
