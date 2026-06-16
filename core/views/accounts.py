from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from core.models import UserAccess
from core.services.analytics import record_event


def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)

        if form.is_valid():
            user = form.save()
            UserAccess.objects.get_or_create(user=user)
            login(request, user)
            record_event(
                user,
                "signup",
                page="signup",
                metadata={"source": "signup_form"},
            )
            messages.success(request, "회원가입이 완료되었습니다. 바로 학습을 시작할 수 있습니다.")
            return redirect("mission_list")
    else:
        form = UserCreationForm()

    return render(request, "registration/signup.html", {
        "form": form,
    })


class AnalyticsLoginView(LoginView):
    def form_valid(self, form):
        response = super().form_valid(form)
        record_event(
            self.request.user,
            "login",
            page="login",
            metadata={"source": "login_form"},
        )
        return response
