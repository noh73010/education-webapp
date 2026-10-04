from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.models import Attempt, CourseFocus, Mission, MissionWork, RealtorStudyPath, Subject
from core.services.realtor_curriculum import (
    REALTOR_EXAM_GUIDE, REALTOR_LEARNING_AREAS, REALTOR_SUBJECT_CODE, area_for_focus, learning_area,
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
    filter_stage = request.GET.get("stage", "all")
    if filter_stage not in {"all", "first", "second"}:
        filter_stage = "all"
    eligible = Mission.objects.filter(subject=subject, is_usable_for_set=True).exclude(
        review_status=Mission.REVIEW_CONFIRMED_ERROR,
    )
    attempts = Attempt.objects.valid_for_learning().filter(user=request.user, mission__subject=subject)
    chapter_groups = build_subject_theory_roadmap(request.user, subject)
    focus = CourseFocus.objects.filter(user=request.user, subject=subject).first()
    recent_any_attempt = attempts.select_related("mission").order_by("-created_at").first()
    pending_work = MissionWork.objects.filter(
        user=request.user, attempt__isnull=True, mission__subject=subject,
    ).select_related("mission").order_by("-updated_at").first()
    area_codes = {area["code"] for area in REALTOR_LEARNING_AREAS}
    saved_area = area_for_focus(focus)
    selected_area_code = saved_area["code"] if saved_area else ""
    if not selected_area_code:
        source = pending_work.mission if pending_work else (recent_any_attempt.mission if recent_any_attempt else None)
        candidate = source.chapter_code[:4] if source else ""
        selected_area_code = candidate if candidate in area_codes else ""
    selected_area = learning_area(selected_area_code)
    if pending_work and not pending_work.mission.chapter_code.startswith(selected_area_code):
        pending_work = None
    recent_attempt = attempts.filter(mission__chapter_code__startswith=selected_area_code).order_by("-created_at").first() if selected_area else None
    areas = [{**area, "available": eligible.filter(chapter_code__startswith=area["code"]).count()}
             for area in REALTOR_LEARNING_AREAS if filter_stage == "all" or area["stage"] == filter_stage]
    selected_group = next((group for group in chapter_groups if group["area_code"] == selected_area_code), None)
    first_visit = not selected_area and not recent_any_attempt and not pending_work
    return render(request, "core/realtor_home.html", {
        "current_subject": subject,
        "study_path": path,
        "filter_stage": filter_stage,
        "areas": areas,
        "selected_area": selected_area,
        "selected_group": selected_group,
        "has_focus": bool(saved_area),
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
    if subject is None:
        return redirect("realtor_home")
    area = learning_area(request.POST.get("area_code", "").strip())
    if area is None:
        messages.warning(request, "공부할 과목을 다시 골라 주세요.")
        return redirect("realtor_home")
    CourseFocus.objects.update_or_create(
        user=request.user, subject=subject,
        defaults={"course": area["course"], "area_code": area["code"]},
    )
    set_current_subject(request, subject)
    if request.POST.get("start") == "1":
        return redirect(f"{reverse('mission_list')}?minutes=5&start=1")
    return redirect("realtor_home")
