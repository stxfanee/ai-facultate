from __future__ import annotations

import json
import re
import time
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
CHROMA_DIR = Path("storage/chroma")
DEFAULT_COLLECTION_NAME = "study_documents_v2"
ACTIVE_COLLECTION_FILE = Path("storage/active_collection.txt")
DEFAULT_LLM_MODEL = "qwen3:8b"
SMARTER_MODEL = "qwen3:14b"
EMBED_MODEL = "nomic-embed-text"
OLLAMA_URL = "http://localhost:11434"
SUPPORTED_EXTS = {".pdf", ".docx", ".pptx"}


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
    selected = filedialog.askdirectory(title="Alege folderul cu cursuri")
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
        filetypes=[
            ("Documente curs", "*.pdf *.docx *.pptx"),
            ("PDF", "*.pdf"),
            ("Word", "*.docx"),
            ("PowerPoint", "*.pptx"),
        ],
    )
    root.destroy()
    return list(selected)


def get_chroma_client() -> chromadb.PersistentClient:
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_active_collection_name() -> str:
    if ACTIVE_COLLECTION_FILE.exists():
        name = ACTIVE_COLLECTION_FILE.read_text(encoding="utf-8").strip()
        if name:
            return name
    return DEFAULT_COLLECTION_NAME


def set_active_collection_name(name: str) -> None:
    ACTIVE_COLLECTION_FILE.parent.mkdir(parents=True, exist_ok=True)
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
        path = Path(raw_path).expanduser()
        if not path.exists():
            continue

        if path.is_dir():
            for ext in SUPPORTED_EXTS:
                files.extend(path.rglob(f"*{ext}"))
        elif path.is_file() and path.suffix.lower() in SUPPORTED_EXTS:
            files.append(path)

    unique_files = sorted({file.resolve() for file in files})
    return [str(file) for file in unique_files]


def build_index(paths: list[str]) -> tuple[int, int]:
    files = collect_supported_files(paths)
    if not files:
        raise ValueError("Nu am gasit fisiere PDF, DOCX sau PPTX in selectia curenta.")

    collection_name = f"{DEFAULT_COLLECTION_NAME}_{int(time.time())}"
    set_active_collection_name(collection_name)
    collection = get_collection(collection_name)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    documents = SimpleDirectoryReader(input_files=files).load_data()
    VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        show_progress=True,
    )

    return len(files), count_indexed_chunks()


def load_index() -> VectorStoreIndex:
    return VectorStoreIndex.from_vector_store(vector_store=get_vector_store())


def make_query_engine(similarity_top_k: int = 6):
    index = load_index()
    return index.as_query_engine(
        similarity_top_k=similarity_top_k,
        response_mode="compact",
    )


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
    if not response.source_nodes:
        st.write("Nu au fost returnate surse.")
        return

    for source in response.source_nodes:
        st.markdown(f"- {format_source(source)}")
        with st.expander("Fragment folosit"):
            st.write(source.node.get_content(metadata_mode="none"))


def query_documents(question: str, top_k: int = 6):
    query_engine = make_query_engine(similarity_top_k=top_k)
    prompt = (
        "/no_think\n"
        "Raspunde exclusiv pe baza documentelor incarcate. "
        "Leaga ideile intre cursuri cand exista conexiuni clare in surse. "
        "Daca informatia nu apare in documente, spune explicit ca nu ai gasit-o. "
        "Mentioneaza sursele in raspuns cand formulezi concluzii importante. "
        f"Intrebare: {question}"
    )
    return query_engine.query(prompt)


def clean_model_text(text: str) -> str:
    return re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()


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
        top_k=8,
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
        top_k=8,
    )
    return extract_json_array(str(response)), response


def initialize_state() -> None:
    st.session_state.setdefault("selected_paths", [str(Path("documents").resolve())])
    st.session_state.setdefault("flashcards", [])
    st.session_state.setdefault("quiz", [])
    st.session_state.setdefault("quiz_checked", False)


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
                st.success(f"Indexare finalizata: {file_count} fisiere, {chunk_count} fragmente.")
            except Exception as exc:
                st.error(str(exc))

        st.caption(f"Fragmente indexate: {count_indexed_chunks()}")
        st.caption(f"Baza locala: {CHROMA_DIR}")

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

        with st.spinner("Caut in documente si leg ideile relevante..."):
            response = query_documents(question, top_k=8)

        st.subheader("Raspuns")
        st.write(clean_model_text(str(response)))
        st.subheader("Surse")
        render_sources(response)


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
                top_k=10,
            )

        st.subheader("Comparatie")
        st.write(clean_model_text(str(response)))
        st.subheader("Surse")
        render_sources(response)


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
    st.set_page_config(page_title=APP_TITLE, page_icon=":books:", layout="wide")
    initialize_state()

    model_name = sidebar_ui()

    st.title(APP_TITLE)
    st.caption("RAG local cu intrebari, conexiuni intre cursuri, flashcards si quiz.")

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
