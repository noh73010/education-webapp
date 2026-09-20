from django.contrib import messages
from django.shortcuts import redirect, render

from core.services.subjects import (
    CURRENT_SUBJECT_SESSION_KEY,
    get_active_subjects,
    set_current_subject,
)
from core.services.access import premium_gating_enabled


def landing(request):
    subjects = get_active_subjects()

    if request.method == "POST":
        subject_code = request.POST.get("subject_code", "").strip()
        subject = next((item for item in subjects if item.code == subject_code), None)

        if subject:
            set_current_subject(request, subject)
            return redirect("mission_list")

        messages.warning(request, "선택할 수 있는 과목을 다시 확인해 주세요.")

    return render(request, "core/landing.html", {
        "subjects": subjects,
        "selected_subject_code": request.session.get(CURRENT_SUBJECT_SESSION_KEY, ""),
    })


def service_info(request):
    return render(request, "core/service_info.html", {
        "premium_gating_enabled": premium_gating_enabled(),
    })


def select_subject(request, subject_code):
    subjects = get_active_subjects()
    subject = next((item for item in subjects if item.code == subject_code), None)

    if not subject:
        messages.warning(request, "선택할 수 없는 과목입니다. 다시 확인해 주세요.")
        return redirect("landing")

    set_current_subject(request, subject)
    return redirect("mission_list")
