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
        self.assertContains(response, "원하는 자격증을 선택하여")
        self.assertContains(response, "과목 선택")
        self.assertContains(response, "물류관리사")
        self.assertNotContains(response, "컴활 2급")
        self.assertContains(response, "학습 시작")
        self.assertContains(response, reverse("signup"))
        self.assertContains(response, reverse("login"))

    def test_landing_page_hides_learning_navigation_for_authenticated_user(self):
        user = User.objects.create_user(username="learner", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("landing"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "학습 홈")
        self.assertNotContains(response, "문제 세트")
        self.assertNotContains(response, "오답노트")
        self.assertNotContains(response, "통계")
        self.assertContains(response, "로그아웃")

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

    def test_subject_select_url_stores_subject_in_session(self):
        subject = get_default_subject()

        response = self.client.post(reverse("select_subject", args=[subject.code]))

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
        self.assertContains(response, reverse("select_subject", args=[LOGISTICS_SUBJECT_CODE]))

    def test_new_active_certificate_is_listed_without_changing_logistics(self):
        from core.models import Subject
        Subject.objects.create(code="new-cert", name="새 자격증", is_active=True)

        response = self.client.get(reverse("landing"))

        self.assertContains(response, "물류관리사")
        self.assertContains(response, "새 자격증")

    def test_mission_list_still_requires_login(self):
        response = self.client.get(reverse("mission_list"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('mission_list')}",
        )
