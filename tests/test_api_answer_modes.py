import unittest

import api_server


class ApiAnswerModeTests(unittest.TestCase):
    def test_ask_defaults_to_auto(self):
        request = api_server.AskRequest(question="Ce este energia internă?")
        self.assertEqual(request.answer_mode, "Auto")

    def test_openapi_exposes_all_answer_modes(self):
        schema = api_server.app.openapi()
        answer_mode = schema["components"]["schemas"]["AskRequest"]["properties"][
            "answer_mode"
        ]
        self.assertEqual(
            answer_mode["enum"],
            ["Auto", "Strict", "Analiză", "Profesor", "Strategie de învățare"],
        )


if __name__ == "__main__":
    unittest.main()
