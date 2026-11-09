from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from core.models import DailyVisit
from core.services.visit_stats import daily_visit_report, is_visit_stats_owner, parse_report_end_day


@login_required
@never_cache
def visit_stats(request):
    if not is_visit_stats_owner(request.user):
        raise Http404

    end_day = parse_report_end_day(request.GET.get("before"))
    selected_day = parse_report_end_day(request.GET.get("day"))
    rows = daily_visit_report(end_day=end_day)
    daily_visitors = (
        DailyVisit.objects
        .filter(day=selected_day)
        .select_related("user")
        .order_by("user__username")
    )
    User = get_user_model()
    member_page = Paginator(
        User.objects.only(
            "username", "email", "date_joined", "last_login", "is_active", "is_staff"
        ).order_by("-date_joined"),
        50,
    ).get_page(request.GET.get("member_page"))
    return render(request, "core/visit_stats.html", {
        "rows": rows,
        "today": daily_visit_report(days=1)[0],
        "yesterday": daily_visit_report(end_day=parse_report_end_day(None) - timedelta(days=1), days=1)[0],
        "selected_day": selected_day,
        "daily_visitors": daily_visitors,
        "member_page": member_page,
        "older_end_day": (rows[-1]["day"] - timedelta(days=1)).isoformat(),
        "newer_end_day": min(rows[0]["day"] + timedelta(days=30), parse_report_end_day(None)).isoformat(),
        "has_newer": rows[0]["day"] < parse_report_end_day(None),
    })
