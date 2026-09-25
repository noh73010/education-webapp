from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from core.models import Attempt, CourseFocus, Mission, Subject, UserWeakness, WrongPattern


class CourseFocusTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("course-focus", password="password")
        self.subject, _ = Subject.objects.get_or_create(code="logistics", defaults={"name": "물류관리사"})
        self.management = self.mission("management", "물류관리론", "LM01")
        self.transport = self.mission("transport", "화물운송론", "FT01")
        self.url = reverse("mission_list")
        self.client.force_login(self.user)

    def mission(self, key, course, chapter):
        return Mission.objects.create(
            external_id=f"focus-{key}", subject=self.subject, title=key,
            course=course, chapter_code=chapter, chapter_name=f"{course} 첫 단원",
            skill=chapter, question_type="choice_one", correct_answer="2",
            answer_schema="1|오답\n2|정답", prompt=f"{course} 문제", explanation="해설",
        )

    def choose(self, course):
        return self.client.post(self.url, {"course": course})

    def test_first_visit_chooses_one_of_five_courses_without_guessing_weakness(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/course_focus_select.html")
        self.assertEqual(len(response.context["course_options"]), 5)
        self.assertContains(response, "순서대로 시작하지 않아도 됩니다")
        self.assertFalse(CourseFocus.objects.filter(user=self.user).exists())

    def test_choice_is_validated_persisted_and_limits_daily_questions(self):
        self.assertEqual(self.choose("가짜 과목").status_code, 400)
        self.assertFalse(CourseFocus.objects.filter(user=self.user).exists())
        self.assertEqual(self.choose("화물운송론").status_code, 302)
        self.assertEqual(CourseFocus.objects.get(user=self.user).course, "화물운송론")
        response = self.client.get(self.url)
        self.assertContains(response, "화물운송론 목차")
        self.assertEqual(response.context["selected_course"], "화물운송론")
        self.assertEqual([row.id for row in response.context["recommended"]], [self.transport.id])
        self.assertEqual([row.id for row in response.context["missions"]], [self.transport.id])
        self.assertContains(response, "아직 풀이 기록이 없어요")
        self.assertNotContains(response, "물류관리론 문제")

        other_browser = Client()
        other_browser.force_login(self.user)
        self.assertEqual(other_browser.get(self.url).context["selected_course"], "화물운송론")

    def test_switching_course_does_not_delete_attempts_or_other_daily_plan(self):
        self.choose("화물운송론")
        self.client.get(self.url)
        first_plan = list(self.user.dailymission_set.values_list("mission_id", flat=True))
        attempt = Attempt.objects.create(user=self.user, mission=self.transport, is_correct=False)
        self.choose("물류관리론")
        response = self.client.get(self.url)
        self.assertEqual(response.context["selected_course"], "물류관리론")
        self.assertEqual([row.id for row in response.context["recommended"]], [self.management.id])
        self.assertTrue(Attempt.objects.filter(pk=attempt.pk).exists())
        self.assertTrue(set(first_plan).issubset(set(self.user.dailymission_set.values_list("mission_id", flat=True))))

    def test_weakness_is_scoped_to_selected_course(self):
        Attempt.objects.create(user=self.user, mission=self.management, is_correct=False)
        Attempt.objects.create(user=self.user, mission=self.transport, is_correct=False)
        pattern = WrongPattern.objects.create(
            subject=self.subject, code="focus-ft", skill="FT01", name="화물운송의 기초 핵심 개념 혼동",
        )
        UserWeakness.objects.create(
            user=self.user, subject=self.subject, wrong_pattern=pattern,
            status=UserWeakness.STATUS_ACTIVE, severity=3, recent_failure_count=2,
        )
        self.choose("물류관리론")
        management = self.client.get(self.url)
        self.assertEqual(management.context["selected_course_weakness"]["state"], "none")
        self.choose("화물운송론")
        transport = self.client.get(self.url)
        self.assertEqual(transport.context["selected_course_weakness"]["label"], "화물운송의 기초")
        self.assertContains(transport, "화물운송론의 약점")
