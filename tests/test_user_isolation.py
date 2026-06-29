import tempfile
import unittest
from pathlib import Path

import app as study_app
from user_accounts import UserAccountStore, user_context


class UserIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.original_accounts = study_app.USER_ACCOUNTS
        study_app.USER_ACCOUNTS = UserAccountStore(self.root / "storage")
        study_app.USER_ACCOUNTS.create_profile("ana")
        study_app.USER_ACCOUNTS.create_profile("bob")

    def tearDown(self):
        study_app.USER_ACCOUNTS = self.original_accounts
        self.temporary_directory.cleanup()

    def test_user_collection_prefixes_are_distinct(self):
        ana_prefix = study_app.user_collection_prefix("ana")
        bob_prefix = study_app.user_collection_prefix("bob")

        self.assertNotEqual(ana_prefix, bob_prefix)
        self.assertTrue(study_app.collection_belongs_to_user(f"{ana_prefix}_123", "ana"))
        self.assertFalse(study_app.collection_belongs_to_user(f"{bob_prefix}_123", "ana"))

    def test_local_collection_does_not_claim_user_collections(self):
        user_collection = f"{study_app.user_collection_prefix('ana')}_123"

        self.assertFalse(study_app.collection_belongs_to_user(user_collection, "local"))
        self.assertTrue(
            study_app.collection_belongs_to_user(
                f"{study_app.DEFAULT_COLLECTION_NAME}_123",
                "local",
            )
        )

    def test_current_documents_dir_and_path_validation_are_per_user(self):
        with user_context("ana"):
            ana_documents = study_app.current_documents_dir()
            bob_documents = study_app.USER_ACCOUNTS.workspace("bob").documents

            self.assertIn("users", str(ana_documents))
            self.assertTrue(study_app.is_current_user_document_path(ana_documents / "curs.pdf"))
            self.assertFalse(study_app.is_current_user_document_path(bob_documents / "curs.pdf"))

    def test_active_collection_file_ignores_other_user_collection(self):
        bob_collection = f"{study_app.user_collection_prefix('bob')}_123"
        with user_context("ana"):
            active_file = study_app.current_active_collection_file()
            active_file.parent.mkdir(parents=True, exist_ok=True)
            active_file.write_text(bob_collection, encoding="utf-8")

            active_collection = study_app.get_active_collection_name()

        self.assertTrue(study_app.collection_belongs_to_user(active_collection, "ana"))
        self.assertNotEqual(active_collection, bob_collection)


if __name__ == "__main__":
    unittest.main()
