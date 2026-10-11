from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.test import override_settings
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount

from core.models import Inquiry, UserEvent


class InquiryTests(TestCase):
    def test_inquiry_page_is_public(self):
        response = self.client.get(reverse("inquiry"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "문의·오류 제보")
        self.assertNotContains(response, "프리미엄 신청")

    def test_anonymous_user_can_submit_inquiry(self):
        response = self.client.post(
            reverse("inquiry"),
            {
                "name": "방문자",
                "contact": "visitor@example.com",
                "inquiry_type": "premium",
                "message": "프리미엄 신청합니다.",
            },
        )

        self.assertRedirects(response, reverse("inquiry_done"))
        inquiry = Inquiry.objects.get()
        self.assertIsNone(inquiry.user)
        self.assertEqual(inquiry.inquiry_type, "premium")

    def test_authenticated_user_submission_links_user_and_records_event(self):
        user = User.objects.create_user(username="learner", password="pass12345")
        self.client.force_login(user)

        response = self.client.post(
            reverse("inquiry"),
            {
                "name": "학습자",
                "contact": "learner@example.com",
                "inquiry_type": "bug",
                "message": "오류가 있습니다.",
            },
        )

        self.assertRedirects(response, reverse("inquiry_done"))
        inquiry = Inquiry.objects.get()
        self.assertEqual(inquiry.user, user)

        event = UserEvent.objects.get(event_type="submit_inquiry")
        self.assertEqual(event.user, user)
        self.assertEqual(event.metadata, {"inquiry_type": "bug"})
        self.assertNotIn("contact", event.metadata)
        self.assertNotIn("message", event.metadata)


@override_settings(INQUIRY_OWNER_EMAIL="owner@example.com")
class PrivateInquiryTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", email="owner@example.com")
        EmailAddress.objects.create(user=self.owner, email="owner@example.com", verified=True)
        SocialAccount.objects.create(user=self.owner, provider="google", uid="owner-google")
        self.member = User.objects.create_user(username="member", password="pass12345")
        self.other = User.objects.create_user(username="other", password="pass12345")
        self.item = Inquiry.objects.create(user=self.member, name="member", contact="", message="비공개 문의")

    def test_member_can_submit_without_contact_and_read_only_own_inquiry(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("inquiry"), {"inquiry_type": "bug", "message": "학습 오류"})
        self.assertRedirects(response, reverse("inquiry_done"))
        created = Inquiry.objects.exclude(pk=self.item.pk).get()
        self.assertEqual(created.contact, "")
        self.assertEqual(created.user, self.member)
        self.assertContains(self.client.get(reverse("my_inquiries")), "학습 오류")
        self.assertEqual(self.client.get(reverse("inquiry_detail", args=[created.pk])).status_code, 200)
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("my_inquiries")), "학습 오류")
        self.assertEqual(self.client.get(reverse("inquiry_detail", args=[created.pk])).status_code, 404)

    def test_guest_email_required_and_guest_cannot_read_details(self):
        bad = self.client.post(reverse("inquiry"), {"inquiry_type": "question", "message": "문의", "contact": "kakao-id"})
        self.assertEqual(bad.status_code, 200)
        self.assertContains(bad, "답변 받을 이메일 주소")
        self.assertEqual(Inquiry.objects.count(), 1)
        good = self.client.post(reverse("inquiry"), {"inquiry_type": "question", "message": "문의", "contact": "guest@example.com"})
        self.assertRedirects(good, reverse("inquiry_done"))
        guest = Inquiry.objects.exclude(pk=self.item.pk).get()
        self.assertIsNone(guest.user)
        self.assertEqual(self.client.get(reverse("inquiry_detail", args=[guest.pk])).status_code, 302)

    def test_only_verified_google_owner_can_use_inbox_reply_and_button(self):
        same_email = User.objects.create_user(username="impostor", email="owner@example.com", is_staff=True)
        SocialAccount.objects.create(user=same_email, provider="google", uid="other-google")
        self.client.force_login(same_email)
        self.assertEqual(self.client.get(reverse("inquiry_inbox")).status_code, 404)
        self.assertEqual(self.client.post(reverse("inquiry_reply", args=[self.item.pk]), {"reply": "x"}).status_code, 404)
        self.assertNotContains(self.client.get(reverse("account_settings")), "운영자 문의함")
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("account_settings")), "운영자 문의함")
        self.assertContains(self.client.get(reverse("inquiry_inbox")), "비공개 문의")
        self.assertRedirects(self.client.post(reverse("inquiry_reply", args=[self.item.pk]), {"reply": "답변 내용"}), reverse("inquiry_detail", args=[self.item.pk]))
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "done")
        self.assertIsNotNone(self.item.replied_at)
        self.client.force_login(self.member)
        self.assertContains(self.client.get(reverse("inquiry_detail", args=[self.item.pk])), "답변 내용")

    def test_owner_role_is_disabled_without_configuration(self):
        with override_settings(INQUIRY_OWNER_EMAIL=""):
            self.client.force_login(self.owner)
            self.assertEqual(self.client.get(reverse("inquiry_inbox")).status_code, 404)

    def test_guest_reply_requires_offsite_contact_confirmation(self):
        guest = Inquiry.objects.create(name="방문자", contact="guest@example.com", message="게스트 문의")
        self.client.force_login(self.owner)
        url = reverse("inquiry_reply", args=[guest.pk])
        self.assertEqual(self.client.post(url, {"reply": "이메일 답변"}).status_code, 400)
        guest.refresh_from_db()
        self.assertEqual(guest.status, "new")
        self.assertRedirects(self.client.post(url, {"reply": "이메일 답변", "guest_contacted": "yes"}), reverse("inquiry_detail", args=[guest.pk]))

    def test_other_staff_cannot_open_inquiry_admin(self):
        staff = User.objects.create_superuser(username="staff", email="staff@example.com", password="pass12345")
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("admin:core_inquiry_changelist")).status_code, 403)
