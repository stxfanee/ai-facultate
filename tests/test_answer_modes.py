import unittest
from unittest.mock import patch

import app


class AnswerModeDetectionTests(unittest.TestCase):
    def test_strict_mode_detection(self):
        self.assertEqual(app.detect_answer_mode("Definește energia internă."), "Strict")
        self.assertEqual(app.detect_answer_mode("Care este formula lucrului mecanic?"), "Strict")

    def test_analysis_mode_detection(self):
        self.assertEqual(
            app.detect_answer_mode("Care curs pare cel mai greu și de ce?"),
            "Analiză",
        )
        self.assertEqual(
            app.detect_answer_mode("Compară Cursul 1 cu Cursul 12."),
            "Analiză",
        )

    def test_professor_mode_detection(self):
        self.assertEqual(
            app.detect_answer_mode("Explică efectul tunel ca unui student de anul I."),
            "Profesor",
        )

    def test_strategy_mode_detection(self):
        self.assertEqual(
            app.detect_answer_mode("Ce ar trebui să învăț prima dată pentru examen?"),
            "Strategie de învățare",
        )
        self.assertEqual(app.detect_answer_mode("Fă-mi un plan."), "Strategie de învățare")
        self.assertEqual(app.detect_answer_mode("Cum abordez sesiunea?"), "Strategie de învățare")

    def test_explicit_mode_overrides_auto_detection(self):
        self.assertEqual(
            app.resolve_answer_mode("Strict", "Compară cele două cursuri"),
            "Strict",
        )


class AnswerPromptTests(unittest.TestCase):
    def test_analysis_prompt_separates_evidence_and_inference(self):
        prompt = app.build_answer_prompt(
            question="Care curs este mai greu?",
            context="[Sursa 1: Curs 1.pdf, pagina 2] Exemplu",
            memory_context="Fără memorie relevantă.",
            target="",
            task="Compară.",
            response_instruction="Răspunde clar.",
            answer_mode="Analiză",
        )
        self.assertIn("Fapte din cursuri", prompt)
        self.assertIn("Inferență / analiză", prompt)
        self.assertIn("Concluzie", prompt)
        self.assertIn("evaluare inferențială", prompt)
        self.assertIn("[document, pagina]", prompt)

    def test_broad_ranking_uses_cross_document_reasoning(self):
        self.assertTrue(
            app.needs_cross_document_reasoning(
                "Care curs este cel mai greu?",
                "Analiză",
                [],
            )
        )

    def test_partial_analysis_keeps_required_structure(self):
        answer = app.partial_comparison_answer(
            "Care curs este mai greu?",
            [
                {
                    "document": {"file_name": "Curs 1.pdf"},
                    "summary": "Dovadă [Curs 1.pdf, pagina 2]",
                    "partial": False,
                }
            ],
            answer_mode="Analiză",
        )
        self.assertIn("Aceasta este o evaluare inferențială", answer)
        self.assertIn("## Fapte din cursuri", answer)
        self.assertIn("## Inferență / analiză", answer)
        self.assertIn("## Concluzie", answer)

    @patch("app.build_study_memory_context", return_value="Fără memorie.")
    @patch("app.generate_prompt_text", return_value=("", False))
    @patch("app.extract_course_evidence_for_comparison")
    def test_large_comparison_returns_structured_partial_result(
        self,
        extract_evidence,
        _generate,
        _memory,
    ):
        documents = [{"file_name": f"Curs {index}.pdf"} for index in range(1, 8)]

        def evidence(document, *_args, **_kwargs):
            return {
                "document": document,
                "summary": f"Dovadă din {document['file_name']}",
                "chunks": [],
                "cache_hit": False,
                "partial": False,
                "retrieval_debug": {},
            }

        extract_evidence.side_effect = evidence
        response = app.compare_courses_hierarchically(
            "Care curs este cel mai greu?",
            documents,
            response_mode="Fast",
            answer_mode="Analiză",
        )

        self.assertEqual(response.debug["answer_mode"], "Analiză")
        self.assertTrue(response.debug["extractive_course_summaries"])
        self.assertIn("## Concluzie", str(response))

    @patch("app.compare_courses_hierarchically")
    @patch("app.detect_document_references", return_value=[])
    @patch("app.get_indexed_documents")
    def test_auto_ranking_routes_all_documents_to_analysis(
        self,
        get_documents,
        _detect_references,
        compare_courses,
    ):
        documents = [
            {"file_name": "Curs 1.pdf"},
            {"file_name": "Curs 2.pdf"},
        ]
        get_documents.return_value = documents
        compare_courses.return_value = app.StudyResponse("ok", [], {})

        app.query_documents(
            "Care curs pare cel mai greu și de ce?",
            answer_mode="Auto",
        )

        compare_courses.assert_called_once()
        arguments = compare_courses.call_args.kwargs
        self.assertEqual(arguments["documents"], documents)
        self.assertEqual(arguments["answer_mode"], "Analiză")


if __name__ == "__main__":
    unittest.main()
