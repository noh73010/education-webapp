from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import UserAccess
from core.services.access import has_full_learning_access, premium_gating_enabled


class AccessPolicyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("launch-user")
        self.access = UserAccess.objects.create(user=self.user, is_premium=False)

    @override_settings(PREMIUM_GATING_ENABLED=False)
    def test_launch_mode_grants_full_access_without_changing_stored_plan(self):
        self.assertFalse(premium_gating_enabled())
        self.assertTrue(has_full_learning_access(self.user))
        self.access.refresh_from_db()
        self.assertFalse(self.access.is_premium)

    @override_settings(PREMIUM_GATING_ENABLED=True)
    def test_future_gating_uses_stored_membership(self):
        self.assertFalse(has_full_learning_access(self.user))
        self.access.is_premium = True
        self.access.save(update_fields=["is_premium"])
        self.assertTrue(has_full_learning_access(self.user))

    @override_settings(PREMIUM_GATING_ENABLED=False)
    def test_usage_page_explains_current_free_policy(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("premium_info"))

        self.assertContains(response, "모든 기능 무료")
        self.assertContains(response, "향후 유료 플랜")
        self.assertNotContains(response, "프리미엄 신청하기")
