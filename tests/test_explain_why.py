import unittest
from unittest.mock import patch

import app


class ExplainWhyTests(unittest.TestCase):
    def test_hybrid_explanation_groups_documents_and_pages(self):
        message = {
            "id": 7,
            "role": "assistant",
            "content": "Răspuns",
            "sources": [
                {
                    "file_name": "Biochimie.pdf",
                    "page": 52,
                    "score": 0.88,
                    "excerpt": "ATP",
                },
                {
                    "file_name": "Biochimie.pdf",
                    "page": 53,
                    "score": 0.91,
                    "excerpt": "Fosforilare oxidativă",
                },
                {
                    "file_name": "Genetica.pdf",
                    "page": 18,
                    "score": 0.72,
                    "excerpt": "Mitocondrie",
                },
            ],
            "metadata": {
                "debug": {
                    "rag_used": True,
                    "general_knowledge_used": True,
                    "intent": "mixed",
                    "knowledge_mode": "Hybrid (recommended)",
                    "knowledge_route": "hybrid",
                    "selected_model": "qwen3:14b",
                    "confidence": 0.82,
                    "routing_reason": "Documente relevante și completare generală.",
                }
            },
        }
        explanation = app.build_explain_why(message)
        self.assertEqual(explanation["knowledge_source"], "Ambele (Hybrid)")
        self.assertEqual(explanation["confidence"], "Ridicată")
        self.assertEqual(explanation["documents"][0]["pages"], [52, 53])
        self.assertIn("Biochimie.pdf", explanation["source_summary"])
        self.assertNotIn("debug", explanation)

    def test_low_confidence_explains_missing_information(self):
        message = {
            "id": 1,
            "role": "assistant",
            "content": "Răspuns parțial",
            "sources": [],
            "metadata": {
                "debug": {
                    "knowledge_route": "general",
                    "general_knowledge_used": True,
                    "confidence": 0.2,
                    "partial": True,
                }
            },
        }
        explanation = app.build_explain_why(message)
        self.assertEqual(explanation["confidence"], "Scăzută")
        self.assertGreaterEqual(len(explanation["missing_information"]), 2)
        self.assertIn("cunoștințe generale", explanation["source_summary"])

    @patch("app.get_indexed_documents", return_value=[])
    @patch("app.answer_general_question")
    def test_query_records_safe_latency_metadata(self, answer_general, _documents):
        answer_general.return_value = app.StudyResponse(
            "Paris",
            [],
            {
                "selected_model": "qwen3:14b",
                "general_knowledge_used": True,
            },
        )
        response = app.query_copilot("Care este capitala Franței?")
        latency = response.debug["latency"]
        self.assertIn("retrieval_seconds", latency)
        self.assertIn("inference_seconds", latency)
        self.assertIn("total_seconds", latency)
        self.assertGreaterEqual(latency["total_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
