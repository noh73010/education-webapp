from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Attempt, Mission, ProblemSet, ProblemSetItem
from core.services.subjects import (
    CURRENT_SUBJECT_SESSION_KEY,
    LOGISTICS_SUBJECT_CODE,
    seed_platform_subjects,
)


class LearningQuestionCardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        subjects = seed_platform_subjects()
        cls.subject = next(
            subject for subject in subjects
            if subject.code == LOGISTICS_SUBJECT_CODE
        )
        cls.user = User.objects.create_user(
            username="card_learner",
            password="pass12345",
        )
        cls.mission = Mission.objects.create(
            external_id="INTERNAL_CARD_EXTERNAL_ID",
            subject=cls.subject,
            course="물류관련법규",
            chapter_code="LW06",
            chapter_name="항만운송사업법",
            title="logistics 29-2 · 물류관련법규 80번",
            skill="LW06",
            level=2,
            prompt="농수산물공판장에 관한 설명으로 옳지 않은 것을 고르는 문제입니다. 관련 법률의 적용 범위와 예외 사항을 함께 판단하세요.",
            question_type="choice_one",
            correct_answer="1",
            answer_schema="1|첫 번째 보기\n2|두 번째 보기",
        )
        Attempt.objects.create(user=cls.user, mission=cls.mission, is_correct=True)
        Attempt.objects.create(user=cls.user, mission=cls.mission, is_correct=False)
        Attempt.objects.create(user=cls.user, mission=cls.mission, is_correct=False)

        cls.problem_set = ProblemSet.objects.create(
            title="항만운송사업법 핵심 문제",
            skill_group="LW06",
            level=2,
            set_type="training",
        )
        ProblemSetItem.objects.create(
            problem_set=cls.problem_set,
            mission=cls.mission,
            order_no=1,
            role="core",
        )

    def setUp(self):
        self.client.force_login(self.user)
        session = self.client.session
        session[CURRENT_SUBJECT_SESSION_KEY] = LOGISTICS_SUBJECT_CODE
        session.save()

    def test_recommendation_and_search_use_learner_facing_cards(self):
        response = self.client.get(reverse("mission_list"), {"q": "농수산물공판장"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="learning-question-card"')
        self.assertContains(response, "📘")
        self.assertContains(response, "물류관련법규")
        self.assertContains(response, "농수산물공판장에 관한 설명으로")
        self.assertContains(response, "풀이 3회 · 정답률 33%")
        self.assertContains(response, "최근: 오답")
        self.assertNotContains(response, self.mission.title)
        self.assertNotContains(response, self.mission.skill)
        self.assertNotContains(response, self.mission.external_id)

    def test_problem_set_preview_uses_same_cards_and_simple_summary(self):
        response = self.client.get(
            reverse("problem_set_detail", args=[self.problem_set.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="learning-question-card"')
        self.assertContains(response, "문제 1")
        self.assertContains(response, "총 1문제")
        self.assertContains(response, "예상 소요시간 약 1분")
        self.assertContains(response, "과목: 물류관련법규")
        self.assertContains(response, "단원: 항만운송사업법")
        self.assertContains(response, "풀이 3회 · 정답률 33%")
        self.assertNotContains(response, self.mission.title)
        self.assertNotContains(response, self.mission.skill)
        self.assertNotContains(response, "역할:")
        self.assertNotContains(response, "Lv 2")

    def test_question_excerpt_is_limited_to_sixty_characters(self):
        response = self.client.get(
            reverse("problem_set_detail", args=[self.problem_set.id]),
        )

        expected = f"{self.mission.prompt[:60].rstrip()}..."
        self.assertContains(response, expected)
        self.assertNotContains(response, self.mission.prompt)
