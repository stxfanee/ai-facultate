import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch

import httpx

import app


class LlmPerformanceTests(unittest.TestCase):
    def test_profiles_have_complete_ollama_configuration(self):
        for name in ("Fast", "Balanced", "Accurate"):
            profile = app.RESPONSE_PROFILES[name]
            self.assertTrue(profile.recommended_model)
            self.assertGreaterEqual(profile.context_window, 2048)
            self.assertGreater(profile.max_output_tokens, 0)
            self.assertGreater(profile.request_timeout, 0)
            self.assertGreater(profile.top_k, 0)
            self.assertGreater(profile.top_p, 0)
            self.assertTrue(profile.keep_alive)
        self.assertLess(
            app.RESPONSE_PROFILES["Fast"].context_window,
            app.RESPONSE_PROFILES["Accurate"].context_window,
        )

    @patch("app.gpu_vram_total_gb", return_value=8.0)
    @patch("app.get_preference", return_value=None)
    @patch("app.list_ollama_model_info")
    def test_balanced_falls_back_to_8b_when_14b_exceeds_vram(
        self, model_info, _preference, _gpu
    ):
        model_info.return_value = {
            "qwen3:8b": {
                "size_bytes": int(4.7 * 1024**3),
                "parameter_size": "8.2B",
                "quantization": "Q4_K_M",
            },
            "qwen3:14b": {
                "size_bytes": int(9.0 * 1024**3),
                "parameter_size": "14.8B",
                "quantization": "Q4_K_M",
            },
        }
        status = app.performance_model_status(["qwen3:8b", "qwen3:14b"])
        self.assertEqual(status["Fast"]["resolved"], "qwen3:8b")
        self.assertEqual(status["Balanced"]["resolved"], "qwen3:8b")
        self.assertEqual(status["Accurate"]["resolved"], "qwen3:14b")
        self.assertTrue(status["Accurate"]["may_spill"])

    @patch("app.model_profile_status")
    @patch("app.performance_model_status")
    @patch("app.list_llm_models", return_value=["qwen3:8b", "qwen3:14b"])
    def test_automatic_selection_uses_fast_for_simple_and_accurate_for_reasoning(
        self, _models, performance, model_profiles
    ):
        performance.return_value = {
            "Fast": {"resolved": "qwen3:8b", "missing": False, "may_spill": False},
            "Balanced": {"resolved": "qwen3:8b", "missing": False, "may_spill": False},
            "Accurate": {"resolved": "qwen3:14b", "missing": False, "may_spill": False, "fits_gpu": True},
        }
        model_profiles.return_value = {
            "rag": {"resolved": "qwen3:8b"},
            "general": {"resolved": "qwen3:8b"},
            "reasoning": {"resolved": "qwen3:14b"},
            "fast": {"resolved": "qwen3:8b"},
        }
        with patch("app.model_vram_status", return_value={"fits_gpu": True}):
            simple = app.select_model_for_mode(
                "Care este capitala Franței?",
                "Balanced",
                "Strict",
                "General knowledge only",
                "general",
            )
            reasoning = app.select_model_for_mode(
                "Analizează și compară mecanismele în detaliu.",
                "Balanced",
                "Analiză",
                "Hybrid (recommended)",
                "synthesis",
            )
        self.assertEqual(simple.model, "qwen3:8b")
        self.assertEqual(simple.profile, "Fast")
        self.assertEqual(reasoning.model, "qwen3:14b")
        self.assertEqual(reasoning.profile, "Accurate")

    @patch("app.performance_model_status")
    @patch("app.list_llm_models", return_value=["qwen3:8b", "qwen3:14b"])
    def test_auto_keeps_14b_for_complex_reasoning_even_when_it_may_spill(
        self, _models, performance
    ):
        performance.return_value = {
            "Fast": {"resolved": "qwen3:8b", "missing": False, "may_spill": False},
            "Balanced": {"resolved": "qwen3:8b", "missing": False, "may_spill": False},
            "Accurate": {"resolved": "qwen3:14b", "missing": False, "may_spill": True, "fits_gpu": False},
        }
        with app.model_mode_context("Auto"):
            route = app.select_model_for_mode(
                "Compară cursurile și evaluează care este mai greu.",
                "Balanced",
                "Auto",
                "Documents only",
                "synthesis",
            )
        self.assertEqual(route.model, "qwen3:14b")
        self.assertEqual(route.profile, "Accurate")
        self.assertEqual(route.complexity, "complex")

    @patch("app.performance_model_status")
    @patch("app.list_llm_models", return_value=["qwen3:8b", "qwen3:14b"])
    def test_explicit_model_mode_overrides_automatic_complexity(
        self, _models, performance
    ):
        performance.return_value = {
            "Fast": {"resolved": "qwen3:8b", "missing": False, "may_spill": False},
            "Balanced": {"resolved": "qwen3:8b", "missing": False, "may_spill": False},
            "Accurate": {"resolved": "qwen3:14b", "missing": False, "may_spill": True},
        }
        with app.model_mode_context("Fast"):
            fast = app.select_model_for_mode(
                "Analizează profund și construiește o strategie.",
                "Balanced",
                "Analiză",
                "Hybrid (recommended)",
                "synthesis",
            )
        with app.model_mode_context("Accurate"):
            accurate = app.select_model_for_mode(
                "Definește ATP.",
                "Balanced",
                "Strict",
                "Documents only",
                "rag",
            )
        self.assertEqual(fast.model, "qwen3:8b")
        self.assertEqual(accurate.model, "qwen3:14b")

    @patch("app.performance_model_status")
    @patch("app.list_llm_models", return_value=["qwen3:8b", "qwen3:14b"])
    def test_auto_uses_8b_for_quiz_generation(self, _models, performance):
        performance.return_value = {
            "Fast": {"resolved": "qwen3:8b", "missing": False, "may_spill": False},
            "Balanced": {"resolved": "qwen3:8b", "missing": False, "may_spill": False},
            "Accurate": {"resolved": "qwen3:14b", "missing": False, "may_spill": True},
        }
        with app.model_mode_context("Auto"):
            route = app.select_model_for_mode(
                "Generează 10 întrebări grilă despre glicoliză.",
                "Balanced",
                "Strict",
                "Documents only",
                "rag",
            )
        self.assertEqual(route.model, "qwen3:8b")

    @patch("app.get_preference")
    def test_timeout_can_be_configured_per_profile(self, preference):
        preference.side_effect = lambda _path, key, *args: (
            "210" if key == "performance_accurate_timeout" else None
        )
        self.assertEqual(app.get_response_profile("Accurate").request_timeout, 210.0)

    @patch("app.ollama_running_model_vram", return_value=5.25)
    @patch("app.model_vram_status", return_value={"estimated_vram_gb": 5.6, "may_spill": False})
    @patch("app.httpx.post")
    def test_benchmark_reports_runtime_metrics(self, post, _estimate, _vram):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "response": "Un răspuns de benchmark.",
            "eval_count": 120,
            "eval_duration": 4_000_000_000,
            "total_duration": 5_000_000_000,
        }
        post.return_value = response
        result = app.benchmark_ollama_model(
            "qwen3:8b",
            "Explică un concept.",
            "Fast",
            runs=1,
        )
        self.assertEqual(result["response_time_s"], 5.0)
        self.assertEqual(result["tokens_per_second"], 30.0)
        self.assertEqual(result["vram_gb"], 5.25)
        self.assertEqual(result["timeout_rate"], 0.0)

    @patch("app.performance_model_status")
    @patch("app.generation_llm")
    def test_timeout_falls_back_to_fast_model(self, generation_llm, performance):
        performance.return_value = {
            "Fast": {"resolved": "qwen3:8b"},
        }

        slow_llm = Mock()
        slow_llm.stream_complete.side_effect = httpx.ReadTimeout("prea lent")
        fast_llm = Mock()
        completion = Mock(delta="răspuns rapid")
        fast_llm.stream_complete.return_value = [completion]
        generation_llm.side_effect = lambda _mode, _tokens, model_name=None: (
            slow_llm if model_name == "qwen3:14b" else fast_llm
        )

        class QueueRequest:
            def raise_if_cancelled(self):
                return None

        @contextmanager
        def llm_slot():
            yield QueueRequest()

        with patch.object(app.INFERENCE_QUEUE, "llm_slot", llm_slot):
            answer, timed_out = app._generate_prompt_text(
                "prompt",
                "Accurate",
                500,
                model_name="qwen3:14b",
            )
        self.assertEqual(answer, "răspuns rapid")
        self.assertFalse(timed_out)
        self.assertEqual(generation_llm.call_count, 2)


if __name__ == "__main__":
    unittest.main()
