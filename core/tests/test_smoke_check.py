from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from core.models import Mission
from core.services.subjects import get_default_subject


class SmokeCheckCommandTests(TestCase):
    @override_settings(DEBUG=True)
    def test_smoke_check_runs_without_failures_on_empty_test_db(self):
        subject = get_default_subject()
        Mission.objects.create(
            external_id="SMOKE_TEST_MISSION",
            subject=subject,
            title="Smoke test mission",
            skill="COUNT",
            level=1,
            prompt="[CONTEXT]\nTest\n[DATA]\nA\n[QUESTION]\nTest question",
            correct_answer="1",
            explanation="Test explanation",
            quality_level="practical",
            is_quality_checked=True,
            is_usable_for_set=True,
        )
        out = StringIO()

        call_command("smoke_check", stdout=out)

        output = out.getvalue()
        self.assertIn("SMOKE CHECK START", output)
        self.assertIn("SMOKE CHECK PASSED", output)
        self.assertIn("URL reverse", output)
        self.assertIn("Template loading", output)
