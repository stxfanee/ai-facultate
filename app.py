from __future__ import annotations

import copy
import contextvars
import base64
import hashlib
import html
import io
import json
import math
import os
import re
import socket
import subprocess
import threading
import time
import unicodedata
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import chromadb
import httpx
import ollama
import streamlit as st
import streamlit.components.v1 as components
from pypdf import PdfReader
from llama_index.core import Settings, SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.storage.storage_context import StorageContext
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore
from deployment import (
    ActiveSessionTracker,
    SlidingWindowRateLimiter,
    build_server_urls,
    configured_public_api_url,
    environment_int,
    get_gpu_status,
)
from request_queue import (
    InferenceRequestQueue,
    QueueWaitTimeoutError,
    RequestCancelledError,
)
from study_memory import (
    NOTEBOOK_CATEGORIES,
    add_conversation_message,
    add_notebook_entry,
    create_conversation,
    delete_all_document_metadata,
    delete_conversation,
    delete_document_metadata,
    delete_notebook_entry,
    edit_conversation_message,
    get_dashboard_summary,
    get_conversation,
    get_document_metadata_map,
    get_flashcard_history,
    get_last_studied_documents,
    get_notebook_entries,
    list_conversations,
    get_preference,
    get_quiz_results,
    get_recent_questions,
    get_recent_sessions,
    get_recommended_topics,
    get_session_plans,
    get_relevant_memory,
    get_studied_documents,
    get_weak_topics,
    initialize_database,
    mark_weak_topic,
    move_conversation,
    record_quiz_result,
    record_flashcard_set,
    record_study_history,
    rename_conversation,
    save_session_plan,
    set_conversation_pinned,
    set_preference,
    update_conversation_metadata,
    update_notebook_entry,
    upsert_document_metadata,
)
from user_accounts import (
    ACTIVE_USERNAME,
    ACTIVE_WORKSPACE,
    DynamicUserMemoryPath,
    UserAccountStore,
    authentication_enabled,
    default_username,
    normalize_username,
    normalize_workspace_name,
    user_context,
    workspace_context,
)

try:
    import fitz
except ImportError:  # Optional PDF thumbnails/OCR rendering.
    fitz = None

try:
    import pytesseract
    from PIL import Image
except ImportError:  # OCR remains optional when native PDF text is unavailable.
    pytesseract = None
    Image = None


# Product name is intentionally stable; do not version or rename it in the UI.
APP_TITLE = "Co-pilot Facultate"
PROJECT_ROOT = Path(__file__).resolve().parent
DOCUMENTS_DIR = PROJECT_ROOT / "documents"
STORAGE_DIR = PROJECT_ROOT / "storage"
CHROMA_DIR = STORAGE_DIR / "chroma"
MEMORY_DIR = STORAGE_DIR / "memory"
LOCAL_MEMORY_DB_PATH = MEMORY_DIR / "study_memory.sqlite3"
USER_ACCOUNTS = UserAccountStore(STORAGE_DIR)
MEMORY_DB_PATH = DynamicUserMemoryPath(USER_ACCOUNTS, LOCAL_MEMORY_DB_PATH)
INFERENCE_QUEUE = InferenceRequestQueue(LOCAL_MEMORY_DB_PATH)
SERVER_CONNECTIONS = ActiveSessionTracker(STORAGE_DIR / "server_status.sqlite3")
STREAMLIT_ACTION_RATE_LIMITER = SlidingWindowRateLimiter(
    environment_int("FACULTY_COPILOT_STREAMLIT_ACTION_RATE_LIMIT", 20, 5, 1000)
)
STREAMLIT_ACTION_CAPACITY = threading.BoundedSemaphore(
    environment_int("FACULTY_COPILOT_MAX_CONCURRENT_UI_ACTIONS", 8, 1, 64)
)
DEFAULT_COLLECTION_NAME = "study_documents_v2"
ACTIVE_COLLECTION_FILE = STORAGE_DIR / "active_collection.txt"
DEFAULT_LLM_MODEL = "qwen3:8b"
SMARTER_MODEL = "qwen3:14b"
EMBED_MODEL = "nomic-embed-text"
OLLAMA_URL = "http://localhost:11434"
DEFAULT_SERVER_PORT = 8501
SUPPORTED_EXTS = {".pdf", ".docx", ".pptx"}
INVENTORY_KEYWORDS = ("indexat", "indexate", "incarcat", "incarcate")
MIN_RETRIEVAL_TOP_K = 5
RETRIEVAL_CACHE_MAX_ENTRIES = 128
OLLAMA_MODELS_CACHE_TTL = 10.0
OLLAMA_MODELS_CACHE: tuple[float, list[str]] = (0.0, [])
OLLAMA_MODELS_CACHE_LOCK = threading.Lock()
ACADEMIC_YEAR_OPTIONS = ["Nespecificat", "Anul 1", "Anul 2", "Anul 3", "Anul 4", "Master"]
DIFFICULTY_FACTORS = {"low": 0.85, "medium": 1.0, "high": 1.25}
STOPWORDS = {
    "a",
    "ai",
    "al",
    "ale",
    "am",
    "are",
    "asta",
    "ca",
    "care",
    "ce",
    "cu",
    "cum",
    "de",
    "despre",
    "din",
    "e",
    "este",
    "explica",
    "in",
    "la",
    "o",
    "pe",
    "pentru",
    "rezumat",
    "sa",
    "se",
    "si",
    "sunt",
    "un",
}


@dataclass(frozen=True)
class ResponseProfile:
    name: str
    top_k: int
    candidate_top_k: int
    max_context_chars: int
    request_timeout: float
    max_output_tokens: int
    answer_instruction: str
    memory_items: int
    comparison_chunks_per_course: int
    comparison_answer_tokens: int


RESPONSE_PROFILES = {
    "Fast": ResponseProfile(
        name="Fast",
        top_k=5,
        candidate_top_k=12,
        max_context_chars=9000,
        request_timeout=180.0,
        max_output_tokens=850,
        answer_instruction=(
            "Raspunde concis, direct si bine structurat. Evita repetitiile. "
            "Pastreaza definitiile si concluziile esentiale si citeaza sursele cheie."
        ),
        memory_items=2,
        comparison_chunks_per_course=2,
        comparison_answer_tokens=700,
    ),
    "Balanced": ResponseProfile(
        name="Balanced",
        top_k=9,
        candidate_top_k=22,
        max_context_chars=17000,
        request_timeout=180.0,
        max_output_tokens=1500,
        answer_instruction=(
            "Ofera un raspuns clar si suficient de detaliat, fara repetitii. "
            "Citeaza documentul si pagina pentru afirmatiile importante."
        ),
        memory_items=4,
        comparison_chunks_per_course=4,
        comparison_answer_tokens=1200,
    ),
    "Accurate": ResponseProfile(
        name="Accurate",
        top_k=14,
        candidate_top_k=36,
        max_context_chars=28000,
        request_timeout=300.0,
        max_output_tokens=2400,
        answer_instruction=(
            "Ofera un raspuns riguros si complet. Verifica ideile intre fragmente, "
            "semnaleaza diferentele si citeaza documentul si pagina pentru fiecare "
            "sectiune sau afirmatie importanta."
        ),
        memory_items=5,
        comparison_chunks_per_course=8,
        comparison_answer_tokens=2000,
    ),
}
DEFAULT_RESPONSE_MODE = "Balanced"
ANSWER_MODE_OPTIONS = [
    "Auto",
    "Strict",
    "Analiză",
    "Profesor",
    "Strategie de învățare",
]
DEFAULT_ANSWER_MODE = "Auto"
KNOWLEDGE_MODE_OPTIONS = [
    "Documents only",
    "Hybrid (recommended)",
    "General knowledge only",
]
DEFAULT_KNOWLEDGE_MODE = "Hybrid (recommended)"
MODEL_PROFILE_KEYS = {
    "rag": "model_profile_rag",
    "general": "model_profile_general",
    "reasoning": "model_profile_reasoning",
    "fast": "model_profile_fast",
}
MODEL_OVERRIDE_CONTEXT: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "faculty_copilot_model_override",
    default=None,
)
REASONING_INSTRUCTION_CONTEXT: contextvars.ContextVar[str] = contextvars.ContextVar(
    "faculty_copilot_reasoning_instruction",
    default="",
)
QUESTION_WORKFLOW_MODES = [
    "Întrebare normală",
    "Compară cursuri",
    "Rezumat document",
    "Caută în document specific",
]
RETRIEVAL_CACHE: OrderedDict[tuple, tuple[list[dict], dict]] = OrderedDict()
RETRIEVAL_CACHE_LOCK = threading.Lock()
COURSE_SUMMARY_CACHE: OrderedDict[tuple, dict] = OrderedDict()
COURSE_SUMMARY_CACHE_LOCK = threading.Lock()
COURSE_SUMMARY_CACHE_MAX_ENTRIES = 128


class StudyResponse:
    def __init__(self, text: str, chunks: list[dict], debug: dict):
        self.text = text
        self.chunks = chunks
        self.debug = debug
        self.source_nodes = []

    def __str__(self) -> str:
        return self.text


@dataclass(frozen=True)
class IntentDecision:
    intent: str
    confidence: float
    reason: str
    explicit_general: bool = False


@dataclass(frozen=True)
class ReasoningPlan:
    """High-level execution plan. It never contains private chain-of-thought."""

    intent: str
    user_goal: str
    answer_mode: str
    claim_type: str
    inference_level: str
    needs_documents: bool
    needs_cross_document_reasoning: bool
    tools: tuple[str, ...]
    context_required: bool
    instruction: str


@dataclass(frozen=True)
class ModelRoute:
    model: str
    profile: str
    reason: str
    answer_mode: str


class GenerationTimeoutError(RuntimeError):
    pass


def get_response_profile(mode: str | None = None) -> ResponseProfile:
    return RESPONSE_PROFILES.get(
        mode or DEFAULT_RESPONSE_MODE,
        RESPONSE_PROFILES[DEFAULT_RESPONSE_MODE],
    )


def ollama_context_window(response_mode: str) -> int:
    return {
        "Fast": 4096,
        "Balanced": 8192,
        "Accurate": 12288,
    }.get(response_mode, 8192)


def clear_retrieval_cache() -> None:
    with RETRIEVAL_CACHE_LOCK:
        RETRIEVAL_CACHE.clear()
    with COURSE_SUMMARY_CACHE_LOCK:
        COURSE_SUMMARY_CACHE.clear()


def ensure_project_dirs() -> None:
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if ACTIVE_USERNAME.get() != "local":
        USER_ACCOUNTS.workspace()
    initialize_database(MEMORY_DB_PATH)


def current_username() -> str:
    return ACTIVE_USERNAME.get()


def current_workspace_slug() -> str:
    return ACTIVE_WORKSPACE.get()


def current_documents_dir() -> Path:
    if current_username() == "local":
        return DOCUMENTS_DIR
    return USER_ACCOUNTS.workspace().documents


def current_memory_db_path() -> Path:
    return Path(os.fspath(MEMORY_DB_PATH))


def current_active_collection_file() -> Path:
    if current_username() == "local":
        return ACTIVE_COLLECTION_FILE
    return USER_ACCOUNTS.workspace().active_collection_file


def user_collection_prefix(
    username: str | None = None,
    workspace_slug: str | None = None,
) -> str:
    username = username or current_username()
    if username == "local":
        return DEFAULT_COLLECTION_NAME
    user_hash = hashlib.sha256(username.encode("utf-8")).hexdigest()[:16]
    base = f"{DEFAULT_COLLECTION_NAME}_user_{user_hash}"
    workspace_slug = workspace_slug or current_workspace_slug()
    if workspace_slug == "general":
        return base
    workspace_hash = hashlib.sha256(workspace_slug.encode("utf-8")).hexdigest()[:12]
    return f"{base}_workspace_{workspace_hash}"


def collection_belongs_to_user(
    name: str,
    username: str | None = None,
    workspace_slug: str | None = None,
) -> bool:
    username = username or current_username()
    if username == "local":
        return name == DEFAULT_COLLECTION_NAME or (
            name.startswith(f"{DEFAULT_COLLECTION_NAME}_")
            and not name.startswith(f"{DEFAULT_COLLECTION_NAME}_user_")
        )
    selected_workspace = workspace_slug or current_workspace_slug()
    prefix = user_collection_prefix(username, selected_workspace)
    if selected_workspace == "general":
        return (
            name == prefix
            or (
                name.startswith(f"{prefix}_")
                and not name.startswith(f"{prefix}_workspace_")
            )
        )
    return name == prefix or name.startswith(f"{prefix}_")


def path_is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def is_current_user_document_path(path: Path) -> bool:
    if current_username() == "local":
        return True
    return path_is_inside(path, current_documents_dir())


def safe_document_filename(name: str) -> str:
    safe_name = Path(name or "").name.strip()
    if not safe_name:
        raise ValueError("Numele documentului nu poate fi gol.")
    if Path(safe_name).suffix.lower() not in SUPPORTED_EXTS:
        raise ValueError("Documentele acceptate sunt PDF, DOCX sau PPTX.")
    return safe_name


def normalize_document_record(document: dict) -> dict | None:
    file_path = document.get("file_path")
    if not file_path:
        return None
    path = Path(file_path).resolve()
    if not is_current_user_document_path(path):
        return None
    normalized = dict(document)
    normalized["file_path"] = str(path)
    normalized["file_name"] = path.name
    return normalized


def normalize_document_selection(documents: list[dict] | None) -> list[dict]:
    selected: list[dict] = []
    for document in documents or []:
        normalized = normalize_document_record(document)
        if normalized is not None:
            selected.append(normalized)
    return selected


def current_server_port() -> int:
    raw_port = os.environ.get("AI_STUDY_SERVER_PORT", str(DEFAULT_SERVER_PORT))
    try:
        return int(raw_port)
    except ValueError:
        return DEFAULT_SERVER_PORT


def get_lan_ip() -> str | None:
    connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        connection.connect(("10.255.255.255", 1))
        return connection.getsockname()[0]
    except OSError:
        try:
            address = socket.gethostbyname(socket.gethostname())
            return address if not address.startswith("127.") else None
        except OSError:
            return None
    finally:
        connection.close()


def get_tailscale_ip() -> str | None:
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    executables = ["tailscale", str(program_files / "Tailscale" / "tailscale.exe")]
    for executable in executables:
        try:
            result = subprocess.run(
                [executable, "ip", "-4"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue

        if result.returncode == 0:
            return next(
                (line.strip() for line in result.stdout.splitlines() if line.strip()),
                None,
            )
    return None


@st.cache_data(ttl=30, show_spinner=False)
def get_server_urls() -> dict[str, str | bool | None]:
    port = current_server_port()
    server_mode = os.environ.get("AI_STUDY_SERVER_MODE") == "1"
    lan_ip = get_lan_ip() if server_mode else None
    tailscale_ip = get_tailscale_ip() if server_mode else None
    return build_server_urls(
        port,
        lan_ip,
        tailscale_ip,
        server_mode=server_mode,
    )


@st.cache_data(ttl=5, show_spinner=False)
def cached_gpu_status() -> dict[str, object]:
    return get_gpu_status()


def streamlit_client_key() -> str:
    headers: dict[str, str] = {}
    try:
        from streamlit.web.server.websocket_headers import _get_websocket_headers

        headers = {
            str(key).lower(): str(value)
            for key, value in (_get_websocket_headers() or {}).items()
        }
    except (ImportError, RuntimeError, AttributeError):
        pass
    candidate = headers.get("cf-connecting-ip") or headers.get(
        "x-forwarded-for", ""
    ).split(",", 1)[0].strip()
    if candidate:
        digest = hashlib.sha256(candidate[:64].encode("utf-8")).hexdigest()[:24]
        return f"proxy-ip:{digest}"
    session_id = st.session_state.get("study_session_id")
    return f"session:{session_id or 'initializing'}"


def enforce_streamlit_action_limit(cost: int = 1) -> None:
    if not STREAMLIT_ACTION_RATE_LIMITER.allow(streamlit_client_key(), cost=cost):
        raise RuntimeError(
            "Prea multe acțiuni într-un minut. Așteaptă puțin și încearcă din nou."
        )


@contextmanager
def streamlit_action_slot():
    if not STREAMLIT_ACTION_CAPACITY.acquire(timeout=1.0):
        raise RuntimeError(
            "Serverul procesează prea multe acțiuni simultan. Încearcă din nou."
        )
    try:
        yield
    finally:
        STREAMLIT_ACTION_CAPACITY.release()


def configure_llama_index(
    model_name: str,
    response_mode: str = DEFAULT_RESPONSE_MODE,
) -> None:
    profile = get_response_profile(response_mode)
    Settings.llm = Ollama(
        model=model_name,
        request_timeout=profile.request_timeout,
        context_window=ollama_context_window(response_mode),
        additional_kwargs={
            "num_predict": profile.max_output_tokens,
            "num_ctx": ollama_context_window(response_mode),
        },
        thinking=False,
        keep_alive="15m",
    )
    Settings.embed_model = OllamaEmbedding(
        model_name=EMBED_MODEL,
        client_kwargs={"timeout": profile.request_timeout},
        keep_alive="15m",
    )
    Settings.chunk_size = 1000
    Settings.chunk_overlap = 160


def ollama_is_running() -> bool:
    try:
        response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2.0)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def list_ollama_models(force_refresh: bool = False) -> list[str]:
    global OLLAMA_MODELS_CACHE
    with OLLAMA_MODELS_CACHE_LOCK:
        cached_at, cached_models = OLLAMA_MODELS_CACHE
        if not force_refresh and time.monotonic() - cached_at < OLLAMA_MODELS_CACHE_TTL:
            return list(cached_models)
    try:
        response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError:
        return []

    models = sorted(
        model.get("name", "") for model in data.get("models", []) if model.get("name")
    )
    with OLLAMA_MODELS_CACHE_LOCK:
        OLLAMA_MODELS_CACHE = (time.monotonic(), models)
    return list(models)


def list_llm_models() -> list[str]:
    return [model for model in list_ollama_models() if "embed" not in model.lower()]


def _installed_match(installed_models: list[str], preferred: str) -> str | None:
    if preferred in installed_models:
        return preferred
    preferred_base = preferred.split(":", 1)[0].lower()
    return next(
        (
            model
            for model in installed_models
            if model.split(":", 1)[0].lower() == preferred_base
        ),
        None,
    )


def model_profile_status(installed_models: list[str] | None = None) -> dict[str, dict]:
    installed = installed_models if installed_models is not None else list_llm_models()
    fallback_any = installed[0] if installed else DEFAULT_LLM_MODEL
    suggested = {
        "rag": _installed_match(installed, "qwen3:8b")
        or _installed_match(installed, "qwen3:14b")
        or fallback_any,
        "general": _installed_match(installed, "gemma3:12b")
        or _installed_match(installed, "qwen3:14b")
        or _installed_match(installed, "qwen3:8b")
        or fallback_any,
        "reasoning": _installed_match(installed, "qwen3:14b")
        or _installed_match(installed, "qwen3:8b")
        or fallback_any,
        "fast": _installed_match(installed, "qwen3:8b") or fallback_any,
    }
    status = {}
    for profile_name, preference_key in MODEL_PROFILE_KEYS.items():
        configured = get_preference(MEMORY_DB_PATH, preference_key) or suggested[profile_name]
        resolved = _installed_match(installed, configured) if installed else configured
        missing = bool(installed and resolved is None)
        if resolved is None:
            resolved = suggested[profile_name]
        status[profile_name] = {
            "configured": configured,
            "resolved": resolved,
            "missing": missing,
            "suggested": suggested[profile_name],
        }
    return status


def get_model_profiles(installed_models: list[str] | None = None) -> dict[str, str]:
    return {
        profile_name: item["resolved"]
        for profile_name, item in model_profile_status(installed_models).items()
    }


@contextmanager
def model_override_context(model_name: str | None):
    token = MODEL_OVERRIDE_CONTEXT.set(model_name)
    try:
        yield
    finally:
        MODEL_OVERRIDE_CONTEXT.reset(token)


def select_model_for_mode(
    question: str,
    response_mode: str,
    answer_mode: str,
    knowledge_mode: str,
    stage: str,
    installed_models: list[str] | None = None,
) -> ModelRoute:
    installed = installed_models if installed_models is not None else list_llm_models()
    override = MODEL_OVERRIDE_CONTEXT.get()
    if override:
        resolved_override = _installed_match(installed, override) if installed else override
        if resolved_override:
            return ModelRoute(
                resolved_override,
                "override",
                "model specificat explicit de clientul API",
                resolve_answer_mode(answer_mode, question),
            )

    status = model_profile_status(installed)
    profiles = {name: item["resolved"] for name, item in status.items()}
    effective_answer_mode = resolve_answer_mode(answer_mode, question)

    if response_mode == "Fast":
        profile_name = "fast"
        reason = "profilul de viteză Fast are prioritate"
    elif response_mode == "Accurate":
        profile_name = "reasoning"
        reason = "profilul Accurate folosește cel mai puternic model configurat"
    elif stage == "general" or knowledge_mode == "General knowledge only":
        profile_name = "general"
        reason = "etapă de cunoștințe generale"
    elif stage == "synthesis" and effective_answer_mode != "Strict":
        profile_name = "reasoning"
        reason = "sinteza hibridă folosește modelul de reasoning"
    elif effective_answer_mode == "Strict":
        profile_name = "rag"
        reason = "modul Strict folosește modelul RAG conservator"
    elif effective_answer_mode in {"Analiză", "Profesor", "Strategie de învățare"}:
        profile_name = "reasoning"
        reason = f"modul {effective_answer_mode} necesită modelul de reasoning"
    elif stage == "rag" or knowledge_mode == "Documents only":
        profile_name = "rag"
        reason = "etapă bazată pe documente/RAG"
    elif stage == "synthesis":
        profile_name = "reasoning"
        reason = "sinteza hibridă folosește modelul de reasoning"
    else:
        profile_name = "rag"
        reason = "rutare implicită spre profilul RAG"

    profile_status = status[profile_name]
    if profile_status["missing"]:
        reason += (
            f"; modelul configurat {profile_status['configured']} lipsește, "
            f"fallback la {profile_status['resolved']}"
        )
    return ModelRoute(
        profiles[profile_name],
        profile_name,
        reason,
        effective_answer_mode,
    )


def pull_ollama_model(model_name: str) -> str:
    response = httpx.post(
        f"{OLLAMA_URL}/api/pull",
        json={"name": model_name, "stream": False},
        timeout=1800.0,
    )
    response.raise_for_status()
    return f"Modelul {model_name} este disponibil local."


def pick_folder_dialog() -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askdirectory(
        title="Alege folderul cu cursuri",
        initialdir=str(PROJECT_ROOT),
    )
    root.destroy()
    return selected


def pick_files_dialog() -> list[str]:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askopenfilenames(
        title="Alege fisierele de curs",
        initialdir=str(PROJECT_ROOT),
        filetypes=[
            ("Documente curs", "*.pdf *.docx *.pptx"),
            ("PDF", "*.pdf"),
            ("Word", "*.docx"),
            ("PowerPoint", "*.pptx"),
        ],
    )
    root.destroy()
    return list(selected)


def resolve_user_path(raw_path: str) -> Path:
    path = Path(raw_path.strip()).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def get_chroma_client() -> chromadb.PersistentClient:
    ensure_project_dirs()
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def list_chroma_collection_names() -> list[str]:
    names: list[str] = []
    for collection in get_chroma_client().list_collections():
        names.append(collection if isinstance(collection, str) else collection.name)
    return names


def delete_chroma_collection(name: str) -> bool:
    if not collection_belongs_to_user(name):
        return False
    client = get_chroma_client()
    if name not in list_chroma_collection_names():
        return False
    client.delete_collection(name)
    return True


def delete_user_chroma_collections(username: str) -> int:
    removed = 0
    base_prefix = user_collection_prefix(username, "general")
    for name in list_chroma_collection_names():
        if name == base_prefix or name.startswith(f"{base_prefix}_"):
            get_chroma_client().delete_collection(name)
            removed += 1
    return removed


def get_active_collection_name() -> str:
    active_file = current_active_collection_file()
    if active_file.exists():
        name = active_file.read_text(encoding="utf-8").strip()
        if name and collection_belongs_to_user(name):
            return name
    return user_collection_prefix()


def set_active_collection_name(name: str) -> None:
    if not collection_belongs_to_user(name):
        raise ValueError("Colecția Chroma nu aparține utilizatorului curent.")
    ensure_project_dirs()
    active_file = current_active_collection_file()
    active_file.parent.mkdir(parents=True, exist_ok=True)
    active_file.write_text(name, encoding="utf-8")


def get_collection(collection_name: str | None = None):
    resolved_name = collection_name or get_active_collection_name()
    if not collection_belongs_to_user(resolved_name):
        raise ValueError("Colecția Chroma nu aparține utilizatorului curent.")
    client = get_chroma_client()
    return client.get_or_create_collection(resolved_name)


def get_vector_store() -> ChromaVectorStore:
    return ChromaVectorStore(chroma_collection=get_collection())


def count_indexed_chunks() -> int:
    return get_collection().count()


def collect_supported_files(paths: list[str]) -> list[str]:
    files: list[Path] = []

    for raw_path in paths:
        path = resolve_user_path(raw_path)
        if not path.exists():
            continue

        if path.is_dir():
            for ext in SUPPORTED_EXTS:
                files.extend(path.rglob(f"*{ext}"))
        elif path.is_file() and path.suffix.lower() in SUPPORTED_EXTS:
            files.append(path)

    unique_files = sorted(
        {
            file.resolve()
            for file in files
            if current_username() == "local" or is_current_user_document_path(file)
        }
    )
    return [str(file) for file in unique_files]


def save_uploaded_documents(uploaded_files) -> list[str]:
    enforce_streamlit_action_limit(cost=2)
    uploads = list(uploaded_files or [])
    max_files = environment_int("FACULTY_COPILOT_MAX_UPLOAD_FILES", 10, 1, 100)
    max_file_bytes = environment_int(
        "FACULTY_COPILOT_MAX_UPLOAD_MB", 100, 1, 2048
    ) * 1024 * 1024
    max_total_bytes = environment_int(
        "FACULTY_COPILOT_MAX_TOTAL_UPLOAD_MB", 250, 1, 4096
    ) * 1024 * 1024
    if len(uploads) > max_files:
        raise RuntimeError(f"Poți încărca maximum {max_files} fișiere simultan.")

    sizes = [len(uploaded_file.getbuffer()) for uploaded_file in uploads]
    if any(size > max_file_bytes for size in sizes):
        raise RuntimeError(
            f"Un fișier depășește limita de {max_file_bytes // (1024 * 1024)} MB."
        )
    if sum(sizes) > max_total_bytes:
        raise RuntimeError(
            f"Selecția depășește limita totală de "
            f"{max_total_bytes // (1024 * 1024)} MB."
        )

    target_dir = current_documents_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[str] = []
    for uploaded_file in uploads:
        safe_name = safe_document_filename(uploaded_file.name)
        target = target_dir / safe_name
        if target.exists():
            stem, suffix = target.stem, target.suffix
            target = target_dir / f"{stem}_{int(time.time())}{suffix}"
        target.write_bytes(uploaded_file.getbuffer())
        saved_paths.append(str(target))
    return saved_paths


def infer_discipline(file_path: str) -> str:
    path = Path(file_path)
    parent = path.parent.name.strip()
    if parent and parent.lower() not in {"documents", "ai", PROJECT_ROOT.name.lower()}:
        return parent

    stem_parts = [part.strip() for part in path.stem.split("-") if part.strip()]
    if len(stem_parts) >= 2:
        return stem_parts[1]

    return "Necunoscuta"


def infer_academic_year(file_path: str) -> str:
    path = Path(file_path)
    candidates = list(path.parts) + [path.stem]
    for value in candidates:
        match = re.search(r"\b(?:an|anul|year)\s*([1-6])\b", searchable_text(value))
        if match:
            return f"Anul {match.group(1)}"
    return "Nespecificat"


def infer_course_label(file_name: str) -> str:
    normalized = searchable_text(Path(file_name).stem)
    match = re.search(r"\bcurs\s*(\d+)(?:\s*(?:si|and)\s*(\d+))?\b", normalized)
    if match and match.group(2):
        return f"Curs {match.group(1)} si {match.group(2)}"
    if match:
        return f"Curs {match.group(1)}"
    return Path(file_name).stem


def document_metadata_key(document: dict) -> str:
    return document.get("file_path") or document.get("file_name") or "document necunoscut"


def default_academic_metadata(file_name: str, file_path: str, discipline: str) -> dict:
    subject = discipline if discipline and discipline != "Necunoscuta" else infer_discipline(file_path or file_name)
    return {
        "academic_year": infer_academic_year(file_path or file_name),
        "subject": subject or "Necunoscuta",
        "course": infer_course_label(file_name),
    }


def apply_saved_academic_metadata(document: dict, metadata_map: dict[str, dict]) -> dict:
    key = document_metadata_key(document)
    saved = metadata_map.get(key) or metadata_map.get(document.get("file_name", "")) or {}
    defaults = default_academic_metadata(
        document.get("file_name", "document necunoscut"),
        document.get("file_path", ""),
        document.get("discipline", "Necunoscuta"),
    )
    document["metadata_key"] = key
    document["academic_year"] = saved.get("academic_year") or defaults["academic_year"]
    document["subject"] = saved.get("subject") or defaults["subject"]
    document["course"] = saved.get("course") or defaults["course"]
    document["discipline"] = document["subject"] or document.get("discipline") or "Necunoscuta"
    return document


def ensure_document_metadata_records(documents: list[dict]) -> None:
    metadata_map = get_document_metadata_map(MEMORY_DB_PATH)
    for document in documents:
        key = document_metadata_key(document)
        if key in metadata_map:
            continue
        upsert_document_metadata(
            MEMORY_DB_PATH,
            document_key=key,
            file_name=document.get("file_name", "document necunoscut"),
            file_path=document.get("file_path"),
            academic_year=document.get("academic_year"),
            subject=document.get("subject") or document.get("discipline"),
            course=document.get("course"),
        )


def file_metadata(file_path: str) -> dict:
    path = Path(file_path).resolve()
    return {
        "file_name": path.name,
        "file_path": str(path),
        "file_extension": path.suffix.lower(),
        "discipline": infer_discipline(str(path)),
        "owner_username": current_username(),
    }


def build_index(paths: list[str]) -> tuple[int, int]:
    files = collect_supported_files(paths)
    if not files:
        raise ValueError("Nu am gasit fisiere PDF, DOCX sau PPTX in selectia curenta.")

    previous_collection = get_active_collection_name()
    collection_prefix = user_collection_prefix()
    collection_name = f"{collection_prefix}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    collection = get_collection(collection_name)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    try:
        documents = SimpleDirectoryReader(
            input_files=files,
            file_metadata=file_metadata,
        ).load_data()
        for document in documents:
            metadata = document.metadata
            metadata["owner_username"] = current_username()
            page = metadata.get("page_label") or metadata.get("page_number") or metadata.get("page")
            if page:
                metadata["page_number"] = str(page)
            file_path = metadata.get("file_path")
            if file_path:
                resolved_path = str(Path(file_path).resolve())
                metadata["file_path"] = resolved_path
                metadata["file_name"] = Path(resolved_path).name
                metadata["file_extension"] = Path(resolved_path).suffix.lower()
                metadata["discipline"] = metadata.get("discipline") or infer_discipline(resolved_path)
                academic_defaults = default_academic_metadata(
                    metadata["file_name"],
                    resolved_path,
                    metadata["discipline"],
                )
                metadata["academic_year"] = academic_defaults["academic_year"]
                metadata["subject"] = academic_defaults["subject"]
                metadata["course"] = academic_defaults["course"]

        VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            show_progress=True,
        )
        chunk_count = collection.count()
        set_active_collection_name(collection_name)
        if (
            previous_collection != collection_name
            and previous_collection in list_chroma_collection_names()
            and collection_belongs_to_user(previous_collection)
        ):
            get_chroma_client().delete_collection(previous_collection)
    except Exception:
        if collection_name in list_chroma_collection_names():
            get_chroma_client().delete_collection(collection_name)
        raise

    clear_retrieval_cache()
    indexed_documents = get_indexed_documents()
    ensure_document_metadata_records(indexed_documents)
    return len(files), chunk_count


def document_by_file_name(file_name: str) -> dict | None:
    requested = searchable_text(Path(file_name or "").name)
    for document in get_indexed_documents():
        if searchable_text(document.get("file_name", "")) == requested:
            return document
    return None


def delete_document_chunks(file_path: Path) -> None:
    collection = get_collection()
    collection.delete(where={"file_path": str(file_path.resolve())})
    clear_retrieval_cache()


def rename_document_chunks(old_path: Path, new_path: Path) -> int:
    collection = get_collection()
    result = collection.get(
        where={"file_path": str(old_path.resolve())},
        include=["metadatas"],
    )
    ids = result.get("ids") or []
    metadatas = result.get("metadatas") or []
    if not ids:
        return 0

    updated_metadatas: list[dict] = []
    academic_defaults = default_academic_metadata(
        new_path.name,
        str(new_path),
        infer_discipline(str(new_path)),
    )
    for metadata in metadatas:
        updated = dict(metadata or {})
        updated.update(
            {
                "file_name": new_path.name,
                "file_path": str(new_path.resolve()),
                "file_extension": new_path.suffix.lower(),
                "discipline": academic_defaults["subject"],
                "academic_year": academic_defaults["academic_year"],
                "subject": academic_defaults["subject"],
                "course": academic_defaults["course"],
                "owner_username": current_username(),
            }
        )
        updated_metadatas.append(
            {key: value for key, value in updated.items() if value is not None}
        )
    collection.update(ids=ids, metadatas=updated_metadatas)
    clear_retrieval_cache()
    return len(ids)


def delete_indexed_document(document: dict) -> None:
    normalized = normalize_document_record(document)
    if normalized is None:
        raise ValueError("Documentul nu aparține utilizatorului curent.")
    path = Path(normalized["file_path"]).resolve()
    delete_document_chunks(path)
    if path.exists():
        path.unlink()
    delete_document_metadata(MEMORY_DB_PATH, str(path))
    delete_document_metadata(MEMORY_DB_PATH, path.name)
    clear_retrieval_cache()


def rename_indexed_document(document: dict, new_name: str) -> Path:
    normalized = normalize_document_record(document)
    if normalized is None:
        raise ValueError("Documentul nu aparține utilizatorului curent.")
    old_path = Path(normalized["file_path"]).resolve()
    safe_name = Path(new_name or "").name.strip()
    if not safe_name:
        raise ValueError("Numele nou nu poate fi gol.")
    target = old_path.with_name(safe_name)
    if target.suffix == "":
        target = target.with_suffix(old_path.suffix)
    if target.suffix.lower() not in SUPPORTED_EXTS:
        raise ValueError("Documentele acceptate sunt PDF, DOCX sau PPTX.")
    if target.suffix.lower() != old_path.suffix.lower():
        raise ValueError("Redenumirea nu poate schimba tipul documentului.")
    target = target.resolve()
    if target == old_path:
        return old_path
    if not is_current_user_document_path(target):
        raise ValueError("Numele ales nu este sigur pentru profilul curent.")
    if target.exists():
        raise ValueError("Există deja un document cu acest nume.")

    old_metadata = get_document_metadata_map(MEMORY_DB_PATH).get(str(old_path)) or {}
    if old_path.exists():
        old_path.rename(target)
    rename_document_chunks(old_path, target)
    delete_document_metadata(MEMORY_DB_PATH, str(old_path))
    delete_document_metadata(MEMORY_DB_PATH, old_path.name)
    upsert_document_metadata(
        MEMORY_DB_PATH,
        document_key=str(target),
        file_name=target.name,
        file_path=str(target),
        academic_year=old_metadata.get("academic_year"),
        subject=old_metadata.get("subject"),
        course=old_metadata.get("course"),
    )
    clear_retrieval_cache()
    return target


def reindex_current_user_documents() -> tuple[int, int]:
    return build_index([str(current_documents_dir())])


def delete_all_current_user_documents() -> int:
    removed_files = 0
    root = current_documents_dir().resolve()
    if root.exists():
        for file_path in sorted(root.rglob("*")):
            if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTS:
                file_path.unlink()
                removed_files += 1
    active_file = current_active_collection_file()
    for collection_name in list_chroma_collection_names():
        if collection_belongs_to_user(collection_name):
            get_chroma_client().delete_collection(collection_name)
    active_file.unlink(missing_ok=True)
    delete_all_document_metadata(MEMORY_DB_PATH)
    clear_retrieval_cache()
    return removed_files


def delete_profile_and_data(username: str) -> bool:
    normalized = normalize_username(username)
    delete_user_chroma_collections(normalized)
    return USER_ACCOUNTS.delete_profile(normalized)


def load_index() -> VectorStoreIndex:
    return VectorStoreIndex.from_vector_store(vector_store=get_vector_store())


def make_query_engine(similarity_top_k: int = MIN_RETRIEVAL_TOP_K):
    index = load_index()
    return index.as_query_engine(
        similarity_top_k=max(similarity_top_k, MIN_RETRIEVAL_TOP_K),
        response_mode="compact",
    )


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return without_marks.lower()


def searchable_text(text: str) -> str:
    normalized = normalize_text(text)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def detect_user_intent(question: str) -> IntentDecision:
    normalized = searchable_text(question)
    tokens = set(normalized.split())
    course_signals = (
        "cursul meu",
        "cursurile mele",
        "din curs",
        "in curs",
        "conform cursului",
        "conform documentului",
        "documentul meu",
        "documentele mele",
        "pdf ul",
        "pagina din",
        "materialele mele",
        "my course",
        "my courses",
        "from my course",
        "my document",
        "my documents",
    )
    has_course_signal = any(phrase in normalized for phrase in course_signals) or bool(
        tokens & {"curs", "cursul", "cursuri", "document", "documentul", "pdf"}
    )
    general_phrases = (
        "cunostinte generale",
        "din cunostintele tale",
        "fara documente",
        "fara curs",
        "in general",
        "la nivel general",
    )
    explicit_general = any(phrase in normalized for phrase in general_phrases)

    flashcard_requested = any(
        phrase in normalized
        for phrase in (
            "genereaza flashcard",
            "creeaza flashcard",
            "fa mi flashcard",
            "vreau flashcard",
            "flashcards despre",
        )
    ) and not re.search(r"\b(?:nu|fara)\s+(?:vreau\s+)?flashcards?\b", normalized)
    if flashcard_requested:
        return IntentDecision("flashcards", 0.98, "cerere explicită de flashcards")
    quiz_requested = any(
        phrase in normalized
        for phrase in (
            "genereaza quiz",
            "creeaza quiz",
            "fa mi quiz",
            "vreau quiz",
            "quiz despre",
            "intrebari grila",
        )
    ) and not re.search(r"\b(?:nu|fara)\s+(?:vreau\s+)?(?:quiz|grile?)\b", normalized)
    if quiz_requested:
        return IntentDecision("quiz", 0.98, "cerere explicită de quiz")
    if any(
        phrase in normalized
        for phrase in (
            "plan de invatare",
            "plan pentru examen",
            "plan sesiune",
            "ce sa invat",
            "cum sa invat",
            "ce repet",
        )
    ):
        return IntentDecision("study_planning", 0.95, "cerere de strategie de studiu")
    if any(
        phrase in normalized
        for phrase in (
            "memoria mea",
            "progresul meu",
            "subiectele mele slabe",
            "ce am intrebat",
            "istoricul meu",
        )
    ):
        return IntentDecision("memory", 0.96, "cerere despre memoria locală")

    compare_signal = any(
        phrase in normalized
        for phrase in (
            "compara",
            "comparatie",
            "diferente intre",
            "asemanari intre",
            "compare",
            "difference between",
        )
    )
    document_plural = any(word in tokens for word in ("cursuri", "documente", "pdfuri"))
    multiple_course_numbers = len(re.findall(r"\bcurs(?:ul)?\s*(\d+)\b", normalized)) > 1
    if compare_signal and (document_plural or multiple_course_numbers):
        return IntentDecision("compare_documents", 0.98, "comparație explicită între documente")

    mixed_phrases = (
        "cursul meu cu",
        "din curs cu",
        "documentul meu cu",
        "documentele mele cu",
        "ce spune cursul si",
        "ce spun cursurile si",
        "raportat la lumea reala",
        "comparativ cu practica",
        "my course with",
        "from my course with",
        "my documents with",
    )
    if has_course_signal and (
        explicit_general or any(phrase in normalized for phrase in mixed_phrases)
    ):
        return IntentDecision(
            "mixed",
            0.94,
            "întrebarea cere simultan cursul și cunoștințe externe",
            explicit_general=explicit_general,
        )

    if any(
        phrase in normalized
        for phrase in (
            "cauta in document",
            "gaseste in curs",
            "unde scrie",
            "la ce pagina",
            "ce contine cursul",
            "rezumat curs",
        )
    ):
        return IntentDecision("document_search", 0.97, "căutare explicită în document")
    if has_course_signal:
        return IntentDecision("course_question", 0.91, "referință explicită la curs/document")
    if explicit_general:
        return IntentDecision(
            "general_knowledge",
            0.98,
            "utilizatorul a cerut explicit cunoștințe generale",
            explicit_general=True,
        )
    obvious_general_phrases = (
        "care este capitala",
        "cine este",
        "cine a fost",
        "cand a avut loc",
        "what is the capital",
        "who is",
        "who was",
        "write code",
        "scrie cod",
        "in python",
        "in javascript",
        "reteta pentru",
        "recipe for",
    )
    named_entity_question = bool(
        re.search(
            r"\b(?:ce\s+este|ce\s+e|what\s+is)\s+(?:un|o|the)?\s*[A-Z][\w.-]+",
            question,
        )
    )
    if named_entity_question or any(
        phrase in normalized for phrase in obvious_general_phrases
    ):
        return IntentDecision(
            "general_knowledge",
            0.9,
            "întrebare generală fără legătură cu documentele",
            explicit_general=True,
        )
    return IntentDecision(
        "general_knowledge",
        0.58,
        "intenție ambiguă; relevanța documentelor trebuie verificată",
    )


def detect_answer_mode(question: str) -> str:
    normalized = searchable_text(question)
    normalized_tokens = set(normalized.split())
    strategy_phrases = (
        "cum invat",
        "cum sa invat",
        "ce sa invat prima",
        "ce ar trebui sa invat",
        "ce repet",
        "ce sa repet",
        "plan de invatare",
        "plan pentru examen",
        "plan sesiune",
        "strategie de invatare",
        "pregatesc pentru examen",
    )
    analysis_phrases = (
        "compara",
        "comparatie",
        "care e mai greu",
        "care este mai greu",
        "cel mai greu",
        "evalueaza",
        "ce e mai important",
        "ce este mai important",
        "prioritizeaza",
        "clasifica",
        "ordoneaza",
        "avantaje si dezavantaje",
        "diferente intre",
    )
    professor_phrases = (
        "explica mi",
        "invata ma",
        "de ce",
        "pas cu pas",
        "ca unui student",
        "pe intelesul",
        "da mi un exemplu",
    )
    strict_phrases = (
        "defineste",
        "definitia",
        "formula",
        "ecuatie",
        "ce este",
        "ce inseamna",
    )

    if (
        any(phrase in normalized for phrase in strategy_phrases)
        or bool(normalized_tokens & {"plan", "planul", "planuri", "planificare"})
        or any(token.startswith("sesiun") for token in normalized_tokens)
    ):
        return "Strategie de învățare"
    if any(phrase in normalized for phrase in analysis_phrases):
        return "Analiză"
    if any(phrase in normalized for phrase in professor_phrases):
        return "Profesor"
    if any(phrase in normalized for phrase in strict_phrases):
        return "Strict"
    return "Profesor"


def resolve_answer_mode(answer_mode: str | None, question: str) -> str:
    requested = answer_mode if answer_mode in ANSWER_MODE_OPTIONS else DEFAULT_ANSWER_MODE
    return detect_answer_mode(question) if requested == "Auto" else requested


def build_reasoning_plan(
    question: str,
    knowledge_mode: str = DEFAULT_KNOWLEDGE_MODE,
    available_documents: int = 0,
    has_conversation_context: bool = False,
) -> ReasoningPlan:
    normalized = searchable_text(question)
    tokens = set(normalized.split())
    decision = detect_user_intent(question)
    answer_mode = detect_answer_mode(question)

    ranking_phrases = (
        "cel mai greu",
        "cea mai grea",
        "care e mai greu",
        "care este mai greu",
        "cel mai important",
        "cea mai importanta",
        "clasifica",
        "ordoneaza",
        "fa un top",
        "rank",
        "hardest course",
        "most difficult course",
    )
    recommendation_phrases = (
        "ce recomanzi",
        "ce imi recomanzi",
        "ce ar trebui",
        "ar trebui sa",
        "cu ce sa incep",
        "care merita",
        "recommend",
        "should i",
    )
    opinion_phrases = (
        "ce parere ai",
        "dupa parerea ta",
        "crezi ca",
        "what do you think",
        "in your opinion",
    )
    explanation_phrases = (
        "explica",
        "de ce",
        "cum functioneaza",
        "ajuta ma sa inteleg",
        "explain",
        "why",
        "how does",
    )
    ranking = any(phrase in normalized for phrase in ranking_phrases)
    recommendation = any(phrase in normalized for phrase in recommendation_phrases)
    opinion = any(phrase in normalized for phrase in opinion_phrases)
    explanation = any(phrase in normalized for phrase in explanation_phrases)
    course_scope = bool(
        tokens
        & {
            "curs",
            "cursul",
            "cursuri",
            "materie",
            "materii",
            "document",
            "documente",
        }
    )

    if recommendation:
        user_goal = "recommendation"
        claim_type = "recommendation"
        inference_level = "evaluative"
        answer_mode = "Strategie de învățare"
    elif ranking:
        user_goal = "ranking"
        claim_type = "inference"
        inference_level = "evaluative"
        answer_mode = "Analiză"
    elif opinion:
        user_goal = "opinion"
        claim_type = "opinion"
        inference_level = "evaluative"
    elif explanation:
        user_goal = "explanation"
        claim_type = "mixed"
        inference_level = "prudent"
    elif answer_mode == "Strict":
        user_goal = "factual_answer"
        claim_type = "fact"
        inference_level = "literal"
    else:
        user_goal = "answer"
        claim_type = "mixed"
        inference_level = "prudent"

    documents_allowed = knowledge_mode != "General knowledge only"
    needs_cross = bool(
        available_documents > 1
        and documents_allowed
        and (ranking or (recommendation and course_scope))
    )
    needs_documents = bool(
        available_documents
        and documents_allowed
        and (
            needs_cross
            or course_scope
            or decision.intent
            in {
                "course_question",
                "document_search",
                "compare_documents",
                "study_planning",
                "flashcards",
                "quiz",
                "memory",
                "mixed",
            }
        )
    )
    tools = ["conversation_memory"] if has_conversation_context else []
    if needs_documents:
        tools.append("cross_document_comparison" if needs_cross else "document_retrieval")
    if decision.intent == "memory" or recommendation:
        tools.append("study_memory")

    instruction = (
        "Analizează intern înainte de răspuns, fără a expune chain-of-thought. "
        "Oferă concluzia, dovezile verificabile și o justificare scurtă, calibrată. "
        "Separă clar faptele, inferențele, opiniile și recomandările atunci când se "
        "amestecă. Inferă rezonabil din dovezi; nu transforma o inferență în fapt. "
        "Dacă dovezile permit doar o concluzie probabilă, exprimă gradul de încredere. "
        "Refuză doar partea care ar necesita inventarea unor fapte. Dacă lipsește o "
        "informație esențială, pune o singură întrebare de clarificare precisă; dacă o "
        "presupunere rezonabilă este suficientă și cu risc mic, declar-o și continuă. "
        "Adaptează explicația la nivelul sugerat de conversație și folosește exemple "
        "pedagogice fără a le prezenta drept dovezi."
    )
    if needs_cross:
        instruction += (
            " Pentru evaluări între cursuri folosește criterii explicite: densitatea și "
            "numărul conceptelor, complexitatea matematică, abstractizarea, prerequisitele, "
            "dimensiunea capitolelor, terminologia și conexiunile cu alte cursuri."
        )

    return ReasoningPlan(
        intent=decision.intent,
        user_goal=user_goal,
        answer_mode=answer_mode,
        claim_type=claim_type,
        inference_level=inference_level,
        needs_documents=needs_documents,
        needs_cross_document_reasoning=needs_cross,
        tools=tuple(dict.fromkeys(tools)),
        context_required=has_conversation_context,
        instruction=instruction,
    )


def attach_reasoning_plan(response: StudyResponse, plan: ReasoningPlan) -> StudyResponse:
    response.debug["reasoning_plan"] = {
        "intent": plan.intent,
        "user_goal": plan.user_goal,
        "answer_mode": plan.answer_mode,
        "claim_type": plan.claim_type,
        "inference_level": plan.inference_level,
        "tools": list(plan.tools),
        "context_used": plan.context_required,
    }
    return response


def answer_mode_instruction(answer_mode: str) -> str:
    if answer_mode == "Strict":
        return (
            "MOD STRICT: foloseste numai fapte afirmate explicit in context. Nu completa "
            "golurile prin presupuneri. Pentru definitii, formule si valori, reda exact "
            "sensul din curs. Daca informatia lipseste, spune clar ca nu apare in "
            "fragmentele disponibile."
        )
    if answer_mode == "Analiză":
        return (
            "MOD ANALIZA: foloseste cursurile ca dovezi si permite inferenta prudenta, "
            "interpolarea, comparatia, ierarhizarea si sinteza. Include exact fraza "
            "«Aceasta este o evaluare inferențială bazată pe conținutul cursurilor.» "
            "Separa raspunsul in sectiunile «Fapte din cursuri», «Inferență / analiză» "
            "si «Concluzie». Nu refuza o ierarhizare doar fiindca ea nu este scrisa "
            "explicit. Evalueaza, cand este relevant: nivelul de abstractizare, "
            "densitatea matematica/formulelor, numarul conceptelor noi, cunostintele "
            "prealabile, relevanta clinica/medicala si dificultatea conceptuala. Explica "
            "incertitudinea si ofera un clasament cand intrebarea il cere. Pentru cursuri, "
            "ia in calcul si dimensiunea capitolelor, densitatea terminologiei si "
            "conexiunile/prerequisitele dintre materii."
        )
    if answer_mode == "Strategie de învățare":
        return (
            "MOD STRATEGIE DE INVATARE: transforma dovezile din cursuri si memoria de "
            "studiu intr-o recomandare practica. Tine cont de complexitatea documentelor, "
            "subiectele slabe, istoricul quizurilor, cursurile neglijate si data examenului "
            "daca exista. Da ordinea de studiu, motivul, timpul orientativ, recapitularea "
            "si un pas concret de verificare. Diferentiaza clar faptele din curs de "
            "recomandarile tale."
        )
    return (
        "MOD PROFESOR: explica precum un profesor universitar, progresiv si pas cu pas. "
        "Leaga conceptele intre documente cand exista dovezi, foloseste analogii si "
        "exemple pedagogice si precizeaza cand acestea sunt doar ilustratii. Pastreaza "
        "rigoarea, nu inventa fapte si citeaza dovezile din cursuri."
    )


def build_answer_prompt(
    question: str,
    context: str,
    memory_context: str,
    target: str,
    task: str,
    response_instruction: str,
    answer_mode: str,
) -> str:
    return (
        "/no_think\n"
        "Esti Co-pilot Facultate, un tutore universitar local. Documentele furnizate sunt "
        "sursa factuala principala. Nu inventa documente, pagini, citate sau rezultate. "
        "Pentru fiecare afirmatie factuala importanta foloseste citari [document, pagina]. "
        "Inferentele trebuie sustinute de dovezi citate si etichetate ca analiza, nu "
        "prezentate drept text explicit al cursului.\n"
        f"{REASONING_INSTRUCTION_CONTEXT.get()}\n"
        f"{answer_mode_instruction(answer_mode)}\n"
        f"{response_instruction}\n\n"
        f"{target}"
        f"Sarcina: {task}\n"
        f"Intrebare: {question}\n\n"
        f"User study memory:\n{memory_context}\n\n"
        f"Context din cursuri:\n{context}\n\n"
        "Raspuns in romana:"
    )


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in searchable_text(text).split()
        if len(token) >= 2 and token not in STOPWORDS
    }


def clean_model_text(text: str) -> str:
    return re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()


def detect_study_topic(question: str, document: dict | None = None) -> str:
    if document and is_document_summary_question(question):
        return Path(document.get("file_name", "document")).stem

    generic_words = STOPWORDS | {
        "arata",
        "continut",
        "document",
        "documente",
        "fisier",
        "fisiere",
        "genereaza",
        "intrebare",
        "intrebari",
        "raspunde",
        "raspuns",
        "spune",
    }
    words = [
        word
        for word in searchable_text(question).split()
        if len(word) >= 3 and word not in generic_words and not word.isdigit()
    ]
    if words:
        return " ".join(words[:6])
    if document:
        return Path(document.get("file_name", "document")).stem
    return "studiu general"


def concise_answer_summary(answer: str, limit: int = 700) -> str:
    cleaned = " ".join(clean_model_text(answer).split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit].rsplit(' ', 1)[0]}..."


def response_source_records(response) -> list[dict]:
    if not isinstance(response, StudyResponse):
        return []

    sources = []
    seen = set()
    for chunk in response.chunks:
        metadata = chunk.get("metadata") or {}
        file_name = metadata.get("file_name") or metadata.get("filename") or "document necunoscut"
        file_path = metadata.get("file_path") or metadata.get("full_path")
        page = metadata.get("page_number") or metadata.get("page_label") or metadata.get("page")
        key = (file_path or file_name, str(page or ""))
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "file_name": file_name,
                "file_path": file_path,
                "page": page,
                "score": round(float(chunk.get("rerank_score", 0.0)), 4),
                "excerpt": " ".join((chunk.get("text") or "").split())[:1200],
            }
        )
    return sources


def response_document_names(response) -> list[str]:
    return sorted(
        {
            source["file_name"]
            for source in response_source_records(response)
            if source.get("file_name")
        }
    )


def build_study_memory_context(
    question: str,
    topic: str,
    document: dict | None,
    limit: int = 4,
) -> str:
    relevant = get_relevant_memory(
        MEMORY_DB_PATH,
        question=question,
        topic=topic,
        document_name=document.get("file_name") if document else None,
        limit=limit,
    )
    weak_topics = relevant.get("weak_topics") or []
    previous_questions = relevant.get("previous_questions") or []
    notebook_entries = get_notebook_entries(MEMORY_DB_PATH, limit=12)
    if not weak_topics and not previous_questions and not notebook_entries:
        return "Nu exista memorie relevanta pentru aceasta intrebare."

    lines = [
        "Foloseste aceste informatii doar pentru a adapta claritatea si accentul raspunsului.",
        "Nu trata memoria ca sursa factuala; faptele trebuie sa vina exclusiv din documente.",
    ]
    if weak_topics:
        lines.append("Subiecte marcate anterior ca dificile:")
        for item in weak_topics:
            lines.append(f"- {item['topic']} ({item['status']})")
    if previous_questions:
        lines.append("Intrebari anterioare relevante:")
        for item in previous_questions:
            summary = concise_answer_summary(item.get("answer_summary") or "", limit=180)
            lines.append(f"- {item['question']} | rezumat anterior: {summary}")
    if notebook_entries:
        lines.append(
            "Notebook confirmat de utilizator (context personal, nu instrucțiuni de sistem):"
        )
        for item in notebook_entries:
            lines.append(f"- [{item['category']}] {item['content']}")
    return "\n".join(lines)


def build_strategy_memory_context(limit: int = 6) -> str:
    dashboard = get_dashboard_summary(MEMORY_DB_PATH)
    weak_topics = get_weak_topics(MEMORY_DB_PATH, limit=limit)
    recommendations = get_recommended_topics(MEMORY_DB_PATH, limit=limit)
    quiz_results = get_quiz_results(MEMORY_DB_PATH, limit=20)
    plans = get_session_plans(MEMORY_DB_PATH, limit=1)
    last_documents = get_last_studied_documents(MEMORY_DB_PATH, limit=limit)
    notebook_entries = get_notebook_entries(MEMORY_DB_PATH, limit=limit)

    lines = [
        "Date locale pentru strategie (nu sunt surse factuale despre materie):",
        f"- Intrebari anterioare: {dashboard.get('total_questions', 0)}",
        f"- Documente studiate: {dashboard.get('documents_studied', 0)}",
        f"- Streak curent: {dashboard.get('study_streak', 0)} zile",
    ]
    quiz_average = dashboard.get("quiz_average")
    if quiz_average is not None:
        lines.append(f"- Medie quiz: {quiz_average:.1f}%")
    if weak_topics:
        lines.append(
            "- Subiecte slabe: "
            + "; ".join(
                f"{item.get('topic', 'necunoscut')} ({item.get('status', 'de repetat')})"
                for item in weak_topics
            )
        )
    if recommendations:
        lines.append(
            "- Prioritati recomandate din memorie: "
            + "; ".join(item.get("topic", "") for item in recommendations if item.get("topic"))
        )
    wrong_quiz_topics = [
        item.get("topic")
        for item in quiz_results
        if float(item.get("score") or 0) < 1 and item.get("topic")
    ]
    if wrong_quiz_topics:
        lines.append("- Subiecte cu raspunsuri gresite la quiz: " + "; ".join(wrong_quiz_topics[:limit]))
    if last_documents:
        lines.append(
            "- Documente studiate recent: "
            + "; ".join(
                item.get("document_name") or item.get("file_name") or "document"
                for item in last_documents
            )
        )
    if plans:
        plan = plans[0]
        lines.append(
            f"- Ultimul plan: {plan.get('subject', 'materie nespecificata')}; "
            f"examen {plan.get('exam_date') or 'fara data'}; "
            f"{plan.get('hours_per_day', 0)} ore/zi; "
            f"documente: {', '.join(plan.get('selected_documents') or [])}"
        )
    if notebook_entries:
        lines.append(
            "- Notebook confirmat: "
            + "; ".join(
                f"[{item['category']}] {item['content']}"
                for item in notebook_entries
            )
        )
    return "\n".join(lines)


def _parse_local_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc).astimezone()
    return parsed.astimezone()


def build_proactive_study_insights(now: datetime | None = None) -> list[dict]:
    """Create evidence-backed suggestions without invoking the LLM."""
    now = (now or datetime.now().astimezone()).astimezone()
    insights: list[dict] = []
    history = get_recent_questions(MEMORY_DB_PATH, limit=250)
    quiz_results = get_quiz_results(MEMORY_DB_PATH, limit=200)
    plans = get_session_plans(MEMORY_DB_PATH, limit=5)
    sessions = get_recent_sessions(MEMORY_DB_PATH, limit=100)
    weak_topics = get_weak_topics(MEMORY_DB_PATH, limit=100)
    flashcard_sets = get_flashcard_history(MEMORY_DB_PATH, limit=30)
    notebook = get_notebook_entries(MEMORY_DB_PATH, limit=30)

    last_activity_by_document: dict[str, datetime] = {}
    for item in history:
        timestamp = _parse_local_datetime(item.get("created_at"))
        if timestamp is None:
            continue
        names = list(item.get("retrieved_documents") or [])
        if item.get("selected_document"):
            names.append(item["selected_document"])
        for name in names:
            key = searchable_text(name)
            previous = last_activity_by_document.get(key)
            if previous is None or timestamp > previous:
                last_activity_by_document[key] = timestamp

    stale_documents = []
    for document in get_indexed_documents():
        name = document.get("file_name") or ""
        last_activity = last_activity_by_document.get(searchable_text(name))
        if last_activity is None:
            stale_documents.append((name, None))
            continue
        days = (now.date() - last_activity.date()).days
        if days >= 10:
            stale_documents.append((name, days))
    if stale_documents:
        name, days = sorted(
            stale_documents,
            key=lambda item: (item[1] is None, item[1] or 10_000),
            reverse=True,
        )[0]
        message = (
            f"Nu ai studiat încă {name}."
            if days is None
            else f"Nu ai revizuit {name} de {days} zile."
        )
        insights.append(
            {
                "severity": "info",
                "title": "Curs care merită revizuit",
                "message": message,
                "basis": "istoricul local de studiu",
            }
        )

    topic_scores: dict[str, dict] = {}
    for result in quiz_results:
        topic = (result.get("topic") or "").strip()
        if not topic:
            continue
        entry = topic_scores.setdefault(
            searchable_text(topic),
            {"topic": topic, "attempts": 0, "wrong": 0},
        )
        entry["attempts"] += 1
        if float(result.get("score") or 0) < 1:
            entry["wrong"] += 1
    repeated_mistakes = [
        item
        for item in topic_scores.values()
        if item["wrong"] >= 2 and item["wrong"] / item["attempts"] >= 0.5
    ]
    if repeated_mistakes:
        weakest = max(
            repeated_mistakes,
            key=lambda item: (item["wrong"] / item["attempts"], item["wrong"]),
        )
        accuracy = 100 * (weakest["attempts"] - weakest["wrong"]) / weakest["attempts"]
        insights.append(
            {
                "severity": "warning",
                "title": "Tipar de greșeli detectat",
                "message": (
                    f"La {weakest['topic']} ai {weakest['wrong']} răspunsuri greșite din "
                    f"{weakest['attempts']} încercări ({accuracy:.0f}% corecte)."
                ),
                "basis": "rezultatele quizurilor",
            }
        )

    for plan in plans:
        exam_date = _parse_local_datetime(plan.get("exam_date"))
        created_at = _parse_local_datetime(plan.get("created_at"))
        if exam_date is None or created_at is None or exam_date.date() < now.date():
            continue
        total_days = max(1, (exam_date.date() - created_at.date()).days)
        elapsed_days = max(0, (now.date() - created_at.date()).days)
        expected_progress = min(1.0, elapsed_days / total_days)
        active_days = {
            timestamp.date()
            for session in sessions
            if (timestamp := _parse_local_datetime(session.get("last_activity")))
            and timestamp >= created_at
        }
        planned_days = max(1, int(plan.get("number_of_days") or total_days))
        observed_progress = min(1.0, len(active_days) / planned_days)
        if expected_progress - observed_progress >= 0.2:
            insights.append(
                {
                    "severity": "warning",
                    "title": "Planul riscă să rămână în urmă",
                    "message": (
                        f"Pentru {plan.get('subject') or 'examen'}, calendarul este la "
                        f"aproximativ {expected_progress * 100:.0f}%, iar activitatea "
                        f"înregistrată acoperă circa {observed_progress * 100:.0f}% din "
                        "zilele planificate."
                    ),
                    "basis": "planul salvat și sesiunile înregistrate",
                }
            )
        days_to_exam = (exam_date.date() - now.date()).days
        if days_to_exam <= 7 and weak_topics:
            insights.append(
                {
                    "severity": "warning",
                    "title": f"Examen în {days_to_exam} zile",
                    "message": (
                        "Prioritizează: "
                        + ", ".join(
                            dict.fromkeys(item.get("topic") or "" for item in weak_topics)
                        )[:240]
                    ),
                    "basis": "data examenului și subiectele slabe",
                }
            )
        break

    if len(quiz_results) >= 10:
        recent_scores = [float(item.get("score") or 0) for item in quiz_results[:20]]
        average = sum(recent_scores) / len(recent_scores)
        recent_weak = [
            item
            for item in weak_topics
            if (_parse_local_datetime(item.get("created_at")) or now)
            >= now - timedelta(days=7)
        ]
        if average >= 0.8 and not recent_weak:
            insights.append(
                {
                    "severity": "success",
                    "title": "Semnale bune pentru examen",
                    "message": (
                        f"Media ultimelor {len(recent_scores)} răspunsuri este "
                        f"{average * 100:.0f}% și nu ai subiecte slabe noi în ultima săptămână."
                    ),
                    "basis": "quizuri și progres; aceasta este o estimare, nu o garanție",
                }
            )

    reminders = [item for item in notebook if item.get("category") == "reminder"]
    if reminders:
        insights.append(
            {
                "severity": "info",
                "title": "Reminder din Notebook",
                "message": reminders[0]["content"],
                "basis": "notă confirmată de tine",
            }
        )
    if weak_topics and not flashcard_sets:
        insights.append(
            {
                "severity": "info",
                "title": "Pas următor sugerat",
                "message": "Ai subiecte marcate ca dificile, dar încă niciun set de flashcarduri salvat.",
                "basis": "subiecte slabe și istoricul flashcardurilor",
            }
        )
    return insights[:4]


def render_proactive_study_agent() -> None:
    try:
        insights = build_proactive_study_insights()
    except Exception:
        return
    if not insights:
        return
    with st.expander("Agent de studiu · observații proactive", expanded=True):
        for insight in insights:
            text = f"**{insight['title']}** — {insight['message']}\n\n_Bază: {insight['basis']}_"
            if insight["severity"] == "warning":
                st.warning(text)
            elif insight["severity"] == "success":
                st.success(text)
            else:
                st.info(text)


def node_metadata_from_chroma(metadata: dict) -> dict:
    node_content = metadata.get("_node_content")
    if not node_content:
        return metadata

    try:
        parsed = json.loads(node_content)
    except json.JSONDecodeError:
        return metadata

    parsed_metadata = parsed.get("metadata")
    if not isinstance(parsed_metadata, dict):
        return metadata

    merged = dict(parsed_metadata)
    merged.update(metadata)
    return merged


def get_indexed_documents() -> list[dict]:
    collection = get_collection()
    chunk_count = collection.count()
    if chunk_count == 0:
        return []

    metadata_map = get_document_metadata_map(MEMORY_DB_PATH)
    result = collection.get(include=["metadatas"], limit=chunk_count)
    metadatas = result.get("metadatas") or []
    documents: dict[str, dict] = {}

    for raw_metadata in metadatas:
        if not raw_metadata:
            continue
        metadata = node_metadata_from_chroma(raw_metadata)
        file_name = metadata.get("file_name") or metadata.get("filename")
        file_path = metadata.get("file_path") or metadata.get("full_path") or ""
        if not file_name and file_path:
            file_name = Path(file_path).name
        if not file_name:
            file_name = "document necunoscut"
        owner = metadata.get("owner_username")
        if owner and owner != current_username():
            continue
        if file_path and not is_current_user_document_path(Path(file_path)):
            continue

        key = file_path or file_name
        page = metadata.get("page_number") or metadata.get("page_label") or metadata.get("page")
        discipline = metadata.get("discipline") or infer_discipline(file_path or file_name)
        academic_defaults = default_academic_metadata(file_name, file_path, discipline)

        document = documents.setdefault(
            key,
            {
                "file_name": file_name,
                "file_path": file_path,
                "discipline": discipline,
                "academic_year": metadata.get("academic_year") or academic_defaults["academic_year"],
                "subject": metadata.get("subject") or academic_defaults["subject"],
                "course": metadata.get("course") or academic_defaults["course"],
                "metadata_key": key,
                "chunks": 0,
                "pages": set(),
            },
        )
        document["chunks"] += 1
        if page:
            document["pages"].add(str(page))

    sorted_documents = sorted(documents.values(), key=lambda item: item["file_name"].lower())
    for document in sorted_documents:
        pages = sorted(
            document["pages"],
            key=lambda value: (0, int(value)) if value.isdigit() else (1, value),
        )
        document["page_count"] = len(pages)
        document["pages"] = pages
        apply_saved_academic_metadata(document, metadata_map)
    return sorted_documents


def is_document_inventory_question(question: str) -> bool:
    normalized = searchable_text(question)
    has_inventory_word = any(keyword in normalized for keyword in INVENTORY_KEYWORDS)
    asks_docs = any(word in normalized for word in ("curs", "document", "fisier", "pdf"))
    asks_what = any(word in normalized for word in ("ce", "care", "lista", "arata"))
    return has_inventory_word and asks_docs and asks_what


def indexed_documents_answer() -> str:
    documents = get_indexed_documents()
    if not documents:
        return "Nu exista documente indexate in baza locala."

    lines = [
        f"Sunt indexate {len(documents)} documente, cu {count_indexed_chunks()} fragmente in total:",
        "",
    ]
    for index, document in enumerate(documents, start=1):
        pages = f", {document['page_count']} pagini" if document["page_count"] else ""
        academic_path = " → ".join(
            value
            for value in (
                document.get("academic_year"),
                document.get("subject") or document.get("discipline"),
                document.get("course"),
            )
            if value and value != "Nespecificat"
        )
        lines.append(
            f"{index}. {document['file_name']} - {document['chunks']} fragmente{pages} "
            f"- structura: {academic_path or 'Nespecificata'}"
        )
        if document.get("file_path"):
            lines.append(f"   Cale: {document['file_path']}")
    return "\n".join(lines)


def document_course_numbers(document: dict) -> set[str]:
    name = searchable_text(document.get("file_name", ""))
    numbers: set[str] = set()
    match = re.search(r"\bcurs\s*(\d+)(?:\s*(?:si|and)\s*(\d+))?\b", name)
    if match:
        numbers.add(match.group(1))
        if match.group(2):
            numbers.add(match.group(2))
    return numbers


def detect_document_reference(question: str) -> dict | None:
    documents = get_indexed_documents()
    if not documents:
        return None

    query = searchable_text(question)
    candidates: list[tuple[int, int, dict]] = []
    course_numbers = re.findall(r"\bcurs(?:ul)?\s*(\d+)\b", query)

    for document in documents:
        file_name = document.get("file_name", "")
        file_name_query = searchable_text(file_name)
        stem_query = searchable_text(Path(file_name).stem)
        score = 0

        if file_name_query and file_name_query in query:
            score = max(score, 120)
        if stem_query and stem_query in query:
            score = max(score, 110)

        doc_numbers = document_course_numbers(document)
        for number in course_numbers:
            if number in doc_numbers:
                if file_name_query.startswith(f"curs {number} "):
                    score = max(score, 100)
                else:
                    score = max(score, 90)

        if score:
            candidates.append((score, -len(file_name), document))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def detect_document_references(question: str) -> list[dict]:
    documents = get_indexed_documents()
    query = searchable_text(question)
    course_numbers = set(re.findall(r"\bcurs(?:ul)?\s*(\d+)\b", query))
    matches = []
    for document in documents:
        file_name = searchable_text(document.get("file_name", ""))
        stem = searchable_text(Path(document.get("file_name", "")).stem)
        exact_name_match = bool(file_name and file_name in query) or bool(stem and stem in query)
        number_match = bool(course_numbers & document_course_numbers(document))
        if exact_name_match or number_match:
            matches.append(document)
    return matches


def needs_cross_document_reasoning(
    question: str,
    answer_mode: str,
    referenced_documents: list[dict],
) -> bool:
    if len(referenced_documents) > 1:
        return answer_mode in {"Analiză", "Profesor", "Strategie de învățare"}

    normalized = searchable_text(question)
    if answer_mode == "Analiză":
        course_scope = any(word in normalized for word in ("curs", "document", "materie"))
        ranking = any(
            phrase in normalized
            for phrase in (
                "cel mai greu",
                "mai greu",
                "cel mai important",
                "mai important",
                "clasifica",
                "ordoneaza",
                "prioritizeaza",
            )
        )
        return course_scope and ranking
    if answer_mode == "Strategie de învățare":
        return any(
            phrase in normalized
            for phrase in (
                "ce sa invat",
                "ce ar trebui sa invat",
                "cum sa invat",
                "ce repet",
                "plan pentru examen",
                "pregatesc pentru examen",
            )
        )
    return False


def is_document_summary_question(question: str) -> bool:
    normalized = searchable_text(question)
    return any(
        phrase in normalized
        for phrase in (
            "despre ce",
            "ce contine",
            "ce este in",
            "rezumat",
            "sumar",
            "sinteza",
            "prezinta",
        )
    )


def distance_to_similarity(distance: float | None) -> float:
    if distance is None:
        return 0.5
    return 1.0 / (1.0 + max(distance, 0.0))


def chroma_result_chunks(result: dict, intro_boost: float = 0.0) -> list[dict]:
    ids = (result.get("ids") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    chunks = []

    for index, text in enumerate(documents):
        metadata = node_metadata_from_chroma(metadatas[index] or {})
        distance = distances[index] if index < len(distances) else None
        chunks.append(
            {
                "id": ids[index] if index < len(ids) else f"chunk-{index}",
                "text": text or "",
                "metadata": metadata,
                "distance": distance,
                "vector_score": distance_to_similarity(distance),
                "intro_boost": intro_boost,
            }
        )
    return chunks


def chroma_get_chunks(result: dict, intro_boost: float = 0.0) -> list[dict]:
    ids = result.get("ids") or []
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []
    chunks = []

    for index, text in enumerate(documents):
        metadata = node_metadata_from_chroma(metadatas[index] or {})
        chunks.append(
            {
                "id": ids[index] if index < len(ids) else f"chunk-{index}",
                "text": text or "",
                "metadata": metadata,
                "distance": None,
                "vector_score": 0.5,
                "intro_boost": intro_boost,
            }
        )
    return chunks


def chunk_page_value(chunk: dict) -> tuple[int, int | str]:
    metadata = chunk.get("metadata") or {}
    page = str(metadata.get("page_number") or metadata.get("page_label") or metadata.get("page") or "")
    if page.isdigit():
        return (0, int(page))
    return (1, page)


def rerank_chunks(question: str, chunks: list[dict], top_k: int) -> list[dict]:
    query_tokens = tokenize(question)
    reranked = []

    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        source_text = " ".join(
            [
                chunk.get("text", ""),
                metadata.get("file_name", ""),
                metadata.get("discipline", ""),
            ]
        )
        chunk_tokens = tokenize(source_text)
        lexical_score = 0.0
        if query_tokens:
            lexical_score = len(query_tokens & chunk_tokens) / len(query_tokens)

        vector_score = chunk.get("vector_score", 0.0)
        intro_boost = chunk.get("intro_boost", 0.0)
        rerank_score = (0.70 * vector_score) + (0.25 * lexical_score) + intro_boost
        chunk["lexical_score"] = lexical_score
        chunk["rerank_score"] = rerank_score
        reranked.append(chunk)

    reranked.sort(
        key=lambda chunk: (
            chunk.get("rerank_score", 0.0),
            -chunk_page_value(chunk)[0],
        ),
        reverse=True,
    )
    return reranked[:top_k]


def unique_chunks(chunks: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for chunk in chunks:
        chunk_id = chunk.get("id")
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        unique.append(chunk)
    return unique


def compact_retrieved_chunks(
    chunks: list[dict],
    similarity_threshold: float = 0.88,
) -> list[dict]:
    compacted = []
    token_sets: list[set[str]] = []
    for chunk in chunks:
        chunk_tokens = tokenize(chunk.get("text", ""))
        is_duplicate = False
        if chunk_tokens:
            for previous_tokens in token_sets:
                union = chunk_tokens | previous_tokens
                overlap = len(chunk_tokens & previous_tokens) / len(union) if union else 0
                if overlap >= similarity_threshold:
                    is_duplicate = True
                    break
        if is_duplicate:
            continue
        compacted.append(chunk)
        token_sets.append(chunk_tokens)
    return compacted


def retrieval_cache_key(
    question: str,
    selected_documents: list[dict],
    top_k: int,
    candidate_top_k: int,
    summary_mode: bool,
) -> tuple:
    collection = get_collection()
    document_key = tuple(
        sorted(
            (
                item.get("file_name", ""),
                item.get("file_path", ""),
                int(item.get("chunks", 0)),
            )
            for item in selected_documents
        )
    )
    return (
        get_active_collection_name(),
        collection.count(),
        searchable_text(question),
        document_key,
        top_k,
        candidate_top_k,
        summary_mode,
    )


def get_cached_retrieval(key: tuple) -> tuple[list[dict], dict] | None:
    with RETRIEVAL_CACHE_LOCK:
        cached = RETRIEVAL_CACHE.get(key)
        if cached is None:
            return None
        RETRIEVAL_CACHE.move_to_end(key)
        chunks, debug = copy.deepcopy(cached)
    debug["cache_hit"] = True
    return chunks, debug


def set_cached_retrieval(key: tuple, chunks: list[dict], debug: dict) -> None:
    with RETRIEVAL_CACHE_LOCK:
        RETRIEVAL_CACHE[key] = copy.deepcopy((chunks, debug))
        RETRIEVAL_CACHE.move_to_end(key)
        while len(RETRIEVAL_CACHE) > RETRIEVAL_CACHE_MAX_ENTRIES:
            RETRIEVAL_CACHE.popitem(last=False)


def get_intro_chunks(document: dict, limit: int = 4) -> list[dict]:
    normalized = normalize_document_record(document)
    if normalized is None:
        return []
    file_path = normalized.get("file_path")

    result = get_collection().get(
        where={"file_path": file_path},
        include=["documents", "metadatas"],
        limit=max(document.get("chunks", limit), limit),
    )
    chunks = chroma_get_chunks(result, intro_boost=0.18)
    chunks.sort(key=chunk_page_value)
    return chunks[:limit]


def retrieve_chunks(
    question: str,
    document: dict | None = None,
    documents: list[dict] | None = None,
    top_k: int | None = None,
    summary_mode: bool = False,
    response_mode: str = DEFAULT_RESPONSE_MODE,
) -> tuple[list[dict], dict]:
    retrieval_started = time.perf_counter()
    profile = get_response_profile(response_mode)
    top_k = max(top_k or profile.top_k, 1)
    collection = get_collection()
    query_text = question
    where = None
    selected_documents = normalize_document_selection(
        documents or ([document] if document else [])
    )
    if document and selected_documents:
        document = selected_documents[0]
    elif document and not selected_documents:
        document = None
    cache_key = retrieval_cache_key(
        question,
        selected_documents,
        top_k,
        profile.candidate_top_k,
        summary_mode,
    )
    cached = get_cached_retrieval(cache_key)
    if cached is not None:
        chunks, debug = cached
        debug["retrieval_seconds"] = round(
            time.perf_counter() - retrieval_started, 4
        )
        return chunks, debug

    if selected_documents:
        file_paths = [
            item.get("file_path")
            for item in selected_documents
            if item.get("file_path")
        ]
        if len(file_paths) == 1:
            where = {"file_path": file_paths[0]}
        elif file_paths:
            where = {"file_path": {"$in": file_paths}}
        document_names = ", ".join(item["file_name"] for item in selected_documents)
        query_text = (
            f"{question}\nDocumente tinta: {document_names}\n"
            "Rezumat continut idei principale definitii formule exemple."
        )

    query_embedding = Settings.embed_model.get_query_embedding(query_text)
    available_chunks = (
        sum(item.get("chunks", 0) for item in selected_documents)
        if selected_documents
        else collection.count()
    )
    candidate_count = min(
        max(profile.candidate_top_k, top_k),
        max(available_chunks, 1),
    )
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=candidate_count,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    candidates = chroma_result_chunks(result)

    if document and summary_mode:
        candidates = unique_chunks(get_intro_chunks(document) + candidates)

    reranked = rerank_chunks(question, candidates, len(candidates))
    reranked = compact_retrieved_chunks(reranked)[:top_k]
    debug = {
        "mode": (
            "comparison"
            if len(selected_documents) > 1
            else "document" if selected_documents else "global"
        ),
        "target_document": document.get("file_name") if document else None,
        "target_documents": [item["file_name"] for item in selected_documents],
        "candidate_count": len(candidates),
        "returned_count": len(reranked),
        "response_mode": profile.name,
        "cache_hit": False,
        "username": current_username(),
        "collection": get_active_collection_name(),
        "documents": sorted(
            {
                (chunk.get("metadata") or {}).get("file_name", "document necunoscut")
                for chunk in reranked
            }
        ),
        "retrieval_seconds": round(time.perf_counter() - retrieval_started, 4),
    }
    set_cached_retrieval(cache_key, reranked, debug)
    return reranked, debug


def chunk_source_label(chunk: dict) -> str:
    metadata = chunk.get("metadata") or {}
    file_name = metadata.get("file_name") or metadata.get("filename") or "document necunoscut"
    page = metadata.get("page_number") or metadata.get("page_label") or metadata.get("page")
    score = chunk.get("rerank_score")
    label = f"{file_name}, pagina {page}" if page else file_name
    if score is not None:
        label += f" | scor rerank: {score:.2f}"
    return label


def build_context(
    chunks: list[dict],
    max_context_chars: int,
) -> tuple[str, list[dict]]:
    context_parts = []
    used_chunks = []
    total_chars = 0
    for index, chunk in enumerate(chunks, start=1):
        text = chunk.get("text", "").strip()
        if not text:
            continue
        source = chunk_source_label(chunk)
        part = f"[Sursa {index}: {source}]\n{text}"
        remaining = max_context_chars - total_chars
        if remaining <= 200:
            break
        if len(part) > remaining:
            part = f"{part[:remaining].rsplit(' ', 1)[0]}..."
        context_parts.append(part)
        used_chunks.append(chunk)
        total_chars += len(part)
    return "\n\n".join(context_parts), used_chunks


def is_timeout_error(error: Exception) -> bool:
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return True
    message = str(error).lower()
    return any(
        phrase in message
        for phrase in ("timed out", "timeout", "read timeout", "deadline exceeded")
    )


def generation_llm(
    response_mode: str,
    max_output_tokens: int,
    model_name: str | None = None,
) -> Ollama:
    profile = get_response_profile(response_mode)
    model_name = model_name or getattr(Settings.llm, "model", DEFAULT_LLM_MODEL)
    return Ollama(
        model=model_name,
        base_url=OLLAMA_URL,
        request_timeout=max(180.0, profile.request_timeout),
        context_window=ollama_context_window(response_mode),
        additional_kwargs={
            "num_predict": max_output_tokens,
            "num_ctx": ollama_context_window(response_mode),
        },
        thinking=False,
        keep_alive="15m",
    )


def generate_prompt_text(
    prompt: str,
    response_mode: str,
    max_output_tokens: int,
    stream_callback: Callable[[str], None] | None = None,
    allow_partial_timeout: bool = False,
    model_name: str | None = None,
) -> tuple[str, bool]:
    enforce_streamlit_action_limit()
    with streamlit_action_slot():
        return _generate_prompt_text(
            prompt,
            response_mode,
            max_output_tokens,
            stream_callback=stream_callback,
            allow_partial_timeout=allow_partial_timeout,
            model_name=model_name,
        )


def _generate_prompt_text(
    prompt: str,
    response_mode: str,
    max_output_tokens: int,
    stream_callback: Callable[[str], None] | None = None,
    allow_partial_timeout: bool = False,
    model_name: str | None = None,
) -> tuple[str, bool]:
    llm = generation_llm(response_mode, max_output_tokens, model_name=model_name)
    answer_parts: list[str] = []
    last_stream_update = 0.0
    try:
        with INFERENCE_QUEUE.llm_slot() as queued_request:
            for completion in llm.stream_complete(prompt):
                queued_request.raise_if_cancelled()
                delta = completion.delta or ""
                if not delta:
                    continue
                answer_parts.append(delta)
                if stream_callback is not None:
                    now = time.monotonic()
                    if now - last_stream_update >= 0.05:
                        stream_callback(clean_model_text("".join(answer_parts)))
                        last_stream_update = now
    except Exception as exc:
        if isinstance(exc, (QueueWaitTimeoutError, RequestCancelledError)):
            raise
        if is_timeout_error(exc):
            partial_text = clean_model_text("".join(answer_parts))
            if allow_partial_timeout:
                return partial_text, True
            raise GenerationTimeoutError(
                "Modelul a depasit timpul de raspuns. Incearca modul Fast "
                "sau redu lungimea maxima a raspunsului."
            ) from exc
        raise

    answer = clean_model_text("".join(answer_parts))
    if stream_callback is not None and answer:
        stream_callback(answer)
    return answer, False


def course_summary_cache_key(
    document: dict,
    topic: str,
    response_mode: str,
    max_chunks: int,
    max_summary_tokens: int,
    model_name: str | None = None,
) -> tuple:
    return (
        get_active_collection_name(),
        count_indexed_chunks(),
        model_name or getattr(Settings.llm, "model", DEFAULT_LLM_MODEL),
        document.get("file_path") or document.get("file_name"),
        int(document.get("chunks", 0)),
        searchable_text(topic),
        response_mode,
        max_chunks,
        max_summary_tokens,
    )


def get_cached_course_summary(key: tuple) -> dict | None:
    with COURSE_SUMMARY_CACHE_LOCK:
        cached = COURSE_SUMMARY_CACHE.get(key)
        if cached is None:
            return None
        COURSE_SUMMARY_CACHE.move_to_end(key)
        result = copy.deepcopy(cached)
    result["cache_hit"] = True
    return result


def set_cached_course_summary(key: tuple, summary: dict) -> None:
    with COURSE_SUMMARY_CACHE_LOCK:
        COURSE_SUMMARY_CACHE[key] = copy.deepcopy(summary)
        COURSE_SUMMARY_CACHE.move_to_end(key)
        while len(COURSE_SUMMARY_CACHE) > COURSE_SUMMARY_CACHE_MAX_ENTRIES:
            COURSE_SUMMARY_CACHE.popitem(last=False)


def extractive_course_summary(
    document: dict,
    topic: str,
    chunks: list[dict],
    max_chars: int = 2600,
) -> str:
    lines = [
        f"Rezumat partial pentru {document['file_name']} despre {topic}:",
    ]
    current_length = len(lines[0])
    for chunk in chunks:
        text = " ".join(chunk.get("text", "").split())
        if not text:
            continue
        source = chunk_source_label(chunk)
        remaining = max_chars - current_length
        if remaining <= 120:
            break
        excerpt = text[: min(650, remaining)]
        if len(text) > len(excerpt):
            excerpt = f"{excerpt.rsplit(' ', 1)[0]}..."
        line = f"- [{source}] {excerpt}"
        lines.append(line)
        current_length += len(line)
    return "\n".join(lines)


def summarize_course_for_comparison(
    document: dict,
    topic: str,
    response_mode: str,
    max_chunks: int,
    max_summary_tokens: int,
    model_name: str,
) -> dict:
    cache_key = course_summary_cache_key(
        document,
        topic,
        response_mode,
        max_chunks,
        max_summary_tokens,
        model_name,
    )
    cached = get_cached_course_summary(cache_key)
    if cached is not None:
        return cached

    retrieval_question = (
        f"Identifica ideile din {document['file_name']} relevante pentru comparatia "
        f"despre: {topic}. Definitii, relatii, formule, exemple si concluzii."
    )
    chunks, retrieval_debug = retrieve_chunks(
        retrieval_question,
        document=document,
        top_k=max_chunks,
        summary_mode=False,
        response_mode=response_mode,
    )
    profile = get_response_profile(response_mode)
    context_limit = min(
        profile.max_context_chars,
        max(3500, max_chunks * 2400),
    )
    context, used_chunks = build_context(chunks, context_limit)
    prompt = (
        "/no_think\n"
        "Rezuma un singur curs pentru o comparatie ulterioara. "
        "Foloseste exclusiv fragmentele primite. Pastreaza numai informatia "
        "relevanta pentru tema si include citari [document, pagina]. "
        "Nu compara inca acest curs cu alte cursuri.\n\n"
        f"Document: {document['file_name']}\n"
        f"Tema comparatiei: {topic}\n\n"
        f"Fragmente:\n{context}\n\n"
        "Rezumat structurat:"
    )

    summary_text, timed_out = generate_prompt_text(
        prompt,
        response_mode=response_mode,
        max_output_tokens=max_summary_tokens,
        allow_partial_timeout=True,
        model_name=model_name,
    )
    partial = timed_out or not summary_text.strip()
    if partial:
        generated_part = (
            f"{summary_text}\n\n"
            if summary_text.strip()
            else ""
        )
        summary_text = generated_part + extractive_course_summary(
            document,
            topic,
            used_chunks,
        )

    result = {
        "document": document,
        "summary": summary_text,
        "chunks": used_chunks,
        "cache_hit": False,
        "partial": partial,
        "retrieval_debug": retrieval_debug,
    }
    set_cached_course_summary(cache_key, result)
    return result


def partial_comparison_answer(
    topic: str,
    course_summaries: list[dict],
    generated_text: str = "",
    answer_mode: str = "Analiză",
) -> str:
    sections = []
    if answer_mode == "Analiză":
        sections.extend(
            [
                "Aceasta este o evaluare inferențială bazată pe conținutul cursurilor.",
                "## Fapte din cursuri",
            ]
        )
    if generated_text.strip():
        sections.append(generated_text.strip())
    sections.append(
        "Comparația completă a fost întreruptă, dar dovezile disponibile sunt:"
    )
    for item in course_summaries:
        status = " (parțial)" if item.get("partial") else ""
        sections.append(
            f"### {item['document']['file_name']}{status}\n{item['summary']}"
        )
    if answer_mode == "Analiză":
        sections.extend(
            [
                "## Inferență / analiză",
                (
                    "Dovezile de mai sus pot susține o comparație, însă generarea "
                    "clasamentului complet a fost întreruptă. Nu transform acest rezultat "
                    "parțial într-o certitudine nejustificată."
                ),
                "## Concluzie",
                (
                    "Rezultat parțial: criteriile și fragmentele relevante sunt păstrate "
                    "mai sus. Reîncercarea poate folosi cache-ul acestor rezumate."
                ),
            ]
        )
    else:
        sections.append(f"Tema comparației: {topic}")
    return "\n\n".join(sections)


def extract_course_evidence_for_comparison(
    document: dict,
    topic: str,
    response_mode: str,
    max_chunks: int,
    max_chars: int,
) -> dict:
    cache_key = (
        "extractive-comparison",
        *course_summary_cache_key(document, topic, response_mode, max_chunks, max_chars),
    )
    cached = get_cached_course_summary(cache_key)
    if cached is not None:
        return cached

    retrieval_question = (
        f"Analizeaza {document['file_name']} pentru: {topic}. Cauta concepte noi, "
        "abstractizare, formule si matematica, cunostinte prealabile, aplicatii, "
        "relevanta clinica sau medicala, dimensiunea capitolelor, densitatea "
        "terminologiei, conexiunile cu alte cursuri si dificultate conceptuala."
    )
    chunks, retrieval_debug = retrieve_chunks(
        retrieval_question,
        document=document,
        top_k=max_chunks,
        summary_mode=False,
        response_mode=response_mode,
    )
    result = {
        "document": document,
        "summary": extractive_course_summary(
            document,
            topic,
            chunks,
            max_chars=max_chars,
        ),
        "chunks": chunks,
        "cache_hit": False,
        "partial": False,
        "retrieval_debug": retrieval_debug,
    }
    set_cached_course_summary(cache_key, result)
    return result


def compare_courses_hierarchically(
    topic: str,
    documents: list[dict],
    response_mode: str = DEFAULT_RESPONSE_MODE,
    answer_mode: str = DEFAULT_ANSWER_MODE,
    knowledge_mode: str = "Documents only",
    max_chunks_per_course: int | None = None,
    max_answer_tokens: int | None = None,
    stream_callback: Callable[[str], None] | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> StudyResponse:
    profile = get_response_profile(response_mode)
    effective_answer_mode = resolve_answer_mode(answer_mode, f"Compara cursuri: {topic}")
    summary_model_route = select_model_for_mode(
        topic,
        response_mode,
        "Strict",
        "Documents only",
        "rag",
    )
    synthesis_model_route = select_model_for_mode(
        topic,
        response_mode,
        answer_mode,
        knowledge_mode,
        "synthesis",
    )
    max_chunks = max(
        1,
        max_chunks_per_course or profile.comparison_chunks_per_course,
    )
    answer_tokens = max(
        300,
        max_answer_tokens or profile.comparison_answer_tokens,
    )
    summary_tokens = min(800, max(320, answer_tokens // 2))
    use_extractive_summaries = len(documents) > 6
    per_course_chars = max(
        700,
        min(2200, profile.max_context_chars // max(1, len(documents))),
    )

    course_summaries = []
    all_chunks = []
    for index, document in enumerate(documents, start=1):
        if progress_callback is not None:
            progress_callback(
                f"Rezumat {index}/{len(documents)}: {document['file_name']}"
            )
        try:
            if use_extractive_summaries:
                summary = extract_course_evidence_for_comparison(
                    document,
                    topic,
                    response_mode,
                    max_chunks,
                    per_course_chars,
                )
            else:
                summary = summarize_course_for_comparison(
                    document,
                    topic,
                    response_mode,
                    max_chunks,
                    summary_tokens,
                    summary_model_route.model,
                )
        except Exception as exc:
            if not is_timeout_error(exc) and not isinstance(exc, GenerationTimeoutError):
                raise
            summary = {
                "document": document,
                "summary": (
                    f"Rezumat indisponibil pentru {document['file_name']}: "
                    "căutarea sau generarea a depășit timpul disponibil."
                ),
                "chunks": [],
                "cache_hit": False,
                "partial": True,
                "retrieval_debug": {},
            }
        course_summaries.append(summary)
        all_chunks.extend(summary["chunks"])

    summary_context = "\n\n".join(
        f"=== {item['document']['file_name']} ===\n{item['summary']}"
        for item in course_summaries
    )
    memory_context = build_study_memory_context(
        topic,
        detect_study_topic(topic),
        None,
        limit=profile.memory_items,
    )
    if effective_answer_mode == "Strategie de învățare":
        memory_context += "\n\n" + build_strategy_memory_context(profile.memory_items + 2)
    comparison_prompt = (
        "/no_think\n"
        "Esti Co-pilot Facultate, un tutore universitar. Analizeaza rezumatele de curs "
        "de mai jos ca dovezi. Nu inventa documente, pagini sau fapte. Pastreaza "
        "citarile existente si sustine fiecare concluzie prin ele. "
        f"{REASONING_INSTRUCTION_CONTEXT.get()} "
        f"{answer_mode_instruction(effective_answer_mode)} "
        f"Nu depasi aproximativ {answer_tokens} tokeni.\n\n"
        f"Tema: {topic}\n\n"
        f"User study memory:\n{memory_context}\n\n"
        f"Rezumate pe curs:\n{summary_context}\n\n"
        "Raspuns in romana:"
    )
    if progress_callback is not None:
        progress_callback("Compar rezumatele cursurilor...")

    comparison_text, final_timed_out = generate_prompt_text(
        comparison_prompt,
        response_mode=response_mode,
        max_output_tokens=answer_tokens,
        stream_callback=stream_callback,
        allow_partial_timeout=True,
        model_name=synthesis_model_route.model,
    )
    partial = final_timed_out or any(item["partial"] for item in course_summaries)
    if final_timed_out or not comparison_text.strip():
        comparison_text = partial_comparison_answer(
            topic,
            course_summaries,
            generated_text=comparison_text,
            answer_mode=effective_answer_mode,
        )
        if stream_callback is not None:
            stream_callback(comparison_text)

    used_chunks = unique_chunks(all_chunks)
    debug = {
        "mode": "comparison_hierarchical",
        "response_mode": response_mode,
        "answer_mode_requested": answer_mode,
        "answer_mode": effective_answer_mode,
        "selected_model": synthesis_model_route.model,
        "model_profile": synthesis_model_route.profile,
        "model_routing_reason": synthesis_model_route.reason,
        "model_stages": {
            "rag": summary_model_route.model,
            "synthesis": synthesis_model_route.model,
        },
        "rag_used": True,
        "general_knowledge_used": False,
        "target_documents": [document["file_name"] for document in documents],
        "documents": [document["file_name"] for document in documents],
        "candidate_count": sum(
            item.get("retrieval_debug", {}).get("candidate_count", 0)
            for item in course_summaries
        ),
        "returned_count": len(used_chunks),
        "context_chunk_count": 0,
        "context_chars": len(summary_context),
        "cache_hit": all(item["cache_hit"] for item in course_summaries),
        "max_chunks_per_course": max_chunks,
        "max_answer_tokens": answer_tokens,
        "partial": partial,
        "extractive_course_summaries": use_extractive_summaries,
        "course_summaries": [
            {
                "document": item["document"]["file_name"],
                "cache_hit": item["cache_hit"],
                "partial": item["partial"],
                "chunks": len(item["chunks"]),
            }
            for item in course_summaries
        ],
        "retrieval_seconds": round(
            sum(
                float(item.get("retrieval_debug", {}).get("retrieval_seconds") or 0)
                for item in course_summaries
            ),
            4,
        ),
    }
    return StudyResponse(comparison_text, used_chunks, debug)


def complete_from_chunks(
    question: str,
    chunks: list[dict],
    debug: dict,
    document: dict | None = None,
    documents: list[dict] | None = None,
    summary_mode: bool = False,
    memory_context: str = "",
    task_override: str | None = None,
    response_mode: str = DEFAULT_RESPONSE_MODE,
    answer_mode: str = DEFAULT_ANSWER_MODE,
    knowledge_mode: str = "Documents only",
    model_stage: str = "rag",
    stream_callback: Callable[[str], None] | None = None,
) -> StudyResponse:
    if not chunks:
        return StudyResponse("Nu am gasit fragmente relevante in documentele indexate.", [], debug)

    profile = get_response_profile(response_mode)
    context, used_chunks = build_context(chunks, profile.max_context_chars)
    debug = dict(debug)
    debug["context_chunk_count"] = len(used_chunks)
    debug["context_chars"] = len(context)
    effective_answer_mode = resolve_answer_mode(answer_mode, question)
    debug["answer_mode_requested"] = answer_mode
    debug["answer_mode"] = effective_answer_mode
    model_route = select_model_for_mode(
        question,
        response_mode,
        answer_mode,
        knowledge_mode,
        model_stage,
    )
    debug["selected_model"] = model_route.model
    debug["model_profile"] = model_route.profile
    debug["model_routing_reason"] = model_route.reason
    debug["rag_used"] = True
    debug["general_knowledge_used"] = False
    selected_documents = documents or ([document] if document else [])
    target = (
        "Documente tinta: "
        + ", ".join(item["file_name"] for item in selected_documents)
        + "\n"
        if selected_documents
        else ""
    )
    task = task_override or (
        "Fa un rezumat clar al documentului tinta."
        if summary_mode
        else "Raspunde la intrebare folosind numai contextul de mai jos."
    )
    prompt = build_answer_prompt(
        question=question,
        context=context,
        memory_context=memory_context,
        target=target,
        task=task,
        response_instruction=profile.answer_instruction,
        answer_mode=effective_answer_mode,
    )
    llm = generation_llm(
        response_mode,
        profile.max_output_tokens,
        model_name=model_route.model,
    )
    try:
        with INFERENCE_QUEUE.llm_slot() as queued_request:
            if stream_callback is not None:
                answer_parts = []
                last_stream_update = 0.0
                for completion in llm.stream_complete(prompt):
                    queued_request.raise_if_cancelled()
                    delta = completion.delta or ""
                    if not delta:
                        continue
                    answer_parts.append(delta)
                    now = time.monotonic()
                    if now - last_stream_update >= 0.05:
                        stream_callback(clean_model_text("".join(answer_parts)))
                        last_stream_update = now
                answer = "".join(answer_parts)
                if answer:
                    stream_callback(clean_model_text(answer))
            else:
                queued_request.raise_if_cancelled()
                answer = str(llm.complete(prompt))
                queued_request.raise_if_cancelled()
    except Exception as exc:
        if isinstance(exc, (QueueWaitTimeoutError, RequestCancelledError)):
            raise
        if is_timeout_error(exc):
            raise GenerationTimeoutError(
                "Modelul a depasit timpul de raspuns. Incearca modul Fast, "
                "o intrebare mai specifica sau un document anume."
            ) from exc
        raise
    return StudyResponse(clean_model_text(answer), used_chunks, debug)


def query_documents(
    question: str,
    top_k: int | None = None,
    document_override: dict | None = None,
    documents_override: list[dict] | None = None,
    summary_mode_override: bool | None = None,
    force_global: bool = False,
    task_override: str | None = None,
    response_mode: str = DEFAULT_RESPONSE_MODE,
    answer_mode: str = DEFAULT_ANSWER_MODE,
    knowledge_mode: str = "Documents only",
    stream_callback: Callable[[str], None] | None = None,
):
    effective_answer_mode = resolve_answer_mode(answer_mode, question)
    referenced_documents = [] if force_global else detect_document_references(question)
    if documents_override:
        document = None
        selected_documents = documents_override
    elif document_override:
        document = document_override
        selected_documents = [document_override]
    elif len(referenced_documents) > 1:
        document = None
        selected_documents = referenced_documents
    else:
        document = None if force_global else (
            referenced_documents[0]
            if referenced_documents
            else detect_document_reference(question)
        )
        selected_documents = [document] if document else []
    selected_documents = normalize_document_selection(selected_documents)
    document = selected_documents[0] if len(selected_documents) == 1 else None

    if needs_cross_document_reasoning(
        question,
        effective_answer_mode,
        selected_documents,
    ):
        reasoning_documents = selected_documents if len(selected_documents) > 1 else get_indexed_documents()
        if len(reasoning_documents) > 1:
            return compare_courses_hierarchically(
                topic=question,
                documents=reasoning_documents,
                response_mode=response_mode,
                answer_mode=effective_answer_mode,
                knowledge_mode=knowledge_mode,
                stream_callback=stream_callback,
            )
    summary_mode = (
        summary_mode_override
        if summary_mode_override is not None
        else bool(document and is_document_summary_question(question))
    )
    topic = detect_study_topic(question, document)
    profile = get_response_profile(response_mode)
    memory_context = build_study_memory_context(
        question,
        topic,
        document,
        limit=profile.memory_items,
    )
    if effective_answer_mode == "Strategie de învățare":
        memory_context += "\n\n" + build_strategy_memory_context(profile.memory_items + 2)
    try:
        chunks, debug = retrieve_chunks(
            question,
            document=document,
            documents=selected_documents,
            top_k=top_k,
            summary_mode=summary_mode,
            response_mode=response_mode,
        )
    except Exception as exc:
        if is_timeout_error(exc):
            raise GenerationTimeoutError(
                "Cautarea in documente a depasit timpul disponibil. Incearca "
                "modul Fast sau selecteaza un document anume."
            ) from exc
        raise
    return complete_from_chunks(
        question,
        chunks,
        debug,
        document=document,
        documents=selected_documents,
        summary_mode=summary_mode,
        memory_context=memory_context,
        task_override=task_override,
        response_mode=response_mode,
        answer_mode=answer_mode,
        knowledge_mode=knowledge_mode,
        stream_callback=stream_callback,
    )


def annotate_route(
    response: StudyResponse,
    intent: str,
    confidence: float,
    knowledge_mode: str,
    route: str,
    reason: str,
) -> StudyResponse:
    response.debug = dict(response.debug)
    response.debug.update(
        {
            "intent": intent,
            "confidence": round(max(0.0, min(1.0, confidence)), 2),
            "knowledge_mode": knowledge_mode,
            "knowledge_route": route,
            "routing_reason": reason,
        }
    )
    return response


def answer_general_question(
    question: str,
    response_mode: str,
    answer_mode: str,
    stream_callback: Callable[[str], None] | None = None,
) -> StudyResponse:
    profile = get_response_profile(response_mode)
    effective_answer_mode = resolve_answer_mode(answer_mode, question)
    topic = detect_study_topic(question)
    memory_context = build_study_memory_context(
        question,
        topic,
        None,
        limit=profile.memory_items,
    )
    if effective_answer_mode == "Strategie de învățare":
        memory_context += "\n\n" + build_strategy_memory_context(profile.memory_items + 2)
    model_route = select_model_for_mode(
        question,
        response_mode,
        answer_mode,
        "General knowledge only",
        "general",
    )
    mode_instruction = answer_mode_instruction(effective_answer_mode)
    if effective_answer_mode == "Strict":
        mode_instruction = (
            "MOD STRICT GENERAL: ofera numai fapte generale consacrate si cu incredere "
            "ridicata. Nu presupune detalii si semnaleaza orice incertitudine. Lipsa "
            "contextului RAG nu este un motiv de refuz in acest mod."
        )
    prompt = (
        "/no_think\n"
        "Esti Co-pilot Facultate. Raspunde folosind cunostintele generale ale modelului, "
        "fara sa cauti in documentele utilizatorului. Nu inventa citari, documente sau "
        "pagini. Daca un fapt este incert, spune clar acest lucru. Nu refuza doar pentru "
        "ca nu ai context RAG. Raspunde in limba intrebarii.\n"
        f"{REASONING_INSTRUCTION_CONTEXT.get()}\n"
        f"{mode_instruction}\n"
        f"{profile.answer_instruction}\n\n"
        f"User study memory (folosita numai pentru personalizare):\n{memory_context}\n\n"
        f"Intrebare: {question}\n\n"
        "Raspuns:"
    )
    answer, _ = generate_prompt_text(
        prompt,
        response_mode=response_mode,
        max_output_tokens=profile.max_output_tokens,
        stream_callback=stream_callback,
        model_name=model_route.model,
    )
    return StudyResponse(
        answer,
        [],
        {
            "mode": "general_knowledge",
            "response_mode": response_mode,
            "answer_mode_requested": answer_mode,
            "answer_mode": effective_answer_mode,
            "documents": [],
            "context_chunk_count": 0,
            "context_chars": 0,
            "selected_model": model_route.model,
            "model_profile": model_route.profile,
            "model_routing_reason": model_route.reason,
            "model_stages": {"general": model_route.model},
            "rag_used": False,
            "general_knowledge_used": True,
        },
    )


def _legacy_complete_hybrid_from_chunks(
    question: str,
    chunks: list[dict],
    debug: dict,
    response_mode: str,
    answer_mode: str,
    memory_context: str,
    stream_callback: Callable[[str], None] | None = None,
) -> StudyResponse:
    profile = get_response_profile(response_mode)
    effective_answer_mode = resolve_answer_mode(answer_mode, question)
    context, used_chunks = build_context(chunks, profile.max_context_chars)
    if not context:
        context = "Nu au fost gasite dovezi suficient de relevante in documentele incarcate."
    mode_instruction = answer_mode_instruction(effective_answer_mode)
    if effective_answer_mode == "Strict":
        mode_instruction = (
            "MOD STRICT HIBRID: pentru partea de curs foloseste numai fapte explicite "
            "din context; pentru partea generala foloseste numai fapte consacrate cu "
            "incredere ridicata. Nu amesteca cele doua categorii si semnaleaza incertitudinea."
        )
    prompt = (
        "/no_think\n"
        "Esti Co-pilot Facultate in mod hibrid. Combina dovezile din cursurile "
        "utilizatorului cu propriile cunostinte generale. Nu inventa citari. "
        "Citeaza [document, pagina] numai pentru afirmatiile sustinute de contextul RAG. "
        "Pentru informatia generala spune explicit ca provine din cunostinte generale, "
        "fara citare de curs. Daca partea specifica documentelor lipseste, mentioneaza "
        "scurt acest fapt, apoi raspunde util din cunostinte generale atunci cand este "
        "rezonabil. Structureaza raspunsul in «Din documentele tale», «Cunoștințe "
        "generale» si «Legătura / concluzia». Raspunde in limba intrebarii.\n"
        f"{REASONING_INSTRUCTION_CONTEXT.get()}\n"
        f"{mode_instruction}\n"
        f"{profile.answer_instruction}\n\n"
        f"User study memory:\n{memory_context}\n\n"
        f"Context RAG din cursuri:\n{context}\n\n"
        f"Intrebare: {question}\n\n"
        "Raspuns hibrid:"
    )
    answer, _ = generate_prompt_text(
        prompt,
        response_mode=response_mode,
        max_output_tokens=profile.max_output_tokens,
        stream_callback=stream_callback,
    )
    hybrid_debug = dict(debug)
    hybrid_debug.update(
        {
            "mode": "hybrid",
            "response_mode": response_mode,
            "answer_mode_requested": answer_mode,
            "answer_mode": effective_answer_mode,
            "context_chunk_count": len(used_chunks),
            "context_chars": len(context),
        }
    )
    return StudyResponse(answer, used_chunks, hybrid_debug)


def complete_hybrid_from_chunks(
    question: str,
    chunks: list[dict],
    debug: dict,
    response_mode: str,
    answer_mode: str,
    memory_context: str,
    stream_callback: Callable[[str], None] | None = None,
) -> StudyResponse:
    profile = get_response_profile(response_mode)
    effective_answer_mode = resolve_answer_mode(answer_mode, question)
    context, used_chunks = build_context(chunks, profile.max_context_chars)
    rag_route = select_model_for_mode(
        question, response_mode, "Strict", "Documents only", "rag"
    )
    general_route = select_model_for_mode(
        question, response_mode, "Auto", "General knowledge only", "general"
    )
    synthesis_mode = "Strict" if effective_answer_mode == "Strict" else "Analiză"
    synthesis_route = select_model_for_mode(
        question,
        response_mode,
        synthesis_mode,
        "Hybrid (recommended)",
        "synthesis",
    )

    if context:
        rag_prompt = (
            "/no_think\n"
            "Extrage doar dovezile relevante pentru intrebare din contextul cursurilor. "
            "Nu folosi cunostinte externe si nu inventa. Pastreaza citarile exacte "
            "[document, pagina]. Daca dovezile sunt incomplete, spune clar ce lipseste. "
            "Raspunde in limba intrebarii.\n\n"
            f"User study memory:\n{memory_context}\n\n"
            f"Context RAG:\n{context}\n\n"
            f"Intrebare: {question}\n\n"
            "Dovezi din cursuri:"
        )
        rag_answer, _ = generate_prompt_text(
            rag_prompt,
            response_mode=response_mode,
            max_output_tokens=max(300, profile.max_output_tokens // 2),
            model_name=rag_route.model,
        )
    else:
        rag_answer = "Nu au fost gasite dovezi relevante in documentele incarcate."

    general_prompt = (
        "/no_think\n"
        "Raspunde folosind cunostinte generale solide. Nu pretinde ca informatia provine "
        "din cursurile utilizatorului si nu crea citari de documente. Semnaleaza prudent "
        "orice incertitudine. Raspunde in limba intrebarii.\n\n"
        f"Intrebare: {question}\n\n"
        "Cunostinte generale relevante:"
    )
    general_answer, _ = generate_prompt_text(
        general_prompt,
        response_mode=response_mode,
        max_output_tokens=max(300, profile.max_output_tokens // 2),
        model_name=general_route.model,
    )

    source_hints = []
    for chunk in used_chunks:
        metadata = chunk.get("metadata") or {}
        file_name = metadata.get("file_name", "document necunoscut")
        page = metadata.get("page_number") or metadata.get("page_label") or "-"
        source_hints.append(f"[{file_name}, pagina {page}]")

    synthesis_prompt = (
        "/no_think\n"
        "Esti Co-pilot Facultate. Sintetizeaza componentele de mai jos intr-un raspuns util "
        "si riguros. Nu inventa citari. Pastreaza [document, pagina] numai langa "
        "afirmatiile sustinute de cursuri. Delimiteaza clar informatia externa. "
        "Structureaza raspunsul in: Din documentele tale, Cunoștințe generale, "
        "Legătura / concluzia. Raspunde in limba intrebarii.\n"
        f"{REASONING_INSTRUCTION_CONTEXT.get()}\n"
        f"{answer_mode_instruction(effective_answer_mode)}\n"
        f"{profile.answer_instruction}\n\n"
        f"Intrebare: {question}\n\n"
        f"Surse RAG disponibile: {', '.join(source_hints) or 'niciuna'}\n\n"
        f"Componenta RAG:\n{rag_answer}\n\n"
        f"Componenta generala:\n{general_answer}\n\n"
        "Raspuns final:"
    )
    answer, _ = generate_prompt_text(
        synthesis_prompt,
        response_mode=response_mode,
        max_output_tokens=profile.max_output_tokens,
        stream_callback=stream_callback,
        model_name=synthesis_route.model,
    )
    hybrid_debug = dict(debug)
    hybrid_debug.update(
        {
            "mode": "hybrid",
            "response_mode": response_mode,
            "answer_mode_requested": answer_mode,
            "answer_mode": effective_answer_mode,
            "context_chunk_count": len(used_chunks),
            "context_chars": len(context),
            "selected_model": synthesis_route.model,
            "model_profile": synthesis_route.profile,
            "model_routing_reason": synthesis_route.reason,
            "model_stages": {
                "rag": rag_route.model if used_chunks else None,
                "general": general_route.model,
                "synthesis": synthesis_route.model,
            },
            "rag_used": bool(used_chunks),
            "general_knowledge_used": True,
        }
    )
    return StudyResponse(answer, used_chunks, hybrid_debug)


def hybrid_retrieval_context(
    question: str,
    response_mode: str,
    document_override: dict | None = None,
    documents_override: list[dict] | None = None,
    summary_mode_override: bool | None = None,
) -> tuple[list[dict], dict, dict | None, list[dict], str]:
    referenced_documents = detect_document_references(question)
    if documents_override:
        document = None
        selected_documents = documents_override
    elif document_override:
        document = document_override
        selected_documents = [document_override]
    elif len(referenced_documents) > 1:
        document = None
        selected_documents = referenced_documents
    else:
        document = referenced_documents[0] if referenced_documents else detect_document_reference(question)
        selected_documents = [document] if document else []
    selected_documents = normalize_document_selection(selected_documents)
    document = selected_documents[0] if len(selected_documents) == 1 else None
    summary_mode = (
        summary_mode_override
        if summary_mode_override is not None
        else bool(document and is_document_summary_question(question))
    )
    chunks, debug = retrieve_chunks(
        question,
        document=document,
        documents=selected_documents,
        summary_mode=summary_mode,
        response_mode=response_mode,
    )
    profile = get_response_profile(response_mode)
    topic = detect_study_topic(question, document)
    memory_context = build_study_memory_context(
        question,
        topic,
        document,
        limit=profile.memory_items,
    )
    return chunks, debug, document, selected_documents, memory_context


def _execute_reasoning_plan(
    question: str,
    plan: ReasoningPlan,
    document_override: dict | None = None,
    documents_override: list[dict] | None = None,
    summary_mode_override: bool | None = None,
    task_override: str | None = None,
    response_mode: str = DEFAULT_RESPONSE_MODE,
    answer_mode: str = DEFAULT_ANSWER_MODE,
    knowledge_mode: str = DEFAULT_KNOWLEDGE_MODE,
    stream_callback: Callable[[str], None] | None = None,
) -> StudyResponse:
    selected_knowledge_mode = (
        knowledge_mode
        if knowledge_mode in KNOWLEDGE_MODE_OPTIONS
        else DEFAULT_KNOWLEDGE_MODE
    )
    decision = detect_user_intent(question)

    if plan.needs_cross_document_reasoning and selected_knowledge_mode != "General knowledge only":
        response = query_documents(
            question,
            document_override=document_override,
            documents_override=documents_override,
            summary_mode_override=summary_mode_override,
            force_global=not bool(documents_override),
            task_override=task_override,
            response_mode=response_mode,
            answer_mode=plan.answer_mode,
            knowledge_mode=selected_knowledge_mode,
            stream_callback=stream_callback,
        )
        return annotate_route(
            response,
            plan.intent,
            0.9,
            selected_knowledge_mode,
            "rag",
            "planul de raționament cere evaluarea comparativă a documentelor",
        )

    if selected_knowledge_mode == "General knowledge only":
        response = answer_general_question(
            question,
            response_mode,
            answer_mode,
            stream_callback,
        )
        return annotate_route(
            response,
            decision.intent,
            0.99,
            selected_knowledge_mode,
            "general",
            "modul General knowledge only a fost selectat",
        )

    if selected_knowledge_mode == "Documents only":
        if count_indexed_chunks() == 0:
            return annotate_route(
                StudyResponse(
                    "Nu există documente indexate pentru modul Documents only.",
                    [],
                    {"mode": "documents_only_empty", "documents": []},
                ),
                decision.intent,
                0.1,
                selected_knowledge_mode,
                "rag",
                "nu există documente indexate",
            )
        response = query_documents(
            question,
            document_override=document_override,
            documents_override=documents_override,
            summary_mode_override=summary_mode_override,
            task_override=task_override,
            response_mode=response_mode,
            answer_mode=answer_mode,
            knowledge_mode=selected_knowledge_mode,
            stream_callback=stream_callback,
        )
        confidence = 0.92 if response.chunks else 0.2
        return annotate_route(
            response,
            decision.intent,
            confidence,
            selected_knowledge_mode,
            "rag",
            "modul Documents only a fost selectat",
        )

    if decision.explicit_general and decision.intent == "general_knowledge":
        response = answer_general_question(
            question,
            response_mode,
            answer_mode,
            stream_callback,
        )
        return annotate_route(
            response,
            decision.intent,
            decision.confidence,
            selected_knowledge_mode,
            "general",
            decision.reason,
        )

    document_intents = {
        "course_question",
        "document_search",
        "compare_documents",
        "study_planning",
        "flashcards",
        "quiz",
        "memory",
    }
    if decision.intent in document_intents and decision.intent != "mixed":
        response = query_documents(
            question,
            document_override=document_override,
            documents_override=documents_override,
            summary_mode_override=summary_mode_override,
            task_override=task_override,
            response_mode=response_mode,
            answer_mode=answer_mode,
            knowledge_mode=selected_knowledge_mode,
            stream_callback=stream_callback,
        )
        if response.chunks:
            return annotate_route(
                response,
                decision.intent,
                decision.confidence,
                selected_knowledge_mode,
                "rag",
                decision.reason,
            )

    if count_indexed_chunks() == 0:
        response = answer_general_question(
            question,
            response_mode,
            answer_mode,
            stream_callback,
        )
        return annotate_route(
            response,
            decision.intent,
            0.72,
            selected_knowledge_mode,
            "general",
            "nu există documente indexate; folosesc cunoștințe generale",
        )

    chunks, debug, _document, _documents, memory_context = hybrid_retrieval_context(
        question,
        response_mode,
        document_override=document_override,
        documents_override=documents_override,
        summary_mode_override=summary_mode_override,
    )
    top_score = max((float(chunk.get("rerank_score") or 0.0) for chunk in chunks), default=0.0)
    top_lexical = max((float(chunk.get("lexical_score") or 0.0) for chunk in chunks), default=0.0)

    if decision.intent == "mixed":
        response = complete_hybrid_from_chunks(
            question,
            chunks,
            debug,
            response_mode,
            answer_mode,
            memory_context,
            stream_callback,
        )
        confidence = max(decision.confidence, min(0.9, 0.45 + top_score / 2))
        return annotate_route(
            response,
            "mixed",
            confidence,
            selected_knowledge_mode,
            "hybrid",
            decision.reason,
        )

    if top_score >= 0.52 or top_lexical >= 0.16:
        response = complete_from_chunks(
            question,
            chunks,
            debug,
            memory_context=memory_context,
            response_mode=response_mode,
            answer_mode=answer_mode,
            knowledge_mode=selected_knowledge_mode,
            stream_callback=stream_callback,
        )
        return annotate_route(
            response,
            "course_question",
            min(0.95, 0.45 + top_score),
            selected_knowledge_mode,
            "rag",
            "documentele au relevanță semantică ridicată",
        )

    if top_score >= 0.38 or top_lexical > 0.0:
        response = complete_hybrid_from_chunks(
            question,
            chunks,
            debug,
            response_mode,
            answer_mode,
            memory_context,
            stream_callback,
        )
        return annotate_route(
            response,
            "mixed",
            min(0.84, 0.45 + top_score / 2),
            selected_knowledge_mode,
            "hybrid",
            "relevanță RAG posibilă, dar neconcludentă",
        )

    if decision.intent in document_intents:
        response = complete_hybrid_from_chunks(
            question,
            chunks,
            debug,
            response_mode,
            answer_mode,
            memory_context,
            stream_callback,
        )
        return annotate_route(
            response,
            "mixed",
            0.42,
            selected_knowledge_mode,
            "hybrid",
            "documentele nu oferă dovezi suficiente; completez prudent din cunoștințe generale",
        )

    response = answer_general_question(
        question,
        response_mode,
        answer_mode,
        stream_callback,
    )
    return annotate_route(
        response,
        "general_knowledge",
        max(0.62, 1.0 - top_score),
        selected_knowledge_mode,
        "general",
        "relevanța documentelor este scăzută",
    )


def query_copilot(
    question: str,
    document_override: dict | None = None,
    documents_override: list[dict] | None = None,
    summary_mode_override: bool | None = None,
    task_override: str | None = None,
    response_mode: str = DEFAULT_RESPONSE_MODE,
    answer_mode: str = DEFAULT_ANSWER_MODE,
    knowledge_mode: str = DEFAULT_KNOWLEDGE_MODE,
    stream_callback: Callable[[str], None] | None = None,
) -> StudyResponse:
    request_started = time.perf_counter()
    available_documents = (
        len(documents_override)
        if documents_override is not None
        else len(get_indexed_documents())
    )
    has_conversation_context = "Contextul conversației anterioare" in question
    plan = build_reasoning_plan(
        question,
        knowledge_mode=knowledge_mode,
        available_documents=available_documents,
        has_conversation_context=has_conversation_context,
    )
    instruction_token = REASONING_INSTRUCTION_CONTEXT.set(plan.instruction)
    try:
        response = _execute_reasoning_plan(
            question,
            plan,
            document_override=document_override,
            documents_override=documents_override,
            summary_mode_override=summary_mode_override,
            task_override=task_override,
            response_mode=response_mode,
            answer_mode=answer_mode,
            knowledge_mode=knowledge_mode,
            stream_callback=stream_callback,
        )
        response = attach_reasoning_plan(response, plan)
        total_seconds = time.perf_counter() - request_started
        retrieval_seconds = float(response.debug.get("retrieval_seconds") or 0)
        response.debug["latency"] = {
            "retrieval_seconds": round(retrieval_seconds, 4),
            "inference_seconds": round(max(0.0, total_seconds - retrieval_seconds), 4),
            "total_seconds": round(total_seconds, 4),
        }
        return response
    finally:
        REASONING_INSTRUCTION_CONTEXT.reset(instruction_token)


def save_answer_to_memory(
    question: str,
    answer: str,
    response=None,
    selected_document: dict | None = None,
    session_id: str | None = None,
    infer_document: bool = True,
) -> dict:
    if selected_document is None and infer_document:
        selected_document = detect_document_reference(question)

    topic = detect_study_topic(question, selected_document)
    retrieved_documents = response_document_names(response)
    selected_document_name = (
        selected_document.get("file_name") if selected_document else None
    )
    history_id = record_study_history(
        MEMORY_DB_PATH,
        session_id=session_id or st.session_state.study_session_id,
        question=question.strip(),
        selected_document=selected_document_name,
        retrieved_documents=retrieved_documents,
        topic=topic,
        answer_summary=concise_answer_summary(answer),
        sources=response_source_records(response),
    )
    return {
        "history_id": history_id,
        "question": question.strip(),
        "answer": answer,
        "response": response,
        "topic": topic,
        "document_name": selected_document_name
        or (retrieved_documents[0] if len(retrieved_documents) == 1 else None),
    }


def extract_json_array(text: str) -> list[dict]:
    text = clean_model_text(text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return []
        else:
            try:
                data = json.loads(f"[{text.strip().strip(',')}]")
            except json.JSONDecodeError:
                return []

    if isinstance(data, dict):
        for key in ("flashcards", "quiz", "questions", "items"):
            value = data.get(key)
            if isinstance(value, list):
                data = value
                break
        else:
            data = [data]

    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def generate_flashcards(
    topic: str,
    count: int,
    response_mode: str = DEFAULT_RESPONSE_MODE,
) -> tuple[list[dict], object]:
    response = query_documents(
        "Genereaza "
        f"{count} flashcarduri despre: {topic}. "
        "Returneaza strict JSON, fara markdown, ca lista de obiecte cu cheile: "
        "front, back, source_hint. Fiecare flashcard trebuie sa fie verificabil din surse. "
        "Daca sursele nu contin destule informatii, returneaza []. Nu inventa.",
        response_mode=response_mode,
        answer_mode="Strict",
    )
    return extract_json_array(str(response)), response


def generate_quiz(
    topic: str,
    count: int,
    response_mode: str = DEFAULT_RESPONSE_MODE,
) -> tuple[list[dict], object]:
    response = query_documents(
        "Genereaza "
        f"{count} intrebari grila interactive despre: {topic}. "
        "Returneaza strict JSON, fara markdown, ca lista de obiecte cu cheile: "
        "question, options, answer_index, explanation, source_document, topic. "
        "options trebuie sa fie o lista cu 4 variante. answer_index este index 0-3. "
        "source_document trebuie sa fie numele documentului din care provine intrebarea. "
        "Daca sursele nu contin destule informatii, returneaza []. Nu inventa.",
        response_mode=response_mode,
        answer_mode="Strict",
    )
    return extract_json_array(str(response)), response


def format_source(source_node) -> str:
    metadata = source_node.node.metadata or {}
    file_name = metadata.get("file_name") or metadata.get("filename") or "document necunoscut"
    page = metadata.get("page_label") or metadata.get("page_number") or metadata.get("page")
    score = source_node.score

    location = f"{file_name}, pagina {page}" if page else file_name
    if score is None:
        return location

    return f"{location} | scor relevanta: {score:.2f}"


def render_sources(response) -> None:
    if isinstance(response, StudyResponse):
        if not response.chunks:
            st.write("Nu au fost returnate surse.")
            return
        for chunk in response.chunks:
            st.markdown(f"- {chunk_source_label(chunk)}")
            with st.expander("Fragment folosit"):
                st.write(chunk.get("text", ""))
        return

    if not response.source_nodes:
        st.write("Nu au fost returnate surse.")
        return

    for source in response.source_nodes:
        st.markdown(f"- {format_source(source)}")
        with st.expander("Fragment folosit"):
            st.write(source.node.get_content(metadata_mode="none"))


def render_retrieval_debug(response) -> None:
    if (
        not isinstance(response, StudyResponse)
        or not st.session_state.get("developer_mode", False)
    ):
        return

    with st.expander("Debug retrieval"):
        debug = response.debug
        st.write(f"Mod: {debug.get('mode')}")
        st.write(f"Profil raspuns: {debug.get('response_mode', DEFAULT_RESPONSE_MODE)}")
        st.write(f"Intenție detectată: {debug.get('intent', '-')}")
        st.write(f"Knowledge mode: {debug.get('knowledge_mode', '-')}")
        st.write(f"Answer mode: {debug.get('answer_mode', '-')}")
        st.write(f"Model Ollama: {debug.get('selected_model', '-')}")
        st.write(f"Motiv rutare: {debug.get('model_routing_reason', '-')}")
        st.write(f"RAG folosit: {'da' if debug.get('rag_used') else 'nu'}")
        st.write(
            "Cunoștințe generale folosite: "
            f"{'da' if debug.get('general_knowledge_used') else 'nu'}"
        )
        st.write(f"Retrieval cache: {'hit' if debug.get('cache_hit') else 'miss'}")
        if len(debug.get("target_documents") or []) > 1:
            st.write(f"Documente tinta: {', '.join(debug['target_documents'])}")
        elif debug.get("target_document"):
            st.write(f"Document tinta: {debug['target_document']}")
        st.write(f"Documente recuperate: {', '.join(debug.get('documents') or [])}")
        st.write(f"Chunk-uri candidate: {debug.get('candidate_count')}")
        st.write(f"Chunk-uri recuperate: {debug.get('returned_count')}")
        st.write(f"Chunk-uri trimise la model: {debug.get('context_chunk_count')}")
        st.write(f"Caractere context: {debug.get('context_chars')}")
        if debug.get("mode") == "comparison_hierarchical":
            st.write(f"Max. chunk-uri/curs: {debug.get('max_chunks_per_course')}")
            st.write(f"Max. tokeni raspuns: {debug.get('max_answer_tokens')}")
            st.write(f"Rezultat partial: {'da' if debug.get('partial') else 'nu'}")
            for item in debug.get("course_summaries") or []:
                st.write(
                    f"- {item['document']}: {item['chunks']} chunk-uri | "
                    f"cache: {'hit' if item['cache_hit'] else 'miss'} | "
                    f"partial: {'da' if item['partial'] else 'nu'}"
                )
        for index, chunk in enumerate(response.chunks, start=1):
            metadata = chunk.get("metadata") or {}
            st.write(
                f"{index}. {metadata.get('file_name', 'document necunoscut')} "
                f"pagina {metadata.get('page_number') or metadata.get('page_label') or '-'} | "
                f"distanta: {chunk.get('distance')} | "
                f"vector: {chunk.get('vector_score', 0):.2f} | "
                f"lexical: {chunk.get('lexical_score', 0):.2f} | "
                f"rerank: {chunk.get('rerank_score', 0):.2f}"
            )


def refresh_indexed_documents_state() -> None:
    documents = get_indexed_documents()
    ensure_document_metadata_records(documents)
    st.session_state.indexed_documents = get_indexed_documents()


def render_indexed_documents_panel() -> None:
    st.header("Documente indexate")

    if st.button("Refresh document list"):
        refresh_indexed_documents_state()

    documents = st.session_state.get("indexed_documents")
    if documents is None:
        documents = get_indexed_documents()
        st.session_state.indexed_documents = documents

    with st.expander("Gestionare documente", expanded=False):
        st.caption(
            "Acțiunile de aici afectează numai profilul curent: "
            f"{current_username()}."
        )
        col_reindex, col_delete = st.columns(2)
        with col_reindex:
            if st.button("Re-indexează toate documentele", use_container_width=True):
                try:
                    with st.spinner("Reconstruiesc indexul profilului curent..."):
                        file_count, chunk_count = reindex_current_user_documents()
                    refresh_indexed_documents_state()
                    st.success(
                        f"Re-indexare finalizată: {file_count} fișiere, "
                        f"{chunk_count} fragmente."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        with col_delete:
            confirm_all = st.text_input(
                "Pentru ștergere totală scrie utilizatorul curent",
                key="delete_all_documents_confirmation",
                placeholder=current_username(),
            )
            if st.button(
                "Șterge toate documentele profilului",
                type="secondary",
                use_container_width=True,
                disabled=confirm_all != current_username(),
            ):
                try:
                    removed = delete_all_current_user_documents()
                    st.session_state.indexed_documents = []
                    st.success(f"Am șters {removed} fișiere și indexul profilului.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    if not documents:
        st.caption("Nu exista documente indexate.")
        return

    st.caption(f"{len(documents)} documente unice pentru {current_username()}")
    grouped_documents = sorted(
        documents,
        key=lambda item: (
            item.get("academic_year") or "",
            item.get("subject") or item.get("discipline") or "",
            item.get("course") or "",
            item["file_name"].lower(),
        ),
    )
    current_group = None
    for document in grouped_documents:
        group = (
            document.get("academic_year") or "Nespecificat",
            document.get("subject") or document.get("discipline") or "Necunoscuta",
        )
        if group != current_group:
            st.markdown(f"**{group[0]} → {group[1]}**")
            current_group = group
        page_text = f" | pagini: {document['page_count']}" if document["page_count"] else ""
        course = document.get("course") or Path(document["file_name"]).stem
        with st.expander(f"{course}: {document['file_name']}"):
            st.write(f"Fragmente: {document['chunks']}{page_text}")
            st.write(f"Materie: {document.get('subject') or document.get('discipline') or 'Necunoscuta'}")
            st.write(f"Curs: {course}")
            if document.get("file_path"):
                st.caption(document["file_path"])
            if document["file_name"].lower().endswith(".pdf"):
                if st.button(
                    "Previzualizează PDF",
                    key=f"preview_pdf_{document['file_name']}",
                    use_container_width=True,
                ):
                    if open_pdf_citation(
                        {
                            "file_name": document["file_name"],
                            "file_path": document.get("file_path"),
                            "page": 1,
                            "excerpt": "",
                        }
                    ):
                        st.session_state.assistant_page = "Chat"
                        st.rerun()
            document_key = hashlib.sha1(
                (document.get("file_path") or document["file_name"]).encode("utf-8")
            ).hexdigest()[:12]

            with st.form(f"rename_document_{document_key}"):
                new_name = st.text_input(
                    "Nume nou",
                    value=document["file_name"],
                    key=f"rename_input_{document_key}",
                )
                submitted = st.form_submit_button("Redenumește")
            if submitted:
                try:
                    renamed_path = rename_indexed_document(document, new_name)
                    refresh_indexed_documents_state()
                    st.success(f"Document redenumit: {renamed_path.name}")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

            col_reindex_doc, col_delete_doc = st.columns(2)
            with col_reindex_doc:
                if st.button(
                    "Re-indexează documentul",
                    key=f"reindex_document_{document_key}",
                    use_container_width=True,
                ):
                    try:
                        with st.spinner("Reconstruiesc indexul profilului..."):
                            file_count, chunk_count = reindex_current_user_documents()
                        refresh_indexed_documents_state()
                        st.success(
                            f"Index reconstruit: {file_count} fișiere, "
                            f"{chunk_count} fragmente."
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
            with col_delete_doc:
                confirm_delete = st.checkbox(
                    f"Confirm ștergerea {document['file_name']}",
                    key=f"confirm_delete_document_{document_key}",
                )
                if st.button(
                    "Șterge documentul",
                    key=f"delete_document_{document_key}",
                    disabled=not confirm_delete,
                    use_container_width=True,
                ):
                    try:
                        delete_indexed_document(document)
                        refresh_indexed_documents_state()
                        st.success("Documentul a fost șters din folder, Chroma și metadata.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))


def render_study_memory_panel() -> None:
    st.header("Memorie de studiu")
    summary = get_dashboard_summary(MEMORY_DB_PATH)

    col_a, col_b = st.columns(2)
    col_a.metric("Intrebari", summary["total_questions"])
    col_b.metric("Documente studiate", summary["documents_studied"])
    col_a.metric("Subiecte slabe", summary["weak_topics"])
    quiz_average = summary["quiz_average"]
    col_b.metric(
        "Medie quiz",
        "Fara rezultate" if quiz_average is None else f"{quiz_average:.0f}%",
    )

    sessions = summary.get("recent_sessions") or []
    if sessions:
        with st.expander("Sesiuni recente"):
            for session in sessions:
                st.caption(
                    f"{session['last_activity']} | "
                    f"{session['questions']} intrebari | "
                    f"{session['quiz_answers']} raspunsuri quiz"
                )

    if st.button("Arată subiectele slabe", key="toggle_weak_topics_button"):
        st.session_state.show_weak_topics = not st.session_state.show_weak_topics

    if st.session_state.show_weak_topics:
        weak_topics = get_weak_topics(MEMORY_DB_PATH, limit=12)
        if weak_topics:
            for item in weak_topics:
                document = f" | {item['document_name']}" if item.get("document_name") else ""
                st.caption(f"{item['topic']} - {item['status']}{document}")
        else:
            st.caption("Nu ai marcat inca subiecte slabe.")

    if st.button(
        "Generează recapitulare din subiectele slabe",
        key="generate_weak_review",
    ):
        recommendations = get_recommended_topics(MEMORY_DB_PATH, limit=8)
        if not recommendations:
            st.warning("Nu exista inca subiecte slabe pentru recapitulare.")
        elif count_indexed_chunks() == 0:
            st.warning("Indexeaza documentele inainte de recapitulare.")
        else:
            topics = ", ".join(item["topic"] for item in recommendations)
            review_question = (
                "Genereaza o recapitulare structurata pentru subiectele mele slabe: "
                f"{topics}. Foloseste numai documentele indexate. Pentru fiecare subiect, "
                "explica ideea esentiala, o confuzie frecventa si o intrebare scurta de verificare."
            )
            try:
                with st.spinner("Generez recapitularea local..."):
                    response = query_documents(
                        review_question,
                        response_mode=st.session_state.response_mode,
                    )
                st.session_state.weak_review = save_answer_to_memory(
                    review_question,
                    clean_model_text(str(response)),
                    response=response,
                )
                st.success("Recapitularea este disponibila in tab-ul Progres.")
            except Exception as exc:
                st.error(f"Nu am putut genera recapitularea: {exc}")

    st.caption(f"Memoria ramane local: {MEMORY_DB_PATH}")


def render_server_access_panel() -> None:
    urls = get_server_urls()
    st.header("Acces server")
    st.caption(f"Mod deployment: {urls['deployment_mode']}")
    st.caption(f"Local: {urls['local']}")
    if urls["server_mode"]:
        st.caption(f"LAN: {urls['lan'] or 'indisponibil'}")
        st.caption(f"Tailscale: {urls['tailscale'] or 'indisponibil'}")
        st.caption(f"Public: {urls['public'] or 'neconfigurat'}")
        st.caption("Inferenta AI ruleaza numai pe acest PC.")
    else:
        st.caption("Porneste START_SERVER.bat pentru acces din retea.")


def render_diagnostics_panel() -> None:
    st.header("Diagnostics")
    st.caption(f"Current project root: {PROJECT_ROOT}")
    st.caption(f"Current storage folder: {STORAGE_DIR}")
    st.caption(f"Current documents folder: {current_documents_dir()}")
    st.caption(f"Current database path: {CHROMA_DIR}")
    st.caption(f"Current memory database: {MEMORY_DB_PATH}")
    st.caption(f"Active collection: {get_active_collection_name()}")
    queue_diagnostics = INFERENCE_QUEUE.diagnostics()
    st.caption(
        "AI queue: "
        f"{queue_diagnostics['running_requests']} running | "
        f"{queue_diagnostics['queued_requests']} queued | "
        f"{queue_diagnostics['active_users']} active users"
    )
    st.caption(
        f"Average response: {queue_diagnostics['average_response_seconds']:.1f}s | "
        f"GPU slots: {queue_diagnostics['max_concurrent_generations']}"
    )


def switch_streamlit_profile(username: str) -> None:
    st.session_state.clear()
    st.session_state.active_profile = username
    st.rerun()


def switch_streamlit_workspace(username: str, workspace_slug: str) -> None:
    active_profile = st.session_state.get("active_profile", username)
    st.session_state.clear()
    st.session_state.active_profile = active_profile
    st.session_state.active_workspace = workspace_slug
    st.rerun()


def render_workspace_sidebar(username: str) -> str:
    workspaces = USER_ACCOUNTS.list_workspaces(username)
    slugs = [item["slug"] for item in workspaces]
    names = {item["slug"]: item["name"] for item in workspaces}
    active = st.session_state.get("active_workspace", "general")
    if active not in slugs:
        active = "general"
        st.session_state.active_workspace = active

    st.sidebar.header("Workspace")
    selected = st.sidebar.selectbox(
        "Workspace curent",
        slugs,
        index=slugs.index(active),
        format_func=lambda slug: names.get(slug, slug),
        key="workspace_selector",
    )
    if selected != active:
        switch_streamlit_workspace(username, selected)

    with st.sidebar.expander("Creează workspace"):
        with st.form("create_workspace_form"):
            new_workspace = st.text_input(
                "Nume",
                placeholder="Biochimie, Cars, Programming...",
            )
            submitted = st.form_submit_button("Creează și deschide")
        if submitted:
            try:
                created = USER_ACCOUNTS.create_workspace(username, new_workspace)
                switch_streamlit_workspace(username, created["slug"])
            except ValueError as exc:
                st.error(str(exc))
    st.sidebar.caption(f"Context activ: {names.get(active, active)}")
    return active


def render_passwordless_profile_gate(profiles: list[str]) -> None:
    st.title("Cine folosește aplicația?")
    st.caption(
        "Alege sau creează un profil local. Profilurile separă documentele, "
        "memoria, quiz-urile, flashcardurile, planurile și conversațiile."
    )
    st.warning(
        "Autentificarea este OFF: profilurile nu sunt protejate prin parolă. "
        "Folosește modul acesta pentru local/LAN/Tailscale cu oameni de încredere."
    )
    if profiles:
        selected = st.selectbox("Profil existent", profiles, key="profile_gate_select")
        if st.button("Continuă cu profilul selectat", type="primary"):
            switch_streamlit_profile(selected)

    with st.form("create_profile_gate"):
        new_profile = st.text_input("Creează profil", placeholder="ex: stxfanee")
        submitted = st.form_submit_button("Creează și intră")
    if submitted:
        try:
            username = USER_ACCOUNTS.create_profile(new_profile)
            switch_streamlit_profile(username)
        except ValueError as exc:
            st.error(str(exc))
    st.stop()


def render_current_user_sidebar(active_profile: str, profiles: list[str]) -> None:
    st.sidebar.header("Utilizator curent")
    st.sidebar.success(active_profile)
    st.sidebar.caption(
        "Auth OFF: profilurile izolează datele, dar nu cer parolă."
    )

    if profiles:
        selected = st.sidebar.selectbox(
            "Schimbă utilizator",
            profiles,
            index=profiles.index(active_profile) if active_profile in profiles else 0,
            key="switch_profile_select",
        )
        if st.sidebar.button(
            "Schimbă profilul",
            use_container_width=True,
            disabled=selected == active_profile,
        ):
            switch_streamlit_profile(selected)

    with st.sidebar.expander("Creează profil"):
        with st.form("create_profile_sidebar"):
            new_profile = st.text_input("Nume profil", key="create_profile_sidebar_name")
            submitted = st.form_submit_button("Creează", use_container_width=True)
        if submitted:
            try:
                username = USER_ACCOUNTS.create_profile(new_profile)
                switch_streamlit_profile(username)
            except ValueError as exc:
                st.error(str(exc))

    with st.sidebar.expander("Șterge profilul curent"):
        st.caption("Șterge workspace-ul profilului, memoria și colecțiile Chroma.")
        confirmation = st.text_input(
            "Scrie exact numele profilului",
            key="delete_profile_confirmation",
        )
        if st.button(
            "Șterge profilul",
            use_container_width=True,
            disabled=confirmation != active_profile,
        ):
            try:
                delete_profile_and_data(active_profile)
                st.session_state.clear()
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def streamlit_user_identity() -> str:
    server_mode = get_server_urls()["server_mode"]
    if not authentication_enabled():
        profiles = USER_ACCOUNTS.list_profiles()
        active_profile = st.session_state.get("active_profile")
        if active_profile not in profiles:
            render_passwordless_profile_gate(profiles)
        username = normalize_username(active_profile)
        st.session_state.access_mode = (
            "Remote user mode" if server_mode else "Server local mode"
        )
        render_current_user_sidebar(username, profiles)
        return username

    if not server_mode:
        st.session_state.access_mode = "Server local mode"
        st.sidebar.info("Server local mode: fișierele sunt citite de pe acest PC.")
        return "local"

    st.sidebar.header("Acces")
    st.session_state.access_mode = "Remote user mode"
    st.sidebar.info(
        "Remote user mode: fișierele vin din browser, iar datele sunt separate "
        "pentru fiecare utilizator."
    )

    authenticated = st.session_state.get("authenticated_username")
    token = st.session_state.get("authenticated_token")
    if authenticated and token and USER_ACCOUNTS.authenticate_token(token) == authenticated:
        st.sidebar.success(f"Conectat: {authenticated}")
        if st.sidebar.button("Deconectare", use_container_width=True):
            st.session_state.pop("authenticated_username", None)
            st.session_state.pop("authenticated_token", None)
            st.rerun()
        return authenticated

    st.sidebar.caption("Autentificare pentru spațiul tău privat")
    with st.sidebar.form("remote_login_form"):
        username = st.text_input("Utilizator")
        secret = st.text_input("Parolă sau token API", type="password")
        submitted = st.form_submit_button("Conectare", use_container_width=True)
    if submitted:
        try:
            normalized = normalize_username(username)
            authenticated_user = USER_ACCOUNTS.authenticate_token(secret)
            issued_token = secret
            if authenticated_user != normalized:
                issued_token = USER_ACCOUNTS.login(normalized, secret) or ""
                authenticated_user = normalized if issued_token else None
            if authenticated_user == normalized:
                st.session_state.authenticated_username = normalized
                st.session_state.authenticated_token = issued_token
                st.rerun()
            st.sidebar.error("Date de autentificare incorecte.")
        except ValueError as exc:
            st.sidebar.error(str(exc))
    st.info("Conectează-te pentru a folosi modul remote și documentele tale private.")
    st.stop()


def initialize_state() -> None:
    ensure_project_dirs()
    st.session_state.setdefault("study_session_id", str(uuid.uuid4()))
    st.session_state.setdefault("selected_paths", [str(current_documents_dir())])
    st.session_state.setdefault("flashcards", [])
    st.session_state.setdefault("quiz", [])
    st.session_state.setdefault("quiz_checked", False)
    st.session_state.setdefault("quiz_context", {})
    st.session_state.setdefault("quiz_result_display", None)
    st.session_state.setdefault("indexed_documents", None)
    st.session_state.setdefault("last_answer", None)
    st.session_state.setdefault("last_question_mode", None)
    st.session_state.setdefault("weak_review", None)
    st.session_state.setdefault("show_weak_topics", False)
    st.session_state.setdefault("response_mode", DEFAULT_RESPONSE_MODE)
    st.session_state.setdefault("answer_mode", DEFAULT_ANSWER_MODE)
    st.session_state.setdefault("knowledge_mode", DEFAULT_KNOWLEDGE_MODE)
    st.session_state.setdefault(
        "auto_routing_enabled",
        get_preference(MEMORY_DB_PATH, "auto_routing_enabled", "1") != "0",
    )
    st.session_state.setdefault("active_conversation_id", None)
    st.session_state.setdefault("current_request_id", None)
    st.session_state.setdefault("current_session_plan", None)
    st.session_state.setdefault("session_plan_ics", None)
    st.session_state.setdefault("assistant_page", "Chat")
    st.session_state.setdefault("pending_chat_prompt", None)
    st.session_state.setdefault("pending_chat_replay", False)
    st.session_state.setdefault("chat_attachments", [])
    st.session_state.setdefault("pdf_viewer_file", None)
    st.session_state.setdefault("pdf_viewer_page", 1)
    st.session_state.setdefault("pdf_viewer_zoom", 100)
    st.session_state.setdefault("pdf_viewer_highlight", "")
    st.session_state.setdefault("pdf_viewer_citation_index", 0)
    st.session_state.setdefault(
        "developer_mode",
        get_preference(MEMORY_DB_PATH, "developer_mode", "0") == "1",
    )


def selected_model_ui(models: list[str]) -> str:
    options = list(models)
    for model in [SMARTER_MODEL, DEFAULT_LLM_MODEL]:
        if model not in options:
            options.append(model)

    saved_model = get_preference(MEMORY_DB_PATH, "llm_model")
    default = (
        saved_model
        if saved_model in options
        else SMARTER_MODEL if SMARTER_MODEL in models else DEFAULT_LLM_MODEL
    )
    index = options.index(default) if default in options else 0
    selected = st.selectbox("Model raspunsuri", options=options, index=index)
    if selected != saved_model:
        set_preference(MEMORY_DB_PATH, "llm_model", selected)
    return selected


def selected_response_mode_ui() -> str:
    options = list(RESPONSE_PROFILES)
    saved_mode = get_preference(
        MEMORY_DB_PATH,
        "response_mode",
        DEFAULT_RESPONSE_MODE,
    )
    if saved_mode not in options:
        saved_mode = DEFAULT_RESPONSE_MODE
    selected = st.radio(
        "Viteză și precizie",
        options=options,
        index=options.index(saved_mode),
        horizontal=True,
        help=(
            "Fast foloseste mai putin context. Balanced este recomandat. "
            "Accurate foloseste mai multe fragmente si citari mai stricte."
        ),
        key="response_mode_selector",
    )
    st.session_state.response_mode = selected
    if selected != saved_mode:
        set_preference(MEMORY_DB_PATH, "response_mode", selected)

    profile = get_response_profile(selected)
    st.caption(
        f"{profile.top_k} fragmente | context max. {profile.max_context_chars // 1000}k | "
        f"timeout {int(profile.request_timeout)}s"
    )
    return selected


def selected_knowledge_mode_ui() -> str:
    if st.session_state.get("auto_routing_enabled", True):
        st.session_state.knowledge_mode = DEFAULT_KNOWLEDGE_MODE
        st.caption("Rutare automată: documente / general / hibrid")
        return DEFAULT_KNOWLEDGE_MODE

    saved_mode = get_preference(
        MEMORY_DB_PATH,
        "knowledge_mode",
        DEFAULT_KNOWLEDGE_MODE,
    )
    if saved_mode not in KNOWLEDGE_MODE_OPTIONS:
        saved_mode = DEFAULT_KNOWLEDGE_MODE
    selected = st.radio(
        "Knowledge mode",
        options=KNOWLEDGE_MODE_OPTIONS,
        index=KNOWLEDGE_MODE_OPTIONS.index(saved_mode),
        help=(
            "Documents only folosește exclusiv RAG. Hybrid combină documentele cu "
            "cunoștințele generale. General knowledge only nu accesează ChromaDB."
        ),
        key="knowledge_mode_selector",
    )
    st.session_state.knowledge_mode = selected
    if selected != saved_mode:
        set_preference(MEMORY_DB_PATH, "knowledge_mode", selected)
    return selected


def start_new_chat() -> None:
    st.session_state.active_conversation_id = None
    st.session_state.last_answer = None
    st.session_state.chat_attachments = []
    st.session_state.pending_chat_prompt = None
    st.session_state.pending_chat_replay = False


def open_conversation(conversation_id: str) -> None:
    conversation = get_conversation(MEMORY_DB_PATH, conversation_id)
    if conversation is None:
        start_new_chat()
        return

    st.session_state.active_conversation_id = conversation_id
    st.session_state.answer_mode = conversation.get("answer_mode") or DEFAULT_ANSWER_MODE
    st.session_state.answer_mode_selector = st.session_state.answer_mode
    st.session_state.response_mode = conversation.get("response_mode") or DEFAULT_RESPONSE_MODE
    st.session_state.response_mode_selector = st.session_state.response_mode
    st.session_state.knowledge_mode = (
        conversation.get("knowledge_mode") or DEFAULT_KNOWLEDGE_MODE
    )
    st.session_state.knowledge_mode_selector = st.session_state.knowledge_mode
    workflow_mode = conversation.get("workflow_mode") or QUESTION_WORKFLOW_MODES[0]
    if workflow_mode not in QUESTION_WORKFLOW_MODES:
        workflow_mode = QUESTION_WORKFLOW_MODES[0]
    st.session_state.question_mode = workflow_mode
    selected_documents = conversation.get("selected_documents") or []
    st.session_state.chat_attachments = conversation.get("attached_documents") or []
    if workflow_mode == "Compară cursuri":
        st.session_state.comparison_documents = selected_documents
    elif workflow_mode == "Rezumat document" and selected_documents:
        st.session_state.summary_document = selected_documents[0]
    elif workflow_mode == "Caută în document specific" and selected_documents:
        st.session_state.specific_search_document = selected_documents[0]
    st.session_state.last_answer = None


def conversation_timestamp(value: str) -> str:
    try:
        timestamp = datetime.fromisoformat(value)
        return timestamp.strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return value or ""


def render_conversation_sidebar() -> None:
    st.header("Co-pilot Facultate")
    if st.button(
        "＋ Chat nou",
        type="primary",
        use_container_width=True,
        key="new_chat",
    ):
        start_new_chat()
        st.rerun()

    search = st.text_input(
        "Caută conversații",
        placeholder="Titlu sau mesaj",
        key="conversation_search",
    )
    conversations = list_conversations(MEMORY_DB_PATH, search=search, limit=40)
    st.caption("Conversații recente")
    if not conversations:
        st.caption("Nicio conversație salvată.")
        return

    active_id = st.session_state.get("active_conversation_id")
    for conversation in conversations:
        conversation_id = conversation["id"]
        title = conversation.get("title") or "Conversație"
        timestamp = conversation_timestamp(conversation.get("updated_at", ""))
        col_open, col_pin = st.columns([6, 1])
        with col_open:
            pin = "📌 " if conversation.get("pinned") else ""
            label = f"{pin}{title}\n{timestamp}"
            if st.button(
                label,
                use_container_width=True,
                type="primary" if conversation_id == active_id else "secondary",
                key=f"open_conversation_{conversation_id}",
            ):
                open_conversation(conversation_id)
                st.rerun()
        with col_pin:
            if st.button(
                "📌" if not conversation.get("pinned") else "↘",
                help=(
                    "Fixează conversația"
                    if not conversation.get("pinned")
                    else "Anulează fixarea"
                ),
                key=f"pin_conversation_{conversation_id}",
            ):
                set_conversation_pinned(
                    MEMORY_DB_PATH,
                    conversation_id,
                    not conversation.get("pinned"),
                )
                st.rerun()

    if active_id:
        active = next(
            (item for item in conversations if item["id"] == active_id), None
        )
        if active:
            with st.expander("Opțiuni chat"):
                renamed_title = st.text_input(
                    "Redenumește",
                    value=active.get("title") or "Conversație",
                    key=f"rename_title_{active_id}",
                )
                if st.button("Salvează titlul", use_container_width=True):
                    rename_conversation(MEMORY_DB_PATH, active_id, renamed_title)
                    st.rerun()
                workspace_options = [
                    item
                    for item in USER_ACCOUNTS.list_workspaces(current_username())
                    if item["slug"] != current_workspace_slug()
                ]
                if workspace_options:
                    target_slug = st.selectbox(
                        "Mută în workspace",
                        [item["slug"] for item in workspace_options],
                        format_func=lambda slug: next(
                            item["name"]
                            for item in workspace_options
                            if item["slug"] == slug
                        ),
                        key=f"move_chat_target_{active_id}",
                    )
                    st.caption(
                        "Istoricul se mută; fișierele atașate rămân în workspace-ul sursă."
                    )
                    if st.button(
                        "Mută chatul",
                        use_container_width=True,
                        key=f"move_chat_{active_id}",
                    ):
                        target_memory = USER_ACCOUNTS.workspace(
                            current_username(), target_slug
                        ).memory_db
                        move_conversation(
                            current_memory_db_path(),
                            target_memory,
                            active_id,
                            target_slug,
                        )
                        start_new_chat()
                        st.rerun()
                confirm_delete = st.checkbox(
                    "Confirm ștergerea",
                    key=f"confirm_chat_delete_{active_id}",
                )
                if st.button(
                    "Șterge chatul",
                    disabled=not confirm_delete,
                    use_container_width=True,
                ):
                    delete_conversation(MEMORY_DB_PATH, active_id)
                    start_new_chat()
                    st.rerun()


def sidebar_ui() -> str:
    with st.sidebar:
        render_conversation_sidebar()
        st.divider()
        st.radio(
            "Spațiu de lucru",
            [
                "Chat",
                "Flashcards",
                "Quiz",
                "Progres",
                "Plan sesiune",
                "Notebook",
                "Setări",
                "Server Status",
            ],
            key="assistant_page",
            label_visibility="collapsed",
        )
        developer_mode = st.toggle(
            "Developer Mode",
            value=bool(st.session_state.get("developer_mode", False)),
            help="Afișează metadate tehnice sigure, fără chain-of-thought sau prompturi.",
            key="developer_mode_toggle",
        )
        if developer_mode != st.session_state.get("developer_mode"):
            st.session_state.developer_mode = developer_mode
            set_preference(
                MEMORY_DB_PATH,
                "developer_mode",
                "1" if developer_mode else "0",
            )
        request_id = st.session_state.get("current_request_id")
        if st.button(
            "■ Oprește generarea",
            disabled=not request_id,
            use_container_width=True,
            help="Trimite o cerere de oprire către coada de inferență.",
        ):
            if INFERENCE_QUEUE.cancel(request_id):
                st.session_state.current_request_id = None
                st.success("Oprirea a fost solicitată.")
        st.divider()
        st.header("Setari")

        models = list_llm_models()
        if ollama_is_running():
            st.success("Ollama ruleaza local.")
        else:
            st.error("Ollama nu raspunde pe http://localhost:11434.")

        profiles = get_model_profiles(models)
        model_name = profiles["rag"]
        response_mode = selected_response_mode_ui()
        selected_knowledge_mode_ui()
        configure_llama_index(model_name, response_mode)

        st.divider()
        st.header("Documente")

        if current_username() != "local" or st.session_state.get("access_mode") == "Remote user mode":
            st.info(
                "Profil activ: fișierele sunt încărcate pe server și păstrate "
                "numai în spațiul utilizatorului curent."
            )
            uploads = st.file_uploader(
                "Alege fișiere de pe acest dispozitiv",
                type=["pdf", "docx", "pptx"],
                accept_multiple_files=True,
                key="remote_document_upload",
            )
            if st.button(
                "Încarcă și indexează",
                type="primary",
                disabled=not uploads,
                use_container_width=True,
            ):
                try:
                    if not ollama_is_running():
                        raise RuntimeError("Ollama nu răspunde pe PC-ul server.")
                    saved_paths = save_uploaded_documents(uploads)
                    with st.spinner("Încarc și indexez documentele în spațiul tău..."):
                        file_count, chunk_count = build_index(
                            [str(current_documents_dir())]
                        )
                    st.session_state.selected_paths = saved_paths
                    refresh_indexed_documents_state()
                    st.session_state.normal_mode_documents = [
                        Path(path).name for path in saved_paths
                    ]
                    st.success(
                        f"Gata: {file_count} fișiere, {chunk_count} fragmente indexate."
                    )
                except Exception as exc:
                    st.error(str(exc))
        else:
            st.caption("Mod local: selectorul Windows folosește fișierele PC-ului server.")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Alege folder"):
                    try:
                        folder = pick_folder_dialog()
                        if folder:
                            st.session_state.selected_paths = [folder]
                    except Exception as exc:
                        st.error(f"Nu am putut deschide selectorul Windows: {exc}")

            with col_b:
                if st.button("Alege fisiere"):
                    try:
                        files = pick_files_dialog()
                        if files:
                            st.session_state.selected_paths = files
                    except Exception as exc:
                        st.error(f"Nu am putut deschide selectorul Windows: {exc}")

            selected_paths_text = "\n".join(st.session_state.selected_paths)
            edited_paths = st.text_area(
                "Selectie curenta", value=selected_paths_text, height=110
            )
            st.session_state.selected_paths = [
                line.strip() for line in edited_paths.splitlines() if line.strip()
            ]

            if st.button("Indexeaza selectia", type="primary"):
                try:
                    if not ollama_is_running():
                        raise RuntimeError(
                            "Ollama nu raspunde. Porneste Ollama si incearca din nou."
                        )
                    with st.spinner("Indexez documentele local..."):
                        file_count, chunk_count = build_index(
                            st.session_state.selected_paths
                        )
                    refresh_indexed_documents_state()
                    st.success(
                        f"Indexare finalizata: {file_count} fisiere, "
                        f"{chunk_count} fragmente."
                    )
                except Exception as exc:
                    st.error(str(exc))

        st.caption(f"Fragmente indexate: {count_indexed_chunks()}")
        st.caption(f"Baza locala: {CHROMA_DIR}")
        st.caption(f"Utilizator activ: {current_username()}")
        st.divider()
        render_indexed_documents_panel()
        st.divider()
        render_study_memory_panel()
        st.divider()
        render_server_access_panel()
        st.divider()
        render_diagnostics_panel()

    return model_name


def run_question(
    question: str,
    spinner_text: str,
    document: dict | None = None,
    documents: list[dict] | None = None,
    summary_mode: bool | None = None,
    task_override: str | None = None,
) -> dict | None:
    stream_placeholder = st.empty()
    queue_placeholder = st.empty()

    def update_stream(text: str) -> None:
        stream_placeholder.markdown(f"{text} ▌")

    def update_queue(status: str, position: int | None, request_id: str) -> None:
        st.session_state.current_request_id = request_id
        if status == "queued" and position:
            queue_placeholder.info(
                f"AI-ul este ocupat. Ești în coadă: poziția {position}."
            )
        elif status == "running":
            queue_placeholder.empty()

    try:
        with INFERENCE_QUEUE.request_context(
            st.session_state.study_session_id,
            request_type="chat",
            callback=update_queue,
        ) as queued_request:
            with st.spinner(spinner_text):
                response = query_copilot(
                    question,
                    document_override=document,
                    documents_override=documents,
                    summary_mode_override=summary_mode,
                    task_override=task_override,
                    response_mode=st.session_state.response_mode,
                    answer_mode=st.session_state.answer_mode,
                    knowledge_mode=st.session_state.knowledge_mode,
                    stream_callback=update_stream,
                )
            response.debug["request_id"] = queued_request.request_id
            st.session_state.last_model_route = {
                "model": response.debug.get("selected_model"),
                "reason": response.debug.get("model_routing_reason"),
            }
            answer = clean_model_text(str(response))
            st.session_state.last_answer = save_answer_to_memory(
                question,
                answer,
                response=response,
                selected_document=document,
                infer_document=(
                    not bool(documents)
                    and response.debug.get("knowledge_route") != "general"
                ),
            )
            st.session_state.last_answer["request_id"] = queued_request.request_id
        queue_placeholder.empty()
        stream_placeholder.empty()
        return st.session_state.last_answer
    except (GenerationTimeoutError, QueueWaitTimeoutError, RequestCancelledError) as exc:
        queue_placeholder.empty()
        stream_placeholder.empty()
        st.error(str(exc))
        return None
    except (httpx.ConnectError, ollama.RequestError):
        queue_placeholder.empty()
        stream_placeholder.empty()
        st.error("Conexiunea cu Ollama s-a intrerupt. Verifica daca Ollama ruleaza si incearca din nou.")
        return None
    except Exception as exc:
        queue_placeholder.empty()
        stream_placeholder.empty()
        st.error(f"Nu am putut genera raspunsul: {exc}")
        return None


def run_course_comparison(
    topic: str,
    documents: list[dict],
    max_chunks_per_course: int,
    max_answer_tokens: int,
) -> dict | None:
    request_started = time.perf_counter()
    progress_placeholder = st.empty()
    stream_placeholder = st.empty()
    queue_placeholder = st.empty()

    def update_progress(message: str) -> None:
        progress_placeholder.info(message)

    def update_stream(text: str) -> None:
        stream_placeholder.markdown(f"{text} ▌")

    def update_queue(status: str, position: int | None, request_id: str) -> None:
        st.session_state.current_request_id = request_id
        if status == "queued" and position:
            queue_placeholder.info(
                f"AI-ul este ocupat. Ești în coadă: poziția {position}."
            )
        elif status == "running":
            queue_placeholder.empty()

    try:
        with INFERENCE_QUEUE.request_context(
            st.session_state.study_session_id,
            request_type="comparison",
            callback=update_queue,
        ) as queued_request:
            response = compare_courses_hierarchically(
                topic=topic,
                documents=documents,
                response_mode=st.session_state.response_mode,
                answer_mode=st.session_state.answer_mode,
                max_chunks_per_course=max_chunks_per_course,
                max_answer_tokens=max_answer_tokens,
                stream_callback=update_stream,
                progress_callback=update_progress,
            )
            total_seconds = time.perf_counter() - request_started
            retrieval_seconds = float(response.debug.get("retrieval_seconds") or 0)
            response.debug["latency"] = {
                "retrieval_seconds": round(retrieval_seconds, 4),
                "inference_seconds": round(
                    max(0.0, total_seconds - retrieval_seconds), 4
                ),
                "total_seconds": round(total_seconds, 4),
            }
            response.debug["request_id"] = queued_request.request_id
            question = (
                "Comparatie intre cursuri pentru tema: "
                f"{topic}. Documente: {', '.join(item['file_name'] for item in documents)}"
            )
            answer = clean_model_text(str(response))
            st.session_state.last_answer = save_answer_to_memory(
                question,
                answer,
                response=response,
                infer_document=False,
            )
            st.session_state.last_answer["request_id"] = queued_request.request_id
        queue_placeholder.empty()
        progress_placeholder.empty()
        stream_placeholder.empty()
        if response.debug.get("partial"):
            st.warning(
                "Comparația conține rezultate parțiale deoarece cel puțin un "
                "pas a depășit timpul disponibil."
            )
        return st.session_state.last_answer
    except (GenerationTimeoutError, QueueWaitTimeoutError, RequestCancelledError) as exc:
        queue_placeholder.empty()
        progress_placeholder.empty()
        stream_placeholder.empty()
        st.error(str(exc))
        return None
    except (httpx.ConnectError, ollama.RequestError):
        queue_placeholder.empty()
        progress_placeholder.empty()
        stream_placeholder.empty()
        st.error(
            "Conexiunea cu Ollama s-a întrerupt. Verifică dacă Ollama rulează "
            "și încearcă din nou."
        )
        return None
    except Exception as exc:
        queue_placeholder.empty()
        progress_placeholder.empty()
        stream_placeholder.empty()
        st.error(f"Nu am putut compara cursurile: {exc}")
        return None


def render_last_answer() -> None:
    last_answer = st.session_state.last_answer
    if not last_answer:
        return

    st.subheader("Raspuns")
    st.write(last_answer["answer"])
    response = last_answer.get("response")
    if response is not None:
        effective_mode = getattr(response, "debug", {}).get("answer_mode")
        if effective_mode:
            st.caption(f"Mod de răspuns folosit: {effective_mode}")
        st.subheader("Surse")
        render_sources(response)
        render_retrieval_debug(response)

    st.caption(f"Subiect detectat: {last_answer['topic']}")
    col_greu, col_neclar, col_repetat = st.columns(3)
    actions = (
        (col_greu, "Marchează ca greu", "greu"),
        (col_neclar, "Marchează ca neclar", "neclar"),
        (col_repetat, "Adaugă la repetat", "de repetat"),
    )
    for column, label, status in actions:
        with column:
            if st.button(
                label,
                key=f"{status}_{last_answer['history_id']}",
                use_container_width=True,
            ):
                added = mark_weak_topic(
                    MEMORY_DB_PATH,
                    study_history_id=last_answer["history_id"],
                    topic=last_answer["topic"],
                    document_name=last_answer.get("document_name"),
                    status=status,
                    question=last_answer["question"],
                )
                if added:
                    st.success("Salvat local.")
                else:
                    st.info("Acest marcaj este deja salvat.")


def conversation_title(first_question: str, limit: int = 72) -> str:
    title = " ".join(first_question.strip().split())
    if len(title) <= limit:
        return title or "Conversație nouă"
    return title[: limit - 1].rsplit(" ", 1)[0] + "…"


def ensure_active_conversation(
    first_question: str,
    workflow_mode: str,
    selected_documents: list[str],
) -> str:
    conversation_id = st.session_state.get("active_conversation_id")
    if conversation_id and get_conversation(MEMORY_DB_PATH, conversation_id):
        update_conversation_metadata(
            MEMORY_DB_PATH,
            conversation_id,
            answer_mode=st.session_state.answer_mode,
            response_mode=st.session_state.response_mode,
            knowledge_mode=st.session_state.knowledge_mode,
            workflow_mode=workflow_mode,
            selected_documents=selected_documents,
        )
        return conversation_id

    conversation_id = str(uuid.uuid4())
    create_conversation(
        MEMORY_DB_PATH,
        conversation_id,
        title=conversation_title(first_question),
        answer_mode=st.session_state.answer_mode,
        response_mode=st.session_state.response_mode,
        knowledge_mode=st.session_state.knowledge_mode,
        workflow_mode=workflow_mode,
        selected_documents=selected_documents,
    )
    st.session_state.active_conversation_id = conversation_id
    return conversation_id


def resolve_workspace_pdf(file_name: str, file_path: str | None = None) -> Path | None:
    documents_root = current_documents_dir().resolve()
    candidates = []
    if file_path:
        candidates.append(Path(file_path))
    candidates.append(documents_root / Path(file_name).name)
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(documents_root)
        except (OSError, ValueError):
            continue
        if resolved.is_file() and resolved.suffix.lower() == ".pdf":
            return resolved
    return None


def _page_number(value, default: int = 1) -> int:
    try:
        return max(1, int(float(value)))
    except (TypeError, ValueError):
        return default


@st.cache_data(show_spinner=False, max_entries=24)
def ocr_engine_available() -> bool:
    if pytesseract is None:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


@st.cache_data(show_spinner=False, max_entries=24)
def extract_pdf_text_layer(path: str, modified_ns: int) -> dict:
    del modified_ns
    pages: list[str] = []
    ocr_pages: list[int] = []
    reader = PdfReader(path)
    for index, page in enumerate(reader.pages):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""
        if (
            not text
            and fitz is not None
            and pytesseract is not None
            and Image is not None
            and ocr_engine_available()
        ):
            try:
                document = fitz.open(path)
                pdf_page = document.load_page(index)
                pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                image = Image.open(io.BytesIO(pixmap.tobytes("png")))
                text = pytesseract.image_to_string(image, lang="ron+eng").strip()
                document.close()
                if text:
                    ocr_pages.append(index + 1)
            except Exception:
                text = ""
        pages.append(text)
    return {
        "pages": pages,
        "page_count": len(pages),
        "ocr_pages": ocr_pages,
    }


@st.cache_data(show_spinner=False, max_entries=96)
def render_pdf_thumbnail(path: str, modified_ns: int, page_number: int) -> bytes | None:
    del modified_ns
    if fitz is None:
        return None
    try:
        document = fitz.open(path)
        page = document.load_page(page_number - 1)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(0.35, 0.35), alpha=False)
        data = pixmap.tobytes("png")
        document.close()
        return data
    except Exception:
        return None


def active_conversation_citations() -> list[dict]:
    conversation_id = st.session_state.get("active_conversation_id")
    conversation = (
        get_conversation(MEMORY_DB_PATH, conversation_id) if conversation_id else None
    )
    citations = []
    seen = set()
    for message in (conversation or {}).get("messages", []):
        for source in message.get("sources") or []:
            file_name = source.get("file_name") or ""
            if not file_name.lower().endswith(".pdf"):
                continue
            key = (file_name, _page_number(source.get("page")))
            if key in seen:
                continue
            seen.add(key)
            citations.append(source)
    return citations


def open_pdf_citation(source: dict, citation_index: int | None = None) -> bool:
    path = resolve_workspace_pdf(
        source.get("file_name") or "",
        source.get("file_path"),
    )
    if path is None:
        return False
    st.session_state.pdf_viewer_file = path.name
    st.session_state.pdf_viewer_page = _page_number(source.get("page"))
    st.session_state.pdf_viewer_highlight = source.get("excerpt") or ""
    if citation_index is not None:
        st.session_state.pdf_viewer_citation_index = citation_index
    return True


def render_pdf_viewer() -> None:
    file_name = st.session_state.get("pdf_viewer_file")
    if not file_name:
        st.info("Deschide o citare PDF din conversație pentru split view.")
        return
    path = resolve_workspace_pdf(file_name)
    if path is None:
        st.warning("PDF-ul nu mai există în workspace-ul curent.")
        st.session_state.pdf_viewer_file = None
        return

    modified_ns = path.stat().st_mtime_ns
    try:
        text_layer = extract_pdf_text_layer(str(path), modified_ns)
    except Exception as exc:
        st.error(f"Nu pot citi PDF-ul: {exc}")
        return
    page_count = max(1, int(text_layer.get("page_count") or 1))
    current_page = min(
        page_count,
        _page_number(st.session_state.get("pdf_viewer_page")),
    )
    st.session_state.pdf_viewer_page = current_page

    header_a, header_b = st.columns([5, 1])
    header_a.markdown(f"### {path.name}")
    if header_b.button("✕", help="Închide PDF", use_container_width=True):
        st.session_state.pdf_viewer_file = None
        st.rerun()

    citations = active_conversation_citations()
    if citations:
        index = min(
            len(citations) - 1,
            int(st.session_state.get("pdf_viewer_citation_index", 0)),
        )
        previous_col, status_col, next_col = st.columns([1, 3, 1])
        if previous_col.button("← Citare", disabled=index == 0, use_container_width=True):
            index -= 1
            open_pdf_citation(citations[index], index)
            st.rerun()
        status_col.caption(f"Citarea {index + 1} din {len(citations)}")
        if next_col.button(
            "Citare →", disabled=index >= len(citations) - 1, use_container_width=True
        ):
            index += 1
            open_pdf_citation(citations[index], index)
            st.rerun()

    nav_previous, nav_page, nav_next, nav_zoom = st.columns([1, 2, 1, 2])
    if nav_previous.button("←", disabled=current_page <= 1, use_container_width=True):
        st.session_state.pdf_viewer_page = current_page - 1
        st.rerun()
    selected_page = nav_page.number_input(
        "Pagina",
        min_value=1,
        max_value=page_count,
        value=current_page,
        step=1,
        label_visibility="collapsed",
    )
    if int(selected_page) != current_page:
        st.session_state.pdf_viewer_page = int(selected_page)
        st.rerun()
    if nav_next.button("→", disabled=current_page >= page_count, use_container_width=True):
        st.session_state.pdf_viewer_page = current_page + 1
        st.rerun()
    zoom = nav_zoom.select_slider(
        "Zoom",
        options=[50, 75, 100, 125, 150, 175, 200],
        value=int(st.session_state.get("pdf_viewer_zoom", 100)),
        label_visibility="collapsed",
    )
    st.session_state.pdf_viewer_zoom = zoom

    with st.form("pdf_search_form"):
        search_query = st.text_input(
            "Caută în PDF",
            value=st.session_state.get("pdf_viewer_search", ""),
        )
        search_submitted = st.form_submit_button("Caută")
    if search_submitted:
        st.session_state.pdf_viewer_search = search_query
        normalized_query = normalize_text(search_query.strip())
        matches = [
            index + 1
            for index, text in enumerate(text_layer["pages"])
            if normalized_query and normalized_query in normalize_text(text)
        ]
        st.session_state.pdf_viewer_search_results = matches
        if matches:
            st.session_state.pdf_viewer_page = matches[0]
            st.rerun()
    matches = st.session_state.get("pdf_viewer_search_results", [])
    if search_query and matches:
        selected_match = st.selectbox(
            "Rezultate",
            matches,
            format_func=lambda page: f"Pagina {page}",
            key="pdf_search_result_page",
        )
        if st.button("Mergi la rezultat", use_container_width=True):
            st.session_state.pdf_viewer_page = selected_match
            st.rerun()
    elif search_query:
        st.caption("Nicio potrivire în stratul text/OCR.")

    with st.expander("Miniaturi"):
        start_page = max(1, current_page - 2)
        thumbnail_pages = range(start_page, min(page_count, start_page + 4) + 1)
        columns = st.columns(len(list(thumbnail_pages)))
        for column, page_number in zip(columns, thumbnail_pages):
            thumbnail = render_pdf_thumbnail(str(path), modified_ns, page_number)
            with column:
                if thumbnail:
                    st.image(thumbnail, use_column_width=True)
                if st.button(
                    str(page_number),
                    key=f"pdf_thumbnail_{path.name}_{page_number}",
                    use_container_width=True,
                ):
                    st.session_state.pdf_viewer_page = page_number
                    st.rerun()

    highlight = st.session_state.get("pdf_viewer_highlight", "")
    if highlight:
        st.markdown("#### Paragraf citat")
        st.markdown(
            f"<mark>{html.escape(highlight)}</mark>",
            unsafe_allow_html=True,
        )

    pdf_data = base64.b64encode(path.read_bytes()).decode("ascii")
    search_fragment = quote((search_query or highlight[:80]).strip())
    fragment = f"page={current_page}&zoom={zoom}"
    if search_fragment:
        fragment += f"&search={search_fragment}"
    components.html(
        f'<iframe title="PDF viewer" src="data:application/pdf;base64,{pdf_data}#{fragment}" '
        'style="width:100%;height:780px;border:1px solid #444;border-radius:10px"></iframe>',
        height=800,
        scrolling=False,
    )
    ocr_pages = text_layer.get("ocr_pages") or []
    if current_page in ocr_pages:
        st.caption("Strat text: OCR (Tesseract)")
    elif text_layer["pages"][current_page - 1]:
        st.caption("Strat text: PDF nativ/OCR existent")
    else:
        st.caption(
            "Această pagină nu are strat text. Pentru OCR instalează Tesseract cu limbile ron+eng."
        )


def render_chat_sources(sources: list[dict], key_prefix: str = "source") -> None:
    if not sources:
        return
    with st.expander(f"Surse ({len(sources)})"):
        for index, source in enumerate(sources):
            file_name = source.get("file_name") or "document necunoscut"
            page = source.get("page")
            location = f"{file_name}, pagina {page}" if page else file_name
            score = source.get("score")
            score_text = f" · relevanță {float(score):.2f}" if score is not None else ""
            st.markdown(f"- **{location}**{score_text}")
            if file_name.lower().endswith(".pdf"):
                if st.button(
                    "Deschide în PDF",
                    key=f"{key_prefix}_open_pdf_{index}",
                ):
                    citations = active_conversation_citations()
                    citation_index = next(
                        (
                            position
                            for position, citation in enumerate(citations)
                            if citation.get("file_name") == file_name
                            and _page_number(citation.get("page")) == _page_number(page)
                        ),
                        0,
                    )
                    if open_pdf_citation(source, citation_index):
                        st.rerun()
                    else:
                        st.error("PDF-ul nu este disponibil în workspace-ul curent.")


def render_chat_study_actions(message: dict) -> None:
    metadata = message.get("metadata") or {}
    history_id = metadata.get("history_id")
    topic = metadata.get("topic")
    if not history_id or not topic:
        return

    with st.expander("Marchează pentru studiu"):
        columns = st.columns(3)
        actions = (
            ("Greu", "greu"),
            ("Neclar", "neclar"),
            ("De repetat", "de repetat"),
        )
        for column, (label, status) in zip(columns, actions):
            with column:
                if st.button(
                    label,
                    key=f"chat_{status}_{message['id']}",
                    use_container_width=True,
                ):
                    added = mark_weak_topic(
                        MEMORY_DB_PATH,
                        study_history_id=int(history_id),
                        topic=topic,
                        document_name=metadata.get("document_name"),
                        status=status,
                        question=metadata.get("question") or "",
                    )
                    st.success("Salvat local." if added else "Marcaj deja salvat.")


def _intent_label(intent: str | None) -> str:
    return {
        "course_question": "Întrebare despre curs",
        "document_search": "Căutare în document",
        "compare_documents": "Comparație între documente",
        "study_planning": "Planificare de studiu",
        "flashcards": "Generare flashcarduri",
        "quiz": "Generare quiz",
        "memory": "Memorie și progres",
        "mixed": "Documente + cunoștințe generale",
        "general_knowledge": "Întrebare generală",
    }.get(intent or "", intent or "Necunoscut")


def _group_explain_sources(sources: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for source in sources:
        file_name = source.get("file_name") or "document necunoscut"
        item = grouped.setdefault(
            file_name,
            {"file_name": file_name, "pages": [], "scores": [], "sources": []},
        )
        page = _page_number(source.get("page"), default=0)
        if page and page not in item["pages"]:
            item["pages"].append(page)
        if source.get("score") is not None:
            item["scores"].append(float(source["score"]))
        item["sources"].append(source)
    for item in grouped.values():
        item["pages"].sort()
        item["relevance"] = (
            max(item["scores"]) if item["scores"] else None
        )
    return list(grouped.values())


def _pages_summary(pages: list[int]) -> str:
    if not pages:
        return "pagini nespecificate"
    if len(pages) == 1:
        return f"pagina {pages[0]}"
    consecutive = pages == list(range(pages[0], pages[-1] + 1))
    return (
        f"paginile {pages[0]}–{pages[-1]}"
        if consecutive
        else "paginile " + ", ".join(str(page) for page in pages)
    )


def build_explain_why(message: dict) -> dict:
    metadata = message.get("metadata") or {}
    debug = metadata.get("debug") or {}
    sources = message.get("sources") or []
    documents = _group_explain_sources(sources)
    rag_used = bool(debug.get("rag_used") or documents)
    general_used = bool(
        debug.get("general_knowledge_used")
        or debug.get("knowledge_route") == "general"
    )
    if rag_used and general_used:
        knowledge_source = "Ambele (Hybrid)"
    elif rag_used:
        knowledge_source = "Documente încărcate"
    elif general_used:
        knowledge_source = "Cunoștințe generale"
    else:
        knowledge_source = "Memorie locală / răspuns operațional"

    plan = debug.get("reasoning_plan") or {}
    intent = debug.get("intent") or plan.get("intent")
    route = debug.get("knowledge_route") or (
        "rag" if rag_used and not general_used else "hybrid" if rag_used else "general"
    )
    routing_reason = (
        debug.get("routing_reason")
        or debug.get("model_routing_reason")
        or "Ruta a fost aleasă din tipul întrebării și sursele disponibile."
    )
    if documents:
        if plan.get("user_goal") == "ranking" or route == "hybrid":
            document_reason = (
                "Întrebarea necesita analiză sau comparație, iar fragmentele selectate "
                "au oferit dovezi relevante pentru criteriile evaluate."
            )
        else:
            document_reason = (
                "Aceste documente conțin fragmente cu relevanță semantică pentru "
                "întrebarea utilizatorului și au trecut etapa de reranking."
            )
    else:
        document_reason = "Nu au fost folosite documente în acest răspuns."

    if general_used and rag_used:
        general_reason = (
            "Documentele au oferit context relevant, iar cunoștințele generale au fost "
            "folosite pentru completare sau legarea conceptelor."
        )
    elif general_used:
        general_reason = (
            "Întrebarea a fost clasificată ca generală sau documentele nu au furnizat "
            "dovezi suficient de relevante."
        )
    else:
        general_reason = "Cunoștințele generale nu au fost necesare."

    raw_confidence = debug.get("confidence")
    if raw_confidence is None:
        scores = [item["relevance"] for item in documents if item["relevance"] is not None]
        raw_confidence = max(scores) if scores else 0.65
    confidence = float(raw_confidence)
    if confidence >= 0.75:
        confidence_label = "Ridicată"
        confidence_reason = "Sursele și ruta aleasă susțin direct răspunsul."
    elif confidence >= 0.45:
        confidence_label = "Medie"
        confidence_reason = "Dovezile sunt utile, dar nu acoperă complet toate detaliile."
    else:
        confidence_label = "Scăzută"
        confidence_reason = (
            "Documentele recuperate au oferit informații parțiale sau relevanța lor a "
            "fost redusă."
        )

    missing_information = []
    if debug.get("partial"):
        missing_information.append("Generarea sau comparația a produs un rezultat parțial.")
    if confidence < 0.45:
        missing_information.append("Sursele disponibile nu acoperă complet întrebarea.")
    if plan.get("inference_level") == "evaluative":
        missing_information.append(
            "Concluzia evaluativă nu este scrisă explicit în cursuri; este o inferență "
            "bazată pe criteriile și dovezile disponibile."
        )
    if general_used and not rag_used:
        missing_information.append(
            "Nu a fost identificată o sursă relevantă în documentele workspace-ului."
        )

    if documents:
        source_parts = [
            f"{item['file_name']} ({_pages_summary(item['pages'])})"
            for item in documents
        ]
        source_summary = "Răspunsul s-a bazat în principal pe " + "; ".join(source_parts)
        source_summary += (
            ", împreună cu cunoștințe generale."
            if general_used
            else "."
        )
    elif general_used:
        source_summary = (
            "Răspunsul s-a bazat pe cunoștințe generale; nu au fost folosite citări "
            "din documentele încărcate."
        )
    else:
        source_summary = "Răspunsul a folosit starea și memoria locală a aplicației."

    return {
        "knowledge_source": knowledge_source,
        "documents": documents,
        "document_reason": document_reason,
        "general_reason": general_reason,
        "intent": _intent_label(intent),
        "knowledge_mode": debug.get("knowledge_mode") or route,
        "model": debug.get("selected_model") or "Nespecificat",
        "routing_reason": routing_reason,
        "confidence": confidence_label,
        "confidence_value": confidence,
        "confidence_reason": confidence_reason,
        "missing_information": missing_information,
        "source_summary": source_summary,
        "route": route,
        "latency": debug.get("latency") or {},
    }


def render_explain_why(message: dict) -> None:
    explanation = build_explain_why(message)
    with st.expander("🧠 Explain why", expanded=False):
        st.markdown(f"**1. Sursa cunoștințelor:** {explanation['knowledge_source']}")
        st.markdown("**2. Documente folosite**")
        if not explanation["documents"]:
            st.caption("Niciun document citat.")
        for document_index, document in enumerate(explanation["documents"]):
            relevance = document.get("relevance")
            relevance_text = (
                f" · relevanță {relevance:.2f}" if relevance is not None else ""
            )
            st.markdown(
                f"- **{document['file_name']}** · {_pages_summary(document['pages'])}"
                f"{relevance_text}"
            )
            for source_index, source in enumerate(document["sources"]):
                if source["file_name"].lower().endswith(".pdf") and st.button(
                    f"Deschide pagina {_page_number(source.get('page'))}",
                    key=(
                        f"explain_open_{message['id']}_{document_index}_{source_index}"
                    ),
                ):
                    if open_pdf_citation(source):
                        st.rerun()
        st.markdown("**3. De ce au fost selectate aceste documente**")
        st.write(explanation["document_reason"])
        st.markdown("**4. De ce au fost folosite cunoștințe generale**")
        st.write(explanation["general_reason"])
        st.markdown("**5. Rutare**")
        st.write(
            {
                "intenție detectată": explanation["intent"],
                "knowledge mode": explanation["knowledge_mode"],
                "model selectat": explanation["model"],
                "motiv": explanation["routing_reason"],
            }
        )
        st.markdown(f"**6. Încredere:** {explanation['confidence']}")
        st.caption(explanation["confidence_reason"])
        st.markdown("**7. Informații lipsă / presupuneri**")
        if explanation["missing_information"]:
            for item in explanation["missing_information"]:
                st.markdown(f"- {item}")
        else:
            st.caption("Nu au fost identificate presupuneri importante.")
        st.markdown("**8. Rezumatul surselor**")
        st.write(explanation["source_summary"])

        if st.session_state.get("developer_mode", False):
            st.divider()
            st.markdown("**Developer Mode**")
            safe_debug = {
                "intent_detection": explanation["intent"],
                "routing_decision": explanation["route"],
                "retrieved_documents": [
                    item["file_name"] for item in explanation["documents"]
                ],
                "similarity_scores": {
                    item["file_name"]: item["relevance"]
                    for item in explanation["documents"]
                },
                "selected_model": explanation["model"],
                "latency": explanation["latency"],
            }
            st.json(safe_debug)
            st.markdown("**Retrieved chunks**")
            for source in message.get("sources") or []:
                st.write(
                    {
                        "document": source.get("file_name"),
                        "page": source.get("page"),
                        "score": source.get("score"),
                        "excerpt": source.get("excerpt") or "indisponibil",
                    }
                )


def render_chat_message(message: dict, show_study_actions: bool = False) -> None:
    role = message.get("role", "assistant")
    with st.chat_message(role):
        st.markdown(message.get("content") or "")
        metadata = message.get("metadata") or {}
        if role == "assistant":
            mode = metadata.get("answer_mode")
            if mode:
                st.caption(f"Mod: {mode}")
            debug = metadata.get("debug") or {}
            intent = debug.get("intent")
            confidence = debug.get("confidence")
            route = debug.get("knowledge_route")
            if intent or route:
                confidence_text = (
                    f" · încredere {float(confidence) * 100:.0f}%"
                    if confidence is not None
                    else ""
                )
                st.caption(
                    f"Rutare: {route or 'necunoscut'} · intenție: "
                    f"{intent or 'necunoscut'}{confidence_text}"
                )
            selected_model = debug.get("selected_model")
            if selected_model:
                st.caption(
                    f"Model: {selected_model} · profil: "
                    f"{debug.get('model_profile', 'automat')} · "
                    f"{debug.get('model_routing_reason', 'rutare automată')}"
                )
            render_chat_sources(
                message.get("sources") or [],
                key_prefix=f"message_{message['id']}",
            )
            render_explain_why(message)
            if show_study_actions:
                render_chat_study_actions(message)
            with st.expander("Copiază răspunsul"):
                st.code(message.get("content") or "", language=None)
        else:
            with st.expander("Editează mesajul"):
                edited = st.text_area(
                    "Mesaj",
                    value=message.get("content") or "",
                    key=f"edit_message_{message['id']}",
                    label_visibility="collapsed",
                )
                if st.button("Salvează și regenerează", key=f"save_edit_{message['id']}"):
                    edit_conversation_message(
                        MEMORY_DB_PATH,
                        int(message["id"]),
                        edited,
                        delete_following=True,
                    )
                    st.session_state.pending_chat_prompt = edited
                    st.session_state.pending_chat_replay = True
                    st.rerun()
        timestamp = conversation_timestamp(message.get("created_at", ""))
        if timestamp:
            st.caption(timestamp)


def persist_assistant_chat_message(
    conversation_id: str,
    result: dict,
    workflow_mode: str,
    selected_documents: list[str],
) -> None:
    response = result.get("response")
    debug = getattr(response, "debug", {}) if response is not None else {}
    answer_mode = debug.get("answer_mode") or resolve_answer_mode(
        st.session_state.answer_mode,
        result.get("question") or "",
    )
    add_conversation_message(
        MEMORY_DB_PATH,
        conversation_id,
        role="assistant",
        content=result["answer"],
        sources=response_source_records(response),
        metadata={
            "history_id": result.get("history_id"),
            "topic": result.get("topic"),
            "document_name": result.get("document_name"),
            "question": result.get("question"),
            "answer_mode": answer_mode,
            "response_mode": st.session_state.response_mode,
            "knowledge_mode": st.session_state.knowledge_mode,
            "workflow_mode": workflow_mode,
            "selected_documents": selected_documents,
            "debug": debug,
        },
    )


def conversation_context(messages: list[dict], limit: int = 10) -> str:
    recent = messages[-limit:]
    if not recent:
        return ""
    lines = []
    for message in recent:
        role = "Utilizator" if message.get("role") == "user" else "Asistent"
        content = " ".join((message.get("content") or "").split())
        if content:
            lines.append(f"{role}: {content[:1800]}")
    return "\n".join(lines)


def questions_tab() -> None:
    with st.expander("Controale conversație", expanded=False):
        col_mode, col_reasoning = st.columns(2)
        with col_mode:
            mode = st.selectbox(
                "Mod de lucru",
                QUESTION_WORKFLOW_MODES,
                key="question_mode",
                help="Lasă Întrebare normală pentru rutare automată.",
            )
        with col_reasoning:
            selected_answer_mode = st.selectbox(
                "Mod răspuns",
                options=ANSWER_MODE_OPTIONS,
                index=ANSWER_MODE_OPTIONS.index(
                    st.session_state.get("answer_mode", DEFAULT_ANSWER_MODE)
                ),
                key="answer_mode_selector",
            )
    st.session_state.answer_mode = selected_answer_mode

    documents = st.session_state.get("indexed_documents")
    if documents is None:
        documents = get_indexed_documents()
        st.session_state.indexed_documents = documents
    document_by_name = {document["file_name"]: document for document in documents}
    document_names = list(document_by_name)

    with st.expander("📎 Atașează documente", expanded=False):
        chat_uploads = st.file_uploader(
            "PDF, DOCX sau PPTX",
            type=["pdf", "docx", "pptx"],
            accept_multiple_files=True,
            key="chat_document_upload",
        )
        if st.button(
            "Încarcă în conversație",
            disabled=not chat_uploads,
            type="primary",
            use_container_width=True,
        ):
            saved_paths = save_uploaded_documents(chat_uploads)
            with st.spinner("Indexez documentele atașate..."):
                build_index([str(current_documents_dir())])
            st.session_state.chat_attachments = [Path(path).name for path in saved_paths]
            refresh_indexed_documents_state()
            st.success("Documentele au fost atașate și sunt active în acest chat.")
            st.rerun()
    selected_names: list[str] = []
    selected_document = None
    profile = get_response_profile(st.session_state.response_mode)
    max_chunks_per_course = profile.comparison_chunks_per_course
    max_answer_tokens = profile.comparison_answer_tokens
    placeholder = "Scrie o întrebare despre cursurile tale"
    input_disabled = (
        count_indexed_chunks() == 0
        and st.session_state.knowledge_mode == "Documents only"
    )

    if mode == "Compară cursuri":
        saved_selection = st.session_state.get("comparison_documents", [])
        st.session_state.comparison_documents = [
            name for name in saved_selection if name in document_by_name
        ]
        selected_names = st.multiselect(
            "Cursuri de comparat",
            options=document_names,
            placeholder="Alege cel puțin două documente",
            key="comparison_documents",
        )
        with st.expander("Opțiuni comparație"):
            col_chunks, col_length = st.columns(2)
            with col_chunks:
                max_chunks_per_course = st.number_input(
                    "Max. fragmente per curs",
                    min_value=1,
                    max_value=12,
                    value=profile.comparison_chunks_per_course,
                    step=1,
                    key=f"comparison_chunks_{st.session_state.response_mode}",
                )
            with col_length:
                max_answer_tokens = st.number_input(
                    "Lungime maximă răspuns (tokeni)",
                    min_value=300,
                    max_value=3000,
                    value=profile.comparison_answer_tokens,
                    step=100,
                    key=f"comparison_answer_tokens_{st.session_state.response_mode}",
                )
        input_disabled = input_disabled or len(selected_names) < 2
        placeholder = "Ce vrei să compari între cursurile selectate?"
    elif mode in {"Rezumat document", "Caută în document specific"}:
        widget_key = (
            "summary_document"
            if mode == "Rezumat document"
            else "specific_search_document"
        )
        saved_document = st.session_state.get(widget_key)
        if saved_document not in document_by_name and document_names:
            st.session_state[widget_key] = document_names[0]
        if document_names:
            selected_name = st.selectbox("Document", document_names, key=widget_key)
            selected_names = [selected_name]
            selected_document = document_by_name[selected_name]
        input_disabled = input_disabled or not document_names
        placeholder = (
            "Spune ce să conțină rezumatul"
            if mode == "Rezumat document"
            else "Întreabă despre documentul selectat"
        )
    else:
        saved_selection = st.session_state.get("normal_mode_documents", [])
        st.session_state.normal_mode_documents = [
            name for name in saved_selection if name in document_by_name
        ]
        if document_names:
            selected_names = st.multiselect(
                "Documente active (opțional)",
                options=document_names,
                placeholder="Lasă gol pentru toate documentele profilului",
                key="normal_mode_documents",
            )

    active_id = st.session_state.get("active_conversation_id")
    conversation = get_conversation(MEMORY_DB_PATH, active_id) if active_id else None
    messages = conversation.get("messages", []) if conversation else []
    last_assistant_id = next(
        (
            message["id"]
            for message in reversed(messages)
            if message.get("role") == "assistant"
        ),
        None,
    )
    for message in messages:
        render_chat_message(
            message,
            show_study_actions=message.get("id") == last_assistant_id,
        )

    if messages and messages[-1].get("role") == "assistant":
        action_columns = st.columns([1, 1, 5])
        with action_columns[0]:
            if st.button("↻ Regenerează", use_container_width=True):
                last_user = next(
                    (item for item in reversed(messages) if item.get("role") == "user"),
                    None,
                )
                if last_user:
                    edit_conversation_message(
                        MEMORY_DB_PATH,
                        int(last_user["id"]),
                        last_user.get("content") or "",
                        delete_following=True,
                    )
                    st.session_state.pending_chat_prompt = last_user.get("content")
                    st.session_state.pending_chat_replay = True
                    st.rerun()
        with action_columns[1]:
            if st.button("Continuă", use_container_width=True):
                st.session_state.pending_chat_prompt = (
                    "Continuă răspunsul anterior fără să repeți ce ai spus deja."
                )
                st.session_state.pending_chat_replay = False
                st.rerun()

    pending_prompt = st.session_state.pop("pending_chat_prompt", None)
    replay_existing = bool(st.session_state.pop("pending_chat_replay", False))
    prompt = pending_prompt or st.chat_input(
        placeholder,
        disabled=input_disabled,
        key="chat_prompt",
    )
    if not prompt:
        return

    attached_names = [
        name
        for name in st.session_state.get("chat_attachments", [])
        if name in document_by_name
    ]
    if attached_names:
        selected_names = list(dict.fromkeys([*selected_names, *attached_names]))
    conversation_id = ensure_active_conversation(prompt, mode, selected_names)
    update_conversation_metadata(
        MEMORY_DB_PATH,
        conversation_id,
        answer_mode=st.session_state.answer_mode,
        response_mode=st.session_state.response_mode,
        knowledge_mode=st.session_state.knowledge_mode,
        workflow_mode=mode,
        selected_documents=selected_names,
        attached_documents=attached_names,
        selected_workspace=current_workspace_slug(),
    )
    user_metadata = {
        "answer_mode": st.session_state.answer_mode,
        "response_mode": st.session_state.response_mode,
        "knowledge_mode": st.session_state.knowledge_mode,
        "workflow_mode": mode,
        "selected_documents": selected_names,
    }
    if not replay_existing:
        add_conversation_message(
            MEMORY_DB_PATH,
            conversation_id,
            role="user",
            content=prompt,
            metadata=user_metadata,
        )
        with st.chat_message("user"):
            st.markdown(prompt)

    result = None
    prior_context = conversation_context(messages)
    model_prompt = prompt
    if prior_context:
        model_prompt = (
            f"{prompt}\n\nContextul conversației anterioare (folosește-l pentru "
            f"continuitate, fără să îl repeți):\n{prior_context}"
        )
    with st.chat_message("assistant"):
        if mode == "Întrebare normală" and is_document_inventory_question(prompt):
            refresh_indexed_documents_state()
            answer = indexed_documents_answer()
            result = save_answer_to_memory(prompt, answer)
        elif mode == "Compară cursuri":
            selected = [document_by_name[name] for name in selected_names]
            result = run_course_comparison(
                model_prompt,
                selected,
                int(max_chunks_per_course),
                int(max_answer_tokens),
            )
        elif mode == "Rezumat document":
            question = f"Rezumat document {selected_names[0]}. Cerință: {model_prompt}"
            result = run_question(
                question,
                "Generez rezumatul...",
                document=selected_document,
                summary_mode=True,
            )
        elif mode == "Caută în document specific":
            result = run_question(
                model_prompt,
                "Caut în documentul selectat...",
                document=selected_document,
                summary_mode=False,
            )
        else:
            selected = [document_by_name[name] for name in selected_names]
            result = run_question(
                model_prompt,
                "Caut în documente și leg ideile relevante...",
                documents=selected or None,
            )

        if result:
            st.markdown(result["answer"])
            response = result.get("response")
            render_chat_sources(response_source_records(response))

    if result:
        persist_assistant_chat_message(
            conversation_id,
            result,
            mode,
            selected_names,
        )
        st.rerun()


def flashcards_tab() -> None:
    col_topic, col_count = st.columns([3, 1])
    with col_topic:
        topic = st.text_input("Tema flashcarduri", placeholder="Exemplu: conceptele cheie din curs")
    with col_count:
        count = st.number_input("Numar", min_value=3, max_value=20, value=8, step=1)

    if st.button("Genereaza flashcards", type="primary"):
        if count_indexed_chunks() == 0:
            st.warning("Indexeaza mai intai documentele.")
            return
        try:
            queue_placeholder = st.empty()

            def update_queue(status: str, position: int | None, request_id: str) -> None:
                st.session_state.current_request_id = request_id
                if status == "queued" and position:
                    queue_placeholder.info(
                        f"AI-ul este ocupat. Ești în coadă: poziția {position}."
                    )
                elif status == "running":
                    queue_placeholder.empty()

            with INFERENCE_QUEUE.request_context(
                st.session_state.study_session_id,
                request_type="flashcards",
                callback=update_queue,
            ) as queued_request:
                with st.spinner("Generez flashcarduri din surse..."):
                    cards, response = generate_flashcards(
                        topic or "toate documentele",
                        int(count),
                        response_mode=st.session_state.response_mode,
                    )
                response.debug["request_id"] = queued_request.request_id
            queue_placeholder.empty()
        except (GenerationTimeoutError, QueueWaitTimeoutError, RequestCancelledError) as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            st.error(f"Nu am putut genera flashcardurile: {exc}")
            return
        st.session_state.flashcards = cards
        if cards:
            record_flashcard_set(
                MEMORY_DB_PATH,
                topic or "toate documentele",
                cards,
            )
        if not cards:
            st.warning("Nu am putut interpreta raspunsul ca JSON. Afisez raspunsul brut.")
            st.write(clean_model_text(str(response)))
            render_sources(response)
            render_retrieval_debug(response)

    for index, card in enumerate(st.session_state.flashcards, start=1):
        front = card.get("front", "")
        back = card.get("back", "")
        source_hint = card.get("source_hint", "")
        with st.expander(f"Flashcard {index}: {front}"):
            st.write(back)
            if source_hint:
                st.caption(source_hint)


def quiz_tab() -> None:
    col_topic, col_count = st.columns([3, 1])
    with col_topic:
        topic = st.text_input("Tema quiz", placeholder="Exemplu: capitolul despre ...")
    with col_count:
        count = st.number_input("Intrebari", min_value=3, max_value=15, value=5, step=1)

    if st.button("Genereaza quiz", type="primary"):
        if count_indexed_chunks() == 0:
            st.warning("Indexeaza mai intai documentele.")
            return
        try:
            queue_placeholder = st.empty()

            def update_queue(status: str, position: int | None, request_id: str) -> None:
                st.session_state.current_request_id = request_id
                if status == "queued" and position:
                    queue_placeholder.info(
                        f"AI-ul este ocupat. Ești în coadă: poziția {position}."
                    )
                elif status == "running":
                    queue_placeholder.empty()

            with INFERENCE_QUEUE.request_context(
                st.session_state.study_session_id,
                request_type="quiz",
                callback=update_queue,
            ) as queued_request:
                with st.spinner("Generez quiz din documente..."):
                    quiz, response = generate_quiz(
                        topic or "toate documentele",
                        int(count),
                        response_mode=st.session_state.response_mode,
                    )
                response.debug["request_id"] = queued_request.request_id
            queue_placeholder.empty()
        except (GenerationTimeoutError, QueueWaitTimeoutError, RequestCancelledError) as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            st.error(f"Nu am putut genera quizul: {exc}")
            return
        for key in list(st.session_state):
            if key.startswith("quiz_answer_"):
                del st.session_state[key]
        st.session_state.quiz = quiz
        st.session_state.quiz_checked = False
        st.session_state.quiz_result_display = None
        st.session_state.quiz_context = {
            "topic": topic or "toate documentele",
            "source_documents": response_document_names(response),
            "quiz_session_id": str(uuid.uuid4()),
        }
        if not quiz:
            st.warning("Nu am putut interpreta raspunsul ca JSON. Afisez raspunsul brut.")
            st.write(clean_model_text(str(response)))
            render_sources(response)
            render_retrieval_debug(response)

    for index, item in enumerate(st.session_state.quiz):
        question = item.get("question", f"Intrebarea {index + 1}")
        options = item.get("options", [])
        if not isinstance(options, list) or len(options) < 2:
            continue
        st.radio(question, options, key=f"quiz_answer_{index}")

    if st.session_state.quiz and st.button("Verifica raspunsurile"):
        results = []
        quiz_context = st.session_state.quiz_context
        st.session_state.quiz_checked = True
        correct = 0
        for index, item in enumerate(st.session_state.quiz):
            options = item.get("options", [])
            answer_index = item.get("answer_index", -1)
            if not isinstance(answer_index, int) or answer_index < 0 or answer_index >= len(options):
                continue

            selected = st.session_state.get(f"quiz_answer_{index}")
            expected = options[answer_index]
            is_correct = selected == expected
            if is_correct:
                correct += 1
            fallback_sources = quiz_context.get("source_documents") or []
            source_document = item.get("source_document")
            if fallback_sources:
                matched_source = next(
                    (
                        name
                        for name in fallback_sources
                        if searchable_text(name) == searchable_text(source_document or "")
                    ),
                    None,
                )
                source_document = matched_source or fallback_sources[0]
            item_topic = item.get("topic") or quiz_context.get("topic") or "quiz"
            record_quiz_result(
                MEMORY_DB_PATH,
                session_id=st.session_state.study_session_id,
                quiz_session_id=quiz_context.get("quiz_session_id") or str(uuid.uuid4()),
                question=item.get("question", f"Intrebarea {index + 1}"),
                selected_answer=selected,
                correct_answer=expected,
                is_correct=is_correct,
                source_document=source_document,
                topic=item_topic,
            )
            results.append(
                {
                    "index": index + 1,
                    "is_correct": is_correct,
                    "correct_answer": expected,
                    "explanation": item.get("explanation", ""),
                }
            )

        st.session_state.quiz_result_display = {
            "correct": correct,
            "total": len(st.session_state.quiz),
            "items": results,
        }

    if st.session_state.quiz_checked and st.session_state.quiz_result_display:
        result_display = st.session_state.quiz_result_display
        for result in result_display["items"]:
            if result["is_correct"]:
                st.success(f"{result['index']}. Corect")
            else:
                st.error(
                    f"{result['index']}. Raspuns corect: {result['correct_answer']}"
                )
            if result["explanation"]:
                st.write(result["explanation"])
        st.info(f"Scor: {result_display['correct']}/{result_display['total']}")


def stable_widget_key(prefix: str, value: str) -> str:
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, value)}"


def document_short_label(document: dict) -> str:
    parts = [
        document.get("academic_year"),
        document.get("subject") or document.get("discipline"),
        document.get("course"),
    ]
    structure = " → ".join(part for part in parts if part and part != "Nespecificat")
    return f"{structure} | {document['file_name']}" if structure else document["file_name"]


def selected_weak_topics(subject: str, documents: list[dict], limit: int = 30) -> list[dict]:
    selected_names = {searchable_text(document["file_name"]) for document in documents}
    selected_subject = searchable_text(subject)
    matches = []
    for item in get_weak_topics(MEMORY_DB_PATH, limit=150):
        topic_text = searchable_text(item.get("topic") or "")
        document_text = searchable_text(item.get("document_name") or "")
        if document_text and document_text in selected_names:
            matches.append(item)
        elif selected_subject and selected_subject in topic_text:
            matches.append(item)
        elif selected_subject and selected_subject in document_text:
            matches.append(item)
        if len(matches) >= limit:
            break
    return matches


def document_weak_topic_count(document: dict, weak_topics: list[dict]) -> int:
    document_name = searchable_text(document["file_name"])
    return sum(
        1
        for item in weak_topics
        if searchable_text(item.get("document_name") or "") == document_name
    )


def estimate_document_workload(
    document: dict,
    difficulty_level: str,
    weak_topics: list[dict],
) -> dict:
    page_count = int(document.get("page_count") or 0)
    chunk_count = int(document.get("chunks") or 0)
    inferred_pages = page_count or max(1, math.ceil(chunk_count / 2))
    weak_count = document_weak_topic_count(document, weak_topics)
    base_hours = max(0.75, inferred_pages * 0.08, chunk_count * 0.16)
    weak_bonus = min(1.5, weak_count * 0.25)
    factor = DIFFICULTY_FACTORS.get(difficulty_level, 1.0)
    estimated_hours = round((base_hours + weak_bonus) * factor, 1)
    return {
        "file_name": document["file_name"],
        "academic_year": document.get("academic_year"),
        "subject": document.get("subject") or document.get("discipline"),
        "course": document.get("course"),
        "chunks": chunk_count,
        "pages": page_count,
        "weak_topics": weak_count,
        "estimated_hours": max(0.5, estimated_hours),
    }


def session_date_window(
    number_of_days: int,
    exam_date_value: date | None,
) -> dict:
    today = date.today()
    safe_days = max(1, int(number_of_days))
    if exam_date_value:
        safe_exam_date = max(exam_date_value, today + timedelta(days=1))
        available_days = max(1, (safe_exam_date - today).days)
        last_study_day = safe_exam_date - timedelta(days=1)
    else:
        safe_exam_date = None
        available_days = safe_days
        last_study_day = today + timedelta(days=available_days - 1)

    return {
        "today": today,
        "exam_date": safe_exam_date,
        "available_study_days": available_days,
        "start_date": today,
        "last_study_day": last_study_day,
    }


def estimate_session_totals(
    subject: str,
    documents: list[dict],
    difficulty_level: str,
    include_revision_days: bool,
    include_quiz_days: bool,
    available_study_days: int,
) -> dict:
    weak_topics = selected_weak_topics(subject, documents)
    workloads = [
        estimate_document_workload(document, difficulty_level, weak_topics)
        for document in documents
    ]
    content_hours = round(sum(item["estimated_hours"] for item in workloads), 1)
    recap_hours = round(
        content_hours * (0.22 if include_revision_days else 0.10),
        1,
    )
    quiz_hours = round(content_hours * 0.12, 1) if include_quiz_days else 0.0
    total_workload_hours = round(content_hours + recap_hours + quiz_hours, 1)
    recommended_hours_per_day = round(
        max(0.5, total_workload_hours / max(1, available_study_days)),
        1,
    )
    return {
        "weak_topics": weak_topics,
        "workloads": workloads,
        "content_hours": content_hours,
        "recap_hours": recap_hours,
        "quiz_hours": quiz_hours,
        "total_workload_hours": total_workload_hours,
        "recommended_hours_per_day": recommended_hours_per_day,
    }


def hours_difficulty_warning(hours_per_day: float) -> str:
    if hours_per_day > 8:
        return "Orele recomandate depasesc 8h/zi: planul este nerealist fara mai multe zile sau mai putine documente."
    if hours_per_day > 6:
        return "Orele recomandate depasesc 6h/zi: planul este foarte greu."
    if hours_per_day > 4:
        return "Orele recomandate depasesc 4h/zi: planul este greu."
    return ""


def split_page_range(document: dict, part_index: int, total_parts: int) -> str:
    pages = [
        int(page)
        for page in document.get("pages", [])
        if str(page).isdigit()
    ]
    if not pages or total_parts <= 1:
        return "toate paginile" if pages else f"partea {part_index}/{total_parts}"
    pages = sorted(pages)
    chunk_size = max(1, math.ceil(len(pages) / total_parts))
    start = (part_index - 1) * chunk_size
    end = min(start + chunk_size, len(pages))
    selected_pages = pages[start:end] or pages[-1:]
    return f"pag. {selected_pages[0]}-{selected_pages[-1]}"


def build_study_tasks(
    documents: list[dict],
    workloads: list[dict],
    hours_per_day: float,
) -> list[dict]:
    tasks = []
    workload_by_name = {item["file_name"]: item for item in workloads}
    max_block_hours = max(0.75, hours_per_day * 0.7)
    for document in documents:
        workload = workload_by_name[document["file_name"]]
        total_hours = workload["estimated_hours"]
        parts = max(1, math.ceil(total_hours / max_block_hours))
        part_hours = round(total_hours / parts, 1)
        for part_index in range(1, parts + 1):
            tasks.append(
                {
                    "document": document["file_name"],
                    "course": document.get("course") or Path(document["file_name"]).stem,
                    "subject": document.get("subject") or document.get("discipline"),
                    "part": f"{part_index}/{parts}",
                    "page_range": split_page_range(document, part_index, parts),
                    "hours": part_hours,
                    "priority_topics": [
                        document.get("course") or Path(document["file_name"]).stem,
                    ],
                }
            )
    return tasks


def build_session_plan(
    subject: str,
    documents: list[dict],
    number_of_days: int,
    hours_per_day: float,
    difficulty_level: str,
    include_revision_days: bool,
    include_quiz_days: bool,
    exam_date_value: date | None,
    auto_hours: bool = False,
) -> dict:
    date_window = session_date_window(number_of_days, exam_date_value)
    available_study_days = date_window["available_study_days"]
    estimates = estimate_session_totals(
        subject,
        documents,
        difficulty_level,
        include_revision_days,
        include_quiz_days,
        available_study_days,
    )
    weak_topics = estimates["weak_topics"]
    workloads = estimates["workloads"]
    recommended_hours_per_day = estimates["recommended_hours_per_day"]
    actual_hours_per_day = (
        recommended_hours_per_day
        if auto_hours
        else round(max(0.5, float(hours_per_day)), 1)
    )
    total_estimated_hours = estimates["content_hours"]
    total_workload_hours = estimates["total_workload_hours"]
    total_available_hours = round(available_study_days * actual_hours_per_day, 1)
    revision_day_count = (
        max(1, min(3, math.ceil(available_study_days * 0.2)))
        if include_revision_days and available_study_days >= 3
        else 0
    )
    study_day_count = max(1, available_study_days - revision_day_count)
    tasks = build_study_tasks(documents, workloads, actual_hours_per_day)
    task_index = 0
    start_date = date_window["start_date"]
    weak_topic_labels = []
    for item in weak_topics:
        label = item.get("topic")
        if label and label not in weak_topic_labels:
            weak_topic_labels.append(label)
        if len(weak_topic_labels) >= 6:
            break

    days = []
    for day_number in range(1, available_study_days + 1):
        is_revision_day = day_number > study_day_count
        current_date = start_date + timedelta(days=day_number - 1)
        recap_time = round(min(0.75, max(0.25, actual_hours_per_day * 0.15)), 1)
        quiz_time = 0.0
        if include_quiz_days and (day_number % 3 == 0 or is_revision_day):
            quiz_time = round(min(0.75, max(0.35, actual_hours_per_day * 0.18)), 1)

        daily_tasks = []
        used_hours = 0.0
        if is_revision_day:
            recap_time = round(max(recap_time, actual_hours_per_day * 0.55), 1)
            if include_quiz_days:
                quiz_time = round(max(quiz_time, min(1.0, actual_hours_per_day * 0.25)), 1)
            daily_tasks.append("Recapitulare generala si refacerea ideilor principale")
        else:
            content_capacity = max(0.5, actual_hours_per_day - recap_time - quiz_time)
            while task_index < len(tasks):
                task = tasks[task_index]
                if used_hours + task["hours"] <= content_capacity + 0.15:
                    daily_tasks.append(
                        (
                            f"{task['course']} ({task['document']}), "
                            f"{task['page_range']} - {task['hours']}h"
                        )
                    )
                    used_hours += task["hours"]
                    task_index += 1
                    continue
                if not daily_tasks and content_capacity >= 0.5:
                    partial_hours = round(content_capacity, 1)
                    daily_tasks.append(
                        (
                            f"{task['course']} ({task['document']}), "
                            f"{task['page_range']} - {partial_hours}h"
                        )
                    )
                    task["hours"] = round(max(0.0, task["hours"] - partial_hours), 1)
                    used_hours += partial_hours
                break

        day_weak_topics = weak_topic_labels[:3] if is_revision_day else weak_topic_labels[:2]
        if is_revision_day and not day_weak_topics:
            day_weak_topics = ["recapitulare din cursurile selectate"]
        priority_topics = []
        for task_text in daily_tasks:
            course_name = task_text.split("(", 1)[0].strip()
            if course_name and course_name not in priority_topics:
                priority_topics.append(course_name)
        if not priority_topics:
            priority_topics = weak_topic_labels[:3] or [subject]

        estimated_hours = round(
            min(actual_hours_per_day, used_hours + recap_time + quiz_time),
            1,
        )
        days.append(
            {
                "day_number": day_number,
                "date": current_date.isoformat(),
                "tasks": daily_tasks,
                "documents": sorted(
                    {
                        task.split("(", 1)[1].split(")", 1)[0]
                        for task in daily_tasks
                        if "(" in task and ")" in task
                    }
                ),
                "estimated_hours": estimated_hours,
                "recap_time": recap_time,
                "quiz_time": quiz_time,
                "priority_topics": priority_topics[:5],
                "weak_topics": day_weak_topics,
            }
        )

    remaining_tasks = len(tasks) - task_index
    warnings = []
    difficulty_warning = hours_difficulty_warning(recommended_hours_per_day)
    if difficulty_warning:
        warnings.append(difficulty_warning)
    if not auto_hours and actual_hours_per_day + 0.05 < recommended_hours_per_day:
        warnings.append(
            f"Timpul ales pare insuficient. Recomandat: {recommended_hours_per_day:.1f} ore/zi."
        )
    if total_workload_hours > total_available_hours * 1.05 or remaining_tasks > 0:
        warnings.append(
            "Timpul disponibil pare insuficient pentru un ritm confortabil. "
            "Mareste numarul de zile, orele pe zi sau redu documentele selectate."
        )

    if remaining_tasks > 0:
        for task in tasks[task_index:]:
            days[-1]["tasks"].append(
                (
                    f"RESTANT: {task['course']} ({task['document']}), "
                    f"{task['page_range']} - {task['hours']}h"
                )
            )
        days[-1]["estimated_hours"] = round(
            days[-1]["estimated_hours"]
            + sum(task["hours"] for task in tasks[task_index:]),
            1,
        )

    title = f"{subject} - plan sesiune"
    if date_window["exam_date"]:
        title += f" pana la {date_window['exam_date'].isoformat()}"

    selected_documents = [
        {
            "file_name": document["file_name"],
            "academic_year": document.get("academic_year"),
            "subject": document.get("subject") or document.get("discipline"),
            "course": document.get("course"),
            "chunks": document.get("chunks"),
            "page_count": document.get("page_count"),
        }
        for document in documents
    ]
    return {
        "title": title,
        "subject": subject,
        "today": date_window["today"].isoformat(),
        "exam_date": date_window["exam_date"].isoformat() if date_window["exam_date"] else None,
        "last_study_day": date_window["last_study_day"].isoformat(),
        "available_study_days": available_study_days,
        "number_of_days": available_study_days,
        "requested_number_of_days": int(number_of_days),
        "hours_per_day": actual_hours_per_day,
        "manual_hours_per_day": round(float(hours_per_day), 1),
        "auto_hours": auto_hours,
        "recommended_hours_per_day": recommended_hours_per_day,
        "difficulty_level": difficulty_level,
        "include_revision_days": include_revision_days,
        "include_quiz_days": include_quiz_days,
        "selected_documents": selected_documents,
        "workloads": workloads,
        "days": days,
        "total_estimated_hours": total_estimated_hours,
        "total_workload_hours": total_workload_hours,
        "total_available_hours": total_available_hours,
        "warning": "\n\n".join(dict.fromkeys(warnings)),
        "weak_topics": weak_topic_labels,
    }


def ics_escape(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def build_session_plan_ics(plan: dict) -> bytes:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Co-pilot Facultate//Session Plan//RO",
        "CALSCALE:GREGORIAN",
    ]
    for day in plan.get("days", []):
        raw_date = day.get("date")
        if raw_date:
            event_date = date.fromisoformat(raw_date)
        else:
            event_date = date.today() + timedelta(days=int(day["day_number"]) - 1)
        if event_date < date.today():
            continue
        end_date = event_date + timedelta(days=1)
        course_label = " + ".join(day.get("priority_topics") or [plan["subject"]])
        title = f"{plan['subject']} - {course_label}"
        if day.get("recap_time", 0) > 0:
            title += " + recapitulare"
        description_lines = [
            f"Ziua {day['day_number']}",
            f"Ore estimate: {day['estimated_hours']}",
            f"Recapitulare: {day['recap_time']}h",
            f"Quiz/flashcards: {day['quiz_time']}h",
            "Sarcini:",
            *[f"- {task}" for task in day.get("tasks", [])],
        ]
        weak_topics = day.get("weak_topics") or []
        if weak_topics:
            description_lines.extend(
                ["Subiecte slabe de repetat:", *[f"- {topic}" for topic in weak_topics]]
            )
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:faculty-copilot-{uuid.uuid4()}@local",
                f"DTSTAMP:{timestamp}",
                f"DTSTART;VALUE=DATE:{event_date.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{end_date.strftime('%Y%m%d')}",
                f"SUMMARY:{ics_escape(title)}",
                f"DESCRIPTION:{ics_escape(chr(10).join(description_lines))}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines).encode("utf-8")


def render_session_plan(plan: dict) -> None:
    if plan.get("warning"):
        st.warning(plan["warning"])

    today_label = plan.get("today") or date.today().isoformat()
    exam_label = plan.get("exam_date") or "nesetata"
    available_days = plan.get("available_study_days") or plan.get("number_of_days")
    col_today, col_exam, col_days = st.columns(3)
    col_today.metric("Azi", today_label)
    col_exam.metric("Data examenului", exam_label)
    col_days.metric("Zile de studiu disponibile", available_days)

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Workload total", f"{plan.get('total_workload_hours', plan['total_estimated_hours']):.1f}h")
    col_b.metric("Ore disponibile total", f"{plan['total_available_hours']:.1f}h")
    col_c.metric("Ore recomandate pe zi", f"{plan.get('recommended_hours_per_day', plan['hours_per_day']):.1f}")
    col_d.metric(
        "Mod ore",
        "automat" if plan.get("auto_hours") else "manual",
    )

    if plan.get("weak_topics"):
        st.caption("Subiecte slabe incluse: " + ", ".join(plan["weak_topics"]))

    rows = []
    for day in plan["days"]:
        rows.append(
            {
                "zi": day["day_number"],
                "data": day.get("date") or f"Ziua {day['day_number']}",
                "sarcini": "\n".join(day.get("tasks") or ["Recapitulare"]),
                "ore": day["estimated_hours"],
                "recap": day["recap_time"],
                "quiz/flashcards": day["quiz_time"],
                "prioritati": ", ".join(day.get("priority_topics") or []),
                "slab de repetat": ", ".join(day.get("weak_topics") or []),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    if plan.get("workloads"):
        with st.expander("Workload estimat pe document"):
            st.dataframe(plan["workloads"], use_container_width=True, hide_index=True)


def render_saved_session_plans() -> None:
    st.markdown("#### Planuri salvate")
    plans = get_session_plans(MEMORY_DB_PATH, limit=10)
    if not plans:
        st.caption("Nu exista inca planuri salvate.")
        return

    for plan in plans:
        with st.expander(
            f"{plan['created_at'].replace('T', ' ')} | {plan['title']}"
        ):
            hydrated_plan = {
                "title": plan["title"],
                "subject": plan["subject"],
                "today": date.today().isoformat(),
                "exam_date": plan["exam_date"],
                "last_study_day": (date.today() + timedelta(days=plan["number_of_days"] - 1)).isoformat(),
                "available_study_days": plan["number_of_days"],
                "number_of_days": plan["number_of_days"],
                "hours_per_day": plan["hours_per_day"],
                "auto_hours": False,
                "recommended_hours_per_day": plan["hours_per_day"],
                "difficulty_level": plan["difficulty_level"],
                "include_revision_days": plan["include_revision_days"],
                "include_quiz_days": plan["include_quiz_days"],
                "selected_documents": plan["selected_documents"],
                "workloads": [],
                "days": plan["plan_days"],
                "total_estimated_hours": plan["total_estimated_hours"],
                "total_workload_hours": plan["total_estimated_hours"],
                "total_available_hours": plan["number_of_days"] * plan["hours_per_day"],
                "warning": "",
                "weak_topics": [],
            }
            render_session_plan(hydrated_plan)
            ics_bytes = build_session_plan_ics(hydrated_plan)
            st.download_button(
                "Descarca .ics",
                data=ics_bytes,
                file_name=f"faculty-copilot-plan-{plan['id']}.ics",
                mime="text/calendar",
                key=f"download_saved_plan_{plan['id']}",
            )


def session_plan_tab() -> None:
    st.subheader("Plan sesiune")
    documents = st.session_state.get("indexed_documents")
    if documents is None:
        documents = get_indexed_documents()
        st.session_state.indexed_documents = documents

    if not documents:
        st.info("Indexeaza cursurile inainte sa generezi un plan de sesiune.")
        render_saved_session_plans()
        return

    subjects = sorted(
        {
            document.get("subject") or document.get("discipline") or "Necunoscuta"
            for document in documents
        }
    )
    selected_subject = st.selectbox("Materie", options=subjects, key="plan_subject")
    subject_documents = [
        document
        for document in documents
        if (document.get("subject") or document.get("discipline") or "Necunoscuta")
        == selected_subject
    ]
    document_options = {
        document_short_label(document): document
        for document in subject_documents
    }
    selected_labels = st.multiselect(
        "Documente/cursuri incluse",
        options=list(document_options),
        default=list(document_options)[: min(4, len(document_options))],
        key="plan_documents",
    )
    selected_documents_preview = [
        document_options[label]
        for label in selected_labels
        if label in document_options
    ]

    col_days, col_hours, col_difficulty = st.columns(3)
    with col_days:
        number_of_days = st.number_input(
            "Zile pana la examen",
            min_value=1,
            max_value=180,
            value=14,
            step=1,
        )
    with col_hours:
        auto_hours = st.checkbox(
            "Calculeaza automat orele necesare pe zi",
            value=False,
            key="plan_auto_hours",
        )
        hours_per_day = st.number_input(
            "Ore disponibile pe zi (manual)",
            min_value=0.5,
            max_value=12.0,
            value=2.0,
            step=0.5,
            disabled=auto_hours,
        )
    with col_difficulty:
        difficulty_level = st.selectbox(
            "Dificultate",
            options=["low", "medium", "high"],
            index=1,
        )

    col_revision, col_quiz, col_exam = st.columns(3)
    with col_revision:
        include_revision_days = st.checkbox("Include zile de recapitulare", value=True)
    with col_quiz:
        include_quiz_days = st.checkbox("Include zile de quiz", value=True)
    with col_exam:
        use_exam_date = st.checkbox("Seteaza data examenului", value=False)
        exam_date_value = (
            st.date_input(
                "Data examenului",
                value=date.today() + timedelta(days=int(number_of_days)),
                min_value=date.today() + timedelta(days=1),
            )
            if use_exam_date
            else None
        )

    date_window = session_date_window(int(number_of_days), exam_date_value)
    col_today, col_exam_info, col_available = st.columns(3)
    col_today.info(f"Azi: {date_window['today'].isoformat()}")
    col_exam_info.info(
        f"Examen: {date_window['exam_date'].isoformat() if date_window['exam_date'] else 'nesetat'}"
    )
    col_available.info(
        f"Zile disponibile de studiu: {date_window['available_study_days']}"
    )
    if use_exam_date:
        st.caption(
            "Cand data examenului este setata, ultima zi de studiu este ziua dinaintea examenului."
        )

    recommended_hours_per_day = None
    if selected_documents_preview:
        estimates = estimate_session_totals(
            selected_subject,
            selected_documents_preview,
            difficulty_level,
            include_revision_days,
            include_quiz_days,
            date_window["available_study_days"],
        )
        recommended_hours_per_day = estimates["recommended_hours_per_day"]
        st.info(f"Ore recomandate pe zi: {recommended_hours_per_day:.1f}")
        difficulty_warning = hours_difficulty_warning(recommended_hours_per_day)
        if difficulty_warning:
            st.warning(difficulty_warning)
        if not auto_hours and float(hours_per_day) + 0.05 < recommended_hours_per_day:
            st.warning(
                f"Timpul ales pare insuficient. Recomandat: {recommended_hours_per_day:.1f} ore/zi."
            )

    if st.button("Genereaza plan de sesiune", type="primary"):
        selected_documents = selected_documents_preview
        if not selected_documents:
            st.warning("Alege cel putin un document.")
        else:
            plan = build_session_plan(
                subject=selected_subject,
                documents=selected_documents,
                number_of_days=int(number_of_days),
                hours_per_day=float(hours_per_day),
                difficulty_level=difficulty_level,
                include_revision_days=include_revision_days,
                include_quiz_days=include_quiz_days,
                exam_date_value=exam_date_value,
                auto_hours=auto_hours,
            )
            plan_id = save_session_plan(
                MEMORY_DB_PATH,
                title=plan["title"],
                subject=plan["subject"],
                exam_date=plan["exam_date"],
                number_of_days=plan["number_of_days"],
                hours_per_day=plan["hours_per_day"],
                difficulty_level=plan["difficulty_level"],
                include_revision_days=plan["include_revision_days"],
                include_quiz_days=plan["include_quiz_days"],
                selected_documents=plan["selected_documents"],
                plan_days=plan["days"],
                total_estimated_hours=plan["total_estimated_hours"],
            )
            plan["id"] = plan_id
            st.session_state.current_session_plan = plan
            st.session_state.session_plan_ics = None
            st.success("Planul a fost generat si salvat local.")

    current_plan = st.session_state.get("current_session_plan")
    if current_plan:
        st.markdown("#### Plan generat")
        render_session_plan(current_plan)
        if st.button("Genereaza orar .ics"):
            st.session_state.session_plan_ics = build_session_plan_ics(current_plan)
        if st.session_state.get("session_plan_ics"):
            st.download_button(
                "Descarca orarul .ics",
                data=st.session_state.session_plan_ics,
                file_name=f"faculty-copilot-plan-{current_plan.get('id', 'nou')}.ics",
                mime="text/calendar",
            )

    render_saved_session_plans()


def build_smart_recommendations(documents: list[dict]) -> list[str]:
    recommendations = []
    for item in get_recommended_topics(MEMORY_DB_PATH, limit=5):
        recommendations.append(
            f"Repeta {item['topic']} - prioritate {item['priority']} ({item['reasons']})."
        )

    studied = {
        searchable_text(item["document"]): item["interactions"]
        for item in get_studied_documents(MEMORY_DB_PATH)
    }
    neglected = [
        document
        for document in documents
        if studied.get(searchable_text(document["file_name"]), 0) == 0
    ]
    for document in neglected[:4]:
        recommendations.append(
            f"Document neglijat: {document.get('course') or document['file_name']} "
            f"din {document.get('subject') or document.get('discipline') or 'materie necunoscuta'}."
        )

    if not recommendations:
        recommendations.append(
            "Continua cu un rezumat scurt pentru cursul urmator si apoi un quiz de verificare."
        )
    return recommendations


def academic_metadata_editor() -> None:
    st.markdown("#### Structura academica")
    documents = st.session_state.get("indexed_documents")
    if documents is None:
        documents = get_indexed_documents()
        st.session_state.indexed_documents = documents
    if not documents:
        st.caption("Nu exista documente indexate pentru editare.")
        return

    for document in sorted(documents, key=lambda item: item["file_name"].lower()):
        key_base = stable_widget_key("doc_meta", document_metadata_key(document))
        with st.expander(document_short_label(document)):
            current_year = document.get("academic_year") or "Nespecificat"
            year_options = list(ACADEMIC_YEAR_OPTIONS)
            if current_year not in year_options:
                year_options.append(current_year)
            academic_year = st.selectbox(
                "An",
                options=year_options,
                index=year_options.index(current_year),
                key=f"{key_base}_year",
            )
            subject = st.text_input(
                "Materie",
                value=document.get("subject") or document.get("discipline") or "",
                key=f"{key_base}_subject",
            )
            course = st.text_input(
                "Curs",
                value=document.get("course") or infer_course_label(document["file_name"]),
                key=f"{key_base}_course",
            )
            if st.button("Salveaza metadatele", key=f"{key_base}_save"):
                upsert_document_metadata(
                    MEMORY_DB_PATH,
                    document_key=document_metadata_key(document),
                    file_name=document["file_name"],
                    file_path=document.get("file_path"),
                    academic_year=academic_year,
                    subject=subject.strip() or "Necunoscuta",
                    course=course.strip() or infer_course_label(document["file_name"]),
                )
                refresh_indexed_documents_state()
                st.success("Metadatele au fost salvate local.")


def model_routing_settings() -> None:
    st.markdown("#### Model routing")
    models = list_llm_models()
    if not models:
        st.warning("Nu am găsit modele Ollama instalate. Pornește Ollama și reîncarcă pagina.")
        return

    st.caption("Modele Ollama instalate: " + ", ".join(models))
    labels = {
        "rag": "RAG model",
        "general": "General knowledge model",
        "reasoning": "Reasoning/Professor model",
        "fast": "Fast model",
    }
    status = model_profile_status(models)
    changed = False
    columns = st.columns(2)
    for index, (profile_name, preference_key) in enumerate(MODEL_PROFILE_KEYS.items()):
        item = status[profile_name]
        configured = item["configured"]
        default_index = models.index(item["resolved"]) if item["resolved"] in models else 0
        with columns[index % 2]:
            selected = st.selectbox(
                labels[profile_name],
                options=models,
                index=default_index,
                key=f"model_profile_setting_{profile_name}",
            )
            if item["missing"]:
                st.warning(
                    f"{configured} nu este instalat; folosesc temporar {item['resolved']}."
                )
            if selected != configured:
                set_preference(MEMORY_DB_PATH, preference_key, selected)
                changed = True

    auto_routing = st.checkbox(
        "Rutare automată a cunoștințelor și modelelor",
        value=get_preference(MEMORY_DB_PATH, "auto_routing_enabled", "1") != "0",
        help="Detectează automat întrebările despre cursuri, generale și mixte.",
        key="auto_routing_setting",
    )
    st.session_state.auto_routing_enabled = auto_routing
    set_preference(MEMORY_DB_PATH, "auto_routing_enabled", "1" if auto_routing else "0")

    if changed:
        st.success("Profilele de model au fost salvate local.")
    last_route = st.session_state.get("last_model_route") or {}
    if last_route:
        st.caption(
            f"Ultima întrebare: {last_route.get('model', '-')} · "
            f"{last_route.get('reason', 'rutare automată')}"
        )


def settings_tab() -> None:
    st.subheader("Setari")
    st.info("Setarile rapide pentru model, documente si server raman in sidebar.")
    model_routing_settings()
    st.divider()
    st.markdown("#### Concurență server AI")
    saved_limit = get_preference(
        LOCAL_MEMORY_DB_PATH,
        "max_concurrent_generations",
        "1",
    )
    try:
        current_limit = max(1, min(4, int(saved_limit or "1")))
    except ValueError:
        current_limit = 1
    selected_limit = st.number_input(
        "Generări LLM simultane",
        min_value=1,
        max_value=4,
        value=current_limit,
        step=1,
        help=(
            "Pentru RTX 3070 8GB este recomandată valoarea 1. Retrieval-ul poate "
            "rula concurent, dar generările Ollama sunt limitate de această valoare."
        ),
        key="max_concurrent_generations_setting",
    )
    if int(selected_limit) != current_limit:
        set_preference(
            LOCAL_MEMORY_DB_PATH,
            "max_concurrent_generations",
            str(int(selected_limit)),
        )
        st.success("Limita a fost salvată și se aplică cererilor noi.")
    queue_diagnostics = INFERENCE_QUEUE.diagnostics()
    metric_columns = st.columns(4)
    metric_columns[0].metric("Utilizatori activi", queue_diagnostics["active_users"])
    metric_columns[1].metric("În coadă", queue_diagnostics["queued_requests"])
    metric_columns[2].metric("Rulează", queue_diagnostics["running_requests"])
    metric_columns[3].metric(
        "Timp mediu",
        f"{queue_diagnostics['average_response_seconds']:.1f}s",
    )
    st.divider()
    academic_metadata_editor()
    st.divider()
    render_server_access_panel()
    st.divider()
    render_diagnostics_panel()


NOTEBOOK_CATEGORY_LABELS = {
    "professor_advice": "Sfat de la profesor",
    "reminder": "Reminder",
    "personal_note": "Notă personală",
    "study_tip": "Sfat de studiu",
    "exam_hint": "Indiciu pentru examen",
    "study_preference": "Preferință de studiu",
}


def notebook_page() -> None:
    st.subheader("Notebook")
    st.caption(
        "Note private, folosite automat pentru personalizare. Co-pilot Facultate nu "
        "adaugă, editează sau șterge nimic fără confirmarea ta explicită."
    )
    categories = [
        category
        for category in NOTEBOOK_CATEGORY_LABELS
        if category in NOTEBOOK_CATEGORIES
    ]
    with st.form("add_notebook_entry_form", clear_on_submit=True):
        category = st.selectbox(
            "Categorie",
            categories,
            format_func=lambda value: NOTEBOOK_CATEGORY_LABELS[value],
        )
        content = st.text_area(
            "Notă",
            placeholder="Ex: Profesorul a spus că acest capitol apare sigur la examen.",
        )
        confirmed = st.checkbox("Confirm că vreau să salvez această notă")
        submitted = st.form_submit_button(
            "Adaugă în Notebook",
            disabled=not confirmed,
            type="primary",
        )
    if submitted:
        try:
            add_notebook_entry(
                MEMORY_DB_PATH,
                category,
                content,
                confirmed=confirmed,
            )
            st.success("Nota a fost salvată.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    entries = get_notebook_entries(MEMORY_DB_PATH, limit=200)
    if not entries:
        st.info("Notebook-ul este gol.")
        return

    for entry in entries:
        entry_id = int(entry["id"])
        label = NOTEBOOK_CATEGORY_LABELS.get(entry["category"], entry["category"])
        with st.expander(f"{label} · {conversation_timestamp(entry['updated_at'])}"):
            edited_category = st.selectbox(
                "Categorie",
                categories,
                index=(
                    categories.index(entry["category"])
                    if entry["category"] in categories
                    else 0
                ),
                format_func=lambda value: NOTEBOOK_CATEGORY_LABELS[value],
                key=f"notebook_category_{entry_id}",
            )
            edited_content = st.text_area(
                "Conținut",
                value=entry["content"],
                key=f"notebook_content_{entry_id}",
            )
            confirm_edit = st.checkbox(
                "Confirm modificarea",
                key=f"notebook_confirm_edit_{entry_id}",
            )
            if st.button(
                "Salvează modificarea",
                disabled=not confirm_edit,
                key=f"notebook_save_{entry_id}",
            ):
                update_notebook_entry(
                    MEMORY_DB_PATH,
                    entry_id,
                    edited_category,
                    edited_content,
                    confirmed=confirm_edit,
                )
                st.rerun()
            confirm_delete = st.checkbox(
                "Confirm ștergerea definitivă",
                key=f"notebook_confirm_delete_{entry_id}",
            )
            if st.button(
                "Șterge nota",
                disabled=not confirm_delete,
                key=f"notebook_delete_{entry_id}",
            ):
                delete_notebook_entry(
                    MEMORY_DB_PATH,
                    entry_id,
                    confirmed=confirm_delete,
                )
                st.rerun()


def server_status_tab() -> None:
    st.subheader("Server Status")
    urls = get_server_urls()
    queue = INFERENCE_QUEUE.diagnostics()
    connections = SERVER_CONNECTIONS.diagnostics()
    gpu = cached_gpu_status()

    summary = st.columns(5)
    summary[0].metric("Deployment", urls["deployment_mode"])
    summary[1].metric("HTTPS", "Activ" if urls["https"] else "Inactiv")
    summary[2].metric("Utilizatori conectați", connections["connected_users"])
    summary[3].metric("În coadă", queue["queued_requests"])
    summary[4].metric("Generări active", queue["running_requests"])

    st.caption(
        "Utilizatorii conectați sunt sesiuni observate în ultimele "
        f"{connections['ttl_seconds'] // 60} minute."
    )
    st.markdown("#### URL-uri")
    for label, key in (
        ("Local", "local"),
        ("LAN", "lan"),
        ("Tailscale", "tailscale"),
        ("Public", "public"),
    ):
        st.code(f"{label}: {urls.get(key) or 'indisponibil / neconfigurat'}")
    public_api_url = configured_public_api_url()
    if public_api_url:
        st.code(f"Public API: {public_api_url}")

    st.markdown("#### GPU")
    if gpu.get("available"):
        gpu_columns = st.columns(4)
        gpu_columns[0].metric("GPU", gpu["name"])
        gpu_columns[1].metric("Utilizare", f"{gpu['utilization_percent']}%")
        gpu_columns[2].metric(
            "VRAM",
            f"{gpu['memory_used_mb']} / {gpu['memory_total_mb']} MB",
        )
        gpu_columns[3].metric("Temperatură", f"{gpu['temperature_c']}°C")
    else:
        st.info("Metricile GPU nu sunt disponibile prin nvidia-smi.")

    st.markdown("#### Protecții")
    st.write(
        {
            "autentificare": "ON" if authentication_enabled() else "OFF",
            "limită fișier MB": environment_int(
                "FACULTY_COPILOT_MAX_UPLOAD_MB", 100, 1, 2048
            ),
            "limită fișiere/cerere": environment_int(
                "FACULTY_COPILOT_MAX_UPLOAD_FILES", 10, 1, 100
            ),
            "cereri simultane API": environment_int(
                "FACULTY_COPILOT_MAX_CONCURRENT_REQUESTS", 32, 1, 512
            ),
            "cereri/IP/minut": environment_int(
                "FACULTY_COPILOT_IP_RATE_LIMIT", 60, 10, 10000
            ),
            "acțiuni UI/sesiune/minut": environment_int(
                "FACULTY_COPILOT_STREAMLIT_ACTION_RATE_LIMIT", 20, 5, 1000
            ),
            "acțiuni UI simultane": environment_int(
                "FACULTY_COPILOT_MAX_CONCURRENT_UI_ACTIONS", 8, 1, 64
            ),
            "sloturi GPU": queue["max_concurrent_generations"],
        }
    )
    if urls["deployment_mode"] == "Public Internet" and not authentication_enabled():
        st.warning(
            "Modul public fără autentificare permite oricui are URL-ul să folosească "
            "profilurile fără parolă. Activează autentificarea înainte de distribuire largă."
        )


def progress_tab() -> None:
    st.subheader("Progresul tau")
    summary = get_dashboard_summary(MEMORY_DB_PATH)
    columns = st.columns(6)
    columns[0].metric("Intrebari", summary["total_questions"])
    columns[1].metric("Cursuri studiate", summary["documents_studied"])
    columns[2].metric("Subiecte slabe", summary["weak_topics"])
    columns[3].metric(
        "Medie quiz",
        "N/A"
        if summary["quiz_average"] is None
        else f"{summary['quiz_average']:.0f}%",
    )
    columns[4].metric("Streak", f"{summary.get('study_streak', 0)} zile")
    columns[5].metric("Planuri", summary.get("saved_plans", 0))

    st.markdown("#### Ultimele documente studiate")
    last_documents = summary.get("last_studied_documents") or get_last_studied_documents(
        MEMORY_DB_PATH,
        limit=5,
    )
    if last_documents:
        st.dataframe(last_documents, use_container_width=True, hide_index=True)
    else:
        st.caption("Nu exista inca documente studiate recent.")

    st.markdown("#### Documente studiate")
    studied_documents = get_studied_documents(MEMORY_DB_PATH)
    if studied_documents:
        st.dataframe(studied_documents, use_container_width=True, hide_index=True)
    else:
        st.caption("Nu exista inca documente in istoricul de studiu.")

    st.markdown("#### Subiecte slabe")
    weak_topics = get_weak_topics(MEMORY_DB_PATH, limit=50)
    if weak_topics:
        weak_rows = [
            {
                "subiect": item["topic"],
                "marcaj": item["status"],
                "document": item.get("document_name") or "-",
                "data": item["created_at"].replace("T", " "),
            }
            for item in weak_topics
        ]
        st.dataframe(weak_rows, use_container_width=True, hide_index=True)
    else:
        st.caption("Foloseste butoanele de sub raspuns pentru a marca dificultatile.")

    st.markdown("#### Intrebari recente")
    recent_questions = get_recent_questions(MEMORY_DB_PATH, limit=15)
    if recent_questions:
        for item in recent_questions:
            with st.expander(
                f"{item['created_at'].replace('T', ' ')} | {item['question']}"
            ):
                st.write(item.get("answer_summary") or "Fara rezumat.")
                documents = item.get("retrieved_documents") or []
                if documents:
                    st.caption(f"Documente: {', '.join(documents)}")
                sources = item.get("sources") or []
                if sources:
                    source_labels = []
                    for source in sources:
                        page = f", pagina {source['page']}" if source.get("page") else ""
                        source_labels.append(f"{source['file_name']}{page}")
                    st.caption(f"Surse: {'; '.join(source_labels)}")
    else:
        st.caption("Istoricul va aparea dupa prima intrebare.")

    st.markdown("#### Rezultate quiz")
    quiz_results = get_quiz_results(MEMORY_DB_PATH, limit=30)
    if quiz_results:
        quiz_rows = [
            {
                "data": item["created_at"].replace("T", " "),
                "intrebare": item["question"],
                "raspunsul tau": item.get("selected_answer") or "Fara raspuns",
                "raspuns corect": item["correct_answer"],
                "scor": "Corect" if item["score"] >= 1 else "Gresit",
                "document": item.get("source_document") or "-",
                "subiect": item.get("topic") or "-",
            }
            for item in quiz_results
        ]
        st.dataframe(quiz_rows, use_container_width=True, hide_index=True)
    else:
        st.caption("Rezultatele vor aparea dupa verificarea unui quiz.")

    st.markdown("#### Recomandari smart")
    documents = st.session_state.get("indexed_documents") or get_indexed_documents()
    for index, recommendation in enumerate(build_smart_recommendations(documents), start=1):
        st.write(f"{index}. {recommendation}")

    st.markdown("#### Planuri de sesiune recente")
    recent_plans = get_session_plans(MEMORY_DB_PATH, limit=3)
    if recent_plans:
        for plan in recent_plans:
            st.caption(
                f"{plan['created_at'].replace('T', ' ')} | {plan['title']} | "
                f"{plan['total_estimated_hours']:.1f}h estimate"
            )
    else:
        st.caption("Planurile generate vor aparea aici.")

    weak_review = st.session_state.get("weak_review")
    if weak_review:
        st.markdown("#### Recapitulare din subiectele slabe")
        st.write(weak_review["answer"])
        response = weak_review.get("response")
        if response is not None:
            with st.expander("Sursele recapitularii"):
                render_sources(response)

    st.info(f"Memoria de studiu este privata si ramane pe acest PC: {MEMORY_DB_PATH}")


def _legacy_main() -> None:
    ensure_project_dirs()
    st.set_page_config(page_title=APP_TITLE, page_icon=":books:", layout="wide")
    initialize_state()

    sidebar_ui()

    st.title(APP_TITLE)
    st.caption(
        "Copilot local pentru facultate: cursuri organizate, RAG, quiz, flashcards, progres si planuri de sesiune."
    )
    st.info(f"Proiect activ: {PROJECT_ROOT}")

    urls = get_server_urls()
    if urls["server_mode"]:
        access_lines = [f"Local: {urls['local']}"]
        if urls["lan"]:
            access_lines.append(f"LAN: {urls['lan']}")
        if urls["tailscale"]:
            access_lines.append(f"Tailscale: {urls['tailscale']}")
        st.info(" | ".join(access_lines))

    tab_names = ["Întrebări", "Flashcards", "Quiz", "Progres", "Plan sesiune", "Setări"]
    tabs = st.tabs(tab_names)

    with tabs[0]:
        questions_tab()
    with tabs[1]:
        flashcards_tab()
    with tabs[2]:
        quiz_tab()
    with tabs[3]:
        progress_tab()
    with tabs[4]:
        session_plan_tab()
    with tabs[5]:
        settings_tab()


def render_workspace_application(username: str) -> None:
    ensure_project_dirs()
    initialize_state()
    SERVER_CONNECTIONS.heartbeat(
        st.session_state.study_session_id,
        username,
        "streamlit",
    )
    sidebar_ui()
    st.markdown(
        """
        <style>
        .block-container {max-width: 980px; padding-top: 1.4rem; padding-bottom: 7rem;}
        [data-testid="stChatMessage"] {border-radius: 18px; padding: .65rem 1rem; margin: .45rem 0;}
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
            margin-left: 14%; background: rgba(110, 90, 210, .13);
        }
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
            margin-right: 9%; background: rgba(128, 128, 128, .07);
        }
        [data-testid="stChatInput"] {max-width: 940px; margin: auto;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    page = st.session_state.get("assistant_page", "Chat")
    workspace_name = USER_ACCOUNTS.workspace().workspace_name
    if page == "Chat":
        active_id = st.session_state.get("active_conversation_id")
        active = get_conversation(MEMORY_DB_PATH, active_id) if active_id else None
        split_view = bool(st.session_state.get("pdf_viewer_file"))
        chat_column, pdf_column = (
            st.columns([1.05, 0.95], gap="medium")
            if split_view
            else (st.container(), None)
        )
        with chat_column:
            st.title(active.get("title") if active else "Cu ce te pot ajuta?")
            st.caption(
                f"{username} · workspace {workspace_name} · AI-ul folosește automat "
                "contextul acestui workspace"
            )
            render_proactive_study_agent()
            questions_tab()
        if pdf_column is not None:
            with pdf_column:
                render_pdf_viewer()
    elif page == "Flashcards":
        st.title("Flashcards")
        flashcards_tab()
    elif page == "Quiz":
        st.title("Quiz")
        quiz_tab()
    elif page == "Progres":
        st.title("Progres")
        progress_tab()
    elif page == "Plan sesiune":
        st.title("Plan sesiune")
        session_plan_tab()
    elif page == "Notebook":
        st.title("Notebook")
        notebook_page()
    elif page == "Setări":
        st.title("Setări")
        settings_tab()
    else:
        server_status_tab()


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon=":books:", layout="wide")
    ensure_project_dirs()
    username = streamlit_user_identity()
    with user_context(username):
        workspace_slug = render_workspace_sidebar(username)
        with workspace_context(workspace_slug):
            render_workspace_application(username)


if __name__ == "__main__":
    main()
