import logging

from django.conf import settings
from django.db import DatabaseError, transaction
from django.db.models import F
from django.utils import timezone

from core.models import DailyVisit, DailyVisitTotal
from core.services.analytics import record_event

logger = logging.getLogger(__name__)


class DailyVisitMiddleware:
    """Count a signed-in learner once per local day without writing on every page view."""

    SESSION_KEY = "daily_visit_recorded"
    EXCLUDED_PREFIXES = ("/admin/", "/accounts/", "/static/", "/media/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = request.user
        if not user.is_authenticated:
            self.record_guest_visit(request, response)
            return response
        if (
            request.method != "GET"
            or response.status_code != 200
            or not user.is_authenticated
            or user.is_staff
            or (settings.VISITOR_STATS_OWNER_EMAIL and user.email.lower() == settings.VISITOR_STATS_OWNER_EMAIL)
            or request.path.startswith(self.EXCLUDED_PREFIXES)
        ):
            return response

        day = timezone.localdate()
        marker = f"{user.pk}:{day.isoformat()}"
        if request.session.get(self.SESSION_KEY) == marker:
            return response
        try:
            with transaction.atomic():
                _, created = DailyVisit.objects.get_or_create(user=user, day=day)
                if created:
                    DailyVisitTotal.objects.get_or_create(day=day)
                    DailyVisitTotal.objects.filter(day=day).update(count=F("count") + 1)
        except DatabaseError:
            logger.exception("Could not record daily visit")
        else:
            request.session[self.SESSION_KEY] = marker
        return response

    def record_guest_visit(self, request, response):
        if (request.method != "GET" or response.status_code != 200
                or not response.get("Content-Type", "").startswith("text/html")
                or request.path.startswith(self.EXCLUDED_PREFIXES)
                or any(term in request.headers.get("User-Agent", "").lower()
                       for term in ("bot", "crawler", "spider", "preview", "curl", "headless"))):
            return
        day = timezone.localdate().isoformat()
        marker = "guest_visit_day"
        prior_day = request.session.get(marker)
        if prior_day == day:
            return
        if record_event(None, "guest_visit_day", metadata={"returning": bool(prior_day)}):
            request.session[marker] = day
