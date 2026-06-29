import unittest
from unittest.mock import patch

import app


class IntentDetectionTests(unittest.TestCase):
    def test_detects_supported_intents(self):
        cases = {
            "Ce spune cursul meu despre efectul tunel?": "course_question",
            "Unde scrie în document despre refracție?": "document_search",
            "Compară Cursul 1 cu Cursul 12.": "compare_documents",
            "Ce să învăț prima dată pentru examen?": "study_planning",
            "Generează flashcards despre optică.": "flashcards",
            "Fă-mi un quiz despre difracție.": "quiz",
            "Care sunt subiectele mele slabe?": "memory",
            "Care este capitala Franței?": "general_knowledge",
            (
                "Compare the tunnel effect from my course with how an STM microscope works."
            ): "mixed",
        }
        for question, expected in cases.items():
            with self.subTest(question=question):
                self.assertEqual(app.detect_user_intent(question).intent, expected)

    def test_named_product_question_is_explicit_general_knowledge(self):
        decision = app.detect_user_intent("ce este un Volvo V90 CC?")
        self.assertEqual(decision.intent, "general_knowledge")
        self.assertTrue(decision.explicit_general)


class HybridRoutingTests(unittest.TestCase):
    @patch("app.generate_prompt_text", return_value=("răspuns", False))
    def test_hybrid_prompt_separates_sources_from_general_knowledge(self, generate):
        chunks = [
            {
                "id": "chunk-1",
                "text": "Efectul tunel este prezentat în curs.",
                "metadata": {"file_name": "Curs 12.pdf", "page_number": 8},
                "rerank_score": 0.7,
            }
        ]
        response = app.complete_hybrid_from_chunks(
            "Compară efectul tunel cu STM.",
            chunks,
            {},
            "Fast",
            "Profesor",
            "Fără memorie relevantă.",
        )
        prompt = generate.call_args.args[0]
        self.assertIn("Din documentele tale", prompt)
        self.assertIn("Cunoștințe generale", prompt)
        self.assertIn("[document, pagina]", prompt)
        self.assertIn("Curs 12.pdf, pagina 8", prompt)
        self.assertEqual(response.chunks, chunks)

    @patch("app.generate_prompt_text", return_value=("Paris", False))
    def test_general_strict_mode_does_not_require_rag_context(self, generate):
        response = app.answer_general_question(
            "Care este capitala Franței?",
            "Fast",
            "Strict",
        )
        prompt = generate.call_args.args[0]
        self.assertIn("Lipsa contextului RAG nu este un motiv de refuz", prompt)
        self.assertEqual(response.chunks, [])

    @patch("app.retrieve_chunks")
    @patch("app.answer_general_question")
    def test_general_only_skips_chromadb(self, answer_general, retrieve_chunks):
        answer_general.return_value = app.StudyResponse("general", [], {})
        response = app.query_copilot(
            "Ce spune cursul despre energie?",
            knowledge_mode="General knowledge only",
        )
        retrieve_chunks.assert_not_called()
        self.assertEqual(response.debug["knowledge_route"], "general")
        self.assertEqual(response.debug["confidence"], 0.99)

    @patch("app.retrieve_chunks")
    @patch("app.answer_general_question")
    def test_obvious_general_question_skips_chromadb_in_hybrid(
        self,
        answer_general,
        retrieve_chunks,
    ):
        answer_general.return_value = app.StudyResponse("Paris", [], {})
        response = app.query_copilot("Care este capitala Franței?")
        retrieve_chunks.assert_not_called()
        self.assertEqual(response.debug["intent"], "general_knowledge")
        self.assertEqual(response.debug["knowledge_route"], "general")

    @patch("app.query_documents")
    def test_documents_only_keeps_rag(self, query_documents):
        query_documents.return_value = app.StudyResponse(
            "rag",
            [{"id": "1"}],
            {},
        )
        with patch("app.count_indexed_chunks", return_value=10):
            response = app.query_copilot(
                "Ce este energia internă?",
                knowledge_mode="Documents only",
            )
        query_documents.assert_called_once()
        self.assertEqual(response.debug["knowledge_route"], "rag")

    @patch("app.complete_hybrid_from_chunks")
    @patch("app.hybrid_retrieval_context")
    @patch("app.count_indexed_chunks", return_value=10)
    def test_mixed_question_combines_rag_and_general(
        self,
        _count,
        hybrid_context,
        complete_hybrid,
    ):
        chunks = [{"rerank_score": 0.61, "lexical_score": 0.2}]
        hybrid_context.return_value = (chunks, {}, None, [], "memory")
        complete_hybrid.return_value = app.StudyResponse("mixed", chunks, {})
        response = app.query_copilot(
            "Compare the tunnel effect from my course with how an STM microscope works."
        )
        complete_hybrid.assert_called_once()
        self.assertEqual(response.debug["intent"], "mixed")
        self.assertEqual(response.debug["knowledge_route"], "hybrid")
        self.assertGreaterEqual(response.debug["confidence"], 0.9)

    @patch("app.complete_from_chunks")
    @patch("app.hybrid_retrieval_context")
    @patch("app.count_indexed_chunks", return_value=10)
    def test_high_document_relevance_routes_to_rag(
        self,
        _count,
        hybrid_context,
        complete_from_chunks,
    ):
        chunks = [{"rerank_score": 0.62, "lexical_score": 0.18}]
        hybrid_context.return_value = (chunks, {}, None, [], "memory")
        complete_from_chunks.return_value = app.StudyResponse("rag", chunks, {})
        response = app.query_copilot("Explică energia internă.")
        complete_from_chunks.assert_called_once()
        self.assertEqual(response.debug["knowledge_route"], "rag")
        self.assertEqual(response.debug["intent"], "course_question")


if __name__ == "__main__":
    unittest.main()
