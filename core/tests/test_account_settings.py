import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Attempt, AttemptWrongReason, ConfusionCard, DailyMission, ExamSession,
    ExamSessionMission, Inquiry, PatternTrainingSession, ProblemSet,
    ProblemSetSession, ProblemSetSessionItem, Mission, StudyProfile, Subject,
    UserAccess, UserEvent, UserStreak, UserWeakness, WrongPattern, WrongReason,
)
from core.services.account_data import reset_learning_data


class AccountSettingsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("member", password="SafePass123!")
        self.other = get_user_model().objects.create_user("other", password="SafePass123!")
        self.client.force_login(self.user)
        self.url = reverse("account_settings")
        self.subject = Subject.objects.create(code="reset-test", name="시험")
        self.mission = Mission.objects.create(subject=self.subject, external_id="reset-1", title="문제", skill="a")
        self.attempt = Attempt.objects.create(user=self.user, mission=self.mission)
        Attempt.objects.create(user=self.other, mission=self.mission)
        self.access = UserAccess.objects.create(user=self.user, is_premium=True)
        StudyProfile.objects.create(user=self.user, daily_minutes=20)
        self.inquiry = Inquiry.objects.create(user=self.user, name="회원", contact="contact", message="문의")

    def payload(self, action):
        return {"action": action, f"{action}-password": "SafePass123!",
                f"{action}-confirmation": "학습 기록 초기화" if action == "reset" else "회원 탈퇴",
                f"{action}-acknowledged": "on"}

    def test_login_required_and_get_does_not_delete(self):
        self.assertContains(self.client.get(self.url), "학습 기록 초기화")
        self.assertTrue(Attempt.objects.filter(pk=self.attempt.pk).exists())
        self.client.logout()
        self.assertEqual(self.client.post(self.url, self.payload("delete")).status_code, 302)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_password_phrase_and_acknowledgement_required(self):
        for field in ("password", "confirmation", "acknowledged"):
            with self.subTest(field=field):
                data = self.payload("delete")
                data[f"delete-{field}"] = ""
                self.assertEqual(self.client.post(self.url, data).status_code, 400)
                self.assertTrue(Attempt.objects.filter(pk=self.attempt.pk).exists())
        data = self.payload("reset")
        data["reset-password"] = "wrong"
        self.assertEqual(self.client.post(self.url, data).status_code, 400)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, self.payload("delete")).status_code, 403)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_reset_all_subjects_and_dependent_records_only(self):
        second = Subject.objects.create(code="reset-second", name="다른 시험")
        mission = Mission.objects.create(subject=second, external_id="reset-2", title="문제", skill="b")
        Attempt.objects.create(user=self.user, mission=mission)
        reason = WrongReason.objects.create(name="reset reason")
        AttemptWrongReason.objects.create(attempt=self.attempt, wrong_reason=reason)
        pattern = WrongPattern.objects.create(subject=self.subject, code="p", name="패턴")
        UserWeakness.objects.create(user=self.user, subject=self.subject, wrong_pattern=pattern)
        PatternTrainingSession.objects.create(user=self.user, wrong_pattern=pattern)
        DailyMission.objects.create(user=self.user, date=timezone.localdate(), mission=self.mission)
        UserStreak.objects.create(user=self.user, current_streak=2)
        ConfusionCard.objects.create(user=self.user, subject=self.subject, mission=self.mission)
        exam = ExamSession.objects.create(user=self.user)
        ExamSessionMission.objects.create(exam_session=exam, mission=self.mission, order_no=1)
        problem_set = ProblemSet.objects.create(title="세트")
        session = ProblemSetSession.objects.create(user=self.user, problem_set=problem_set)
        ProblemSetSessionItem.objects.create(problem_set_session=session, mission=self.mission, order_no=1, attempt=self.attempt)
        UserEvent.objects.create(user=self.user, event_type="finish_mission")
        UserEvent.objects.create(user=self.user, event_type="signup")
        other_device = Client()
        other_device.force_login(self.user)
        session = other_device.session
        session["pattern_training_results"] = [True]
        session.save()
        data = self.payload("reset")
        data["user_id"] = self.other.pk  # A supplied target is never trusted.
        self.assertRedirects(self.client.post(self.url, data), reverse("login"), fetch_redirect_response=False)
        for model in (Attempt, DailyMission, UserStreak, ConfusionCard, UserWeakness,
                      PatternTrainingSession, ExamSession, ProblemSetSession):
            self.assertFalse(model.objects.filter(user=self.user).exists(), model.__name__)
        self.assertFalse(AttemptWrongReason.objects.exists())
        self.assertFalse(ExamSessionMission.objects.exists())
        self.assertFalse(ProblemSetSessionItem.objects.exists())
        self.assertTrue(Attempt.objects.filter(user=self.other).exists())
        self.assertTrue(UserAccess.objects.get(user=self.user).is_premium)
        self.assertEqual(StudyProfile.objects.get(user=self.user).daily_minutes, 20)
        self.assertTrue(Inquiry.objects.filter(pk=self.inquiry.pk).exists())
        self.assertFalse(UserEvent.objects.filter(user=self.user, event_type="finish_mission").exists())
        self.assertTrue(UserEvent.objects.filter(user=self.user, event_type="signup").exists())
        self.assertEqual(Mission.objects.filter(subject__in=[self.subject, second]).count(), 2)
        self.assertEqual(other_device.get(self.url).status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_delete_removes_account_personal_data_and_social_credentials(self):
        from allauth.account.models import EmailAddress
        from allauth.socialaccount.models import SocialAccount
        social = SocialAccount.objects.create(user=self.user, provider="google", uid="test-member")
        EmailAddress.objects.create(user=self.user, email="member@example.com", verified=True)
        UserEvent.objects.create(user=self.user, event_type="signup", metadata={"personal": "test"})
        self.assertEqual(self.client.post(self.url, self.payload("delete")).status_code, 302)
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Inquiry.objects.filter(pk=self.inquiry.pk).exists())
        self.assertFalse(UserEvent.objects.filter(user_id=self.user.pk).exists())
        self.assertFalse(SocialAccount.objects.filter(pk=social.pk).exists())
        self.assertFalse(EmailAddress.objects.filter(email="member@example.com").exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.other.pk).exists())
        self.assertTrue(Mission.objects.filter(pk=self.mission.pk).exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_social_member_requires_recent_login(self):
        self.user.set_unusable_password()
        self.user.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url, self.payload("reset")).status_code, 400)
        with patch("core.views.account_settings.get_authentication_records", return_value=[
            {"method": "socialaccount", "at": time.time() - 3600},
        ]):
            self.assertEqual(self.client.post(self.url, self.payload("reset")).status_code, 400)
        with patch("core.views.account_settings.get_authentication_records", return_value=[
            {"method": "socialaccount", "at": time.time()},
        ]):
            self.assertEqual(self.client.post(self.url, self.payload("reset")).status_code, 302)
        self.assertFalse(Attempt.objects.filter(user=self.user).exists())

    def test_reset_is_atomic(self):
        with patch("core.services.account_data._remove_sessions", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                reset_learning_data(self.user)
        self.assertTrue(Attempt.objects.filter(pk=self.attempt.pk).exists())

    def test_unknown_action_rejected(self):
        self.assertEqual(self.client.post(self.url, {"action": "all"}).status_code, 400)
        self.assertTrue(Attempt.objects.filter(pk=self.attempt.pk).exists())
