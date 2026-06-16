import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.utils import timezone

from core.models import UserEvent

logger = logging.getLogger(__name__)


def record_event(user, event_type, page=None, metadata=None):
    if not event_type:
        return None

    event_user = user if getattr(user, "is_authenticated", False) else None
    if event_user is not None and not isinstance(event_user, get_user_model()):
        event_user = None

    safe_metadata = metadata if isinstance(metadata, dict) else {}

    try:
        return UserEvent.objects.create(
            user=event_user,
            event_type=event_type,
            page=page or "",
            metadata=safe_metadata,
        )
    except Exception:
        logger.exception("Failed to record user event: %s", event_type)
        return None


def get_analytics_summary(*, recent_limit=20, top_limit=5):
    User = get_user_model()
    today = timezone.localdate()
    seven_days_ago = timezone.now() - timedelta(days=7)

    today_events = UserEvent.objects.filter(created_at__date=today)

    popular_events = list(
        UserEvent.objects
        .filter(created_at__gte=seven_days_ago)
        .values("event_type")
        .annotate(count=Count("id"))
        .order_by("-count", "event_type")[:top_limit]
    )

    recent_events = list(
        UserEvent.objects
        .select_related("user")
        .order_by("-created_at")[:recent_limit]
    )

    return {
        "total_users": User.objects.count(),
        "today_users": User.objects.filter(date_joined__date=today).count(),
        "today_mission_finish_count": today_events.filter(event_type="finish_mission").count(),
        "today_exam_start_count": today_events.filter(event_type="start_exam").count(),
        "today_exam_finish_count": today_events.filter(event_type="finish_exam").count(),
        "today_pattern_start_count": today_events.filter(event_type="start_pattern_training").count(),
        "today_pattern_finish_count": today_events.filter(event_type="finish_pattern_training").count(),
        "today_premium_page_view_count": today_events.filter(event_type="premium_page_view").count(),
        "popular_events": popular_events,
        "recent_events": recent_events,
    }
