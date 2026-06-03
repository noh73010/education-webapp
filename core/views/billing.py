from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.services.access import get_user_access


@login_required
def premium_info(request):
    access = get_user_access(request.user)
    return render(request, "core/premium_info.html", {
        "is_premium": access.is_premium,
        "premium_ended_at": access.premium_ended_at,
    })