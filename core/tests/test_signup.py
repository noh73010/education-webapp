from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import UserAccess


User = get_user_model()


class SignupTest(TestCase):
    def test_signup_page_returns_200(self):
        response = self.client.get(reverse("signup"))

        self.assertEqual(response.status_code, 200)

    def test_signup_creates_user_access_and_logs_in(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "newuser",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertRedirects(
            response,
            reverse("mission_list"),
            fetch_redirect_response=False,
        )

        user = User.objects.get(username="newuser")
        access = UserAccess.objects.get(user=user)

        self.assertFalse(access.is_premium)

        missions_response = self.client.get(reverse("mission_list"))
        self.assertEqual(missions_response.status_code, 200)
