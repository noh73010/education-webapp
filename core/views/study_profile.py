from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from core.models import StudyProfile


@login_required
def study_profile(request):
    profile, _ = StudyProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        raw_date = request.POST.get("target_exam_date", "").strip()
        try:
            profile.target_exam_date = date.fromisoformat(raw_date) if raw_date else None
        except ValueError:
            return render(request, "core/study_profile.html", {"profile": profile, "error": "올바른 시험일을 입력하세요."})
        profile.save(update_fields=["target_exam_date", "updated_at"])
        messages.success(request, "시험일을 저장했습니다.")
        return redirect("mission_list")
    return render(request, "core/study_profile.html", {"profile": profile})
