import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import deployment


class DeploymentConfigurationTests(unittest.TestCase):
    def test_public_url_requires_https_and_has_no_credentials(self):
        with patch.dict(
            os.environ,
            {"FACULTY_COPILOT_PUBLIC_URL": "http://study.example.com"},
            clear=False,
        ):
            self.assertIsNone(deployment.configured_public_url())
        with patch.dict(
            os.environ,
            {"FACULTY_COPILOT_PUBLIC_URL": "https://user:secret@study.example.com"},
            clear=False,
        ):
            self.assertIsNone(deployment.configured_public_url())
        with patch.dict(
            os.environ,
            {"FACULTY_COPILOT_PUBLIC_URL": "https://study.example.com/subpath"},
            clear=False,
        ):
            self.assertIsNone(deployment.configured_public_url())

    def test_public_mode_and_urls_are_explicit(self):
        environment = {
            "FACULTY_COPILOT_DEPLOYMENT_MODE": "Public Internet",
            "FACULTY_COPILOT_PUBLIC_URL": "https://study.example.com/",
        }
        with patch.dict(os.environ, environment, clear=False):
            urls = deployment.build_server_urls(
                8501,
                "192.168.1.50",
                "100.64.0.2",
                server_mode=True,
            )
        self.assertEqual(urls["deployment_mode"], "Public Internet")
        self.assertEqual(urls["public"], "https://study.example.com")
        self.assertEqual(urls["lan"], "http://192.168.1.50:8501")
        self.assertEqual(urls["tailscale"], "http://100.64.0.2:8501")
        self.assertTrue(urls["https"])

    def test_active_sessions_are_counted_without_storing_network_identity(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            tracker = deployment.ActiveSessionTracker(
                Path(temporary_directory) / "server_status.sqlite3"
            )
            tracker.heartbeat("browser-one", "default_user", "streamlit")
            tracker.heartbeat("browser-two", "default_user", "streamlit")
            status = tracker.diagnostics(ttl_seconds=60)
        self.assertEqual(status["connected_users"], 2)
        self.assertEqual(status["distinct_workspaces"], 1)

    def test_gpu_metrics_are_optional(self):
        completed = Mock(
            returncode=0,
            stdout="NVIDIA GeForce RTX 3070, 42, 2048, 8192, 61\n",
        )
        with patch("deployment.subprocess.run", return_value=completed):
            status = deployment.get_gpu_status()
        self.assertTrue(status["available"])
        self.assertEqual(status["utilization_percent"], 42)
        self.assertEqual(status["memory_total_mb"], 8192)

    def test_sliding_window_limiter_isolated_by_client_key(self):
        limiter = deployment.SlidingWindowRateLimiter(limit=2, window_seconds=60)
        self.assertTrue(limiter.allow("client-one"))
        self.assertTrue(limiter.allow("client-one"))
        self.assertFalse(limiter.allow("client-one"))
        self.assertTrue(limiter.allow("client-two"))


if __name__ == "__main__":
    unittest.main()
