from django import forms

from core.models import Inquiry


class InquiryForm(forms.ModelForm):
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
            "message": "프리미엄 신청, 오류 상황, 궁금한 점을 적어 주세요.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "이름 또는 닉네임"}),
            "contact": forms.TextInput(attrs={"placeholder": "연락 가능한 이메일 또는 연락처"}),
            "message": forms.Textarea(attrs={"rows": 6, "placeholder": "문의 내용을 입력하세요."}),
        }
