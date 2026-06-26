from __future__ import annotations

import json
import os
import queue
import ssl
import threading
import uuid
from pathlib import Path
from tkinter import (
    BooleanVar,
    BOTH,
    END,
    LEFT,
    RIGHT,
    X,
    Y,
    Button,
    Checkbutton,
    Entry,
    Frame,
    Label,
    Listbox,
    Scrollbar,
    Spinbox,
    StringVar,
    Tk,
    messagebox,
)
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


APP_TITLE = "AI Study Copilot Client"
DEFAULT_SERVER_URL = "http://localhost:8000"
REQUEST_TIMEOUT_SECONDS = 240


def settings_file() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "AI Study Copilot Client" / "settings.json"
    return Path.home() / ".ai_study_copilot_client" / "settings.json"


def load_settings() -> dict:
    path = settings_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(settings: dict) -> None:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_server_url(value: str) -> str:
    cleaned = (value or "").strip().rstrip("/")
    if not cleaned:
        return DEFAULT_SERVER_URL
    if not urlparse(cleaned).scheme:
        cleaned = f"http://{cleaned}"
    return cleaned.rstrip("/")


class ApiClient:
    def __init__(self, server_url: str, verify_tls: bool = True) -> None:
        self.server_url = normalize_server_url(server_url)
        self.verify_tls = verify_tls

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self.server_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url, data=data, headers=headers, method=method)
        context = None
        if url.startswith("https://") and not self.verify_tls:
            context = ssl._create_unverified_context()

        try:
            with urlopen(
                request,
                timeout=REQUEST_TIMEOUT_SECONDS,
                context=context,
            ) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(detail)
                detail = parsed.get("detail", detail)
            except json.JSONDecodeError:
                pass
            raise RuntimeError(f"Server error {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(
                "Nu ma pot conecta la server. Verifica adresa LAN/Tailscale si "
                "daca start_server.bat ruleaza pe desktop."
            ) from exc
        except TimeoutError as exc:
            raise RuntimeError("Cererea a depasit timpul disponibil.") from exc

        if not body:
            return {}
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Serverul nu a returnat JSON valid: {body[:300]}") from exc


class CopilotClientApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1120x760")
        self.session_id = str(uuid.uuid4())
        self.settings = load_settings()
        self.documents: list[dict] = []
        self.task_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self.server_url = StringVar(
            value=self.settings.get("server_url", DEFAULT_SERVER_URL)
        )
        self.username = StringVar(value=self.settings.get("username", ""))
        self.response_mode = StringVar(value=self.settings.get("response_mode", "Balanced"))
        self.remember_server = BooleanVar(value=self.settings.get("remember_server", True))
        self.verify_tls = BooleanVar(value=self.settings.get("verify_tls", True))

        self._build_layout()
        self._poll_queue()

    def api(self) -> ApiClient:
        return ApiClient(self.server_url.get(), verify_tls=self.verify_tls.get())

    def base_payload(self) -> dict:
        return {
            "session_id": self.session_id,
            "username": self.username.get().strip() or None,
            "response_mode": self.response_mode.get(),
        }

    def save_current_settings(self) -> None:
        if self.remember_server.get():
            save_settings(
                {
                    "server_url": normalize_server_url(self.server_url.get()),
                    "username": self.username.get().strip(),
                    "response_mode": self.response_mode.get(),
                    "remember_server": True,
                    "verify_tls": self.verify_tls.get(),
                }
            )
            self.set_status("Setari salvate local.")
        else:
            try:
                settings_file().unlink(missing_ok=True)
            except OSError:
                pass
            self.set_status("Remember server este dezactivat.")

    def _build_layout(self) -> None:
        connection = ttk.LabelFrame(self.root, text="Conexiune server AI")
        connection.pack(fill=X, padx=10, pady=8)

        Label(connection, text="Server URL").pack(side=LEFT, padx=(8, 4))
        Entry(connection, textvariable=self.server_url, width=42).pack(side=LEFT, padx=4)
        Label(connection, text="Username").pack(side=LEFT, padx=(12, 4))
        Entry(connection, textvariable=self.username, width=18).pack(side=LEFT, padx=4)
        ttk.Combobox(
            connection,
            textvariable=self.response_mode,
            values=["Fast", "Balanced", "Accurate"],
            width=10,
            state="readonly",
        ).pack(side=LEFT, padx=6)
        Checkbutton(connection, text="Remember server", variable=self.remember_server).pack(
            side=LEFT,
            padx=4,
        )
        Checkbutton(connection, text="Verify HTTPS", variable=self.verify_tls).pack(
            side=LEFT,
            padx=4,
        )
        Button(connection, text="Save", command=self.save_current_settings).pack(
            side=LEFT,
            padx=4,
        )
        Button(connection, text="Test", command=self.test_connection).pack(side=LEFT, padx=4)

        self.status = StringVar(
            value="Client usor: nu ruleaza Ollama, nu descarca modele, nu creeaza ChromaDB."
        )
        Label(self.root, textvariable=self.status, anchor="w").pack(fill=X, padx=12)

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill=BOTH, expand=True, padx=10, pady=8)

        self._build_questions_tab()
        self._build_flashcards_tab()
        self._build_quiz_tab()
        self._build_progress_tab()
        self._build_plan_tab()

    def _build_questions_tab(self) -> None:
        tab = Frame(self.tabs)
        self.tabs.add(tab, text="Întrebări")

        top = Frame(tab)
        top.pack(fill=X, padx=8, pady=8)
        Button(top, text="Refresh documente", command=self.refresh_documents).pack(side=LEFT)
        Label(top, text="Document").pack(side=LEFT, padx=(12, 4))
        self.question_document = StringVar(value="Global")
        self.question_document_box = ttk.Combobox(
            top,
            textvariable=self.question_document,
            values=["Global"],
            width=54,
            state="readonly",
        )
        self.question_document_box.pack(side=LEFT)
        Button(top, text="Trimite", command=self.ask_question).pack(side=RIGHT)

        self.question_input = ScrolledText(tab, height=7, wrap="word")
        self.question_input.pack(fill=X, padx=8, pady=(0, 8))
        self.question_output = ScrolledText(tab, wrap="word")
        self.question_output.pack(fill=BOTH, expand=True, padx=8, pady=8)

    def _build_flashcards_tab(self) -> None:
        tab = Frame(self.tabs)
        self.tabs.add(tab, text="Flashcards")

        top = Frame(tab)
        top.pack(fill=X, padx=8, pady=8)
        Label(top, text="Tema").pack(side=LEFT)
        self.flashcards_topic = StringVar()
        Entry(top, textvariable=self.flashcards_topic, width=60).pack(side=LEFT, padx=6)
        Label(top, text="Numar").pack(side=LEFT)
        self.flashcards_count = Spinbox(top, from_=1, to=20, width=5)
        self.flashcards_count.delete(0, END)
        self.flashcards_count.insert(0, "8")
        self.flashcards_count.pack(side=LEFT, padx=6)
        Button(top, text="Genereaza", command=self.generate_flashcards).pack(side=LEFT)

        self.flashcards_output = ScrolledText(tab, wrap="word")
        self.flashcards_output.pack(fill=BOTH, expand=True, padx=8, pady=8)

    def _build_quiz_tab(self) -> None:
        tab = Frame(self.tabs)
        self.tabs.add(tab, text="Quiz")

        top = Frame(tab)
        top.pack(fill=X, padx=8, pady=8)
        Label(top, text="Tema").pack(side=LEFT)
        self.quiz_topic = StringVar()
        Entry(top, textvariable=self.quiz_topic, width=60).pack(side=LEFT, padx=6)
        Label(top, text="Intrebari").pack(side=LEFT)
        self.quiz_count = Spinbox(top, from_=1, to=20, width=5)
        self.quiz_count.delete(0, END)
        self.quiz_count.insert(0, "5")
        self.quiz_count.pack(side=LEFT, padx=6)
        Button(top, text="Genereaza", command=self.generate_quiz).pack(side=LEFT)

        self.quiz_output = ScrolledText(tab, wrap="word")
        self.quiz_output.pack(fill=BOTH, expand=True, padx=8, pady=8)

    def _build_progress_tab(self) -> None:
        tab = Frame(self.tabs)
        self.tabs.add(tab, text="Progres")

        Button(tab, text="Refresh progres", command=self.refresh_progress).pack(
            anchor="w",
            padx=8,
            pady=8,
        )
        self.progress_output = ScrolledText(tab, wrap="word")
        self.progress_output.pack(fill=BOTH, expand=True, padx=8, pady=8)

    def _build_plan_tab(self) -> None:
        tab = Frame(self.tabs)
        self.tabs.add(tab, text="Plan sesiune")

        form = ttk.LabelFrame(tab, text="Date plan")
        form.pack(fill=X, padx=8, pady=8)

        Label(form, text="Materie").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.plan_subject = StringVar()
        self.plan_subject_box = ttk.Combobox(
            form,
            textvariable=self.plan_subject,
            values=[],
            width=28,
        )
        self.plan_subject_box.grid(row=0, column=1, sticky="w", padx=6, pady=4)
        self.plan_subject_box.bind("<<ComboboxSelected>>", lambda event: self.update_plan_documents())

        Label(form, text="Zile pana la examen").grid(row=0, column=2, sticky="w", padx=6)
        self.plan_days = Spinbox(form, from_=1, to=180, width=8)
        self.plan_days.delete(0, END)
        self.plan_days.insert(0, "14")
        self.plan_days.grid(row=0, column=3, sticky="w", padx=6)

        Label(form, text="Ore/zi manual").grid(row=0, column=4, sticky="w", padx=6)
        self.plan_hours = Spinbox(form, from_=0.5, to=12.0, increment=0.5, width=8)
        self.plan_hours.delete(0, END)
        self.plan_hours.insert(0, "2.0")
        self.plan_hours.grid(row=0, column=5, sticky="w", padx=6)

        self.plan_auto_hours = BooleanVar(value=True)
        Checkbutton(form, text="Auto ore/zi", variable=self.plan_auto_hours).grid(
            row=1,
            column=0,
            sticky="w",
            padx=6,
            pady=4,
        )

        Label(form, text="Dificultate").grid(row=1, column=1, sticky="e", padx=6)
        self.plan_difficulty = StringVar(value="medium")
        ttk.Combobox(
            form,
            textvariable=self.plan_difficulty,
            values=["low", "medium", "high"],
            width=10,
            state="readonly",
        ).grid(row=1, column=2, sticky="w", padx=6)

        self.plan_revision = BooleanVar(value=True)
        self.plan_quiz = BooleanVar(value=True)
        Checkbutton(form, text="Recapitulare", variable=self.plan_revision).grid(
            row=1,
            column=3,
            sticky="w",
            padx=6,
        )
        Checkbutton(form, text="Quiz days", variable=self.plan_quiz).grid(
            row=1,
            column=4,
            sticky="w",
            padx=6,
        )

        Label(form, text="Data examen YYYY-MM-DD optional").grid(
            row=2,
            column=0,
            sticky="w",
            padx=6,
            pady=4,
        )
        self.plan_exam_date = StringVar()
        Entry(form, textvariable=self.plan_exam_date, width=18).grid(
            row=2,
            column=1,
            sticky="w",
            padx=6,
        )
        Button(form, text="Refresh documente", command=self.refresh_documents).grid(
            row=2,
            column=3,
            sticky="w",
            padx=6,
        )
        Button(form, text="Genereaza plan", command=self.generate_session_plan).grid(
            row=2,
            column=4,
            sticky="w",
            padx=6,
        )

        docs_frame = Frame(tab)
        docs_frame.pack(fill=X, padx=8, pady=4)
        Label(docs_frame, text="Documente incluse").pack(anchor="w")
        self.plan_documents = Listbox(docs_frame, selectmode="extended", height=7)
        scrollbar = Scrollbar(docs_frame, orient="vertical", command=self.plan_documents.yview)
        self.plan_documents.configure(yscrollcommand=scrollbar.set)
        self.plan_documents.pack(side=LEFT, fill=X, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        self.plan_output = ScrolledText(tab, wrap="word")
        self.plan_output.pack(fill=BOTH, expand=True, padx=8, pady=8)

    def set_status(self, message: str) -> None:
        self.status.set(message)

    def run_task(self, label: str, worker, on_success) -> None:
        self.set_status(label)

        def wrapped() -> None:
            try:
                result = worker()
                self.task_queue.put(("success", (on_success, result)))
            except Exception as exc:
                self.task_queue.put(("error", exc))

        threading.Thread(target=wrapped, daemon=True).start()

    def _poll_queue(self) -> None:
        try:
            while True:
                event, payload = self.task_queue.get_nowait()
                if event == "success":
                    callback, result = payload
                    callback(result)
                    self.set_status("Gata.")
                else:
                    self.set_status("Eroare.")
                    messagebox.showerror(APP_TITLE, str(payload))
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def test_connection(self) -> None:
        self.save_current_settings()
        self.run_task(
            "Testez conexiunea...",
            lambda: self.api().request("GET", "/health"),
            self.show_health,
        )

    def show_health(self, data: dict) -> None:
        urls = data.get("urls") or {}
        message = (
            f"Status: {data.get('status')}\n"
            f"Ollama pe server: {'da' if data.get('ollama') else 'nu'}\n"
            f"Documente: {data.get('documents')}\n"
            f"Chunks: {data.get('chunks')}\n"
            f"LAN: {urls.get('lan') or '-'}\n"
            f"Tailscale: {urls.get('tailscale') or '-'}"
        )
        messagebox.showinfo(APP_TITLE, message)

    def refresh_documents(self) -> None:
        self.run_task(
            "Citesc documentele de pe server...",
            lambda: self.api().request("GET", "/documents"),
            self.load_documents_into_ui,
        )

    def load_documents_into_ui(self, data: dict) -> None:
        self.documents = data.get("documents") or []
        names = ["Global"] + [item["file_name"] for item in self.documents]
        self.question_document_box.configure(values=names)
        if self.question_document.get() not in names:
            self.question_document.set("Global")

        subjects = sorted(
            {
                item.get("subject") or item.get("discipline") or "Necunoscuta"
                for item in self.documents
            }
        )
        self.plan_subject_box.configure(values=subjects)
        if subjects and self.plan_subject.get() not in subjects:
            self.plan_subject.set(subjects[0])
        self.update_plan_documents()
        self.set_status(f"{len(self.documents)} documente incarcate de pe server.")

    def update_plan_documents(self) -> None:
        subject = self.plan_subject.get()
        self.plan_documents.delete(0, END)
        for item in self.documents:
            item_subject = item.get("subject") or item.get("discipline") or "Necunoscuta"
            if subject and item_subject != subject:
                continue
            course = item.get("course") or item.get("file_name")
            self.plan_documents.insert(END, f"{course} | {item['file_name']}")

    def selected_plan_document_names(self) -> list[str]:
        selected = []
        for index in self.plan_documents.curselection():
            value = self.plan_documents.get(index)
            selected.append(value.split(" | ", 1)[-1])
        return selected

    def ask_question(self) -> None:
        question = self.question_input.get("1.0", END).strip()
        if not question:
            messagebox.showwarning(APP_TITLE, "Scrie o intrebare.")
            return
        document = self.question_document.get()
        payload = {
            **self.base_payload(),
            "question": question,
            "document": None if document == "Global" else document,
        }
        self.run_task(
            "Astept raspunsul serverului...",
            lambda: self.api().request("POST", "/ask", payload),
            lambda data: self.write_answer(self.question_output, data),
        )

    def write_answer(self, widget: ScrolledText, data: dict) -> None:
        lines = [data.get("answer", "")]
        sources = data.get("sources") or []
        if sources:
            lines.append("\nSurse:")
            for source in sources:
                page = f", pagina {source.get('page')}" if source.get("page") else ""
                lines.append(f"- {source.get('file_name')}{page}")
        widget.delete("1.0", END)
        widget.insert(END, "\n".join(lines))

    def generate_flashcards(self) -> None:
        payload = {
            **self.base_payload(),
            "topic": self.flashcards_topic.get().strip() or "toate documentele",
            "count": int(self.flashcards_count.get()),
        }
        self.run_task(
            "Generez flashcards pe server...",
            lambda: self.api().request("POST", "/flashcards", payload),
            self.show_flashcards,
        )

    def show_flashcards(self, data: dict) -> None:
        lines = []
        for index, item in enumerate(data.get("items") or [], start=1):
            lines.append(f"{index}. {item.get('front', '')}")
            lines.append(f"   {item.get('back', '')}")
            if item.get("source_hint"):
                lines.append(f"   Sursa: {item['source_hint']}")
            lines.append("")
        if not lines:
            lines.append("Serverul nu a returnat flashcards.")
        self.flashcards_output.delete("1.0", END)
        self.flashcards_output.insert(END, "\n".join(lines))

    def generate_quiz(self) -> None:
        payload = {
            **self.base_payload(),
            "topic": self.quiz_topic.get().strip() or "toate documentele",
            "count": int(self.quiz_count.get()),
        }
        self.run_task(
            "Generez quiz pe server...",
            lambda: self.api().request("POST", "/quiz", payload),
            self.show_quiz,
        )

    def show_quiz(self, data: dict) -> None:
        lines = []
        for index, item in enumerate(data.get("items") or [], start=1):
            options = item.get("options") or []
            answer_index = item.get("answer_index", -1)
            lines.append(f"{index}. {item.get('question', '')}")
            for option_index, option in enumerate(options):
                prefix = "  *" if option_index == answer_index else "   "
                lines.append(f"{prefix} {option}")
            if item.get("explanation"):
                lines.append(f"   Explicatie: {item['explanation']}")
            lines.append("")
        if not lines:
            lines.append("Serverul nu a returnat quiz.")
        self.quiz_output.delete("1.0", END)
        self.quiz_output.insert(END, "\n".join(lines))

    def refresh_progress(self) -> None:
        self.run_task(
            "Citesc progresul de pe server...",
            lambda: self.api().request("GET", "/progress"),
            self.show_progress,
        )

    def show_progress(self, data: dict) -> None:
        summary = data.get("summary") or {}
        lines = [
            "Rezumat progres",
            f"- Intrebari: {summary.get('total_questions', 0)}",
            f"- Documente studiate: {summary.get('documents_studied', 0)}",
            f"- Subiecte slabe: {summary.get('weak_topics', 0)}",
            f"- Medie quiz: {summary.get('quiz_average') or 'N/A'}",
            f"- Streak: {summary.get('study_streak', 0)} zile",
            "",
            "Recomandari:",
        ]
        for item in data.get("recommendations") or []:
            lines.append(
                f"- {item.get('topic')} | prioritate {item.get('priority')}: {item.get('reasons')}"
            )
        lines.append("\nSubiecte slabe:")
        for item in data.get("weak_topics") or []:
            lines.append(f"- {item.get('topic')} ({item.get('status')})")
        lines.append("\nPlanuri salvate:")
        for item in data.get("session_plans") or []:
            lines.append(f"- {item.get('title')} | {item.get('total_estimated_hours')}h")
        self.progress_output.delete("1.0", END)
        self.progress_output.insert(END, "\n".join(lines))

    def generate_session_plan(self) -> None:
        documents = self.selected_plan_document_names()
        if not documents:
            messagebox.showwarning(APP_TITLE, "Selecteaza cel putin un document.")
            return
        exam_date = self.plan_exam_date.get().strip() or None
        payload = {
            **self.base_payload(),
            "subject": self.plan_subject.get().strip() or "Materie",
            "documents": documents,
            "number_of_days": int(self.plan_days.get()),
            "hours_per_day": float(self.plan_hours.get()),
            "difficulty_level": self.plan_difficulty.get(),
            "include_revision_days": self.plan_revision.get(),
            "include_quiz_days": self.plan_quiz.get(),
            "exam_date": exam_date,
            "auto_hours": self.plan_auto_hours.get(),
        }
        self.run_task(
            "Generez planul pe server...",
            lambda: self.api().request("POST", "/session-plan", payload),
            self.show_session_plan,
        )

    def show_session_plan(self, data: dict) -> None:
        plan = data.get("plan") or {}
        lines = [
            plan.get("title", "Plan sesiune"),
            f"Azi: {plan.get('today')}",
            f"Examen: {plan.get('exam_date') or 'nesetat'}",
            f"Zile disponibile: {plan.get('available_study_days')}",
            f"Ore recomandate/zi: {plan.get('recommended_hours_per_day')}",
            f"Ore folosite/zi: {plan.get('hours_per_day')}",
            f"Workload total: {plan.get('total_workload_hours')}h",
        ]
        if plan.get("warning"):
            lines.append(f"\nAvertisment: {plan['warning']}")
        lines.append("\nZile:")
        for day in plan.get("days") or []:
            lines.append(
                f"\nZiua {day.get('day_number')} | {day.get('date')} | "
                f"{day.get('estimated_hours')}h"
            )
            for task in day.get("tasks") or []:
                lines.append(f"- {task}")
            weak = ", ".join(day.get("weak_topics") or [])
            if weak:
                lines.append(f"  De repetat: {weak}")
        self.plan_output.delete("1.0", END)
        self.plan_output.insert(END, "\n".join(lines))


def main() -> None:
    root = Tk()
    CopilotClientApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
