from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class LandingPageTests(TestCase):
    def test_landing_page_is_public(self):
        response = self.client.get(reverse("landing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "컴활 2급 실전형 학습 시스템")
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

    def test_mission_list_still_requires_login(self):
        response = self.client.get(reverse("mission_list"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('mission_list')}",
        )
