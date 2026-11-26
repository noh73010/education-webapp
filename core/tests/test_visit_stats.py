from datetime import timedelta
from unittest.mock import patch

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Attempt, DailyVisit, DailyVisitTotal, Mission, UserEvent
from core.services.visit_stats import daily_visit_report


@override_settings(VISITOR_STATS_OWNER_EMAIL="owner@example.com")
class VisitStatsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", email="owner@example.com")
        EmailAddress.objects.create(user=self.owner, email="owner@example.com", verified=True)
        SocialAccount.objects.create(user=self.owner, provider="google", uid="owner-google")
        self.learner = User.objects.create_user(username="learner")

    def test_next_day_review_requires_same_account_and_saved_question(self):
        mission = Mission.objects.create(external_id="review-first", title="Review", prompt="Review")
        other_mission = Mission.objects.create(external_id="review-other", title="Another", prompt="Another")
        now = timezone.now()
        yesterday = timezone.localdate() - timedelta(days=1)
        save = UserEvent.objects.create(user=self.learner, event_type="guest_practice_saved", metadata={
            "course": "realtor-naver-fees", "review_missions": [mission.pk],
        })
        UserEvent.objects.filter(pk=save.pk).update(created_at=now - timedelta(days=1))
        Attempt.objects.create(user=self.owner, mission=mission, submitted_answer="1")
        Attempt.objects.create(user=self.learner, mission=other_mission, submitted_answer="1")
        same_day = Attempt.objects.create(user=self.learner, mission=mission, submitted_answer="1")
        Attempt.objects.filter(pk=same_day.pk).update(created_at=now - timedelta(days=1))
        self.client.force_login(self.owner)
        url = reverse("visit_stats")
        def reviews():
            response = self.client.get(url, {"funnel_days": "7", "funnel_end": yesterday.isoformat()})
            return dict(response.context["blog_rows"])["네이버 글 · 중개보수 계산"][-1]
        self.assertEqual(reviews(), 0)
        for _ in range(2):
            Attempt.objects.create(user=self.learner, mission=mission, submitted_answer="2")
        self.assertEqual(reviews(), 1)

    def test_owner_only_even_when_another_account_has_same_email(self):
        other = User.objects.create_user(username="other", email="owner@example.com", is_staff=True)
        SocialAccount.objects.create(user=other, provider="google", uid="other-google")
        url = reverse("visit_stats")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get(reverse("account_settings")), "방문 계정 통계 보기")

    @override_settings(VISITOR_STATS_OWNER_EMAIL="")
    def test_unconfigured_owner_is_denied(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("visit_stats")).status_code, 404)

    def test_guest_visit_is_deduplicated_and_next_day_is_returning(self):
        landing = reverse("landing")
        today = timezone.localdate()
        self.client.get(landing, HTTP_USER_AGENT="ExampleBot")
        with patch("core.middleware.timezone.localdate", return_value=today - timedelta(days=1)):
            self.client.get(landing)
            self.client.get(landing)
        self.client.get(landing)
        self.client.get(landing)
        events = UserEvent.objects.filter(event_type="guest_visit_day", user__isnull=True)
        self.assertEqual(events.count(), 2)
        self.assertEqual(events.filter(metadata__returning=True).count(), 1)

    def test_visit_is_unique_per_account_and_day(self):
        self.client.force_login(self.learner)
        self.client.get(reverse("landing"))
        self.client.get(reverse("mission_list"))
        self.assertEqual(DailyVisit.objects.filter(user=self.learner).count(), 1)

        second_browser = self.client_class()
        second_browser.force_login(self.learner)
        second_browser.get(reverse("landing"))
        self.assertEqual(DailyVisit.objects.filter(user=self.learner).count(), 1)
        self.assertEqual(DailyVisitTotal.objects.get(day=timezone.localdate()).count, 1)

    def test_owner_can_see_registered_members_and_selected_day_visitors(self):
        self.learner.email = "learner@example.com"
        self.learner.save(update_fields=["email"])
        DailyVisit.objects.create(user=self.learner, day=timezone.localdate())
        DailyVisitTotal.objects.create(day=timezone.localdate(), count=1)
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("visit_stats"),
            {"day": timezone.localdate().isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "가입 회원 목록")
        self.assertContains(response, "learner@example.com")
        self.assertContains(response, "방문 회원")

    def test_other_member_cannot_access_member_or_visitor_lists(self):
        self.client.force_login(self.learner)

        response = self.client.get(reverse("visit_stats"))

        self.assertEqual(response.status_code, 404)

    def test_new_day_and_account_switch_are_recorded(self):
        today = timezone.localdate()
        with patch("core.middleware.timezone.localdate", return_value=today - timedelta(days=1)):
            self.client.force_login(self.learner)
            self.client.get(reverse("landing"))
        self.client.get(reverse("landing"))
        self.assertEqual(DailyVisit.objects.filter(user=self.learner).count(), 2)
        another_learner = User.objects.create_user(username="another_learner")
        self.client.force_login(another_learner)
        self.client.get(reverse("landing"))
        self.assertEqual(DailyVisit.objects.filter(user=another_learner).count(), 1)
        self.assertEqual(DailyVisitTotal.objects.get(day=today).count, 2)

    def test_staff_and_unauthenticated_requests_are_not_counted(self):
        self.client.get(reverse("landing"))
        staff = User.objects.create_user(username="staff", is_staff=True)
        self.client.force_login(staff)
        self.client.get(reverse("landing"))
        self.assertEqual(DailyVisit.objects.count(), 0)

    def test_old_event_counts_are_labeled_as_partial_not_exact(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        old_event = UserEvent.objects.create(user=self.learner, event_type="login")
        UserEvent.objects.filter(pk=old_event.pk).update(created_at=timezone.now() - timedelta(days=1))
        other = UserEvent.objects.create(user=self.learner, event_type="finish_mission")
        UserEvent.objects.filter(pk=other.pk).update(created_at=timezone.now() - timedelta(days=1))
        DailyVisit.objects.create(user=self.learner, day=timezone.localdate())
        DailyVisitTotal.objects.create(day=timezone.localdate(), count=1)

        rows = daily_visit_report(days=2)
        self.assertEqual(rows[0]["count"], 1)
        self.assertTrue(rows[0]["exact"])
        self.assertEqual(rows[1]["day"], yesterday)
        self.assertEqual(rows[1]["count"], 1)
        self.assertFalse(rows[1]["exact"])

    def test_anonymous_total_survives_member_deletion(self):
        self.client.force_login(self.learner)
        self.client.get(reverse("landing"))
        self.learner.delete()

        self.assertEqual(DailyVisit.objects.count(), 0)
        self.assertEqual(daily_visit_report(days=1)[0]["count"], 1)
