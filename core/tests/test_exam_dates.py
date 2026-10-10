from datetime import timedelta
from importlib import import_module

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import OfficialExamDate, StudyProfile, Subject, SubjectExamGoal
from core.services.personal_coach import build_personal_coach_context
from core.services.subjects import ensure_logistics_subject


class ExamDateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("date-learner", password="pw")
        self.logistics = ensure_logistics_subject()
        self.realtor, _ = Subject.objects.get_or_create(code="realtor", defaults={"name": "공인중개사"})
        self.client.force_login(self.user)

    def select_subject(self, subject):
        session = self.client.session
        session["current_subject_code"] = subject.code
        session.save()

    def test_verified_future_date_is_suggested_but_not_saved_until_confirmed(self):
        self.select_subject(self.realtor)
        date = timezone.localdate() + timedelta(days=21)
        official = OfficialExamDate.objects.create(
            subject=self.realtor, label="검증된 시험", exam_date=date,
            source_url="https://www.q-net.or.kr/site/junggae", verified_on=timezone.localdate(),
        )
        response = self.client.get(reverse("study_profile"))
        self.assertContains(response, "검증된 시험")
        self.assertContains(self.client.get(reverse("realtor_home")), "시험일 확인·설정")
        self.assertFalse(SubjectExamGoal.objects.filter(user=self.user).exists())
        self.client.post(reverse("study_profile"), {"action": "official", "official_id": official.pk})
        self.assertEqual(SubjectExamGoal.objects.get(user=self.user, subject=self.realtor).target_date, date)

    def test_manual_dates_are_independent_and_only_current_subject_is_shown(self):
        self.select_subject(self.logistics)
        logistics_date = timezone.localdate() + timedelta(days=45)
        realtor_date = timezone.localdate() + timedelta(days=5)
        self.client.post(reverse("study_profile"), {"target_exam_date": logistics_date.isoformat()})
        self.select_subject(self.realtor)
        self.client.post(reverse("study_profile"), {"target_exam_date": realtor_date.isoformat()})
        self.assertEqual(SubjectExamGoal.objects.filter(user=self.user).count(), 2)
        self.assertEqual(build_personal_coach_context(self.user, self.realtor)["dday_phase"], "review")
        self.assertEqual(build_personal_coach_context(self.user, self.logistics)["dday_phase"], "foundation")
        self.assertContains(self.client.get(reverse("realtor_home")), "D-5")
        self.select_subject(self.logistics)
        self.assertContains(self.client.get(reverse("mission_list")), "D-45")
        self.client.post(reverse("study_profile"), {"action": "clear"})
        self.assertFalse(SubjectExamGoal.objects.filter(user=self.user, subject=self.logistics).exists())
        self.assertTrue(SubjectExamGoal.objects.filter(user=self.user, subject=self.realtor).exists())

    def test_past_date_does_not_trigger_final_mode(self):
        SubjectExamGoal.objects.create(
            user=self.user, subject=self.logistics,
            target_date=timezone.localdate() - timedelta(days=1),
        )
        context = build_personal_coach_context(self.user, self.logistics)
        self.assertEqual(context["dday_phase"], "standard")
        self.assertIn("다음 응시일", context["dday_message"])

    def test_past_manual_date_is_rejected_without_overwriting_goal(self):
        self.select_subject(self.logistics)
        future = timezone.localdate() + timedelta(days=12)
        past = timezone.localdate() - timedelta(days=1)
        self.client.post(reverse("study_profile"), {"target_exam_date": future.isoformat()})
        response = self.client.post(reverse("study_profile"), {"target_exam_date": past.isoformat()})
        self.assertContains(response, "지난 날짜는 목표 시험일")
        self.assertEqual(SubjectExamGoal.objects.get(user=self.user, subject=self.logistics).target_date, future)

    def test_official_date_cannot_be_selected_for_another_subject(self):
        self.select_subject(self.logistics)
        official = OfficialExamDate.objects.filter(subject=self.realtor).first()
        response = self.client.post(reverse("study_profile"), {"action": "official", "official_id": official.pk})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(SubjectExamGoal.objects.filter(user=self.user).exists())

    def test_legacy_date_migration_preserves_date_without_duplication(self):
        legacy_date = timezone.localdate() + timedelta(days=14)
        StudyProfile.objects.create(user=self.user, target_exam_date=legacy_date)
        migrate = import_module("core.migrations.0050_subject_exam_dates").preserve_legacy_goals_and_seed_schedule
        migrate(apps, None)
        migrate(apps, None)
        goals = SubjectExamGoal.objects.filter(user=self.user, subject=self.logistics)
        self.assertEqual(goals.count(), 1)
        self.assertEqual(goals.get().target_date, legacy_date)
