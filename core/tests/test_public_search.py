from xml.etree import ElementTree

from django.test import TestCase, override_settings
from django.urls import reverse
from core.models import UserEvent


class PublicSearchTests(TestCase):
    def test_public_quiz_and_practice_arrivals_are_separate(self):
        url = reverse("land_zones")
        campaign = "realtor-quiz-zones"
        self.client.head(url)
        self.assertFalse(UserEvent.objects.filter(event_type="blog_guest_quiz_arrival").exists())
        for _ in range(2):
            self.assertContains(self.client.get(url), f"?blog={campaign}")
        events = UserEvent.objects.filter(metadata__course=campaign)
        self.assertEqual(events.filter(event_type="blog_guest_quiz_arrival").count(), 1)

        self.assertEqual(events.filter(event_type="blog_guest_arrival").count(), 0)
        self.client.get(reverse("guest_practice"), {"blog": campaign})
        self.assertEqual(events.filter(event_type="blog_guest_arrival").count(), 1)
        self.assertContains(self.client.get(url, {"source": "naver"}), "?blog=realtor-land-zones")
        self.assertEqual(UserEvent.objects.filter(event_type="blog_guest_quiz_arrival", metadata__course="realtor-land-zones").count(), 1)
        self.assertEqual(events.filter(event_type="blog_guest_quiz_arrival").count(), 1)

    def test_law_quizzes_explain_practice_scope(self):
        for view, scope in (
            ("land_zones", "도시·군관리계획을 함께 다루는 단원"),
            ("land_readjustment", "도시개발사업의 시행 방식과 절차"),
        ):
            with self.subTest(view=view):
                response = self.client.get(reverse(view))
                self.assertContains(response, scope)
                self.assertContains(response, "무료 5문제 풀기")
                self.assertContains(response, "답을 제출하면 바로 정답과 해설")

    @override_settings(ALLOWED_HOSTS=["example.com", "testserver"])
    def test_public_pages_have_search_metadata(self):
        for name in ("landing", "service_info", "content_sources", "privacy_info", "realtor_study_kit"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name), HTTP_HOST="example.com")
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<meta name="robots" content="index, follow">')
                self.assertContains(response, '<meta name="description" content="')
                self.assertContains(
                    response,
                    f'<link rel="canonical" href="http://example.com{reverse(name)}">',
                )

    def test_login_is_not_marked_for_indexing(self):
        response = self.client.get(reverse("login"))

        self.assertContains(response, '<meta name="robots" content="noindex, nofollow">')
        self.assertNotContains(response, '<link rel="canonical"')

    @override_settings(ALLOWED_HOSTS=["example.com", "testserver"])
    def test_robots_points_to_sitemap(self):
        response = self.client.get(reverse("robots_txt"), HTTP_HOST="example.com")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        self.assertIn("Sitemap: http://example.com/sitemap.xml", response.content.decode())

    @override_settings(ALLOWED_HOSTS=["example.com", "testserver"])
    def test_sitemap_lists_only_public_pages(self):
        response = self.client.get(reverse("sitemap_xml"), HTTP_HOST="example.com")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/xml"))
        root = ElementTree.fromstring(response.content)
        namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        locations = {
            node.text for node in root.findall(f"{namespace}url/{namespace}loc")
        }
        self.assertEqual(
            locations,
            {f"http://example.com{reverse(name)}" for name in (
                "landing", "service_info", "study_examples", "reorder_point", "building_ratios", "land_zones", "land_readjustment",
                "content_sources", "privacy_info", "realtor_study_kit"
            )},
        )

    def test_realtor_quiz_links_guest_practice_without_login(self):
        response = self.client.get(reverse("realtor_study_kit"))
        self.assertContains(response, "<summary>정답과 풀이</summary>", count=3)
        self.assertContains(response, '?lesson=realtor-intro')
        self.assertContains(response, '?lesson=building-ratios')
        self.assertContains(self.client.get(reverse("landing")), reverse("realtor_study_kit"))
