from __future__ import annotations

import os
import threading
import uuid
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import app as study_app
from study_memory import (
    get_dashboard_summary,
    get_preference,
    get_quiz_results,
    get_recent_questions,
    get_recommended_topics,
    get_session_plans,
    get_studied_documents,
    get_weak_topics,
    save_session_plan,
)


app = FastAPI(
    title="Faculty Copilot API",
    version="0.4.0",
    description=(
        "Server local pentru clienti Faculty Copilot. Ollama, ChromaDB si "
        "inferenta ruleaza numai pe PC-ul server."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
INFERENCE_LOCK = threading.Lock()
AnswerMode = Literal["Auto", "Strict", "Analiză", "Profesor", "Strategie de învățare"]


@app.exception_handler(study_app.GenerationTimeoutError)
async def generation_timeout_handler(
    request: Request,
    error: study_app.GenerationTimeoutError,
) -> JSONResponse:
    return JSONResponse(status_code=504, content={"detail": str(error)})


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=5000)
    document: str | None = None
    model: str | None = None
    response_mode: Literal["Fast", "Balanced", "Accurate"] = "Balanced"
    answer_mode: AnswerMode = "Auto"
    session_id: str | None = None
    username: str | None = None


class GenerationRequest(BaseModel):
    topic: str = Field(default="toate documentele", min_length=1, max_length=1000)
    count: int = Field(default=5, ge=1, le=20)
    model: str | None = None
    response_mode: Literal["Fast", "Balanced", "Accurate"] = "Balanced"
    session_id: str | None = None
    username: str | None = None


class CompareRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=1000)
    documents: list[str] = Field(min_length=2, max_length=12)
    model: str | None = None
    response_mode: Literal["Fast", "Balanced", "Accurate"] = "Balanced"
    answer_mode: AnswerMode = "Auto"
    max_chunks_per_course: int | None = Field(default=None, ge=1, le=12)
    max_answer_tokens: int | None = Field(default=None, ge=300, le=3000)
    session_id: str | None = None
    username: str | None = None


class SessionPlanRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    documents: list[str] = Field(min_length=1, max_length=50)
    number_of_days: int = Field(ge=1, le=180)
    hours_per_day: float = Field(default=2.0, ge=0.5, le=12.0)
    difficulty_level: Literal["low", "medium", "high"] = "medium"
    include_revision_days: bool = True
    include_quiz_days: bool = True
    exam_date: date | None = None
    auto_hours: bool = False
    session_id: str | None = None
    username: str | None = None


def configure_model(
    model_name: str | None = None,
    response_mode: str = study_app.DEFAULT_RESPONSE_MODE,
) -> str:
    if not study_app.ollama_is_running():
        raise HTTPException(
            status_code=503,
            detail="Ollama nu raspunde pe PC-ul server.",
        )
    selected_model = (
        model_name
        or get_preference(study_app.MEMORY_DB_PATH, "llm_model")
        or study_app.DEFAULT_LLM_MODEL
    )
    study_app.configure_llama_index(selected_model, response_mode)
    return selected_model


def require_documents() -> None:
    if study_app.count_indexed_chunks() == 0:
        raise HTTPException(
            status_code=409,
            detail="Nu exista documente indexate.",
        )


def resolve_document(reference: str | None) -> dict | None:
    if not reference:
        return None

    normalized_reference = study_app.searchable_text(reference)
    for document in study_app.get_indexed_documents():
        file_name = document.get("file_name", "")
        if normalized_reference in {
            study_app.searchable_text(file_name),
            study_app.searchable_text(Path(file_name).stem),
        }:
            return document

    detected = study_app.detect_document_reference(reference)
    if detected:
        return detected
    raise HTTPException(status_code=404, detail=f"Document negasit: {reference}")


def api_session_id(session_id: str | None) -> str:
    return f"api-{session_id or uuid.uuid4()}"


def request_session_id(session_id: str | None, username: str | None = None) -> str:
    if username:
        safe_username = study_app.searchable_text(username).replace(" ", "-") or "user"
        return f"client-{safe_username}-{session_id or uuid.uuid4()}"
    return api_session_id(session_id)


def response_payload(response) -> dict:
    return {
        "answer": study_app.clean_model_text(str(response)),
        "sources": study_app.response_source_records(response),
        "debug": response.debug if isinstance(response, study_app.StudyResponse) else {},
    }


@app.get("/health")
def health() -> dict:
    study_app.ensure_project_dirs()
    ollama_running = study_app.ollama_is_running()
    host = os.environ.get("FACULTY_COPILOT_API_HOST", "0.0.0.0")
    port = int(os.environ.get("FACULTY_COPILOT_API_PORT", "8000"))
    lan_ip = study_app.get_lan_ip()
    tailscale_ip = study_app.get_tailscale_ip()
    https_enabled = bool(
        os.environ.get("FACULTY_COPILOT_SSL_CERTFILE")
        and os.environ.get("FACULTY_COPILOT_SSL_KEYFILE")
    )
    scheme = "https" if https_enabled else "http"
    return {
        "status": "ok" if ollama_running else "degraded",
        "ollama": ollama_running,
        "api": True,
        "api_host": host,
        "api_port": port,
        "https": https_enabled,
        "urls": {
            "local": f"{scheme}://localhost:{port}",
            "lan": f"{scheme}://{lan_ip}:{port}" if lan_ip else None,
            "tailscale": f"{scheme}://{tailscale_ip}:{port}" if tailscale_ip else None,
            "docs": f"{scheme}://localhost:{port}/docs",
        },
        "project_root": str(study_app.PROJECT_ROOT),
        "documents": len(study_app.get_indexed_documents()),
        "chunks": study_app.count_indexed_chunks(),
        "inference_location": "server_pc",
        "client_rule": "clients_do_not_run_ollama_or_chromadb",
    }


@app.get("/documents")
def documents() -> dict:
    study_app.ensure_project_dirs()
    return {"documents": study_app.get_indexed_documents()}


@app.get("/progress")
def progress() -> dict:
    study_app.ensure_project_dirs()
    return {
        "summary": get_dashboard_summary(study_app.MEMORY_DB_PATH),
        "studied_documents": get_studied_documents(study_app.MEMORY_DB_PATH),
        "weak_topics": get_weak_topics(study_app.MEMORY_DB_PATH, limit=50),
        "recent_questions": get_recent_questions(study_app.MEMORY_DB_PATH, limit=20),
        "quiz_results": get_quiz_results(study_app.MEMORY_DB_PATH, limit=30),
        "recommendations": get_recommended_topics(study_app.MEMORY_DB_PATH, limit=10),
        "session_plans": get_session_plans(study_app.MEMORY_DB_PATH, limit=10),
    }


@app.post("/ask")
def ask(request: AskRequest) -> dict:
    study_app.ensure_project_dirs()
    require_documents()
    document = resolve_document(request.document)

    with INFERENCE_LOCK:
        model = configure_model(request.model, request.response_mode)
        if study_app.is_document_inventory_question(request.question):
            answer = study_app.indexed_documents_answer()
            study_app.save_answer_to_memory(
                request.question,
                answer,
                session_id=request_session_id(request.session_id, request.username),
            )
            return {"answer": answer, "sources": [], "debug": {}, "model": model}

        response = study_app.query_documents(
            request.question,
            document_override=document,
            response_mode=request.response_mode,
            answer_mode=request.answer_mode,
        )
        payload = response_payload(response)
        study_app.save_answer_to_memory(
            request.question,
            payload["answer"],
            response=response,
            selected_document=document,
            session_id=request_session_id(request.session_id, request.username),
        )
        payload["model"] = model
        return payload


@app.post("/quiz")
def quiz(request: GenerationRequest) -> dict:
    study_app.ensure_project_dirs()
    require_documents()
    with INFERENCE_LOCK:
        model = configure_model(request.model, request.response_mode)
        items, response = study_app.generate_quiz(
            request.topic,
            request.count,
            response_mode=request.response_mode,
        )
        payload = response_payload(response)
        study_app.save_answer_to_memory(
            f"Genereaza quiz despre: {request.topic}",
            payload["answer"],
            response=response,
            session_id=request_session_id(request.session_id, request.username),
        )
        return {
            "items": items,
            "sources": payload["sources"],
            "debug": payload["debug"],
            "model": model,
        }


@app.post("/flashcards")
def flashcards(request: GenerationRequest) -> dict:
    study_app.ensure_project_dirs()
    require_documents()
    with INFERENCE_LOCK:
        model = configure_model(request.model, request.response_mode)
        items, response = study_app.generate_flashcards(
            request.topic,
            request.count,
            response_mode=request.response_mode,
        )
        payload = response_payload(response)
        study_app.save_answer_to_memory(
            f"Genereaza flashcarduri despre: {request.topic}",
            payload["answer"],
            response=response,
            session_id=request_session_id(request.session_id, request.username),
        )
        return {
            "items": items,
            "sources": payload["sources"],
            "debug": payload["debug"],
            "model": model,
        }


@app.post("/compare")
def compare(request: CompareRequest) -> dict:
    study_app.ensure_project_dirs()
    require_documents()
    documents = [resolve_document(reference) for reference in request.documents]
    if any(document is None for document in documents):
        raise HTTPException(status_code=404, detail="Un document selectat nu a fost gasit.")

    with INFERENCE_LOCK:
        model = configure_model(request.model, request.response_mode)
        response = study_app.compare_courses_hierarchically(
            topic=request.topic,
            documents=documents,
            response_mode=request.response_mode,
            answer_mode=request.answer_mode,
            max_chunks_per_course=request.max_chunks_per_course,
            max_answer_tokens=request.max_answer_tokens,
        )
        payload = response_payload(response)
        study_app.save_answer_to_memory(
            f"Comparatie intre cursuri: {request.topic}",
            payload["answer"],
            response=response,
            infer_document=False,
            session_id=request_session_id(request.session_id, request.username),
        )
        payload["model"] = model
        return payload


@app.post("/session-plan")
def session_plan(request: SessionPlanRequest) -> dict:
    study_app.ensure_project_dirs()
    require_documents()
    documents = [resolve_document(reference) for reference in request.documents]
    if any(document is None for document in documents):
        raise HTTPException(status_code=404, detail="Un document selectat nu a fost gasit.")

    plan = study_app.build_session_plan(
        subject=request.subject,
        documents=documents,
        number_of_days=request.number_of_days,
        hours_per_day=request.hours_per_day,
        difficulty_level=request.difficulty_level,
        include_revision_days=request.include_revision_days,
        include_quiz_days=request.include_quiz_days,
        exam_date_value=request.exam_date,
        auto_hours=request.auto_hours,
    )
    plan_id = save_session_plan(
        study_app.MEMORY_DB_PATH,
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
        total_estimated_hours=plan["total_workload_hours"],
    )
    plan["id"] = plan_id
    plan["inference_location"] = "server_pc"
    return {"plan": plan}
