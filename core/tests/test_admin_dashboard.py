from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import UserEvent


class AdminDashboardTests(TestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("admin_dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_regular_user_is_redirected_to_mission_home(self):
        user = User.objects.create_user(username="regular", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("admin_dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("mission_list"))

    def test_staff_user_can_view_dashboard_summary(self):
        staff = User.objects.create_user(
            username="staff_user",
            password="pass12345",
            is_staff=True,
        )
        UserEvent.objects.create(
            user=staff,
            event_type="finish_mission",
            page="mission_detail",
            metadata={"mission_id": 1},
        )
        UserEvent.objects.create(
            user=staff,
            event_type="start_exam",
            page="exam_create",
            metadata={"exam_id": 1},
        )

        self.client.force_login(staff)
        response = self.client.get(reverse("admin_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "운영 대시보드")
        self.assertContains(response, "전체 회원 수")
        self.assertContains(response, "오늘 문제 풀이 완료 수")
        self.assertContains(response, "finish_mission")
        self.assertContains(response, "staff_user")
