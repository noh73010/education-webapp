from xml.etree import ElementTree

from django.test import TestCase, override_settings
from django.urls import reverse


class PublicSearchTests(TestCase):
    @override_settings(ALLOWED_HOSTS=["example.com", "testserver"])
    def test_public_pages_have_search_metadata(self):
        for name in ("landing", "service_info", "content_sources"):
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
                "landing", "service_info", "content_sources"
            )},
        )
