import unittest
from unittest.mock import patch

import app


INSTALLED = ["qwen3:8b", "qwen3:14b", "gemma3:12b"]


class ModelRoutingTests(unittest.TestCase):
    @patch("app.get_preference", return_value=None)
    def test_profiles_prefer_installed_suggested_models(self, _preference):
        profiles = app.get_model_profiles(INSTALLED)
        self.assertEqual(profiles["rag"], "qwen3:8b")
        self.assertEqual(profiles["general"], "gemma3:12b")
        self.assertEqual(profiles["reasoning"], "qwen3:14b")
        self.assertEqual(profiles["fast"], "qwen3:8b")

    @patch("app.get_preference", return_value=None)
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
        self.assertEqual(general.model, "gemma3:12b")

    @patch("app.get_preference", return_value=None)
    def test_missing_configured_model_falls_back(self, _preference):
        with patch(
            "app.get_preference",
            side_effect=lambda _db, key, *args: "missing:99b" if key.endswith("general") else None,
        ):
            status = app.model_profile_status(INSTALLED)
        self.assertTrue(status["general"]["missing"])
        self.assertEqual(status["general"]["resolved"], "gemma3:12b")


if __name__ == "__main__":
    unittest.main()
