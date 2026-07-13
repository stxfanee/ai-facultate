import unittest
from unittest.mock import patch

from apps.web import app
from server.tools.factual_benchmark import (
    CP_PS_HP_REGRESSION,
    default_technical_questions,
    evaluate_answer,
    run_factual_benchmark,
)


class FactualReliabilityTests(unittest.TestCase):
    def test_technical_questions_use_conservative_generation_context(self):
        captured = {}

        class FakeOllama:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        with patch.object(app, "Ollama", FakeOllama):
            token = app.TECHNICAL_QUESTION_CONTEXT.set(True)
            try:
                app.generation_llm("Balanced", 200, model_name="qwen3:8b")
            finally:
                app.TECHNICAL_QUESTION_CONTEXT.reset(token)

        self.assertLessEqual(captured["temperature"], 0.15)
        self.assertLessEqual(captured["additional_kwargs"]["top_p"], 0.88)

    def test_factual_discipline_detects_technical_questions(self):
        instruction = app.factual_discipline_instruction("Care este 1 PS in kW?", "General knowledge only")
        self.assertIn("Nu ghici valori exacte", instruction)
        self.assertIn("Nu sunt suficient de sigur", instruction)

    def test_benchmark_question_set_has_100_items(self):
        self.assertEqual(len(default_technical_questions()), 100)

    def test_benchmark_flags_forbidden_conversion_claim(self):
        result = evaluate_answer(CP_PS_HP_REGRESSION, "1 PS ? 0.98632 kW", 0.1)
        self.assertTrue(result.hallucination_flag)
        self.assertIn("0.98632", result.forbidden_claims_found[0])

    def test_benchmark_runs_with_mock_answer_function(self):
        summary = run_factual_benchmark(lambda _q: "CP = PS; 0.73549875; 1.3596216; 0.74569987; 1.3410221", [CP_PS_HP_REGRESSION])
        self.assertEqual(summary["question_count"], 1)
        self.assertEqual(summary["hallucination_rate"], 0.0)
        self.assertEqual(summary["average_factual_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
