from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from core.adapters import SocialAccountAdapter
from core.forms import SocialSignupForm
from core.models import UserAccess, UserEvent


User = get_user_model()
SOCIAL_PROVIDER_SETTINGS = {
    "SOCIAL_LOGIN_PROVIDERS": ("google", "naver", "kakao"),
    "SOCIALACCOUNT_PROVIDERS": {
        provider: {
            "APP": {"client_id": "test", "secret": "test", "key": ""}
        }
        for provider in ("google", "naver", "kakao")
    },
}


class SocialLoginTests(TestCase):
    def pending_sociallogin(self, email=""):
        email_addresses = []
        if email:
            email_addresses.append(
                EmailAddress(email=email, verified=True, primary=True)
            )
        return SocialLogin(
            user=User(username="", email=email),
            account=SocialAccount(provider="naver", uid="pending-naver-user"),
            email_addresses=email_addresses,
            provider=SocialAccountAdapter().get_provider(
                RequestFactory().get("/"), "naver"
            ),
        )

    @override_settings(**SOCIAL_PROVIDER_SETTINGS)
    def test_login_page_has_all_social_login_posts(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        for provider in ("google", "naver", "kakao"):
            self.assertContains(response, reverse(f"{provider}_login"))
        self.assertContains(response, 'method="post"', count=4)

    @override_settings(**SOCIAL_PROVIDER_SETTINGS)
    def test_signup_page_has_all_social_signup_posts(self):
        response = self.client.get(reverse("signup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "간편 회원가입")
        for provider in ("google", "naver", "kakao"):
            self.assertContains(response, reverse(f"{provider}_login"))
        self.assertContains(response, 'method="post"', count=4)

    @override_settings(
        **SOCIAL_PROVIDER_SETTINGS,
        ALLOWED_HOSTS=["127.0.0.1"],
    )
    def test_naver_login_uses_local_request_origin_for_callback(self):
        response = self.client.post(
            reverse("naver_login"),
            HTTP_HOST="127.0.0.1:8888",
        )

        self.assertEqual(response.status_code, 302)
        authorization_url = urlparse(response["Location"])
        query = parse_qs(authorization_url.query)
        self.assertEqual(authorization_url.netloc, "nid.naver.com")
        self.assertEqual(
            query["redirect_uri"],
            ["http://127.0.0.1:8888/accounts/naver/login/callback/"],
        )

    @override_settings(
        **SOCIAL_PROVIDER_SETTINGS,
        ALLOWED_HOSTS=["comhal-study.onrender.com"],
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    )
    def test_naver_login_uses_https_callback_behind_render_proxy(self):
        response = self.client.post(
            reverse("naver_login"),
            HTTP_HOST="comhal-study.onrender.com",
            HTTP_X_FORWARDED_PROTO="https",
        )

        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlparse(response["Location"]).query)
        self.assertEqual(
            query["redirect_uri"],
            [
                "https://comhal-study.onrender.com/"
                "accounts/naver/login/callback/"
            ],
        )

    @override_settings(**SOCIAL_PROVIDER_SETTINGS)
    def test_duplicate_social_email_shows_connection_guidance_without_form(self):
        User.objects.create_user(
            username="existing-social-member",
            email="same@example.com",
        )
        session = self.client.session
        session["socialaccount_sociallogin"] = self.pending_sociallogin(
            "same@example.com"
        ).serialize()
        session.save()

        response = self.client.get(reverse("socialaccount_signup"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "socialaccount/signup.html")
        self.assertContains(response, "이미 사용 중인 회원 정보예요")
        self.assertContains(response, "계정 관리 → 로그인 방법")
        self.assertNotContains(response, 'name="username"')
        self.assertNotContains(response, 'name="email"')

    @override_settings(**SOCIAL_PROVIDER_SETTINGS)
    def test_social_signup_fallback_does_not_accept_manual_account_fields(self):
        sociallogin = self.pending_sociallogin()
        form = SocialSignupForm(
            data={"username": "manual", "email": "manual@example.com"},
            sociallogin=sociallogin,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("필요한 계정 정보를 받지 못했습니다", str(form.errors))

    @override_settings(**SOCIAL_PROVIDER_SETTINGS)
    def test_account_settings_offers_explicit_provider_connection(self):
        user = User.objects.create_user(username="connected-member")
        SocialAccount.objects.create(user=user, provider="google", uid="google-user")
        self.client.force_login(user)

        response = self.client.get(reverse("account_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "로그인 방법")
        self.assertContains(response, "Google")
        self.assertContains(response, "연결됨")
        self.assertContains(response, "네이버 연결하기")
        self.assertContains(response, "/accounts/naver/login/?process=connect")

    def test_connected_provider_returns_to_account_settings(self):
        redirect_url = SocialAccountAdapter().get_connect_redirect_url(
            RequestFactory().get("/accounts/naver/login/callback/"),
            SimpleNamespace(provider="naver"),
        )

        self.assertEqual(redirect_url, reverse("account_settings"))

    @override_settings(SOCIAL_LOGIN_PROVIDERS=())
    def test_login_page_works_without_social_credentials(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "social-login-section")
        self.assertContains(response, 'name="username"')

    @override_settings(SOCIAL_LOGIN_PROVIDERS=())
    def test_signup_page_works_without_social_credentials(self):
        response = self.client.get(reverse("signup"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "social-login-section")
        self.assertContains(response, 'name="username"')

    @patch("allauth.socialaccount.adapter.DefaultSocialAccountAdapter.save_user")
    def test_social_signup_creates_access_and_signup_event(self, save_user):
        user = User.objects.create_user(username="social-user")
        save_user.return_value = user
        sociallogin = SimpleNamespace(
            account=SimpleNamespace(provider="google"),
        )

        result = SocialAccountAdapter().save_user(
            RequestFactory().get("/accounts/google/login/callback/"),
            sociallogin,
        )

        self.assertEqual(result, user)
        self.assertTrue(UserAccess.objects.filter(user=user).exists())
        self.assertTrue(
            UserEvent.objects.filter(
                user=user,
                event_type="signup",
                metadata__source="google",
            ).exists()
        )
