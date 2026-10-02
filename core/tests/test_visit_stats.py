from datetime import timedelta
from unittest.mock import patch

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import DailyVisit, DailyVisitTotal, UserEvent
from core.services.visit_stats import daily_visit_report


@override_settings(VISITOR_STATS_OWNER_EMAIL="owner@example.com")
class VisitStatsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", email="owner@example.com")
        EmailAddress.objects.create(user=self.owner, email="owner@example.com", verified=True)
        SocialAccount.objects.create(user=self.owner, provider="google", uid="owner-google")
        self.learner = User.objects.create_user(username="learner")

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
