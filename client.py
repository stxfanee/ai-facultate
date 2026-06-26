from __future__ import annotations

import json
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
import streamlit as st


APP_TITLE = "Faculty Copilot Client"
SETTINGS_DIR = Path.home() / ".faculty_copilot"
SETTINGS_FILE = SETTINGS_DIR / "client_settings.json"
DEFAULT_SERVER_URL = "http://localhost:8000"
REQUEST_TIMEOUT = 240.0


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(settings: dict) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def normalize_server_url(value: str) -> str:
    cleaned = (value or "").strip().rstrip("/")
    if not cleaned:
        return DEFAULT_SERVER_URL
    parsed = urlparse(cleaned)
    if not parsed.scheme:
        cleaned = f"http://{cleaned}"
    return cleaned.rstrip("/")


def client_session_id() -> str:
    if "client_session_id" not in st.session_state:
        st.session_state.client_session_id = str(uuid.uuid4())
    return st.session_state.client_session_id


def request_json(
    method: str,
    path: str,
    payload: dict | None = None,
) -> dict:
    server_url = st.session_state.server_url
    verify_tls = st.session_state.verify_tls
    url = f"{server_url}{path}"
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, verify=verify_tls) as client:
            response = client.request(method, url, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as exc:
        raise RuntimeError(
            "Nu ma pot conecta la server. Verifica adresa, Tailscale/LAN si daca "
            "start_server.bat ruleaza pe desktop."
        ) from exc
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail")
        except (ValueError, AttributeError):
            detail = exc.response.text
        raise RuntimeError(f"Serverul a raspuns cu eroare: {detail}") from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError(
            "Cererea a depasit timpul disponibil. Incearca modul Fast sau o intrebare mai scurta."
        ) from exc
    except httpx.TransportError as exc:
        raise RuntimeError(f"Eroare de retea: {exc}") from exc


def render_connection_sidebar() -> None:
    settings = load_settings()
    with st.sidebar:
        st.header("Conexiune server")
        server_input = st.text_input(
            "Adresa server",
            value=st.session_state.get(
                "server_url",
                settings.get("server_url", DEFAULT_SERVER_URL),
            ),
            help="Exemple: http://192.168.1.50:8000 sau http://100.x.y.z:8000 prin Tailscale.",
        )
        st.session_state.server_url = normalize_server_url(server_input)
        st.session_state.username = st.text_input(
            "Username optional",
            value=st.session_state.get("username", settings.get("username", "")),
        )
        remember = st.checkbox(
            "Remember server",
            value=bool(settings.get("remember_server", True)),
        )
        st.session_state.verify_tls = st.checkbox(
            "Verifica certificatul HTTPS",
            value=bool(settings.get("verify_tls", True)),
            help="Debifeaza doar pentru certificate locale/self-signed de incredere.",
        )

        if remember:
            save_settings(
                {
                    "server_url": st.session_state.server_url,
                    "username": st.session_state.username,
                    "remember_server": True,
                    "verify_tls": st.session_state.verify_tls,
                }
            )
        else:
            try:
                SETTINGS_FILE.unlink(missing_ok=True)
            except OSError:
                pass

        if st.button("Testeaza conexiunea"):
            try:
                health = request_json("GET", "/health")
                st.session_state.health = health
                st.success("Conectat la server.")
            except RuntimeError as exc:
                st.error(str(exc))

        st.caption(f"Server activ: {st.session_state.server_url}")
        st.caption("Clientul nu ruleaza Ollama, nu descarca modele si nu creeaza ChromaDB.")
        st.caption("Pentru acces din afara retelei locale foloseste Tailscale.")


def payload_base() -> dict:
    return {
        "session_id": client_session_id(),
        "username": st.session_state.get("username") or None,
        "response_mode": st.session_state.get("response_mode", "Balanced"),
    }


def render_health() -> None:
    health = st.session_state.get("health")
    if not health:
        try:
            health = request_json("GET", "/health")
            st.session_state.health = health
        except RuntimeError as exc:
            st.warning(str(exc))
            return

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Server", health.get("status", "necunoscut"))
    col_b.metric("Ollama pe server", "da" if health.get("ollama") else "nu")
    col_c.metric("Documente", health.get("documents", 0))

    urls = health.get("urls") or {}
    with st.expander("URL-uri server"):
        st.write(f"Local: {urls.get('local') or '-'}")
        st.write(f"LAN: {urls.get('lan') or '-'}")
        st.write(f"Tailscale: {urls.get('tailscale') or '-'}")
        st.write(f"Docs API: {urls.get('docs') or '-'}")
        st.caption("Inferenta AI ruleaza numai pe serverul desktop.")


def load_documents() -> list[dict]:
    data = request_json("GET", "/documents")
    return data.get("documents") or []


def source_label(source: dict) -> str:
    page = f", pagina {source.get('page')}" if source.get("page") else ""
    score = f" | scor {source.get('score')}" if source.get("score") is not None else ""
    return f"{source.get('file_name', 'document')}{page}{score}"


def render_sources(sources: list[dict]) -> None:
    if not sources:
        return
    st.markdown("#### Surse")
    for source in sources:
        st.write(f"- {source_label(source)}")


def questions_tab() -> None:
    st.subheader("Intrebari RAG")
    documents = st.session_state.get("documents_cache")
    if documents is None:
        try:
            documents = load_documents()
            st.session_state.documents_cache = documents
        except RuntimeError as exc:
            st.error(str(exc))
            documents = []

    document_names = ["Global"] + [document["file_name"] for document in documents]
    selected_document = st.selectbox("Document optional", options=document_names)
    question = st.text_area("Intrebarea ta", height=140)
    if st.button("Trimite intrebarea", type="primary"):
        if not question.strip():
            st.warning("Scrie o intrebare.")
            return
        payload = {
            **payload_base(),
            "question": question,
            "document": None if selected_document == "Global" else selected_document,
        }
        try:
            with st.spinner("Astept raspunsul serverului..."):
                data = request_json("POST", "/ask", payload)
            st.markdown("#### Raspuns")
            st.write(data.get("answer", ""))
            render_sources(data.get("sources") or [])
        except RuntimeError as exc:
            st.error(str(exc))


def compare_tab() -> None:
    st.subheader("Compara cursuri")
    try:
        documents = st.session_state.get("documents_cache") or load_documents()
        st.session_state.documents_cache = documents
    except RuntimeError as exc:
        st.error(str(exc))
        return

    names = [document["file_name"] for document in documents]
    selected = st.multiselect("Documente", options=names)
    topic = st.text_input("Tema comparatiei")
    col_a, col_b = st.columns(2)
    with col_a:
        max_chunks = st.number_input("Max. fragmente per curs", 1, 12, 4)
    with col_b:
        max_tokens = st.number_input("Lungime maxima raspuns", 300, 3000, 1200, step=100)

    if st.button("Compara", type="primary"):
        if len(selected) < 2:
            st.warning("Alege cel putin doua documente.")
            return
        if not topic.strip():
            st.warning("Scrie tema comparatiei.")
            return
        payload = {
            **payload_base(),
            "topic": topic,
            "documents": selected,
            "max_chunks_per_course": int(max_chunks),
            "max_answer_tokens": int(max_tokens),
        }
        try:
            with st.spinner("Serverul compara rezumatele cursurilor..."):
                data = request_json("POST", "/compare", payload)
            st.markdown("#### Comparatie")
            st.write(data.get("answer", ""))
            render_sources(data.get("sources") or [])
        except RuntimeError as exc:
            st.error(str(exc))


def flashcards_tab() -> None:
    st.subheader("Flashcards")
    col_topic, col_count = st.columns([3, 1])
    with col_topic:
        topic = st.text_input("Tema", key="flashcards_topic")
    with col_count:
        count = st.number_input("Numar", 1, 20, 8, key="flashcards_count")

    if st.button("Genereaza flashcards", type="primary"):
        payload = {**payload_base(), "topic": topic or "toate documentele", "count": int(count)}
        try:
            with st.spinner("Serverul genereaza flashcards..."):
                data = request_json("POST", "/flashcards", payload)
            for index, item in enumerate(data.get("items") or [], start=1):
                with st.expander(f"{index}. {item.get('front', 'Flashcard')}"):
                    st.write(item.get("back", ""))
                    if item.get("source_hint"):
                        st.caption(item["source_hint"])
            render_sources(data.get("sources") or [])
        except RuntimeError as exc:
            st.error(str(exc))


def quiz_tab() -> None:
    st.subheader("Quiz")
    col_topic, col_count = st.columns([3, 1])
    with col_topic:
        topic = st.text_input("Tema", key="quiz_topic")
    with col_count:
        count = st.number_input("Intrebari", 1, 20, 5, key="quiz_count")

    if st.button("Genereaza quiz", type="primary"):
        payload = {**payload_base(), "topic": topic or "toate documentele", "count": int(count)}
        try:
            with st.spinner("Serverul genereaza quiz..."):
                data = request_json("POST", "/quiz", payload)
            st.session_state.quiz_items = data.get("items") or []
            st.session_state.quiz_sources = data.get("sources") or []
        except RuntimeError as exc:
            st.error(str(exc))

    quiz_items = st.session_state.get("quiz_items") or []
    for index, item in enumerate(quiz_items):
        options = item.get("options") or []
        if options:
            st.radio(item.get("question", f"Intrebarea {index + 1}"), options, key=f"client_quiz_{index}")

    if quiz_items and st.button("Verifica local raspunsurile"):
        correct = 0
        for index, item in enumerate(quiz_items):
            options = item.get("options") or []
            answer_index = item.get("answer_index", -1)
            selected = st.session_state.get(f"client_quiz_{index}")
            expected = options[answer_index] if 0 <= answer_index < len(options) else None
            if selected == expected:
                correct += 1
                st.success(f"{index + 1}. Corect")
            else:
                st.error(f"{index + 1}. Raspuns corect: {expected}")
            if item.get("explanation"):
                st.write(item["explanation"])
        st.info(f"Scor local: {correct}/{len(quiz_items)}")
        render_sources(st.session_state.get("quiz_sources") or [])


def documents_tab() -> None:
    st.subheader("Documente de pe server")
    if st.button("Refresh documente"):
        st.session_state.documents_cache = None
    try:
        documents = st.session_state.get("documents_cache") or load_documents()
        st.session_state.documents_cache = documents
    except RuntimeError as exc:
        st.error(str(exc))
        return

    if not documents:
        st.info("Serverul nu are documente indexate.")
        return
    rows = [
        {
            "an": document.get("academic_year"),
            "materie": document.get("subject") or document.get("discipline"),
            "curs": document.get("course"),
            "document": document.get("file_name"),
            "pagini": document.get("page_count"),
            "fragmente": document.get("chunks"),
        }
        for document in documents
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def settings_tab() -> None:
    st.subheader("Setari client")
    st.write(f"Setarile salvate sunt aici: `{SETTINGS_FILE}`")
    st.write("Clientul comunica doar prin JSON cu FastAPI.")
    st.write("Nu porni Ollama, nu descarca modele si nu indexa documente pe laptopul client.")
    if st.button("Sterge setarile salvate"):
        try:
            SETTINGS_FILE.unlink(missing_ok=True)
            st.success("Setarile au fost sterse.")
        except OSError as exc:
            st.error(f"Nu am putut sterge setarile: {exc}")


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon=":books:", layout="wide")
    settings = load_settings()
    st.session_state.setdefault("server_url", settings.get("server_url", DEFAULT_SERVER_URL))
    st.session_state.setdefault("username", settings.get("username", ""))
    st.session_state.setdefault("verify_tls", bool(settings.get("verify_tls", True)))
    st.session_state.setdefault("response_mode", "Balanced")

    render_connection_sidebar()

    st.title(APP_TITLE)
    st.caption("Interfata client pentru serverul Faculty Copilot. AI-ul ruleaza pe desktop.")
    render_health()

    st.session_state.response_mode = st.radio(
        "Mod raspuns",
        options=["Fast", "Balanced", "Accurate"],
        index=["Fast", "Balanced", "Accurate"].index(st.session_state.response_mode),
        horizontal=True,
    )

    tabs = st.tabs(["Intrebari", "Compara", "Flashcards", "Quiz", "Documente", "Setari"])
    with tabs[0]:
        questions_tab()
    with tabs[1]:
        compare_tab()
    with tabs[2]:
        flashcards_tab()
    with tabs[3]:
        quiz_tab()
    with tabs[4]:
        documents_tab()
    with tabs[5]:
        settings_tab()


if __name__ == "__main__":
    main()
