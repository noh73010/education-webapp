from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.models import Attempt, CourseFocus, Mission, MissionWork, RealtorStudyPath, Subject
from core.services.realtor_curriculum import (
    REALTOR_EXAM_GUIDE, REALTOR_SITTINGS, REALTOR_SUBJECT_CODE, courses_for_path,
)
from core.services.theory import build_subject_theory_roadmap

from core.services.subjects import (
    CURRENT_SUBJECT_SESSION_KEY,
    get_active_subjects,
    set_current_subject,
)
from core.services.access import premium_gating_enabled
from core.services.content_sources import logistics_source_notices


def landing(request):
    subjects = get_active_subjects()

    if request.method == "POST":
        subject_code = request.POST.get("subject_code", "").strip()
        subject = next((item for item in subjects if item.code == subject_code), None)

        if subject:
            set_current_subject(request, subject)
            return redirect("realtor_home" if subject.code == REALTOR_SUBJECT_CODE else "mission_list")

        messages.warning(request, "선택할 수 있는 과목을 다시 확인해 주세요.")

    return render(request, "core/landing.html", {
        "subjects": subjects,
        "selected_subject_code": request.session.get(CURRENT_SUBJECT_SESSION_KEY, ""),
        "canonical_url": request.build_absolute_uri(reverse("landing")),
    })


def service_info(request):
    return render(request, "core/service_info.html", {
        "premium_gating_enabled": premium_gating_enabled(),
        "canonical_url": request.build_absolute_uri(reverse("service_info")),
    })


def content_sources(request):
    return render(request, "core/content_sources.html", {
        "logistics_sources": logistics_source_notices(),
        "canonical_url": request.build_absolute_uri(reverse("content_sources")),
    })


def select_subject(request, subject_code):
    subjects = get_active_subjects()
    subject = next((item for item in subjects if item.code == subject_code), None)

    if not subject:
        messages.warning(request, "선택할 수 없는 과목입니다. 다시 확인해 주세요.")
        return redirect("landing")

    set_current_subject(request, subject)
    return redirect("realtor_home" if subject.code == REALTOR_SUBJECT_CODE else "mission_list")


@login_required
def realtor_home(request):
    subject = Subject.objects.filter(code=REALTOR_SUBJECT_CODE, is_active=True).first()
    if subject is None:
        return redirect("landing")
    set_current_subject(request, subject)
    preference = RealtorStudyPath.objects.filter(user=request.user).first()
    path = preference.path if preference else ""
    eligible = Mission.objects.filter(subject=subject, is_usable_for_set=True).exclude(
        review_status=Mission.REVIEW_CONFIRMED_ERROR,
    )
    counts = dict(eligible.values("course").annotate(total=Count("pk")).values_list("course", "total"))
    attempts = Attempt.objects.valid_for_learning().filter(user=request.user, mission__subject=subject)
    solved = dict(attempts.values("mission__course").annotate(total=Count("pk")).values_list("mission__course", "total"))
    mistakes = dict(attempts.filter(is_correct=False).values("mission__course").annotate(total=Count("pk")).values_list("mission__course", "total"))
    stages = []
    for stage in ("first", "second"):
        sittings = []
        for item in REALTOR_SITTINGS:
            if item["stage"] != stage:
                continue
            rows = [{"name": name, "available": counts.get(name, 0),
                     "attempts": solved.get(name, 0), "mistakes": mistakes.get(name, 0)}
                    for name in item["courses"]]
            sittings.append({**item, "course_rows": rows})
        stages.append({"code": stage, "label": "1차" if stage == "first" else "2차", "sittings": sittings})
    if path == "second":
        stages.reverse()
    chapter_groups = build_subject_theory_roadmap(request.user, subject)
    if path == "second":
        chapter_groups.sort(key=lambda group: group["stage"] != "second")
    allowed_courses = courses_for_path(path) if path else ()
    saved_course = CourseFocus.objects.filter(user=request.user, subject=subject).values_list("course", flat=True).first()
    recent_any_attempt = attempts.filter(mission__course__in=allowed_courses).select_related("mission").order_by("-created_at").first()
    pending_work = MissionWork.objects.filter(
        user=request.user, attempt__isnull=True, mission__subject=subject,
        mission__course__in=allowed_courses,
    ).select_related("mission").order_by("-updated_at").first()
    selected_course = saved_course if saved_course in allowed_courses else (
        pending_work.mission.course if pending_work else (
            recent_any_attempt.mission.course if recent_any_attempt else ""
        )
    )
    if pending_work and pending_work.mission.course != selected_course:
        pending_work = None
    recent_attempt = attempts.filter(mission__course=selected_course).order_by("-created_at").first() if selected_course else None
    first_visit = not selected_course and not recent_any_attempt and not pending_work
    return render(request, "core/realtor_home.html", {
        "current_subject": subject,
        "study_path": path,
        "focused_courses": courses_for_path(path) if path else (),
        "stages": stages,
        "chapter_groups": chapter_groups,
        "allowed_courses": [
            {"name": name, "available": counts.get(name, 0)} for name in allowed_courses
        ],
        "selected_course": selected_course,
        "recent_attempt": recent_attempt,
        "pending_work": pending_work,
        "first_visit": first_visit,
        "exam_guide_url": REALTOR_EXAM_GUIDE,
    })


@login_required
@require_POST
def realtor_choose_path(request):
    subject = Subject.objects.filter(code=REALTOR_SUBJECT_CODE, is_active=True).first()
    if subject is None:
        return redirect("landing")
    path = request.POST.get("path", "")
    if path not in dict(RealtorStudyPath.PATH_CHOICES):
        messages.warning(request, "공부할 시험 단계를 다시 선택해 주세요.")
        return redirect("realtor_home")
    RealtorStudyPath.objects.update_or_create(user=request.user, defaults={"path": path})
    set_current_subject(request, subject)
    messages.success(request, "학습 목표를 저장했습니다. 언제든 이 화면에서 바꿀 수 있어요.")
    return redirect("realtor_home")


@login_required
@require_POST
def realtor_choose_course(request):
    subject = Subject.objects.filter(code=REALTOR_SUBJECT_CODE, is_active=True).first()
    preference = RealtorStudyPath.objects.filter(user=request.user).first()
    if subject is None or preference is None:
        return redirect("realtor_home")
    course = request.POST.get("course", "").strip()
    if course not in courses_for_path(preference.path):
        messages.warning(request, "선택한 시험 단계의 과목을 골라 주세요.")
        return redirect("realtor_home")
    CourseFocus.objects.update_or_create(
        user=request.user, subject=subject, defaults={"course": course},
    )
    set_current_subject(request, subject)
    return redirect("realtor_home")
