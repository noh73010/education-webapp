from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import SimpleTestCase


class ResponsiveLayoutTests(SimpleTestCase):
    def test_base_loads_responsive_styles_after_existing_styles(self):
        html = render_to_string("core/base.html")
        self.assertLess(html.index("core/theory.css"), html.index("core/responsive.css"))
        self.assertNotIn("user-scalable=no", html)

    def test_stylesheet_is_available(self):
        self.assertIsNotNone(finders.find("core/responsive.css"))
        self.assertIsNotNone(finders.find("core/logistics.css"))
        self.assertIsNotNone(finders.find("core/design_refinements.css"))

    def test_refinements_keep_mobile_theory_art_compact(self):
        html = render_to_string("core/base.html")
        self.assertLess(html.index("core/logistics.css"), html.index("core/design_refinements.css"))
        with open(finders.find("core/design_refinements.css"), encoding="utf-8") as stylesheet:
            css = stylesheet.read()
        self.assertIn(".theory-lesson-art { width: min(36%, 120px)", css)
        self.assertIn(".learning-empty-state", css)

    def test_logistics_theme_is_scoped_and_loaded_after_responsive_rules(self):
        html = render_to_string("core/base.html")
        self.assertLess(html.index("core/responsive.css"), html.index("core/logistics.css"))
        with open(finders.find("core/logistics.css"), encoding="utf-8") as stylesheet:
            css = stylesheet.read()
        self.assertIn("body.theme-logistics .coach-summary-action", css)
        self.assertIn("body.theme-logistics .course-chapter-row::before", css)
        self.assertIn("body.theme-logistics .cbt-choice-option", css)

    def test_learning_coach_colors_layout_and_reduced_motion_are_defined(self):
        path = finders.find("core/style.css")
        with open(path, encoding="utf-8") as stylesheet:
            css = stylesheet.read()
        self.assertIn(".home-primary-grid", css)
        self.assertIn(".coach-summary-action", css)
        self.assertIn(".coach-summary-warning", css)
        self.assertIn(".coach-summary-success", css)
        self.assertIn("prefers-reduced-motion", css)
