from __future__ import annotations

import contextvars
import hashlib
import hmac
import os
import re
import secrets
import shutil
import sqlite3
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PBKDF2_ITERATIONS = 310_000
ACTIVE_USERNAME = contextvars.ContextVar("faculty_copilot_username", default="local")
ACTIVE_WORKSPACE = contextvars.ContextVar("faculty_copilot_workspace", default="general")
DEFAULT_USERNAME = "default_user"


def authentication_enabled() -> bool:
    """Return whether requests must provide user credentials."""
    value = os.environ.get("FACULTY_COPILOT_AUTH_ENABLED", "0")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def normalize_username(username: str) -> str:
    value = re.sub(r"[^a-z0-9._-]+", "-", (username or "").strip().lower())
    value = value.strip("-._")
    if not value or len(value) > 64:
        raise ValueError("Numele de utilizator trebuie să aibă între 1 și 64 de caractere.")
    return value


def normalize_workspace_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", (name or "").strip())
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", without_accents.lower()).strip("-._")
    if not value or len(value) > 64:
        raise ValueError("Numele workspace-ului trebuie să aibă între 1 și 64 de caractere.")
    return value


def default_username() -> str:
    """Return the shared workspace used while authentication is disabled."""
    configured = os.environ.get("FACULTY_COPILOT_DEFAULT_USER", DEFAULT_USERNAME)
    try:
        return normalize_username(configured)
    except ValueError:
        return DEFAULT_USERNAME


def _hash_secret(secret: str, salt: bytes | None = None) -> tuple[str, str]:
    if not secret:
        raise ValueError("Parola sau tokenul nu poate fi gol.")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", secret.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return salt.hex(), digest.hex()


def _verify_secret(secret: str, salt_hex: str | None, digest_hex: str | None) -> bool:
    if not secret or not salt_hex or not digest_hex:
        return False
    _salt, candidate = _hash_secret(secret, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, digest_hex)


@dataclass(frozen=True)
class UserWorkspace:
    username: str
    workspace_slug: str
    workspace_name: str
    root: Path
    documents: Path
    memory: Path
    memory_db: Path
    active_collection_file: Path


class UserAccountStore:
    def __init__(self, storage_root: Path):
        self.storage_root = Path(storage_root)
        self.auth_dir = self.storage_root / "auth"
        self.users_dir = self.storage_root / "users"
        self.database_path = self.auth_dir / "users.sqlite3"
        self.initialize()

    @contextmanager
    def _database(self):
        connection = sqlite3.connect(self.database_path, timeout=30)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        self.auth_dir.mkdir(parents=True, exist_ok=True)
        self.users_dir.mkdir(parents=True, exist_ok=True)
        with self._database() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_salt TEXT,
                    password_hash TEXT,
                    token_salt TEXT,
                    token_hash TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workspaces (
                    username TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(username, slug)
                )
                """
            )
        self._bootstrap_from_environment()

    def _bootstrap_from_environment(self) -> None:
        username = os.environ.get("FACULTY_COPILOT_ADMIN_USERNAME", "").strip()
        password = os.environ.get("FACULTY_COPILOT_ADMIN_PASSWORD", "").strip()
        token = os.environ.get("FACULTY_COPILOT_API_TOKEN", "").strip()
        if username and (password or token) and not self.user_exists(username):
            self.create_user(username, password=password or None, token=token or None)

    def user_exists(self, username: str) -> bool:
        try:
            normalized = normalize_username(username)
        except ValueError:
            return False
        with self._database() as connection:
            row = connection.execute(
                "SELECT 1 FROM users WHERE username = ? AND enabled = 1",
                (normalized,),
            ).fetchone()
        return row is not None

    def list_profiles(self) -> list[str]:
        """List enabled accounts and passwordless workspace profiles."""
        with self._database() as connection:
            rows = connection.execute(
                "SELECT username FROM users WHERE enabled = 1 ORDER BY username"
            ).fetchall()
        profiles = {str(row[0]) for row in rows}
        if self.users_dir.exists():
            for path in self.users_dir.iterdir():
                if not path.is_dir():
                    continue
                try:
                    profiles.add(normalize_username(path.name))
                except ValueError:
                    continue
        return sorted(profiles)

    def create_profile(self, username: str) -> str:
        """Create a local profile without a password or API token."""
        normalized = normalize_username(username)
        now = _now()
        with self._database() as connection:
            connection.execute(
                """
                INSERT INTO users(
                    username, password_salt, password_hash, token_salt, token_hash,
                    enabled, created_at, updated_at
                ) VALUES (?, NULL, NULL, NULL, NULL, 1, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    enabled = 1,
                    updated_at = excluded.updated_at
                """,
                (normalized, now, now),
            )
        self.workspace(normalized)
        return normalized

    def list_workspaces(self, username: str) -> list[dict]:
        normalized = normalize_username(username)
        self._ensure_general_workspace(normalized)
        with self._database() as connection:
            rows = connection.execute(
                """
                SELECT slug, display_name, created_at, updated_at
                FROM workspaces WHERE username = ?
                ORDER BY CASE WHEN slug = 'general' THEN 0 ELSE 1 END,
                         lower(display_name)
                """,
                (normalized,),
            ).fetchall()
        return [
            {
                "slug": str(row[0]),
                "name": str(row[1]),
                "created_at": str(row[2]),
                "updated_at": str(row[3]),
            }
            for row in rows
        ]

    def _ensure_general_workspace(self, username: str) -> None:
        timestamp = _now()
        with self._database() as connection:
            connection.execute(
                """
                INSERT INTO workspaces(username, slug, display_name, created_at, updated_at)
                VALUES (?, 'general', 'General', ?, ?)
                ON CONFLICT(username, slug) DO NOTHING
                """,
                (username, timestamp, timestamp),
            )

    def create_workspace(self, username: str, name: str) -> dict:
        normalized = normalize_username(username)
        display_name = " ".join((name or "").strip().split())
        slug = normalize_workspace_name(display_name)
        if slug == "general":
            self._ensure_general_workspace(normalized)
            return {"slug": "general", "name": "General"}
        timestamp = _now()
        with self._database() as connection:
            connection.execute(
                """
                INSERT INTO workspaces(username, slug, display_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(username, slug) DO UPDATE SET
                    display_name = excluded.display_name,
                    updated_at = excluded.updated_at
                """,
                (normalized, slug, display_name, timestamp, timestamp),
            )
        self.workspace(normalized, slug)
        return {"slug": slug, "name": display_name}

    def delete_workspace(self, username: str, workspace_slug: str) -> bool:
        normalized = normalize_username(username)
        slug = normalize_workspace_name(workspace_slug)
        if slug == "general":
            raise ValueError("Workspace-ul General păstrează datele existente și nu poate fi șters.")
        root = (self.users_dir / normalized / "workspaces" / slug).resolve()
        workspace_root = (self.users_dir / normalized / "workspaces").resolve()
        if root.parent != workspace_root:
            raise ValueError("Calea workspace-ului nu este sigură.")
        with self._database() as connection:
            cursor = connection.execute(
                "DELETE FROM workspaces WHERE username = ? AND slug = ?",
                (normalized, slug),
            )
        existed = root.exists() or cursor.rowcount > 0
        if root.exists():
            shutil.rmtree(root)
        return existed

    def delete_profile(self, username: str) -> bool:
        normalized = normalize_username(username)
        if normalized == "local":
            raise ValueError("Profilul local intern nu poate fi șters.")
        with self._database() as connection:
            connection.execute(
                "DELETE FROM workspaces WHERE username = ?", (normalized,)
            )
            cursor = connection.execute(
                "DELETE FROM users WHERE username = ?", (normalized,)
            )
            deleted_rows = cursor.rowcount
        root = (self.users_dir / normalized).resolve()
        users_root = self.users_dir.resolve()
        if root.parent != users_root:
            raise ValueError("Calea profilului nu este sigură.")
        existed = root.exists() or deleted_rows > 0
        if root.exists():
            shutil.rmtree(root)
        return existed

    def create_user(
        self,
        username: str,
        password: str | None = None,
        token: str | None = None,
    ) -> tuple[str, str]:
        normalized = normalize_username(username)
        if not password and not token:
            password = secrets.token_urlsafe(16)
        issued_token = token or secrets.token_urlsafe(32)
        password_salt = password_hash = None
        if password:
            password_salt, password_hash = _hash_secret(password)
        token_salt, token_hash = _hash_secret(issued_token)
        now = _now()
        with self._database() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    username, password_salt, password_hash, token_salt, token_hash,
                    enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password_salt = excluded.password_salt,
                    password_hash = excluded.password_hash,
                    token_salt = excluded.token_salt,
                    token_hash = excluded.token_hash,
                    enabled = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized,
                    password_salt,
                    password_hash,
                    token_salt,
                    token_hash,
                    now,
                    now,
                ),
            )
        self.workspace(normalized)
        return normalized, issued_token

    def login(self, username: str, password: str) -> str | None:
        normalized = normalize_username(username)
        with self._database() as connection:
            row = connection.execute(
                """
                SELECT password_salt, password_hash
                FROM users WHERE username = ? AND enabled = 1
                """,
                (normalized,),
            ).fetchone()
        if not row or not _verify_secret(password, row[0], row[1]):
            return None
        token = secrets.token_urlsafe(32)
        token_salt, token_hash = _hash_secret(token)
        with self._database() as connection:
            connection.execute(
                """
                UPDATE users SET token_salt = ?, token_hash = ?, updated_at = ?
                WHERE username = ?
                """,
                (token_salt, token_hash, _now(), normalized),
            )
        return token

    def authenticate_token(self, token: str) -> str | None:
        if not token:
            return None
        with self._database() as connection:
            rows = connection.execute(
                """
                SELECT username, token_salt, token_hash
                FROM users WHERE enabled = 1 AND token_hash IS NOT NULL
                """
            ).fetchall()
        for username, salt, digest in rows:
            if _verify_secret(token, salt, digest):
                return username
        return None

    def workspace(
        self,
        username: str | None = None,
        workspace_name: str | None = None,
    ) -> UserWorkspace:
        normalized = normalize_username(username or ACTIVE_USERNAME.get())
        slug = normalize_workspace_name(workspace_name or ACTIVE_WORKSPACE.get())
        self._ensure_general_workspace(normalized)
        profile_root = self.users_dir / normalized
        root = (
            profile_root
            if slug == "general"
            else profile_root / "workspaces" / slug
        )
        workspace_records = {
            item["slug"]: item["name"] for item in self.list_workspaces(normalized)
        }
        display_name = workspace_records.get(slug)
        if display_name is None:
            raise ValueError("Workspace-ul nu există.")
        documents = root / "documents"
        memory = root / "memory"
        documents.mkdir(parents=True, exist_ok=True)
        memory.mkdir(parents=True, exist_ok=True)
        return UserWorkspace(
            username=normalized,
            workspace_slug=slug,
            workspace_name=display_name,
            root=root,
            documents=documents,
            memory=memory,
            memory_db=memory / "study_memory.sqlite3",
            active_collection_file=root / "active_collection.txt",
        )


@contextmanager
def user_context(username: str):
    normalized = normalize_username(username)
    token = ACTIVE_USERNAME.set(normalized)
    try:
        yield normalized
    finally:
        ACTIVE_USERNAME.reset(token)


@contextmanager
def workspace_context(workspace_name: str):
    slug = normalize_workspace_name(workspace_name)
    token = ACTIVE_WORKSPACE.set(slug)
    try:
        yield slug
    finally:
        ACTIVE_WORKSPACE.reset(token)


class DynamicUserMemoryPath(os.PathLike[str]):
    def __init__(self, store: UserAccountStore, local_path: Path):
        self.store = store
        self.local_path = Path(local_path)

    def current(self) -> Path:
        username = ACTIVE_USERNAME.get()
        return self.local_path if username == "local" else self.store.workspace(username).memory_db

    def __fspath__(self) -> str:
        return str(self.current())

    def __str__(self) -> str:
        return str(self.current())

    def __repr__(self) -> str:
        return repr(self.current())

    @property
    def parent(self) -> Path:
        return self.current().parent

    @property
    def name(self) -> str:
        return self.current().name

    def exists(self) -> bool:
        return self.current().exists()
