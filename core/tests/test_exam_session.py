from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import ExamSession, ExamSessionMission, Mission, UserAccess


User = get_user_model()


class ExamResumeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="tester",
            password="1234",
        )
        UserAccess.objects.create(user=self.user, is_premium=True)

        self.mission = Mission.objects.create(
            external_id="TEST_EXAM_RESUME_001",
            title="시험 재개 테스트 문제",
            skill="IF",
            level=1,
            prompt="[CONTEXT]\n테스트\n[DATA]\nA1=1\n[QUESTION]\n테스트 문제",
            question_type="choice_one",
            learning_type="feature",
            answer_input_type="none",
            correct_answer="A",
            answer_schema="A|IF\nB|SUM",
            explanation="시험 재개 테스트용 문제입니다.",
            quality_level="practical",
            is_quality_checked=True,
            is_usable_for_set=True,
        )

    def test_resume_existing_exam_session(self):
        self.client.login(username="tester", password="1234")

        existing_session = ExamSession.objects.create(
            user=self.user,
            title="진행 중 시험",
            status="in_progress",
            total_questions=1,
        )
        ExamSessionMission.objects.create(
            exam_session=existing_session,
            mission=self.mission,
            order_no=1,
        )

        before_count = ExamSession.objects.count()

        response = self.client.post(reverse("exam_create"))

        after_count = ExamSession.objects.count()

        self.assertEqual(before_count, after_count)
        self.assertRedirects(
            response,
            reverse("exam_take", args=[existing_session.id, 1]),
            fetch_redirect_response=False,
        )
