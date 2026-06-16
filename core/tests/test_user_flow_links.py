from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class UserFlowLinkTests(TestCase):
    def test_landing_has_primary_user_flow_links(self):
        response = self.client.get(reverse("landing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("signup"))
        self.assertContains(response, reverse("login"))
        self.assertContains(response, reverse("inquiry"))

    def test_login_page_links_to_signup(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "회원가입하기")
        self.assertContains(response, reverse("signup"))

    def test_inquiry_done_has_next_action_links_for_authenticated_user(self):
        user = User.objects.create_user(username="flow_user", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("inquiry_done"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("landing"))
        self.assertContains(response, reverse("premium_info"))
        self.assertContains(response, reverse("mission_list"))
