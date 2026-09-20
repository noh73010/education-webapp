from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.db import transaction
from django.urls import reverse

from core.models import UserAccess
from core.services.analytics import record_event


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Keep social signups consistent with the local signup flow."""

    def save_user(self, request, sociallogin, form=None):
        with transaction.atomic():
            user = super().save_user(request, sociallogin, form)
            UserAccess.objects.get_or_create(user=user)

        record_event(
            user,
            "signup",
            page="social_signup",
            metadata={"source": sociallogin.account.provider},
        )
        return user

    def get_connect_redirect_url(self, request, socialaccount):
        return reverse("account_settings")
