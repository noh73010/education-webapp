from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Attempt, ExamSession, ExamSessionMission, Mission
from core.services.subjects import CURRENT_SUBJECT_SESSION_KEY, LOGISTICS_SUBJECT_CODE, seed_platform_subjects


class CbtQuestionUiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        subjects = seed_platform_subjects()
        cls.subject = next(subject for subject in subjects if subject.code == LOGISTICS_SUBJECT_CODE)
        cls.mission = Mission.objects.create(
            external_id="CBT_INTERNAL_EXTERNAL_ID",
            subject=cls.subject,
            course="보관하역론",
            chapter_code="WH02",
            chapter_name="하역론",
            difficulty="상",
            title="logistics 29-2 · 보관하역론 29번",
            skill="WH02",
            level=3,
            prompt="다음 중 하역장비 선정 시 일반적으로 고려하지 않는 요소는?",
            question_type="choice_one",
            answer_input_type="none",
            correct_answer="2",
            answer_schema="1|첫 번째 보기\n2|두 번째 보기\n3|세 번째 보기\n4|네 번째 보기\n5|다섯 번째 보기",
            explanation="두 번째 보기가 정답입니다.",
        )
        cls.last_mission = Mission.objects.create(
            external_id="CBT_LAST_MISSION",
            subject=cls.subject,
            course="보관하역론",
            chapter_code="WH02",
            chapter_name="하역론",
            title="마지막 문제 내부 제목",
            skill="WH02",
            prompt="마지막 문제입니다.",
            question_type="choice_one",
            correct_answer="1",
            answer_schema="1|정답\n2|오답",
        )
        cls.user = User.objects.create_user(username="cbt_learner", password="pass12345")

    def setUp(self):
        self.client.force_login(self.user)
        session = self.client.session
        session[CURRENT_SUBJECT_SESSION_KEY] = LOGISTICS_SUBJECT_CODE
        session.save()

    def test_learning_question_shows_only_learner_facing_information(self):
        response = self.client.get(reverse("mission_detail", args=[self.mission.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "보관하역론")
        self.assertContains(response, self.mission.prompt)
        self.assertContains(response, "답안을 선택하세요.")
        self.assertContains(response, "답안 제출")
        self.assertContains(response, "첫 번째 보기")
        self.assertContains(response, 'class="cbt-choice-marker"', count=5)
        self.assertNotContains(response, self.mission.title)
        self.assertNotContains(response, "스킬:")
        self.assertNotContains(response, "WH02")
        self.assertNotContains(response, "난이도:")
        self.assertNotContains(response, "객관식 단일 선택형")

    def test_learning_question_submission_behavior_is_unchanged(self):
        response = self.client.post(
            reverse("mission_detail", args=[self.mission.id]),
            {"submitted_answer": "2"},
        )

        self.assertEqual(response.status_code, 200)
        attempt = Attempt.objects.get(user=self.user, mission=self.mission)
        self.assertTrue(attempt.is_correct)
        self.assertContains(response, "정답입니다.")

    def test_problem_set_button_label_matches_progress(self):
        session = self.client.session
        session["problem_set_mission_ids"] = [self.mission.id, self.last_mission.id]
        session.save()

        middle_response = self.client.get(reverse("mission_detail", args=[self.mission.id]))
        last_response = self.client.get(reverse("mission_detail", args=[self.last_mission.id]))

        self.assertContains(middle_response, "다음 문제")
        self.assertNotContains(middle_response, "정답 확인")
        self.assertContains(last_response, "결과 확인")
        self.assertNotContains(last_response, "정답 확인")

    def test_exam_question_uses_same_focused_presentation(self):
        exam = ExamSession.objects.create(user=self.user, total_questions=1)
        ExamSessionMission.objects.create(exam_session=exam, mission=self.mission, order_no=1)

        response = self.client.get(reverse("exam_take", args=[exam.id, 1]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "보관하역론")
        self.assertContains(response, self.mission.prompt)
        self.assertContains(response, "답안을 선택하세요.")
        self.assertContains(response, "답안 제출 및 종료")
        self.assertNotContains(response, self.mission.title)
        self.assertNotContains(response, "스킬:")
        self.assertNotContains(response, "난이도:")
        self.assertNotContains(response, "객관식 단일 선택형")

    def test_admin_change_page_keeps_internal_mission_fields(self):
        admin_user = User.objects.create_superuser(
            username="cbt_admin",
            email="admin@example.com",
            password="pass12345",
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("admin:core_mission_change", args=[self.mission.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.mission.external_id)
        self.assertContains(response, self.mission.skill)
        self.assertContains(response, self.mission.difficulty)
        self.assertContains(response, str(self.mission.id))
