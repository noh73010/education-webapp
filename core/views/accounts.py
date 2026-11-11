from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from core.forms import SignupForm
from core.models import UserAccess
from core.services.analytics import record_event


def signup(request):
    next_url = request.POST.get("next", request.GET.get("next", ""))
    if not (next_url.startswith("/") and not next_url.startswith("//") and
            url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()})):
        next_url = ""
    if request.user.is_authenticated:
        return redirect(next_url) if next_url else redirect("mission_list")

    if request.method == "POST":
        form = SignupForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                UserAccess.objects.create(user=user)
            login(
                request,
                user,
                backend="django.contrib.auth.backends.ModelBackend",
            )
            record_event(
                user,
                "signup",
                page="signup",
                metadata={"source": "signup_form"},
            )
            messages.success(request, "회원가입이 완료되었습니다. 바로 학습을 시작할 수 있습니다.")
            return redirect(next_url) if next_url else redirect("mission_list")
    else:
        form = SignupForm()

    return render(request, "registration/signup.html", {
        "form": form,
        "next": next_url,
        "social_login_providers": settings.SOCIAL_LOGIN_PROVIDERS,
    })


class AnalyticsLoginView(LoginView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["social_login_providers"] = settings.SOCIAL_LOGIN_PROVIDERS
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        record_event(
            self.request.user,
            "login",
            page="login",
            metadata={"source": "login_form"},
        )
        return response
