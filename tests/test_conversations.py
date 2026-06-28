import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path

import app
from study_memory import (
    add_conversation_message,
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    update_conversation_metadata,
    initialize_database,
)


class ConversationStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "memory.sqlite3"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_conversation_round_trip_search_and_delete(self):
        create_conversation(
            self.database_path,
            "conversation-1",
            "Efectul tunel",
            answer_mode="Profesor",
            response_mode="Balanced",
            workflow_mode="Caută în document specific",
            selected_documents=["Curs 12.pdf"],
        )
        add_conversation_message(
            self.database_path,
            "conversation-1",
            "user",
            "Explică efectul tunel.",
        )
        assistant_id = add_conversation_message(
            self.database_path,
            "conversation-1",
            "assistant",
            "Explicație cu sursă.",
            sources=[{"file_name": "Curs 12.pdf", "page": 8, "score": 0.91}],
            metadata={"answer_mode": "Profesor", "history_id": 4},
        )

        conversation = get_conversation(self.database_path, "conversation-1")
        self.assertIsNotNone(conversation)
        self.assertEqual(conversation["selected_documents"], ["Curs 12.pdf"])
        self.assertEqual(len(conversation["messages"]), 2)
        self.assertEqual(conversation["messages"][1]["id"], assistant_id)
        self.assertEqual(
            conversation["messages"][1]["sources"][0]["file_name"],
            "Curs 12.pdf",
        )
        self.assertEqual(conversation["messages"][1]["metadata"]["history_id"], 4)

        matches = list_conversations(self.database_path, search="tunel")
        self.assertEqual([item["id"] for item in matches], ["conversation-1"])
        matches = list_conversations(self.database_path, search="sursă")
        self.assertEqual([item["id"] for item in matches], ["conversation-1"])

        update_conversation_metadata(
            self.database_path,
            "conversation-1",
            answer_mode="Analiză",
            response_mode="Accurate",
            knowledge_mode="Hybrid (recommended)",
            workflow_mode="Compară cursuri",
            selected_documents=["Curs 1.pdf", "Curs 12.pdf"],
        )
        updated = get_conversation(self.database_path, "conversation-1")
        self.assertEqual(updated["answer_mode"], "Analiză")
        self.assertEqual(updated["response_mode"], "Accurate")
        self.assertEqual(updated["knowledge_mode"], "Hybrid (recommended)")
        self.assertEqual(updated["selected_documents"], ["Curs 1.pdf", "Curs 12.pdf"])

        self.assertTrue(delete_conversation(self.database_path, "conversation-1"))
        self.assertIsNone(get_conversation(self.database_path, "conversation-1"))
        self.assertFalse(delete_conversation(self.database_path, "conversation-1"))

    def test_title_is_generated_from_first_question(self):
        short = app.conversation_title("  Ce este energia internă?  ")
        self.assertEqual(short, "Ce este energia internă?")
        long_title = app.conversation_title("cuvânt " * 30, limit=40)
        self.assertLessEqual(len(long_title), 40)
        self.assertTrue(long_title.endswith("…"))

    def test_existing_database_gets_knowledge_mode_migration(self):
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                """
                CREATE TABLE conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    answer_mode TEXT NOT NULL DEFAULT 'Auto',
                    response_mode TEXT NOT NULL DEFAULT 'Balanced',
                    workflow_mode TEXT NOT NULL DEFAULT 'Întrebare normală',
                    selected_documents TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            connection.commit()
        initialize_database(self.database_path)
        with closing(sqlite3.connect(self.database_path)) as connection:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(conversations)")
            }
        self.assertIn("knowledge_mode", columns)


if __name__ == "__main__":
    unittest.main()
