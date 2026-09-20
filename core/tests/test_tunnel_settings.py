from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from myproject.settings import add_tunnel_host


class TunnelSettingsTests(SimpleTestCase):
    def test_empty_tunnel_host_preserves_existing_settings(self):
        hosts, origins = add_tunnel_host(
            ["localhost"], ["https://production.example"], True, ""
        )

        self.assertEqual(["localhost"], hosts)
        self.assertEqual(["https://production.example"], origins)

    def test_development_tunnel_adds_exact_host_and_https_origin(self):
        hosts, origins = add_tunnel_host(
            ["localhost"], [], True, "sample.trycloudflare.com"
        )

        self.assertEqual(["localhost", "sample.trycloudflare.com"], hosts)
        self.assertEqual(["https://sample.trycloudflare.com"], origins)

    def test_tunnel_host_is_ignored_in_production(self):
        hosts, origins = add_tunnel_host(
            ["production.example"],
            ["https://production.example"],
            False,
            "sample.trycloudflare.com",
        )

        self.assertEqual(["production.example"], hosts)
        self.assertEqual(["https://production.example"], origins)

    def test_rejects_url_port_path_and_wildcard(self):
        invalid_values = (
            "https://sample.trycloudflare.com",
            "sample.trycloudflare.com:443",
            "sample.trycloudflare.com/path",
            "*.trycloudflare.com",
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ImproperlyConfigured):
                    add_tunnel_host([], [], True, value)
