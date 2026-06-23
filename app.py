from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path

import chromadb
import httpx
import streamlit as st
from llama_index.core import Settings, SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.storage.storage_context import StorageContext
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore


APP_TITLE = "AI Study Assistant v2"
PROJECT_ROOT = Path(__file__).resolve().parent
DOCUMENTS_DIR = PROJECT_ROOT / "documents"
STORAGE_DIR = PROJECT_ROOT / "storage"
CHROMA_DIR = STORAGE_DIR / "chroma"
DEFAULT_COLLECTION_NAME = "study_documents_v2"
ACTIVE_COLLECTION_FILE = STORAGE_DIR / "active_collection.txt"
DEFAULT_LLM_MODEL = "qwen3:8b"
SMARTER_MODEL = "qwen3:14b"
EMBED_MODEL = "nomic-embed-text"
OLLAMA_URL = "http://localhost:11434"
SUPPORTED_EXTS = {".pdf", ".docx", ".pptx"}
INVENTORY_KEYWORDS = ("indexat", "indexate", "incarcat", "incarcate")
MIN_RETRIEVAL_TOP_K = 10
CHROMA_CANDIDATE_TOP_K = 24
MAX_CONTEXT_CHARS = 24000
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


class StudyResponse:
    def __init__(self, text: str, chunks: list[dict], debug: dict):
        self.text = text
        self.chunks = chunks
        self.debug = debug
        self.source_nodes = []

    def __str__(self) -> str:
        return self.text


def ensure_project_dirs() -> None:
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)


def configure_llama_index(model_name: str) -> None:
    Settings.llm = Ollama(model=model_name, request_timeout=240.0)
    Settings.embed_model = OllamaEmbedding(model_name=EMBED_MODEL)
    Settings.chunk_size = 1000
    Settings.chunk_overlap = 160


def ollama_is_running() -> bool:
    try:
        response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2.0)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def list_ollama_models() -> list[str]:
    try:
        response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError:
        return []

    return sorted(model.get("name", "") for model in data.get("models", []) if model.get("name"))


def list_llm_models() -> list[str]:
    return [model for model in list_ollama_models() if "embed" not in model.lower()]


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


def get_active_collection_name() -> str:
    if ACTIVE_COLLECTION_FILE.exists():
        name = ACTIVE_COLLECTION_FILE.read_text(encoding="utf-8").strip()
        if name:
            return name
    return DEFAULT_COLLECTION_NAME


def set_active_collection_name(name: str) -> None:
    ensure_project_dirs()
    ACTIVE_COLLECTION_FILE.write_text(name, encoding="utf-8")


def get_collection(collection_name: str | None = None):
    client = get_chroma_client()
    return client.get_or_create_collection(collection_name or get_active_collection_name())


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

    unique_files = sorted({file.resolve() for file in files})
    return [str(file) for file in unique_files]


def infer_discipline(file_path: str) -> str:
    path = Path(file_path)
    parent = path.parent.name.strip()
    if parent and parent.lower() not in {"documents", "ai", PROJECT_ROOT.name.lower()}:
        return parent

    stem_parts = [part.strip() for part in path.stem.split("-") if part.strip()]
    if len(stem_parts) >= 2:
        return stem_parts[1]

    return "Necunoscuta"


def file_metadata(file_path: str) -> dict:
    path = Path(file_path).resolve()
    return {
        "file_name": path.name,
        "file_path": str(path),
        "file_extension": path.suffix.lower(),
        "discipline": infer_discipline(str(path)),
    }


def build_index(paths: list[str]) -> tuple[int, int]:
    files = collect_supported_files(paths)
    if not files:
        raise ValueError("Nu am gasit fisiere PDF, DOCX sau PPTX in selectia curenta.")

    collection_name = f"{DEFAULT_COLLECTION_NAME}_{int(time.time())}"
    set_active_collection_name(collection_name)
    collection = get_collection(collection_name)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    documents = SimpleDirectoryReader(
        input_files=files,
        file_metadata=file_metadata,
    ).load_data()
    for document in documents:
        metadata = document.metadata
        page = metadata.get("page_label") or metadata.get("page_number") or metadata.get("page")
        if page:
            metadata["page_number"] = str(page)
        file_path = metadata.get("file_path")
        if file_path:
            metadata["file_name"] = Path(file_path).name
            metadata["file_extension"] = Path(file_path).suffix.lower()
            metadata["discipline"] = metadata.get("discipline") or infer_discipline(file_path)

    VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        show_progress=True,
    )

    return len(files), count_indexed_chunks()


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


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in searchable_text(text).split()
        if len(token) >= 2 and token not in STOPWORDS
    }


def clean_model_text(text: str) -> str:
    return re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()


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

        key = file_path or file_name
        page = metadata.get("page_number") or metadata.get("page_label") or metadata.get("page")
        discipline = metadata.get("discipline") or infer_discipline(file_path or file_name)

        document = documents.setdefault(
            key,
            {
                "file_name": file_name,
                "file_path": file_path,
                "discipline": discipline,
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
        discipline = document.get("discipline") or "Necunoscuta"
        lines.append(
            f"{index}. {document['file_name']} - {document['chunks']} fragmente{pages} "
            f"- disciplina: {discipline}"
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


def get_intro_chunks(document: dict, limit: int = 4) -> list[dict]:
    file_path = document.get("file_path")
    if not file_path:
        return []

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
    top_k: int = MIN_RETRIEVAL_TOP_K,
    summary_mode: bool = False,
) -> tuple[list[dict], dict]:
    top_k = max(top_k, MIN_RETRIEVAL_TOP_K)
    collection = get_collection()
    query_text = question
    where = None

    if document:
        where = {"file_path": document["file_path"]}
        query_text = (
            f"{question}\nDocument: {document['file_name']}\n"
            "Rezumat continut idei principale definitii formule exemple."
        )

    query_embedding = Settings.embed_model.get_query_embedding(query_text)
    available_chunks = document.get("chunks", CHROMA_CANDIDATE_TOP_K) if document else collection.count()
    candidate_count = min(max(CHROMA_CANDIDATE_TOP_K, top_k), max(available_chunks, 1))
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=candidate_count,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    candidates = chroma_result_chunks(result)

    if document and summary_mode:
        candidates = unique_chunks(get_intro_chunks(document) + candidates)

    reranked = rerank_chunks(question, candidates, min(top_k, len(candidates)))
    debug = {
        "mode": "document" if document else "global",
        "target_document": document.get("file_name") if document else None,
        "candidate_count": len(candidates),
        "returned_count": len(reranked),
        "documents": sorted(
            {
                (chunk.get("metadata") or {}).get("file_name", "document necunoscut")
                for chunk in reranked
            }
        ),
    }
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


def build_context(chunks: list[dict]) -> str:
    context_parts = []
    total_chars = 0
    for index, chunk in enumerate(chunks, start=1):
        text = chunk.get("text", "").strip()
        if not text:
            continue
        source = chunk_source_label(chunk)
        part = f"[Sursa {index}: {source}]\n{text}"
        if total_chars + len(part) > MAX_CONTEXT_CHARS:
            break
        context_parts.append(part)
        total_chars += len(part)
    return "\n\n".join(context_parts)


def complete_from_chunks(
    question: str,
    chunks: list[dict],
    debug: dict,
    document: dict | None = None,
    summary_mode: bool = False,
) -> StudyResponse:
    if not chunks:
        return StudyResponse("Nu am gasit fragmente relevante in documentele indexate.", [], debug)

    context = build_context(chunks)
    target = f"Document tinta: {document['file_name']}\n" if document else ""
    task = (
        "Fa un rezumat clar al documentului tinta."
        if summary_mode
        else "Raspunde la intrebare folosind numai contextul de mai jos."
    )
    prompt = (
        "/no_think\n"
        "Esti un asistent local pentru studiu. "
        "Foloseste exclusiv contextul furnizat. Nu inventa surse si nu folosi cunostinte externe. "
        "Cand exista surse, mentioneaza numele documentului si pagina.\n\n"
        f"{target}"
        f"Sarcina: {task}\n"
        f"Intrebare: {question}\n\n"
        f"Context:\n{context}\n\n"
        "Raspuns in romana:"
    )
    completion = Settings.llm.complete(prompt)
    return StudyResponse(clean_model_text(str(completion)), chunks, debug)


def query_documents(question: str, top_k: int = MIN_RETRIEVAL_TOP_K):
    document = detect_document_reference(question)
    summary_mode = bool(document and is_document_summary_question(question))
    chunks, debug = retrieve_chunks(
        question,
        document=document,
        top_k=max(top_k, MIN_RETRIEVAL_TOP_K),
        summary_mode=summary_mode,
    )
    return complete_from_chunks(
        question,
        chunks,
        debug,
        document=document,
        summary_mode=summary_mode,
    )


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


def generate_flashcards(topic: str, count: int) -> tuple[list[dict], object]:
    response = query_documents(
        "Genereaza "
        f"{count} flashcarduri despre: {topic}. "
        "Returneaza strict JSON, fara markdown, ca lista de obiecte cu cheile: "
        "front, back, source_hint. Fiecare flashcard trebuie sa fie verificabil din surse. "
        "Daca sursele nu contin destule informatii, returneaza []. Nu inventa.",
        top_k=MIN_RETRIEVAL_TOP_K,
    )
    return extract_json_array(str(response)), response


def generate_quiz(topic: str, count: int) -> tuple[list[dict], object]:
    response = query_documents(
        "Genereaza "
        f"{count} intrebari grila interactive despre: {topic}. "
        "Returneaza strict JSON, fara markdown, ca lista de obiecte cu cheile: "
        "question, options, answer_index, explanation. "
        "options trebuie sa fie o lista cu 4 variante. answer_index este index 0-3. "
        "Daca sursele nu contin destule informatii, returneaza []. Nu inventa.",
        top_k=MIN_RETRIEVAL_TOP_K,
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
    if not isinstance(response, StudyResponse):
        return

    with st.expander("Debug retrieval"):
        debug = response.debug
        st.write(f"Mod: {debug.get('mode')}")
        if debug.get("target_document"):
            st.write(f"Document tinta: {debug['target_document']}")
        st.write(f"Documente recuperate: {', '.join(debug.get('documents') or [])}")
        st.write(f"Chunk-uri candidate: {debug.get('candidate_count')}")
        st.write(f"Chunk-uri trimise la model: {debug.get('returned_count')}")
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
    st.session_state.indexed_documents = get_indexed_documents()


def render_indexed_documents_panel() -> None:
    st.header("Documente indexate")

    if st.button("Refresh document list"):
        refresh_indexed_documents_state()

    documents = st.session_state.get("indexed_documents")
    if documents is None:
        documents = get_indexed_documents()
        st.session_state.indexed_documents = documents

    if not documents:
        st.caption("Nu exista documente indexate.")
        return

    st.caption(f"{len(documents)} documente unice")
    for document in documents:
        page_text = f" | pagini: {document['page_count']}" if document["page_count"] else ""
        with st.expander(f"{document['file_name']}"):
            st.write(f"Fragmente: {document['chunks']}{page_text}")
            st.write(f"Disciplina: {document.get('discipline') or 'Necunoscuta'}")
            if document.get("file_path"):
                st.caption(document["file_path"])


def render_diagnostics_panel() -> None:
    st.header("Diagnostics")
    st.caption(f"Current project root: {PROJECT_ROOT}")
    st.caption(f"Current storage folder: {STORAGE_DIR}")
    st.caption(f"Current documents folder: {DOCUMENTS_DIR}")
    st.caption(f"Current database path: {CHROMA_DIR}")
    st.caption(f"Active collection: {get_active_collection_name()}")


def initialize_state() -> None:
    ensure_project_dirs()
    st.session_state.setdefault("selected_paths", [str(DOCUMENTS_DIR)])
    st.session_state.setdefault("flashcards", [])
    st.session_state.setdefault("quiz", [])
    st.session_state.setdefault("quiz_checked", False)
    st.session_state.setdefault("indexed_documents", None)


def selected_model_ui(models: list[str]) -> str:
    options = list(models)
    for model in [SMARTER_MODEL, DEFAULT_LLM_MODEL]:
        if model not in options:
            options.append(model)

    default = SMARTER_MODEL if SMARTER_MODEL in models else DEFAULT_LLM_MODEL
    index = options.index(default) if default in options else 0
    return st.selectbox("Model raspunsuri", options=options, index=index)


def sidebar_ui() -> str:
    with st.sidebar:
        st.header("Setari")

        models = list_llm_models()
        if ollama_is_running():
            st.success("Ollama ruleaza local.")
        else:
            st.error("Ollama nu raspunde pe http://localhost:11434.")

        model_name = selected_model_ui(models)
        if model_name not in models:
            st.warning("Modelul ales nu este instalat local.")
            if st.button("Descarca modelul ales"):
                try:
                    with st.spinner("Descarc modelul in Ollama..."):
                        st.success(pull_ollama_model(model_name))
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        configure_llama_index(model_name)

        st.divider()
        st.header("Documente")

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
        edited_paths = st.text_area("Selectie curenta", value=selected_paths_text, height=110)
        st.session_state.selected_paths = [
            line.strip() for line in edited_paths.splitlines() if line.strip()
        ]

        if st.button("Indexeaza selectia", type="primary"):
            try:
                if not ollama_is_running():
                    raise RuntimeError("Ollama nu raspunde. Porneste Ollama si incearca din nou.")
                with st.spinner("Indexez documentele local..."):
                    file_count, chunk_count = build_index(st.session_state.selected_paths)
                refresh_indexed_documents_state()
                st.success(f"Indexare finalizata: {file_count} fisiere, {chunk_count} fragmente.")
            except Exception as exc:
                st.error(str(exc))

        st.caption(f"Fragmente indexate: {count_indexed_chunks()}")
        st.caption(f"Baza locala: {CHROMA_DIR}")
        st.divider()
        render_indexed_documents_panel()
        st.divider()
        render_diagnostics_panel()

    return model_name


def answer_tab() -> None:
    question = st.text_area(
        "Intrebarea ta",
        placeholder="Exemplu: Cum se leaga conceptele X si Y intre cursuri?",
        height=130,
    )

    if st.button("Raspunde", type="primary"):
        if not question.strip():
            st.warning("Scrie mai intai o intrebare.")
            return
        if count_indexed_chunks() == 0:
            st.warning("Indexeaza mai intai documentele.")
            return

        if is_document_inventory_question(question):
            refresh_indexed_documents_state()
            st.subheader("Raspuns")
            st.write(indexed_documents_answer())
            return

        with st.spinner("Caut in documente si leg ideile relevante..."):
            response = query_documents(question, top_k=MIN_RETRIEVAL_TOP_K)

        st.subheader("Raspuns")
        st.write(clean_model_text(str(response)))
        st.subheader("Surse")
        render_sources(response)
        render_retrieval_debug(response)


def links_tab() -> None:
    topic = st.text_input("Tema de comparat", placeholder="Exemplu: memorie, invatare, algoritmi")

    if st.button("Compara si leaga ideile", type="primary"):
        if not topic.strip():
            st.warning("Scrie tema.")
            return
        if count_indexed_chunks() == 0:
            st.warning("Indexeaza mai intai documentele.")
            return

        with st.spinner("Compar cursurile si caut conexiuni..."):
            response = query_documents(
                "Compara documentele pentru tema: "
                f"{topic}. Structureaza raspunsul in: idei comune, diferente, contradictii, "
                "exemple din surse si o sinteza finala.",
                top_k=MIN_RETRIEVAL_TOP_K,
            )

        st.subheader("Comparatie")
        st.write(clean_model_text(str(response)))
        st.subheader("Surse")
        render_sources(response)
        render_retrieval_debug(response)


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
        with st.spinner("Generez flashcarduri din surse..."):
            cards, response = generate_flashcards(topic or "toate documentele", int(count))
        st.session_state.flashcards = cards
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
        with st.spinner("Generez quiz din documente..."):
            quiz, response = generate_quiz(topic or "toate documentele", int(count))
        st.session_state.quiz = quiz
        st.session_state.quiz_checked = False
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
        st.session_state.quiz_checked = True

    if st.session_state.quiz_checked:
        correct = 0
        for index, item in enumerate(st.session_state.quiz):
            options = item.get("options", [])
            answer_index = item.get("answer_index", -1)
            if not isinstance(answer_index, int) or answer_index < 0 or answer_index >= len(options):
                continue

            selected = st.session_state.get(f"quiz_answer_{index}")
            expected = options[answer_index]
            if selected == expected:
                correct += 1
                st.success(f"{index + 1}. Corect")
            else:
                st.error(f"{index + 1}. Raspuns corect: {expected}")
            explanation = item.get("explanation", "")
            if explanation:
                st.write(explanation)

        st.info(f"Scor: {correct}/{len(st.session_state.quiz)}")


def main() -> None:
    ensure_project_dirs()
    st.set_page_config(page_title=APP_TITLE, page_icon=":books:", layout="wide")
    initialize_state()

    sidebar_ui()

    st.title(APP_TITLE)
    st.caption("RAG local cu intrebari, conexiuni intre cursuri, flashcards si quiz.")
    st.info(f"Proiect activ: {PROJECT_ROOT}")

    tab_answer, tab_links, tab_flashcards, tab_quiz = st.tabs(
        ["Intrebari", "Legaturi intre cursuri", "Flashcards", "Quiz"]
    )

    with tab_answer:
        answer_tab()
    with tab_links:
        links_tab()
    with tab_flashcards:
        flashcards_tab()
    with tab_quiz:
        quiz_tab()


if __name__ == "__main__":
    main()
