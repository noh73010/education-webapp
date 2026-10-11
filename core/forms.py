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
    def __init__(self, *args, premium_gating_enabled=False, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["name"].required = False
        self.fields["contact"].required = not (user and user.is_authenticated)
        self.fields["contact"].label = "답변 받을 이메일" if self.fields["contact"].required else "별도 연락받을 이메일 (선택)"
        self.fields["contact"].help_text = (
            "비회원에게는 웹 답변함이 제공되지 않습니다. 운영자가 별도로 답할 이메일을 입력하세요."
            if self.fields["contact"].required else "답변은 내 문의에서 확인할 수 있습니다. 별도 연락을 원할 때만 이메일을 남기세요."
        )
        if not premium_gating_enabled:
            self.fields["inquiry_type"].choices = [
                choice for choice in self.fields["inquiry_type"].choices
                if choice[0] != "premium"
            ]

    def clean_contact(self):
        contact = self.cleaned_data["contact"].strip()
        if not (self.user and self.user.is_authenticated):
            return forms.EmailField(error_messages={"invalid": "답변 받을 이메일 주소를 입력하세요."}).clean(contact)
        return contact

    def save(self, commit=True):
        inquiry = super().save(commit=False)
        if not inquiry.name:
            inquiry.name = self.user.get_username() if self.user and self.user.is_authenticated else "비회원"
        if commit:
            inquiry.save()
        return inquiry

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
            "contact": "답변 연락처",
            "message": "오류 상황이나 궁금한 점을 적어 주세요.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "이름 또는 닉네임"}),
            "contact": forms.EmailInput(attrs={"placeholder": "email@example.com"}),
            "message": forms.Textarea(attrs={"rows": 6, "placeholder": "문의 내용을 입력하세요."}),
        }
