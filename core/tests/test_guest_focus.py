from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from core.models import Attempt, Mission, Subject, UserEvent
from core.services.guest_focus import FOCUS, TITLE, identity, trial_funnel


class GuestFocusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        subject, _ = Subject.objects.get_or_create(code="realtor", defaults={"name": "공인중개사"})
        for source, alternative, title, _ in FOCUS:
            for short in (source, alternative):
                Mission.objects.get_or_create(external_id=identity(short), defaults=dict(
                    subject=subject, course="민법 및 민사특별법", chapter_code="RE02-01", chapter_name="민법 총칙",
                    title=title, prompt="사례 " + short, question_type="choice_one", correct_answer="1",
                    answer_schema="1|가\n2|나\n3|다\n4|라\n5|마", explanation="비공개 해설 " + short))
        cls.url = reverse("guest_practice")

    def post(self, action, **data):
        return self.client.post(self.url, {"action": action, "run_id": self.client.session.get("guest_practice", {}).get("id", ""), **data})

    def complete(self, wrong=None, unsure=None):
        self.post("start", subject="realtor", entry_mode="focus")
        for step in range(5):
            self.post("answer", step=step, answer="2" if step == wrong else "1")
            if step == unsure:
                self.post("confidence", step=step, confidence="unsure")
            self.post("next", step=step)

    def test_curated_entry_and_no_preview_answer_leak(self):
        page = self.client.get(reverse("landing"))
        self.assertContains(page, TITLE)
        self.assertNotContains(page, "비공개 해설")
        self.post("start", subject="realtor", entry_mode="focus")
        state = self.client.session["guest_practice"]
        ids = [Mission.objects.get(pk=pk).external_id for pk, _ in state["questions"]]
        self.assertEqual(ids, [identity(x[0]) for x in FOCUS])
        self.assertNotContains(self.client.get(self.url), "비공개 해설")

    def test_wrong_takes_priority_and_bonus_is_new_and_not_spoiled(self):
        self.complete(wrong=2, unsure=0)
        page = self.client.get(self.url)
        self.assertEqual(page.context["guidance"]["title"], FOCUS[2][2])
        original = self.client.session["guest_practice"]["questions"]
        self.post("followup_start")
        page = self.client.get(self.url)
        self.assertEqual(page.context["bonus"]["mission"].external_id, identity(FOCUS[2][1]))
        self.assertNotContains(page, "비공개 해설 " + FOCUS[2][1])
        self.assertEqual(self.client.session["guest_practice"]["questions"], original)
        self.post("followup_answer", answer="1")
        self.assertContains(self.client.get(self.url), "비공개 해설 " + FOCUS[2][1])
        self.post("followup_answer", answer="2")
        self.assertTrue(self.client.session["guest_practice"]["followup"]["correct"])
        self.assertEqual(UserEvent.objects.filter(event_type="trial_followup_answer").count(), 1)

    def test_all_correct_challenge_without_claiming_weakness_and_no_forced_signup(self):
        self.complete()
        page = self.client.get(self.url)
        self.assertFalse(page.context["guidance"]["needs_review"])
        self.assertContains(page, "모두 맞혔다면, 다른 사례로 한 번 더")
        self.assertContains(page, "전체 실력이나 합격 가능성을 판단하는 진단은 아닙니다")
        self.assertFalse(Attempt.objects.exists())
        self.assertEqual(UserEvent.objects.filter(event_type="trial_start").count(), 1)
        self.client.get(self.url)
        self.post("next", step=4)
        self.assertEqual(UserEvent.objects.filter(event_type="trial_complete").count(), 1)

    def test_login_save_includes_bonus_once_and_preserves_review_targets(self):
        self.complete(wrong=0)
        self.post("followup_start")
        self.post("followup_answer", answer="2")
        user = get_user_model().objects.create_user(username="focus-learner")
        self.client.force_login(user)
        response = self.post("save")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Attempt.objects.filter(user=user).count(), 6)
        save = UserEvent.objects.get(event_type="guest_practice_saved", user=user)
        self.assertEqual(len(save.metadata["review_missions"]), 2)
        self.assertEqual(save.metadata["entry_mode"], "focus")
        self.post("save")
        self.assertEqual(Attempt.objects.filter(user=user).count(), 6)
        self.assertEqual(UserEvent.objects.filter(event_type="trial_saved").count(), 1)

    def test_stale_bonus_does_not_discard_original_results_or_grade_old_content(self):
        self.complete(wrong=1)
        self.post("followup_start")
        pk = self.client.session["guest_practice"]["followup"]["pk"]
        Mission.objects.filter(pk=pk).update(content_version=2)
        page = self.client.get(self.url)
        self.assertContains(page, "추가 문제가 업데이트")
        self.assertEqual(len(self.client.session["guest_practice"]["answers"]), 5)
        self.assertIsNone(page.context["bonus"])
        self.post("followup_answer", answer="1")
        self.assertNotIn("followup", self.client.session["guest_practice"])

    def test_old_run_cannot_start_or_answer_followup(self):
        self.complete(wrong=1)
        old = self.client.session["guest_practice"]["id"]
        self.post("start", subject="realtor", entry_mode="focus")
        for action in ("followup_start", "followup_answer"):
            self.assertEqual(self.post(action, run_id=old, answer="1").status_code, 409)

    def test_fallback_when_curated_set_incomplete_and_no_alternative(self):
        Mission.objects.all().delete()
        subject = Subject.objects.get(code="realtor")
        for i in range(5):
            Mission.objects.create(subject=subject, course="Fallback", title="Fallback", prompt="Question",
                external_id=f"fallback-{i}", question_type="choice_one", correct_answer="1",
                answer_schema="1|a\n2|b\n3|c\n4|d\n5|e", explanation="Explanation")
        self.complete(wrong=0)
        page = self.client.get(self.url)
        self.assertIsNone(page.context["guidance"]["alternative"])
        self.assertContains(page, "연결된 추가 문제는 아직 준비 중")
        self.assertEqual(self.client.session["guest_practice"]["entry_mode"], "daily")

    def test_next_day_review_excludes_today_and_requires_saved_target_attempt(self):
        self.complete(wrong=0)
        user = get_user_model().objects.create_user(username="return-learner")
        self.client.force_login(user)
        self.post("save")
        save = UserEvent.objects.get(event_type="guest_practice_saved")
        now = timezone.now()
        UserEvent.objects.filter(pk=save.pk).update(created_at=now-timedelta(days=2))
        attempt = Attempt.objects.get(user=user, mission_id=save.metadata["review_missions"][0])
        Attempt.objects.filter(pk=attempt.pk).update(created_at=now-timedelta(days=1))
        funnel = trial_funnel(timezone.localdate()-timedelta(days=4), timezone.localdate())
        self.assertEqual((funnel["next_day_review"], funnel["eligible_saves"]), (1, 1))
