import unittest
from unittest.mock import patch

from apps.web import app


class ReasoningEngineTests(unittest.TestCase):
    def test_hardest_course_builds_cross_document_inference_plan(self):
        plan = app.build_reasoning_plan(
            "Care este cel mai greu curs?",
            available_documents=6,
        )
        self.assertEqual(plan.user_goal, "ranking")
        self.assertEqual(plan.answer_mode, "Analiză")
        self.assertEqual(plan.claim_type, "inference")
        self.assertEqual(plan.inference_level, "evaluative")
        self.assertTrue(plan.needs_documents)
        self.assertTrue(plan.needs_cross_document_reasoning)
        self.assertIn("cross_document_comparison", plan.tools)

    def test_recommendation_uses_documents_and_study_memory(self):
        plan = app.build_reasoning_plan(
            "Cu ce curs ar trebui să încep pentru examen?",
            available_documents=4,
            has_conversation_context=True,
        )
        self.assertEqual(plan.user_goal, "recommendation")
        self.assertEqual(plan.claim_type, "recommendation")
        self.assertIn("study_memory", plan.tools)
        self.assertIn("conversation_memory", plan.tools)

    def test_no_cross_document_claim_without_documents(self):
        plan = app.build_reasoning_plan(
            "Care este cel mai greu curs?",
            available_documents=0,
        )
        self.assertFalse(plan.needs_documents)
        self.assertFalse(plan.needs_cross_document_reasoning)

    def test_artifact_keywords_are_not_treated_as_requests_by_themselves(self):
        self.assertNotEqual(
            app.detect_user_intent("Ce înseamnă un quiz bine construit?").intent,
            "quiz",
        )
        self.assertNotEqual(
            app.detect_user_intent("Nu vreau quiz, explică-mi difracția.").intent,
            "quiz",
        )
        self.assertEqual(
            app.detect_user_intent("Fă-mi un quiz despre difracție.").intent,
            "quiz",
        )

    def test_debug_plan_contains_decisions_not_chain_of_thought(self):
        plan = app.build_reasoning_plan("Explică entropia.")
        response = app.attach_reasoning_plan(app.StudyResponse("Răspuns", [], {}), plan)
        debug_plan = response.debug["reasoning_plan"]
        self.assertIn("tools", debug_plan)
        self.assertNotIn("instruction", debug_plan)
        self.assertNotIn("thoughts", debug_plan)

    @patch("apps.web.app.query_documents")
    @patch("apps.web.app.get_indexed_documents")
    def test_ranking_executes_cross_document_tool(self, indexed, query_documents):
        indexed.return_value = [
            {"file_name": "A.pdf"},
            {"file_name": "B.pdf"},
            {"file_name": "C.pdf"},
        ]
        query_documents.return_value = app.StudyResponse("Clasament", [], {})
        response = app.query_copilot("Care este cel mai greu curs?")

        query_documents.assert_called_once()
        arguments = query_documents.call_args.kwargs
        self.assertTrue(arguments["force_global"])
        self.assertEqual(arguments["answer_mode"], "Analiză")
        self.assertEqual(
            response.debug["reasoning_plan"]["user_goal"],
            "ranking",
        )


if __name__ == "__main__":
    unittest.main()


