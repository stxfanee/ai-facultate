import unittest
from unittest.mock import patch

from apps.web import app


INSTALLED = ["qwen3:8b", "qwen3:14b", "gemma3:12b"]


class ModelRoutingTests(unittest.TestCase):
    @patch("apps.web.app.get_preference", return_value=None)
    def test_profiles_prefer_installed_suggested_models(self, _preference):
        profiles = app.get_model_profiles(INSTALLED)
        self.assertEqual(profiles["rag"], "qwen3:8b")
        self.assertEqual(profiles["general"], "gemma3:12b")
        self.assertEqual(profiles["reasoning"], "qwen3:14b")
        self.assertEqual(profiles["fast"], "qwen3:8b")

    @patch("apps.web.app.get_preference", return_value=None)
    def test_speed_and_answer_modes_override_normal_route(self, _preference):
        fast = app.select_model_for_mode(
            "Explică efectul tunel",
            "Fast",
            "Profesor",
            "Documents only",
            "rag",
            INSTALLED,
        )
        professor = app.select_model_for_mode(
            "Explică efectul tunel",
            "Balanced",
            "Profesor",
            "Documents only",
            "rag",
            INSTALLED,
        )
        general = app.select_model_for_mode(
            "Ce este un Volvo V90 CC?",
            "Balanced",
            "Auto",
            "General knowledge only",
            "general",
            INSTALLED,
        )
        self.assertEqual(fast.model, "qwen3:8b")
        self.assertEqual(professor.model, "qwen3:14b")
        # Auto keeps ordinary chat on the configured 8B performance profile.
        self.assertEqual(general.model, "qwen3:8b")


    @patch("apps.web.app.get_preference", return_value=None)
    def test_model_selection_options_prioritize_auto_and_qwen_models(self, _preference):
        options = app.model_selection_options(["gemma3:12b", "qwen3:14b", "qwen3:8b"])
        self.assertEqual(options[0], app.MODEL_SELECTION_AUTO)
        self.assertEqual(options[1:3], ["qwen3:8b", "qwen3:14b"])
        self.assertIn("gemma3:12b", options)

    @patch("apps.web.app.get_preference", return_value=None)
    @patch("apps.web.app.performance_model_status")
    def test_manual_model_override_forces_model_over_auto_routing(self, performance, _preference):
        performance.return_value = {
            "Fast": {"resolved": "qwen3:8b", "missing": False, "may_spill": False},
            "Balanced": {"resolved": "qwen3:8b", "missing": False, "may_spill": False},
            "Accurate": {"resolved": "qwen3:14b", "missing": False, "may_spill": False},
        }
        with app.model_override_context("qwen3:8b"), app.model_mode_context("Auto"):
            route = app.select_model_for_mode(
                "Analizeaza profund si compara toate cursurile.",
                "Balanced",
                "Analiz?",
                "Documents only",
                "synthesis",
                INSTALLED,
            )
        self.assertEqual(route.model, "qwen3:8b")
        self.assertEqual(route.model_selection_mode, "Manual")
        self.assertEqual(route.model_mode, "Manual")
        self.assertIn("manual", app.model_route_debug(route)["selected_model_source"])

    @patch("apps.web.app.get_preference", return_value=None)
    @patch("apps.web.app.model_profile_status")
    @patch("apps.web.app.performance_model_status")
    def test_auto_complex_questions_use_configured_reasoning_model(
        self, performance, model_profiles, _preference
    ):
        performance.return_value = {
            "Fast": {"resolved": "qwen3:8b", "missing": False, "may_spill": False},
            "Balanced": {"resolved": "qwen3:8b", "missing": False, "may_spill": False},
            "Accurate": {"resolved": "qwen3:14b", "missing": False, "may_spill": False},
        }
        model_profiles.return_value = {
            "reasoning": {"resolved": "gemma3:12b", "configured": "gemma3:12b", "missing": False}
        }
        with app.model_mode_context("Auto"):
            route = app.select_model_for_mode(
                "Care curs este mai greu si de ce?",
                "Balanced",
                "Auto",
                "Documents only",
                "synthesis",
                INSTALLED,
            )
        self.assertEqual(route.model, "gemma3:12b")
        self.assertEqual(route.profile, "Accurate")
        self.assertEqual(route.model_selection_mode, "Auto")
        self.assertIn("Reasoning model", route.reason)

    @patch("apps.web.app.get_preference", return_value=None)
    def test_missing_configured_model_falls_back(self, _preference):
        with patch(
            "apps.web.app.get_preference",
            side_effect=lambda _db, key, *args: "missing:99b" if key.endswith("general") else None,
        ):
            status = app.model_profile_status(INSTALLED)
        self.assertTrue(status["general"]["missing"])
        self.assertEqual(status["general"]["resolved"], "gemma3:12b")


    @patch("apps.web.app.get_preference", return_value=None)
    def test_model_selection_options_include_mistral_small(self, _preference):
        installed = ["qwen3:8b", "qwen3:14b", "mistral-small3.2-24b-q3-local"]
        options = app.model_selection_options(installed)
        self.assertEqual(options[0], app.MODEL_SELECTION_AUTO)
        self.assertEqual(options[1:4], ["qwen3:8b", "qwen3:14b", "mistral-small3.2-24b-q3-local"])

    @patch("apps.web.app.get_preference", return_value=None)
    def test_mistral_small_alias_resolves_local_quantization(self, _preference):
        installed = ["qwen3:8b", "mistral-small3.2-24b-q2-local", "mistral-small3.2-24b-q3-local"]
        self.assertEqual(
            app.resolve_manual_model_selection(app.MISTRAL_SMALL_MODEL, installed),
            "mistral-small3.2-24b-q3-local",
        )

    @patch("apps.web.app.list_ollama_model_info", return_value={})
    @patch("apps.web.app.get_preference", return_value=None)
    def test_mistral_is_not_accurate_default_without_benchmark(self, _preference, _info):
        installed = ["qwen3:8b", "qwen3:14b", "mistral-small3.2-24b-q3-local"]
        status = app.performance_model_status(installed)
        self.assertEqual(status["Accurate"]["resolved"], "qwen3:14b")

    @patch("apps.web.app.list_ollama_model_info", return_value={})
    @patch("apps.web.app.get_preference")
    def test_mistral_can_be_enabled_for_auto_after_benchmark(self, preference, _info):
        def fake_preference(_db, key, *args):
            if key == app.MISTRAL_AUTO_ENABLED_KEY:
                return "1"
            if key == app.MISTRAL_BENCHMARK_KEY:
                return "benchmark_mistral.json"
            return None

        preference.side_effect = fake_preference
        installed = ["qwen3:8b", "qwen3:14b", "mistral-small3.2-24b-q3-local"]
        status = app.performance_model_status(installed)
        self.assertEqual(status["Accurate"]["resolved"], "mistral-small3.2-24b-q3-local")
if __name__ == "__main__":
    unittest.main()


