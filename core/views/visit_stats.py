from collections import Counter
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from core.models import Attempt, DailyVisit, UserEvent
from core.services.analytics import record_event
from core.services.guest_focus import trial_funnel
from core.views.guest_practice import BLOG_COURSES, BLOG_REPORT_LABELS
from core.services.visit_stats import daily_visit_report, is_visit_stats_owner, parse_report_end_day


@never_cache
@require_POST
@csrf_protect
def confirm_guest_visit(request):
    if (request.user.is_authenticated or not request.COOKIES.get(settings.CSRF_COOKIE_NAME)
            or request.headers.get("Sec-GPC") == "1" or request.headers.get("DNT") == "1"
            or any(term in request.headers.get("User-Agent", "").lower()
                   for term in ("bot", "crawler", "spider", "preview", "curl", "headless"))):
        return HttpResponse(status=204)
    day = timezone.localdate().isoformat()
    marker = "confirmed_guest_visit_day"
    previous = request.session.get(marker)
    if previous != day and record_event(None, marker, metadata={"returning": bool(previous)}):
        request.session[marker] = day
    return HttpResponse(status=204)


def next_day_review_counts(start_day, end_day):
    counts = Counter()
    saves = UserEvent.objects.filter(
        event_type="guest_practice_saved", user__isnull=False,
        metadata__course__in=tuple(BLOG_COURSES),
        created_at__date__range=(start_day, min(end_day, timezone.localdate() - timedelta(days=1))),
    ).values_list("user_id", "created_at", "metadata")
    for user_id, saved_at, metadata in saves.iterator():
        missions = metadata.get("review_missions")
        if missions and Attempt.objects.valid_for_learning().filter(
            user_id=user_id, mission_id__in=missions,
            created_at__date=timezone.localtime(saved_at).date() + timedelta(days=1),
        ).exclude(submitted_answer="").exists():
            counts[metadata["course"]] += 1
    return counts


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
    funnel_days = 7 if request.GET.get("funnel_days") == "7" else 14
    funnel_end = parse_report_end_day(request.GET.get("funnel_end") or request.GET.get("before"))
    funnel_start = funnel_end - timedelta(days=funnel_days - 1)
    stages = ("quiz_arrival", "arrival", "start", "first_answer", "complete", "login_click", "login", "saved")
    guest_visits = UserEvent.objects.filter(event_type="confirmed_guest_visit_day", created_at__date__range=(funnel_start, funnel_end))
    legacy_guest_visits = UserEvent.objects.filter(
        event_type="guest_visit_day", created_at__date__range=(funnel_start, funnel_end),
    )
    counts = {(row["metadata__course"], row["event_type"]): row["total"] for row in
              UserEvent.objects.filter(
                  created_at__date__range=(funnel_start, funnel_end),
                  event_type__in=[f"blog_guest_{stage}" for stage in stages],
              ).values("metadata__course", "event_type").annotate(total=Count("pk"))}
    reviews = next_day_review_counts(funnel_start, funnel_end)
    return render(request, "core/visit_stats.html", {
        "rows": rows,
        "trial_funnel": trial_funnel(funnel_start, funnel_end),
        "funnel_days": funnel_days,
        "funnel_start": funnel_start,
        "funnel_end": funnel_end,
        "guest_visits": guest_visits.count(),
        "legacy_guest_visits": legacy_guest_visits.count(),
        "guest_returns": guest_visits.filter(metadata__returning=True).count(),
        "blog_rows": [(BLOG_REPORT_LABELS.get(code, name), [counts.get((code, f"blog_guest_{stage}"), 0) for stage in stages] + [reviews[code]])
                      for code, name in BLOG_COURSES.items()],
        "today": daily_visit_report(days=1)[0],
        "yesterday": daily_visit_report(end_day=parse_report_end_day(None) - timedelta(days=1), days=1)[0],
        "selected_day": selected_day,
        "daily_visitors": daily_visitors,
        "member_page": member_page,
        "older_end_day": (rows[-1]["day"] - timedelta(days=1)).isoformat(),
        "newer_end_day": min(rows[0]["day"] + timedelta(days=30), parse_report_end_day(None)).isoformat(),
        "has_newer": rows[0]["day"] < parse_report_end_day(None),
    })
