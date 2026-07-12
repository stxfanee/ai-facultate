import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.client import launcher


class DesktopClientTests(unittest.TestCase):
    def test_normalize_server_url_prefers_https_for_public_hosts(self):
        self.assertEqual(
            launcher.normalize_server_url("faculty.example.com/"),
            "https://faculty.example.com",
        )
        self.assertEqual(
            launcher.normalize_server_url("localhost:8501/"),
            "http://localhost:8501",
        )
        self.assertEqual(
            launcher.normalize_server_url("192.168.1.50:8501"),
            "http://192.168.1.50:8501",
        )

    def test_plain_http_warning_only_for_public_urls(self):
        self.assertEqual(launcher.security_warning_for_url("http://localhost:8501"), "")
        self.assertEqual(launcher.security_warning_for_url("http://192.168.1.50:8501"), "")
        self.assertIn("HTTPS", launcher.security_warning_for_url("http://example.com"))
        self.assertEqual(launcher.security_warning_for_url("https://example.com"), "")

    def test_health_urls_support_streamlit_and_api_fallback(self):
        self.assertEqual(
            launcher.streamlit_health_url("https://study.example.com"),
            "https://study.example.com/_stcore/health",
        )
        self.assertEqual(
            launcher.api_health_url("http://192.168.1.50:8501"),
            "http://192.168.1.50:8000/health",
        )

    def test_config_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "client_config.json"
            config = launcher.ClientConfig(
                server_url="https://study.example.com/",
                width=1400,
                height=900,
                maximized=True,
            )
            config.save(path)
            loaded = launcher.ClientConfig.load(path)
        self.assertEqual(loaded.server_url, "https://study.example.com")
        self.assertEqual(loaded.width, 1400)
        self.assertEqual(loaded.height, 900)
        self.assertTrue(loaded.maximized)

    def test_test_server_prefers_streamlit_health(self):
        calls = []

        def fake_read(url, timeout=7):
            calls.append(url)
            return 200, "ok"

        with patch("apps.client.launcher.read_url_text", side_effect=fake_read):
            result = launcher.test_server("https://study.example.com")
        self.assertEqual(result["kind"], "streamlit")
        self.assertEqual(calls, ["https://study.example.com/_stcore/health"])

    def test_test_server_falls_back_to_api_health(self):
        def fake_read(url, timeout=7):
            if url.endswith("/_stcore/health"):
                return 404, "missing"
            return 200, json.dumps({"api": True})

        with patch("apps.client.launcher.read_url_text", side_effect=fake_read):
            result = launcher.test_server("http://192.168.1.50:8501")
        self.assertEqual(result["kind"], "api")


if __name__ == "__main__":
    unittest.main()


