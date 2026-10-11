from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Mission, Subject


AD_SETTINGS = {
    "ADSENSE_ENABLED": True,
    "ADSENSE_CLIENT_ID": "ca-pub-1234567890123456",
    "ADSENSE_LOGISTICS_HOME_SLOT": "1234567890",
    "ADSENSE_REALTOR_HOME_SLOT": "0987654321",
}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class HomeAdPlacementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("ad-placement-learner")
        cls.mission = Mission.objects.create(
            external_id="HOME_ADS_TEST_QUESTION",
            subject=Subject.objects.get(code="logistics"),
            course="보관하역론",
            chapter_code="WH02",
            chapter_name="하역론",
            title="광고 분리 테스트 문제",
            skill="WH02",
            prompt="광고가 없는 문제 화면인가요?",
            question_type="choice_one",
            correct_answer="1",
            answer_schema="1|예\n2|아니요",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_ads_txt_is_public_and_exact(self):
        self.client.logout()
        response = self.client.get(reverse("ads_txt"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.content,
            b"google.com, pub-7309766716223051, DIRECT, f08c47fec0942fa0\n",
        )

    def test_public_privacy_and_advertising_notice(self):
        self.client.logout()
        landing = self.client.get(reverse("landing"))
        self.assertContains(landing, reverse("privacy_info"))
        notice = self.client.get(reverse("privacy_info"))
        self.assertEqual(notice.status_code, 200)
        self.assertContains(notice, "Google AdSense")
        self.assertContains(notice, "쿠키")

    @override_settings(**AD_SETTINGS)
    def test_manual_unit_appears_once_at_bottom_of_each_home_only(self):
        logistics = self.client.get(reverse("mission_list"))
        self.assertEqual(logistics.status_code, 200)
        self.assertContains(logistics, 'data-ad-slot="1234567890"')
        self.assertNotContains(logistics, 'data-ad-slot="0987654321"')
        self.assertEqual(logistics.content.count(b"adsbygoogle.js"), 1)
        self.assertLess(
            logistics.content.index(b'id="search-section"'),
            logistics.content.index(b'class="home-ad"'),
        )

        question = self.client.get(reverse("mission_detail", args=[self.mission.pk]))
        self.assertEqual(question.status_code, 200)
        self.assertNotContains(question, "adsbygoogle.js")

        realtor = self.client.get(reverse("realtor_home"))
        self.assertEqual(realtor.status_code, 200)
        self.assertContains(realtor, 'data-ad-slot="0987654321"')
        self.assertNotContains(realtor, 'data-ad-slot="1234567890"')
        self.assertEqual(realtor.content.count(b"adsbygoogle.js"), 1)
        self.assertLess(
            realtor.content.index(b'class="realtor-more"'),
            realtor.content.index(b'class="home-ad"'),
        )

        for page_name in ("exam_start", "wrong_notes", "stats"):
            with self.subTest(page=page_name):
                response = self.client.get(reverse(page_name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "adsbygoogle.js")

        self.client.post(reverse("realtor_choose_course"), {"area_code": "RE01"})
        realtor_missions = self.client.get(reverse("mission_list"))
        self.assertEqual(realtor_missions.status_code, 200)
        self.assertNotContains(realtor_missions, "adsbygoogle.js")

    @override_settings(**{**AD_SETTINGS, "ADSENSE_ENABLED": False})
    def test_default_off_state_does_not_load_ads_or_empty_slot(self):
        for page_name in ("mission_list", "realtor_home"):
            with self.subTest(page=page_name):
                response = self.client.get(reverse(page_name))
                self.assertContains(response, 'name="google-adsense-account" content="ca-pub-7309766716223051"')
                self.assertNotContains(response, "adsbygoogle.js")
                self.assertNotContains(response, 'class="home-ad"')

    @override_settings(**{**AD_SETTINGS, "ADSENSE_CLIENT_ID": "invalid"})
    def test_malformed_account_configuration_fails_closed(self):
        response = self.client.get(reverse("mission_list"))
        self.assertNotContains(response, "adsbygoogle.js")
