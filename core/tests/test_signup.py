from django.contrib.auth import BACKEND_SESSION_KEY, get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import UserAccess, UserEvent


User = get_user_model()


class SignupTest(TestCase):
    def test_signup_page_returns_200(self):
        response = self.client.get(reverse("signup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "회원가입")
        self.assertContains(response, "아이디")
        self.assertContains(response, "비밀번호")
        self.assertContains(response, "로그인하기")
        self.assertContains(response, "signup-login-link")
        self.assertNotContains(response, "Password confirmation")

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

        self.assertEqual(User.objects.filter(username="newuser").count(), 1)
        self.assertEqual(UserAccess.objects.filter(user=user).count(), 1)
        self.assertFalse(access.is_premium)
        self.assertEqual(
            UserEvent.objects.filter(user=user, event_type="signup").count(),
            1,
        )
        self.assertEqual(
            self.client.session[BACKEND_SESSION_KEY],
            "django.contrib.auth.backends.ModelBackend",
        )

        missions_response = self.client.get(reverse("mission_list"))
        self.assertEqual(missions_response.status_code, 200)

    def test_invalid_signup_does_not_create_user(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "newuser",
                "password1": "StrongPass123!",
                "password2": "different-password",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "비밀번호")
        self.assertFalse(User.objects.filter(username="newuser").exists())

    def test_authenticated_user_is_redirected_from_signup(self):
        user = User.objects.create_user(
            username="existinguser",
            password="StrongPass123!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("signup"))

        self.assertRedirects(
            response,
            reverse("mission_list"),
            fetch_redirect_response=False,
        )

    def test_guest_result_return_url_survives_signup(self):
        next_url = reverse('guest_practice')
        login = self.client.get(reverse('login'), {'next': next_url})
        self.assertContains(login, reverse('signup') + '?next=')
        page = self.client.get(reverse('signup'), {'next': next_url})
        self.assertEqual(page.context['next'], next_url)
        response = self.client.post(reverse('signup'), {'username': 'guest-convert',
            'password1': 'StrongPass123!', 'password2': 'StrongPass123!', 'next': next_url})
        self.assertRedirects(response, next_url, fetch_redirect_response=False)

    def test_signup_rejects_external_return_url(self):
        for target in ('https://example.com/', '//example.com/', '/\\example.com/'):
            with self.subTest(target=target):
                page = self.client.get(reverse('signup'), {'next': target})
                self.assertEqual(page.context['next'], '')
        response = self.client.post(reverse('signup'), {'username': 'safe-convert',
            'password1': 'StrongPass123!', 'password2': 'StrongPass123!', 'next': '//example.com/'})
        self.assertRedirects(response, reverse('mission_list'), fetch_redirect_response=False)

    def test_signup_validation_error_keeps_internal_return_url(self):
        next_url = reverse('guest_practice')
        response = self.client.post(reverse('signup'), {'username': 'incomplete',
            'password1': 'StrongPass123!', 'password2': 'mismatch', 'next': next_url})
        self.assertEqual(response.context['next'], next_url)
        self.assertContains(response, 'name="next"')
