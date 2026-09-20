from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Attempt, Mission, Subject, UserAccess
from core.services.subjects import CURRENT_SUBJECT_SESSION_KEY
from core.views.wrong_notes import WRONG_NOTES_PAGE_SIZE


class WrongNotesPaginationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("wrong-note-user")
        UserAccess.objects.create(user=self.user, is_premium=False)
        self.subject, _ = Subject.objects.update_or_create(
            code="logistics",
            defaults={"name": "물류관리사", "is_active": True},
        )
        self.other_subject = Subject.objects.create(
            code="other-cert",
            name="다른 자격증",
            is_active=True,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session[CURRENT_SUBJECT_SESSION_KEY] = self.subject.code
        session.save()

    def create_mission(self, number, *, subject=None, skill="LM01"):
        return Mission.objects.create(
            external_id=f"WRONG-PAGE-{number:03d}",
            subject=subject or self.subject,
            course="물류관리론",
            chapter_code=skill,
            chapter_name="물류관리총론",
            title=f"오답 페이지 문제 {number}",
            skill=skill,
            level=1,
            prompt=f"페이지네이션 확인용 문제 본문 {number}",
            answer_schema="1|보기 1|2|보기 2",
            correct_answer="1",
            explanation="해설",
            question_type="choice_one",
            is_usable_for_set=True,
        )

    def create_wrong_attempts(self, count, *, subject=None, skill="LM01", start=0):
        attempts = []
        for number in range(start, start + count):
            mission = self.create_mission(number, subject=subject, skill=skill)
            attempts.append(Attempt.objects.create(
                user=self.user,
                mission=mission,
                submitted_answer="2",
                is_correct=False,
            ))
        return attempts

    @override_settings(PREMIUM_GATING_ENABLED=False)
    def test_only_one_mobile_sized_page_is_rendered(self):
        self.create_wrong_attempts(205)

        response = self.client.get(reverse("wrong_notes"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["wrong_items"]), WRONG_NOTES_PAGE_SIZE)
        self.assertEqual(response.context["page_obj"].paginator.count, 205)
        self.assertEqual(response.context["page_obj"].paginator.num_pages, 11)
        self.assertEqual(
            response.content.count(b'class="info-box mb-medium"'),
            WRONG_NOTES_PAGE_SIZE,
        )

    @override_settings(PREMIUM_GATING_ENABLED=False)
    def test_page_links_preserve_filters_and_second_page_has_only_its_items(self):
        attempts = self.create_wrong_attempts(25, skill="LM01")

        response = self.client.get(reverse("wrong_notes"), {
            "mode": "all",
            "days": "30",
            "skill": "LM01",
        })

        self.assertEqual(
            response.context["filter_query"],
            "mode=all&days=30&skill=LM01",
        )
        self.assertContains(
            response,
            "?mode=all&amp;days=30&amp;skill=LM01&amp;page=2#wrong-note-list",
        )

        second_page = self.client.get(reverse("wrong_notes"), {
            "mode": "all",
            "days": "30",
            "skill": "LM01",
            "page": "2",
        })
        second_page_ids = [
            item["attempt"].id for item in second_page.context["wrong_items"]
        ]
        self.assertEqual(len(second_page_ids), 5)
        self.assertEqual(second_page_ids, [attempt.id for attempt in reversed(attempts[:5])])

    @override_settings(PREMIUM_GATING_ENABLED=False)
    def test_latest_attempt_state_drives_open_filter_and_actions_stay_distinct(self):
        mission = self.create_mission(1)
        old_wrong = Attempt.objects.create(
            user=self.user,
            mission=mission,
            submitted_answer="2",
            is_correct=False,
        )
        Attempt.objects.create(
            user=self.user,
            mission=mission,
            submitted_answer="1",
            is_correct=True,
        )

        open_response = self.client.get(reverse("wrong_notes"))
        self.assertEqual(open_response.context["wrong_items"], [])

        all_response = self.client.get(reverse("wrong_notes"), {"mode": "all"})
        self.assertEqual(len(all_response.context["wrong_items"]), 1)
        latest_attempt = all_response.context["wrong_items"][0]["attempt"]
        self.assertTrue(latest_attempt.is_correct)
        self.assertNotEqual(latest_attempt.id, old_wrong.id)
        self.assertContains(
            all_response,
            f'{reverse("mission_detail", args=[mission.id])}?attempt={latest_attempt.id}',
        )
        self.assertContains(all_response, ">다시 풀기</a>", html=False)

    @override_settings(PREMIUM_GATING_ENABLED=False)
    def test_attempts_from_another_subject_are_not_counted_or_rendered(self):
        own_attempt = self.create_wrong_attempts(1)[0]
        other_attempt = self.create_wrong_attempts(
            1,
            subject=self.other_subject,
            start=100,
        )[0]

        response = self.client.get(reverse("wrong_notes"))
        rendered_ids = [item["attempt"].id for item in response.context["wrong_items"]]

        self.assertEqual(rendered_ids, [own_attempt.id])
        self.assertNotContains(response, other_attempt.mission.prompt)

    @override_settings(PREMIUM_GATING_ENABLED=True)
    def test_future_free_policy_still_caps_wrong_notes_at_five(self):
        self.create_wrong_attempts(8)

        response = self.client.get(reverse("wrong_notes"), {"page": "2"})

        self.assertEqual(len(response.context["wrong_items"]), 5)
        self.assertTrue(response.context["is_limited"])
        self.assertFalse(response.context["has_full_access"])
        self.assertEqual(response.context["page_obj"].number, 1)
        self.assertEqual(response.context["page_obj"].paginator.num_pages, 1)
        self.assertContains(response, "무료 회원은 오답노트를 5개까지만")
