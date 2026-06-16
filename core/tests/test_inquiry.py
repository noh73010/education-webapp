from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Inquiry, UserEvent


class InquiryTests(TestCase):
    def test_inquiry_page_is_public(self):
        response = self.client.get(reverse("inquiry"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "프리미엄 신청/문의")

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
