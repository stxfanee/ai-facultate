import unittest

from server.api import api_server


class ApiAnswerModeTests(unittest.TestCase):
    def test_ask_defaults_to_auto(self):
        request = api_server.AskRequest(question="Ce este energia internă?")
        self.assertEqual(request.answer_mode, "Auto")
        self.assertEqual(request.knowledge_mode, "Hybrid (recommended)")
        self.assertIsNone(request.request_id)

    def test_openapi_exposes_all_answer_modes(self):
        schema = api_server.app.openapi()
        answer_mode = schema["components"]["schemas"]["AskRequest"]["properties"][
            "answer_mode"
        ]
        self.assertEqual(
            answer_mode["enum"],
            ["Auto", "Strict", "Analiză", "Profesor", "Strategie de învățare"],
        )

    def test_openapi_exposes_queue_and_cancellation_endpoints(self):
        paths = api_server.app.openapi()["paths"]
        self.assertIn("/queue", paths)
        self.assertIn("/requests/{request_id}", paths)
        self.assertIn("get", paths["/requests/{request_id}"])
        self.assertIn("delete", paths["/requests/{request_id}"])

    def test_client_can_supply_request_id_for_polling(self):
        request = api_server.AskRequest(
            question="Explică energia internă.",
            request_id="client-request-123",
        )
        self.assertEqual(request.request_id, "client-request-123")

    def test_openapi_exposes_knowledge_modes(self):
        schema = api_server.app.openapi()
        knowledge_mode = schema["components"]["schemas"]["AskRequest"]["properties"][
            "knowledge_mode"
        ]
        self.assertEqual(
            knowledge_mode["enum"],
            [
                "Documents only",
                "Hybrid (recommended)",
                "General knowledge only",
            ],
        )

    def test_openapi_exposes_remote_user_endpoints(self):
        paths = api_server.app.openapi()["paths"]
        for path in (
            "/auth/login",
            "/documents/upload",
            "/documents/index",
            "/routing/debug",
        ):
            self.assertIn(path, paths)

    def test_automatic_routing_is_enabled_by_default(self):
        request = api_server.AskRequest(question="Ce este un Volvo V90 CC?")
        self.assertTrue(request.auto_routing)


if __name__ == "__main__":
    unittest.main()


