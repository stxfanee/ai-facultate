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
                auto_public_access=True,
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

    def test_named_cloudflare_config_is_parsed(self):
        reference, url = launcher.parse_cloudflare_named_config(
            """
            tunnel: faculty-tunnel
            ingress:
              - hostname: study.example.com
                service: http://localhost:8501
            """
        )
        self.assertEqual(reference, "faculty-tunnel")
        self.assertEqual(url, "https://study.example.com")

    def test_named_cloudflare_tunnel_is_preferred_when_configured(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder) / "home"
            config_dir = home / ".cloudflared"
            config_dir.mkdir(parents=True)
            (config_dir / "config.yml").write_text(
                "tunnel: faculty-tunnel\n"
                "ingress:\n"
                "  - hostname: study.example.com\n"
                "    service: http://localhost:8501\n",
                encoding="utf-8",
            )
            controller = launcher.ServerController(
                launcher.LauncherSettings(project_root=folder)
            )
            tunnel_list = json.dumps(
                [{"id": "abc-123", "name": "faculty-tunnel"}]
            )
            with patch.object(
                controller, "_run", return_value=(0, tunnel_list)
            ), patch("server_launcher.launcher.Path.home", return_value=home):
                named = controller._cloudflare_named_tunnel("cloudflared.exe")
        self.assertIsNotNone(named)
        command, url, name = named
        self.assertIn("faculty-tunnel", command)
        self.assertEqual(url, "https://study.example.com")
        self.assertEqual(name, "faculty-tunnel")

    def test_existing_tailscale_funnel_is_detected_without_reconfigure(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = launcher.ServerController(
                launcher.LauncherSettings(
                    project_root=folder, tunnel="tailscale"
                )
            )
            with patch(
                "server_launcher.launcher.find_tailscale",
                return_value="tailscale.exe",
            ), patch.object(
                controller,
                "_tailscale_identity",
                return_value=(True, "pc.tailnet.ts.net", ""),
            ), patch.object(
                controller,
                "_tailscale_funnel_status",
                return_value=(True, "https://pc.tailnet.ts.net"),
            ), patch.object(controller, "_run") as run:
                controller._start_tailscale()
            run.assert_not_called()
            self.assertEqual(controller.active_tunnel, "tailscale")
            self.assertEqual(
                controller.public_url, "https://pc.tailnet.ts.net"
            )

    def test_tailscale_json_status_detects_config_without_embedded_url(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = launcher.ServerController(
                launcher.LauncherSettings(project_root=folder)
            )
            with patch(
                "server_launcher.launcher.find_tailscale",
                return_value="tailscale.exe",
            ), patch.object(
                controller,
                "_run",
                return_value=(
                    0,
                    json.dumps(
                        {"Web": {"pc.tailnet.ts.net:443": {"Handlers": {}}}}
                    ),
                ),
            ):
                configured, url = controller._tailscale_funnel_status()
        self.assertTrue(configured)
        self.assertEqual(url, "")

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
