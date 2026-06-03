from datetime import timedelta
from django.utils import timezone

from core.models import UserAccess


def activate_premium_for_30_days(user):
    access, _ = UserAccess.objects.get_or_create(user=user)

    now = timezone.now()

    if access.premium_ended_at and access.premium_ended_at > now:
        start_base = access.premium_ended_at
    else:
        start_base = now

    access.is_premium = True
    access.premium_started_at = now
    access.premium_ended_at = start_base + timedelta(days=30)
    access.save()

    return access