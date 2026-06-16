from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.services.access import get_user_access
from core.services.analytics import record_event


@login_required
def premium_info(request):
    access = get_user_access(request.user)
    record_event(
        request.user,
        "premium_page_view",
        page="premium_info",
        metadata={"is_premium": access.is_premium},
    )
    return render(request, "core/premium_info.html", {
        "is_premium": access.is_premium,
        "premium_ended_at": access.premium_ended_at,
    })
