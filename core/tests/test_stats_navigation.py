from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Attempt, AttemptWrongReason, Mission, Subject, WrongReason


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StatsNavigationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("stats-learner")
        self.other = get_user_model().objects.create_user("other-stats-learner")
        self.realtor = Subject.objects.get(code="realtor")
        self.logistics = Subject.objects.get(code="logistics")
        self.mission = Mission.objects.create(
            subject=self.realtor, external_id="stats-re05-03", title="지적공부 문제",
            course="부동산공시법 및 부동산세법", chapter_code="RE05-03",
            chapter_name="이전 데이터 단원명", skill="RE05-03",
            prompt="지적공부에서 확인할 사항은?", question_type="choice_one",
            answer_schema="1|정답\n2|오답", correct_answer="1", explanation="지적공부 해설",
        )
        self.reason, _ = WrongReason.objects.get_or_create(name="문제를 잘못 읽음")
        self.client.force_login(self.user)
        session = self.client.session
        session["current_subject_code"] = self.realtor.code
        session.save()

    def make_wrong(self, user=None, mission=None):
        attempt = Attempt.objects.create(
            user=user or self.user, mission=mission or self.mission,
            submitted_answer="2", is_correct=False,
        )
        AttemptWrongReason.objects.create(attempt=attempt, wrong_reason=self.reason)
        return attempt

    def test_realtor_scope_uses_subject_and_canonical_chapter_names(self):
        first = self.make_wrong()
        self.make_wrong()
        response = self.client.get(reverse("stats"))
        self.assertContains(response, "부동산공시법")
        self.assertContains(response, "지적공부")
        self.assertNotContains(response, "RE05-03")
        detail_url = reverse("mission_detail", args=[self.mission.pk]) + f"?attempt={first.pk}"
        self.assertContains(response, detail_url.replace("&", "&amp;"))
        self.assertContains(self.client.get(detail_url), "지적공부 해설")

    def test_wrong_reason_problems_are_scoped_and_paginated(self):
        mine = [self.make_wrong() for _ in range(23)]
        self.make_wrong(user=self.other)
        other_subject_mission = Mission.objects.create(
            subject=self.logistics, external_id="stats-logistics", title="물류 문제",
            skill="LM01", prompt="다른 자격증 문제", question_type="choice_one",
            answer_schema="1|정답\n2|오답", correct_answer="1",
        )
        self.make_wrong(mission=other_subject_mission)
        stats = self.client.get(reverse("stats"))
        self.assertContains(stats, "문제를 잘못 읽음 · 23회")
        self.assertContains(stats, reverse("wrong_reason_attempts", args=[self.reason.pk]))

        url = reverse("wrong_reason_attempts", args=[self.reason.pk])
        first_page = self.client.get(url)
        self.assertEqual(first_page.context["page_obj"].paginator.count, 23)
        self.assertEqual(len(first_page.context["page_obj"].object_list), 20)
        self.assertContains(first_page, f"?attempt={mine[-1].pk}")
        second_page = self.client.get(url, {"page": "2"})
        self.assertEqual(len(second_page.context["page_obj"].object_list), 3)
        self.assertNotContains(first_page, "다른 자격증 문제")

        Attempt.objects.filter(pk=mine[-1].pk).update(created_at=timezone.now() - timedelta(days=40))
        recent = self.client.get(url, {"period": "7"})
        self.assertEqual(recent.context["page_obj"].paginator.count, 22)
