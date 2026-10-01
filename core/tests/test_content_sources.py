from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings
from django.urls import reverse

from core.services.content_sources import published_logistics_sources


class ContentSourcesTests(TestCase):
    def test_only_existing_sittings_from_verified_rounds_are_listed(self):
        with TemporaryDirectory() as temporary_dir:
            source_dir = Path(temporary_dir) / "generated" / "logistics"
            source_dir.mkdir(parents=True)
            for name in (
                "logistics_25-1.csv",
                "logistics_26-1.csv",
                "logistics_26-2.csv",
                "logistics_30-1.csv",
            ):
                (source_dir / name).touch()

            with override_settings(BASE_DIR=Path(temporary_dir)):
                sources = published_logistics_sources()
                response = self.client.get(reverse("content_sources"))

        self.assertEqual([item["round_number"] for item in sources], [25, 26])
        self.assertEqual([item["label"] for item in sources[0]["sittings"]], ["1교시"])
        self.assertEqual(
            [item["label"] for item in sources[1]["sittings"]],
            ["1교시", "2교시"],
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2021년 제25회")
        self.assertContains(response, "2022년 제26회")
        self.assertNotContains(response, "제30회")
        self.assertContains(response, "artlSeq=5208820&amp;boardId=Q004")
        self.assertContains(response, "공공누리 제1유형")
        self.assertContains(response, "공식 서비스가 아닙니다")

    def test_public_page_has_empty_state_without_published_sources(self):
        with TemporaryDirectory() as temporary_dir:
            with override_settings(BASE_DIR=Path(temporary_dir)):
                response = self.client.get(reverse("content_sources"))

        self.assertContains(response, "현재 공개할 물류관리사 기출문제 출처가 없습니다.")

    def test_landing_and_service_info_footers_link_to_sources(self):
        for page_name in ("landing", "service_info"):
            with self.subTest(page=page_name):
                response = self.client.get(reverse(page_name))
                self.assertContains(response, f'href="{reverse("content_sources")}"')
