from __future__ import annotations

import json
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


VALID_WEAK_STATUSES = {"greu", "neclar", "de repetat"}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _json_dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_load(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(without_accents.lower().split())


def _tokens(text: str) -> set[str]:
    return {token for token in _normalize(text).split() if len(token) >= 3}


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS study_sessions (
            session_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            last_activity TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS study_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            question TEXT NOT NULL,
            selected_document TEXT,
            retrieved_documents TEXT NOT NULL DEFAULT '[]',
            topic TEXT,
            answer_summary TEXT,
            sources TEXT NOT NULL DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS weak_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            study_history_id INTEGER,
            topic TEXT NOT NULL,
            document_name TEXT,
            status TEXT NOT NULL,
            question TEXT,
            UNIQUE(study_history_id, status),
            FOREIGN KEY(study_history_id) REFERENCES study_history(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            quiz_session_id TEXT NOT NULL,
            question TEXT NOT NULL,
            selected_answer TEXT,
            correct_answer TEXT NOT NULL,
            score REAL NOT NULL,
            source_document TEXT,
            topic TEXT
        );

        CREATE TABLE IF NOT EXISTS user_preferences (
            preference_key TEXT PRIMARY KEY,
            preference_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS document_metadata (
            document_key TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            file_path TEXT,
            academic_year TEXT,
            subject TEXT,
            course TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS session_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            title TEXT NOT NULL,
            subject TEXT,
            exam_date TEXT,
            number_of_days INTEGER NOT NULL,
            hours_per_day REAL NOT NULL,
            difficulty_level TEXT NOT NULL,
            include_revision_days INTEGER NOT NULL DEFAULT 1,
            include_quiz_days INTEGER NOT NULL DEFAULT 1,
            selected_documents TEXT NOT NULL DEFAULT '[]',
            plan_days TEXT NOT NULL DEFAULT '[]',
            total_estimated_hours REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_history_created_at
            ON study_history(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_history_topic
            ON study_history(topic);
        CREATE INDEX IF NOT EXISTS idx_weak_topic
            ON weak_topics(topic);
        CREATE INDEX IF NOT EXISTS idx_quiz_created_at
            ON quiz_results(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_session_plans_created_at
            ON session_plans(created_at DESC);
        """
    )
    connection.commit()


def _connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    _create_schema(connection)
    return connection


@contextmanager
def _database(database_path: Path):
    connection = _connect(database_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path: Path) -> None:
    with _database(database_path):
        pass


def ensure_session(database_path: Path, session_id: str) -> None:
    timestamp = _now()
    with _database(database_path) as connection:
        connection.execute(
            """
            INSERT INTO study_sessions(session_id, started_at, last_activity)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET last_activity = excluded.last_activity
            """,
            (session_id, timestamp, timestamp),
        )


def record_study_history(
    database_path: Path,
    session_id: str,
    question: str,
    selected_document: str | None,
    retrieved_documents: list[str],
    topic: str,
    answer_summary: str,
    sources: list[dict],
) -> int:
    timestamp = _now()
    with _database(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO study_history(
                session_id, created_at, question, selected_document,
                retrieved_documents, topic, answer_summary, sources
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                timestamp,
                question,
                selected_document,
                _json_dump(retrieved_documents),
                topic,
                answer_summary,
                _json_dump(sources),
            ),
        )
        connection.execute(
            """
            INSERT INTO study_sessions(session_id, started_at, last_activity)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET last_activity = excluded.last_activity
            """,
            (session_id, timestamp, timestamp),
        )
        return int(cursor.lastrowid)


def mark_weak_topic(
    database_path: Path,
    study_history_id: int | None,
    topic: str,
    document_name: str | None,
    status: str,
    question: str,
) -> bool:
    if status not in VALID_WEAK_STATUSES:
        raise ValueError(f"Status necunoscut: {status}")

    with _database(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO weak_topics(
                created_at, study_history_id, topic, document_name, status, question
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (_now(), study_history_id, topic, document_name, status, question),
        )
        return cursor.rowcount > 0


def record_quiz_result(
    database_path: Path,
    session_id: str,
    quiz_session_id: str,
    question: str,
    selected_answer: str | None,
    correct_answer: str,
    is_correct: bool,
    source_document: str | None,
    topic: str,
) -> None:
    timestamp = _now()
    with _database(database_path) as connection:
        connection.execute(
            """
            INSERT INTO quiz_results(
                session_id, created_at, quiz_session_id, question,
                selected_answer, correct_answer, score, source_document, topic
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                timestamp,
                quiz_session_id,
                question,
                selected_answer,
                correct_answer,
                1.0 if is_correct else 0.0,
                source_document,
                topic,
            ),
        )
        connection.execute(
            """
            INSERT INTO study_sessions(session_id, started_at, last_activity)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET last_activity = excluded.last_activity
            """,
            (session_id, timestamp, timestamp),
        )


def get_preference(
    database_path: Path,
    preference_key: str,
    default: str | None = None,
) -> str | None:
    with _database(database_path) as connection:
        row = connection.execute(
            """
            SELECT preference_value
            FROM user_preferences
            WHERE preference_key = ?
            """,
            (preference_key,),
        ).fetchone()
    return row["preference_value"] if row else default


def set_preference(database_path: Path, preference_key: str, preference_value: str) -> None:
    with _database(database_path) as connection:
        connection.execute(
            """
            INSERT INTO user_preferences(preference_key, preference_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(preference_key) DO UPDATE SET
                preference_value = excluded.preference_value,
                updated_at = excluded.updated_at
            """,
            (preference_key, preference_value, _now()),
        )


def upsert_document_metadata(
    database_path: Path,
    document_key: str,
    file_name: str,
    file_path: str | None,
    academic_year: str | None,
    subject: str | None,
    course: str | None,
) -> None:
    with _database(database_path) as connection:
        connection.execute(
            """
            INSERT INTO document_metadata(
                document_key, file_name, file_path, academic_year,
                subject, course, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_key) DO UPDATE SET
                file_name = excluded.file_name,
                file_path = excluded.file_path,
                academic_year = excluded.academic_year,
                subject = excluded.subject,
                course = excluded.course,
                updated_at = excluded.updated_at
            """,
            (
                document_key,
                file_name,
                file_path,
                academic_year,
                subject,
                course,
                _now(),
            ),
        )


def get_document_metadata_map(database_path: Path) -> dict[str, dict]:
    with _database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT document_key, file_name, file_path, academic_year,
                   subject, course, updated_at
            FROM document_metadata
            """
        ).fetchall()
    return {row["document_key"]: dict(row) for row in rows}


def get_weak_topics(database_path: Path, limit: int = 50) -> list[dict]:
    with _database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT id, created_at, study_history_id, topic, document_name, status, question
            FROM weak_topics
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_recent_questions(database_path: Path, limit: int = 20) -> list[dict]:
    with _database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT id, created_at, question, selected_document, retrieved_documents,
                   topic, answer_summary, sources
            FROM study_history
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        item["retrieved_documents"] = _json_load(item["retrieved_documents"], [])
        item["sources"] = _json_load(item["sources"], [])
        results.append(item)
    return results


def get_quiz_results(database_path: Path, limit: int = 30) -> list[dict]:
    with _database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT id, created_at, quiz_session_id, question, selected_answer,
                   correct_answer, score, source_document, topic
            FROM quiz_results
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_studied_documents(database_path: Path) -> list[dict]:
    document_counts: dict[str, int] = {}
    with _database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT selected_document, retrieved_documents
            FROM study_history
            ORDER BY created_at DESC
            """
        ).fetchall()
        quiz_rows = connection.execute(
            """
            SELECT source_document
            FROM quiz_results
            WHERE source_document IS NOT NULL AND source_document != ''
            """
        ).fetchall()

    for row in rows:
        names = _json_load(row["retrieved_documents"], [])
        if row["selected_document"]:
            names.append(row["selected_document"])
        for name in set(names):
            if name:
                document_counts[name] = document_counts.get(name, 0) + 1

    for row in quiz_rows:
        name = row["source_document"]
        if name:
            document_counts[name] = document_counts.get(name, 0) + 1

    return [
        {"document": name, "interactions": count}
        for name, count in sorted(
            document_counts.items(),
            key=lambda item: (-item[1], item[0].lower()),
        )
    ]


def get_last_studied_documents(database_path: Path, limit: int = 5) -> list[dict]:
    seen = set()
    documents = []
    for item in get_recent_questions(database_path, limit=80):
        names = []
        if item.get("selected_document"):
            names.append(item["selected_document"])
        names.extend(item.get("retrieved_documents") or [])
        for name in names:
            normalized = _normalize(name)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            documents.append(
                {
                    "document": name,
                    "last_activity": item["created_at"],
                    "topic": item.get("topic") or "-",
                }
            )
            if len(documents) >= limit:
                return documents
    return documents


def get_recent_sessions(database_path: Path, limit: int = 5) -> list[dict]:
    with _database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                sessions.session_id,
                sessions.started_at,
                sessions.last_activity,
                (
                    SELECT COUNT(*)
                    FROM study_history history
                    WHERE history.session_id = sessions.session_id
                ) AS questions,
                (
                    SELECT COUNT(*)
                    FROM quiz_results quiz
                    WHERE quiz.session_id = sessions.session_id
                ) AS quiz_answers
            FROM study_sessions sessions
            WHERE EXISTS (
                SELECT 1
                FROM study_history history
                WHERE history.session_id = sessions.session_id
            )
            OR EXISTS (
                SELECT 1
                FROM quiz_results quiz
                WHERE quiz.session_id = sessions.session_id
            )
            ORDER BY sessions.last_activity DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_study_streak(database_path: Path) -> int:
    with _database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT created_at FROM study_history
            UNION ALL
            SELECT created_at FROM quiz_results
            UNION ALL
            SELECT created_at FROM session_plans
            """
        ).fetchall()

    study_days = set()
    for row in rows:
        try:
            study_days.add(datetime.fromisoformat(row["created_at"]).date())
        except (TypeError, ValueError):
            continue

    today = datetime.now().astimezone().date()
    streak = 0
    current_day = today
    while current_day in study_days:
        streak += 1
        current_day = current_day.fromordinal(current_day.toordinal() - 1)
    return streak


def get_dashboard_summary(database_path: Path) -> dict:
    with _database(database_path) as connection:
        total_questions = connection.execute(
            "SELECT COUNT(*) FROM study_history"
        ).fetchone()[0]
        weak_topics = connection.execute(
            "SELECT COUNT(DISTINCT lower(topic)) FROM weak_topics"
        ).fetchone()[0]
        quiz_average = connection.execute(
            "SELECT AVG(score) FROM quiz_results"
        ).fetchone()[0]
        saved_plans = connection.execute(
            "SELECT COUNT(*) FROM session_plans"
        ).fetchone()[0]

    return {
        "total_questions": int(total_questions or 0),
        "documents_studied": len(get_studied_documents(database_path)),
        "weak_topics": int(weak_topics or 0),
        "quiz_average": None if quiz_average is None else float(quiz_average) * 100,
        "recent_sessions": get_recent_sessions(database_path, limit=5),
        "last_studied_documents": get_last_studied_documents(database_path, limit=5),
        "study_streak": get_study_streak(database_path),
        "saved_plans": int(saved_plans or 0),
    }


def get_relevant_memory(
    database_path: Path,
    question: str,
    topic: str,
    document_name: str | None,
    limit: int = 5,
) -> dict:
    question_tokens = _tokens(f"{question} {topic}")
    normalized_document = _normalize(document_name or "")

    weak_candidates = get_weak_topics(database_path, limit=100)
    weak_scored = []
    for item in weak_candidates:
        item_tokens = _tokens(f"{item.get('topic', '')} {item.get('question', '')}")
        score = len(question_tokens & item_tokens)
        if normalized_document and _normalize(item.get("document_name") or "") == normalized_document:
            score += 4
        if score:
            weak_scored.append((score, item))

    history_candidates = get_recent_questions(database_path, limit=100)
    history_scored = []
    for item in history_candidates:
        item_tokens = _tokens(f"{item.get('topic', '')} {item.get('question', '')}")
        score = len(question_tokens & item_tokens)
        studied_documents = item.get("retrieved_documents") or []
        if item.get("selected_document"):
            studied_documents.append(item["selected_document"])
        if normalized_document and any(
            _normalize(name) == normalized_document for name in studied_documents
        ):
            score += 4
        if score:
            history_scored.append((score, item))

    weak_scored.sort(key=lambda value: (value[0], value[1]["created_at"]), reverse=True)
    history_scored.sort(key=lambda value: (value[0], value[1]["created_at"]), reverse=True)
    return {
        "weak_topics": [item for _, item in weak_scored[:limit]],
        "previous_questions": [item for _, item in history_scored[:limit]],
    }


def get_recommended_topics(database_path: Path, limit: int = 8) -> list[dict]:
    scores: dict[str, dict] = {}
    status_weights = {"de repetat": 3, "neclar": 2, "greu": 2}

    for item in get_weak_topics(database_path, limit=200):
        topic = (item.get("topic") or "").strip()
        if not topic:
            continue
        key = _normalize(topic)
        entry = scores.setdefault(
            key,
            {"topic": topic, "priority": 0, "reasons": set()},
        )
        entry["priority"] += status_weights.get(item.get("status"), 1)
        entry["reasons"].add(item.get("status") or "subiect slab")

    for item in get_quiz_results(database_path, limit=300):
        if item.get("score", 0) >= 1:
            continue
        topic = (item.get("topic") or "").strip()
        if not topic:
            continue
        key = _normalize(topic)
        entry = scores.setdefault(
            key,
            {"topic": topic, "priority": 0, "reasons": set()},
        )
        entry["priority"] += 2
        entry["reasons"].add("raspuns gresit la quiz")

    recommendations = sorted(
        scores.values(),
        key=lambda item: (-item["priority"], item["topic"].lower()),
    )
    for item in recommendations:
        item["reasons"] = ", ".join(sorted(item["reasons"]))
    return recommendations[:limit]


def save_session_plan(
    database_path: Path,
    title: str,
    subject: str,
    exam_date: str | None,
    number_of_days: int,
    hours_per_day: float,
    difficulty_level: str,
    include_revision_days: bool,
    include_quiz_days: bool,
    selected_documents: list[dict],
    plan_days: list[dict],
    total_estimated_hours: float,
) -> int:
    timestamp = _now()
    with _database(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO session_plans(
                created_at, title, subject, exam_date, number_of_days,
                hours_per_day, difficulty_level, include_revision_days,
                include_quiz_days, selected_documents, plan_days,
                total_estimated_hours
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                title,
                subject,
                exam_date,
                number_of_days,
                hours_per_day,
                difficulty_level,
                1 if include_revision_days else 0,
                1 if include_quiz_days else 0,
                _json_dump(selected_documents),
                _json_dump(plan_days),
                total_estimated_hours,
            ),
        )
        return int(cursor.lastrowid)


def get_session_plans(database_path: Path, limit: int = 20) -> list[dict]:
    with _database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT id, created_at, title, subject, exam_date, number_of_days,
                   hours_per_day, difficulty_level, include_revision_days,
                   include_quiz_days, selected_documents, plan_days,
                   total_estimated_hours
            FROM session_plans
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    plans = []
    for row in rows:
        item = dict(row)
        item["include_revision_days"] = bool(item["include_revision_days"])
        item["include_quiz_days"] = bool(item["include_quiz_days"])
        item["selected_documents"] = _json_load(item["selected_documents"], [])
        item["plan_days"] = _json_load(item["plan_days"], [])
        plans.append(item)
    return plans


def get_session_plan(database_path: Path, plan_id: int) -> dict | None:
    with _database(database_path) as connection:
        row = connection.execute(
            """
            SELECT id, created_at, title, subject, exam_date, number_of_days,
                   hours_per_day, difficulty_level, include_revision_days,
                   include_quiz_days, selected_documents, plan_days,
                   total_estimated_hours
            FROM session_plans
            WHERE id = ?
            """,
            (plan_id,),
        ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["include_revision_days"] = bool(item["include_revision_days"])
    item["include_quiz_days"] = bool(item["include_quiz_days"])
    item["selected_documents"] = _json_load(item["selected_documents"], [])
    item["plan_days"] = _json_load(item["plan_days"], [])
    return item
