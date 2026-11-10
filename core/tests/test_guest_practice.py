from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Attempt, Mission, Subject


class GuestPracticeTests(TestCase):
    def test_five_questions_then_login_and_save(self):
        url = reverse("guest_practice")
        for code in ("logistics", "realtor"):
            subject, _ = Subject.objects.get_or_create(code=code, defaults={"name": code})
            for index in range(6):
                Mission.objects.create(
                    subject=subject, course="Sample", external_id=f"{code}-{index}",
                    title="Sample", prompt=f"Question {index}", question_type="choice_one",
                    correct_answer="1", answer_schema="1|One\n2|Two\n3|Three\n4|Four\n5|Five",
                    explanation="A private explanation until graded",
                )
        self.assertContains(self.client.get(url), 'value="logistics"')
        self.assertContains(self.client.get(url), 'value="realtor"')
        self.client.post(url, {"action": "start", "subject": "realtor", "course": "Sample"})
        for index in range(5):
            response = self.client.get(url)
            self.assertContains(response, f"Question {index}")
            self.assertNotContains(response, "A private explanation until graded")
            self.client.post(url, {"action": "answer", "step": index, "answer": "1", "confidence": "guessed"})
            self.assertContains(self.client.get(url), "A private explanation until graded")
            self.client.post(url, {"action": "next", "step": index})
        self.assertContains(self.client.get(url), "5문제 중 5문제 정답")
        self.assertFalse(Attempt.objects.exists())
        self.assertEqual(self.client.post(url, {"action": "save"}).status_code, 302)
        user = get_user_model().objects.create_user(username="learner", password="test-password")
        self.client.post(reverse("login"), {"username": user.username, "password": "test-password", "next": url})
        self.assertContains(self.client.get(url), "학습 기록 저장하고 복습 이어가기")
        self.assertRedirects(self.client.post(url, {"action": "save"}), reverse("wrong_notes"), fetch_redirect_response=False)
        self.client.post(url, {"action": "save"})
        self.assertEqual(Attempt.objects.filter(user=user, mission__subject__code="realtor").count(), 5)
