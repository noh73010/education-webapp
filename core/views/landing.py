from django.contrib import messages
from django.shortcuts import redirect, render

from core.services.subjects import (
    CURRENT_SUBJECT_SESSION_KEY,
    get_active_subjects,
    set_current_subject,
)


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
