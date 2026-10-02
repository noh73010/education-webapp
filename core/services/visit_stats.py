from datetime import date, datetime, time, timedelta

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.db.models import Count, Min
from django.db.models.functions import TruncDate
from django.utils import timezone

from core.models import DailyVisitTotal, UserEvent


def is_visit_stats_owner(user):
    owner_email = settings.VISITOR_STATS_OWNER_EMAIL
    return bool(
        owner_email
        and user.is_authenticated
        and user.is_active
        and EmailAddress.objects.filter(user=user, email__iexact=owner_email, verified=True).exists()
        and SocialAccount.objects.filter(user=user, provider="google").exists()
    )


def daily_visit_report(end_day=None, days=30):
    """Exact visits since tracking started; older event counts are only lower bounds."""
    end_day = end_day or timezone.localdate()
    start_day = end_day - timedelta(days=days - 1)
    current_timezone = timezone.get_current_timezone()
    start_time = timezone.make_aware(datetime.combine(start_day, time.min), current_timezone)
    end_time = timezone.make_aware(datetime.combine(end_day + timedelta(days=1), time.min), current_timezone)
    first_tracked_day = DailyVisitTotal.objects.aggregate(first=Min("day"))["first"]

    exact_counts = dict(
        DailyVisitTotal.objects.filter(day__range=(start_day, end_day))
        .values_list("day", "count")
    )
    observed_counts = dict(
        UserEvent.objects.filter(
            created_at__gte=start_time,
            created_at__lt=end_time,
            user__is_staff=False,
        )
        .annotate(day=TruncDate("created_at", tzinfo=current_timezone))
        .values("day").annotate(total=Count("user_id", distinct=True))
        .values_list("day", "total")
    )
    rows = []
    for offset in range(days):
        day = end_day - timedelta(days=offset)
        exact = first_tracked_day is not None and day >= first_tracked_day
        rows.append({
            "day": day,
            "count": exact_counts.get(day, 0) if exact else observed_counts.get(day, 0),
            "exact": exact,
        })
    return rows


def parse_report_end_day(raw_value):
    if not raw_value:
        return timezone.localdate()
    try:
        parsed = date.fromisoformat(raw_value)
    except ValueError:
        return timezone.localdate()
    return min(parsed, timezone.localdate())
