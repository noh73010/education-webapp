import time

from allauth.account import app_settings
from allauth.account.authentication import get_authentication_records
from allauth.socialaccount.models import SocialAccount
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from core.services.account_data import delete_member, reset_learning_data


SOCIAL_PROVIDER_LABELS = {
    "google": "Google",
    "naver": "네이버",
    "kakao": "카카오",
}


class AccountActionForm(forms.Form):
    confirmation = forms.CharField(label="확인 문구", max_length=30)
    password = forms.CharField(
        label="현재 비밀번호", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    acknowledged = forms.BooleanField(label="삭제 범위와 복구할 수 없음을 확인했습니다.")

    def __init__(self, *args, user, phrase, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.phrase = phrase
        self.fields["confirmation"].help_text = f'아래에 “{phrase}”를 그대로 입력하세요.'
        if not user.has_usable_password():
            del self.fields["password"]

    def clean_confirmation(self):
        value = self.cleaned_data["confirmation"]
        if value != self.phrase:
            raise forms.ValidationError("확인 문구를 정확히 입력하세요.")
        return value

    def clean_password(self):
        value = self.cleaned_data["password"]
        if not self.user.check_password(value):
            raise forms.ValidationError("현재 비밀번호가 맞지 않습니다.")
        return value


def _recent_social_login(request):
    now = time.time()
    return any(
        record.get("method") == "socialaccount"
        and isinstance(record.get("at"), (int, float))
        and 0 <= now - record["at"] < app_settings.REAUTHENTICATION_TIMEOUT
        for record in get_authentication_records(request)
    )


def _social_login_options(user):
    connected = set(
        SocialAccount.objects.filter(user=user).values_list("provider", flat=True)
    )
    provider_ids = list(settings.SOCIAL_LOGIN_PROVIDERS)
    provider_ids.extend(sorted(connected.difference(provider_ids)))
    available = set(settings.SOCIAL_LOGIN_PROVIDERS)
    return [
        {
            "id": provider_id,
            "label": SOCIAL_PROVIDER_LABELS.get(provider_id, provider_id.title()),
            "connected": provider_id in connected,
            "available": provider_id in available,
        }
        for provider_id in provider_ids
    ]


@login_required
@never_cache
@sensitive_post_parameters("reset-password", "delete-password")
@require_http_methods(["GET", "POST"])
def account_settings(request):
    action = request.POST.get("action") if request.method == "POST" else None
    reset_form = AccountActionForm(
        request.POST if action == "reset" else None,
        user=request.user, phrase="학습 기록 초기화", prefix="reset",
    )
    delete_form = AccountActionForm(
        request.POST if action == "delete" else None,
        user=request.user, phrase="회원 탈퇴", prefix="delete",
    )
    needs_login = not request.user.has_usable_password() and not _recent_social_login(request)
    form = {"reset": reset_form, "delete": delete_form}.get(action)
    if form is not None and form.is_valid():
        if needs_login:
            form.add_error(None, "안전을 위해 로그아웃 후 소셜 계정으로 다시 로그인하고 진행하세요.")
        else:
            if action == "reset":
                reset_learning_data(request.user)
                message = "모든 자격증의 학습 기록을 초기화했습니다. 다시 로그인해 시작하세요."
            else:
                delete_member(request.user)
                message = "회원 탈퇴가 완료되었습니다. 계정과 연결된 데이터가 삭제되었습니다."
            logout(request)
            messages.success(request, message)
            return redirect("login")
    return render(request, "core/account_settings.html", {
        "reset_form": reset_form,
        "delete_form": delete_form,
        "needs_login": needs_login,
        "social_login_options": _social_login_options(request.user),
    }, status=400 if request.method == "POST" else 200)
