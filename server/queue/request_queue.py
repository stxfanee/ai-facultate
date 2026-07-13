from __future__ import annotations

import contextvars
import ctypes
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator


QueueCallback = Callable[[str, int | None, str], None]
MAX_CONCURRENT_PREFERENCE = "max_concurrent_generations"
DEFAULT_MAX_CONCURRENT = 1
MAX_ALLOWED_CONCURRENT = 4
DEFAULT_QUEUE_TIMEOUT_SECONDS = 600.0
STALE_RUNNING_SECONDS = 3600


class QueueWaitTimeoutError(TimeoutError):
    pass


class RequestCancelledError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _process_is_running(process_id: int) -> bool:
    if process_id <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        still_active = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            process_id,
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(
                handle,
                ctypes.byref(exit_code),
            ):
                return False
            return exit_code.value == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(process_id, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class InferenceRequestQueue:
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self._current_request: contextvars.ContextVar[QueuedInferenceRequest | None] = (
            contextvars.ContextVar("faculty_copilot_inference_request", default=None)
        )
        self.ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @contextmanager
    def _database(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def ensure_schema(self) -> None:
        with self._database() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS inference_requests (
                    request_id TEXT PRIMARY KEY,
                    user_session_id TEXT NOT NULL,
                    request_type TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'completed', 'failed')),
                    created_at TEXT NOT NULL,
                    ready_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    owner_pid INTEGER,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_inference_requests_queue
                    ON inference_requests(status, ready_at, created_at);
                CREATE INDEX IF NOT EXISTS idx_inference_requests_user
                    ON inference_requests(user_session_id, created_at DESC);
                """
            )

    def get_max_concurrent(self, connection: sqlite3.Connection | None = None) -> int:
        owns_connection = connection is None
        connection = connection or self._connect()
        try:
            row = connection.execute(
                "SELECT preference_value FROM user_preferences WHERE preference_key = ?",
                (MAX_CONCURRENT_PREFERENCE,),
            ).fetchone()
            value = int(row["preference_value"]) if row else DEFAULT_MAX_CONCURRENT
        except (sqlite3.Error, TypeError, ValueError):
            value = DEFAULT_MAX_CONCURRENT
        finally:
            if owns_connection:
                connection.close()
        return max(1, min(MAX_ALLOWED_CONCURRENT, value))

    def enqueue(
        self,
        user_session_id: str,
        request_type: str = "generation",
        callback: QueueCallback | None = None,
        request_id: str | None = None,
    ) -> "QueuedInferenceRequest":
        request_id = request_id or str(uuid.uuid4())
        user_session_id = user_session_id or "anonymous"
        with self._database() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup_stale_running(connection)
            self._cleanup_abandoned_queued(connection, user_session_id, request_type)
            connection.execute(
                """
                INSERT INTO inference_requests(
                    request_id, user_session_id, request_type, status, created_at, owner_pid
                ) VALUES (?, ?, ?, 'queued', ?, ?)
                """,
                (request_id, user_session_id, request_type, _now(), os.getpid()),
            )
        return QueuedInferenceRequest(self, request_id, callback)

    @contextmanager
    def request_context(
        self,
        user_session_id: str,
        request_type: str = "generation",
        callback: QueueCallback | None = None,
        request_id: str | None = None,
    ) -> Iterator["QueuedInferenceRequest"]:
        existing = self._current_request.get()
        if existing is not None:
            if callback is not None:
                existing.callback = callback
            yield existing
            return

        request = self.enqueue(
            user_session_id,
            request_type,
            callback,
            request_id=request_id,
        )
        token = self._current_request.set(request)
        try:
            yield request
        except Exception as exc:
            self.fail(request.request_id, str(exc))
            raise
        else:
            self.complete(request.request_id)
        finally:
            self._current_request.reset(token)

    @contextmanager
    def llm_slot(
        self,
        user_session_id: str = "implicit",
        request_type: str = "generation",
        callback: QueueCallback | None = None,
        timeout_seconds: float | None = None,
    ) -> Iterator["QueuedInferenceRequest"]:
        existing = self._current_request.get()
        if existing is not None:
            if callback is not None:
                existing.callback = callback
            existing.acquire(timeout_seconds)
            existing.raise_if_cancelled()
            yield existing
            return

        with self.request_context(user_session_id, request_type, callback) as request:
            request.acquire(timeout_seconds)
            request.raise_if_cancelled()
            yield request

    def current_request(self) -> "QueuedInferenceRequest | None":
        return self._current_request.get()

    def _cleanup_abandoned_queued(
        self,
        connection: sqlite3.Connection,
        user_session_id: str | None = None,
        request_type: str | None = None,
    ) -> None:
        now = _now()
        timeout = float(
            os.environ.get(
                "FACULTY_COPILOT_QUEUE_ABANDONED_SECONDS",
                min(DEFAULT_QUEUE_TIMEOUT_SECONDS, 120.0),
            )
        )
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=timeout)).isoformat(
            timespec="seconds"
        )
        connection.execute(
            """
            UPDATE inference_requests
            SET status = 'failed', completed_at = ?,
                error_message = 'Cerere abandonata in coada AI.'
            WHERE status = 'queued' AND ready_at IS NOT NULL AND ready_at < ?
            """,
            (now, cutoff),
        )
        queued_rows = connection.execute(
            """
            SELECT request_id, owner_pid
            FROM inference_requests
            WHERE status = 'queued' AND owner_pid IS NOT NULL
            """
        ).fetchall()
        for row in queued_rows:
            if not _process_is_running(int(row["owner_pid"])):
                connection.execute(
                    """
                    UPDATE inference_requests
                    SET status = 'failed', completed_at = ?,
                        error_message = 'Procesul care astepta coada AI s-a oprit.'
                    WHERE request_id = ? AND status = 'queued'
                    """,
                    (now, row["request_id"]),
                )
        if user_session_id:
            params: list[str] = [now, user_session_id]
            type_clause = ""
            if request_type:
                type_clause = " AND request_type = ?"
                params.append(request_type)
            connection.execute(
                f"""
                UPDATE inference_requests
                SET status = 'failed', completed_at = ?,
                    error_message = 'Cerere inlocuita de o intrebare mai noua.'
                WHERE status = 'queued' AND user_session_id = ?{type_clause}
                """,
                params,
            )

    def _cleanup_stale_running(self, connection: sqlite3.Connection) -> None:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=STALE_RUNNING_SECONDS)
        ).isoformat(timespec="seconds")
        connection.execute(
            """
            UPDATE inference_requests
            SET status = 'failed', completed_at = ?,
                error_message = 'Cerere expirată după oprirea procesului server.'
            WHERE status = 'running' AND started_at < ?
            """,
            (_now(), cutoff),
        )
        running_rows = connection.execute(
            """
            SELECT request_id, owner_pid
            FROM inference_requests
            WHERE status = 'running' AND owner_pid IS NOT NULL
            """
        ).fetchall()
        for row in running_rows:
            if not _process_is_running(int(row["owner_pid"])):
                connection.execute(
                    """
                    UPDATE inference_requests
                    SET status = 'failed', completed_at = ?,
                        error_message = 'Procesul care rula cererea s-a oprit.'
                    WHERE request_id = ? AND status = 'running'
                    """,
                    (_now(), row["request_id"]),
                )

    def try_acquire(self, request_id: str) -> tuple[bool, int | None]:
        with self._database() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup_stale_running(connection)
            self._cleanup_abandoned_queued(connection)
            request = connection.execute(
                "SELECT * FROM inference_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if request is None:
                raise KeyError(f"Cerere inexistentă: {request_id}")
            if request["cancel_requested"]:
                connection.execute(
                    """
                    UPDATE inference_requests
                    SET status = 'failed', completed_at = ?, error_message = 'Cerere anulată.'
                    WHERE request_id = ? AND status = 'queued'
                    """,
                    (_now(), request_id),
                )
                raise RequestCancelledError("Cererea a fost anulată.")
            if request["status"] == "running":
                return True, 0
            if request["status"] == "failed":
                raise RequestCancelledError(request["error_message"] or "Cererea a eșuat.")
            if request["status"] == "completed":
                return True, 0

            ready_at = request["ready_at"] or _now()
            if request["ready_at"] is None:
                connection.execute(
                    "UPDATE inference_requests SET ready_at = ? WHERE request_id = ?",
                    (ready_at, request_id),
                )

            running = connection.execute(
                "SELECT COUNT(*) FROM inference_requests WHERE status = 'running'"
            ).fetchone()[0]
            available = max(0, self.get_max_concurrent(connection) - int(running))
            queued_rows = connection.execute(
                """
                SELECT request_id
                FROM inference_requests
                WHERE status = 'queued' AND ready_at IS NOT NULL
                ORDER BY ready_at, created_at, request_id
                """
            ).fetchall()
            queued_ids = [row["request_id"] for row in queued_rows]
            position = queued_ids.index(request_id) + 1
            if available > 0 and request_id in queued_ids[:available]:
                connection.execute(
                    """
                    UPDATE inference_requests
                    SET status = 'running', started_at = COALESCE(started_at, ?),
                        owner_pid = ?
                    WHERE request_id = ? AND status = 'queued'
                    """,
                    (_now(), os.getpid(), request_id),
                )
                return True, 0
            return False, position

    def complete(self, request_id: str) -> None:
        with self._database() as connection:
            connection.execute(
                """
                UPDATE inference_requests
                SET status = 'completed', completed_at = ?
                WHERE request_id = ? AND status IN ('queued', 'running')
                  AND cancel_requested = 0
                """,
                (_now(), request_id),
            )

    def fail(self, request_id: str, error_message: str) -> None:
        with self._database() as connection:
            connection.execute(
                """
                UPDATE inference_requests
                SET status = 'failed', completed_at = ?, error_message = ?
                WHERE request_id = ? AND status IN ('queued', 'running')
                """,
                (_now(), error_message[:1000], request_id),
            )

    def cancel(self, request_id: str) -> bool:
        with self._database() as connection:
            cursor = connection.execute(
                """
                UPDATE inference_requests
                SET cancel_requested = 1,
                    status = CASE WHEN status = 'queued' THEN 'failed' ELSE status END,
                    completed_at = CASE WHEN status = 'queued' THEN ? ELSE completed_at END,
                    error_message = CASE WHEN status = 'queued' THEN 'Cerere anulată.' ELSE error_message END
                WHERE request_id = ? AND status IN ('queued', 'running')
                """,
                (_now(), request_id),
            )
            return cursor.rowcount > 0

    def is_cancel_requested(self, request_id: str) -> bool:
        with self._database() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM inference_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return bool(row and row["cancel_requested"])

    def get_request(self, request_id: str) -> dict | None:
        with self._database() as connection:
            row = connection.execute(
                "SELECT * FROM inference_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if row is None:
                return None
            item = dict(row)
            if item["status"] == "queued" and item.get("ready_at"):
                item["position"] = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM inference_requests
                    WHERE status = 'queued' AND ready_at IS NOT NULL
                      AND (ready_at < ? OR (ready_at = ? AND created_at <= ?))
                    """,
                    (item["ready_at"], item["ready_at"], item["created_at"]),
                ).fetchone()[0]
            else:
                item["position"] = 0
        item["cancel_requested"] = bool(item["cancel_requested"])
        return item

    def diagnostics(self) -> dict:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(
            timespec="seconds"
        )
        with self._database() as connection:
            self._cleanup_stale_running(connection)
            self._cleanup_abandoned_queued(connection)
            active_users = connection.execute(
                """
                SELECT COUNT(DISTINCT user_session_id)
                FROM inference_requests
                WHERE created_at >= ?
                """,
                (cutoff,),
            ).fetchone()[0]
            queued = connection.execute(
                """
                SELECT COUNT(*) FROM inference_requests
                WHERE status = 'queued' AND ready_at IS NOT NULL
                """
            ).fetchone()[0]
            running = connection.execute(
                "SELECT COUNT(*) FROM inference_requests WHERE status = 'running'"
            ).fetchone()[0]
            average = connection.execute(
                """
                SELECT AVG((julianday(completed_at) - julianday(started_at)) * 86400.0)
                FROM inference_requests
                WHERE status = 'completed' AND started_at IS NOT NULL
                  AND completed_at IS NOT NULL
                """
            ).fetchone()[0]
        return {
            "active_users": int(active_users or 0),
            "queued_requests": int(queued or 0),
            "running_requests": int(running or 0),
            "average_response_seconds": round(float(average or 0.0), 1),
            "max_concurrent_generations": self.get_max_concurrent(),
        }


class QueuedInferenceRequest:
    def __init__(
        self,
        queue: InferenceRequestQueue,
        request_id: str,
        callback: QueueCallback | None = None,
    ):
        self.queue = queue
        self.request_id = request_id
        self.callback = callback
        self.acquired = False

    def acquire(self, timeout_seconds: float | None = None) -> None:
        if self.acquired:
            self.raise_if_cancelled()
            return
        timeout = timeout_seconds or float(
            os.environ.get(
                "FACULTY_COPILOT_QUEUE_TIMEOUT",
                DEFAULT_QUEUE_TIMEOUT_SECONDS,
            )
        )
        started_waiting = time.monotonic()
        previous_position = None
        while True:
            acquired, position = self.queue.try_acquire(self.request_id)
            if acquired:
                self.acquired = True
                if self.callback is not None:
                    self.callback("running", 0, self.request_id)
                return
            if self.callback is not None and position != previous_position:
                self.callback("queued", position, self.request_id)
                previous_position = position
            if time.monotonic() - started_waiting >= timeout:
                message = (
                    "Timpul maxim de așteptare în coada AI a fost depășit. "
                    "Încearcă din nou când serverul este mai liber."
                )
                self.queue.fail(self.request_id, message)
                raise QueueWaitTimeoutError(message)
            time.sleep(0.25)

    def raise_if_cancelled(self) -> None:
        if self.queue.is_cancel_requested(self.request_id):
            raise RequestCancelledError("Cererea a fost anulată.")

    def status(self) -> dict | None:
        return self.queue.get_request(self.request_id)
