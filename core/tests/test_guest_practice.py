from datetime import date, datetime, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Attempt, Mission, Subject


class GuestPracticeTests(TestCase):
    def guest_post(self, url, data, **kwargs):
        data = {"run_id": self.client.session.get("guest_practice", {}).get("id", ""), **data}
        return self.client.post(url, data, **kwargs)

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
        self.guest_post(url, {"action": "start", "subject": "realtor", "course": "Sample"})
        question_ids = [row[0] for row in self.client.session["guest_practice"]["questions"]]
        for index, pk in enumerate(question_ids):
            response = self.client.get(url)
            self.assertContains(response, Mission.objects.get(pk=pk).prompt)
            self.assertNotContains(response, "A private explanation until graded")
            self.guest_post(url, {"action": "answer", "step": index, "answer": "1", "confidence": "guessed"})
            self.assertContains(self.client.get(url), "A private explanation until graded")
            self.guest_post(url, {"action": "next", "step": index})
        self.assertContains(self.client.get(url), "5문제 중 5문제 정답")
        result = self.client.get(url)
        self.assertEqual(len(result.context["review"]), 5)
        for pk in question_ids:
            self.assertContains(result, Mission.objects.get(pk=pk).prompt)
        self.assertContains(result, "A private explanation until graded", count=5)
        self.assertEqual(result.context["review_count"], 5)
        self.assertContains(result, "정답 · 다시 확인", count=5)
        self.assertFalse(Attempt.objects.exists())
        self.assertEqual(self.guest_post(url, {"action": "save"}).status_code, 302)
        user = get_user_model().objects.create_user(username="learner", password="test-password")
        self.client.post(reverse("login"), {"username": user.username, "password": "test-password", "next": url})
        self.assertContains(self.client.get(url), "학습 기록 저장하고 복습 이어가기")
        self.assertRedirects(self.guest_post(url, {"action": "save"}), reverse("wrong_notes"), fetch_redirect_response=False)
        self.guest_post(url, {"action": "save"})
        self.assertEqual(Attempt.objects.filter(user=user, mission__subject__code="realtor").count(), 5)

    def test_landing_starts_complete_subject_sample_without_course(self):
        subject, _ = Subject.objects.get_or_create(code="realtor", defaults={"name": "공인중개사"})
        for course, count in (("Incomplete", 2), ("부동산학개론", 5)):
            for index in range(count):
                Mission.objects.create(
                    subject=subject, course=course, external_id=f"{course}-{index}",
                    title="Preview", prompt=f"Preview {course} {index}", question_type="choice_one",
                    correct_answer="1", answer_schema="1|One\n2|Two\n3|Three\n4|Four\n5|Five",
                    explanation="Preview explanation",
                )
        landing = self.client.get(reverse("landing"))
        self.assertContains(landing, "Preview 부동산학개론")
        self.assertContains(landing, 'name="subject" value="realtor"')
        self.assertContains(landing, "선택한 자격증 5문제 풀어보기")
        self.client.post(reverse("guest_practice"), {"action": "start", "subject": "realtor"})
        state = self.client.session["guest_practice"]
        self.assertEqual(len(state["questions"]), 5)
        self.assertEqual(set(Mission.objects.filter(pk__in=[q[0] for q in state["questions"]]).values_list("course", flat=True)), {"부동산학개론"})
        self.assertContains(self.client.get(reverse("guest_practice")), "Preview 부동산학개론")

    def test_incomplete_subject_sample_does_not_start(self):
        response = self.client.post(reverse("guest_practice"), {"action": "start", "subject": "unavailable"})
        self.assertNotIn("guest_practice", self.client.session)
        self.assertContains(response, "아직 준비 중입니다")

    def test_daily_sample_is_stable_rotates_and_preserves_in_progress_run(self):
        from core.views.guest_practice import sample_questions
        subject, _ = Subject.objects.get_or_create(code="realtor", defaults={"name": "공인중개사"})
        for index in range(12):
            Mission.objects.create(subject=subject, course="Daily", external_id=f"daily-{index}",
                title="Daily", prompt=f"Daily {index}", question_type="choice_one", correct_answer="1",
                answer_schema="1|One\n2|Two\n3|Three\n4|Four\n5|Five", explanation="Daily explanation")
        url = reverse("guest_practice")
        with patch("core.views.guest_practice.timezone.now", return_value=datetime(2026, 11, 10, 14, 59, tzinfo=dt_timezone.utc)):
            first = [m.pk for m in sample_questions("realtor", "Daily")]
            self.assertEqual(first, [m.pk for m in sample_questions("realtor", "Daily")])
            self.guest_post(url, {"action": "start", "subject": "realtor", "course": "Daily"})
            self.assertEqual(first, [q[0] for q in self.client.session["guest_practice"]["questions"]])
        with patch("core.views.guest_practice.timezone.now", return_value=datetime(2026, 11, 10, 15, 0, tzinfo=dt_timezone.utc)):
            second = [m.pk for m in sample_questions("realtor", "Daily")]
            self.assertEqual(len(set(second)), 5)
            self.assertTrue(set(first).isdisjoint(second))
            self.assertEqual(self.client.get(url).context["mission"].pk, first[0])
            self.guest_post(url, {"action": "start", "subject": "realtor", "course": "Daily"})
            self.assertEqual(second, [q[0] for q in self.client.session["guest_practice"]["questions"]])

    def test_exactly_five_available_questions_remain_usable(self):
        from core.views.guest_practice import daily_sample
        from types import SimpleNamespace
        missions = [SimpleNamespace(pk=i, subject=SimpleNamespace(code="realtor"), course="Only five") for i in range(5)]
        self.assertEqual({m.pk for m in daily_sample(missions)}, set(range(5)))
        self.assertEqual(daily_sample(missions[:4]), [])

    def test_confidence_only_for_correct_answers_and_wrong_post_is_ignored(self):
        subject, _ = Subject.objects.get_or_create(code="logistics", defaults={"name": "물류관리사"})
        for index in range(5):
            Mission.objects.create(subject=subject, course="Confidence", external_id=f"confidence-{index}",
                title="Confidence", prompt="Question", question_type="choice_one", correct_answer="1",
                answer_schema="1|One\n2|Two\n3|Three\n4|Four\n5|Five", explanation="Explanation")
        url = reverse("guest_practice")
        self.guest_post(url, {"action": "start", "subject": "logistics", "course": "Confidence"})
        self.assertNotContains(self.client.get(url), 'name="confidence"')
        self.guest_post(url, {"action": "answer", "step": 0, "answer": "2", "confidence": "guessed"})
        response = self.client.get(url)
        self.assertContains(response, "오답이에요")
        self.assertNotContains(response, 'name="confidence"')
        self.assertEqual(self.guest_post(url, {"action": "confidence", "step": 0, "confidence": "unsure"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code, 409)
        self.assertEqual(self.client.session["guest_practice"]["answers"][0], ["2", "", False])
        self.guest_post(url, {"action": "next", "step": 0})
        self.guest_post(url, {"action": "answer", "step": 1, "answer": "1"})
        self.assertContains(self.client.get(url), 'name="confidence"', count=2)
        for confidence in ("guessed", "unsure"):
            response = self.guest_post(url, {"action": "confidence", "step": 1, "confidence": confidence}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
            self.assertEqual(response.json(), {"saved": True, "confidence": confidence})
            self.assertContains(self.client.get(url), "✓ 이 체험에 반영했어요")
            self.assertEqual(self.client.session["guest_practice"]["answers"][1], ["1", confidence, True])
        self.guest_post(url, {"action": "next", "step": 1})
        self.assertEqual(self.client.session["guest_practice"]["step"], 2)

    def test_previous_run_forms_cannot_write_to_restarted_run(self):
        subject, _ = Subject.objects.get_or_create(code="realtor", defaults={"name": "공인중개사"})
        for index in range(5):
            Mission.objects.create(subject=subject, course="Guard", external_id=f"guard-{index}",
                title="Guard", prompt="Question", question_type="choice_one", correct_answer="1",
                answer_schema="1|One\n2|Two\n3|Three\n4|Four\n5|Five", explanation="Explanation")
        url = reverse("guest_practice")
        self.guest_post(url, {"action": "start", "subject": "realtor", "course": "Guard"})
        old = self.client.session["guest_practice"]["id"]
        self.guest_post(url, {"action": "start", "subject": "realtor", "course": "Guard"})
        for action in ("answer", "confidence", "next", "save"):
            response = self.guest_post(url, {"action": action, "run_id": old, "step": "0", "answer": "1", "confidence": "unsure"})
            self.assertEqual(response.status_code, 409)
            self.assertContains(response, "현재 체험으로 돌아가기", status_code=409)
        self.assertEqual(self.client.session["guest_practice"]["answers"], [])
        self.guest_post(url, {"action": "answer", "step": "0", "answer": "1"})
        rejected = self.guest_post(url, {"action": "confidence", "run_id": old, "step": "0", "confidence": "unsure"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(rejected.status_code, 409)
        self.assertFalse(rejected.json()["saved"])
        self.assertEqual(self.client.session["guest_practice"]["answers"][0][1], "")
        missing = self.client.post(url, {"action": "confidence", "step": "0", "confidence": "unsure"})
        self.assertEqual(missing.status_code, 409)
