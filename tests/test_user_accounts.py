import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from user_accounts import (
    DynamicUserMemoryPath,
    UserAccountStore,
    authentication_enabled,
    default_username,
    user_context,
)


class UserAccountTests(unittest.TestCase):
    def test_authentication_is_off_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(authentication_enabled())
            self.assertEqual(default_username(), "default_user")

    def test_authentication_can_be_enabled_without_changing_user_architecture(self):
        environment = {
            "FACULTY_COPILOT_AUTH_ENABLED": "true",
            "FACULTY_COPILOT_DEFAULT_USER": "LAN Test User",
        }
        with patch.dict("os.environ", environment, clear=True):
            self.assertTrue(authentication_enabled())
            self.assertEqual(default_username(), "lan-test-user")

    def test_password_token_and_workspaces_are_isolated(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = UserAccountStore(Path(temporary_directory) / "storage")
            username, token = store.create_user("Ana Pop", password="parola-lunga")
            self.assertEqual(username, "ana-pop")
            self.assertEqual(store.authenticate_token(token), "ana-pop")
            self.assertIsNotNone(store.login("ana-pop", "parola-lunga"))

            ana = store.workspace("ana-pop")
            bob, _ = store.create_user("bob", password="alta-parola")
            self.assertNotEqual(ana.root, store.workspace(bob).root)
            self.assertTrue(ana.documents.exists())

    def test_dynamic_memory_path_follows_user_context(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = UserAccountStore(root / "storage")
            store.create_user("ana", password="parola-lunga")
            dynamic = DynamicUserMemoryPath(store, root / "local.sqlite3")
            self.assertEqual(dynamic.current(), root / "local.sqlite3")
            with user_context("ana"):
                self.assertIn("users\\ana\\memory", str(dynamic))


if __name__ == "__main__":
    unittest.main()
