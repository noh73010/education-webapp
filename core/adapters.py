from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.db import transaction
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from urllib.parse import urlencode
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.providers.base import AuthError
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

    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        state = (extra_context or {}).get("state") or {}
        target = state.get("next", "")
        if not (isinstance(target, str) and target.startswith("/") and not target.startswith("//")
                and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()})):
            target = ""
        messages.info(request, "소셜 로그인을 취소했어요. 다시 로그인하거나 다른 방법을 선택해 주세요."
                      if error == AuthError.CANCELLED else
                      "소셜 로그인을 완료하지 못했어요. 다시 시도하거나 다른 로그인 방법을 선택해 주세요.")
        destination = reverse("login") + ("?" + urlencode({"next": target}) if target else "")
        raise ImmediateHttpResponse(redirect(destination))

    def get_connect_redirect_url(self, request, socialaccount):
        return reverse("account_settings")
