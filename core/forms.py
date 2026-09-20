from django import forms
from django.contrib.auth.forms import UserCreationForm

from allauth.account.utils import filter_users_by_email
from allauth.socialaccount.forms import SignupForm as AllauthSocialSignupForm

from core.models import Inquiry


class SignupForm(UserCreationForm):
    """회원가입 화면에서 사용하는 기본 사용자 생성 폼."""

    class Meta(UserCreationForm.Meta):
        fields = ("username", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "아이디"
        self.fields["username"].widget.attrs.update({
            "autocomplete": "username",
            "autofocus": True,
        })
        self.fields["password1"].label = "비밀번호"
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].label = "비밀번호 확인"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"


class SocialSignupForm(AllauthSocialSignupForm):
    """Do not ask learners to invent local credentials after social auth."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        provider_email = (self.initial.get("email") or "").strip()
        self.has_existing_email = bool(
            provider_email and filter_users_by_email(provider_email)
        )

    def clean(self):
        cleaned_data = super().clean()
        if self.has_existing_email:
            raise forms.ValidationError(
                "이미 가입된 계정으로 로그인한 뒤 소셜 로그인을 연결해 주세요."
            )
        raise forms.ValidationError(
            "소셜 로그인 제공자에게서 필요한 계정 정보를 받지 못했습니다."
        )


class InquiryForm(forms.ModelForm):
    def __init__(self, *args, premium_gating_enabled=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not premium_gating_enabled:
            self.fields["inquiry_type"].choices = [
                choice for choice in self.fields["inquiry_type"].choices
                if choice[0] != "premium"
            ]

    class Meta:
        model = Inquiry
        fields = ("name", "contact", "inquiry_type", "message")
        labels = {
            "name": "이름",
            "contact": "연락처",
            "inquiry_type": "문의 유형",
            "message": "문의 내용",
        }
        help_texts = {
            "contact": "이메일, 전화번호, 카카오톡 ID 등 연락 가능한 수단을 입력하세요.",
            "message": "오류 상황이나 궁금한 점을 적어 주세요.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "이름 또는 닉네임"}),
            "contact": forms.TextInput(attrs={"placeholder": "연락 가능한 이메일 또는 연락처"}),
            "message": forms.Textarea(attrs={"rows": 6, "placeholder": "문의 내용을 입력하세요."}),
        }
