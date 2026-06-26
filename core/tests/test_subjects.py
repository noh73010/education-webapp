from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from core.models import Mission, Subject
from core.services.mission_quality import usable_missions
from core.services.subjects import (
    CURRENT_SUBJECT_SESSION_KEY,
    DEFAULT_SUBJECT_CODE,
    LOGISTICS_SUBJECT_CODE,
    get_default_subject,
    seed_platform_subjects,
)


class SubjectPlatformTests(TestCase):
    def create_mission(self, external_id, subject=None, is_usable=True):
        return Mission.objects.create(
            external_id=external_id,
            subject=subject,
            title=f"{external_id} title",
            skill="COUNT",
            level=1,
            prompt="[CONTEXT]\n출석표\n[DATA]\nA1:A5\n[QUESTION]\n결석 횟수를 확인하세요.",
            correct_answer="1",
            explanation="COUNT 계열 함수 학습용 테스트 문제입니다.",
            quality_level="practical",
            is_quality_checked=True,
            is_usable_for_set=is_usable,
        )

    def test_ensure_default_subject_command_assigns_legacy_missions(self):
        mission = self.create_mission("SUBJECT_LEGACY", subject=None)
        out = StringIO()

        call_command("ensure_default_subject", stdout=out)
        mission.refresh_from_db()

        self.assertEqual(mission.subject.code, DEFAULT_SUBJECT_CODE)
        self.assertTrue(Subject.objects.filter(code=DEFAULT_SUBJECT_CODE).exists())
        self.assertIn("Default subject ready", out.getvalue())

    def test_usable_missions_filters_by_default_subject(self):
        default_subject = get_default_subject()
        other_subject = Subject.objects.create(code="sqld", name="SQLD")
        default_mission = self.create_mission("SUBJECT_DEFAULT", subject=default_subject)
        self.create_mission("SUBJECT_SQLD", subject=other_subject)

        missions = list(usable_missions())

        self.assertIn(default_mission, missions)
        self.assertTrue(all(mission.subject_id == default_subject.id for mission in missions))

    def test_mission_list_works_with_default_subject(self):
        subject = get_default_subject()
        self.create_mission("SUBJECT_HOME", subject=subject)
        user = User.objects.create_user(username="learner", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("mission_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "현재 과목")
        self.assertContains(response, "컴활 2급")

    def test_mission_list_sets_default_subject_when_session_is_empty(self):
        subject = get_default_subject()
        self.create_mission("SUBJECT_HOME_FALLBACK", subject=subject)
        user = User.objects.create_user(username="fallback", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("mission_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session[CURRENT_SUBJECT_SESSION_KEY], subject.code)
        self.assertContains(response, "과목을 아직 선택하지 않아 기본 과목으로 시작합니다.")

    def test_seed_subjects_command_creates_logistics_subject(self):
        out = StringIO()

        call_command("seed_subjects", stdout=out)

        self.assertTrue(
            Subject.objects.filter(
                code=LOGISTICS_SUBJECT_CODE,
                name="물류관리사",
                is_active=True,
            ).exists()
        )
        self.assertIn("logistics", out.getvalue())

    def test_logistics_subject_without_missions_does_not_break_mission_list(self):
        seed_platform_subjects()
        user = User.objects.create_user(username="logistics", password="pass12345")
        self.client.force_login(user)
        session = self.client.session
        session[CURRENT_SUBJECT_SESSION_KEY] = LOGISTICS_SUBJECT_CODE
        session.save()

        response = self.client.get(reverse("mission_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "현재 과목")
        self.assertContains(response, "물류관리사")
        self.assertContains(response, "현재 선택한 과목에는 아직 준비된 문제가 없습니다")
