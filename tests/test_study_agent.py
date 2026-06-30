import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import app
from study_memory import (
    add_notebook_entry,
    delete_notebook_entry,
    get_flashcard_history,
    get_notebook_entries,
    record_flashcard_set,
    update_notebook_entry,
)


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "memory.sqlite3"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_notebook_requires_confirmation_for_every_mutation(self):
        with self.assertRaises(ValueError):
            add_notebook_entry(
                self.database_path,
                "professor_advice",
                "Capitol important.",
            )
        entry_id = add_notebook_entry(
            self.database_path,
            "professor_advice",
            "Capitol important.",
            confirmed=True,
        )
        self.assertEqual(len(get_notebook_entries(self.database_path)), 1)

        with self.assertRaises(ValueError):
            update_notebook_entry(
                self.database_path,
                entry_id,
                "exam_hint",
                "Apare la examen.",
            )
        self.assertTrue(
            update_notebook_entry(
                self.database_path,
                entry_id,
                "exam_hint",
                "Apare la examen.",
                confirmed=True,
            )
        )
        with self.assertRaises(ValueError):
            delete_notebook_entry(self.database_path, entry_id)
        self.assertTrue(
            delete_notebook_entry(
                self.database_path,
                entry_id,
                confirmed=True,
            )
        )

    def test_flashcard_sets_are_persistent(self):
        record_flashcard_set(
            self.database_path,
            "Genetică",
            [{"front": "Genă", "back": "Unitate ereditară"}],
        )
        history = get_flashcard_history(self.database_path)
        self.assertEqual(history[0]["topic"], "Genetică")
        self.assertEqual(history[0]["cards"][0]["front"], "Genă")


class ProactiveAgentTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc).astimezone()

    @patch("app.get_notebook_entries", return_value=[])
    @patch("app.get_flashcard_history", return_value=[])
    @patch("app.get_weak_topics", return_value=[])
    @patch("app.get_recent_sessions", return_value=[])
    @patch("app.get_session_plans", return_value=[])
    @patch("app.get_quiz_results", return_value=[])
    @patch("app.get_recent_questions")
    @patch("app.get_indexed_documents", return_value=[{"file_name": "Genetica.pdf"}])
    def test_detects_course_not_revised_for_ten_days(
        self,
        _documents,
        recent_questions,
        _quiz,
        _plans,
        _sessions,
        _weak,
        _flashcards,
        _notebook,
    ):
        recent_questions.return_value = [
            {
                "created_at": (self.now - timedelta(days=12)).isoformat(),
                "selected_document": "Genetica.pdf",
                "retrieved_documents": [],
            }
        ]
        insights = app.build_proactive_study_insights(now=self.now)
        self.assertIn("12 zile", insights[0]["message"])
        self.assertIn("Genetica.pdf", insights[0]["message"])

    @patch("app.get_notebook_entries", return_value=[])
    @patch("app.get_flashcard_history", return_value=[])
    @patch("app.get_weak_topics", return_value=[])
    @patch("app.get_recent_sessions", return_value=[])
    @patch("app.get_session_plans", return_value=[])
    @patch("app.get_recent_questions", return_value=[])
    @patch("app.get_indexed_documents", return_value=[])
    @patch("app.get_quiz_results")
    def test_detects_repeated_quiz_mistakes(
        self,
        quiz_results,
        _documents,
        _history,
        _plans,
        _sessions,
        _weak,
        _flashcards,
        _notebook,
    ):
        quiz_results.return_value = [
            {"topic": "Glicoliză", "score": 0},
            {"topic": "Glicoliză", "score": 0},
            {"topic": "Glicoliză", "score": 1},
        ]
        insights = app.build_proactive_study_insights(now=self.now)
        mistake = next(item for item in insights if "greșeli" in item["title"])
        self.assertIn("Glicoliză", mistake["message"])
        self.assertIn("2 răspunsuri greșite", mistake["message"])

    def test_product_name_is_stable(self):
        self.assertEqual(app.APP_TITLE, "Co-pilot Facultate")

    @patch(
        "app.get_notebook_entries",
        return_value=[
            {
                "category": "study_preference",
                "content": "Prefer explicații cu exemple vizuale.",
            }
        ],
    )
    @patch(
        "app.get_relevant_memory",
        return_value={"weak_topics": [], "previous_questions": []},
    )
    def test_confirmed_notebook_is_used_as_assistant_context(self, _memory, _notes):
        context = app.build_study_memory_context(
            "Explică fotosinteza",
            "fotosinteză",
            None,
        )
        self.assertIn("Prefer explicații cu exemple vizuale.", context)
        self.assertIn("nu instrucțiuni de sistem", context)


if __name__ == "__main__":
    unittest.main()
