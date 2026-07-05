import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from server_launcher import launcher


class ServerLauncherTests(unittest.TestCase):
    def test_settings_round_trip_and_invalid_tunnel_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            settings = launcher.LauncherSettings(
                project_root=folder,
                api_port=8100,
                streamlit_port=8600,
                tunnel="cloudflare",
                auto_start=True,
            )
            settings.save(path)
            self.assertEqual(launcher.LauncherSettings.load(path), settings)
            path.write_text(
                json.dumps({"project_root": folder, "tunnel": "unsafe"}),
                encoding="utf-8",
            )
            self.assertEqual(launcher.LauncherSettings.load(path).tunnel, "none")

    def test_cloudflare_public_url_is_extracted(self):
        log = "INF Your quick Tunnel has been created! https://quiet-tree.trycloudflare.com"
        self.assertEqual(
            launcher.extract_cloudflare_url(log),
            "https://quiet-tree.trycloudflare.com",
        )
        self.assertEqual(launcher.extract_cloudflare_url("no URL"), "")

    def test_environment_keeps_server_safety_limits(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = launcher.LauncherSettings(
                project_root=folder, tunnel="cloudflare"
            )
            controller = launcher.ServerController(settings)
            env = controller.environment()
        self.assertEqual(env["FACULTY_COPILOT_DEPLOYMENT_MODE"], "Public Internet")
        self.assertEqual(env["FACULTY_COPILOT_MAX_UPLOAD_MB"], "100")
        self.assertEqual(env["FACULTY_COPILOT_IP_RATE_LIMIT"], "60")
        self.assertEqual(env["FACULTY_COPILOT_AUTH_ENABLED"], "0")

    def test_spawn_does_not_duplicate_live_owned_process(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = launcher.ServerController(
                launcher.LauncherSettings(project_root=folder)
            )
            process = Mock()
            process.poll.return_value = None
            controller.processes["FastAPI"] = process
            with patch("server_launcher.launcher.subprocess.Popen") as popen:
                self.assertTrue(
                    controller._spawn("FastAPI", ["python", "-V"], {})
                )
            popen.assert_not_called()

    @patch("server_launcher.launcher.shutil.which", return_value=None)
    def test_missing_cloudflared_is_reported_as_unavailable(self, _which):
        with patch.object(Path, "exists", return_value=False):
            self.assertIsNone(launcher.find_cloudflared())


if __name__ == "__main__":
    unittest.main()
