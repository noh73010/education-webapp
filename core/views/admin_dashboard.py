from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from core.services.analytics import get_analytics_summary


@login_required
def admin_dashboard(request):
    if not request.user.is_staff:
        messages.warning(request, "운영자만 접근할 수 있는 페이지입니다.")
        return redirect("mission_list")

    summary = get_analytics_summary(recent_limit=20, top_limit=5)

    return render(request, "core/admin_dashboard.html", {
        "summary": summary,
    })
