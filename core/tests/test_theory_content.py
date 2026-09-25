from django.test import SimpleTestCase

from core.services.logistics_curriculum import LOGISTICS_CURRICULUM
from core.services.theory import load_theory_markdown, render_theory_markdown


class LogisticsTheoryContentTests(SimpleTestCase):
    def test_all_curriculum_chapters_have_matching_study_content(self):
        chapters = [chapter for course in LOGISTICS_CURRICULUM for chapter in course["chapters"]]
        self.assertEqual(len(chapters), 35)

        for code, title in chapters:
            with self.subTest(chapter=code):
                content = load_theory_markdown("logistics", code)
                self.assertIsNotNone(content)
                self.assertEqual(content.splitlines()[0], f"# {title}")
                self.assertIn("## 먼저 이해하기", content)
                self.assertIn("## 자주 틀리는 함정", content)
                self.assertIn("## 개념 확인", content)
                self.assertIn("정답:", content)
                self.assertGreaterEqual(len(content.strip()), 300)
                self.assertNotIn("준비 중", content)
                self.assertIn('<details class="theory-check-answer">', render_theory_markdown(content))

    def test_legal_chapters_link_to_current_curriculum(self):
        law_chapters = LOGISTICS_CURRICULUM[-1]["chapters"]
        self.assertEqual([code for code, _ in law_chapters], [f"LR{number:02d}" for number in range(1, 8)])
        for code, title in law_chapters:
            with self.subTest(chapter=code):
                content = load_theory_markdown("logistics", code)
                self.assertTrue(content.startswith(f"# {title}\n"))
