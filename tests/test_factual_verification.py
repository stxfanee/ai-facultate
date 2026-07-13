import unittest

from apps.web import app


class FactualVerificationTests(unittest.TestCase):
    def test_cp_ps_hp_regression_answer_uses_trusted_constants(self):
        question = "Care este diferența dintre CP, PS și hp și cum se convertesc în kW?"
        response = app.query_copilot(question, knowledge_mode="General knowledge only")
        text = str(response)
        self.assertIn("CP", text)
        self.assertIn("PS", text)
        self.assertIn("hp", text)
        self.assertIn("0.73549875", text)
        self.assertIn("1.3596216", text)
        self.assertIn("0.74569987", text)
        self.assertIn("1.3410221", text)
        self.assertNotIn("0.98632", text)
        self.assertEqual(response.debug["tool_used"], "unit_converter")
        self.assertEqual(response.debug["factual_verification"]["confidence"], "High")

    def test_verifier_replaces_wrong_ps_claim(self):
        draft = app.StudyResponse("1 PS ≈ 0.98632 kW", [], {})
        response = app.verify_factual_answer(
            "Care este diferența dintre CP, PS și hp și cum se convertesc în kW?",
            draft,
        )
        self.assertIn("0.73549875", str(response))
        self.assertNotIn("0.98632", str(response))
        self.assertTrue(response.debug["factual_verification"]["reviewer_corrected"])


if __name__ == "__main__":
    unittest.main()
