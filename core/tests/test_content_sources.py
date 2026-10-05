from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings
from django.urls import reverse

from core.services.content_sources import logistics_source_notices, realtor_source_notices


class ContentSourcesTests(TestCase):
    def test_realtor_rounds_and_sittings_link_to_qnet_sources(self):
        sources = realtor_source_notices()
        self.assertEqual([item["round_number"] for item in sources], [35, 36])
        for source in sources:
            self.assertEqual(
                [item["label"] for item in source["sittings"]],
                ["1차", "2차 1교시", "2차 2교시"],
            )
        response = self.client.get(reverse("content_sources"))
        self.assertContains(response, "제35회 공인중개사")
        self.assertContains(response, "제36회 공인중개사")
        self.assertContains(response, "artlSeq=5214724&amp;boardId=Q004")
        self.assertContains(response, "artlSeq=5247125&amp;boardId=Q004")

    def test_verified_sources_list_both_sittings_independent_of_csv_files(self):
        with TemporaryDirectory() as temporary_dir:
            with override_settings(BASE_DIR=Path(temporary_dir)):
                sources = logistics_source_notices()
                response = self.client.get(reverse("content_sources"))

        self.assertEqual([item["round_number"] for item in sources], [25, 26, 27, 28, 29])
        for source in sources:
            self.assertEqual(
                [item["label"] for item in source["sittings"]],
                ["1교시", "2교시"],
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2021년 제25회")
        self.assertContains(response, "2022년 제26회")
        self.assertContains(response, "보관하역론 · 물류관련법규", count=5)
        self.assertContains(response, "artlSeq=5208820&amp;boardId=Q004")
        self.assertContains(response, "공공누리 제1유형")
        self.assertContains(response, "공식 서비스가 아닙니다")
        self.assertContains(response, "현재 출제 중임을 뜻하지는 않습니다")

    def test_navigation_and_public_footers_link_to_sources(self):
        for page_name in ("landing", "service_info"):
            with self.subTest(page=page_name):
                response = self.client.get(reverse(page_name))
                self.assertContains(response, f'href="{reverse("content_sources")}"')

        response = self.client.get(reverse("content_sources"))
        self.assertContains(response, 'class="sub-link">콘텐츠 출처</a>')
