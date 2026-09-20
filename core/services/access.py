from django.conf import settings
from django.utils import timezone

from core.models import UserAccess


def get_user_access(user):
    access, _ = UserAccess.objects.get_or_create(user=user)

    if access.is_premium and access.premium_ended_at:
        now = timezone.now()
        if now >= access.premium_ended_at:
            access.is_premium = False
            access.save(update_fields=["is_premium"])

    return access


def is_user_premium(user):
    access = get_user_access(user)
    return access.is_premium


def premium_gating_enabled():
    """Return whether paid-plan usage limits are currently enforced."""
    return settings.PREMIUM_GATING_ENABLED


def has_full_learning_access(user):
    """Grant launch access without changing the member's stored plan."""
    return not premium_gating_enabled() or is_user_premium(user)
