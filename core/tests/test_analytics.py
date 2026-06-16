from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import UserEvent
from core.services.analytics import record_event


class AnalyticsTests(TestCase):
    def test_record_event_creates_minimal_event(self):
        user = User.objects.create_user(username="analytics_user", password="pass12345")

        event = record_event(
            user,
            "start_mission",
            page="mission_detail",
            metadata={"mission_id": 1, "skill": "COUNT"},
        )

        self.assertIsNotNone(event)
        self.assertEqual(UserEvent.objects.count(), 1)
        self.assertEqual(event.user, user)
        self.assertEqual(event.event_type, "start_mission")
        self.assertEqual(event.metadata["mission_id"], 1)

    def test_login_success_records_event(self):
        User.objects.create_user(username="login_user", password="pass12345")

        response = self.client.post(
            reverse("login"),
            {"username": "login_user", "password": "pass12345"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(UserEvent.objects.filter(event_type="login").exists())

    def test_signup_success_records_event(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "new_user",
                "password1": "StrongPass12345",
                "password2": "StrongPass12345",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(UserEvent.objects.filter(event_type="signup").exists())
