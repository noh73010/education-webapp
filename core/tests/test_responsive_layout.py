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

    def test_learning_coach_colors_layout_and_reduced_motion_are_defined(self):
        path = finders.find("core/style.css")
        with open(path, encoding="utf-8") as stylesheet:
            css = stylesheet.read()
        self.assertIn(".home-primary-grid", css)
        self.assertIn(".coach-summary-action", css)
        self.assertIn(".coach-summary-warning", css)
        self.assertIn(".coach-summary-success", css)
        self.assertIn("prefers-reduced-motion", css)
