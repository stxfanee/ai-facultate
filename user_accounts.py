from __future__ import annotations

import contextvars
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PBKDF2_ITERATIONS = 310_000
ACTIVE_USERNAME = contextvars.ContextVar("faculty_copilot_username", default="local")
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

    def workspace(self, username: str | None = None) -> UserWorkspace:
        normalized = normalize_username(username or ACTIVE_USERNAME.get())
        root = self.users_dir / normalized
        documents = root / "documents"
        memory = root / "memory"
        documents.mkdir(parents=True, exist_ok=True)
        memory.mkdir(parents=True, exist_ok=True)
        return UserWorkspace(
            username=normalized,
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
