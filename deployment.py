from __future__ import annotations

import os
import sqlite3
import subprocess
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


DEPLOYMENT_MODES = ("Local", "LAN", "Tailscale", "Public Internet")
_MODE_ALIASES = {
    "local": "Local",
    "lan": "LAN",
    "tailscale": "Tailscale",
    "public": "Public Internet",
    "public internet": "Public Internet",
    "public_internet": "Public Internet",
}


def environment_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def normalize_deployment_mode(value: str) -> str:
    normalized = _MODE_ALIASES.get((value or "").strip().lower())
    if normalized is None:
        raise ValueError(
            "Modul de deployment trebuie să fie Local, LAN, Tailscale sau Public Internet."
        )
    return normalized


def configured_https_url(environment_name: str) -> str | None:
    raw_url = os.environ.get(environment_name, "").strip()
    if not raw_url:
        return None
    parsed = urlsplit(raw_url)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return None
    return urlunsplit(("https", parsed.netloc, "", "", ""))


def configured_public_url() -> str | None:
    configured = os.environ.get("FACULTY_COPILOT_PUBLIC_URL", "").strip()
    if configured:
        return configured_https_url("FACULTY_COPILOT_PUBLIC_URL")

    # Public launchers can discover a temporary URL only after the app process
    # has started.  A small runtime file lets Server Status pick it up without
    # restarting Streamlit.  The directory is gitignored and contains no tunnel
    # credentials.
    runtime_file = Path(
        os.environ.get(
            "FACULTY_COPILOT_PUBLIC_URL_FILE",
            str(
                Path(__file__).resolve().parent
                / "storage"
                / "runtime"
                / "public_url.txt"
            ),
        )
    )
    try:
        runtime_url = runtime_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    parsed = urlsplit(runtime_url)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return None
    return urlunsplit(("https", parsed.netloc, "", "", ""))


def configured_public_api_url() -> str | None:
    return configured_https_url("FACULTY_COPILOT_PUBLIC_API_URL")


def get_deployment_mode(server_mode: bool | None = None) -> str:
    configured = os.environ.get("FACULTY_COPILOT_DEPLOYMENT_MODE", "").strip()
    if configured:
        try:
            return normalize_deployment_mode(configured)
        except ValueError:
            return "LAN" if server_mode else "Local"
    if configured_public_url():
        return "Public Internet"
    if server_mode is None:
        server_mode = os.environ.get("AI_STUDY_SERVER_MODE") == "1"
    return "LAN" if server_mode else "Local"


def build_server_urls(
    port: int,
    lan_ip: str | None,
    tailscale_ip: str | None,
    *,
    server_mode: bool,
) -> dict[str, str | bool | None]:
    public_url = configured_public_url()
    return {
        "local": f"http://localhost:{port}",
        "lan": f"http://{lan_ip}:{port}" if server_mode and lan_ip else None,
        "tailscale": (
            f"http://{tailscale_ip}:{port}"
            if server_mode and tailscale_ip
            else None
        ),
        "public": public_url,
        "https": bool(public_url),
        "deployment_mode": get_deployment_mode(server_mode),
        "server_mode": server_mode,
    }


def get_gpu_status() -> dict[str, object]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return {"available": False}
    if result.returncode != 0 or not result.stdout.strip():
        return {"available": False}

    values = [part.strip() for part in result.stdout.splitlines()[0].split(",")]
    if len(values) != 5:
        return {"available": False}
    try:
        return {
            "available": True,
            "name": values[0],
            "utilization_percent": int(values[1]),
            "memory_used_mb": int(values[2]),
            "memory_total_mb": int(values[3]),
            "temperature_c": int(values[4]),
        }
    except ValueError:
        return {"available": False}


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = max(1, int(limit))
        self.window_seconds = max(1, int(window_seconds))
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, cost: int = 1) -> bool:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] > self.window_seconds:
                events.popleft()
            if len(events) + cost > self.limit:
                return False
            events.extend([now] * max(1, cost))
            return True


class ActiveSessionTracker:
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._database() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS active_sessions (
                    session_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    client_type TEXT NOT NULL,
                    last_seen REAL NOT NULL
                )
                """
            )

    @contextmanager
    def _database(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def heartbeat(self, session_id: str, username: str, client_type: str) -> None:
        if not session_id:
            return
        with self._database() as connection:
            ttl = environment_int(
                "FACULTY_COPILOT_ACTIVE_SESSION_TTL_SECONDS", 900, 60, 86400
            )
            connection.execute(
                "DELETE FROM active_sessions WHERE last_seen < ?",
                (time.time() - (ttl * 2),),
            )
            connection.execute(
                """
                INSERT INTO active_sessions(session_id, username, client_type, last_seen)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    username = excluded.username,
                    client_type = excluded.client_type,
                    last_seen = excluded.last_seen
                """,
                (session_id[:128], username[:64], client_type[:32], time.time()),
            )

    def diagnostics(self, ttl_seconds: int | None = None) -> dict[str, int]:
        ttl = ttl_seconds or environment_int(
            "FACULTY_COPILOT_ACTIVE_SESSION_TTL_SECONDS", 900, 60, 86400
        )
        cutoff = time.time() - ttl
        with self._database() as connection:
            connection.execute(
                "DELETE FROM active_sessions WHERE last_seen < ?", (cutoff - ttl,)
            )
            connected_sessions, distinct_users = connection.execute(
                """
                SELECT COUNT(*), COUNT(DISTINCT username)
                FROM active_sessions WHERE last_seen >= ?
                """,
                (cutoff,),
            ).fetchone()
        return {
            "connected_users": int(connected_sessions or 0),
            "distinct_workspaces": int(distinct_users or 0),
            "ttl_seconds": ttl,
        }
