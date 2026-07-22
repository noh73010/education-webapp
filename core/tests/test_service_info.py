from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class ServiceInfoPageTests(TestCase):
    def test_service_info_is_public_and_explains_learning_flow(self):
        response = self.client.get(reverse("service_info"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "혼자 공부하는 자격증")
        self.assertContains(response, "과목 선택")
        self.assertContains(response, "오답 복습")
        self.assertContains(response, "추천 문제")
        self.assertContains(response, "학습 통계")
        self.assertContains(response, "반복 학습")

    def test_service_info_does_not_hardcode_subject_names(self):
        response = self.client.get(reverse("service_info"))

        self.assertNotContains(response, "물류관리사")
        self.assertNotContains(response, "컴활 2급")

    def test_service_info_shows_actual_free_and_premium_ranges(self):
        response = self.client.get(reverse("service_info"))

        self.assertContains(response, "최근 5개")
        self.assertContains(response, "하루 1회", count=2)
        self.assertContains(response, "상세 약점 분석")

    def test_service_info_cta_returns_to_subject_selection(self):
        response = self.client.get(reverse("service_info"))

        self.assertContains(response, "과목 선택하기")
        self.assertContains(response, f'href="{reverse("landing")}"')

    def test_landing_service_link_opens_service_info(self):
        response = self.client.get(reverse("landing"))

        self.assertContains(response, f'href="{reverse("service_info")}"')

    def test_service_info_hides_learning_navigation_for_authenticated_user(self):
        user = User.objects.create_user(username="service_reader", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("service_info"))

        self.assertNotContains(response, reverse("mission_list"))
        self.assertNotContains(response, reverse("problem_set_list"))
        self.assertNotContains(response, reverse("wrong_notes"))
        self.assertContains(response, "로그아웃")
