from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.models import OfficialExamDate
from core.services.exam_dates import goal_for, save_goal, upcoming_official_dates
from core.services.subjects import get_current_subject


@login_required
def study_profile(request):
    subject, _ = get_current_subject(request)
    goal = goal_for(request.user, subject)
    official_dates = upcoming_official_dates(subject)
    error = None
    if request.method == "POST":
        action = request.POST.get("action", "manual")
        if action == "official":
            try:
                official_id = int(request.POST.get("official_id", ""))
            except ValueError:
                official_id = None
            official = get_object_or_404(official_dates, pk=official_id)
            save_goal(request.user, subject, official.exam_date)
        elif action == "clear":
            save_goal(request.user, subject, None)
        else:
            raw_date = request.POST.get("target_exam_date", "").strip()
            try:
                target_date = date.fromisoformat(raw_date)
            except ValueError:
                error = "올바른 시험일을 입력하세요."
            else:
                if target_date < timezone.localdate():
                    error = "지난 날짜는 목표 시험일로 설정할 수 없습니다."
                else:
                    save_goal(request.user, subject, target_date)
        if not error:
            messages.success(request, f"{subject.name} 목표 시험일을 저장했습니다." if action != "clear" else f"{subject.name} 목표 시험일을 지웠습니다.")
            return redirect("mission_list")
    return render(request, "core/study_profile.html", {
        "subject": subject, "goal": goal, "official_dates": official_dates, "error": error,
    })
