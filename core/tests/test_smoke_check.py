from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings


class SmokeCheckCommandTests(TestCase):
    @override_settings(DEBUG=True)
    def test_smoke_check_runs_without_failures_on_empty_test_db(self):
        out = StringIO()

        call_command("smoke_check", stdout=out)

        output = out.getvalue()
        self.assertIn("SMOKE CHECK START", output)
        self.assertIn("SMOKE CHECK PASSED", output)
        self.assertIn("URL reverse", output)
        self.assertIn("Template loading", output)
