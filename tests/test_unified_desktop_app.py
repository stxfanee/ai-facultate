
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from desktop_app import launcher


class UnifiedDesktopAppTests(unittest.TestCase):
    def test_config_round_trip_and_invalid_values_fall_back(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            config = launcher.UnifiedConfig(
                mode="server",
                server_url="https://study.example.com/",
                project_root=folder,
                tunnel="cloudflare",
                auto_public_access=True,
                theme="light",
                width=1440,
                height=900,
            )
            config.save(path)
            loaded = launcher.UnifiedConfig.load(path)
            self.assertEqual(loaded.mode, "server")
            self.assertEqual(loaded.server_url, "https://study.example.com")
            self.assertEqual(loaded.tunnel, "cloudflare")
            self.assertTrue(loaded.auto_public_access)
            self.assertEqual(loaded.theme, "light")

            path.write_text('{"mode":"bad","tunnel":"unsafe","width":1}', encoding="utf-8")
            loaded = launcher.UnifiedConfig.load(path)
            self.assertEqual(loaded.mode, "")
            self.assertEqual(loaded.tunnel, "none")
            self.assertEqual(loaded.width, launcher.MIN_WIDTH)

    def test_first_launch_screen_asks_for_server_or_client_mode(self):
        html = launcher.first_launch_html()
        self.assertIn("Cum vrei s\u0103 folose\u0219ti aplica\u021bia?", html)
        self.assertIn("Server mode", html)
        self.assertIn("Client mode", html)
        self.assertIn("Dark mode", html)
        self.assertIn("Light mode", html)
        self.assertIn("Auto", html)

    def test_initial_html_remembers_previous_mode(self):
        self.assertIn("Client mode", launcher.initial_html(launcher.UnifiedConfig(mode="client")))
        self.assertIn("Pornesc serverul", launcher.initial_html(launcher.UnifiedConfig(mode="server")))

    @patch("desktop_app.launcher.test_server", return_value={"message": "ok", "warning": ""})
    def test_client_connect_saves_url_and_does_not_start_server(self, _test_server):
        api = launcher.UnifiedAppApi()
        api.bind_window(Mock())
        api.controller.start_all = Mock()
        with tempfile.TemporaryDirectory() as folder:
            with patch("desktop_app.launcher.config_file", return_value=Path(folder) / "settings.json"):
                result = api.connect_client("study.example.com")
        self.assertEqual(result["message"], "ok")
        self.assertEqual(api.config.mode, "client")
        self.assertEqual(api.config.server_url, "https://study.example.com")
        api._window.load_url.assert_called_once_with("https://study.example.com")
        api.controller.start_all.assert_not_called()

    def test_default_server_url_can_be_discovered_from_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / launcher.DEFAULT_SERVER_URL_FILENAME
            path.write_text("study.example.com\n", encoding="utf-8")
            with patch("desktop_app.launcher.default_server_url_candidates", return_value=[path]):
                self.assertEqual(launcher.discover_default_server_url(), "https://study.example.com")

    @patch("desktop_app.launcher.test_server", return_value={"message": "ok", "warning": ""})
    def test_client_mode_uses_default_server_url_without_manual_input(self, _test_server):
        api = launcher.UnifiedAppApi()
        api.bind_window(Mock())
        api.controller.start_all = Mock()
        with tempfile.TemporaryDirectory() as folder:
            with patch("desktop_app.launcher.config_file", return_value=Path(folder) / "settings.json"):
                with patch("desktop_app.launcher.discover_default_server_url", return_value="https://study.example.com"):
                    result = api.connect_client("")
        self.assertEqual(result["message"], "ok")
        self.assertEqual(api.config.server_url, "https://study.example.com")
        api._window.load_url.assert_called_once_with("https://study.example.com")
        api.controller.start_all.assert_not_called()


    def test_settings_and_recovery_expose_theme_and_cache_actions(self):
        config = launcher.UnifiedConfig(mode="server", theme="auto")
        settings = launcher.settings_html(config)
        self.assertIn("Dark mode", settings)
        self.assertIn("Light mode", settings)
        self.assertIn("Auto", settings)
        recovery = launcher.recovery_html(config, "frontend failed", ["log line"])
        self.assertIn("Reload app", recovery)
        self.assertIn("Clear WebView cache and reload", recovery)

    def test_clear_webview_cache_removes_known_cache_dirs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "profile"
            cache = root / "EBWebView" / "Default" / "Cache"
            cache.mkdir(parents=True)
            (cache / "old.bin").write_text("stale", encoding="utf-8")
            with patch("desktop_app.launcher.webview_storage_path", return_value=root):
                removed = launcher.clear_webview_cache_files()
        self.assertTrue(any("Cache" in item for item in removed))
        self.assertFalse(cache.exists())

    def test_streamlit_url_uses_cache_busting_query(self):
        self.assertEqual(launcher.streamlit_url(8501, cache_bust=False), "http://localhost:8501")
        self.assertIn("_copilot_reload=", launcher.streamlit_url(8501, cache_bust=True))

    def test_server_settings_are_derived_from_unified_config(self):
        config = launcher.UnifiedConfig(
            mode="server",
            project_root="F:/AI/ai-facultate-code",
            tunnel="tailscale",
            auto_public_access=True,
            auto_restart=False,
        )
        settings = config.server_settings()
        self.assertEqual(settings.project_root, "F:/AI/ai-facultate-code")
        self.assertEqual(settings.tunnel, "tailscale")
        self.assertTrue(settings.auto_public_access)
        self.assertFalse(settings.auto_restart)


if __name__ == "__main__":
    unittest.main()

