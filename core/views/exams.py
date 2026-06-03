from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

from core.models import Mission, ExamSession, ExamSessionMission
from core.services.access import get_user_access
from core.services.exams import (
    create_exam_session,
    submit_exam_answer,
    finish_exam_session,
)
from core.services.exam_analysis import build_exam_analysis
from core.services.grading import (
    parse_answer_schema,
    grade_answer,
    grade_multi_answer,
)




@login_required
def exam_start(request):
    """
    시험 시작 안내 페이지
    """
    access = get_user_access(request.user)
    return render(request, "core/exam_start.html", {
        "is_premium": access.is_premium,
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

    access = get_user_access(request.user)
    today = timezone.localdate()

    if not access.is_premium:
        today_exam_count = ExamSession.objects.filter(
            user=request.user,
            started_at__date=today,
        ).count()

        if today_exam_count >= 1:
            return render(request, "core/exam_start.html", {
                "limit_error": "무료 회원은 실전 모의고사를 하루 1회만 볼 수 있습니다.",
                "is_premium": access.is_premium,
            })

    exam = create_exam_session(user=request.user)
    first_item = exam.items.order_by("order_no").first()

    if not first_item:
        return redirect("mission_list")

    return redirect("exam_take", exam_id=exam.id, order_no=1)


@login_required
def exam_take(request, exam_id, order_no):
    exam = get_object_or_404(ExamSession, id=exam_id, user=request.user)

    if exam.status != "in_progress":
        return redirect("exam_result", exam_id=exam.id)

    item = get_object_or_404(
        ExamSessionMission.objects.select_related("mission", "exam_session"),
        exam_session=exam,
        order_no=order_no,
    )

    mission = item.mission
    total_count = exam.items.count()
    schema_items = parse_answer_schema(mission.answer_schema)

    if request.method == "POST":
        is_correct = None

        # 1) 수동 확인형 문제
        if mission.question_type == "manual":
            raw = request.POST.get("is_correct")

            if raw in ("true", "false"):
                is_correct = (raw == "true")

        # 2) 자동채점형 문제 - 멀티 입력
        elif schema_items:
            submitted_answers = request.POST.getlist("submitted_answers")

            grading_result = grade_multi_answer(
                submitted_answers=submitted_answers,
                schema_text=mission.answer_schema,
            )

            if grading_result["error"] is None:
                is_correct = grading_result["is_correct"]

        # 3) 자동채점형 문제 - 단일 입력
        else:
            submitted_answer = request.POST.get("submitted_answer", "").strip()

            grading_result = grade_answer(
                question_type=mission.question_type,
                answer_input_type=mission.answer_input_type,
                submitted_answer=submitted_answer,
                correct_answer=mission.correct_answer,
            )

            if grading_result["error"] is None:
                is_correct = grading_result["is_correct"]

        if is_correct is not None:
            submit_exam_answer(item, is_correct)

            next_order = order_no + 1
            if next_order <= total_count:
                return redirect("exam_take", exam_id=exam.id, order_no=next_order)
            else:
                finish_exam_session(exam)
                return redirect("exam_result", exam_id=exam.id)

    end_time = exam.started_at + timedelta(minutes=exam.time_limit_min)
    remaining_seconds = int((end_time - timezone.now()).total_seconds())

    return render(request, "core/exam_take.html", {
        "exam": exam,
        "item": item,
        "mission": mission,
        "order_no": order_no,
        "total_count": total_count,
        "remaining_seconds": max(remaining_seconds, 0),
        "schema_items": schema_items,
    })


@login_required
def exam_submit(request, exam_id):
    exam = get_object_or_404(ExamSession, id=exam_id, user=request.user)

    if exam.status == "in_progress":
        finish_exam_session(exam)

    return redirect("exam_result", exam_id=exam.id)


@login_required
def exam_result(request, exam_id):
    """
    시험 결과 페이지
    """
    exam = get_object_or_404(ExamSession, id=exam_id, user=request.user)
    items = exam.items.select_related("mission").all()
    access = get_user_access(request.user)

    skill_rows = (
        items.values("mission__skill")
        .annotate(
            total=Count("id"),
            correct=Count("id", filter=Q(user_answer_correct=True)),
            wrong=Count("id", filter=Q(user_answer_correct=False) | Q(user_answer_correct__isnull=True)),
        )
        .order_by("mission__skill")
    )

    skill_rows = list(skill_rows)
    for row in skill_rows:
        total = row["total"] or 0
        correct = row["correct"] or 0
        row["accuracy"] = round((correct / total) * 100, 1) if total else 0.0

    wrong_items = [item for item in items if item.user_answer_correct is not True]

    analysis = build_exam_analysis(
        exam=exam,
        skill_rows=skill_rows,
        wrong_items=wrong_items,
    )
    # 추천 문제 5개
    recommend_missions = []

    if analysis["weak_skills"]:
        weak_skill_names = [row["skill"] for row in analysis["weak_skills"]]

        recommend_missions = (
            Mission.objects.filter(skill__in=weak_skill_names)
            .exclude(
                id__in=[item.mission.id for item in items]
            )
            .order_by("?")[:5]
        )

    return render(request, "core/exam_result.html", {
        "exam": exam,
        "items": items,
        "skill_rows": skill_rows,
        "wrong_items": wrong_items,
        "analysis": analysis,
        "is_premium": access.is_premium,
        "recommend_missions": recommend_missions,
    })
@login_required
def exam_recommend_start(request, exam_id):
    """
    시험 결과에서 추천된 5문제 복습 루프 시작
    """
    exam = get_object_or_404(ExamSession, id=exam_id, user=request.user)
    items = exam.items.select_related("mission").all()

    skill_rows = (
        items.values("mission__skill")
        .annotate(
            total=Count("id"),
            correct=Count("id", filter=Q(user_answer_correct=True)),
            wrong=Count("id", filter=Q(user_answer_correct=False) | Q(user_answer_correct__isnull=True)),
        )
        .order_by("mission__skill")
    )

    skill_rows = list(skill_rows)
    for row in skill_rows:
        total = row["total"] or 0
        correct = row["correct"] or 0
        row["accuracy"] = round((correct / total) * 100, 1) if total else 0.0

    wrong_items = [item for item in items if item.user_answer_correct is not True]

    analysis = build_exam_analysis(
        exam=exam,
        skill_rows=skill_rows,
        wrong_items=wrong_items,
    )

    recommend_missions = []

    if analysis["weak_skills"]:
        weak_skill_names = [row["skill"] for row in analysis["weak_skills"]]

        recommend_missions = list(
            Mission.objects.filter(skill__in=weak_skill_names)
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
    exams = (
        ExamSession.objects
        .filter(user=request.user)
        .order_by("-started_at")
    )

    recent_exams = list(exams[:5])

    avg_score = 0
    if recent_exams:
        avg_score = round(sum(e.score for e in recent_exams) / len(recent_exams), 1)

    passed_count = sum(1 for e in recent_exams if e.score >= 60)
    total_count = len(recent_exams)
    pass_rate = round((passed_count / total_count) * 100, 1) if total_count else 0.0

    # 최근 5회 점수 목록 (오래된 것 → 최근 순으로 뒤집어서 표시)
    recent_scores = [e.score for e in reversed(recent_exams)]

    # 최고 점수
    best_score = max(recent_scores) if recent_scores else 0

    # 최근 점수 변화량
    score_change = 0
    if len(recent_scores) >= 2:
        score_change = recent_scores[-1] - recent_scores[-2]

    # 추이 판정
    trend_label = "데이터 부족"
    if len(recent_scores) >= 2:
        if recent_scores[-1] > recent_scores[0]:
            trend_label = "상승 중"
        elif recent_scores[-1] < recent_scores[0]:
            trend_label = "하락 중"
        else:
            trend_label = "변동 없음"

    return render(request, "core/exam_history.html", {
        "exams": exams,
        "recent_exams": recent_exams,
        "avg_score": avg_score,
        "passed_count": passed_count,
        "total_count": total_count,
        "pass_rate": pass_rate,
        "recent_scores": recent_scores,
        "best_score": best_score,
        "score_change": score_change,
        "trend_label": trend_label,
    })