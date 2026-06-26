from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.services.subjects import (
    CURRENT_SUBJECT_SESSION_KEY,
    LOGISTICS_SUBJECT_CODE,
    get_default_subject,
    seed_platform_subjects,
)


class LandingPageTests(TestCase):
    def test_landing_page_is_public(self):
        response = self.client.get(reverse("landing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "학습할 과목을 선택하세요")
        self.assertContains(response, "과목 선택")
        self.assertContains(response, "컴활 2급")
        self.assertContains(response, "무료로 시작하기")
        self.assertContains(response, reverse("signup"))
        self.assertContains(response, reverse("login"))

    def test_landing_page_shows_learning_home_for_authenticated_user(self):
        user = User.objects.create_user(username="learner", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("landing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "학습 홈으로 이동")
        self.assertContains(response, reverse("mission_list"))

    def test_landing_post_stores_subject_in_session(self):
        subject = get_default_subject()

        response = self.client.post(
            reverse("landing"),
            {"subject_code": subject.code},
        )

        self.assertRedirects(response, reverse("mission_list"), fetch_redirect_response=False)
        self.assertEqual(
            self.client.session[CURRENT_SUBJECT_SESSION_KEY],
            subject.code,
        )

    def test_landing_page_shows_logistics_after_subject_seed(self):
        seed_platform_subjects()

        response = self.client.get(reverse("landing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "물류관리사")
        self.assertContains(response, LOGISTICS_SUBJECT_CODE)

    def test_mission_list_still_requires_login(self):
        response = self.client.get(reverse("mission_list"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('mission_list')}",
        )
