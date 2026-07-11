
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
        with patch("desktop_app.launcher.current_runtime_public_url", return_value=""):
            self.assertIn("Client mode", launcher.initial_html(launcher.UnifiedConfig(mode="client")))
        self.assertIn("Pornesc serverul", launcher.initial_html(launcher.UnifiedConfig(mode="server")))

    def test_client_startup_url_opens_directly_without_setup_screen(self):
        config = launcher.UnifiedConfig(app_mode="client", default_server_url="https://study.example.com")
        with patch("desktop_app.launcher.current_runtime_public_url", return_value=""):
            self.assertEqual(launcher.initial_window_url(config), "https://study.example.com")
            self.assertIn("Conectez clientul", launcher.initial_html(config))

    @patch("desktop_app.launcher.test_server")
    def test_on_start_client_loads_no_local_services_and_does_not_block_on_full_health_check(self, test_server_mock):
        api = launcher.UnifiedAppApi()
        api.bind_window(Mock())
        api.config = launcher.UnifiedConfig(app_mode="client", default_server_url="https://study.example.com")
        api.controller.start_all = Mock()
        with patch("desktop_app.launcher.current_runtime_public_url", return_value=""):
            with patch.object(api, "_start_client_health_check") as health_mock:
                launcher.on_start(api)
        api.controller.start_all.assert_not_called()
        test_server_mock.assert_not_called()
        health_mock.assert_called_once_with("https://study.example.com")

    def test_client_connect_saves_url_and_does_not_start_server(self):
        api = launcher.UnifiedAppApi()
        api.bind_window(Mock())
        api.controller.start_all = Mock()
        with tempfile.TemporaryDirectory() as folder:
            with patch("desktop_app.launcher.config_file", return_value=Path(folder) / "settings.json"):
                with patch.object(api, "_start_client_health_check") as health_mock:
                    result = api.connect_client("study.example.com")
        self.assertEqual(result["message"], "Conectez la server...")
        self.assertEqual(api.config.mode, "client")
        self.assertEqual(api.config.server_url, "https://study.example.com")
        self.assertEqual(api.config.default_server_url, "https://study.example.com")
        api._window.load_url.assert_called_once_with("https://study.example.com")
        health_mock.assert_called_once_with("https://study.example.com")
        api.controller.start_all.assert_not_called()

    def test_default_server_url_can_be_discovered_from_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / launcher.DEFAULT_SERVER_URL_FILENAME
            path.write_text("study.example.com\n", encoding="utf-8")
            with patch("desktop_app.launcher.default_server_url_candidates", return_value=[path]):
                self.assertEqual(launcher.discover_default_server_url(), "https://study.example.com")

    def test_runtime_public_url_overrides_stale_client_url(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runtime = root / "storage" / "runtime"
            runtime.mkdir(parents=True)
            (runtime / "public_url.txt").write_text("https://new-link.trycloudflare.com", encoding="utf-8")
            config = launcher.UnifiedConfig(
                app_mode="client",
                default_server_url="https://old-link.trycloudflare.com",
                project_root=str(root),
            )
            self.assertEqual(
                launcher.client_url_or_default(config),
                "https://new-link.trycloudflare.com",
            )

    def test_public_url_sync_updates_saved_client_url(self):
        api = launcher.UnifiedAppApi()
        api.config = launcher.UnifiedConfig(
            mode="server",
            app_mode="server",
            server_url="https://old-link.trycloudflare.com",
            default_server_url="https://old-link.trycloudflare.com",
        )
        with tempfile.TemporaryDirectory() as folder:
            with patch("desktop_app.launcher.config_file", return_value=Path(folder) / "settings.json"):
                api.snapshot_dict = Mock(return_value={"public_url": "https://new-link.trycloudflare.com"})
                self.assertEqual(
                    api._sync_public_url_to_client_config(),
                    "https://new-link.trycloudflare.com",
                )
        self.assertEqual(api.config.server_url, "https://new-link.trycloudflare.com")
        self.assertEqual(api.config.default_server_url, "https://new-link.trycloudflare.com")

    def test_local_server_reclaims_stale_temporary_cloudflare_client_url(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app.py").write_text("# app", encoding="utf-8")
            (root / "server_launcher").mkdir()
            config = launcher.UnifiedConfig(
                app_mode="client",
                mode="client",
                default_server_url="https://old-link.trycloudflare.com",
                project_root=str(root),
            )
            self.assertEqual(launcher.initial_window_url(config), "")
            html = launcher.initial_html(config)
            self.assertIn("Pornesc serverul", html)
            self.assertEqual(config.app_mode, "server")
            self.assertEqual(config.tunnel, "cloudflare")
            self.assertTrue(config.auto_public_access)

    def test_on_start_reclaims_stale_temporary_cloudflare_url_on_server_host(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app.py").write_text("# app", encoding="utf-8")
            (root / "server_launcher").mkdir()
            api = launcher.UnifiedAppApi()
            api.config = launcher.UnifiedConfig(
                app_mode="client",
                mode="client",
                default_server_url="https://old-link.trycloudflare.com",
                project_root=str(root),
            )
            api.start_server = Mock()
            with patch("desktop_app.launcher.config_file", return_value=root / "settings.json"):
                launcher.on_start(api)
            api.start_server.assert_called_once_with(True)
            self.assertEqual(api.config.app_mode, "server")
            self.assertEqual(api.config.tunnel, "cloudflare")
            self.assertTrue(api.config.auto_public_access)

    def test_client_mode_uses_default_server_url_without_manual_input(self):
        api = launcher.UnifiedAppApi()
        api.bind_window(Mock())
        api.config = launcher.UnifiedConfig(app_mode="client")
        api.controller.start_all = Mock()
        with tempfile.TemporaryDirectory() as folder:
            with patch("desktop_app.launcher.config_file", return_value=Path(folder) / "settings.json"):
                with patch("desktop_app.launcher.discover_default_server_url", return_value="https://study.example.com"):
                    with patch("desktop_app.launcher.current_runtime_public_url", return_value=""):
                        with patch.object(api, "_start_client_health_check") as health_mock:
                            result = api.connect_client("")
        self.assertEqual(result["message"], "Conectez la server...")
        self.assertEqual(api.config.server_url, "https://study.example.com")
        api._window.load_url.assert_called_once_with("https://study.example.com")
        health_mock.assert_called_once_with("https://study.example.com")
        api.controller.start_all.assert_not_called()


    def test_settings_and_recovery_expose_theme_and_cache_actions(self):
        config = launcher.UnifiedConfig(mode="server", theme="auto")
        settings = launcher.settings_html(config)
        self.assertIn("Dark mode", settings)
        self.assertIn("Light mode", settings)
        self.assertIn("Auto", settings)
        self.assertIn("Developer Mode", settings)
        self.assertNotIn("Server URL", settings)
        recovery = launcher.recovery_html(config, "frontend failed", ["log line"])
        self.assertIn("Reload app", recovery)
        self.assertIn("Clear WebView cache and reload", recovery)

    def test_developer_mode_exposes_advanced_server_configuration(self):
        config = launcher.UnifiedConfig(mode="server", developer_mode=True, server_url="https://study.example.com")
        settings = launcher.settings_html(config)
        self.assertIn("Advanced", settings)
        self.assertIn("Server URL", settings)
        self.assertIn("Public tunnel", settings)

    def test_offline_client_screen_hides_raw_errors(self):
        html = launcher.client_unavailable_html(launcher.UnifiedConfig(mode="client"))
        self.assertIn("Serverul nu este disponibil momentan.", html)
        self.assertIn("Retry", html)
        self.assertIn("Open Settings", html)

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

